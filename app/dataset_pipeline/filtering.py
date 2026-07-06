"""感冒相关病例筛选与质量标记。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from app.dataset_pipeline.jsonl import read_jsonl, write_jsonl
from app.dataset_pipeline.paths import PROCESSED_DIR, ensure_pipeline_dirs


COLD_KEYWORDS = [
    "感冒",
    "发热",
    "发烧",
    "咳嗽",
    "鼻塞",
    "流涕",
    "流鼻涕",
    "咽痛",
    "嗓子疼",
    "喉咙痛",
    "上呼吸道感染",
    "上感",
    "怕冷",
    "恶寒",
]

CONTACT_PATTERNS = [
    re.compile(r"1[3-9]\d{9}"),
    re.compile(r"(微信|薇信|wx|QQ|电话|手机号|联系方式|加我)", re.IGNORECASE),
]

AD_PATTERNS = [
    re.compile(r"(点击|咨询热线|专家在线|官方网址|预约挂号|包治|根治)", re.IGNORECASE),
]


def matched_keywords(record: dict[str, Any]) -> list[str]:
    """返回命中的感冒相关关键词。"""

    text = " ".join(
        str(record.get(field) or "")
        for field in ("department", "title", "question", "answer")
    )
    return [keyword for keyword in COLD_KEYWORDS if keyword in text]


def build_quality_flags(record: dict[str, Any]) -> dict[str, bool]:
    """给候选样本增加质量标记，便于后续人工筛查。"""

    text = " ".join(str(record.get(field) or "") for field in ("title", "question", "answer"))
    title_question_len = len((record.get("title") or "") + (record.get("question") or ""))
    contains_contact_info = any(pattern.search(text) for pattern in CONTACT_PATTERNS)
    possible_ad = any(pattern.search(text) for pattern in AD_PATTERNS)
    too_short = title_question_len < 12
    return {
        "too_short": too_short,
        "possible_ad": possible_ad,
        "contains_contact_info": contains_contact_info,
        "needs_manual_review": too_short or possible_ad or contains_contact_info,
    }


def is_cold_candidate(record: dict[str, Any]) -> bool:
    """判断是否属于感冒/上呼吸道感染相关候选样本。"""

    return bool(matched_keywords(record))


def filter_toyhom_cold_cases(
    input_path: Path = PROCESSED_DIR / "toyhom_clean.jsonl",
    output_path: Path = PROCESSED_DIR / "toyhom_cold_candidates.jsonl",
) -> int:
    """从清洗数据中筛选感冒相关候选病例。"""

    ensure_pipeline_dirs()
    records = []
    for record in read_jsonl(input_path):
        keywords = matched_keywords(record)
        if not keywords:
            continue
        enriched = dict(record)
        enriched["matched_keywords"] = keywords
        enriched["quality_flags"] = build_quality_flags(record)
        records.append(enriched)
    return write_jsonl(output_path, records)
