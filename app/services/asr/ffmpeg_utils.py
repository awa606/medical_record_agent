from __future__ import annotations

import os
import shutil
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
PORTABLE_FFMPEG = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
PORTABLE_FFPROBE = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffprobe.exe"


def find_ffmpeg_executable() -> Path | None:
    candidates = []
    env_binary = os.environ.get("FFMPEG_BINARY")
    if env_binary:
        candidates.append(Path(env_binary))

    env_dir = os.environ.get("FFMPEG_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / "ffmpeg.exe")
        candidates.append(Path(env_dir) / "bin" / "ffmpeg.exe")

    candidates.append(PORTABLE_FFMPEG)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    system_path = shutil.which("ffmpeg")
    return Path(system_path).resolve() if system_path else None


def find_ffprobe_executable() -> Path | None:
    candidates = []
    env_binary = os.environ.get("FFPROBE_BINARY")
    if env_binary:
        candidates.append(Path(env_binary))

    env_dir = os.environ.get("FFMPEG_DIR")
    if env_dir:
        candidates.append(Path(env_dir) / "ffprobe.exe")
        candidates.append(Path(env_dir) / "bin" / "ffprobe.exe")

    ffmpeg = find_ffmpeg_executable()
    if ffmpeg is not None:
        candidates.append(ffmpeg.with_name("ffprobe.exe"))

    candidates.append(PORTABLE_FFPROBE)

    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate.resolve()

    system_path = shutil.which("ffprobe")
    return Path(system_path).resolve() if system_path else None


def ensure_ffmpeg_on_path() -> Path | None:
    executable = find_ffmpeg_executable()
    if executable is None:
        return None
    parent = str(executable.parent)
    path_parts = os.environ.get("PATH", "").split(os.pathsep)
    if parent not in path_parts:
        os.environ["PATH"] = parent + os.pathsep + os.environ.get("PATH", "")
    os.environ.setdefault("FFMPEG_BINARY", str(executable))
    return executable
