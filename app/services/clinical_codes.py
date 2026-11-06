"""Small deterministic clinical-code checks used before export.

This is deliberately a format/dictionary aid, not a full ICD-10 catalog.
"""
from __future__ import annotations

import re

from app.schemas import MedicalRecordFields

ICD10_PATTERN = re.compile(r"^[A-Z][0-9]{2}(?:\.[0-9A-Z]{1,4})?$")

# A conservative starter set for the synthetic demo; unknown valid codes are
# accepted because hospitals may use a licensed, fuller catalog.
COMMON_ICD10 = {
    "R50.9": "发热待查",
    "J06.9": "上呼吸道感染",
    "J18.9": "肺部感染",
    "J45.9": "哮喘",
    "I10": "高血压",
    "E11.9": "2型糖尿病",
    "K29.7": "胃炎",
    "N39.0": "尿路感染",
}


def normalize_icd10(code: str | None) -> str | None:
    value = str(code or "").strip().upper()
    return value or None


def icd10_errors(fields: MedicalRecordFields) -> list[str]:
    errors: list[str] = []
    for index, diagnosis in enumerate(fields.candidate_diagnoses, start=1):
        code = normalize_icd10(diagnosis.icd10_code)
        if not code:
            continue
        if not ICD10_PATTERN.fullmatch(code):
            errors.append(f"候选诊断 {index} 的 ICD-10 编码格式无效：{code}（示例：J06.9）。")
    return errors


def icd10_warnings(fields: MedicalRecordFields) -> list[str]:
    warnings: list[str] = []
    for index, diagnosis in enumerate(fields.candidate_diagnoses, start=1):
        code = normalize_icd10(diagnosis.icd10_code)
        if not code or code not in COMMON_ICD10:
            continue
        expected = COMMON_ICD10[code]
        if expected not in diagnosis.name and diagnosis.name not in expected:
            warnings.append(
                f"候选诊断 {index} 的 ICD-10 {code} 通常对应“{expected}”，请核对名称与编码。"
            )
    return warnings
