from __future__ import annotations

from pathlib import Path
from typing import Any

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.evaluator import ASREvaluator


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_HOTWORD_PATH = PROJECT_ROOT / "config" / "hotwords_medical.txt"


class FunASREngine:
    name = "funasr-paraformer-zh"

    def __init__(
        self,
        model: str = "paraformer-zh",
        device: str = "cpu",
        hotword_path: str | Path | None = DEFAULT_HOTWORD_PATH,
        enable_punctuation: bool = True,
        enable_vad: bool = True,
    ) -> None:
        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "FunASR import failed. Please check ASR dependencies with "
                "`python scripts/check_funasr_env.py` and install optional dependencies with "
                "`pip install -r requirements-asr.txt`. "
                f"Original error: {exc!r}"
            ) from exc

        self.hotwords = self._load_hotwords(hotword_path)
        model_kwargs: dict[str, Any] = {"model": model, "device": device}
        if enable_vad:
            model_kwargs["vad_model"] = "fsmn-vad"
        if enable_punctuation:
            model_kwargs["punc_model"] = "ct-punc"
        self.model = AutoModel(**model_kwargs)

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        generate_kwargs: dict[str, Any] = {
            "input": str(audio_path),
            "batch_size_s": 300,
        }
        if self.hotwords:
            generate_kwargs["hotword"] = " ".join(self.hotwords)

        raw_result = self.model.generate(**generate_kwargs)
        text = self._extract_text(raw_result)
        segments = self._extract_segments(raw_result, text)
        conversation_text = self._build_conversation_text(segments, text)
        keywords = ASREvaluator().keyword_metrics(self.hotwords, text)

        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=text,
            conversation_text=conversation_text,
            segments=segments,
            duration=self._infer_duration(segments),
            medical_keywords={
                "expected": keywords["expected"],
                "recognized": keywords["recognized"],
                "missing": keywords["missing"],
            },
        )

    def _load_hotwords(self, hotword_path: str | Path | None) -> list[str]:
        if hotword_path is None:
            return []
        path = Path(hotword_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            return []
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    def _extract_text(self, raw_result: Any) -> str:
        items = raw_result if isinstance(raw_result, list) else [raw_result]
        texts: list[str] = []
        for item in items:
            if isinstance(item, dict):
                value = item.get("text") or item.get("preds") or ""
                if isinstance(value, str):
                    texts.append(value.strip())
            elif isinstance(item, str):
                texts.append(item.strip())
        return "\n".join(text for text in texts if text)

    def _extract_segments(self, raw_result: Any, fallback_text: str) -> list[ASRSegment]:
        items = raw_result if isinstance(raw_result, list) else [raw_result]
        segments: list[ASRSegment] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            sentence_info = item.get("sentence_info") or item.get("sentences") or []
            for index, sentence in enumerate(sentence_info):
                if not isinstance(sentence, dict):
                    continue
                text = str(sentence.get("text") or "").strip()
                if not text:
                    continue
                segments.append(
                    ASRSegment(
                        speaker=str(sentence.get("spk") or sentence.get("speaker") or f"spk{index}"),
                        role=None,
                        text=text,
                        start_time=self._timestamp_to_seconds(sentence.get("start")),
                        end_time=self._timestamp_to_seconds(sentence.get("end")),
                        confidence=self._optional_float(sentence.get("confidence")),
                    )
                )
        if segments:
            return segments
        return [ASRSegment(speaker="spk0", role=None, text=fallback_text, start_time=None, end_time=None)]

    def _build_conversation_text(self, segments: list[ASRSegment], fallback_text: str) -> str:
        if not segments:
            return fallback_text
        return "\n".join(f"[{segment.speaker or 'spk0'}] {segment.text}" for segment in segments)

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
