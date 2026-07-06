from __future__ import annotations

import copy
import json
import re
from pathlib import Path
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_MANIFEST_PATH = PROJECT_ROOT / "data" / "asr_eval" / "manifest.json"

DOCTOR_PATTERNS = [
    "你好",
    "哪里不舒服",
    "哪里不好",
    "哪里被咬",
    "现在什么感受",
    "大概被咬了多久",
    "做没做过什么处理",
    "有没有",
    "你是直接来",
    "现在除了",
    "还有什么",
    "被咬伤之后",
    "大小便怎么样",
    "好的",
]
PATIENT_PATTERNS = [
    "我是",
    "感觉",
    "大概咬了",
    "用酒精",
    "我这",
    "吃的",
    "直接来",
    "我现在",
    "严重的时候",
    "我感觉",
    "这块都没有",
]


def load_asr_manifest(manifest_path: Path = DEFAULT_MANIFEST_PATH) -> dict[str, dict[str, Any]]:
    if not manifest_path.exists():
        return {}
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    samples = data.get("samples", data if isinstance(data, list) else [])
    return {
        str(sample["sample_id"]): sample
        for sample in samples
        if isinstance(sample, dict) and sample.get("sample_id")
    }


def find_sample_config(sample_id: str, manifest: dict[str, dict[str, Any]] | None = None) -> dict[str, Any] | None:
    samples = manifest if manifest is not None else load_asr_manifest()
    return samples.get(sample_id)


def apply_manifest_role_strategy(
    result: ASRResult,
    sample_id: str,
    manifest: dict[str, dict[str, Any]] | None = None,
) -> ASRResult:
    sample = find_sample_config(sample_id, manifest)
    if sample is None:
        return result

    updated = result.model_copy(deep=True)
    strategy = sample.get("role_strategy")
    if strategy == "single_speaker_script_split":
        updated.segments = split_single_speaker_script(updated.text)
        updated.conversation_text = conversation_from_segments(updated.segments)
    elif strategy == "manual_speaker_role_map":
        speaker_role_map = sample.get("speaker_role_map") or {}
        if sample.get("speaker_mode") == "two_speaker_consultation" and not _has_reliable_speaker_turns(updated.segments):
            updated.role_strategy = "single_segment_needs_review"
            updated.conversation_text = f"[待校正] {updated.text}"
            if updated.engine == "qwen3-asr-0.6b":
                warning = "Qwen3-ASR did not provide reliable speaker roles; please manually review roles."
            else:
                warning = (
                    "FunASR returned a single long segment; speaker role mapping was not applied. "
                    "Please manually review roles."
                )
            if warning not in updated.warnings:
                updated.warnings.append(warning)
        else:
            updated.segments = apply_speaker_role_map(updated.segments, speaker_role_map)
            updated.conversation_text = conversation_from_segments(updated.segments)

    expected_keywords = sample.get("expected_keywords") or []
    if expected_keywords:
        keyword_result = ASREvaluator().keyword_metrics(expected_keywords, updated.text)
        updated.medical_keywords = {
            "expected": keyword_result["expected"],
            "recognized": keyword_result["recognized"],
            "missing": keyword_result["missing"],
        }

    updated.manifest_sample_id = sample_id
    updated.scenario = sample.get("scenario")
    updated.speaker_mode = sample.get("speaker_mode")
    updated.evaluate_diarization = bool(sample.get("evaluate_diarization", False))
    if not updated.role_strategy:
        updated.role_strategy = strategy
    return mark_role_review_state(updated)


def mark_role_review_state(result: ASRResult) -> ASRResult:
    updated = result.model_copy(deep=True)
    needs_review = updated.role_strategy == "single_segment_needs_review"
    if not updated.segments and updated.text:
        needs_review = True
    for segment in updated.segments:
        if not segment.role:
            needs_review = True
        if updated.role_strategy == "single_segment_needs_review":
            segment.needs_review = True
        elif not segment.role:
            segment.needs_review = True
    updated.needs_review = needs_review
    return updated


def split_single_speaker_script(text: str) -> list[ASRSegment]:
    clauses = _split_clauses(text)
    segments: list[ASRSegment] = []
    for clause in clauses:
        role = _classify_clause_role(clause)
        if segments and segments[-1].role == role:
            segments[-1].text = f"{segments[-1].text}{clause}"
            continue
        segments.append(
            ASRSegment(
                speaker="script",
                role=role,
                text=clause,
                start_time=None,
                end_time=None,
                confidence=None,
            )
        )
    return segments


def apply_speaker_role_map(
    segments: list[ASRSegment],
    speaker_role_map: dict[str, str],
) -> list[ASRSegment]:
    mapped_segments = copy.deepcopy(segments)
    for segment in mapped_segments:
        role = _lookup_speaker_role(segment.speaker, speaker_role_map)
        if role:
            segment.role = role
    return mapped_segments


def _has_reliable_speaker_turns(segments: list[ASRSegment]) -> bool:
    if len(segments) <= 1:
        return False
    speakers = [segment.speaker for segment in segments if segment.speaker]
    if len(set(speakers)) < 2:
        return False
    return True


def conversation_from_segments(segments: list[ASRSegment]) -> str:
    lines = []
    for segment in segments:
        label = segment.role or segment.speaker or "spk0"
        lines.append(f"[{label}] {segment.text}")
    return "\n".join(lines)


def _split_clauses(text: str) -> list[str]:
    compact_text = re.sub(r"\s+", "", text or "")
    return [
        match.group(0)
        for match in re.finditer(r"[^，。！？?,.!?]+[，。！？?,.!?]?", compact_text)
        if match.group(0).strip()
    ]


def _classify_clause_role(clause: str) -> str:
    if any(pattern in clause for pattern in PATIENT_PATTERNS):
        return "患者"
    if any(pattern in clause for pattern in DOCTOR_PATTERNS) or "？" in clause or "?" in clause:
        return "医生"
    return "患者"


def _lookup_speaker_role(speaker: str | None, speaker_role_map: dict[str, str]) -> str | None:
    if not speaker:
        return None
    candidates = [speaker]
    match = re.search(r"(\d+)", speaker)
    if match:
        number = int(match.group(1))
        candidates.extend(
            [
                f"spk{number}",
                f"speaker{number}",
                f"发言人{number}",
                f"说话人{number}",
            ]
        )
        if number == 0:
            candidates.extend(["发言人1", "说话人1", "speaker1"])
        elif number == 1:
            candidates.extend(["发言人2", "说话人2", "speaker2"])
    for candidate in candidates:
        if candidate in speaker_role_map:
            return speaker_role_map[candidate]
    return None
