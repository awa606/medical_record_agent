from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "medical_record_agent.sqlite3"
TERMINAL_TASK_STATUSES = {"WAITING_DOCTOR_REVIEW", "DONE", "FAILED"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def get_db_path() -> Path:
    return Path(os.environ.get("MEDICAL_RECORD_AGENT_DB", DEFAULT_DB_PATH))


def get_connection() -> sqlite3.Connection:
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    return connection


def init_db() -> None:
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

            CREATE TABLE IF NOT EXISTS auth_user (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'doctor')),
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
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                invalidated_at TEXT,
                invalidation_reason TEXT,
                FOREIGN KEY(encounter_id) REFERENCES encounter(id),
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
    _ensure_column(connection, "agent_task", "input_text", "TEXT")
    _ensure_column(connection, "agent_task", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "agent_task", "completed_at", "TEXT")
    _ensure_column(connection, "agent_task", "owner_user_id", "INTEGER")
    _ensure_column(connection, "agent_task", "encounter_id", "INTEGER")
    _ensure_column(connection, "agent_task", "current_record_revision_id", "INTEGER")
    _ensure_column(connection, "agent_task_step", "attempt_no", "INTEGER NOT NULL DEFAULT 1")
    _ensure_column(connection, "agent_task_step", "input_snapshot_json", "TEXT")
    _ensure_column(connection, "agent_task_step", "output_snapshot_json", "TEXT")


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
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


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
                patient_id, doctor_user_id, task_id, status,
                current_revision_id, created_at, updated_at
            )
            VALUES (?, ?, ?, 'draft', NULL, ?, ?)
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
        cursor = connection.execute(
            """
            INSERT INTO record_revision (
                encounter_id, task_id, revision_no, source, fields_json,
                draft_text, safety_check_json, quality_report_json,
                result_json, created_by_user_id, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                encounter_id,
                task_id,
                revision_no,
                source,
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
            JOIN agent_task t ON t.encounter_id = e.id
            WHERE t.id = ?
            """,
            (task_id,),
        ).fetchone()
    return row_to_dict(row)


def create_encounter(
    *,
    doctor_user_id: int | None,
    deidentified_id: str,
    display_name: str | None = None,
) -> dict[str, Any]:
    init_db()
    now = utc_now()
    with closing(get_connection()) as connection:
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
                (deidentified_id, display_name or deidentified_id, doctor_user_id, now, now),
            )
            patient_id = int(cursor.lastrowid)
        else:
            patient_id = int(patient["id"])
        cursor = connection.execute(
            """
            INSERT INTO encounter (
                patient_id, doctor_user_id, task_id, status,
                current_revision_id, created_at, updated_at
            )
            VALUES (?, ?, NULL, 'draft', NULL, ?, ?)
            """,
            (patient_id, doctor_user_id, now, now),
        )
        encounter_id = int(cursor.lastrowid)
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
) -> list[dict[str, Any]]:
    init_db()
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("e.status = ?")
        params.append(status)
    if role != "admin" or mine:
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
                status, created_at, invalidated_at, invalidation_reason
            )
            VALUES (?, ?, ?, ?, 'active', ?, NULL, NULL)
            """,
            (encounter_id, revision_id, task_id, actor_user_id, now),
        )
        approval_id = int(cursor.lastrowid)
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


def create_audit_log(task_id: int, event_type: str, event_detail: Any) -> int:
    init_db()
    with closing(get_connection()) as connection:
        cursor = connection.execute(
            """
            INSERT INTO audit_log (task_id, event_type, event_detail, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, event_type, json_dumps(event_detail), utc_now()),
        )
        audit_id = int(cursor.lastrowid)
        connection.commit()
        return audit_id


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
) -> int:
    init_db()
    if role not in {"admin", "doctor"}:
        raise ValueError("Unsupported user role")
    from app.services.auth import hash_password

    now = utc_now()
    try:
        with closing(get_connection()) as connection:
            cursor = connection.execute(
                """
                INSERT INTO auth_user (
                    username, display_name, role, password_hash,
                    is_active, created_at, updated_at, last_login_at
                )
                VALUES (?, ?, ?, ?, 1, ?, ?, NULL)
                """,
                (username, display_name, role, hash_password(password), now, now),
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


def list_users() -> list[dict[str, Any]]:
    init_db()
    with closing(get_connection()) as connection:
        rows = connection.execute(
            """
            SELECT id, username, display_name, role, is_active,
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
