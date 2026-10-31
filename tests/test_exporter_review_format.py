from pathlib import Path

import pymupdf

from app.schemas import MedicalField, MedicalRecordFields, SafetyCheckResult
from app.services.exporter import (
    WORD_NOTICE,
    _paragraphs_markdown,
    _record_paragraphs,
    export_record,
    render_pdf,
)


def _export(tmp_path, monkeypatch, fields, *, approved=True):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path))
    safety = SafetyCheckResult(passed=True)
    paths = export_record(19019, {
        "fields": fields.model_dump(),
        "safety_check": safety.model_dump(),
        "approved": approved,
    })
    assert set(paths) == {"pdf_path"}, paths
    pdf_path = Path(paths["pdf_path"])
    assert pdf_path.read_bytes()[:5] == b"%PDF-"
    assert pdf_path.stat().st_size > 800
    paragraphs = _record_paragraphs(fields, safety, approved=approved)
    markdown = _paragraphs_markdown(paragraphs)
    return markdown, [text for _kind, text in paragraphs], pdf_path


def test_pdf_export_keeps_hierarchy_notice_and_searchable_text(tmp_path, monkeypatch):
    fields = MedicalRecordFields(chief_complaint=MedicalField(value="发热伴咳嗽2天"))
    markdown, paragraphs, pdf_path = _export(tmp_path, monkeypatch, fields)

    assert markdown.startswith("# 门诊病历")
    assert paragraphs[0] == "门诊病历"
    assert not any(text.startswith(("# ", "## ", "> ")) for text in paragraphs)
    assert sum(text.count(WORD_NOTICE) for text in paragraphs) == 1
    assert "草稿" not in "\n".join(paragraphs)
    assert "审核状态：已完成医生分项审核" in paragraphs

    with pymupdf.open(pdf_path) as document:
        assert document.page_count == 1
        text = "".join(document[0].get_text().split())
        fonts = document[0].get_fonts()
    assert "初诊病历记录" in text
    assert "主诉" in text and "发热伴咳嗽2天" in text
    assert "医师签名" in text
    assert any("NotoSansSC" in str(font[3]) for font in fonts), fonts


def test_pdf_includes_doctor_name_when_provided(tmp_path, monkeypatch):
    fields = MedicalRecordFields(chief_complaint=MedicalField(value="发热"))
    safety = SafetyCheckResult(passed=True)
    target = tmp_path / "doctor_name.pdf"
    render_pdf(
        target,
        fields,
        safety,
        approved=True,
        task_id=1,
        encounter_id=2,
        doctor_name="李医生",
    )
    with pymupdf.open(target) as document:
        text = "".join(document[0].get_text().split())
    assert "接诊医师" in text
    assert "李医生" in text


def test_pdf_short_generated_record_with_full_meta_fits_one_page(tmp_path):
    from app.agents import MedicalRecordOrchestrator

    result = MedicalRecordOrchestrator().run_from_text("患者发热三天，伴咳嗽。")
    fields = MedicalRecordFields.model_validate(result["fields"])
    target = tmp_path / "short_full_meta.pdf"
    render_pdf(
        target,
        fields,
        SafetyCheckResult(passed=True),
        approved=True,
        task_id=5,
        encounter_id=8,
        department="全科门诊",
        encounter_created_at="2026-10-31T09:00:00",
        patient_display_name="张示例",
        patient_deidentified_id="SIM-DEMO",
        doctor_name="李医生",
    )
    with pymupdf.open(target) as document:
        assert document.page_count == 1
        text = "".join(document[0].get_text())
    assert "接诊医师" in text
    assert "李医生" in text
    assert "医师签名" in text


def test_pdf_renders_empty_record_and_hospital_name(tmp_path, monkeypatch):
    monkeypatch.setenv("MRA_HOSPITAL_NAME", "测试医院")
    fields = MedicalRecordFields()
    _, _, pdf_path = _export(tmp_path, monkeypatch, fields, approved=False)
    with pymupdf.open(pdf_path) as document:
        text = "".join(document[0].get_text().split())
    assert "测试医院" in text
    assert "未提及/待补充" in text
    assert "未完成医生分项审核" in text


def test_pdf_paginates_long_record_and_keeps_signature_on_last_page(tmp_path, monkeypatch):
    long_text = "反复发热咳嗽两周，伴咽痛，无胸痛。" * 120
    fields = MedicalRecordFields(
        chief_complaint=MedicalField(value="发热咳嗽两周"),
        present_illness=MedicalField(value=long_text),
    )
    _, _, pdf_path = _export(tmp_path, monkeypatch, fields)
    with pymupdf.open(pdf_path) as document:
        assert document.page_count >= 2
        pages = ["".join(page.get_text().split()) for page in document]
    first_page = pages[0]
    last_page = pages[-1]
    assert "现病史" in first_page
    assert "反复发热" in first_page
    assert "医师签名" in last_page
    assert "AI辅助生成" in last_page
    for page_text in pages:
        if "辅助检查" in page_text:
            assert "本次未提供" in page_text


def test_reviewed_content_does_not_keep_generic_pending_message(tmp_path, monkeypatch):
    fields = MedicalRecordFields(chief_complaint=MedicalField(
        value="发热伴咳嗽2天", status="partial", missing_elements=["待医生补充"],
        confirmed_by_doctor=True, doctor_review_status="content_confirmed",
    ))
    markdown, _, _ = _export(tmp_path, monkeypatch, fields)
    section = markdown.split("## 主诉\n", 1)[1].split("## 现病史", 1)[0]
    assert "发热伴咳嗽2天" in section
    assert "待医生补充" not in section
    assert "部分完成，仍需补充" not in section
    assert "内容已核对" in section


def test_reviewed_partial_keeps_specific_missing_information(tmp_path, monkeypatch):
    fields = MedicalRecordFields(present_illness=MedicalField(
        value="咳嗽", status="partial", missing_elements=["起病时间", "诱因"],
        confirmed_by_doctor=True, doctor_review_status="content_confirmed",
    ))
    markdown, _, _ = _export(tmp_path, monkeypatch, fields)
    assert "记录仍缺：起病时间、诱因" in markdown
    assert "内容已核对" in markdown


def test_missing_review_is_not_exported_as_obtained_fact(tmp_path, monkeypatch):
    fields = MedicalRecordFields()
    fields.past_history.confirmed_by_doctor = True
    fields.past_history.doctor_review_status = "not_asked_confirmed"
    fields.allergy_history.confirmed_by_doctor = True
    fields.allergy_history.doctor_review_status = "missing_accepted"
    markdown, paragraphs, _ = _export(tmp_path, monkeypatch, fields)
    assert "未询问（医生确认）；本项信息未采集" in markdown
    assert "信息缺失（医生已接受本次缺失）；不代表否认或正常" in markdown
    assert "无药物过敏" not in markdown
    assert "信息缺失（医生已接受本次缺失）；不代表否认或正常" in paragraphs


def test_pending_conflict_and_literal_patient_markup_are_preserved(tmp_path, monkeypatch):
    literal = "# 原始标记\n## 患者自己的文字\n> 原文标记\n字符 & < > 保留"
    fields = MedicalRecordFields(chief_complaint=MedicalField(
        value=literal, status="conflicting", hint="原文不一致",
    ))
    markdown, paragraphs, _ = _export(tmp_path, monkeypatch, fields, approved=False)
    assert "证据冲突，需医生复核：原文不一致" in markdown
    assert "审核状态：未完成医生分项审核" in paragraphs
    assert literal in "\n".join(paragraphs)


def test_export_does_not_modify_review_state(tmp_path, monkeypatch):
    fields = MedicalRecordFields(chief_complaint=MedicalField(
        value="发热", status="partial", missing_elements=["起病时间"],
        confirmed_by_doctor=True, doctor_review_status="content_confirmed",
    ))
    before = fields.model_dump()
    _export(tmp_path, monkeypatch, fields)
    assert fields.model_dump() == before


def test_removed_ai_candidates_are_not_clinical_exclusions_in_any_export(tmp_path, monkeypatch):
    fields = MedicalRecordFields.model_validate({"candidate_diagnoses": [{
        "name": "发热待查", "deleted_by_doctor": True,
        "doctor_review_status": "ai_candidate_deleted",
    }]})
    before = fields.model_dump()
    markdown, paragraphs, _ = _export(tmp_path, monkeypatch, fields)
    expected = "无保留的候选诊断；AI候选已移除（不代表临床排除）；审核记录保留"
    assert expected in markdown
    assert expected in paragraphs
    assert "已由医生排除" not in markdown
    assert fields.model_dump() == before
