"""Version boundaries for normal publication, archived citations, and migrating installations."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
import sqlite3
from threading import Barrier

import pytest
from fastapi.testclient import TestClient

from app.db.sqlite import create_task, get_connection, set_task_owner, update_task
from app.main import app
from app.services import knowledge_store as store
from tests.auth_helpers import create_user, login_as_admin, login_as_user
from tests.test_knowledge_admin_api import _payload


@pytest.fixture
def local_db(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_DB", str(tmp_path / "publication.sqlite3"))


def import_version(version, lines, active):
    return store.ingest_pages(
        source={**_payload(version=version), "title": f"卷 {version}"},
        document_bytes="\n".join(lines).encode("utf-8"),
        pages=[store.KnowledgePage(n, "索引", text) for n, text in enumerate(lines, start=1)],
        extraction_method="test", activate=active,
    )["document_id"]


def test_doctor_ranking_sources_and_admin_history_across_publication(local_db):
    admin = TestClient(app)
    doctor = TestClient(app)
    create_user(admin, username="library-doctor")
    login_as_admin(admin)
    owner = login_as_user(doctor, username="library-doctor")
    task_id = create_task("text", "WAITING_DOCTOR_REVIEW", input_text="飞舟 云桥")
    set_task_owner(task_id, owner["id"])
    update_task(task_id, result_json=json.dumps({"conversation_text": "飞舟 云桥"}, ensure_ascii=False))
    old = import_version("甲", ["飞舟", "云桥", "云桥", "云桥", "星图"], True)
    query = {"query": "飞舟 云桥"}
    search = "/api/knowledge/retrieve"
    docs = "/api/knowledge/admin/documents"

    def doctor_view():
        result = doctor.post(search, json=query)
        assert result.status_code == 200
        source = doctor.get("/api/knowledge/sources/nhc-record-standard").json()
        field = doctor.post(search, json={**query, "task_id": task_id, "related_fields": ["主诉"]})
        case = doctor.get(f"/api/tasks/{task_id}/evidence")
        for response in (result, field, case):
            assert response.status_code == 200
            rows = response.json()["results"]
            assert rows
            for row in rows:
                for key in ("document_id", "version", "document_type", "disease_scope", "metadata_origin"):
                    assert row[key] == source[key]
        return result.json(), source

    baseline = doctor_view()
    assert len(baseline[0]["results"]) == 4
    assert baseline[1]["metadata_origin"] == "version_import"
    assert (baseline[1]["document_type"], baseline[1]["disease_scope"]) == ("record-standard", "通用病历书写")
    assert all(row["usage_scope"] == baseline[1]["usage_scope"] for row in baseline[0]["results"])
    new_payload = {**_payload(version="乙", content="# 飞舟\n" + "\n".join(f"# 飞舟 {i}\n飞舟新版" for i in range(16))),
                   "title": "候审说明", "publisher": "新版单位", "source_url": "https://example.test/v2",
                   "document_type": "teaching-form", "disease_scope": "教学表格"}
    imported = admin.post("/api/knowledge/admin/import", json=new_payload)
    assert imported.status_code == 201, imported.text
    new = imported.json()["document_id"]
    assert doctor_view() == baseline
    assert admin.patch(f"{docs}/{new}", json={"title": "待发表版本", "usage_scope": "新版范围"}).status_code == 200
    assert admin.get(f"{docs}/{old}").json()["title"] == "卷 甲"
    assert doctor_view() == baseline
    preview = "/api/knowledge/admin/test-search"
    assert doctor.post(preview, json={**query, "document_id": new}).status_code == 403
    history = admin.post(preview, json={**query, "document_id": new}).json()["results"]
    assert history and all(r["title"] == "待发表版本" and r["document_id"] == new for r in history)
    assert all(row["usage_scope"] == "新版范围" for row in history)
    assert {(r["document_type"], r["disease_scope"]) for r in history} == {("teaching-form", "教学表格")}
    assert admin.post(f"{docs}/{new}/enable").status_code == 200
    published = doctor_view()
    assert published[1]["title"] == "待发表版本"
    assert published[1]["usage_scope"] == "新版范围"
    assert all(row["usage_scope"] == "新版范围" for row in published[0]["results"])
    assert all(r["source_url"] == new_payload["source_url"] and r["document_id"] == new for r in published[0]["results"])
    archived = admin.post(preview, json={**query, "document_id": old}).json()["results"]
    assert len(archived) == 4
    assert {(r["document_type"], r["disease_scope"]) for r in archived} == {("record-standard", "通用病历书写")}
    assert admin.post(f"{docs}/{old}/enable").status_code == 200
    assert doctor_view() == baseline
    assert admin.post(f"{docs}/{old}/disable").status_code == 200
    assert doctor.get("/api/knowledge/sources").json()["sources"] == []
    assert doctor.post(search, json=query).json()["results"] == []
    assert admin.post(preview, json={**query, "document_id": old}).json()["count"] == 4


@pytest.mark.parametrize(("registration", "expected"), [
    ({}, ("clinical-reference", "")),
    ({"document_type": "   ", "disease_scope": "  "}, ("   ", "  ")),
])
def test_search_returns_the_stored_classification_for_optional_import_fields(local_db, registration, expected):
    admin, doctor = TestClient(app), TestClient(app)
    create_user(admin, username="classification-reader")
    login_as_admin(admin)
    login_as_user(doctor, username="classification-reader")
    payload = _payload(content="# 课堂登记\n合成归档记录")
    del payload["document_type"], payload["disease_scope"]
    imported = admin.post("/api/knowledge/admin/import", json={**payload, **registration})
    assert imported.status_code == 201
    doc = imported.json()["document_id"]
    assert admin.post(f"/api/knowledge/admin/documents/{doc}/enable").status_code == 200
    hits = doctor.post("/api/knowledge/retrieve", json={"query": "归档"}).json()["results"]
    assert [(r["document_type"], r["disease_scope"]) for r in hits] == [expected]
    assert hits[0]["metadata_origin"] == "version_import"


def test_same_content_with_another_identity_is_rejected_without_audit_misattribution(local_db):
    client = TestClient(app)
    login_as_admin(client)
    route = "/api/knowledge/admin/import"
    doc = client.post(route, json=_payload()).json()["document_id"]
    repeat = client.post(route, json=_payload()).json()
    assert repeat["document_id"] == doc and not repeat["created"]
    for changes in ({"source_id": "different"}, {"version": "different"}):
        assert client.post(route, json={**_payload(), **changes}).status_code == 409
    assert client.get("/api/knowledge/admin/documents").json()["count"] == 1
    assert client.get("/api/knowledge/admin/health").json()["audit_count"] == 2


def test_failed_activation_rolls_back_flags_source_fts_and_audit(local_db):
    old = import_version("甲", ["飞舟 云桥", "星图"], True)
    new = import_version("乙", ["云桥", "云桥 新版"], False)
    before = store.retrieve_knowledge("飞舟 云桥")
    with closing(get_connection()) as conn:
        conn.execute("""CREATE TRIGGER reject_audit BEFORE INSERT ON knowledge_admin_audit
                        BEGIN SELECT RAISE(ABORT,'interrupted switch'); END""")
        with pytest.raises(sqlite3.IntegrityError, match="interrupted switch"):
            store.set_knowledge_document_active(new, active=True, actor_user_id=1, connection=conn)
        assert conn.execute("SELECT count(*) FROM knowledge_admin_audit").fetchone()[0] == 0
        assert conn.execute("SELECT title FROM knowledge_source").fetchone()[0] == "卷 甲"
        assert store.get_knowledge_source("nhc-record-standard", conn)["document_id"] == old
        assert store.retrieve_knowledge("飞舟 云桥", connection=conn) == before
        conn.execute("DROP TRIGGER reject_audit")
        store.set_knowledge_document_active(new, active=True, actor_user_id=1, connection=conn)
        assert conn.execute("SELECT count(*) FROM knowledge_admin_audit").fetchone()[0] == 1
        assert store.get_knowledge_source("nhc-record-standard", conn)["document_id"] == new


def test_two_concurrent_enable_requests_publish_one_complete_document(local_db):
    old = import_version("甲", ["飞舟 旧版"], True)
    new = import_version("乙", ["飞舟 新版一", "飞舟 新版二"], False)
    start = Barrier(2)

    def enable(document_id):
        start.wait(timeout=5)
        return store.set_knowledge_document_active(document_id, active=True, actor_user_id=2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(enable, [old, new]))
    assert [row["document_id"] for row in responses] == [old, new]
    assert all(row["is_current"] and row["is_active"] for row in responses)
    with closing(get_connection()) as conn:
        by_source = store.get_knowledge_source("nhc-record-standard", conn)
        chunks = conn.execute("SELECT chunk_id FROM knowledge_chunk WHERE document_id=?", (by_source["document_id"],))
        assert {r[0] for r in chunks} == {r[0] for r in conn.execute("SELECT chunk_id FROM knowledge_published_terms_fts")}
        assert conn.execute("SELECT count(*) FROM knowledge_document WHERE is_current=1 AND is_active=1").fetchone()[0] == 1
        assert conn.execute("SELECT count(*) FROM knowledge_admin_audit").fetchone()[0] == 2


@pytest.mark.parametrize("missing_classification_columns", [False, True])
def test_schema_upgrade_respects_outer_transaction_and_legacy_metadata_provenance(local_db, missing_classification_columns):
    old = import_version("甲", ["旧版 星图"], True)
    new = import_version("乙", ["新版 飞舟"], False)
    with closing(get_connection()) as conn:
        store.register_knowledge_writer(conn)
        # Recreate the specific persisted shape of a pre-versioned installation.
        conn.executescript("""DROP TABLE knowledge_published_terms_fts; DROP TABLE knowledge_document_source;
                              DROP TABLE knowledge_publication_schema;
                              UPDATE knowledge_source SET title='迁移时唯一可见的标题';""")
        if missing_classification_columns:
            conn.execute("ALTER TABLE knowledge_source DROP COLUMN document_type")
            conn.execute("ALTER TABLE knowledge_source DROP COLUMN disease_scope")
        conn.execute("BEGIN IMMEDIATE")
        store.init_knowledge_schema(conn)
        assert conn.in_transaction
        assert store.get_knowledge_document(old, conn)["metadata_origin"] == "legacy_observed"
        conn.rollback()
        assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_document_source'").fetchone()
        store.init_knowledge_schema(conn)
        for doc in (old, new):
            row = store.get_knowledge_document(doc, conn)
            assert (row["title"], row["metadata_origin"]) == ("迁移时唯一可见的标题", "legacy_observed")
            hits = store.retrieve_knowledge("旧版" if doc == old else "新版", connection=conn,
                                            document_id=doc, include_inactive=True)["results"]
            expected = ("clinical-reference", "") if missing_classification_columns else ("record-standard", "通用病历书写")
            assert [(r["document_type"], r["disease_scope"], r["metadata_origin"]) for r in hits] == [(*expected, "legacy_observed")]
        store.update_knowledge_document_metadata(new, metadata={"title": "校订仅该版标题"}, actor_user_id=1, connection=conn)
        assert store.get_knowledge_document(new, conn)["metadata_origin"] == "legacy_observed"
        assert store.get_knowledge_document(old, conn)["title"] == "迁移时唯一可见的标题"
        assert conn.execute("SELECT count(*) FROM knowledge_published_terms_fts").fetchone()[0] == 1


def test_like_without_full_text_keeps_version_boundaries_and_rebuilds_on_engine_return(local_db, monkeypatch):
    with monkeypatch.context() as scope:
        scope.setattr(store, "knowledge_fts_available", lambda _: False)
        old = import_version("甲", ["星舟旧页"], True)
        new = import_version("乙", ["星舟新页"], False)
        result = store.retrieve_knowledge("星舟")
        assert result["retrieval_mode"] == "like_v1"
        assert [r["document_id"] for r in result["results"]] == [old]
        assert [r["document_id"] for r in store.retrieve_knowledge("星舟", document_id=new, include_inactive=True)["results"]] == [new]
        with closing(get_connection()) as conn:
            assert not conn.execute("SELECT 1 FROM sqlite_master WHERE name LIKE '%_fts'").fetchone()
        store.set_knowledge_document_active(new, active=True, actor_user_id=4)
    rebuilt = store.retrieve_knowledge("星舟")
    assert rebuilt["retrieval_mode"] == "fts5_v1"
    assert [r["document_id"] for r in rebuilt["results"]] == [new]
    assert store.retrieve_knowledge("星", document_id=old, include_inactive=True)["results"][0]["title"] == "卷 甲"

def test_allowed_source_identifiers_with_same_slug_are_distinct(local_db):
    client = TestClient(app)
    login_as_admin(client)
    route = "/api/knowledge/admin/import"
    first = {**_payload(), "source_id": "Library.A"}
    second = {**first, "source_id": "library-a"}
    saved = client.post(route, json=first).json()
    assert saved["source_id"] == "Library.A"
    assert client.post(route, json=first).json()["document_id"] == saved["document_id"]
    assert client.post(route, json=second).status_code == 409
    other = client.post(route, json={**second, "content": "另一来源的正文"}).json()
    assert (other["source_id"], other["created"]) == ("library-a", True)


def test_legacy_connections_can_read_but_cannot_partially_change_published_documents(local_db):
    original = import_version("甲", ["云桥 原件"], True)
    draft = import_version("乙", ["云桥 候审"], False)
    before = store.retrieve_knowledge("云桥")
    with closing(get_connection()) as old:
        assert old.execute("SELECT title FROM knowledge_source").fetchone()[0] == "卷 甲"
        for sql, values in (
            ("UPDATE knowledge_document SET is_current=0 WHERE document_id=?", (original,)),
            ("UPDATE knowledge_document SET is_active=1 WHERE document_id=?", (draft,)),
            ("UPDATE knowledge_source SET title='另一来源' WHERE source_id=?", ("nhc-record-standard",)),
            ("UPDATE knowledge_document SET effective_date='2099-01-01' WHERE document_id=?", (original,)),
            ("INSERT INTO knowledge_admin_audit(actor_user_id,action,document_id,detail_json,created_at) "
             "VALUES(1,'knowledge_import_duplicate',?,'{}','test')", (draft,)),
        ):
            with pytest.raises(sqlite3.OperationalError, match="mra_versioned_knowledge_writer"):
                old.execute(sql, values)
            old.rollback()
    assert store.retrieve_knowledge("云桥") == before
    assert store.get_knowledge_document(original)["effective_date"] == "2010-03-01"
    assert store.knowledge_health()["audit_count"] == 0
