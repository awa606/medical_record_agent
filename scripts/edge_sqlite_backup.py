from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SIDECAR_SUFFIXES = ("-wal", "-shm")


def _table_names(connection: sqlite3.Connection) -> list[str]:
    return [
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]


def sqlite_report(db_path: Path) -> dict[str, Any]:
    """Integrity plus per-table row counts; used before and after a restore."""
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    with closing(sqlite3.connect(db_path)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        quick = connection.execute("PRAGMA quick_check").fetchone()
        counts = {
            table: int(connection.execute(f'SELECT COUNT(*) AS count FROM "{table}"').fetchone()[0])
            for table in _table_names(connection)
        }
    return {
        "path": str(db_path),
        "bytes": db_path.stat().st_size,
        "integrity_check": integrity[0] if integrity else None,
        "quick_check": quick[0] if quick else None,
        "tables": counts,
    }


def _require_integrity(report: dict[str, Any], label: str) -> None:
    if report["integrity_check"] != "ok":
        raise RuntimeError(f"{label} failed integrity_check: {report['integrity_check']}")


def backup_sqlite(db_path: Path, output_path: Path) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(output_path)) as target:
        source.backup(target)
    report = sqlite_report(output_path)
    _require_integrity(report, "backup")
    return output_path


def restore_sqlite(
    backup_path: Path,
    db_path: Path,
    *,
    force: bool = False,
    keep_current: bool = True,
    require_tables: list[str] | None = None,
) -> Path:
    """Restore with verification, a rollback copy and WAL sidecar cleanup.

    The caller must stop the application first: a running process may keep a
    stale WAL file that would replay pre-restore pages.
    """
    if not backup_path.exists():
        raise FileNotFoundError(f"SQLite backup not found: {backup_path}")
    backup_report = sqlite_report(backup_path)
    _require_integrity(backup_report, "backup")
    missing = sorted(set(require_tables or []) - set(backup_report["tables"]))
    if missing:
        raise RuntimeError(
            f"Backup is missing required tables {missing}; refusing to replace the target"
        )
    if db_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing database without --force: {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    rollback_path: Path | None = None
    if db_path.exists() and keep_current:
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        rollback_path = db_path.with_name(f"{db_path.name}.pre-restore-{stamp}")
        with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(rollback_path)) as target:
            source.backup(target)
        _require_integrity(sqlite_report(rollback_path), "rollback copy")

    tmp_path = db_path.with_name(f"{db_path.name}.restore_tmp")
    with closing(sqlite3.connect(backup_path)) as source, closing(sqlite3.connect(tmp_path)) as target:
        source.backup(target)
    _require_integrity(sqlite_report(tmp_path), "restored database")
    tmp_path.replace(db_path)
    for suffix in SIDECAR_SUFFIXES:
        sidecar = Path(f"{db_path}{suffix}")
        if sidecar.exists():
            sidecar.unlink()

    restored = sqlite_report(db_path)
    _require_integrity(restored, "restored database")
    if restored["tables"] != backup_report["tables"]:
        raise RuntimeError(
            "Restored row counts do not match the backup: "
            f"backup={backup_report['tables']} restored={restored['tables']}"
            + (f" rollback={rollback_path}" if rollback_path else "")
        )
    return db_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup, verify or restore the Medical Record Agent edge SQLite database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a consistent SQLite backup.")
    backup.add_argument("--db", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    restore = subparsers.add_parser("restore", help="Restore a SQLite backup with verification.")
    restore.add_argument("--backup", required=True, type=Path)
    restore.add_argument("--db", required=True, type=Path)
    restore.add_argument("--force", action="store_true")
    restore.add_argument(
        "--no-keep-current",
        action="store_true",
        help="Skip the .pre-restore rollback copy of the current database.",
    )
    restore.add_argument(
        "--require-tables",
        default="",
        help="Comma separated tables the backup must contain, e.g. patient,encounter,approval.",
    )

    verify = subparsers.add_parser("verify", help="Integrity and row counts of a database file.")
    verify.add_argument("--db", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "backup":
            path = backup_sqlite(args.db, args.output)
            print(json.dumps(sqlite_report(path), ensure_ascii=False))
            return 0
        if args.command == "restore":
            required = [item.strip() for item in args.require_tables.split(",") if item.strip()]
            path = restore_sqlite(
                args.backup,
                args.db,
                force=args.force,
                keep_current=not args.no_keep_current,
                require_tables=required,
            )
            print(json.dumps(sqlite_report(path), ensure_ascii=False))
            return 0
        if args.command == "verify":
            print(json.dumps(sqlite_report(args.db), ensure_ascii=False))
            return 0
    except (FileNotFoundError, FileExistsError) as exc:
        print(json.dumps({"error": exc.__class__.__name__, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    except (RuntimeError, sqlite3.DatabaseError) as exc:
        print(json.dumps({"error": exc.__class__.__name__, "detail": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
