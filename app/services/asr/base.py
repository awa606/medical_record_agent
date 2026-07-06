from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas import ASRResult


class ASREngine(Protocol):
    name: str

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        """Transcribe an audio file into text usable by the record agent."""
