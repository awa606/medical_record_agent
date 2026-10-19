from pathlib import Path
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from app.schemas import MedicalField, MedicalRecordFields, SafetyCheckResult
from app.services.exporter import WORD_NOTICE, export_record


NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _export(tmp_path, monkeypatch, fields, *, approved=True):
    monkeypatch.setenv("MEDICAL_RECORD_AGENT_OUTPUT_DIR", str(tmp_path))
    paths = export_record(19019, {
        "fields": fields.model_dump(),
        "safety_check": SafetyCheckResult(passed=True).model_dump(),
        "approved": approved,
    })
    markdown = Path(paths["markdown_path"]).read_text(encoding="utf-8")
    with ZipFile(paths["word_path"]) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    paragraphs = ["".join(p.itertext()) for p in root.findall("w:body/w:p", NS)]
    return markdown, root, paragraphs


def test_docx_renders_native_headings_and_one_notice(tmp_path, monkeypatch):
    fields = MedicalRecordFields(chief_complaint=MedicalField(value="发热伴咳嗽2天"))
    markdown, root, paragraphs = _export(tmp_path, monkeypatch, fields)

    assert markdown.startswith("# 门诊病历")
    assert paragraphs[0] == "门诊病历"
    assert not any(text.startswith(("# ", "## ", "> ")) for text in paragraphs)
    assert sum(text.count(WORD_NOTICE) for text in paragraphs) == 1
    assert "草稿" not in "\n".join(paragraphs)
    assert "审核状态：已完成医生分项审核" in paragraphs
    title = root.find("w:body/w:p", NS)
    assert title.find("w:pPr/w:jc", NS).get(f"{{{NS['w']}}}val") == "center"
    heading = next(p for p in root.findall("w:body/w:p", NS) if "".join(p.itertext()) == "主诉")
    assert heading.find("w:r/w:rPr/w:b", NS) is not None


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
    markdown, _, paragraphs = _export(tmp_path, monkeypatch, fields)
    assert "未询问（医生确认）；本项信息未采集" in markdown
    assert "信息缺失（医生已接受本次缺失）；不代表否认或正常" in markdown
    assert "无药物过敏" not in markdown
    assert "信息缺失（医生已接受本次缺失）；不代表否认或正常" in paragraphs


def test_pending_conflict_and_literal_patient_markup_are_preserved(tmp_path, monkeypatch):
    literal = "# 原始标记\n## 患者自己的文字\n> 原文标记\n字符 & < > 保留"
    fields = MedicalRecordFields(chief_complaint=MedicalField(
        value=literal, status="conflicting", hint="原文不一致",
    ))
    markdown, _, paragraphs = _export(tmp_path, monkeypatch, fields, approved=False)
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
    markdown, _, paragraphs = _export(tmp_path, monkeypatch, fields)
    expected = "无保留的候选诊断；AI候选已移除（不代表临床排除）；审核记录保留"
    assert expected in markdown
    assert expected in paragraphs
    assert "已由医生排除" not in markdown
    assert fields.model_dump() == before
