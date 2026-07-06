"""人工标注样本抽样与指南生成。"""

from __future__ import annotations

import random
from pathlib import Path

from app.dataset_pipeline.jsonl import read_jsonl, write_jsonl
from app.dataset_pipeline.paths import ANNOTATION_DIR, PROCESSED_DIR, ensure_pipeline_dirs


ANNOTATION_GUIDE = """# Toyhom 感冒相关样本人工标注指南

## 数据用途

本标注集仅用于课程项目中的病历字段抽取评测和问诊表达分析，不用于真实诊疗、
自动诊断或自动处方。原始 Toyhom CSV 不提交到 GitHub。

## 标注原则

- 只根据 title 和 question 标注，不从 answer 中补充患者事实。
- 未提及字段标记为 missing=true，不要写“无”。
- 诊断类内容只可标记为“候选/待医生确认”。
- 遇到广告、联系方式、明显无关病例时，将 needs_manual_review 标为 true。

## 字段说明

- chief_complaint：患者这次就诊最主要问题，可来自标题或问题开头。
- present_illness：症状发生、发展、持续时间和主要不适。
- symptoms：明确出现的症状，如发热、咳嗽、鼻塞、流涕、咽痛。
- duration：持续时间，如 2 天、半个月、昨天开始。
- accompanying_symptoms：伴随症状，如乏力、头痛、怕冷、咳痰。
- negative_symptoms：明确否认的症状，如“不发烧”“没有咳嗽”。
- past_history：既往史，如哮喘、鼻炎、高血压、糖尿病。
- medication_history：本次或近期用药史。
- allergy_history：过敏史；未提及时保持 missing=true。
- items_to_complete：仍需补问或医生查体补充的项目。
- evidence_text：必须尽量填写支持字段的原文片段。
"""


def sample_annotation_set(
    input_path: Path = PROCESSED_DIR / "pseudo_emr_cases.jsonl",
    output_path: Path = ANNOTATION_DIR / "annotation_sample_100.jsonl",
    guide_path: Path = ANNOTATION_DIR / "annotation_guide.md",
    sample_size: int = 100,
    seed: int = 42,
) -> int:
    """从伪病历候选集中抽样，生成待人工标注样本和指南。"""

    ensure_pipeline_dirs()
    records = read_jsonl(input_path)
    rng = random.Random(seed)
    if len(records) > sample_size:
        records = rng.sample(records, sample_size)

    annotation_records = []
    for record in records:
        annotation_records.append(
            {
                "case_id": record.get("case_id"),
                "source": record.get("source"),
                "department": record.get("department"),
                "title": record.get("title"),
                "question": record.get("question"),
                "quality_flags": record.get("quality_flags", {}),
                "pseudo_fields": record.get("pseudo_fields", {}),
                "gold_fields": {},
                "annotation_status": "待标注",
                "annotator_note": "",
            }
        )

    guide_path.parent.mkdir(parents=True, exist_ok=True)
    guide_path.write_text(ANNOTATION_GUIDE, encoding="utf-8")
    return write_jsonl(output_path, annotation_records)
