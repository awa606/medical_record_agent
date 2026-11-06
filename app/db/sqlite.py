from __future__ import annotations

import json
import hashlib
import hmac
import os
import sqlite3
import time
from contextlib import closing
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "medical_record_agent.sqlite3"
TERMINAL_TASK_STATUSES = {"WAITING_DOCTOR_REVIEW", "DONE", "FAILED"}
CHECK_IN_STATUSES = {"registered", "checked_in", "in_progress", "completed", "cancelled"}
DEPARTMENT_VISIBLE_ROLES = {"intake", "intake_admin", "frontdesk"}
AUDIT_CHAIN_GENESIS = "0" * 64
LOGIN_FAILURE_THRESHOLD = 5
LOGIN_FAILURE_WINDOW_SECONDS = 900
LOGIN_LOCK_SECONDS = 300
USER_ADMIN_FIELDS = {"display_name", "role", "department_id", "is_active"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def get_db_path() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_DB", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=5)
    try:
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
    except Exception:
        # Never leak a half-configured handle: on Windows an open file blocks
        # backup, restore and temporary-directory cleanup.
        connection.close()
        raise
    return connection


def init_db() -> None:
    """Create or migrate the schema, tolerating a short startup lock race."""
    for attempt in range(3):
        try:
            _init_db_once()
            return
        except sqlite3.OperationalError as exc:
            if "locked" not in str(exc).lower() or attempt == 2:
                raise
            time.sleep(0.05 * (attempt + 1))


def _init_db_once() -> None:
    with closing(get_connection()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS agent_task (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                input_type TEXT NOT NULL,
                input_text TEXT,
                status TEXT NOT NULL,
                current_stage TEXT,
                result_json TEXT,
                error_message TEXT,
                retry_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS agent_task_step (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                step_name TEXT NOT NULL,
                status TEXT NOT NULL,
                attempt_no INTEGER NOT NULL DEFAULT 1,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                duration_ms INTEGER,
                input_snapshot_json TEXT,
                output_snapshot_json TEXT,
                error_message TEXT,
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                event_detail TEXT,
                created_at TEXT NOT NULL,
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS audit_chain (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                actor_user_id INTEGER,
                payload TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                entry_hash TEXT NOT NULL,
                key_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_audit_chain_created_at ON audit_chain(created_at);

            CREATE TABLE IF NOT EXISTS auth_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'doctor', 'frontdesk', 'intake', 'intake_admin')),
                department_id TEXT,
                password_hash TEXT NOT NULL,
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                last_login_at TEXT
            );

            CREATE TABLE IF NOT EXISTS auth_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                token_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked_at TEXT,
                FOREIGN KEY(user_id) REFERENCES auth_user(id)
            );

            CREATE TABLE IF NOT EXISTS auth_login_attempt (
                username TEXT NOT NULL,
                client_ip TEXT NOT NULL,
                failures INTEGER NOT NULL DEFAULT 0,
                first_failed_at TEXT,
                locked_until TEXT,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (username, client_ip)
            );

            CREATE TABLE IF NOT EXISTS patient (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                deidentified_id TEXT NOT NULL UNIQUE,
                display_name TEXT,
                created_by_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS encounter (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_id INTEGER NOT NULL,
                doctor_user_id INTEGER,
                task_id INTEGER,
                status TEXT NOT NULL,
                check_in_status TEXT NOT NULL DEFAULT 'checked_in',
                current_revision_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(patient_id) REFERENCES patient(id),
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS record_revision (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                task_id INTEGER,
                revision_no INTEGER NOT NULL,
                source TEXT NOT NULL,
                content_hash TEXT,
                fields_json TEXT,
                draft_text TEXT,
                safety_check_json TEXT,
                quality_report_json TEXT,
                result_json TEXT,
                created_by_user_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(encounter_id) REFERENCES encounter(id),
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS approval (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                task_id INTEGER,
                approved_by_user_id INTEGER,
                content_hash TEXT,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                invalidated_at TEXT,
                invalidation_reason TEXT,
                FOREIGN KEY(encounter_id) REFERENCES encounter(id),
                FOREIGN KEY(revision_id) REFERENCES record_revision(id),
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS approval_item (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                approval_id INTEGER NOT NULL,
                task_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                item_key TEXT NOT NULL,
                action TEXT NOT NULL,
                status TEXT NOT NULL,
                high_risk_confirmed INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                actor_user_id INTEGER,
                created_at TEXT NOT NULL,
                FOREIGN KEY(approval_id) REFERENCES approval(id),
                FOREIGN KEY(revision_id) REFERENCES record_revision(id),
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );

            CREATE TABLE IF NOT EXISTS export_event (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                encounter_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                approval_id INTEGER NOT NULL,
                task_id INTEGER,
                exported_by_user_id INTEGER,
                exports_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(encounter_id) REFERENCES encounter(id),
                FOREIGN KEY(revision_id) REFERENCES record_revision(id),
                FOREIGN KEY(approval_id) REFERENCES approval(id),
                FOREIGN KEY(task_id) REFERENCES agent_task(id)
            );
            """
        )
        _migrate_schema(connection)
        _bootstrap_admin_user(connection)
        connection.commit()


def _migrate_schema(connection: sqlite3.Connection) -> None:
    _migrate_auth_user_role_check(connection)
    _ensure_column(connection, "auth_user", "department_id", "TEXT")
    _ensure_column(connection, "agent_task", "input_text", "TEXT")
    _ensure_column(connection, "agent_task", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "agent_task", "completed_at", "TEXT")
    _ensure_column(connection, "agent_task", "owner_user_id", "INTEGER")
    _ensure_column(connection, "agent_task", "encounter_id", "INTEGER")
    _ensure_column(connection, "agent_task", "current_record_revision_id", "INTEGER")
    _ensure_column(connection, "encounter", "check_in_status", "TEXT NOT NULL DEFAULT 'checked_in'")
    _ensure_column(connection, "patient", "department_id", "TEXT")
    _ensure_column(connection, "encounter", "department_id", "TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_encounter_department ON encounter(department_id)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_patient_department ON patient(department_id)"
    )
    _ensure_column(connection, "agent_task_step", "attempt_no", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(connection, "agent_task_step", "input_snapshot_json", "TEXT")
    _ensure_column(connection, "agent_task_step", "output_snapshot_json", "TEXT")
    _ensure_column(connection, "record_revision", "content_hash", "TEXT")
    _ensure_column(connection, "approval", "content_hash", "TEXT")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS approval_item (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            approval_id INTEGER NOT NULL,
            task_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            item_type TEXT NOT NULL,
            item_key TEXT NOT NULL,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            high_risk_confirmed INTEGER NOT NULL DEFAULT 0,
            note TEXT,
            actor_user_id INTEGER,
            created_at TEXT NOT NULL,
            FOREIGN KEY(approval_id) REFERENCES approval(id),
            FOREIGN KEY(revision_id) REFERENCES record_revision(id),
            FOREIGN KEY(task_id) REFERENCES agent_task(id)
        )
        """
    )
    for row in connection.execute(
        "SELECT id, result_json FROM record_revision WHERE content_hash IS NULL OR content_hash = ''"
    ).fetchall():
        try:
            result = json.loads(row["result_json"] or "{}")
        except json.JSONDecodeError:
            result = {}
        connection.execute(
            "UPDATE record_revision SET content_hash = ? WHERE id = ?",
            (record_content_hash(result), row["id"]),
        )
    connection.execute(
        """
        UPDATE approval
        SET content_hash = (
            SELECT record_revision.content_hash
            FROM record_revision
            WHERE record_revision.id = approval.revision_id
        )
        WHERE content_hash IS NULL OR content_hash = ''
        """
    )


AUTH_USER_ROLE_CHECK = "CHECK(role IN ('admin', 'doctor', 'frontdesk', 'intake', 'intake_admin'))"
AUTH_USER_REQUIRED_COLUMNS: dict[str, str] = {
    "id": "INTEGER PRIMARY KEY AUTOINCREMENT",
    "username": "TEXT NOT NULL UNIQUE",
    "display_name": "TEXT NOT NULL",
    "role": f"TEXT NOT NULL {AUTH_USER_ROLE_CHECK}",
    "department_id": "TEXT",
    "password_hash": "TEXT NOT NULL",
    "is_active": "INTEGER NOT NULL DEFAULT 1",
    "created_at": "TEXT NOT NULL",
    "updated_at": "TEXT NOT NULL",
    "last_login_at": "TEXT",
}


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _auth_user_role_check_needs_migration(connection: sqlite3.Connection) -> bool:
    row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'auth_user'"
    ).fetchone()
    if row is None or not row["sql"]:
        return False
    sql = str(row["sql"]).lower()
    columns = {item["name"] for item in connection.execute("PRAGMA table_info(auth_user)").fetchall()}
    required_roles_present = all(role in sql for role in ("frontdesk", "intake", "intake_admin"))
    required_columns_present = set(AUTH_USER_REQUIRED_COLUMNS).issubset(columns)
    return not (required_roles_present and required_columns_present)


def _column_definition_from_info(column: sqlite3.Row) -> str:
    definition = column["type"] or "TEXT"
    if column["notnull"]:
        definition += " NOT NULL"
    if column["dflt_value"] is not None:
        definition += f" DEFAULT {column['dflt_value']}"
    return definition


def _copy_auth_user_rows_for_migration(
    connection: sqlite3.Connection,
    *,
    new_columns: list[str],
    old_columns: set[str],
) -> None:
    now = utc_now()
    select_parts: list[str] = []
    for column in new_columns:
        if column in old_columns:
            select_parts.append(_quote_identifier(column))
        elif column == "department_id":
            select_parts.append("NULL")
        elif column == "is_active":
            select_parts.append("1")
        elif column in {"created_at", "updated_at"}:
            select_parts.append("?")
        elif column == "last_login_at":
            select_parts.append("NULL")
        else:
            select_parts.append("NULL")
    timestamp_params = [now for column in new_columns if column not in old_columns and column in {"created_at", "updated_at"}]
    connection.execute(
        f"""
        INSERT INTO auth_user_new ({", ".join(_quote_identifier(column) for column in new_columns)})
        SELECT {", ".join(select_parts)}
        FROM auth_user
        """,
        timestamp_params,
    )


def _migrate_auth_user_role_check(connection: sqlite3.Connection) -> None:
    if not _auth_user_role_check_needs_migration(connection):
        return
    if connection.in_transaction:
        connection.commit()

    old_foreign_keys = int(connection.execute("PRAGMA foreign_keys").fetchone()[0])
    table_info = connection.execute("PRAGMA table_info(auth_user)").fetchall()
    old_columns = {column["name"] for column in table_info}
    indexes = connection.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type = 'index'
          AND tbl_name = 'auth_user'
          AND sql IS NOT NULL
        ORDER BY name
        """
    ).fetchall()

    new_definitions = dict(AUTH_USER_REQUIRED_COLUMNS)
    for column in table_info:
        name = column["name"]
        if name not in new_definitions:
            new_definitions[name] = _column_definition_from_info(column)
    new_columns = list(new_definitions)

    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute("DROP TABLE IF EXISTS auth_user_new")
        connection.execute(
            f"""
            CREATE TABLE auth_user_new (
                {", ".join(f"{_quote_identifier(name)} {definition}" for name, definition in new_definitions.items())}
            )
            """
        )
        _copy_auth_user_rows_for_migration(
            connection,
            new_columns=new_columns,
            old_columns=old_columns,
        )
        connection.execute("DROP TABLE auth_user")
        connection.execute("ALTER TABLE auth_user_new RENAME TO auth_user")
        for index in indexes:
            connection.execute(index["sql"])
        foreign_key_issues = connection.execute("PRAGMA foreign_key_check").fetchall()
        if foreign_key_issues:
            raise RuntimeError(f"auth_user migration failed foreign_key_check: {len(foreign_key_issues)}")
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity is None or integrity[0] != "ok":
            raise RuntimeError(f"auth_user migration failed integrity_check: {integrity[0] if integrity else 'no result'}")
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute(f"PRAGMA foreign_keys={old_foreign_keys}")


def _ensure_column(
    connection: sqlite3.Connection,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name in columns:
        return
    try:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
    except sqlite3.OperationalError as exc:
        # Two processes may run the migration at the same moment. The loser
        # sees "duplicate column name"; that is success, not a 500.
        if "duplicate column name" not in str(exc).lower():
            raise


def _bootstrap_admin_user(connection: sqlite3.Connection) -> None:
    if os.environ.get("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", "1").lower() in {"0", "false", "no"}:
        return
    existing = connection.execute("SELECT COUNT(*) AS count FROM auth_user").fetchone()
    if existing is not None and int(existing["count"]) > 0:
        return

    username = os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", "admin123456")
    display_name = os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_DISPLAY_NAME", "Local Admin")
    mode = os.environ.get("RECORD_PROVIDER_MODE", "demo").strip().lower()
    using_default_password = "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD" not in os.environ
    if mode in {"live", "edge"} and (using_default_password or _is_weak_password(password, username)):
        raise RuntimeError("Edge/Live mode requires a strong MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD")

    from app.services.auth import hash_password

    now = utc_now()
    connection.execute(
        """
        INSERT INTO auth_user (
            username, display_name, role, password_hash,
            is_active, created_at, updated_at, last_login_at
        )
        VALUES (?, ?, 'admin', ?, 1, ?, ?, NULL)
        """,
        (username, display_name, hash_password(password), now, now),
    )


def _is_weak_password(password: str, username: str) -> bool:
    lowered = password.lower()
    return (
        len(password) < 10
        or lowered in {"admin", "admin123", "admin123456", "password", "12345678"}
        or lowered == username.lower()
    )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


def json_or_none(value: Any) -> str | None:
    if value is None:
        return None
    return json_dumps(value)


RECORD_CONTENT_KEYS = {
    "fields",
    "draft",
    "safety_check",
    "quality_report",
    "degraded",
    "degraded_messages",
    "llm_trace",
}

REVIEW_METADATA_KEYS = {
    "confirmed_by_doctor",
    "doctor_review_status",
    "doctor_review_note",
    "deleted_by_doctor",
    "high_risk_confirmed_by_doctor",
    "approval",
    "approval_summary",
    "approved",
    "reviewed",
    "record_revision",
    "exports",
    "export_event",
}


def _normalize_record_content(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _normalize_record_content(item)
            for key, item in sorted(value.items())
            if key not in REVIEW_METADATA_KEYS
        }
    if isinstance(value, list):
        return [_normalize_record_content(item) for item in value]
    return value


def record_content_hash(result: dict[str, Any]) -> str:
    content = {
        key: result.get(key)
        for key in sorted(RECORD_CONTENT_KEYS)
        if key in result
    }
    normalized = _normalize_record_content(content)
    payload = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class StaleRecordRevisionError(ValueError):
    def __init__(
        self,
        *,
        expected_revision_id: int | None,
        expected_content_hash: str | None,
        current_revision_id: int | None,
        current_content_hash: str | None,
    ) -> None:
        super().__init__("Record revision is stale")
        self.expected_revision_id = expected_revision_id
        self.expected_content_hash = expected_content_hash
        self.current_revision_id = current_revision_id
        self.current_content_hash = current_content_hash


def create_task(
    input_type: str,
    status: str,
    current_stage: str | None = None,
    input_text: str | None = None,
) -> int:
    init_db()
    now = utc_now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO agent_task (
                input_type, input_text, status, current_stage, result_json,
                error_message, retry_count, created_at, updated_at, completed_at
            )
            VALUES (?, ?, ?, ?, NULL, NULL, 0, ?, ?, NULL)
            """,
            (input_type, input_text, status, current_stage, now, now),
        )
        task_id = int(cursor.lastrowid)
        connection.commit()
    return task_id


def set_task_owner(task_id: int, owner_user_id: int | None) -> None:
    init_db()
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE agent_task
            SET owner_user_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (owner_user_id, utc_now(), task_id),
        )
        if owner_user_id is not None:
            now = utc_now()
            connection.execute(
                """
                UPDATE encounter
                SET doctor_user_id = ?,
                    updated_at = ?
                WHERE doctor_user_id IS NULL
                  AND (
                    task_id = ?
                    OR id = (SELECT encounter_id FROM agent_task WHERE id = ?)
                  )
                """,
                (owner_user_id, now, task_id, task_id),
            )
        connection.commit()


def _update_task_workflow_links(
    connection: sqlite3.Connection,
    *,
    task_id: int,
    encounter_id: int | None = None,
    revision_id: int | None = None,
) -> None:
    connection.execute(
        """
        UPDATE agent_task
        SET encounter_id = COALESCE(?, encounter_id),
            current_record_revision_id = COALESCE(?, current_record_revision_id),
            updated_at = ?
        WHERE id = ?
        """,
        (encounter_id, revision_id, utc_now(), task_id),
    )


def _validate_check_in_status(status: str) -> str:
    normalized = (status or "").strip().lower()
    if normalized not in CHECK_IN_STATUSES:
        raise ValueError(f"Unsupported check_in_status: {status}")
    return normalized


def ensure_task_encounter(
    task_id: int,
    *,
    actor_user_id: int | None = None,
    patient_label: str | None = None,
) -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        if task["encounter_id"] is not None:
            encounter = connection.execute(
                "SELECT * FROM encounter WHERE id = ?",
                (task["encounter_id"],),
            ).fetchone()
            if encounter is not None:
                return dict(encounter)

        now = utc_now()
        doctor_user_id = actor_user_id if actor_user_id is not None else task["owner_user_id"]
        deidentified_id = f"SIM-{task_id:06d}"
        display_name = patient_label or "模拟患者"
        patient = connection.execute(
            "SELECT * FROM patient WHERE deidentified_id = ?",
            (deidentified_id,),
        ).fetchone()
        if patient is None:
            cursor = connection.execute(
                """
                INSERT INTO patient (
                    deidentified_id, display_name, created_by_user_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (deidentified_id, display_name, actor_user_id, now, now),
            )
            patient_id = int(cursor.lastrowid)
        else:
            patient_id = int(patient["id"])

        cursor = connection.execute(
            """
            INSERT INTO encounter (
                patient_id, doctor_user_id, task_id, status, check_in_status,
                current_revision_id, created_at, updated_at
            )
            VALUES (?, ?, ?, 'draft', 'in_progress', NULL, ?, ?)
            """,
            (patient_id, doctor_user_id, task_id, now, now),
        )
        encounter_id = int(cursor.lastrowid)
        _update_task_workflow_links(connection, task_id=task_id, encounter_id=encounter_id)
        connection.commit()
        encounter = connection.execute("SELECT * FROM encounter WHERE id = ?", (encounter_id,)).fetchone()
        return dict(encounter)


def _invalidate_active_approvals(
    connection: sqlite3.Connection,
    *,
    encounter_id: int,
    reason: str,
) -> int:
    now = utc_now()
    cursor = connection.execute(
        """
        UPDATE approval
        SET status = 'invalidated',
            invalidated_at = ?,
            invalidation_reason = ?
        WHERE encounter_id = ?
          AND invalidated_at IS NULL
          AND status = 'active'
        """,
        (now, reason, encounter_id),
    )
    return int(cursor.rowcount or 0)


def _ensure_task_encounter_with_connection(
    connection: sqlite3.Connection,
    *,
    task_id: int,
    actor_user_id: int | None = None,
    patient_label: str | None = None,
) -> dict[str, Any]:
    task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
    if task is None:
        raise ValueError(f"Task not found: {task_id}")
    if task["encounter_id"] is not None:
        encounter = connection.execute(
            "SELECT * FROM encounter WHERE id = ?",
            (task["encounter_id"],),
        ).fetchone()
        if encounter is not None:
            return dict(encounter)

    now = utc_now()
    doctor_user_id = actor_user_id if actor_user_id is not None else task["owner_user_id"]
    deidentified_id = f"SIM-{task_id:06d}"
    display_name = patient_label or "模拟患者"
    patient = connection.execute(
        "SELECT * FROM patient WHERE deidentified_id = ?",
        (deidentified_id,),
    ).fetchone()
    if patient is None:
        cursor = connection.execute(
            """
            INSERT INTO patient (
                deidentified_id, display_name, created_by_user_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (deidentified_id, display_name, actor_user_id, now, now),
        )
        patient_id = int(cursor.lastrowid)
    else:
        patient_id = int(patient["id"])

    cursor = connection.execute(
        """
        INSERT INTO encounter (
            patient_id, doctor_user_id, task_id, status, check_in_status,
            current_revision_id, created_at, updated_at
        )
        VALUES (?, ?, ?, 'draft', 'in_progress', NULL, ?, ?)
        """,
        (patient_id, doctor_user_id, task_id, now, now),
    )
    encounter_id = int(cursor.lastrowid)
    _update_task_workflow_links(connection, task_id=task_id, encounter_id=encounter_id)
    encounter = connection.execute("SELECT * FROM encounter WHERE id = ?", (encounter_id,)).fetchone()
    return dict(encounter)


def _insert_record_revision_row(
    connection: sqlite3.Connection,
    *,
    task_id: int,
    encounter_id: int,
    result: dict[str, Any],
    actor_user_id: int | None,
    source: str,
) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(revision_no), 0) AS max_revision FROM record_revision WHERE encounter_id = ?",
        (encounter_id,),
    ).fetchone()
    revision_no = int(row["max_revision"]) + 1 if row is not None else 1
    now = utc_now()
    content_hash = record_content_hash(result)
    cursor = connection.execute(
        """
        INSERT INTO record_revision (
            encounter_id, task_id, revision_no, source, content_hash, fields_json,
            draft_text, safety_check_json, quality_report_json,
            result_json, created_by_user_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            encounter_id,
            task_id,
            revision_no,
            source,
            content_hash,
            json_or_none(result.get("fields")),
            result.get("draft"),
            json_or_none(result.get("safety_check")),
            json_or_none(result.get("quality_report")),
            json_dumps(result),
            actor_user_id,
            now,
        ),
    )
    return int(cursor.lastrowid)


def _update_encounter_revision_row(
    connection: sqlite3.Connection,
    *,
    encounter_id: int,
    revision_id: int,
    workflow_status: str,
) -> None:
    connection.execute(
        """
        UPDATE encounter
        SET status = ?, current_revision_id = ?, updated_at = ?
        WHERE id = ?
        """,
        (workflow_status, revision_id, utc_now(), encounter_id),
    )


def _update_task_result_revision_row(
    connection: sqlite3.Connection,
    *,
    task_id: int,
    result: dict[str, Any],
    status: str | None,
    current_stage: str,
    encounter_id: int,
    revision_id: int,
    expected_previous_revision_id: int | None = None,
    expected_previous_content_hash: str | None = None,
) -> None:
    completed_at_value = utc_now() if status in TERMINAL_TASK_STATUSES else None
    params: list[Any] = [
        status,
        current_stage,
        json_dumps(result),
        encounter_id,
        revision_id,
        completed_at_value,
        utc_now(),
        task_id,
    ]
    where = "WHERE id = ?"
    if expected_previous_revision_id is not None:
        where += """
            AND current_record_revision_id = ?
            AND EXISTS (
                SELECT 1
                FROM record_revision rr
                WHERE rr.id = ?
                  AND rr.task_id = agent_task.id
                  AND (
                        rr.content_hash = ?
                        OR (rr.content_hash IS NULL AND ? IS NULL)
                      )
            )
        """
        params.extend(
            [
                expected_previous_revision_id,
                expected_previous_revision_id,
                expected_previous_content_hash,
                expected_previous_content_hash,
            ]
        )
    cursor = connection.execute(
        f"""
        UPDATE agent_task
        SET status = COALESCE(?, status),
            current_stage = ?,
            result_json = ?,
            encounter_id = COALESCE(?, encounter_id),
            current_record_revision_id = ?,
            completed_at = COALESCE(?, completed_at),
            updated_at = ?
        {where}
        """,
        params,
    )
    if cursor.rowcount != 1:
        row = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
        current_revision_id = row["current_record_revision_id"] if row is not None else None
        current_hash = None
        if current_revision_id is not None:
            revision = connection.execute(
                "SELECT content_hash FROM record_revision WHERE id = ?",
                (current_revision_id,),
            ).fetchone()
            current_hash = revision["content_hash"] if revision is not None else None
        raise StaleRecordRevisionError(
            expected_revision_id=expected_previous_revision_id,
            expected_content_hash=expected_previous_content_hash,
            current_revision_id=current_revision_id,
            current_content_hash=current_hash,
        )


def _insert_audit_log_row(
    connection: sqlite3.Connection,
    *,
    task_id: int,
    event_type: str,
    event_detail: Any,
    actor_user_id: int | None = None,
    resource_type: str = "task",
    resource_id: str | int | None = None,
) -> int:
    cursor = connection.execute(
        """
        INSERT INTO audit_log (task_id, event_type, event_detail, created_at)
        VALUES (?, ?, ?, ?)
        """,
        (task_id, event_type, json_dumps(event_detail), utc_now()),
    )
    audit_id = int(cursor.lastrowid)
    _append_audit_chain(
        connection,
        event_type=event_type,
        payload=json_dumps(
            {
                "audit_id": audit_id,
                "task_id": task_id,
                "event_type": event_type,
                "event_detail": event_detail,
            }
        ),
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else str(task_id),
        actor_user_id=actor_user_id,
    )
    return audit_id


def create_record_revision_for_task(
    task_id: int,
    result: dict[str, Any],
    *,
    actor_user_id: int | None = None,
    source: str,
    workflow_status: str,
    invalidate_approvals: bool = True,
) -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        encounter = ensure_task_encounter(task_id, actor_user_id=actor_user_id)
        encounter_id = int(encounter["id"])
        if invalidate_approvals:
            _invalidate_active_approvals(
                connection,
                encounter_id=encounter_id,
                reason=f"new_revision:{source}",
            )

        row = connection.execute(
            "SELECT COALESCE(MAX(revision_no), 0) AS max_revision FROM record_revision WHERE encounter_id = ?",
            (encounter_id,),
        ).fetchone()
        revision_no = int(row["max_revision"]) + 1 if row is not None else 1
        now = utc_now()
        content_hash = record_content_hash(result)
        cursor = connection.execute(
            """
            INSERT INTO record_revision (
                encounter_id, task_id, revision_no, source, content_hash, fields_json,
                draft_text, safety_check_json, quality_report_json,
                result_json, created_by_user_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                encounter_id,
                task_id,
                revision_no,
                source,
                content_hash,
                json_or_none(result.get("fields")),
                result.get("draft"),
                json_or_none(result.get("safety_check")),
                json_or_none(result.get("quality_report")),
                json_dumps(result),
                actor_user_id,
                now,
            ),
        )
        revision_id = int(cursor.lastrowid)
        connection.execute(
            """
            UPDATE encounter
            SET status = ?, current_revision_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (workflow_status, revision_id, now, encounter_id),
        )
        _update_task_workflow_links(
            connection,
            task_id=task_id,
            encounter_id=encounter_id,
            revision_id=revision_id,
        )
        connection.commit()
        return get_record_revision(revision_id) or {}


def apply_review_revision_transaction(
    task_id: int,
    result: dict[str, Any],
    *,
    expected_revision_id: int,
    expected_content_hash: str,
    actor_user_id: int | None = None,
    status: str,
    current_stage: str,
    source: str,
    workflow_status: str,
    event_type: str,
    event_detail: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        try:
            connection.execute("BEGIN IMMEDIATE")
            task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
            if task is None:
                raise ValueError(f"Task not found: {task_id}")
            current_revision_id = task["current_record_revision_id"]
            if current_revision_id is None:
                raise ValueError("Task has no current record revision")
            revision = connection.execute(
                "SELECT id, content_hash FROM record_revision WHERE id = ? AND task_id = ?",
                (current_revision_id, task_id),
            ).fetchone()
            if revision is None:
                raise ValueError("Current record revision not found")
            current_content_hash = revision["content_hash"]
            if int(expected_revision_id) != int(current_revision_id) or expected_content_hash != current_content_hash:
                raise StaleRecordRevisionError(
                    expected_revision_id=expected_revision_id,
                    expected_content_hash=expected_content_hash,
                    current_revision_id=int(current_revision_id),
                    current_content_hash=current_content_hash,
                )

            encounter = _ensure_task_encounter_with_connection(
                connection,
                task_id=task_id,
                actor_user_id=actor_user_id,
            )
            encounter_id = int(encounter["id"])
            _invalidate_active_approvals(
                connection,
                encounter_id=encounter_id,
                reason=f"new_revision:{source}",
            )
            revision_id = _insert_record_revision_row(
                connection,
                task_id=task_id,
                encounter_id=encounter_id,
                result=result,
                actor_user_id=actor_user_id,
                source=source,
            )
            _update_encounter_revision_row(
                connection,
                encounter_id=encounter_id,
                revision_id=revision_id,
                workflow_status=workflow_status,
            )
            _update_task_result_revision_row(
                connection,
                task_id=task_id,
                result=result,
                status=status,
                current_stage=current_stage,
                encounter_id=encounter_id,
                revision_id=revision_id,
                expected_previous_revision_id=int(current_revision_id),
                expected_previous_content_hash=current_content_hash,
            )
            _insert_audit_log_row(
                connection,
                task_id=task_id,
                event_type=event_type,
                event_detail=event_detail,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        row = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
    return row_to_dict(row) or {}


def get_record_revision(revision_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM record_revision WHERE id = ?",
            (revision_id,),
        ).fetchone()
    return row_to_dict(row)


def get_task_encounter(task_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT e.*
            FROM encounter e
            JOIN agent_task t
              ON (t.encounter_id = e.id OR e.task_id = t.id)
            WHERE t.id = ?
            ORDER BY CASE WHEN t.encounter_id = e.id THEN 0 ELSE 1 END
            LIMIT 1
            """,
            (task_id,),
        ).fetchone()
    return row_to_dict(row)


def create_encounter(
    *,
    doctor_user_id: int | None,
    deidentified_id: str,
    display_name: str | None = None,
    check_in_status: str = "registered",
    department_id: str | None = None,
) -> dict[str, Any]:
    init_db()
    now = utc_now()
    normalized_check_in_status = _validate_check_in_status(check_in_status)
    department = (department_id or "").strip() or None
    with closing(get_connection()) as connection:
        patient = connection.execute(
            "SELECT * FROM patient WHERE deidentified_id = ?",
            (deidentified_id,),
        ).fetchone()
        if patient is None:
            cursor = connection.execute(
                """
                INSERT INTO patient (
                    deidentified_id, display_name, created_by_user_id,
                    department_id, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    deidentified_id,
                    display_name or deidentified_id,
                    doctor_user_id,
                    department,
                    now,
                    now,
                ),
            )
            patient_id = int(cursor.lastrowid)
        else:
            patient_id = int(patient["id"])
            # Backfill only; an existing department is never reassigned implicitly.
            if department and patient["department_id"] is None:
                connection.execute(
                    "UPDATE patient SET department_id = ?, updated_at = ? WHERE id = ?",
                    (department, now, patient_id),
                )
        cursor = connection.execute(
            """
            INSERT INTO encounter (
                patient_id, doctor_user_id, task_id, status, check_in_status,
                current_revision_id, department_id, created_at, updated_at
            )
            VALUES (?, ?, NULL, 'draft', ?, NULL, ?, ?, ?)
            """,
            (patient_id, doctor_user_id, normalized_check_in_status, department, now, now),
        )
        encounter_id = int(cursor.lastrowid)
        connection.commit()
    return get_encounter(encounter_id) or {}


def update_encounter_check_in_status(encounter_id: int, check_in_status: str) -> dict[str, Any]:
    init_db()
    normalized_check_in_status = _validate_check_in_status(check_in_status)
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE encounter
            SET check_in_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (normalized_check_in_status, utc_now(), encounter_id),
        )
        connection.commit()
    return get_encounter(encounter_id) or {}


def _failed_task_has_no_record(connection: sqlite3.Connection, encounter: Any) -> bool:
    """Only an intact failed attempt without clinical artifacts may be superseded."""
    previous_id = encounter["task_id"]
    if previous_id is None or encounter["current_revision_id"] is not None:
        return False
    previous = connection.execute("SELECT * FROM agent_task WHERE id = ?", (previous_id,)).fetchone()
    if (previous is None or previous["status"] != "FAILED"
            or previous["encounter_id"] != encounter["id"]
            or previous["owner_user_id"] != encounter["doctor_user_id"]
            or encounter["check_in_status"] not in {"checked_in", "in_progress"}):
        return False
    for table in ("record_revision", "approval", "export_event"):
        if connection.execute(f"SELECT 1 FROM {table} WHERE encounter_id = ? OR task_id = ? LIMIT 1",
                              (encounter["id"], previous_id)).fetchone():
            return False
    return True


def can_retry_failed_encounter(encounter_id: int) -> bool:
    init_db()
    with closing(get_connection()) as connection:
        encounter = connection.execute("SELECT * FROM encounter WHERE id = ?", (encounter_id,)).fetchone()
        return encounter is not None and _failed_task_has_no_record(connection, encounter)


def bind_task_to_encounter(
    task_id: int,
    encounter_id: int,
    *,
    owner_user_id: int,
    check_in_status: str | None = "in_progress",
    allow_failed_replacement: bool = False,
) -> dict[str, Any]:
    init_db()
    if owner_user_id is None:
        raise ValueError("Task owner is required when binding an encounter")
    normalized_check_in_status = (
        _validate_check_in_status(check_in_status)
        if check_in_status is not None
        else None
    )
    with closing(get_connection()) as connection:
        # Check and replace the active pointer under the same write lock. A
        # concurrent second submission must see the new CREATED task and fail.
        connection.execute("BEGIN IMMEDIATE")
        task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        encounter = connection.execute("SELECT * FROM encounter WHERE id = ?", (encounter_id,)).fetchone()
        if encounter is None:
            raise ValueError(f"Encounter not found: {encounter_id}")
        if encounter["doctor_user_id"] is None:
            raise ValueError("Encounter has no doctor owner")
        if int(encounter["doctor_user_id"]) != int(owner_user_id):
            raise ValueError("Task owner does not match encounter doctor")
        replaced_task_id = None
        if encounter["task_id"] is not None and int(encounter["task_id"]) != int(task_id):
            if not (allow_failed_replacement and task["status"] == "CREATED"
                    and task["encounter_id"] is None
                    and _failed_task_has_no_record(connection, encounter)):
                raise ValueError("Encounter is already bound to a different task")
            replaced_task_id = int(encounter["task_id"])
        if task["encounter_id"] is not None and int(task["encounter_id"]) != int(encounter_id):
            raise ValueError("Task is already bound to a different encounter")

        now = utc_now()
        if replaced_task_id is not None:
            _insert_audit_log_row(
                connection,
                task_id=task_id,
                event_type="failed_task_replaced",
                event_detail={
                    "previous_task_id": replaced_task_id,
                    "encounter_id": encounter_id,
                    "owner_user_id": owner_user_id,
                    "reason": "explicit_generation_after_failure",
                    "previous_result_preserved": True,
                },
                resource_type="task",
                resource_id=task_id,
            )
        connection.execute(
            """
            UPDATE agent_task
            SET owner_user_id = ?,
                encounter_id = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (owner_user_id, encounter_id, now, task_id),
        )
        if normalized_check_in_status is None:
            connection.execute(
                """
                UPDATE encounter
                SET task_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (task_id, now, encounter_id),
            )
        else:
            connection.execute(
                """
                UPDATE encounter
                SET task_id = ?, check_in_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (task_id, normalized_check_in_status, now, encounter_id),
            )
        connection.commit()
    return get_encounter(encounter_id) or {}


def get_encounter(encounter_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT e.*, p.deidentified_id AS patient_deidentified_id,
                   p.display_name AS patient_display_name,
                   t.status AS task_status,
                   t.current_stage AS task_current_stage,
                   t.result_json AS task_result_json
            FROM encounter e
            JOIN patient p ON p.id = e.patient_id
            LEFT JOIN agent_task t ON t.id = e.task_id
            WHERE e.id = ?
            """,
            (encounter_id,),
        ).fetchone()
    return row_to_dict(row)


def list_encounters(
    *,
    user_id: int,
    role: str,
    status: str | None = None,
    mine: bool = True,
    q: str | None = None,
    department_id: str | None = None,
) -> list[dict[str, Any]]:
    init_db()
    clauses: list[str] = []
    params: list[Any] = []
    department = (department_id or "").strip() or None
    if status:
        clauses.append("e.status = ?")
        params.append(status)
    if role in DEPARTMENT_VISIBLE_ROLES and department:
        # Front desk / intake work on one department. A legacy row without a
        # stored department is visible only when its doctor belongs to the same
        # department; it must not leak across departments.
        clauses.append(
            "(e.department_id = ? OR (e.department_id IS NULL AND e.doctor_user_id IN "
            "(SELECT id FROM auth_user WHERE department_id = ?)))"
        )
        params.extend([department, department])
    elif role != "admin" or mine:
        clauses.append("e.doctor_user_id = ?")
        params.append(user_id)
    if q:
        like = f"%{q}%"
        clauses.append(
            "(p.deidentified_id LIKE ? OR p.display_name LIKE ? OR CAST(e.task_id AS TEXT) LIKE ?)"
        )
        params.extend([like, like, like])
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    query = f"""
        SELECT e.*, p.deidentified_id AS patient_deidentified_id,
               p.display_name AS patient_display_name,
               t.status AS task_status,
               t.current_stage AS task_current_stage
        FROM encounter e
        JOIN patient p ON p.id = e.patient_id
        LEFT JOIN agent_task t ON t.id = e.task_id
        {where}
        ORDER BY e.updated_at DESC, e.id DESC
    """
    with closing(get_connection()) as connection:
        rows = connection.execute(query, params).fetchall()
    return [dict(row) for row in rows]


def list_record_revisions_for_encounter(encounter_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM record_revision
            WHERE encounter_id = ?
            ORDER BY revision_no ASC
            """,
            (encounter_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_record_revisions_for_task(task_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM record_revision
            WHERE task_id = ?
            ORDER BY revision_no ASC
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_approval_for_task(
    task_id: int,
    *,
    actor_user_id: int | None = None,
    content_hash: str | None = None,
    approval_items: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        task = connection.execute("SELECT * FROM agent_task WHERE id = ?", (task_id,)).fetchone()
        if task is None:
            raise ValueError(f"Task not found: {task_id}")
        encounter_id = task["encounter_id"]
        revision_id = task["current_record_revision_id"]
        if encounter_id is None or revision_id is None:
            raise ValueError("Task has no current record revision")
        revision = connection.execute(
            "SELECT * FROM record_revision WHERE id = ?",
            (revision_id,),
        ).fetchone()
        if revision is None:
            raise ValueError("Current record revision not found")
        revision_hash = revision["content_hash"] or record_content_hash(
            json.loads(revision["result_json"] or "{}")
        )
        if content_hash is not None and content_hash != revision_hash:
            raise ValueError("Approval content hash does not match current revision")
        active = connection.execute(
            """
            SELECT *
            FROM approval
            WHERE revision_id = ? AND status = 'active' AND invalidated_at IS NULL
            """,
            (revision_id,),
        ).fetchone()
        if active is not None:
            raise ValueError("Current revision is already approved")
        _invalidate_active_approvals(
            connection,
            encounter_id=int(encounter_id),
            reason="new_approval",
        )
        now = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO approval (
                encounter_id, revision_id, task_id, approved_by_user_id,
                content_hash, status, created_at, invalidated_at, invalidation_reason
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, NULL, NULL)
            """,
            (encounter_id, revision_id, task_id, actor_user_id, revision_hash, now),
        )
        approval_id = int(cursor.lastrowid)
        for item in approval_items or []:
            connection.execute(
                """
                INSERT INTO approval_item (
                    approval_id, task_id, revision_id, item_type, item_key,
                    action, status, high_risk_confirmed, note, actor_user_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    approval_id,
                    task_id,
                    revision_id,
                    item.get("item_type"),
                    item.get("item_key"),
                    item.get("action"),
                    item.get("status", "completed"),
                    1 if item.get("high_risk_confirmed") else 0,
                    item.get("note"),
                    actor_user_id,
                    now,
                ),
            )
        connection.execute(
            "UPDATE encounter SET status = 'approved', updated_at = ? WHERE id = ?",
            (now, encounter_id),
        )
        connection.commit()
        return dict(
            connection.execute("SELECT * FROM approval WHERE id = ?", (approval_id,)).fetchone()
        )


def get_active_approval_for_task(task_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT a.*
            FROM approval a
            JOIN agent_task t ON t.current_record_revision_id = a.revision_id
            WHERE t.id = ?
              AND a.status = 'active'
              AND a.invalidated_at IS NULL
            """,
            (task_id,),
        ).fetchone()
    return row_to_dict(row)


def list_approval_items_for_approval(approval_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM approval_item
            WHERE approval_id = ?
            ORDER BY id ASC
            """,
            (approval_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def list_approvals_for_task(task_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM approval
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_export_event_for_task(
    task_id: int,
    *,
    approval_id: int,
    actor_user_id: int | None,
    exports: dict[str, Any],
) -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        approval = connection.execute(
            "SELECT * FROM approval WHERE id = ? AND status = 'active' AND invalidated_at IS NULL",
            (approval_id,),
        ).fetchone()
        if approval is None:
            raise ValueError("Active approval not found")
        now = utc_now()
        cursor = connection.execute(
            """
            INSERT INTO export_event (
                encounter_id, revision_id, approval_id, task_id,
                exported_by_user_id, exports_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                approval["encounter_id"],
                approval["revision_id"],
                approval_id,
                task_id,
                actor_user_id,
                json_dumps(exports),
                now,
            ),
        )
        export_event_id = int(cursor.lastrowid)
        connection.execute(
            "UPDATE encounter SET status = 'exported', updated_at = ? WHERE id = ?",
            (now, approval["encounter_id"]),
        )
        connection.commit()
        return dict(connection.execute("SELECT * FROM export_event WHERE id = ?", (export_event_id,)).fetchone())


def list_export_events_for_task(task_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM export_event
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def update_task(
    task_id: int,
    *,
    input_text: str | None = None,
    status: str | None = None,
    current_stage: str | None = None,
    result_json: str | None = None,
    error_message: str | None = None,
    retry_count: int | None = None,
    completed_at: str | None = None,
) -> None:
    init_db()
    completed_at_value = completed_at
    if completed_at_value is None and status in TERMINAL_TASK_STATUSES:
        completed_at_value = utc_now()

    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE agent_task
            SET input_text = COALESCE(?, input_text),
                status = COALESCE(?, status),
                current_stage = COALESCE(?, current_stage),
                result_json = COALESCE(?, result_json),
                error_message = COALESCE(?, error_message),
                retry_count = COALESCE(?, retry_count),
                completed_at = COALESCE(?, completed_at),
                updated_at = ?
            WHERE id = ?
            """,
            (
                input_text,
                status,
                current_stage,
                result_json,
                error_message,
                retry_count,
                completed_at_value,
                utc_now(),
                task_id,
            ),
        )
        connection.commit()


def increment_task_retry_count(task_id: int) -> int:
    init_db()
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE agent_task
            SET retry_count = retry_count + 1,
                updated_at = ?
            WHERE id = ?
            """,
            (utc_now(), task_id),
        )
        row = connection.execute(
            "SELECT retry_count FROM agent_task WHERE id = ?",
            (task_id,),
        ).fetchone()
        connection.commit()
    return int(row["retry_count"]) if row is not None else 0


def create_task_step(
    task_id: int,
    step_name: str,
    status: str = "RUNNING",
    *,
    attempt_no: int = 1,
    input_snapshot: Any | None = None,
) -> int:
    init_db()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO agent_task_step (
                task_id, step_name, status, attempt_no, started_at,
                ended_at, duration_ms, input_snapshot_json,
                output_snapshot_json, error_message
            )
            VALUES (?, ?, ?, ?, ?, NULL, NULL, ?, NULL, NULL)
            """,
            (
                task_id,
                step_name,
                status,
                attempt_no,
                utc_now(),
                json_or_none(input_snapshot),
            ),
        )
        step_id = int(cursor.lastrowid)
        connection.commit()
        return step_id


def finish_task_step(
    step_id: int,
    *,
    status: str,
    error_message: str | None = None,
    output_snapshot: Any | None = None,
) -> None:
    init_db()
    ended_at = utc_now()
    with closing(get_connection()) as connection:
        step = connection.execute(
            "SELECT started_at FROM agent_task_step WHERE id = ?",
            (step_id,),
        ).fetchone()
        duration_ms = None
        if step is not None:
            started_at = datetime.fromisoformat(step["started_at"])
            duration_ms = int((datetime.fromisoformat(ended_at) - started_at).total_seconds() * 1000)

        connection.execute(
            """
            UPDATE agent_task_step
            SET status = ?, ended_at = ?, duration_ms = ?,
                output_snapshot_json = ?, error_message = ?
            WHERE id = ?
            """,
            (
                status,
                ended_at,
                duration_ms,
                json_or_none(output_snapshot),
                error_message,
                step_id,
            ),
        )
        connection.commit()


def _audit_hmac_key() -> bytes | None:
    raw = os.environ.get("MRA_AUDIT_HMAC_KEY", "").strip()
    return raw.encode("utf-8") if raw else None


def _audit_hash(key: bytes | None, prev_hash: str, payload: str) -> tuple[str, str]:
    material = f"{prev_hash}\n{payload}".encode("utf-8")
    if key is not None:
        return hmac.new(key, material, hashlib.sha256).hexdigest(), "hmac-sha256"
    return hashlib.sha256(material).hexdigest(), "sha256"


def _append_audit_chain(
    connection: sqlite3.Connection,
    *,
    event_type: str,
    payload: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        "SELECT entry_hash FROM audit_chain ORDER BY id DESC LIMIT 1"
    ).fetchone()
    prev_hash = row["entry_hash"] if row is not None else AUDIT_CHAIN_GENESIS
    key = _audit_hmac_key()
    entry_hash, key_id = _audit_hash(key, prev_hash, payload)
    cursor = connection.execute(
        """
        INSERT INTO audit_chain (
            event_type, resource_type, resource_id, actor_user_id,
            payload, prev_hash, entry_hash, key_id, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_type,
            resource_type,
            resource_id,
            actor_user_id,
            payload,
            prev_hash,
            entry_hash,
            key_id,
            utc_now(),
        ),
    )
    return {
        "id": int(cursor.lastrowid),
        "prev_hash": prev_hash,
        "entry_hash": entry_hash,
        "key_id": key_id,
    }


def append_audit_event(
    event_type: str,
    payload: Any,
    *,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    actor_user_id: int | None = None,
) -> dict[str, Any]:
    """Append a tamper-evident event that has no agent task (login, config)."""
    init_db()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        entry = _append_audit_chain(
            connection,
            event_type=event_type,
            payload=json_dumps(payload),
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id is not None else None,
            actor_user_id=actor_user_id,
        )
        connection.commit()
        return entry
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def verify_audit_chain(anchor: dict[str, Any] | None = None) -> dict[str, Any]:
    """Walk the chain and recompute every hash. Any edit breaks verification.

    ``anchor`` is an externally stored ``{entries, head_hash}`` snapshot. It is
    what makes a *tail* truncation detectable: the chain alone cannot notice
    rows that were removed from its end.
    """
    init_db()
    key = _audit_hmac_key()
    with closing(get_connection()) as connection:
        rows = connection.execute("SELECT * FROM audit_chain ORDER BY id ASC").fetchall()
    prev = AUDIT_CHAIN_GENESIS
    hashes: list[str] = []
    for row in rows:
        if row["key_id"] == "hmac-sha256" and key is None:
            return {
                "ok": False,
                "entries": len(rows),
                "broken_at": row["id"],
                "reason": "missing_hmac_key",
                "key_id": row["key_id"],
            }
        expected, key_id = _audit_hash(key, row["prev_hash"], row["payload"])
        if row["prev_hash"] != prev:
            return {
                "ok": False,
                "entries": len(rows),
                "broken_at": row["id"],
                "reason": "prev_hash_mismatch",
                "expected_prev_hash": prev,
                "stored_prev_hash": row["prev_hash"],
                "key_id": key_id,
            }
        if not hmac.compare_digest(expected, row["entry_hash"]):
            return {
                "ok": False,
                "entries": len(rows),
                "broken_at": row["id"],
                "reason": "hash_mismatch",
                "expected_hash": expected,
                "stored_hash": row["entry_hash"],
                "key_id": key_id,
            }
        prev = row["entry_hash"]
        hashes.append(row["entry_hash"])
    report: dict[str, Any] = {
        "ok": True,
        "entries": len(rows),
        "head": prev,
        "key_id": "hmac-sha256" if key is not None else "sha256",
    }
    if anchor:
        anchored_entries = int(anchor.get("entries") or 0)
        anchored_head = anchor.get("head_hash")
        if anchored_entries > len(rows):
            return {
                **report,
                "ok": False,
                "reason": "anchor_truncated",
                "anchored_entries": anchored_entries,
                "current_entries": len(rows),
                "anchor": anchor,
            }
        if anchored_entries > 0 and hashes[anchored_entries - 1] != anchored_head:
            return {
                **report,
                "ok": False,
                "reason": "anchor_mismatch",
                "anchored_entries": anchored_entries,
                "anchored_head_hash": anchored_head,
                "current_prefix_hash": hashes[anchored_entries - 1],
                "anchor": anchor,
            }
        report["anchor"] = {
            "checked": True,
            "entries": anchored_entries,
            "head_hash": anchored_head,
            "anchored_at": anchor.get("anchored_at"),
        }
    return report


def list_audit_chain_entries(limit: int = 50) -> list[dict[str, Any]]:
    init_db()
    bounded = max(1, min(int(limit), 500))
    with closing(get_connection()) as connection:
        rows = connection.execute(
            "SELECT * FROM audit_chain ORDER BY id DESC LIMIT ?",
            (bounded,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_audit_log(
    task_id: int,
    event_type: str,
    event_detail: Any,
    *,
    actor_user_id: int | None = None,
    resource_type: str = "task",
    resource_id: str | int | None = None,
) -> int:
    init_db()
    connection = get_connection()
    try:
        connection.execute("BEGIN IMMEDIATE")
        audit_id = _insert_audit_log_row(
            connection,
            task_id=task_id,
            event_type=event_type,
            event_detail=event_detail,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
        )
        connection.commit()
        return audit_id
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def get_task(task_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM agent_task WHERE id = ?",
            (task_id,),
        ).fetchone()
    return row_to_dict(row)


def get_task_steps(task_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM agent_task_step
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def get_audit_logs(task_id: int) -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT *
            FROM audit_log
            WHERE task_id = ?
            ORDER BY id ASC
            """,
            (task_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def create_user(
    *,
    username: str,
    password: str,
    display_name: str,
    role: str,
    department_id: str | None = None,
) -> int:
    init_db()
    if role not in {"admin", "doctor", "frontdesk", "intake", "intake_admin"}:
        raise ValueError("Unsupported user role")
    from app.services.auth import hash_password

    now = utc_now()
    try:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO auth_user (
                    username, display_name, role, department_id, password_hash,
                    is_active, created_at, updated_at, last_login_at
                )
                VALUES (?, ?, ?, ?, ?, 1, ?, ?, NULL)
                """,
                (username, display_name, role, department_id, hash_password(password), now, now),
            )
            user_id = int(cursor.lastrowid)
            connection.commit()
            return user_id
    except sqlite3.IntegrityError as exc:
        raise ValueError("Username already exists") from exc


def get_user_by_username(username: str) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM auth_user WHERE username = ?",
            (username,),
        ).fetchone()
    return row_to_dict(row)


def get_user_by_id(user_id: int) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            "SELECT * FROM auth_user WHERE id = ?",
            (user_id,),
        ).fetchone()
    return row_to_dict(row)


def count_active_admins(exclude_user_id: int | None = None) -> int:
    """How many enabled admins would remain after excluding one account."""
    init_db()
    with closing(get_connection()) as connection:
        if exclude_user_id is None:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM auth_user WHERE role = 'admin' AND is_active = 1"
            ).fetchone()
        else:
            row = connection.execute(
                """
                SELECT COUNT(*) AS count FROM auth_user
                WHERE role = 'admin' AND is_active = 1 AND id != ?
                """,
                (exclude_user_id,),
            ).fetchone()
    return int(row["count"]) if row is not None else 0


def list_users() -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, username, display_name, role, department_id, is_active,
                   created_at, updated_at, last_login_at
            FROM auth_user
            ORDER BY id ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def update_user_last_login(user_id: int) -> None:
    init_db()
    now = utc_now()
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE auth_user
            SET last_login_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, user_id),
        )
        connection.commit()


def create_auth_session(
    *,
    user_id: int,
    token_hash: str,
    expires_at: str,
) -> int:
    init_db()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO auth_session (user_id, token_hash, created_at, expires_at, revoked_at)
            VALUES (?, ?, ?, ?, NULL)
            """,
            (user_id, token_hash, utc_now(), expires_at),
        )
        session_id = int(cursor.lastrowid)
        connection.commit()
        return session_id


def get_auth_session_user(token_hash: str) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT u.*
            FROM auth_session s
            JOIN auth_user u ON u.id = s.user_id
            WHERE s.token_hash = ?
              AND s.revoked_at IS NULL
              AND s.expires_at > ?
              AND u.is_active = 1
            """,
            (token_hash, utc_now()),
        ).fetchone()
    return row_to_dict(row)


def revoke_auth_session(token_hash: str) -> None:
    init_db()
    with closing(get_connection()) as connection:
        connection.execute(
            """
            UPDATE auth_session
            SET revoked_at = ?
            WHERE token_hash = ? AND revoked_at IS NULL
            """,
            (utc_now(), token_hash),
        )
        connection.commit()


def revoke_user_sessions(user_id: int) -> int:
    """Revoke every live session of a user (disable, role change, reset)."""
    init_db()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            UPDATE auth_session
            SET revoked_at = ?
            WHERE user_id = ? AND revoked_at IS NULL
            """,
            (utc_now(), user_id),
        )
        connection.commit()
        return int(cursor.rowcount or 0)


def update_user_admin(user_id: int, fields: dict[str, Any]) -> dict[str, Any] | None:
    """Admin-only profile/role/department/active-state update."""
    unknown = set(fields) - USER_ADMIN_FIELDS
    if unknown:
        raise ValueError(f"Unsupported user fields: {sorted(unknown)}")
    if "role" in fields and fields["role"] not in {
        "admin",
        "doctor",
        "frontdesk",
        "intake",
        "intake_admin",
    }:
        raise ValueError("Unsupported user role")
    if "display_name" in fields and not (
        isinstance(fields["display_name"], str) and fields["display_name"].strip()
    ):
        raise ValueError("display_name must be a non-empty string")
    if "is_active" in fields and not isinstance(fields["is_active"], bool):
        raise ValueError("is_active must be a boolean")
    if "department_id" in fields and not (
        fields["department_id"] is None or isinstance(fields["department_id"], str)
    ):
        raise ValueError("department_id must be a string or null")
    init_db()
    if not fields:
        return get_user_by_id(user_id)
    assignments = ", ".join(f"{name} = ?" for name in fields)
    params = [int(bool(value)) if name == "is_active" else value for name, value in fields.items()]
    now = utc_now()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            f"UPDATE auth_user SET {assignments}, updated_at = ? WHERE id = ?",
            (*params, now, user_id),
        )
        connection.commit()
        if cursor.rowcount == 0:
            return None
    return get_user_by_id(user_id)


def _seconds_until(value: str | None) -> int | None:
    if not value:
        return None
    try:
        remaining = (datetime.fromisoformat(value) - datetime.now(UTC)).total_seconds()
    except ValueError:
        return None
    return max(0, int(remaining) + 1)


def login_lock_state(username: str, client_ip: str) -> dict[str, Any] | None:
    init_db()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT * FROM auth_login_attempt
            WHERE username = ? AND client_ip = ?
            """,
            (username, client_ip),
        ).fetchone()
    if row is None:
        return None
    retry_after = _seconds_until(row["locked_until"])
    if retry_after is None or retry_after <= 0:
        return None
    return {
        "locked": True,
        "failures": int(row["failures"]),
        "locked_until": row["locked_until"],
        "retry_after": retry_after,
    }


def register_login_failure(
    username: str,
    client_ip: str,
    *,
    threshold: int = LOGIN_FAILURE_THRESHOLD,
    window_seconds: int = LOGIN_FAILURE_WINDOW_SECONDS,
    lock_seconds: int = LOGIN_LOCK_SECONDS,
) -> dict[str, Any]:
    """Count a failed login for one (username, IP) pair, locking after N."""
    init_db()
    now = datetime.now(UTC)
    now_iso = now.isoformat()
    with closing(get_connection()) as connection:
        row = connection.execute(
            """
            SELECT * FROM auth_login_attempt
            WHERE username = ? AND client_ip = ?
            """,
            (username, client_ip),
        ).fetchone()
        failures = 1
        first_failed_at = now_iso
        if row is not None:
            first = row["first_failed_at"]
            try:
                first_dt = datetime.fromisoformat(first) if first else now
            except ValueError:
                first_dt = now
            within_window = (now - first_dt).total_seconds() <= window_seconds
            if row["locked_until"] and _seconds_until(row["locked_until"]) in (None, 0):
                within_window = False
            if within_window:
                failures = int(row["failures"]) + 1
                first_failed_at = first or now_iso
        locked_until = None
        if failures >= threshold:
            locked_until = (now + timedelta(seconds=lock_seconds)).isoformat()
        connection.execute(
            """
            INSERT INTO auth_login_attempt (
                username, client_ip, failures, first_failed_at, locked_until, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(username, client_ip) DO UPDATE SET
                failures = excluded.failures,
                first_failed_at = excluded.first_failed_at,
                locked_until = excluded.locked_until,
                updated_at = excluded.updated_at
            """,
            (username, client_ip, failures, first_failed_at, locked_until, now_iso),
        )
        # Bound table growth from random usernames: retained for one day.
        connection.execute(
            "DELETE FROM auth_login_attempt WHERE updated_at < ?",
            ((now - timedelta(days=1)).isoformat(),),
        )
        connection.commit()
    if locked_until:
        return {
            "locked": True,
            "failures": failures,
            "locked_until": locked_until,
            "retry_after": lock_seconds,
        }
    return {
        "locked": False,
        "failures": failures,
        "remaining": max(0, threshold - failures),
    }


def clear_login_failures(username: str, client_ip: str) -> None:
    init_db()
    with closing(get_connection()) as connection:
        connection.execute(
            "DELETE FROM auth_login_attempt WHERE username = ? AND client_ip = ?",
            (username, client_ip),
        )
        connection.commit()


def audit_chain_head() -> dict[str, Any]:
    init_db()
    with closing(get_connection()) as connection:
        count = connection.execute("SELECT COUNT(*) AS count FROM audit_chain").fetchone()
        row = connection.execute(
            "SELECT entry_hash, key_id, created_at FROM audit_chain ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return {
        "entries": int(count["count"]) if count is not None else 0,
        "head_hash": row["entry_hash"] if row is not None else AUDIT_CHAIN_GENESIS,
        "key_id": row["key_id"] if row is not None else "sha256",
        "last_entry_at": row["created_at"] if row is not None else None,
    }
