from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas import MedicalRecordFields, SafetyCheckResult
from app.services.privacy import anonymize_text


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"
WORD_NOTICE = "AI 辅助生成，病历内容以医生审核确认为准"


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
        paragraphs.append(("body", "无保留的候选诊断（AI候选已由医生排除；审核记录保留）"))
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


def export_record(task_id: int, result: dict[str, Any]) -> dict[str, str]:
    fields = MedicalRecordFields.model_validate(result["fields"])
    safety_check = SafetyCheckResult.model_validate(result["safety_check"])
    # The API verifies the live approval and Revision before entering here.
    # Never infer approval from nonempty or individually confirmed fields.
    paragraphs = _record_paragraphs(fields, safety_check, approved=result.get("approved") is True)
    markdown_text = _paragraphs_markdown(paragraphs)

    output_dir = Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"task_{task_id}_medical_record.md"
    word_path = output_dir / f"task_{task_id}_medical_record.docx"

    markdown_path.write_text(markdown_text, encoding="utf-8")
    write_docx(word_path, markdown_text, paragraphs=paragraphs)

    return {
        "markdown_path": str(markdown_path),
        "word_path": str(word_path),
    }
