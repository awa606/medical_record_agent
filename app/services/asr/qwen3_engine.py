from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.funasr_engine import DEFAULT_HOTWORD_PATH


DEPENDENCY_ERROR = (
    "Qwen3-ASR dependencies are not installed. Please install requirements-qwen3-asr.txt"
)
DEFAULT_MODEL_ID = "Qwen/Qwen3-ASR-0.6B"
ROLE_REVIEW_WARNING = (
    "Qwen3-ASR did not provide reliable speaker roles; please manually review roles."
)


class Qwen3ASREngine:
    name = "qwen3-asr-0.6b"

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        hotword_path: str | Path | None = DEFAULT_HOTWORD_PATH,
        model_instance: Any | None = None,
        language: str | None = None,
    ) -> None:
        self.model_id = model_id or os.environ.get("QWEN3_ASR_MODEL_ID") or DEFAULT_MODEL_ID
        self.device = device or os.environ.get("QWEN3_ASR_DEVICE") or "cpu"
        self.language = language or os.environ.get("QWEN3_ASR_LANGUAGE")
        self.max_new_tokens = int(os.environ.get("QWEN3_ASR_MAX_NEW_TOKENS", "512"))
        self.hotwords = self._load_hotwords(hotword_path)
        self.model = model_instance if model_instance is not None else self._load_model()

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        raw_result = self._transcribe_with_model(audio_path)
        return self._result_from_response(audio_id, raw_result)

    def _load_model(self) -> Any:
        try:
            from qwen_asr import Qwen3ASRModel
        except ImportError as exc:
            raise RuntimeError(DEPENDENCY_ERROR) from exc

        model_kwargs: dict[str, Any] = {
            "device_map": self.device,
            "max_new_tokens": self.max_new_tokens,
        }
        try:
            return Qwen3ASRModel.from_pretrained(self.model_id, **model_kwargs)
        except TypeError:
            model = Qwen3ASRModel.from_pretrained(self.model_id)
            if hasattr(model, "to"):
                model = model.to(self.device)
            return model

    def _transcribe_with_model(self, audio_path: Path) -> Any:
        transcribe = getattr(self.model, "transcribe", None)
        if transcribe is None:
            raise RuntimeError("Qwen3-ASR model does not provide a transcribe method")

        try:
            return transcribe(audio=str(audio_path), language=self.language)
        except TypeError:
            try:
                return transcribe(audio=str(audio_path))
            except TypeError:
                if self.language:
                    try:
                        return transcribe(str(audio_path), language=self.language)
                    except TypeError:
                        pass
                return transcribe(str(audio_path))

    def _result_from_response(self, audio_id: str, raw_result: Any) -> ASRResult:
        text = self._extract_text(raw_result)
        segments = self._extract_segments(raw_result, text)
        keywords = ASREvaluator().keyword_metrics(self.hotwords, text)

        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=text,
            conversation_text=f"[待校正] {text}",
            segments=segments,
            duration=self._infer_duration(segments),
            medical_keywords={
                "expected": keywords["expected"],
                "recognized": keywords["recognized"],
                "missing": keywords["missing"],
            },
            warnings=[ROLE_REVIEW_WARNING],
        )

    def _load_hotwords(self, hotword_path: str | Path | None) -> list[str]:
        if hotword_path is None:
            return []
        path = Path(hotword_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[3] / path
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _extract_text(self, raw_result: Any) -> str:
        if isinstance(raw_result, str):
            return raw_result.strip()
        if isinstance(raw_result, list):
            return "\n".join(
                text for text in (self._extract_text(item) for item in raw_result) if text
            )
        if isinstance(raw_result, dict):
            nested = raw_result.get("data") or raw_result.get("result")
            if isinstance(nested, (dict, list, str)):
                nested_text = self._extract_text(nested)
                if nested_text:
                    return nested_text
            for key in ("text", "transcript", "recognized_text", "raw_text"):
                value = raw_result.get(key)
                if value is not None:
                    return str(value).strip()
            segments = raw_result.get("segments") or raw_result.get("sentences") or raw_result.get("utterances")
            if isinstance(segments, list):
                return "".join(segment.text for segment in self._segments_from_items(segments))
            return ""
        for attr in ("text", "transcript", "recognized_text"):
            value = getattr(raw_result, attr, None)
            if value is not None:
                return str(value).strip()
        return ""

    def _extract_segments(self, raw_result: Any, fallback_text: str) -> list[ASRSegment]:
        items: Any = None
        if isinstance(raw_result, dict):
            body = raw_result
            nested = raw_result.get("data") or raw_result.get("result")
            if isinstance(nested, dict):
                body = {**raw_result, **nested}
            items = body.get("segments") or body.get("sentences") or body.get("utterances")
        elif hasattr(raw_result, "segments"):
            items = getattr(raw_result, "segments")

        segments = self._segments_from_items(items)
        if segments:
            return segments
        return [ASRSegment(speaker="qwen3", role=None, text=fallback_text)]

    def _segments_from_items(self, items: Any) -> list[ASRSegment]:
        if not isinstance(items, list):
            return []

        segments: list[ASRSegment] = []
        for item in items:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    segments.append(ASRSegment(speaker="qwen3", role=None, text=text))
                continue
            if not isinstance(item, dict):
                continue
            text = str(
                item.get("text")
                or item.get("transcript")
                or item.get("sentence")
                or item.get("utterance")
                or ""
            ).strip()
            if not text:
                continue
            segments.append(
                ASRSegment(
                    speaker=str(item.get("speaker") or item.get("spk") or "qwen3"),
                    role=None,
                    text=text,
                    start_time=self._optional_float(item.get("start_time", item.get("start"))),
                    end_time=self._optional_float(item.get("end_time", item.get("end"))),
                    confidence=self._optional_float(item.get("confidence", item.get("conf"))),
                )
            )
        return segments

    def _infer_duration(self, segments: list[ASRSegment]) -> float | None:
        end_times = [segment.end_time for segment in segments if segment.end_time is not None]
        return max(end_times) if end_times else None

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
