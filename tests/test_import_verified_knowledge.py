import hashlib
import json
import sqlite3

import pytest

from app.services.knowledge_store import KnowledgePage, ingest_pages, init_knowledge_schema
from scripts.import_verified_knowledge import digest, import_package


@pytest.fixture
def package(tmp_path, monkeypatch):
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(source))
    source_meta = {"source_id": "official-test", "title": "测试规范", "publisher": "测试机构",
                   "source_url": "https://example.test/official", "version": "v1", "usage_scope": "测试"}
    ingest_pages(source=source_meta, document_bytes=b"approved-v1",
                 pages=[KnowledgePage(1, "病历", "病历书写应当客观真实准确完整。")], extraction_method="test")
    with sqlite3.connect(target) as conn:
        conn.row_factory = sqlite3.Row
        init_knowledge_schema(conn)
        conn.execute("CREATE TABLE encounter(id TEXT PRIMARY KEY, revision TEXT)")
        conn.execute("INSERT INTO encounter VALUES ('keep-me', 'unchanged')")
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"sources": [{"source_id": "official-test",
        "expected_sha256": hashlib.sha256(b"approved-v1").hexdigest()}]}), encoding="utf-8")
    return source, target, manifest, tmp_path


def test_import_keeps_business_and_is_idempotent(package):
    source, target, manifest, folder = package
    result = import_package(source, target, digest(source), manifest, folder / "backup1.db")
    assert result["inserted"]["knowledge_document"] == 1
    assert result["business_tables_imported"] is False
    before = digest(target)
    again = import_package(source, target, digest(source), manifest, folder / "backup2.db")
    assert not any(again["inserted"].values())
    assert digest(target) == before
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT * FROM encounter").fetchall() == [("keep-me", "unchanged")]
        assert conn.execute("SELECT count(*) FROM knowledge_chunk_fts WHERE knowledge_chunk_fts MATCH '病历书'").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM knowledge_admin_audit").fetchone()[0] == 0


def test_wrong_source_hash_changes_nothing(package):
    source, target, manifest, folder = package
    before = digest(target)
    with pytest.raises(ValueError, match="SHA256"):
        import_package(source, target, "0" * 64, manifest, folder / "backup.db")
    assert digest(target) == before
    assert not (folder / "backup.db").exists()


def test_late_conflict_rolls_back_all_inserts(package):
    source, target, manifest, folder = package
    import_package(source, target, digest(source), manifest, folder / "backup1.db")
    with sqlite3.connect(target) as conn:
        conn.execute("DELETE FROM knowledge_source")
        conn.execute("UPDATE knowledge_document SET version='manual-edit'")
    with pytest.raises(ValueError, match="refusing to overwrite"):
        import_package(source, target, digest(source), manifest, folder / "backup2.db")
    with sqlite3.connect(target) as conn:
        assert conn.execute("SELECT count(*) FROM knowledge_source").fetchone()[0] == 0
        assert conn.execute("SELECT version FROM knowledge_document").fetchone()[0] == "manual-edit"
        assert conn.execute("SELECT revision FROM encounter").fetchone()[0] == "unchanged"


def test_unapproved_document_rejected(package):
    source, target, manifest, folder = package
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE knowledge_document SET is_active=0")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(ValueError, match="approved active"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")


def test_bad_chunk_hash_rejected(package):
    source, target, manifest, folder = package
    with sqlite3.connect(source) as conn:
        conn.execute("UPDATE knowledge_chunk SET content='tampered'")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(ValueError, match="chunk content hash"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")


def test_existing_index_corruption_is_not_silently_accepted(package):
    source, target, manifest, folder = package
    import_package(source, target, digest(source), manifest, folder / "backup1.db")
    with sqlite3.connect(target) as conn:
        conn.execute("DELETE FROM knowledge_chunk_terms_fts")
    with pytest.raises(ValueError, match="FTS index mismatch"):
        import_package(source, target, digest(source), manifest, folder / "backup2.db")
