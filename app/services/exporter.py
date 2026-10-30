from __future__ import annotations

import os
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services.privacy import anonymize_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"
WORD_NOTICE = "AI 辅助生成，病历内容以医生审核确认为准"
PDF_FONT_PATH = PROJECT_ROOT / "assets" / "fonts" / "NotoSansSC-Regular.ttf"
PDF_FONT_NAME = "NotoSansSC"
PDF_FALLBACK_FONT = "STSong-Light"


def _register_pdf_font() -> str:
    """Embed an OFL CJK font so PDF text stays searchable and copyable."""
    if PDF_FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return PDF_FONT_NAME
    if PDF_FONT_PATH.is_file():
        pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, str(PDF_FONT_PATH)))
        return PDF_FONT_NAME
    if PDF_FALLBACK_FONT in pdfmetrics.getRegisteredFontNames():
        return PDF_FALLBACK_FONT
    pdfmetrics.registerFont(UnicodeCIDFont(PDF_FALLBACK_FONT))
    return PDF_FALLBACK_FONT


FIELD_LABELS = [
    ("chief_complaint", "主诉"),
    ("present_illness", "现病史"),
    ("previous_treatment", "既往处理"),
    ("accompanying_symptoms", "伴随症状"),
    ("past_history", "既往史"),
    ("allergy_history", "过敏史"),
    ("physical_exam", "查体"),
]


def _record_paragraphs(
    fields: MedicalRecordFields, safety_check: SafetyCheckResult, *, approved: bool = False
) -> list[tuple[str, str]]:
    paragraphs = [
        ("title", "门诊病历"),
        ("note", WORD_NOTICE),
        ("note", "审核状态：已完成医生分项审核" if approved else "审核状态：未完成医生分项审核"),
    ]
    for field_name, label in FIELD_LABELS:
        field = getattr(fields, field_name)
        has_content = bool(not field.missing and field.value)
        reviewed = bool(field.confirmed_by_doctor and field.doctor_review_status == "content_confirmed")
        value = field.value if has_content else "未提及/待补充"
        if not has_content:
            if field.confirmed_by_doctor and field.doctor_review_status == "not_asked_confirmed":
                value = "未询问（医生确认）；本项信息未采集"
            elif field.confirmed_by_doctor and field.doctor_review_status == "missing_accepted":
                value = "信息缺失（医生已接受本次缺失）；不代表否认或正常"
            elif field_name == "physical_exam":
                value = "待医生查体补充"
        paragraphs.extend([("heading", label), ("body", str(value))])
        if field.status == "partial" and has_content:
            # Confirmation acknowledges the saved content, not facts that were
            # never collected. Keep concrete gaps, but retire generic UI tasks.
            missing = [item for item in field.missing_elements if item.strip()]
            if reviewed:
                missing = [item for item in missing if item not in {"待医生补充", "待补充信息"}]
                note = "内容已核对" + (f"；记录仍缺：{'、'.join(missing)}" if missing else "")
            else:
                note = f"部分完成，仍需补充：{'、'.join(missing or ['待补充信息'])}"
            paragraphs.append(("note", note))
        elif reviewed and has_content:
            paragraphs.append(("note", "内容已核对"))
        if field.status == "conflicting":
            paragraphs.append(("note", f"证据冲突，需医生复核：{field.hint or '请核对原始转写'}"))

    paragraphs.append(("heading", "候选诊断"))
    retained_diagnoses = [
        diagnosis for diagnosis in fields.candidate_diagnoses
        if not diagnosis.deleted_by_doctor and diagnosis.doctor_review_status != "ai_candidate_deleted"
    ]
    if retained_diagnoses:
        for diagnosis in retained_diagnoses:
            confirmed = diagnosis.confirmed_by_doctor and diagnosis.doctor_review_status == "candidate_confirmed"
            review = "医生已确认候选" if confirmed else "候选/待医生确认"
            paragraphs.append(("list", f"{diagnosis.name}（{review}）"))
    elif fields.candidate_diagnoses:
        paragraphs.append(("body", "无保留的候选诊断；AI候选已移除（不代表临床排除）；审核记录保留"))
    else:
        paragraphs.append(("body", "未记录候选诊断" if approved else "未提及/待医生确认"))
    paragraphs.extend([
        ("heading", "自动安全校验"),
        ("body", f"校验通过：{'是' if safety_check.passed else '否'}；导出阻断：{'是' if safety_check.blocked else '否'}"),
    ])
    return [(kind, anonymize_text(text)) for kind, text in paragraphs]


def _paragraphs_markdown(paragraphs: list[tuple[str, str]]) -> str:
    prefixes = {"title": "# ", "heading": "## ", "note": "> ", "list": "- "}
    return "\n\n".join(prefixes.get(kind, "") + text for kind, text in paragraphs) + "\n"
def render_markdown(
    fields: MedicalRecordFields, safety_check: SafetyCheckResult, *, approved: bool = False
) -> str:
    return _paragraphs_markdown(_record_paragraphs(fields, safety_check, approved=approved))


def _document_xml(markdown_text: str, paragraphs: list[tuple[str, str]] | None = None) -> str:
    if paragraphs is None:
        # Formal exports carry typed blocks so literal patient text is not parsed.
        paragraphs = []
        for line in markdown_text.splitlines():
            kind = "body"
            for prefix, candidate in (("## ", "heading"), ("# ", "title"), ("> ", "note"), ("- ", "list")):
                if line.startswith(prefix):
                    kind, line = candidate, line[len(prefix):]
                    break
            paragraphs.append((kind, line))
    rendered = []
    for kind, text in paragraphs:
        size = {"title": 36, "heading": 28, "note": 20}.get(kind, 24)
        font = "黑体" if kind in {"title", "heading"} else "宋体"
        bold = "<w:b/>" if kind in {"title", "heading"} else ""
        align = '<w:jc w:val="center"/>' if kind == "title" else ""
        keep = "<w:keepNext/>" if kind in {"title", "heading"} else ""
        style = f'<w:rPr><w:rFonts w:ascii="Calibri" w:hAnsi="Calibri" w:eastAsia="{font}"/>{bold}<w:sz w:val="{size}"/><w:szCs w:val="{size}"/></w:rPr>'
        for line in text.split("\n"):
            rendered.append(
                f'<w:p><w:pPr>{align}{keep}<w:spacing w:before="80" w:after="80" w:line="300" w:lineRule="auto"/></w:pPr>'
                f'<w:r>{style}<w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>'
            )
    body = "\n".join(rendered)
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""


def write_docx(path: Path, markdown_text: str, *, paragraphs: list[tuple[str, str]] | None = None) -> None:
    with ZipFile(path, "w", ZIP_DEFLATED) as docx:
        docx.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>
""",
        )
        docx.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>
""",
        )
        docx.writestr("word/document.xml", _document_xml(markdown_text, paragraphs))


def _pdf_styles() -> dict[str, ParagraphStyle]:
    font_name = _register_pdf_font()
    base = ParagraphStyle(
        "body",
        fontName=font_name,
        fontSize=10.5,
        leading=18,
        textColor=colors.HexColor("#1f2937"),
    )
    return {
        "title": ParagraphStyle(
            "title",
            parent=base,
            fontSize=19,
            leading=26,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#111827"),
        ),
        "subtitle": ParagraphStyle(
            "subtitle",
            parent=base,
            fontSize=9,
            leading=14,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#52627a"),
        ),
        "heading": ParagraphStyle(
            "heading",
            parent=base,
            fontSize=12,
            leading=20,
            textColor=colors.HexColor("#0f3d75"),
        ),
        "body": base,
        "note": ParagraphStyle(
            "note",
            parent=base,
            fontSize=9,
            leading=14,
            textColor=colors.HexColor("#52627a"),
        ),
        "signature": ParagraphStyle(
            "signature",
            parent=base,
            fontSize=10.5,
            leading=22,
            textColor=colors.HexColor("#1f2937"),
        ),
    }


def _pdf_text(value: str) -> str:
    return escape(str(value)).replace("\n", "<br/>")


def _pdf_meta_rows(
    fields: MedicalRecordFields,
    *,
    task_id: int,
    encounter_id: int | None,
    approved: bool,
    generated_at: datetime,
    department: str | None = None,
    encounter_created_at: str | None = None,
    patient_deidentified_id: str | None = None,
    patient_display_name: str | None = None,
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    patient_label = patient_display_name or patient_deidentified_id or "未关联患者"
    rows.append(("姓名", patient_label))
    rows.append(("性别/年龄", "________ / ________"))
    allergy = fields.allergy_history
    allergy_text = str(allergy.value).strip() if allergy.value and not allergy.missing else "未提及/待补充"
    rows.append(("药物过敏史", allergy_text))
    rows.append(("科别", department or "未关联科室"))
    rows.append(("门诊病历号", f"E-{encounter_id}" if encounter_id is not None else "未关联就诊"))
    if encounter_created_at:
        rows.append(("就诊时间", str(encounter_created_at)[:16].replace("T", " ")))
    rows.extend(
        [
            ("任务编号", str(task_id)),
            ("导出时间", generated_at.strftime("%Y-%m-%d %H:%M")),
            ("审核状态", "已完成医生分项审核" if approved else "未完成医生分项审核"),
        ]
    )
    return rows


def _pdf_sections(fields: MedicalRecordFields) -> list[tuple[str, str, str | None]]:
    def value_of(name: str) -> str:
        field = getattr(fields, name)
        return str(field.value).strip() if field.value and not field.missing else ""

    def missing_note(name: str) -> str | None:
        field = getattr(fields, name)
        if field.value and not field.missing:
            if field.status == "conflicting":
                return f"证据冲突，需医生复核：{field.hint or '请核对原始转写'}"
            return None
        if field.confirmed_by_doctor and field.doctor_review_status == "not_asked_confirmed":
            return "未询问（医生确认）；本项信息未采集"
        if field.confirmed_by_doctor and field.doctor_review_status == "missing_accepted":
            return "信息缺失（医生已接受本次缺失）；不代表否认或正常"
        return "未提及/待补充"

    chief = value_of("chief_complaint")
    present = value_of("present_illness")
    accompanying = value_of("accompanying_symptoms")
    past = value_of("past_history")
    previous = value_of("previous_treatment")
    exam = value_of("physical_exam")

    present_text = present or "未提及/待补充"
    if accompanying:
        present_text = f"{present_text}\n伴随症状：{accompanying}"
    past_text = past or "未提及/待补充"
    if previous:
        past_text = f"{past_text}\n既往处理：{previous}"

    retained = [
        diagnosis
        for diagnosis in fields.candidate_diagnoses
        if not diagnosis.deleted_by_doctor and diagnosis.doctor_review_status != "ai_candidate_deleted"
    ]
    if retained:
        diagnosis_text = "\n".join(
            f"{index + 1}. {diagnosis.name}（"
            + ("医生已确认候选" if diagnosis.doctor_review_status == "candidate_confirmed" else "候选/待医生确认")
            + "）"
            for index, diagnosis in enumerate(retained)
        )
    elif fields.candidate_diagnoses:
        diagnosis_text = "无保留的候选诊断；AI 候选已移除（不代表临床排除）；审核记录保留"
    else:
        diagnosis_text = "未记录候选诊断"

    return [
        ("主诉", chief or "未提及/待补充", None if chief else missing_note("chief_complaint")),
        ("现病史", present_text, None),
        ("既往史", past_text, None),
        ("体格及专科检查", exam or "待医生查体补充", None if exam else missing_note("physical_exam")),
        ("辅助检查", "本次未提供；如有检验检查结果，请在病历系统中补录。", None),
        ("诊断", diagnosis_text, "AI 候选诊断必须由医生确认，不构成诊断结论。"),
        ("治疗意见", "待医生补充。", "本系统不生成处方或治疗建议。"),
    ]


def render_pdf(
    path: Path,
    fields: MedicalRecordFields,
    safety_check: SafetyCheckResult,
    *,
    approved: bool,
    task_id: int,
    encounter_id: int | None = None,
    generated_at: datetime | None = None,
    department: str | None = None,
    encounter_created_at: str | None = None,
    patient_deidentified_id: str | None = None,
    patient_display_name: str | None = None,
) -> Path:
    """Hospital-style outpatient record: meta header, sections, signature block."""
    styles = _pdf_styles()
    generated_at = generated_at or datetime.now()
    doc = SimpleDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=f"门诊病历 E-{encounter_id}" if encounter_id is not None else "门诊病历",
        author="MediListen",
    )
    story: list[Any] = [
        Paragraph(
            f"医疗机构名称：{os.environ.get('MRA_HOSPITAL_NAME', '').strip() or '____________________'}",
            styles["subtitle"],
        ),
        Paragraph("初 诊 病 历 记 录", styles["title"]),
        Paragraph("AI 辅助生成 · 医生审核确认后方可作为病历使用", styles["subtitle"]),
        Spacer(1, 4 * mm),
    ]

    meta_rows = _pdf_meta_rows(
        fields,
        task_id=task_id,
        encounter_id=encounter_id,
        approved=approved,
        generated_at=generated_at,
        department=department,
        encounter_created_at=encounter_created_at,
        patient_deidentified_id=patient_deidentified_id,
        patient_display_name=patient_display_name,
    )
    meta_table = Table(
        [[Paragraph(f"<b>{_pdf_text(k)}</b>", styles["note"]), Paragraph(_pdf_text(v), styles["note"])] for k, v in meta_rows],
        colWidths=[30 * mm, 140 * mm],
    )
    meta_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#dfe6ef")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f3f6fa")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    story.extend([meta_table, Spacer(1, 5 * mm), HRFlowable(width="100%", color=colors.HexColor("#c9d4e3"))])

    for heading, body, note in _pdf_sections(fields):
        block: list[Any] = [
            Paragraph(_pdf_text(heading), styles["heading"]),
            Paragraph(_pdf_text(body), styles["body"]),
        ]
        if note:
            block.append(Paragraph(_pdf_text(note), styles["note"]))
        block.append(Spacer(1, 3 * mm))
        story.append(KeepTogether(block))

    story.append(KeepTogether([
        Spacer(1, 4 * mm),
        HRFlowable(width="100%", color=colors.HexColor("#c9d4e3")),
        Spacer(1, 2 * mm),
        Paragraph(
            _pdf_text(
                f"自动安全校验：{'通过' if safety_check.passed else '未通过'}；"
                f"导出阻断：{'是' if safety_check.blocked else '否'}"
            ),
            styles["note"],
        ),
        Spacer(1, 8 * mm),
        Paragraph("医师签名：__________________　　日期：______年____月____日", styles["signature"]),
        Spacer(1, 3 * mm),
        Paragraph(WORD_NOTICE, styles["note"]),
    ]))

    def _footer(canvas, doc_obj) -> None:
        canvas.saveState()
        canvas.setFont(styles["body"].fontName, 8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"第 {doc_obj.page} 页")
        canvas.drawString(20 * mm, 10 * mm, "MediListen · 门诊病历")
        canvas.restoreState()

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return path


def export_record(task_id: int, result: dict[str, Any]) -> dict[str, str]:
    fields = MedicalRecordFields.model_validate(result["fields"])
    safety_check = SafetyCheckResult.model_validate(result["safety_check"])
    # The API verifies the live approval and Revision before entering here.
    # Never infer approval from nonempty or individually confirmed fields.
    approved = result.get("approved") is True
    encounter_id = result.get("encounter_id")
    output_dir = Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = output_dir / f"task_{task_id}_medical_record.pdf"
    render_pdf(
        pdf_path,
        fields,
        safety_check,
        approved=approved,
        task_id=task_id,
        encounter_id=int(encounter_id) if encounter_id is not None else None,
        department=result.get("encounter_department"),
        encounter_created_at=result.get("encounter_created_at"),
        patient_deidentified_id=result.get("patient_deidentified_id"),
        patient_display_name=result.get("patient_display_name"),
    )
    return {"pdf_path": str(pdf_path)}

