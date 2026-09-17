from __future__ import annotations

import os
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from app.db import get_connection
from app.main import app
from app.services.knowledge_store import init_knowledge_schema
from tests.auth_helpers import create_user, login_as_admin, login_as_user


def _payload(*, version: str = "2026-v1", content: str | None = None) -> dict:
    return {
        "source_id": "nhc-record-standard",
        "title": "病历书写基本规范",
        "publisher": "国家卫生健康委员会",
        "source_url": "https://www.nhc.gov.cn/example/record-standard.shtml",
        "published_at": "2010-02-04",
        "effective_date": "2010-03-01",
        "version": version,
        "usage_scope": "医生人工参考，不参与自动批准。",
        "document_type": "record-standard",
        "disease_scope": "通用病历书写",
        "filename": "record-standard.md",
        "content": content or "# 基本要求\n病历书写应当客观、真实、准确、及时、完整、规范。",
    }


class TestKnowledgeAdminApi:
    def setup_method(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db = os.environ.get("MEDICAL_RECORD_AGENT_DB")
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(Path(self.temp_dir.name) / "knowledge-admin.sqlite3")
        self.client = TestClient(app)

    def teardown_method(self) -> None:
        if self.previous_db is None:
            os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        else:
            os.environ["MEDICAL_RECORD_AGENT_DB"] = self.previous_db
        self.temp_dir.cleanup()

    def test_admin_import_defaults_inactive_then_enable_and_disable_controls_doctor_search(self) -> None:
        login_as_admin(self.client)
        imported = self.client.post("/api/knowledge/admin/import", json=_payload())
        assert imported.status_code == 201, imported.text
        document_id = imported.json()["document_id"]
        assert imported.json()["is_active"] is False
        assert imported.json()["activation_required"] is True

        documents = self.client.get("/api/knowledge/admin/documents")
        assert documents.status_code == 200, documents.text
        assert documents.json()["documents"][0]["document_type"] == "record-standard"

        test_search = self.client.post(
            "/api/knowledge/admin/test-search",
            json={"query": "客观真实准确", "document_id": document_id},
        )
        assert test_search.status_code == 200, test_search.text
        assert test_search.json()["count"] >= 1
        assert test_search.json()["administrative_test_only"] is True

        create_user(self.client, username="knowledge-doctor")
        login_as_user(self.client, username="knowledge-doctor")
        hidden = self.client.post("/api/knowledge/retrieve", json={"query": "客观真实准确"})
        assert hidden.status_code == 200, hidden.text
        assert all(item.get("document_id") != document_id for item in hidden.json()["results"])

        self.client.post("/api/auth/logout")
        login_as_admin(self.client)
        enabled = self.client.post(f"/api/knowledge/admin/documents/{document_id}/enable")
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["is_active"] is True

        self.client.post("/api/auth/logout")
        login_as_user(self.client, username="knowledge-doctor")
        visible = self.client.post("/api/knowledge/retrieve", json={"query": "客观真实准确"})
        assert visible.status_code == 200, visible.text
        assert any(item.get("document_id") == document_id for item in visible.json()["results"])

        self.client.post("/api/auth/logout")
        login_as_admin(self.client)
        disabled = self.client.post(f"/api/knowledge/admin/documents/{document_id}/disable")
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["is_active"] is False
        assert self.client.get("/api/knowledge/sources").json()["sources"] == []

    def test_permissions_duplicate_sha_new_version_and_audit(self) -> None:
        anonymous = self.client.get("/api/knowledge/admin/documents")
        assert anonymous.status_code == 401

        create_user(self.client, username="forbidden-doctor")
        login_as_user(self.client, username="forbidden-doctor")
        assert self.client.post("/api/knowledge/admin/import", json=_payload()).status_code == 403
        assert self.client.patch("/api/knowledge/admin/documents/missing", json={"title": "x"}).status_code == 403

        self.client.post("/api/auth/logout")
        login_as_admin(self.client)
        first = self.client.post("/api/knowledge/admin/import", json=_payload()).json()
        duplicate = self.client.post("/api/knowledge/admin/import", json=_payload()).json()
        assert duplicate["created"] is False
        assert duplicate["document_id"] == first["document_id"]

        second = self.client.post(
            "/api/knowledge/admin/import",
            json=_payload(version="2026-v2", content="# 修订\n病历修改必须保留痕迹。"),
        )
        assert second.status_code == 201, second.text
        assert second.json()["document_id"] != first["document_id"]
        documents = self.client.get("/api/knowledge/admin/documents").json()["documents"]
        assert len(documents) == 2

        patch = self.client.patch(
            f"/api/knowledge/admin/documents/{second.json()['document_id']}",
            json={"disease_scope": "病历质量", "title": "病历书写基本规范（修订元数据）"},
        )
        assert patch.status_code == 200, patch.text
        assert patch.json()["disease_scope"] == "病历质量"
        assert self.client.patch(
            f"/api/knowledge/admin/documents/{first['document_id']}",
            json={"version": "forbidden"},
        ).status_code == 422

        health = self.client.get("/api/knowledge/admin/health")
        assert health.status_code == 200, health.text
        assert health.json()["document_count"] == 2
        assert health.json()["audit_count"] >= 4

    def test_import_rejects_file_type_size_and_invalid_utf8_boundary(self) -> None:
        login_as_admin(self.client)
        invalid_type = self.client.post(
            "/api/knowledge/admin/import",
            json={**_payload(), "filename": "guide.pdf"},
        )
        assert invalid_type.status_code == 415

        oversized = self.client.post(
            "/api/knowledge/admin/import",
            json={**_payload(), "content": "医" * 700_000},
        )
        assert oversized.status_code == 413

    def test_old_database_schema_migrates_without_losing_rows(self) -> None:
        connection = get_connection()
        try:
            connection.executescript(
                """
                CREATE TABLE knowledge_source (
                    source_id TEXT PRIMARY KEY, title TEXT NOT NULL, publisher TEXT NOT NULL,
                    source_url TEXT NOT NULL, download_url TEXT, published_at TEXT,
                    usage_scope TEXT NOT NULL, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE knowledge_document (
                    document_id TEXT PRIMARY KEY, source_id TEXT NOT NULL, version TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL UNIQUE, retrieved_at TEXT NOT NULL,
                    page_count INTEGER NOT NULL, extraction_method TEXT NOT NULL,
                    is_current INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
                );
                INSERT INTO knowledge_source VALUES
                    ('legacy', 'Legacy', 'Publisher', 'https://example.test', NULL, NULL,
                     'reference', '2026-01-01', '2026-01-01');
                INSERT INTO knowledge_document VALUES
                    ('legacy-doc', 'legacy', 'v1', 'abc', '2026-01-01', 1, 'legacy', 1, '2026-01-01');
                """
            )
            connection.commit()
            init_knowledge_schema(connection)
            row = connection.execute(
                "SELECT is_active, content_format FROM knowledge_document WHERE document_id='legacy-doc'"
            ).fetchone()
            assert tuple(row) == (1, "pdf")
        finally:
            connection.close()
