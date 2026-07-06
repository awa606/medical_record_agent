from __future__ import annotations

import os
from html import escape
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from app.schemas import MedicalRecordFields, SafetyCheckResult


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"
WORD_NOTICE = "AI 辅助草稿，以医生确认版本为准"


FIELD_LABELS = [
    ("chief_complaint", "主诉"),
    ("present_illness", "现病史"),
    ("previous_treatment", "既往处理"),
    ("accompanying_symptoms", "伴随症状"),
    ("past_history", "既往史"),
    ("allergy_history", "过敏史"),
    ("physical_exam", "查体"),
]


def render_markdown(fields: MedicalRecordFields, safety_check: SafetyCheckResult) -> str:
    lines = [
        "# 门诊病历",
        "",
        f"> {WORD_NOTICE}",
        "",
    ]

    for field_name, label in FIELD_LABELS:
        field = getattr(fields, field_name)
        value = field.value if not field.missing and field.value else "未提及/待补充"
        if field_name == "physical_exam" and field.missing:
            value = "待医生查体补充"
        lines.extend([f"## {label}", value, ""])

    lines.append("## 候选诊断")
    if fields.candidate_diagnoses:
        for diagnosis in fields.candidate_diagnoses:
            lines.append(f"- {diagnosis.name}（{diagnosis.status}，医生已确认）")
    else:
        lines.append("未提及/待医生确认")

    lines.extend(
        [
            "",
            "## 安全校验",
            f"- 通过：{safety_check.passed}",
            f"- 阻断：{safety_check.blocked}",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _document_xml(markdown_text: str) -> str:
    paragraphs = [WORD_NOTICE, *markdown_text.splitlines()]
    body = "\n".join(
        f"<w:p><w:r><w:t>{escape(paragraph)}</w:t></w:r></w:p>"
        for paragraph in paragraphs
    )
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    {body}
    <w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440"/></w:sectPr>
  </w:body>
</w:document>
"""


def write_docx(path: Path, markdown_text: str) -> None:
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
        docx.writestr("word/document.xml", _document_xml(markdown_text))


def export_record(task_id: int, result: dict[str, Any]) -> dict[str, str]:
    fields = MedicalRecordFields.model_validate(result["fields"])
    safety_check = SafetyCheckResult.model_validate(result["safety_check"])
    markdown_text = render_markdown(fields, safety_check)

    output_dir = Path(os.environ.get("MEDICAL_RECORD_AGENT_OUTPUT_DIR", DEFAULT_OUTPUT_DIR))
    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / f"task_{task_id}_medical_record.md"
    word_path = output_dir / f"task_{task_id}_medical_record.docx"

    markdown_path.write_text(markdown_text, encoding="utf-8")
    write_docx(word_path, markdown_text)

    return {
        "markdown_path": str(markdown_path),
        "word_path": str(word_path),
    }
