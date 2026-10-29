"""Run an isolated, fail-closed Alpha 5.1 local-provider verification server.

Use the existing FunASR Python environment. All runtime data, credentials and
logs remain under a new ignored .artifacts directory. Never use patient data.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import sys


ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / ".artifacts"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8771)
    parser.add_argument("--modelscope-cache", type=Path, required=True)
    parser.add_argument("--ffmpeg-bin", type=Path, required=True)
    args = parser.parse_args()
    target = args.run_dir.resolve()
    if not target.is_relative_to(ARTIFACTS.resolve()) or target == ARTIFACTS.resolve():
        parser.error("--run-dir must be a new child of the repository .artifacts directory")
    if target.exists():
        parser.error("--run-dir already exists; refusing to overwrite evidence")
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be in 1024..65535")
    model_cache = args.modelscope_cache.resolve()
    if not (model_cache / "models").is_dir():
        parser.error("--modelscope-cache must contain the existing models directory")
    ffmpeg_bin = args.ffmpeg_bin.resolve()
    if not (ffmpeg_bin / "ffmpeg.exe").is_file():
        parser.error("--ffmpeg-bin must contain an existing ffmpeg.exe")

    runtime = target / "runtime"
    for directory in (runtime / "uploads", runtime / "outputs", runtime / "speaker-profiles"):
        directory.mkdir(parents=True)
    password = secrets.token_urlsafe(32)
    (target / "admin-password.txt").write_text(password, encoding="utf-8")
    os.environ.update({
        "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD": password,
        "MEDICAL_RECORD_AGENT_DB": str(runtime / "mra.sqlite3"),
        "MEDICAL_RECORD_AGENT_UPLOAD_DIR": str(runtime / "uploads"),
        "MEDICAL_RECORD_AGENT_OUTPUT_DIR": str(runtime / "outputs"),
        "MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR": str(runtime / "speaker-profiles"),
        "RECORD_PROVIDER_MODE": "edge",
        "MEDICAL_RECORD_AGENT_ASR_ENGINE": "funasr",
        "ASR_ENGINE": "funasr",
        "MEDICAL_RECORD_AGENT_REQUIRE_FUNASR": "1",
        "ASR_PREWARM_ENABLED": "1",
        "ASR_PREWARM_PROFILE": "upload",
        "LLM_PROVIDER": "ollama",
        "OLLAMA_BASE_URL": "http://127.0.0.1:11434",
        "OLLAMA_MODEL": "qwen3:4b",
        "LLM_TIMEOUT_SECONDS": "180",
        "LLM_MAX_RETRIES": "0",
        "MRA_ANONYMIZE": "1",
        "HF_HUB_OFFLINE": "1",
        "TRANSFORMERS_OFFLINE": "1",
        "MODELSCOPE_CACHE": str(model_cache),
        "FFMPEG_BINARY": str(ffmpeg_bin / "ffmpeg.exe"),
    })
    os.environ["PATH"] = str(ffmpeg_bin) + os.pathsep + os.environ.get("PATH", "")
    for name in ("ONLINE_LLM_API_KEY", "ONLINE_LLM_API_BASE", "ONLINE_LLM_MODEL"):
        os.environ.pop(name, None)

    print(json.dumps({"run_dir": str(target), "port": args.port,
                      "asr": "funasr", "llm": "ollama/qwen3:4b",
                      "mode": "edge", "fallback": "forbidden"}), flush=True)
    sys.path.insert(0, str(ROOT))
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=args.port, log_level="info")


if __name__ == "__main__":
    main()
