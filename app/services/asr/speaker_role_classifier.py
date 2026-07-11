from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from urllib import error, request

from app.schemas.asr import ASRResult, SpeakerRoleAssignment
from app.services.asr.role_strategy import conversation_from_segments
from app.services.asr.speaker_profiles import apply_doctor_voice_profile


ALLOWED_MODEL_ROLES = {"患者", "其他"}


def resolve_speaker_roles(
    result: ASRResult,
    *,
    audio_path,
    doctor_profile_id: str | None = None,
) -> ASRResult:
    updated = apply_doctor_voice_profile(result, audio_path, doctor_profile_id)
    provider = os.environ.get("SPEAKER_ROLE_PROVIDER", "rules").strip().lower()
    unresolved = [
        item
        for item in updated.speaker_assignments
        if item.requires_confirmation and item.role != "医生"
    ]
    if provider != "ollama" or not unresolved:
        return updated
    try:
        predictions = _classify_with_ollama(updated, unresolved)
    except (RuntimeError, ValueError, error.URLError, TimeoutError) as exc:
        warning = f"Local speaker role model unavailable; use one global mapping confirmation. Reason: {exc}"
        if warning not in updated.warnings:
            updated.warnings.append(warning)
        return updated

    assignment_map = {item.speaker_id: item for item in updated.speaker_assignments}
    for speaker_id, prediction in predictions.items():
        existing = assignment_map.get(speaker_id)
        if existing is None or existing.role == "医生":
            continue
        assignment_map[speaker_id] = existing.model_copy(
            update={
                "role": prediction["role"],
                "confidence": prediction["confidence"],
                "source": "ollama_qwen3_speaker_context",
                "reason": prediction["reason"],
                "requires_confirmation": prediction["confidence"] < 0.72,
            }
        )
    updated.speaker_assignments = [assignment_map[item.speaker_id] for item in updated.speaker_assignments]
    for segment in updated.segments:
        assignment = assignment_map.get(segment.speaker_id or segment.speaker or "")
        if assignment is None:
            continue
        segment.role = assignment.role
        segment.role_confidence = assignment.confidence
        segment.role_source = assignment.source
        segment.role_note = assignment.reason
        segment.needs_review = assignment.requires_confirmation
    updated.needs_review = any(item.requires_confirmation for item in updated.speaker_assignments)
    updated.conversation_text = conversation_from_segments(updated.segments)
    updated.role_strategy = "doctor_profile_and_qwen3_global_speaker_role"
    return updated


def _classify_with_ollama(
    result: ASRResult,
    unresolved: list[SpeakerRoleAssignment],
) -> dict[str, dict[str, object]]:
    base_url = os.environ.get("SPEAKER_ROLE_OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("SPEAKER_ROLE_OLLAMA_MODEL", "qwen3:4b-instruct")
    timeout = float(os.environ.get("SPEAKER_ROLE_TIMEOUT_SECONDS", "30"))
    grouped: dict[str, list[str]] = defaultdict(list)
    unresolved_ids = {item.speaker_id for item in unresolved}
    for segment in result.segments:
        speaker_id = segment.speaker_id or segment.speaker or ""
        if speaker_id in unresolved_ids and segment.text.strip():
            grouped[speaker_id].append(segment.text.strip())
    speaker_blocks = "\n".join(
        f"{speaker_id}: {' '.join(lines)[:3500]}"
        for speaker_id, lines in grouped.items()
    )
    prompt = (
        "你只做整位说话人的角色归类，不做诊断。医生已经由声纹或规则单独锁定。"
        "请把下面每位剩余说话人归为患者或其他（家属、护士、陪诊人员等）。"
        "只输出 JSON：{\"assignments\":[{\"speaker_id\":\"...\",\"role\":\"患者|其他\","
        "\"confidence\":0到1,\"reason\":\"简短依据\"}]}。\n"
        f"{speaker_blocks}"
    )
    payload = {
        "model": model,
        "stream": False,
        "think": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": "你是本地说话人角色分类器，只返回结构化 JSON。"},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0},
    }
    req = request.Request(
        f"{base_url}/api/chat",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with request.urlopen(req, timeout=timeout) as response:
        raw = json.loads(response.read().decode("utf-8"))
    content = raw.get("message", {}).get("content") or raw.get("response")
    if not isinstance(content, str):
        raise RuntimeError("Ollama response has no content")
    data = _parse_json_object(content)
    predictions: dict[str, dict[str, object]] = {}
    for item in data.get("assignments", []):
        speaker_id = str(item.get("speaker_id") or "")
        role = str(item.get("role") or "")
        if speaker_id not in unresolved_ids or role not in ALLOWED_MODEL_ROLES:
            continue
        confidence = min(max(float(item.get("confidence") or 0.0), 0.0), 0.88)
        predictions[speaker_id] = {
            "role": role,
            "confidence": confidence,
            "reason": str(item.get("reason") or "本地模型按整位说话人的上下文判断"),
        }
    return predictions


def _parse_json_object(content: str) -> dict:
    stripped = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", stripped, flags=re.DOTALL)
        if match is None:
            raise ValueError("Role model did not return JSON")
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Role model JSON must be an object")
    return value
