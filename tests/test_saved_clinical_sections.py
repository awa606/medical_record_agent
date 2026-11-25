from app.schemas import MedicalField, MedicalRecordFields
from app.services.record_rules import check_draft_safety, render_draft
import pytest


def test_optional_clinical_sections_in_saved_narrative():
    fields = MedicalRecordFields(
        personal_history=MedicalField(value="个人事项甲"),
        marital_history=MedicalField(value="既往记录乙"),
        family_history=MedicalField(value="父亲的情况丙"),
        auxiliary_exam=MedicalField(value="本人右腕影像报告待回。"),
        treatment_notes=MedicalField(value="核对资料后复评。"),
        treatment_plan=MedicalField(value="系统建议示例"),
    )
    draft = render_draft(fields)
    expected = ("个人史：个人事项甲", "婚育史：既往记录乙", "家族史：父亲的情况丙",
                "辅助检查：本人右腕影像报告待回。", "医生处理意见：核对资料后复评。")
    assert all(line in draft.splitlines() for line in expected)
    assert "系统建议示例" not in draft
    assert "查体：待医生查体补充" in draft
    assert check_draft_safety(draft, fields).passed


def test_empty_legacy_fields_and_partial_or_conflicting_values():
    legacy = render_draft({})
    assert "辅助检查" not in legacy
    partial = MedicalRecordFields(auxiliary_exam=MedicalField(
        value="测量记录尚未收到", status="partial", missing_elements=["本人报告"]))
    assert "辅助检查：测量记录尚未收到（部分完成，仍需补充：本人报告）" in render_draft(partial)
    conflict = MedicalRecordFields(family_history=MedicalField(value="未采纳的内容", status="conflicting"))
    draft = render_draft(conflict)
    assert "家族史：待核对（模型内容未采纳）" in draft
    assert "未采纳的内容" not in draft
    assert check_draft_safety(draft, conflict).blocked


def test_negative_imaging_is_separate_from_physical_exam():
    fields = MedicalRecordFields(auxiliary_exam=MedicalField(value="本人的右腕影像报告无明显异常"))
    draft = render_draft(fields)
    assert check_draft_safety(draft, fields).passed
    for extra in ("查体：无明显异常", "无明显异常", "辅助检查：无明显异常",
                  "辅助检查：本人的右腕影像报告无明显异常"):
        assert check_draft_safety(draft + "\n" + extra, fields).blocked


@pytest.mark.parametrize("value", ["生命体征平稳", "查体无异常", "查体无明显异常",
                                   "右腕影像报告待回\n查体：无明显异常"])
def test_report_cannot_supply_missing_physical_exam(value):
    fields = MedicalRecordFields(auxiliary_exam=MedicalField(value=value))
    draft = render_draft(fields)
    assert "\n查体：无明显异常" not in draft
    assert check_draft_safety(draft, fields).blocked


def test_adding_sections_does_not_allow_confirmed_diagnosis_or_allergy_conflict():
    fields = MedicalRecordFields(
        allergy_history=MedicalField(value="青霉素过敏"),
        treatment_notes=MedicalField(value="使用阿莫西林"),
        auxiliary_exam=MedicalField(value="确诊为示例"),
    )
    result = check_draft_safety(render_draft(fields), fields)
    assert result.blocked
    assert any("过敏" in err for err in result.errors)
    assert any("最终诊断" in err for err in result.errors)



@pytest.mark.parametrize("report", ["本人本次右腕影像报告。\n报告所见无明显异常。",
                                     "体检中心既往胸片原文：无明显异常。"])
def test_report_layout_and_institution_do_not_create_physical_findings(report):
    fields = MedicalRecordFields(auxiliary_exam=MedicalField(value=report))
    draft = render_draft(fields)
    assert check_draft_safety(draft, fields).passed
    assert check_draft_safety(draft + "\n体检无明显异常", fields).blocked
