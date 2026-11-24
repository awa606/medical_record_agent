import sqlite3

import pytest

from app.db.sqlite import init_db, create_encounter
from app.services.knowledge_store import KnowledgePage, ingest_pages, register_knowledge_writer, retrieve_knowledge
from scripts.prepare_test_runtime import prepare


@pytest.mark.parametrize("old", [False, True], ids=["versioned", "legacy"])
def test_only_active_knowledge_copied_and_accounts_history_remain_separate(tmp_path, monkeypatch, old):
    source, target = tmp_path / "source.db", tmp_path / "target.db"
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(source))
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", "Source-only-test-password")
    init_db()
    create_encounter(doctor_user_id=1, deidentified_id="SOURCE-PATIENT", display_name="DO-NOT-COPY")
    for index in (1, 2):
        ingest_pages(source={"source_id": f"guide-{index}", "title": "测试规范", "publisher": "测试机构",
                             "source_url": "https://example.test", "version": "v1", "usage_scope": "测试"},
                     document_bytes=f"guide-{index}".encode(), pages=[KnowledgePage(1, "表现", "发热和咳嗽。")], extraction_method="test")
    with sqlite3.connect(source) as db:
        register_knowledge_writer(db)
        db.execute("UPDATE knowledge_document SET is_active=0 WHERE source_id='guide-2'")
        if old:
            for table in ("knowledge_document_source", "knowledge_published_terms_fts", "knowledge_publication_schema"):
                db.execute(f"DROP TABLE {table}")
        db.commit()
        db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD", "Target-only-test-password")
    monkeypatch.setenv("MRA_TEST_DOCTOR_PASSWORD", "Doctor-only-test-password")
    result = prepare(source, target)
    assert result["knowledge_counts"]["knowledge_document"] == 1
    with sqlite3.connect(target) as db:
        assert db.execute("SELECT deidentified_id FROM patient").fetchall() == [("SIM-TEST-EXAMPLE-001",)]
        assert db.execute("SELECT count(*) FROM auth_session").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM agent_task").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM record_revision").fetchone()[0] == 0
        assert db.execute("SELECT count(*) FROM knowledge_chunk_terms_fts").fetchone()[0] == 1
        assert db.execute("SELECT count(*) FROM knowledge_published_terms_fts").fetchone()[0] == 1
        assert db.execute("SELECT metadata_origin FROM knowledge_document_source").fetchone()[0] == (
            "legacy_observed" if old else "version_import")
        assert not db.execute("PRAGMA foreign_key_check").fetchall()
        db.row_factory = sqlite3.Row
        row = retrieve_knowledge("发热", connection=db)["results"][0]
        assert row["source_id"] == "guide-1"
        history = retrieve_knowledge("发热", connection=db, document_id=row["document_id"], include_inactive=True)
        assert history["results"] == [row]
    with pytest.raises(ValueError, match="already exists"):
        prepare(source, target)
