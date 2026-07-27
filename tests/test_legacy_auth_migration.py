from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch

from app.agents import MedicalRecordOrchestrator
from app.api.tasks import TaskApprovalRequest, approve_task
from app.db import (
    create_user as db_create_user,
    get_active_approval_for_task,
    get_connection,
    get_task,
    get_task_encounter,
    get_user_by_username,
    init_db,
    list_record_revisions_for_task,
)
from tests.approval_helpers import approval_payload_for_fields


class LegacyAuthMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "MEDICAL_RECORD_AGENT_DB",
                "MEDICAL_RECORD_AGENT_OUTPUT_DIR",
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
                "ONLINE_LLM_API_BASE",
                "ONLINE_LLM_API_KEY",
                "ONLINE_LLM_MODEL",
                "OLLAMA_BASE_URL",
                "OLLAMA_MODEL",
            ]
        }
        for key in [
            "LLM_PROVIDER",
            "RECORD_PROVIDER_MODE",
            "ONLINE_LLM_API_BASE",
            "ONLINE_LLM_API_KEY",
            "ONLINE_LLM_MODEL",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
        ]:
            os.environ.pop(key, None)
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(self.temp_dir.name, "legacy-auth.sqlite3")
        os.environ["MEDICAL_RECORD_AGENT_OUTPUT_DIR"] = os.path.join(self.temp_dir.name, "outputs")

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def _prepare_legacy_rc2_database(self) -> dict[str, int]:
        init_db()
        doctor_a_id = db_create_user(
            username="legacy-doctor-a",
            password="doctor-pass-123",
            display_name="Legacy Doctor A",
            role="doctor",
            department_id="fever",
        )
        doctor_b_id = db_create_user(
            username="legacy-doctor-b",
            password="doctor-pass-123",
            display_name="Legacy Doctor B",
            role="doctor",
            department_id="resp",
        )
        result = MedicalRecordOrchestrator().run_from_text("patient has fever for three days")
        task_id = int(result["task_id"])
        approve_task(task_id, TaskApprovalRequest(**approval_payload_for_fields(result["fields"], task_id=task_id)))
        encounter = get_task_encounter(task_id)
        revision = list_record_revisions_for_task(task_id)[0]

        with closing(get_connection()) as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE auth_user_rc2 (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    display_name TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('admin', 'doctor')),
                    password_hash TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT
                )
                """
            )
            connection.execute(
                """
                INSERT INTO auth_user_rc2 (
                    id, username, display_name, role, password_hash,
                    is_active, created_at, updated_at, last_login_at
                )
                SELECT id, username, display_name, role, password_hash,
                       is_active, created_at, updated_at, last_login_at
                FROM auth_user
                WHERE role IN ('admin', 'doctor')
                """
            )
            connection.execute("DROP TABLE auth_user")
            connection.execute("ALTER TABLE auth_user_rc2 RENAME TO auth_user")
            connection.execute("CREATE INDEX idx_auth_user_role_rc2 ON auth_user(role)")
            connection.commit()
            connection.execute("PRAGMA foreign_keys=ON")

        return {
            "doctor_a_id": doctor_a_id,
            "doctor_b_id": doctor_b_id,
            "task_id": task_id,
            "encounter_id": int(encounter["id"]),
            "revision_id": int(revision["id"]),
        }

    def _auth_user_schema(self) -> str:
        with closing(get_connection()) as connection:
            row = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'auth_user'"
            ).fetchone()
        return row["sql"]

    def test_migrate_legacy_auth_role_check(self):
        self._prepare_legacy_rc2_database()
        self.assertNotIn("frontdesk", self._auth_user_schema())

        init_db()

        schema = self._auth_user_schema()
        self.assertIn("frontdesk", schema)
        self.assertIn("intake", schema)
        self.assertIn("intake_admin", schema)

    def test_migration_preserves_existing_users(self):
        ids = self._prepare_legacy_rc2_database()
        init_db()

        self.assertEqual(get_user_by_username("legacy-doctor-a")["id"], ids["doctor_a_id"])
        self.assertEqual(get_user_by_username("legacy-doctor-b")["id"], ids["doctor_b_id"])
        self.assertEqual(get_user_by_username("admin")["role"], "admin")

    def test_migration_preserves_existing_clinical_data(self):
        ids = self._prepare_legacy_rc2_database()
        init_db()

        self.assertEqual(get_task(ids["task_id"])["id"], ids["task_id"])
        self.assertEqual(get_task_encounter(ids["task_id"])["id"], ids["encounter_id"])
        self.assertEqual(list_record_revisions_for_task(ids["task_id"])[0]["id"], ids["revision_id"])
        self.assertIsNotNone(get_active_approval_for_task(ids["task_id"]))

    def test_frontdesk_role_can_be_created_after_migration(self):
        self._prepare_legacy_rc2_database()
        init_db()

        user_id = db_create_user(
            username="frontdesk-after-migration",
            password="frontdesk-pass-123",
            display_name="Frontdesk",
            role="frontdesk",
            department_id="fever",
        )
        self.assertEqual(get_user_by_username("frontdesk-after-migration")["id"], user_id)

    def test_intake_role_can_be_created_after_migration(self):
        self._prepare_legacy_rc2_database()
        init_db()

        user_id = db_create_user(
            username="intake-after-migration",
            password="intake-pass-123",
            display_name="Intake",
            role="intake",
            department_id="fever",
        )
        self.assertEqual(get_user_by_username("intake-after-migration")["id"], user_id)

    def test_migration_is_idempotent(self):
        ids = self._prepare_legacy_rc2_database()
        init_db()
        first_schema = self._auth_user_schema()
        first_user_count = self._auth_user_count()

        init_db()

        self.assertEqual(self._auth_user_schema(), first_schema)
        self.assertEqual(self._auth_user_count(), first_user_count)
        self.assertEqual(get_task(ids["task_id"])["id"], ids["task_id"])

    def test_migration_preserves_indexes_and_unique_constraints(self):
        self._prepare_legacy_rc2_database()
        init_db()

        with closing(get_connection()) as connection:
            index_names = {
                row["name"]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'index' AND tbl_name = 'auth_user'"
                ).fetchall()
            }
        self.assertIn("idx_auth_user_role_rc2", index_names)
        with self.assertRaises(ValueError):
            db_create_user(
                username="legacy-doctor-a",
                password="doctor-pass-123",
                display_name="Duplicate",
                role="doctor",
            )

    def test_migration_passes_foreign_key_check(self):
        self._prepare_legacy_rc2_database()
        init_db()

        with closing(get_connection()) as connection:
            self.assertEqual(connection.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")

    def test_migration_rolls_back_on_copy_failure(self):
        self._prepare_legacy_rc2_database()
        before_schema = self._auth_user_schema()
        with patch(
            "app.db.sqlite._copy_auth_user_rows_for_migration",
            side_effect=RuntimeError("copy failed"),
        ):
            with self.assertRaises(RuntimeError):
                init_db()

        self.assertEqual(self._auth_user_schema(), before_schema)
        self.assertNotIn("frontdesk", self._auth_user_schema())
        self.assertEqual(get_user_by_username("legacy-doctor-a")["username"], "legacy-doctor-a")

    def _auth_user_count(self) -> int:
        with closing(get_connection()) as connection:
            return int(connection.execute("SELECT COUNT(*) AS count FROM auth_user").fetchone()["count"])


if __name__ == "__main__":
    unittest.main()
