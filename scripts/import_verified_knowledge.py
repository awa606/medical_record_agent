"""Import a verified local Knowledge V1 package without copying business tables.

Stop the target application first. The existing target schema must already have
been initialized by that application. Never use this tool as a database restore.
"""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.knowledge_store import _search_tokens  # noqa: E402

TABLE_KEYS = {
    "knowledge_source": ("source_id",),
    "knowledge_document": ("document_id",),
    "knowledge_chunk": ("chunk_id",),
    "knowledge_embedding": ("chunk_id", "model_id"),
}


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def import_package(source: Path, target: Path, expected_sha: str,
                   manifest: Path, backup: Path) -> dict:
    source, target, backup = source.resolve(), target.resolve(), backup.resolve()
    if not source.is_file() or not target.is_file() or source == target:
        raise ValueError("source and initialized target must be distinct existing databases")
    if backup.exists() or backup in (source, target):
        raise ValueError("backup must be a new file")
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("source has uncheckpointed WAL; export a closed package first")
    if digest(source) != expected_sha:
        raise ValueError("source SHA256 mismatch")
    approved = json.loads(manifest.read_text(encoding="utf-8"))["sources"]
    expected = {s["source_id"]: s.get("imported_content_sha256", s.get("extracted_content_sha256", s["expected_sha256"]))
                for s in approved}
    with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as src:
        src.row_factory = sqlite3.Row
        if src.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("source integrity failure")
        rows = {table: [dict(r) for r in src.execute(f"SELECT * FROM {table}")]
                for table in TABLE_KEYS}
    documents = rows["knowledge_document"]
    if ({r["source_id"] for r in rows["knowledge_source"]} != set(expected)
            or len(documents) != len(expected)
            or {r["source_id"]: r["content_sha256"] for r in documents} != expected
            or any(not r["is_current"] or not r["is_active"] for r in documents)):
        raise ValueError("package does not match the approved active document manifest")
    document_ids = {r["document_id"] for r in documents}
    chunks = rows["knowledge_chunk"]
    chunk_ids = {r["chunk_id"] for r in chunks}
    if (not chunks or any(r["document_id"] not in document_ids or
            hashlib.sha256(r["content"].encode("utf-8")).hexdigest() != r["content_sha256"]
            for r in chunks) or any(r["chunk_id"] not in chunk_ids
                                   for r in rows["knowledge_embedding"])):
        raise ValueError("invalid chunk content hash or package lineage")
    if digest(source) != expected_sha:
        raise ValueError("source changed during validation")
    inserted = {table: 0 for table in TABLE_KEYS}
    with closing(sqlite3.connect(target)) as dst, dst:
        dst.row_factory = sqlite3.Row
        dst.execute("PRAGMA foreign_keys=ON")
        if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("target integrity failure")
        for table in (*TABLE_KEYS, "knowledge_chunk_fts", "knowledge_chunk_terms_fts"):
            if not dst.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone():
                raise ValueError("target application schema is not initialized")
        backup.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive file creation prevents accidentally replacing an earlier backup.
        with backup.open("xb"):
            pass
        with closing(sqlite3.connect(backup)) as copy:
            dst.backup(copy)
        dst.execute("BEGIN IMMEDIATE")
        for table, keys in TABLE_KEYS.items():
            for row in rows[table]:
                where = " AND ".join(f"{key}=?" for key in keys)
                old = dst.execute(f"SELECT * FROM {table} WHERE {where}",
                                  tuple(row[k] for k in keys)).fetchone()
                if old:
                    if dict(old) != row:
                        raise ValueError(f"existing {table} differs; refusing to overwrite")
                    continue
                if table == "knowledge_document" and dst.execute(
                    "SELECT 1 FROM knowledge_document WHERE source_id=? AND is_current=1",
                    (row["source_id"],),
                ).fetchone():
                    raise ValueError("another current document already exists; administrator review required")
                columns = tuple(row)
                dst.execute(f"INSERT INTO {table} ({','.join(columns)}) VALUES "
                            f"({','.join('?' for _ in columns)})", tuple(row.values()))
                inserted[table] += 1
                if table == "knowledge_chunk":
                    dst.execute("INSERT INTO knowledge_chunk_fts(chunk_id,section,content) VALUES (?,?,?)",
                                (row["chunk_id"], row["section"], row["content"]))
                    dst.execute("INSERT INTO knowledge_chunk_terms_fts(chunk_id,terms) VALUES (?,?)",
                                (row["chunk_id"], _search_tokens(f'{row["section"]} {row["content"]}')))
        for row in chunks:
            actual = dst.execute("SELECT section,content FROM knowledge_chunk_fts WHERE chunk_id=?",
                                 (row["chunk_id"],)).fetchall()
            terms = dst.execute("SELECT terms FROM knowledge_chunk_terms_fts WHERE chunk_id=?",
                                (row["chunk_id"],)).fetchall()
            if ([tuple(r) for r in actual] != [(row["section"], row["content"])] or
                    [r[0] for r in terms] != [_search_tokens(f'{row["section"]} {row["content"]}')]):
                raise ValueError("FTS index mismatch; refusing a partial deployment")
        dst.commit()
    return {"source_sha256": expected_sha, "backup_sha256": digest(backup),
            "inserted": inserted, "documents": len(documents), "chunks": len(chunks),
            "embeddings": len(rows["knowledge_embedding"]),
            "business_tables_imported": False, "admin_audit_imported": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=ROOT / "config/knowledge/knowledge_v1.json")
    args = parser.parse_args()
    print(json.dumps(import_package(args.source, args.target, args.source_sha256,
                                    args.manifest, args.backup), ensure_ascii=False))


if __name__ == "__main__":
    main()
