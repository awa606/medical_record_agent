from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_record_editor_and_field_knowledge_actions_are_bound_to_existing_apis() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert 'id="editRecordButton"' in html
    assert 'id="cancelRecordEditButton"' in html
    assert 'data-record-field-input=' in script
    assert 'data-knowledge-field=' in script
    assert 'api("/api/knowledge/retrieve"' in script
    assert "expected_revision_id" in script
    assert "expected_content_hash" in script
    assert "stale_record_revision" in script
    assert ".record-field-editor textarea" in css
    assert ".record-edit-notice.conflict" in css


def test_knowledge_detail_includes_traceability_fields_and_safe_url() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    for field in (
        "publisher",
        "version",
        "section",
        "page",
        "document_id",
        "chunk_id",
        "content_sha256",
        "source_url",
    ):
        assert field in script
    assert '["http:", "https:"]' in script
