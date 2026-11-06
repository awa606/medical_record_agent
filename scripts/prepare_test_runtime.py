"""Initialize an empty test database; copy active knowledge only, never identities."""
from __future__ import annotations

import argparse
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3


def prepare(source: Path, target: Path) -> dict:
    if target.exists():
        raise ValueError("Target already exists; never replace a business database")
    if not source.is_file() or source.resolve() == target.resolve():
        raise ValueError("A separate consistent knowledge-source backup is required")
    if not os.environ.get("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD"):
        raise ValueError("Independent bootstrap password required")
    if not os.environ.get("MRA_TEST_DOCTOR_PASSWORD"):
        raise ValueError("Independent test doctor password required")
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    wal = Path(str(source) + "-wal")
    if wal.exists() and wal.stat().st_size:
        raise ValueError("Use a closed consistent backup, not a live WAL database")
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(target)
    from app.db.sqlite import init_db, create_encounter, create_user
    from app.services.knowledge_store import init_knowledge_schema, _search_tokens
    init_db()
    init_knowledge_schema()
    with closing(sqlite3.connect(source.resolve().as_uri() + "?mode=ro", uri=True)) as src, closing(sqlite3.connect(target)) as dst:
        src.row_factory = sqlite3.Row
        if src.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise ValueError("Source integrity check failed")
        documents = list(src.execute("SELECT * FROM knowledge_document WHERE is_current=1 AND is_active=1"))
        if not documents:
            raise ValueError("No enabled knowledge in source; target retained for diagnosis")
        doc_ids = {row["document_id"] for row in documents}
        source_ids = {row["source_id"] for row in documents}
        chunks = [row for row in src.execute("SELECT * FROM knowledge_chunk") if row["document_id"] in doc_ids]
        if not chunks or any(hashlib.sha256(row["content"].encode("utf8")).hexdigest() != row["content_sha256"] for row in chunks):
            raise ValueError("Knowledge chunk hash mismatch")
        chunk_ids = {row["chunk_id"] for row in chunks}
        projection = {
            "knowledge_source": [row for row in src.execute("SELECT * FROM knowledge_source") if row["source_id"] in source_ids],
            "knowledge_document": documents,
            "knowledge_chunk": chunks,
            "knowledge_embedding": [row for row in src.execute("SELECT * FROM knowledge_embedding") if row["chunk_id"] in chunk_ids],
        }
        with dst:
            dst.execute("PRAGMA foreign_keys=ON")
            for table, rows in projection.items():
                columns = [row[1] for row in dst.execute(f'PRAGMA table_info("{table}")')]
                if rows and set(columns) != set(rows[0].keys()):
                    raise ValueError("Knowledge schema differs; no silent migration allowed")
                dst.executemany(f'INSERT INTO "{table}" VALUES ({",".join("?" for _ in columns)})',
                                [[row[column] for column in columns] for row in rows])
            for row in chunks:
                dst.execute("INSERT INTO knowledge_chunk_fts(chunk_id,section,content) VALUES(?,?,?)",
                            (row["chunk_id"], row["section"], row["content"]))
                dst.execute("INSERT INTO knowledge_chunk_terms_fts(chunk_id,terms) VALUES(?,?)",
                            (row["chunk_id"], _search_tokens(row["section"] + " " + row["content"])))
        assert not dst.execute("PRAGMA foreign_key_check").fetchall()
        admin_id = dst.execute("SELECT id FROM auth_user WHERE username='admin'").fetchone()[0]
        assert dst.execute("SELECT count(*) FROM auth_session").fetchone()[0] == 0
        assert dst.execute("SELECT count(*) FROM agent_task").fetchone()[0] == 0
    doctor_id = create_user(username="doctor", password=os.environ["MRA_TEST_DOCTOR_PASSWORD"],
                            display_name="测试医生", role="doctor")
    example = create_encounter(doctor_user_id=doctor_id, deidentified_id="SIM-TEST-EXAMPLE-001",
                               display_name="合成示例（待输入）", check_in_status="checked_in")
    assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
    return {"source_sha256": source_hash, "knowledge_counts": {key: len(value) for key, value in projection.items()},
            "example_encounter_id": example["id"], "business_history_copied": False, "sessions_copied": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source, args.target), ensure_ascii=False))
