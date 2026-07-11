from __future__ import annotations

from pathlib import Path
from typing import Protocol

from app.schemas.asr import DiarizationTurn


class DiarizationEngine(Protocol):
    name: str

    def availability(self) -> tuple[bool, str]: ...

    def diarize(self, audio_path: Path) -> list[DiarizationTurn]: ...
