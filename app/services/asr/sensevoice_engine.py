from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.funasr_engine import DEFAULT_HOTWORD_PATH


DEPENDENCY_ERROR = (
    "SenseVoice requires FunASR dependencies. Install `requirements-asr.txt` "
    "inside `.venv-asr` before running engine=sensevoice."
)
DEFAULT_MODEL_ID = "FunAudioLLM/SenseVoiceSmall"
ROLE_REVIEW_WARNING = (
    "SenseVoice speaker labels are model-generated and must be reviewed by the doctor."
)


class SenseVoiceASREngine:
    name = "sensevoice-small"

    def __init__(
        self,
        model_id: str | None = None,
        device: str | None = None,
        language: str | None = None,
        hotword_path: str | Path | None = DEFAULT_HOTWORD_PATH,
        model_instance: Any | None = None,
        postprocess: Callable[[str], str] | None = None,
    ) -> None:
        self.model_id = model_id or os.environ.get("SENSEVOICE_MODEL_ID") or DEFAULT_MODEL_ID
        self.device = device or os.environ.get("SENSEVOICE_DEVICE") or "cpu"
        self.language = language or os.environ.get("SENSEVOICE_LANGUAGE") or "zh"
        self.hotwords = self._load_hotwords(hotword_path)
        self._postprocess = postprocess or self._load_postprocess()
        started_at = time.perf_counter()
        self.model = model_instance if model_instance is not None else self._load_model()
        self.model_load_time_seconds = round(time.perf_counter() - started_at, 3)

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        raw_result = self.model.generate(
            input=str(audio_path),
            cache={},
            language=self.language,
            use_itn=True,
            batch_size_s=300,
        )
        text = self._extract_text(raw_result)
        segments = self._extract_segments(raw_result, text)
        keywords = ASREvaluator().keyword_metrics(self.hotwords, text)

        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=text,
            conversation_text=self._conversation_from_segments(segments, text),
            segments=segments,
            duration=self._infer_duration(segments),
            medical_keywords={
                "expected": keywords["expected"],
                "recognized": keywords["recognized"],
                "missing": keywords["missing"],
            },
            warnings=[ROLE_REVIEW_WARNING],
        )

    def _load_model(self) -> Any:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(DEPENDENCY_ERROR) from exc

        return AutoModel(
            model=self.model_id,
            vad_model="fsmn-vad",
            vad_kwargs={"max_single_segment_time": 30000},
            device=self.device,
            hub=os.environ.get("SENSEVOICE_HUB", "hf"),
        )

    def _load_postprocess(self) -> Callable[[str], str]:
        try:
            from funasr.utils.postprocess_utils import rich_transcription_postprocess

            return rich_transcription_postprocess
        except Exception:
            return lambda value: value

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
        segments = self._segments_from_items(self._response_items(raw_result))
        if segments:
            return "\n".join(segment.text for segment in segments if segment.text.strip())

        items = raw_result if isinstance(raw_result, list) else [raw_result]
        texts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("text") or item.get("preds") or item.get("sentence") or ""
                if isinstance(value, str):
                    texts.append(self._postprocess(value.strip()))
            elif isinstance(item, str):
                texts.append(self._postprocess(item.strip()))
        return "\n".join(text for text in texts if text)

    def _extract_segments(self, raw_result: Any, fallback_text: str) -> list[ASRSegment]:
        segments = self._segments_from_items(self._response_items(raw_result))
        if segments:
            return segments
        return [ASRSegment(speaker="sensevoice", role=None, text=fallback_text)]

    def _response_items(self, raw_result: Any) -> list[Any]:
        items = raw_result if isinstance(raw_result, list) else [raw_result]
        nested: list[Any] = []
        for item in items:
            if isinstance(item, dict):
                sentence_info = item.get("sentence_info") or item.get("sentences") or item.get("segments")
                if isinstance(sentence_info, list):
                    nested.extend(sentence_info)
                else:
                    nested.append(item)
            else:
                nested.append(item)
        return nested

    def _segments_from_items(self, items: list[Any]) -> list[ASRSegment]:
        segments: list[ASRSegment] = []
        for index, item in enumerate(items):
            if isinstance(item, str):
                text = self._postprocess(item.strip())
                if text:
                    segments.append(ASRSegment(speaker="sensevoice", role=None, text=text))
                continue
            if not isinstance(item, dict):
                continue
            raw_text = str(
                item.get("text")
                or item.get("sentence")
                or item.get("transcript")
                or item.get("utterance")
                or ""
            ).strip()
            text = self._postprocess(raw_text)
            if not text:
                continue
            segments.append(
                ASRSegment(
                    speaker=str(item.get("spk") or item.get("speaker") or f"spk{index}"),
                    role=None,
                    text=text,
                    start_time=self._timestamp_to_seconds(item.get("start", item.get("start_time"))),
                    end_time=self._timestamp_to_seconds(item.get("end", item.get("end_time"))),
                    confidence=self._optional_float(item.get("confidence", item.get("conf"))),
                    needs_review=True,
                )
            )
        return segments

    def _conversation_from_segments(self, segments: list[ASRSegment], fallback_text: str) -> str:
        if not segments:
            return f"[待校正] {fallback_text}"
        return "\n".join(f"[{segment.speaker or 'sensevoice'}] {segment.text}" for segment in segments)

    def _infer_duration(self, segments: list[ASRSegment]) -> float | None:
        end_times = [segment.end_time for segment in segments if segment.end_time is not None]
        return max(end_times) if end_times else None

    def _timestamp_to_seconds(self, value: Any) -> float | None:
        number = self._optional_float(value)
        if number is None:
            return None
        return round(number / 1000.0, 3) if number > 1000 else number

    def _optional_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
