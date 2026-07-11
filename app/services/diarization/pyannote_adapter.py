from __future__ import annotations

import importlib.util
import os
from pathlib import Path

from app.schemas.asr import DiarizationTurn


class PyannoteCommunityAdapter:
    name = "pyannote_community_1"

    def __init__(self, *, token: str | None = None) -> None:
        self.token = token or os.environ.get("HF_TOKEN")
        self._pipeline = None

    def availability(self) -> tuple[bool, str]:
        try:
            audio_spec = importlib.util.find_spec("pyannote.audio")
        except ModuleNotFoundError:
            audio_spec = None
        if audio_spec is None:
            return False, "pyannote.audio is not installed"
        if not self.token:
            return False, "HF_TOKEN is required for pyannote Community-1"
        return True, "pyannote Community-1 dependency and token available"

    def diarize(self, audio_path: Path) -> list[DiarizationTurn]:
        available, reason = self.availability()
        if not available:
            raise RuntimeError(reason)
        if self._pipeline is None:
            from pyannote.audio import Pipeline

            self._pipeline = Pipeline.from_pretrained(
                "pyannote/speaker-diarization-community-1",
                token=self.token,
            )
        output = self._pipeline(str(audio_path))
        annotation = getattr(output, "speaker_diarization", output)
        return [
            DiarizationTurn(
                start_time=float(turn.start),
                end_time=float(turn.end),
                speaker_id=str(speaker),
            )
            for turn, _, speaker in annotation.itertracks(yield_label=True)
        ]
