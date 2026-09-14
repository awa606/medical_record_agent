from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import BinaryIO

from fastapi import HTTPException


DEFAULT_AUDIO_UPLOAD_MAX_BYTES = 200 * 1024 * 1024
DEFAULT_RECORDING_CHUNK_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_RECORDING_MAX_SECONDS = 30 * 60


def _env_int(name: str, default: int) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except ValueError:
        return default
    return value if value > 0 else default


def audio_upload_max_bytes() -> int:
    return _env_int("MEDICAL_RECORD_AGENT_MAX_UPLOAD_BYTES", DEFAULT_AUDIO_UPLOAD_MAX_BYTES)


def recording_chunk_max_bytes() -> int:
    return _env_int("MEDICAL_RECORD_AGENT_MAX_RECORDING_CHUNK_BYTES", DEFAULT_RECORDING_CHUNK_MAX_BYTES)


def recording_max_seconds() -> int:
    return _env_int("MEDICAL_RECORD_AGENT_MAX_RECORDING_SECONDS", DEFAULT_RECORDING_MAX_SECONDS)


def copy_upload_with_limit(
    source: BinaryIO,
    destination: Path,
    *,
    max_bytes: int,
) -> int:
    destination.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    try:
        with destination.open("wb") as output:
            while True:
                chunk = source.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(status_code=413, detail=f"Uploaded audio exceeds {max_bytes} bytes")
                output.write(chunk)
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return total


def directory_free_bytes(path: Path) -> int:
    path.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(path).free
