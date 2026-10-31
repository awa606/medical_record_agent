from __future__ import annotations

import os
import sqlite3
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.auth import assert_owner_or_admin
from app.db import (
    append_audit_event,
    get_connection,
    list_audit_chain_entries,
    verify_audit_chain,
)
from app.main import app
from app.services import privacy
from app.services.llm.base import LLMProviderUnavailableError
from app.services.llm.factory import create_llm_provider
from scripts.edge_sqlite_backup import backup_sqlite, restore_sqlite
from tests.auth_helpers import authenticated_request, create_user, login_as_admin, login_as_user


ENV_KEYS = [
    "MEDICAL_RECORD_AGENT_DB",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME",
    "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD",
    "MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP",
    "RECORD_PROVIDER_MODE",
    "LLM_PROVIDER",
    "MRA_ANONYMIZE",
    "MRA_ALLOW_UNREDACTED_OUTBOUND",
    "MRA_AUDIT_HMAC_KEY",
    "MRA_METRICS_TOKEN",
    "ONLINE_LLM_API_BASE",
    "ONLINE_LLM_API_KEY",
    "ONLINE_LLM_MODEL",
    "ONLINE_LLM_PROFILE",
]


class IsolatedEnvTestCase(unittest.TestCase):
    """Each test gets its own SQLite file and a clean environment."""

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


class OwnerCheckFailClosedTests(IsolatedEnvTestCase):
    def test_http_request_without_user_is_401(self):
        class FakeRequest:
            state = type("State", (), {})()

        with self.assertRaises(HTTPException) as raised:
            assert_owner_or_admin(1, FakeRequest())
        self.assertEqual(raised.exception.status_code, 401)

    def test_direct_call_without_request_is_internal_not_http(self):
        # No HTTP boundary: FastAPI never delivers None, so this path is only
        # reachable from tests or maintenance code.
        self.assertIsNone(assert_owner_or_admin(1, None))

    def test_owner_and_admin_are_allowed_other_user_is_403(self):
        owner = {
            "id": 7,
            "username": "owner",
            "display_name": "Owner",
            "role": "doctor",
            "department_id": None,
            "is_active": True,
        }
        self.assertIsNone(assert_owner_or_admin(7, authenticated_request(owner)))
        admin = {**owner, "id": 1, "username": "admin", "role": "admin"}
        self.assertIsNone(assert_owner_or_admin(7, authenticated_request(admin)))
        intruder = {**owner, "id": 8, "username": "other"}
        with self.assertRaises(HTTPException) as raised:
            assert_owner_or_admin(7, authenticated_request(intruder))
        self.assertEqual(raised.exception.status_code, 403)

    def test_anonymous_encounter_read_is_401(self):
        client = TestClient(app)
        response = client.get("/api/encounters")
        self.assertEqual(response.status_code, 401)


class DepartmentScopingTests(IsolatedEnvTestCase):
    def _create_encounter(self, client: TestClient, doctor: str) -> dict:
        login_as_user(client, username=doctor)
        response = client.post("/api/encounters", json={"patient_display_name": "张示例"})
        self.assertEqual(response.status_code, 200, response.text)
        client.post("/api/auth/logout")
        return response.json()

    def test_department_is_stored_exposed_and_enforced(self):
        client = TestClient(app)
        create_user(client, username="doc-a", department_id="dept-cardio")
        create_user(
            client,
            username="desk-cardio",
            role="intake",
            display_name="Cardio Desk",
            department_id="dept-cardio",
        )
        create_user(
            client,
            username="desk-neuro",
            role="intake",
            display_name="Neuro Desk",
            department_id="dept-neuro",
        )

        encounter = self._create_encounter(client, "doc-a")
        self.assertEqual(encounter["department_id"], "dept-cardio")
        encounter_id = encounter["id"]

        login_as_user(client, username="desk-cardio")
        listed = client.get("/api/encounters", params={"mine": "false"})
        self.assertEqual(listed.status_code, 200)
        self.assertIn(encounter_id, {row["id"] for row in listed.json()["encounters"]})
        self.assertEqual(client.get(f"/api/encounters/{encounter_id}").status_code, 200)
        client.post("/api/auth/logout")

        login_as_user(client, username="desk-neuro")
        listed = client.get("/api/encounters", params={"mine": "false"})
        self.assertNotIn(encounter_id, {row["id"] for row in listed.json()["encounters"]})
        self.assertEqual(client.get(f"/api/encounters/{encounter_id}").status_code, 403)
        client.post("/api/auth/logout")

        admin = login_as_admin(client)
        self.assertEqual(admin["role"], "admin")
        users = {row["username"]: row for row in client.get("/api/auth/users").json()["users"]}
        self.assertEqual(users["doc-a"]["department_id"], "dept-cardio")
        self.assertEqual(users["desk-neuro"]["department_id"], "dept-neuro")

    def test_doctor_without_department_keeps_owner_only_visibility(self):
        client = TestClient(app)
        create_user(client, username="doc-b")
        encounter = self._create_encounter(client, "doc-b")
        self.assertIsNone(encounter["department_id"])

    def test_legacy_null_department_is_scoped_by_owning_doctor(self):
        client = TestClient(app)
        create_user(client, username="doc-legacy", department_id="dept-cardio")
        create_user(client, username="desk-cardio", role="intake", department_id="dept-cardio")
        create_user(client, username="desk-neuro", role="intake", department_id="dept-neuro")
        legacy = self._create_encounter(client, "doc-legacy")
        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("UPDATE encounter SET department_id = NULL WHERE id = ?", (legacy["id"],))
            connection.commit()

        login_as_user(client, username="desk-cardio")
        ids = {row["id"] for row in client.get("/api/encounters", params={"mine": "false"}).json()["encounters"]}
        self.assertIn(legacy["id"], ids)
        self.assertEqual(client.get(f"/api/encounters/{legacy['id']}").status_code, 200)
        client.post("/api/auth/logout")

        login_as_user(client, username="desk-neuro")
        ids = {row["id"] for row in client.get("/api/encounters", params={"mine": "false"}).json()["encounters"]}
        self.assertNotIn(legacy["id"], ids)
        self.assertEqual(client.get(f"/api/encounters/{legacy['id']}").status_code, 403)

    def test_intake_can_check_in_but_doctor_keeps_start_and_complete(self):
        client = TestClient(app)
        create_user(client, username="doc-flow", department_id="dept-cardio")
        create_user(client, username="desk-flow", role="intake", department_id="dept-cardio")
        encounter = self._create_encounter(client, "doc-flow")

        login_as_user(client, username="desk-flow")
        self.assertEqual(
            client.post(f"/api/encounters/{encounter['id']}/check-in").status_code, 200
        )
        self.assertEqual(
            client.post(f"/api/encounters/{encounter['id']}/start").status_code, 403
        )
        self.assertEqual(
            client.post(f"/api/encounters/{encounter['id']}/complete").status_code, 403
        )
        client.post("/api/auth/logout")

        login_as_user(client, username="doc-flow")
        self.assertEqual(client.post(f"/api/encounters/{encounter['id']}/start").status_code, 200)
        self.assertEqual(client.post(f"/api/encounters/{encounter['id']}/complete").status_code, 200)


class AuditChainTests(IsolatedEnvTestCase):
    def test_chain_verifies_and_detects_tampering(self):
        append_audit_event("auth_login", {"username": "a"}, resource_type="auth_user", resource_id=1)
        append_audit_event("auth_login", {"username": "b"}, resource_type="auth_user", resource_id=2)
        append_audit_event("auth_logout", {"session_revoked": True}, resource_type="auth_session")

        report = verify_audit_chain()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["entries"], 3)

        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("UPDATE audit_chain SET payload = ? WHERE id = 2", ('{"username":"evil"}',))
            connection.commit()

        tampered = verify_audit_chain()
        self.assertFalse(tampered["ok"])
        self.assertEqual(tampered["broken_at"], 2)
        self.assertEqual(tampered["reason"], "hash_mismatch")

    def test_hmac_key_mode_and_missing_key(self):
        os.environ["MRA_AUDIT_HMAC_KEY"] = "test-audit-key"
        entry = append_audit_event("auth_login", {"username": "a"}, actor_user_id=1)
        self.assertEqual(entry["key_id"], "hmac-sha256")
        self.assertTrue(verify_audit_chain()["ok"])

        os.environ.pop("MRA_AUDIT_HMAC_KEY")
        report = verify_audit_chain()
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "missing_hmac_key")

    def test_login_appends_chain_entry(self):
        client = TestClient(app)
        login_as_admin(client)
        entries = list_audit_chain_entries()
        self.assertTrue(any(item["event_type"] == "auth_login" for item in entries))
        self.assertTrue(verify_audit_chain()["ok"])

    def test_task_audit_log_is_chained(self):
        from app.db import create_audit_log, create_task

        task_id = create_task(input_type="text", status="CREATED", input_text="发热两天")
        create_audit_log(task_id, "manual_check", {"ok": True}, actor_user_id=1)
        entries = list_audit_chain_entries()
        self.assertTrue(any(item["event_type"] == "manual_check" for item in entries))
        self.assertTrue(verify_audit_chain()["ok"])

    def test_low_level_audit_insert_is_chained(self):
        from app.db import create_task
        from app.db.sqlite import _insert_audit_log_row

        task_id = create_task(input_type="text", status="CREATED", input_text="发热两天")
        connection = get_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            _insert_audit_log_row(
                connection,
                task_id=task_id,
                event_type="doctor_review_saved",
                event_detail={"revision_no": 2},
            )
            connection.commit()
        finally:
            connection.close()
        self.assertTrue(
            any(item["event_type"] == "doctor_review_saved" for item in list_audit_chain_entries())
        )
        self.assertTrue(verify_audit_chain()["ok"])

    def test_prev_hash_mismatch_is_reported(self):
        append_audit_event("auth_login", {"username": "a"})
        append_audit_event("auth_login", {"username": "b"})
        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("UPDATE audit_chain SET prev_hash = ? WHERE id = 2", ("deadbeef",))
            connection.commit()
        report = verify_audit_chain()
        self.assertFalse(report["ok"])
        self.assertEqual(report["reason"], "prev_hash_mismatch")
        self.assertEqual(report["stored_prev_hash"], "deadbeef")


class PrivacyGateTests(IsolatedEnvTestCase):
    def test_online_provider_defaults_to_redaction(self):
        os.environ["LLM_PROVIDER"] = "online"
        self.assertTrue(privacy.enabled())

    def test_mock_demo_keeps_legacy_default(self):
        self.assertFalse(privacy.enabled())

    def test_explicitly_disabled_online_provider_is_refused(self):
        os.environ.update(
            {
                "LLM_PROVIDER": "online",
                "MRA_ANONYMIZE": "0",
                "ONLINE_LLM_API_BASE": "https://llm.example.test",
                "ONLINE_LLM_API_KEY": "test-key",
                "ONLINE_LLM_MODEL": "test-model",
            }
        )
        with self.assertRaises(LLMProviderUnavailableError) as raised:
            create_llm_provider("online")
        self.assertIn("ONLINE_ANONYMIZATION_REQUIRED", str(raised.exception))

    def test_explicit_risk_acceptance_allows_online_provider(self):
        os.environ.update(
            {
                "LLM_PROVIDER": "online",
                "MRA_ANONYMIZE": "0",
                "MRA_ALLOW_UNREDACTED_OUTBOUND": "1",
                "ONLINE_LLM_API_BASE": "https://llm.example.test",
                "ONLINE_LLM_API_KEY": "test-key",
                "ONLINE_LLM_MODEL": "test-model",
            }
        )
        provider = create_llm_provider("online")
        self.assertEqual(provider.name, "online")


class MetricsTests(IsolatedEnvTestCase):
    def test_metrics_requires_admin_and_exposes_aggregates(self):
        client = TestClient(app)
        self.assertEqual(client.get("/metrics").status_code, 401)

        login_as_admin(client)
        response = client.get("/metrics")
        self.assertEqual(response.status_code, 200, response.text)
        body = response.text
        self.assertIn("mra_patient_total", body)
        self.assertIn("mra_audit_chain_valid", body)
        self.assertIn("mra_audit_chain_entries", body)
        self.assertNotIn("张示例", body)

    def test_metrics_token_allows_scraping_without_session(self):
        os.environ["MRA_METRICS_TOKEN"] = "scrape-token"
        client = TestClient(app)
        unauthorized = client.get("/metrics")
        self.assertEqual(unauthorized.status_code, 401)
        authorized = client.get("/metrics", headers={"Authorization": "Bearer scrape-token"})
        self.assertEqual(authorized.status_code, 200, authorized.text)

    def test_non_ascii_bearer_is_rejected_cleanly(self):
        from starlette.requests import Request

        from app.api.runtime import _metrics_authorized

        os.environ["MRA_METRICS_TOKEN"] = "scrape-token"
        # httpx refuses to send non-ASCII header values, so build the request
        # at the ASGI layer where Starlette decodes headers as latin-1.
        request = Request(
            {
                "type": "http",
                "method": "GET",
                "path": "/metrics",
                "headers": [(b"authorization", b"Bearer caf\xe9")],
                "query_string": b"",
                "app": None,
            }
        )
        self.assertFalse(_metrics_authorized(request))


class RestoreScriptTests(IsolatedEnvTestCase):
    def _make_db(self, path: Path) -> None:
        with closing(sqlite3.connect(path)) as connection:
            connection.execute("CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)")
            connection.execute("INSERT INTO sample (value) VALUES ('ok')")
            connection.commit()

    def test_restore_verifies_counts_and_keeps_rollback_copy(self):
        db_path = Path(self.temp_dir.name) / "source.sqlite3"
        backup_path = Path(self.temp_dir.name) / "backups" / "source.backup.sqlite3"
        self._make_db(db_path)

        backup_sqlite(db_path, backup_path)
        with closing(sqlite3.connect(db_path)) as connection:
            connection.execute("INSERT INTO sample (value) VALUES ('mutation')")
            connection.commit()

        restore_sqlite(backup_path, db_path, force=True)

        with closing(sqlite3.connect(db_path)) as connection:
            values = [row[0] for row in connection.execute("SELECT value FROM sample ORDER BY id")]
        self.assertEqual(values, ["ok"])
        rollbacks = list(db_path.parent.glob(f"{db_path.name}.pre-restore-*"))
        self.assertEqual(len(rollbacks), 1)

    def test_restore_refuses_without_force(self):
        db_path = Path(self.temp_dir.name) / "source.sqlite3"
        backup_path = Path(self.temp_dir.name) / "backup.sqlite3"
        self._make_db(db_path)
        backup_sqlite(db_path, backup_path)
        with self.assertRaises(FileExistsError):
            restore_sqlite(backup_path, db_path)

    def test_corrupt_backup_is_refused_before_touching_target(self):
        db_path = Path(self.temp_dir.name) / "source.sqlite3"
        bad_backup = Path(self.temp_dir.name) / "bad.sqlite3"
        self._make_db(db_path)
        bad_backup.write_bytes(b"not a sqlite database")
        with self.assertRaises((sqlite3.DatabaseError, RuntimeError)):
            restore_sqlite(bad_backup, db_path, force=True)
        with closing(sqlite3.connect(db_path)) as connection:
            values = [row[0] for row in connection.execute("SELECT value FROM sample")]
        self.assertEqual(values, ["ok"])

    def test_restore_requires_named_tables(self):
        db_path = Path(self.temp_dir.name) / "source.sqlite3"
        backup_path = Path(self.temp_dir.name) / "backup.sqlite3"
        self._make_db(db_path)
        backup_sqlite(db_path, backup_path)
        with self.assertRaises(RuntimeError):
            restore_sqlite(backup_path, db_path, force=True, require_tables=["patient"])


class InitDbConcurrencyTests(IsolatedEnvTestCase):
    def test_concurrent_first_init_does_not_raise(self):
        import threading

        errors: list[BaseException] = []

        def worker() -> None:
            try:
                from app.db import init_db

                init_db()
            except BaseException as exc:  # noqa: BLE001 - collect every failure
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])


class SecurityApiTests(IsolatedEnvTestCase):
    def test_audit_chain_endpoint_is_admin_only(self):
        client = TestClient(app)
        self.assertEqual(client.get("/api/security/audit-chain").status_code, 401)

        create_user(client, username="security-doctor")
        login_as_user(client, username="security-doctor")
        self.assertEqual(client.get("/api/security/audit-chain").status_code, 403)
        client.post("/api/auth/logout")

        login_as_admin(client)
        response = client.get("/api/security/audit-chain", params={"limit": 5})
        self.assertEqual(response.status_code, 200, response.text)
        body = response.json()
        self.assertTrue(body["verification"]["ok"])
        self.assertGreaterEqual(len(body["entries"]), 1)
        self.assertTrue(any(item["event_type"] == "auth_login" for item in body["entries"]))

    def test_verify_endpoint_reports_tampering(self):
        client = TestClient(app)
        login_as_admin(client)
        self.assertEqual(client.get("/api/security/audit-chain/verify").json()["ok"], True)

        with closing(sqlite3.connect(os.environ["MEDICAL_RECORD_AGENT_DB"])) as connection:
            connection.execute("UPDATE audit_chain SET payload = '{}' WHERE id = 1")
            connection.commit()

        result = client.get("/api/security/audit-chain/verify").json()
        self.assertFalse(result["ok"])
        self.assertEqual(result["reason"], "hash_mismatch")


if __name__ == "__main__":
    unittest.main()
