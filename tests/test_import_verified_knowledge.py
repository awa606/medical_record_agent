import hashlib
import json
import sqlite3

import pytest

from app.services.knowledge_store import (
    KnowledgePage, ingest_pages, init_knowledge_schema, register_knowledge_writer, retrieve_knowledge,
)
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
        register_knowledge_writer(conn)
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
        register_knowledge_writer(conn)
        conn.execute("UPDATE knowledge_document SET is_active=0")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(ValueError, match="approved active"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")


def test_bad_chunk_hash_rejected(package):
    source, target, manifest, folder = package
    with sqlite3.connect(source) as conn:
        register_knowledge_writer(conn)
        conn.execute("UPDATE knowledge_chunk SET content='tampered'")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    with pytest.raises(ValueError, match="chunk content hash"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")


@pytest.mark.parametrize("table", ["knowledge_chunk_terms_fts", "knowledge_published_terms_fts"])
def test_existing_index_corruption_is_not_silently_accepted(package, table):
    source, target, manifest, folder = package
    import_package(source, target, digest(source), manifest, folder / "backup1.db")
    with sqlite3.connect(target) as conn:
        conn.execute(f"DELETE FROM {table}")
    with pytest.raises(ValueError, match="FTS index mismatch"):
        import_package(source, target, digest(source), manifest, folder / "backup2.db")


def legacy_schema(path):
    with sqlite3.connect(path) as conn:
        for table in ("knowledge_document_source", "knowledge_published_terms_fts", "knowledge_publication_schema"):
            conn.execute(f"DROP TABLE {table}")
        conn.commit()
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")


@pytest.mark.parametrize("old", [False, True], ids=["versioned", "legacy"])
def test_verified_source_provenance_and_both_search_routes(package, old):
    source, target, manifest, folder = package
    if old:
        legacy_schema(source)
        legacy_schema(target)
    with sqlite3.connect(source) as src:
        doc = src.execute("SELECT document_id FROM knowledge_document").fetchone()[0]
        times = src.execute("SELECT created_at,updated_at FROM " +
                            ("knowledge_source" if old else "knowledge_document_source")).fetchone()
    source_hash = digest(source)
    imported = import_package(source, target, source_hash, manifest, folder / "first.db")
    assert imported["inserted"]["knowledge_document_source"] == 1
    with sqlite3.connect(target) as db:
        db.row_factory = sqlite3.Row
        origin = "legacy_observed" if old else "version_import"
        assert tuple(db.execute("SELECT metadata_origin,created_at,updated_at FROM knowledge_document_source").fetchone()) == (origin, *times)
        for kwargs in ({}, {"include_inactive": True, "document_id": doc}):
            results = retrieve_knowledge("病历书写", connection=db, **kwargs)["results"]
            assert [(r["document_id"], r["metadata_origin"]) for r in results] == [(doc, origin)]
    before = digest(target)
    assert not any(import_package(source, target, source_hash, manifest, folder / "again.db")["inserted"].values())
    assert digest(target) == before and digest(source) == source_hash


def test_partial_new_package_cannot_pass_as_legacy(package):
    source, target, manifest, folder = package
    with sqlite3.connect(source) as db:
        db.execute("DELETE FROM knowledge_document_source")
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    before = digest(target)
    with pytest.raises(ValueError, match="missing versioned source"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")
    assert digest(target) == before and not (folder / "backup.db").exists()


def test_snapshot_collision_preserves_origin_and_existing_rows(package):
    source, target, manifest, folder = package
    import_package(source, target, digest(source), manifest, folder / "first.db")
    with sqlite3.connect(target) as db:
        db.execute("UPDATE knowledge_document_source SET metadata_origin='legacy_observed'")
    before = digest(target)
    with pytest.raises(ValueError, match="versioned source metadata differs"):
        import_package(source, target, digest(source), manifest, folder / "conflict.db")
    assert digest(target) == before


def test_abort_after_migration_rolls_back_schema_public_and_historical_indexes(package):
    source, target, manifest, folder = package
    legacy_schema(target)
    with sqlite3.connect(target) as db:
        db.execute("""CREATE TRIGGER stop_chunk BEFORE INSERT ON knowledge_chunk
                      BEGIN SELECT RAISE(ABORT, 'controlled failure'); END""")
    before = digest(target)
    with pytest.raises(sqlite3.IntegrityError, match="controlled failure"):
        import_package(source, target, digest(source), manifest, folder / "backup.db")
    assert digest(target) == before and (folder / "backup.db").exists()
    with sqlite3.connect(target) as db:
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='knowledge_document_source'").fetchone()
        assert db.execute("SELECT count(*) FROM knowledge_source").fetchone()[0] == 0
