from __future__ import annotations

import json
import os
import base64
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment


def _first_text(data: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = data.get(key)
        if value is not None:
            return str(value)
    return ""


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_segment(segment: Any) -> ASRSegment | None:
    if isinstance(segment, str):
        text = segment.strip()
        return ASRSegment(speaker="online", role=None, text=text) if text else None
    if not isinstance(segment, dict):
        return None

    text = _first_text(segment, ("text", "transcript", "sentence", "utterance"))
    if not text:
        return None
    return ASRSegment(
        speaker=(
            str(segment.get("speaker"))
            if segment.get("speaker") is not None
            else str(segment.get("spk"))
            if segment.get("spk") is not None
            else str(segment.get("speaker_id"))
            if segment.get("speaker_id") is not None
            else None
        ),
        role=str(segment.get("role")) if segment.get("role") is not None else None,
        text=text,
        start_time=segment.get("start_time", segment.get("start", segment.get("begin"))),
        end_time=segment.get("end_time", segment.get("end")),
        confidence=segment.get("confidence", segment.get("conf")),
    )


def _normalize_keywords(value: Any) -> dict[str, list[str]]:
    if isinstance(value, dict):
        return {
            "expected": [str(item) for item in _as_list(value.get("expected"))],
            "recognized": [str(item) for item in _as_list(value.get("recognized"))],
            "missing": [str(item) for item in _as_list(value.get("missing"))],
        }
    if isinstance(value, list):
        return {"expected": [], "recognized": [str(item) for item in value], "missing": []}
    return {"expected": [], "recognized": [], "missing": []}


def normalize_online_asr_response(data: dict[str, Any], audio_id: str = "") -> ASRResult:
    """Adapt common online ASR JSON shapes to the project's ASRResult schema."""
    if not isinstance(data, dict):
        raise RuntimeError("Online ASR response JSON must be an object")

    body = data
    nested = data.get("data") or data.get("result")
    if isinstance(nested, dict):
        body = {**data, **nested}

    text = _first_text(body, ("text", "transcript", "recognized_text", "raw_text"))
    raw_segments = body.get("segments", body.get("sentences", body.get("utterances")))
    segments = [
        normalized
        for normalized in (_normalize_segment(segment) for segment in _as_list(raw_segments))
        if normalized is not None
    ]
    if not text and segments:
        text = "".join(segment.text for segment in segments)
    if not segments and text:
        segments = [ASRSegment(speaker="online", role=None, text=text)]

    conversation_text = _first_text(body, ("conversation_text", "dialogue_text"))
    if not conversation_text:
        conversation_text = text

    warnings = body.get("warnings", body.get("warning"))
    return ASRResult(
        audio_id=str(body.get("audio_id") or audio_id),
        engine=str(body.get("engine") or body.get("provider") or "online"),
        text=text,
        conversation_text=conversation_text,
        segments=segments,
        duration=body.get("duration", body.get("audio_duration")),
        medical_keywords=_normalize_keywords(body.get("medical_keywords", body.get("keywords"))),
        warnings=[str(item) for item in _as_list(warnings)],
    )


class OnlineASREngine:
    name = "online"

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: int = 120,
    ) -> None:
        self.api_url = api_url or os.environ.get("ONLINE_ASR_API_URL")
        self.api_key = api_key or os.environ.get("ONLINE_ASR_API_KEY")
        self.timeout_seconds = timeout_seconds
        missing = [
            name
            for name, value in [
                ("ONLINE_ASR_API_URL", self.api_url),
                ("ONLINE_ASR_API_KEY", self.api_key),
            ]
            if not value
        ]
        if missing:
            raise RuntimeError(
                "Online ASR is not configured. Missing environment variables: "
                f"{', '.join(missing)}. 当前选择的是在线 ASR，不是在线 LLM。"
                "如果要测试 DeepSeek，请使用文本导入，或 ASR 选择 FunASR 后上传生成病历。"
                "Do not hard-code API keys; set them in the runtime environment."
            )

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        payload = {
            "audio_id": audio_id,
            "filename": audio_path.name,
            "audio_base64": base64.b64encode(audio_path.read_bytes()).decode("ascii"),
        }
        request = urllib.request.Request(
            self.api_url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Online ASR request failed: {exc}") from exc

        try:
            data = json.loads(response_body)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Online ASR response is not valid JSON") from exc

        return normalize_online_asr_response(data, audio_id=audio_id)

    def _result_from_response(self, audio_id: str, data: dict[str, Any]) -> ASRResult:
        return normalize_online_asr_response(data, audio_id=audio_id)
