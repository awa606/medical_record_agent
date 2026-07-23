from __future__ import annotations

from typing import Any

from app.services.fever_respiratory_pack import (
    PACK_VERSION as FEVER_RESPIRATORY_PACK_VERSION,
    REFERENCE_CATALOG,
    SOURCE_CATALOG_VERSION,
)
from app.services.knowledge_rules import RULES as COMMON_COLD_RULES


KNOWLEDGE_BASE_VERSION = "clinical_knowledge_base_v1"


def _reference_payloads() -> list[dict[str, Any]]:
    return [
        reference.model_dump(mode="json")
        for reference in sorted(
            REFERENCE_CATALOG.values(),
            key=lambda item: item.reference_id,
        )
    ]


def _common_cold_rule_payloads() -> list[dict[str, Any]]:
    return [
        {
            "rule_id": rule.rule_id,
            "name": rule.name,
            "source_type": "course_mock",
            "clinical_review_status": "needs_medical_review",
            "clinical_use_limit": "课程模拟规则，仅用于演示候选诊断参考，不作为真实临床诊断依据。",
        }
        for rule in COMMON_COLD_RULES
    ]


def build_clinical_knowledge_base() -> dict[str, Any]:
    references = _reference_payloads()
    common_cold_rules = _common_cold_rule_payloads()
    return {
        "version": KNOWLEDGE_BASE_VERSION,
        "status": "review_limited",
        "description": "本地只读临床知识目录，供候选诊断参考、来源追溯和后台核验展示使用。",
        "packs": [
            {
                "pack_id": FEVER_RESPIRATORY_PACK_VERSION,
                "name": "发热/呼吸系统疾病包 v1",
                "scope": "发热、头痛、咳嗽、胸闷、胸痛、气促和呼吸困难相关的鉴别诊断参考。",
                "status": "active",
                "source_catalog_version": SOURCE_CATALOG_VERSION,
                "reference_count": len(references),
                "rule_count": 3,
                "clinical_review_status": "needs_medical_review",
                "evidence_policy": "候选诊断必须绑定原文事实和已核验来源；输出为鉴别诊断参考，不表达确诊或疾病概率。",
            },
            {
                "pack_id": "common_cold_course_mock_v1",
                "name": "感冒中医证候课程模拟规则",
                "scope": "课程演示用感冒证候规则，保留为 mock/demo 候选参考。",
                "status": "demo_only",
                "source_catalog_version": "course_mock_rules_v1",
                "reference_count": 0,
                "rule_count": len(common_cold_rules),
                "clinical_review_status": "needs_medical_review",
                "evidence_policy": "仅用于课程模拟，不作为真实临床诊断依据；Live/Edge 正式模式不应作为默认临床知识来源。",
            },
        ],
        "references": references,
        "rule_sets": common_cold_rules,
        "limits": [
            "当前知识库仅覆盖有限的发热/呼吸场景和课程模拟感冒规则。",
            "候选诊断必须经医生审核，不得作为确诊结论或处方依据。",
            "未配置真实 Provider 或处于 demo/mock 模式时，结果不得自动进入可导出状态。",
        ],
    }


def list_clinical_references() -> dict[str, Any]:
    return {
        "catalog_version": SOURCE_CATALOG_VERSION,
        "references": _reference_payloads(),
    }


__all__ = [
    "KNOWLEDGE_BASE_VERSION",
    "build_clinical_knowledge_base",
    "list_clinical_references",
]
