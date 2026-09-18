from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_workspace_renders_knowledge_reference_card() -> None:
    doctor_js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "相关知识参考" in doctor_js
    assert "renderKnowledgeReferenceCard" in doctor_js
    assert "assist:knowledge" in doctor_js
    assert "/api/tasks/${encodeURIComponent(taskId)}/evidence" in doctor_js
    assert "本模块仅展示相关知识参考，不自动确认诊断或处置" in doctor_js


def test_doctor_knowledge_reference_does_not_claim_auto_diagnosis() -> None:
    doctor_js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    forbidden = [
        "AI 已证明",
        "推荐诊断",
        "自动确诊",
    ]
    for phrase in forbidden:
        assert phrase not in doctor_js


def test_doctor_knowledge_reference_styles_are_isolated() -> None:
    css = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert ".knowledge-reference-list" in css
    assert ".knowledge-reference-item" in css
    assert "overflow-wrap: anywhere" in css


def test_admin_knowledge_ui_uses_real_api_and_safe_utf8_rendering() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    doctor_js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert 'id="knowledgeImportForm"' in html
    assert 'id="knowledgeTestSearchForm"' in html
    assert 'id="adminKnowledgePanel"' in html
    assert "/api/knowledge/admin/import" in doctor_js
    assert "/api/knowledge/admin/test-search" in doctor_js
    assert "/api/knowledge/admin/documents/${encodeURIComponent(documentId)}" in doctor_js
    assert 'new TextDecoder("utf-8", { fatal: true })' in doctor_js
    assert "escapeHtml(document.title)" in doctor_js
