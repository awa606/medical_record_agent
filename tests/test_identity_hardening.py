from __future__ import annotations

import json
import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import append_audit_event
from app.main import app
from app.services.audit_anchor import append_anchor, read_last_anchor, verify_with_anchor
from scripts.audit_anchor import main as anchor_main
from tests.auth_helpers import create_user, login_as_admin, login_as_user


ENV_KEYS = [
    "MEDICAL_RECORD_AGENT_DB",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
    "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
    "RECORD_PROVIDER_MODE",
    "LLM_PROVIDER",
    "MRA_AUDIT_HMAC_KEY",
    "MRA_AUDIT_ANCHOR_FILE",
    "MRA_AUDIT_ANCHOR_KEY",
    "MRA_REQUIRE_AUDIT_ANCHOR",
]

WRONG_PASSWORD = "definitely-wrong-password"


class IsolatedTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(self.temp_dir.name) / "app.sqlite3")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        for attempt in range(5):
            try:
                self.temp_dir.cleanup()
                break
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.2)


class LoginLockoutTests(IsolatedTestCase):
    def _login(self, client: TestClient, username: str, password: str):
        return client.post("/api/auth/login", json={"username": username, "password": password})

    def test_five_failures_throttle_guessing_without_locking_out_the_doctor(self):
        client = TestClient(app)
        create_user(client, username="lockme")
        for _ in range(4):
            response = self._login(client, "lockme", WRONG_PASSWORD)
            self.assertEqual(response.status_code, 401)
            self.assertIn("remaining_attempts", response.json()["detail"])
        fifth = self._login(client, "lockme", WRONG_PASSWORD)
        self.assertEqual(fifth.status_code, 429)
        self.assertIn("Retry-After", fifth.headers)
        # A correct password still works: the lock throttles guessing, it does
        # not let an attacker lock a doctor out of their own account.
        allowed = self._login(client, "lockme", "doctor-pass-123")
        self.assertEqual(allowed.status_code, 200)
        # The successful login cleared the failure counter.
        self.assertEqual(self._login(client, "lockme", WRONG_PASSWORD).status_code, 401)

    def test_lock_is_scoped_to_username(self):
        client = TestClient(app)
        create_user(client, username="lockme")
        create_user(client, username="other-user")
        for _ in range(5):
            self._login(client, "lockme", WRONG_PASSWORD)
        self.assertEqual(self._login(client, "lockme", WRONG_PASSWORD).status_code, 429)
        self.assertEqual(self._login(client, "other-user", WRONG_PASSWORD).status_code, 401)

    def test_successful_login_clears_failure_counter(self):
        client = TestClient(app)
        create_user(client, username="clearme")
        self.assertEqual(self._login(client, "clearme", WRONG_PASSWORD).status_code, 401)
        self.assertEqual(self._login(client, "clearme", WRONG_PASSWORD).status_code, 401)
        self.assertEqual(self._login(client, "clearme", "doctor-pass-123").status_code, 200)
        after = self._login(client, "clearme", WRONG_PASSWORD)
        self.assertEqual(after.status_code, 401)
        self.assertEqual(after.json()["detail"]["remaining_attempts"], 4)

    def test_unknown_user_does_not_leak_existence(self):
        client = TestClient(app)
        missing = self._login(client, "no-such-user", WRONG_PASSWORD)
        self.assertEqual(missing.status_code, 401)
        self.assertEqual(missing.json()["detail"]["message"], "Invalid username or password")


class UserAdminTests(IsolatedTestCase):
    def test_disable_revokes_existing_session_and_blocks_login(self):
        admin_client = TestClient(app)
        doctor_client = TestClient(app)
        doctor = create_user(admin_client, username="doc-disable", department_id="dept-a")
        login_as_user(doctor_client, username="doc-disable")
        self.assertEqual(doctor_client.get("/api/auth/me").status_code, 200)

        login_as_admin(admin_client)
        patched = admin_client.patch(f"/api/auth/users/{doctor['id']}", json={"is_active": False})
        self.assertEqual(patched.status_code, 200, patched.text)
        self.assertFalse(patched.json()["is_active"])

        self.assertEqual(doctor_client.get("/api/auth/me").status_code, 401)
        relogin = doctor_client.post(
            "/api/auth/login",
            json={"username": "doc-disable", "password": "doctor-pass-123"},
        )
        self.assertEqual(relogin.status_code, 401)

        enabled = admin_client.patch(f"/api/auth/users/{doctor['id']}", json={"is_active": True})
        self.assertEqual(enabled.status_code, 200)
        self.assertEqual(
            doctor_client.post(
                "/api/auth/login",
                json={"username": "doc-disable", "password": "doctor-pass-123"},
            ).status_code,
            200,
        )

    def test_role_change_revokes_sessions_and_department_update_is_visible(self):
        admin_client = TestClient(app)
        doctor_client = TestClient(app)
        doctor = create_user(admin_client, username="doc-role", department_id="dept-a")
        login_as_user(doctor_client, username="doc-role")

        login_as_admin(admin_client)
        changed = admin_client.patch(
            f"/api/auth/users/{doctor['id']}",
            json={"role": "intake", "department_id": "dept-b"},
        )
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(changed.json()["role"], "intake")
        self.assertEqual(changed.json()["department_id"], "dept-b")
        self.assertEqual(doctor_client.get("/api/auth/me").status_code, 401)

        login_as_user(doctor_client, username="doc-role")
        me = doctor_client.get("/api/auth/me").json()
        self.assertEqual(me["role"], "intake")
        self.assertEqual(me["department_id"], "dept-b")

    def test_admin_cannot_disable_self_and_doctor_cannot_patch(self):
        admin_client = TestClient(app)
        admin = login_as_admin(admin_client)
        self.assertEqual(
            admin_client.patch(f"/api/auth/users/{admin['id']}", json={"is_active": False}).status_code,
            400,
        )
        admin_client.post("/api/auth/logout")

        create_user(admin_client, username="doc-plain")
        login_as_user(admin_client, username="doc-plain")
        self.assertEqual(
            admin_client.patch(f"/api/auth/users/{admin['id']}", json={"is_active": False}).status_code,
            403,
        )

    def test_last_active_admin_cannot_be_demoted(self):
        admin_client = TestClient(app)
        admin = login_as_admin(admin_client)
        demoted = admin_client.patch(f"/api/auth/users/{admin['id']}", json={"role": "doctor"})
        self.assertEqual(demoted.status_code, 400)
        self.assertIn("at least one active admin", demoted.json()["detail"].lower())

    def test_second_admin_can_be_demoted(self):
        admin_client = TestClient(app)
        login_as_admin(admin_client)
        created = admin_client.post(
            "/api/auth/users",
            json={
                "username": "admin-two",
                "password": "admin-two-pass-123",
                "display_name": "Admin Two",
                "role": "admin",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        demoted = admin_client.patch(
            f"/api/auth/users/{created.json()['id']}",
            json={"role": "doctor"},
        )
        self.assertEqual(demoted.status_code, 200, demoted.text)
        self.assertEqual(demoted.json()["role"], "doctor")

    def test_null_is_active_cannot_disable_the_last_admin(self):
        admin_client = TestClient(app)
        admin = login_as_admin(admin_client)
        response = admin_client.patch(
            f"/api/auth/users/{admin['id']}",
            json={"is_active": None},
        )
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(admin_client.get("/api/auth/me").status_code, 200)

    def test_null_is_active_cannot_disable_another_user(self):
        admin_client = TestClient(app)
        doctor = create_user(admin_client, username="doc-null")
        login_as_admin(admin_client)
        response = admin_client.patch(
            f"/api/auth/users/{doctor['id']}",
            json={"is_active": None},
        )
        self.assertEqual(response.status_code, 400, response.text)
        users = {
            row["username"]: row
            for row in admin_client.get("/api/auth/users").json()["users"]
        }
        self.assertTrue(users["doc-null"]["is_active"])

    def test_null_display_name_and_role_are_rejected(self):
        admin_client = TestClient(app)
        doctor = create_user(admin_client, username="doc-null-fields")
        login_as_admin(admin_client)
        self.assertEqual(
            admin_client.patch(
                f"/api/auth/users/{doctor['id']}",
                json={"display_name": None},
            ).status_code,
            400,
        )
        self.assertEqual(
            admin_client.patch(
                f"/api/auth/users/{doctor['id']}",
                json={"role": None},
            ).status_code,
            400,
        )


class AuditAnchorTests(IsolatedTestCase):
    def test_anchor_detects_tail_truncation(self):
        anchor_file = Path(self.temp_dir.name) / "anchors.jsonl"
        for index in range(3):
            append_audit_event("auth_login", {"username": f"user-{index}"})
        entry = append_anchor(anchor_file)
        self.assertEqual(entry["entries"], 3)
        self.assertEqual(read_last_anchor(anchor_file)["head_hash"], entry["head_hash"])

        self.assertTrue(verify_with_anchor(anchor_file)["ok"])
        append_audit_event("auth_login", {"username": "after-anchor"})
        report = verify_with_anchor(anchor_file)
        self.assertTrue(report["ok"])
        self.assertTrue(report["anchor"]["checked"])

        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            # Deleting only post-anchor rows is legitimate; going below the
            # anchored entry count is what the anchor must catch.
            connection.execute("DELETE FROM audit_chain WHERE id >= 3")
            connection.commit()

        truncated = verify_with_anchor(anchor_file)
        self.assertFalse(truncated["ok"])
        self.assertEqual(truncated["reason"], "anchor_truncated")
        self.assertEqual(truncated["anchored_entries"], 3)

    def test_no_anchor_file_reports_unchecked(self):
        report = verify_with_anchor(Path(self.temp_dir.name) / "missing.jsonl")
        self.assertTrue(report["ok"])
        self.assertEqual(report["anchor"], {"checked": False, "reason": "no_anchor"})

    def test_anchor_cli_roundtrip_and_truncation_exit_code(self):
        anchor_file = Path(self.temp_dir.name) / "cli-anchors.jsonl"
        append_audit_event("auth_login", {"username": "cli"})
        self.assertEqual(anchor_main(["anchor", "--file", str(anchor_file)]), 0)
        self.assertEqual(anchor_main(["verify", "--file", str(anchor_file)]), 0)

        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("DELETE FROM audit_chain")
            connection.commit()
        self.assertEqual(anchor_main(["verify", "--file", str(anchor_file)]), 1)

    def test_zero_entry_anchor_is_invalid(self):
        anchor_file = Path(self.temp_dir.name) / "zero.jsonl"
        append_audit_event("auth_login", {"username": "zero"})
        anchor_file.write_text('{"entries": 0, "head_hash": "0"}\n', encoding="utf-8")
        report = verify_with_anchor(anchor_file)
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "anchor_invalid")

    def test_signed_anchor_rejects_forgery(self):
        os.environ["MRA_AUDIT_ANCHOR_KEY"] = "anchor-signing-key"
        anchor_file = Path(self.temp_dir.name) / "signed.jsonl"
        append_audit_event("auth_login", {"username": "signed-a"})
        append_audit_event("auth_login", {"username": "signed-b"})
        entry = append_anchor(anchor_file)
        self.assertIn("signature", entry)
        self.assertTrue(verify_with_anchor(anchor_file)["ok"])

        forged = json.loads(anchor_file.read_text(encoding="utf-8").strip())
        forged["entries"] = 1
        anchor_file.write_text(json.dumps(forged) + "\n", encoding="utf-8")
        report = verify_with_anchor(anchor_file)
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "anchor_signature_invalid")

    def test_strict_mode_requires_an_anchor(self):
        os.environ["MRA_REQUIRE_AUDIT_ANCHOR"] = "1"
        report = verify_with_anchor(Path(self.temp_dir.name) / "missing.jsonl")
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "anchor_missing")

    def test_metrics_chain_gauge_flips_when_the_tail_is_removed(self):
        anchor_file = Path(self.temp_dir.name) / "metrics-anchors.jsonl"
        os.environ["MRA_AUDIT_ANCHOR_FILE"] = str(anchor_file)
        client = TestClient(app)
        login_as_admin(client)
        append_audit_event("auth_login", {"username": "metric-a"})
        append_audit_event("auth_login", {"username": "metric-b"})
        append_anchor(anchor_file)

        body = client.get("/metrics").text
        self.assertIn("mra_audit_chain_valid 1", body)
        self.assertIn("mra_audit_anchor_checked 1", body)

        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("DELETE FROM audit_chain WHERE id >= 2")
            connection.commit()

        body = client.get("/metrics").text
        self.assertIn("mra_audit_chain_valid 0", body)


if __name__ == "__main__":
    unittest.main()
