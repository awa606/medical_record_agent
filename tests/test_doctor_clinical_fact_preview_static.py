from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_preview_triggers_on_short_clinical_facts() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "function hasClinicalPreviewSignal" in script
    assert "!hasClinicalPreviewSignal(text)" in script
    assert "我发烧39" not in script


def test_doctor_fields_show_partial_and_evidence_labels() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    css = (ROOT / "static" / "doctor.css").read_text(encoding="utf-8")

    assert 'field.status === "partial"' in script
    assert "部分完成" in script
    assert "证据冲突" in script
    assert "查看原文证据" in script
    assert "field-status-text" in script
    assert ".status-badge.partial" in css
    assert ".status-badge.negative" not in css
    assert ".status-dot-label.partial" in css


def test_doctor_preview_explains_no_candidate_and_extraction_source() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "字段抽取：" in script
    assert "extraction_info" in script
    assert "当前信息不足，完成关键补问后生成" in script
    assert "文本导入" in script
    assert "inputStatus" in script
