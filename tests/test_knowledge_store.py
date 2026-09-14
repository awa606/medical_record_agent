from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app
from app.db.sqlite import get_connection
from app.services import knowledge_store
from app.services.knowledge_store import KnowledgePage, get_knowledge_source, ingest_pages, retrieve_knowledge
from tests.auth_helpers import login_as_admin


SOURCE = {
    "source_id": "nhc-test",
    "title": "测试指南",
    "publisher": "测试发布机构",
    "source_url": "https://example.test/source.pdf",
    "download_url": "https://example.test/source.pdf",
    "published_at": "2026-01-01",
    "usage_scope": "测试",
    "version": "2026年版",
}


def test_ingest_is_idempotent_versions_source_and_returns_page_citations() -> None:
    with tempfile.TemporaryDirectory() as directory:
        previous = os.environ.get("MEDICAL_RECORD_AGENT_DB")
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(directory) / "knowledge.sqlite3")
        try:
            pages = [KnowledgePage(page=3, section="临床表现", content="患者可出现发热、咳嗽和咽痛等临床表现。")]
            first = ingest_pages(source=SOURCE, document_bytes=b"version-one", pages=pages, extraction_method="unit")
            repeated = ingest_pages(source=SOURCE, document_bytes=b"version-one", pages=pages, extraction_method="unit")
            updated_source = {**SOURCE, "version": "2026年修订版"}
            second = ingest_pages(source=updated_source, document_bytes=b"version-two", pages=pages, extraction_method="unit")

            assert first["created"] is True
            assert repeated["created"] is False
            assert repeated["document_id"] == first["document_id"]
            assert second["created"] is True
            assert second["document_id"] != first["document_id"]
            assert get_knowledge_source("nhc-test")["version"] == "2026年修订版"

            result = retrieve_knowledge("发热咳嗽", limit=5)
            assert result["retrieval_mode"] == "fts5_v1"
            assert result["results"][0]["page"] == 3
            assert result["results"][0]["publisher"] == "测试发布机构"
            assert result["results"][0]["content_sha256"]
            assert result["results"][0]["dense_score"] is None
        finally:
            if previous is None:
                os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
            else:
                os.environ["MEDICAL_RECORD_AGENT_DB"] = previous


def test_api_uses_index_when_database_contains_chunks() -> None:
    with tempfile.TemporaryDirectory() as directory:
        previous = os.environ.get("MEDICAL_RECORD_AGENT_DB")
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(directory) / "knowledge-api.sqlite3")
        try:
            ingest_pages(
                source=SOURCE,
                document_bytes=b"api-version",
                pages=[KnowledgePage(page=5, section="风险", content="持续高热并呼吸困难需要及时由医生评估。")],
                extraction_method="unit",
            )
            client = TestClient(app)
            login_as_admin(client)
            response = client.post("/api/knowledge/retrieve", json={"query": "持续高热呼吸困难"})
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["retrieval_mode"] == "fts5_v1"
            assert payload["results"][0]["page"] == 5
            assert payload["results"][0]["retrieval_mode"] == "fts5_v1"
            assert payload["results"][0]["document_id"]
            assert payload["results"][0]["chunk_id"]
        finally:
            if previous is None:
                os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
            else:
                os.environ["MEDICAL_RECORD_AGENT_DB"] = previous


def test_runtime_falls_back_to_fts_when_local_embedding_model_is_missing(monkeypatch) -> None:
    with tempfile.TemporaryDirectory() as directory:
        previous = os.environ.get("MEDICAL_RECORD_AGENT_DB")
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(directory) / "knowledge-offline.sqlite3")
        try:
            imported = ingest_pages(
                source=SOURCE,
                document_bytes=b"offline-version",
                pages=[KnowledgePage(page=7, section="风险", content="发热咳嗽需要结合病程由医生评估。")],
                extraction_method="unit",
            )
            connection = get_connection()
            try:
                chunk_id = connection.execute(
                    "SELECT chunk_id FROM knowledge_chunk WHERE document_id = ?", (imported["document_id"],)
                ).fetchone()[0]
                connection.execute(
                    """
                    INSERT INTO knowledge_embedding(chunk_id, model_id, dimensions, vector_json, created_at)
                    VALUES (?, ?, 2, ?, '2026-09-14T00:00:00+00:00')
                    """,
                    (chunk_id, knowledge_store.DEFAULT_EMBEDDING_MODEL, json.dumps([1.0, 0.0])),
                )
                connection.commit()
            finally:
                connection.close()

            def missing_model(_model_id: str, _local_files_only: bool = True):
                raise OSError("model cache unavailable")

            monkeypatch.setattr(knowledge_store, "_embedding_model", missing_model)
            result = retrieve_knowledge("发热咳嗽", limit=5)
            assert result["retrieval_mode"] == "fts5_v1"
            assert result["results"][0]["dense_score"] is None
        finally:
            if previous is None:
                os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
            else:
                os.environ["MEDICAL_RECORD_AGENT_DB"] = previous
