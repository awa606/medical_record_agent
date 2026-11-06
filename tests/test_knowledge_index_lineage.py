import hashlib

import pytest

from app.db.sqlite import get_connection
from app.services.knowledge_store import KnowledgePage, ingest_pages
from scripts.ingest_knowledge import _index_payload
from tests.test_knowledge_store import SOURCE


def test_full_page_derivative_is_deterministic_and_preserves_old_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "knowledge.sqlite3"))
    pages = [KnowledgePage(page=n, section=f"章节 {n}", content=f"发热记录第{n}页") for n in (1, 2)]
    original = b"immutable official source fixture"
    old = ingest_pages(source=SOURCE, document_bytes=original, pages=pages,
                       extraction_method="test", max_chunks=1)
    source = {**SOURCE, "version": "full-index-v2", "index_profile": "full-pages-v1"}
    payload, lineage = _index_payload(source, original, pages)
    assert _index_payload(source, original, pages)[0] == payload
    assert lineage["original_file_sha256"] == hashlib.sha256(original).hexdigest()
    assert payload != original
    new = ingest_pages(source=source, document_bytes=payload, pages=pages,
                       extraction_method="test", activate=False)
    repeated = ingest_pages(source=source, document_bytes=payload, pages=pages,
                            extraction_method="test", activate=False)
    assert new["created"] and not new["is_active"] and new["page_count"] == 2
    assert not repeated["created"] and repeated["document_id"] == new["document_id"]
    with get_connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM knowledge_chunk WHERE document_id=?", (old["document_id"],)).fetchone()[0] == 1
        assert conn.execute("SELECT is_current FROM knowledge_document WHERE document_id=?", (old["document_id"],)).fetchone()[0] == 1


def test_full_page_profile_rejects_chunk_cap_and_changed_text_changes_identity():
    source = {**SOURCE, "index_profile": "full-pages-v1"}
    pages = [KnowledgePage(page=1, section="症状", content="发热")]
    with pytest.raises(ValueError, match="without a chunk cap"):
        _index_payload({**source, "max_chunks": 10}, b"original", pages)
    first, _ = _index_payload(source, b"original", pages)
    second, _ = _index_payload(source, b"original", [KnowledgePage(page=1, section="症状", content="发热、咳嗽")])
    assert first != second
