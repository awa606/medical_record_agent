from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.schemas.asr import DiarizationTurn


class ThreeDSpeakerAdapter:
    """Runs a locally configured 3D-Speaker wrapper that emits JSON turns."""

    name = "three_d_speaker"

    def __init__(self) -> None:
        self.python = os.environ.get("THREED_SPEAKER_PYTHON")
        self.script = os.environ.get("THREED_SPEAKER_SCRIPT")

    def availability(self) -> tuple[bool, str]:
        if not self.python or not Path(self.python).exists():
            return False, "THREED_SPEAKER_PYTHON is not configured"
        if not self.script or not Path(self.script).exists():
            return False, "THREED_SPEAKER_SCRIPT is not configured"
        return True, "3D-Speaker local wrapper configured"

    def diarize(self, audio_path: Path) -> list[DiarizationTurn]:
        available, reason = self.availability()
        if not available:
            raise RuntimeError(reason)
        completed = subprocess.run(
            [self.python, self.script, "--audio", str(audio_path), "--format", "json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        data = json.loads(completed.stdout)
        return [DiarizationTurn.model_validate(item) for item in data.get("turns", data)]
