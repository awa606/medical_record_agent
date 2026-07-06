from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = PROJECT_ROOT / "data" / "medical_record_agent.sqlite3"
DEFAULT_OUTPUT_PATH = PROJECT_ROOT / "data" / "outputs" / "medical_record_agent_db_export.json"
JSON_COLUMNS = {"result_json", "event_detail", "input_snapshot_json", "output_snapshot_json"}


def decode_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def rows_for_table(connection: sqlite3.Connection, table_name: str) -> list[dict[str, Any]]:
    rows = connection.execute(f"SELECT * FROM {table_name} ORDER BY id ASC").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        for column in JSON_COLUMNS:
            if column in item:
                item[column] = decode_json(item[column])
        result.append(item)
    return result


def export_db(db_path: Path, output_path: Path) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {db_path}")

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    try:
        exported = {
            "database": str(db_path),
            "agent_task": rows_for_table(connection, "agent_task"),
            "agent_task_step": rows_for_table(connection, "agent_task_step"),
            "audit_log": rows_for_table(connection, "audit_log"),
        }
    finally:
        connection.close()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(exported, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Export the medical record Agent SQLite database to readable JSON.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    args = parser.parse_args()

    output_path = export_db(args.db, args.output)
    print(output_path)


if __name__ == "__main__":
    main()
