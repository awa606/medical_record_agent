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
            """
        )
        _migrate_schema(connection)
        connection.commit()


def _migrate_schema(connection: sqlite3.Connection) -> None:
    _ensure_column(connection, "agent_task", "input_text", "TEXT")
    _ensure_column(connection, "agent_task", "retry_count", "INTEGER NOT NULL DEFAULT 0")
    _ensure_column(connection, "agent_task", "completed_at", "TEXT")
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
