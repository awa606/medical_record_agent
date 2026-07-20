from __future__ import annotations

import argparse
import sqlite3
from contextlib import closing
from pathlib import Path


def backup_sqlite(db_path: Path, output_path: Path) -> Path:
    if not db_path.exists():
        raise FileNotFoundError(f"SQLite database not found: {db_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with closing(sqlite3.connect(db_path)) as source, closing(sqlite3.connect(output_path)) as target:
        source.backup(target)
    return output_path


def restore_sqlite(backup_path: Path, db_path: Path, *, force: bool = False) -> Path:
    if not backup_path.exists():
        raise FileNotFoundError(f"SQLite backup not found: {backup_path}")
    if db_path.exists() and not force:
        raise FileExistsError(f"Refusing to overwrite existing database without --force: {db_path}")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = db_path.with_name(f"{db_path.name}.restore_tmp")
    with closing(sqlite3.connect(backup_path)) as source, closing(sqlite3.connect(tmp_path)) as target:
        source.backup(target)
    tmp_path.replace(db_path)
    return db_path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backup or restore the Medical Record Agent edge SQLite database.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    backup = subparsers.add_parser("backup", help="Create a consistent SQLite backup.")
    backup.add_argument("--db", required=True, type=Path)
    backup.add_argument("--output", required=True, type=Path)

    restore = subparsers.add_parser("restore", help="Restore a SQLite backup.")
    restore.add_argument("--backup", required=True, type=Path)
    restore.add_argument("--db", required=True, type=Path)
    restore.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "backup":
        path = backup_sqlite(args.db, args.output)
        print(path)
        return 0
    if args.command == "restore":
        path = restore_sqlite(args.backup, args.db, force=args.force)
        print(path)
        return 0
    raise AssertionError(f"Unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
