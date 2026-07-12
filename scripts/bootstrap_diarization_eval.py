"""Prepare and document the next true diarization evaluation environment.

This script does not download models or install packages by default. It records
whether pyannote and 3D-Speaker are ready, then writes exact next commands.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from typing import Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_19_diarization_bootstrap"

ModuleChecker = Callable[[str], bool]
PathExists = Callable[[str], bool]


def collect_bootstrap_status(
    *,
    env: Mapping[str, str] | None = None,
    module_checker: ModuleChecker | None = None,
    path_exists: PathExists | None = None,
) -> dict[str, object]:
    env = env or os.environ
    module_checker = module_checker or module_available
    path_exists = path_exists or (lambda value: Path(value).exists())

    hf_token_present = bool(env.get("HF_TOKEN"))
    pyannote_audio = module_checker("pyannote.audio")
    pyannote_metrics = module_checker("pyannote.metrics")
    pyannote_ready = pyannote_audio and hf_token_present

    speaker_python = env.get("THREED_SPEAKER_PYTHON", "")
    speaker_script = env.get("THREED_SPEAKER_SCRIPT", "")
    speaker_python_ready = bool(speaker_python and path_exists(speaker_python))
    speaker_script_ready = bool(speaker_script and path_exists(speaker_script))
    threed_ready = speaker_python_ready and speaker_script_ready

    payload = {
        "scope": "v0.8.19 diarization engine bootstrap",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "pyannote": {
            "status": "ready" if pyannote_ready else "blocked",
            "pyannote_audio_installed": pyannote_audio,
            "pyannote_metrics_installed": pyannote_metrics,
            "hf_token_present": hf_token_present,
            "reason": pyannote_reason(pyannote_audio, hf_token_present),
        },
        "three_d_speaker": {
            "status": "ready" if threed_ready else "blocked",
            "python_configured": bool(speaker_python),
            "python_exists": speaker_python_ready,
            "script_configured": bool(speaker_script),
            "script_exists": speaker_script_ready,
            "reason": threed_reason(speaker_python_ready, speaker_script_ready),
        },
        "recommended_commands": recommended_commands(),
        "next_decision": "run measured pyannote or 3D-Speaker comparison once one engine is ready",
    }
    return payload


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def pyannote_reason(pyannote_audio: bool, hf_token_present: bool) -> str:
    missing = []
    if not pyannote_audio:
        missing.append("pyannote.audio is not installed")
    if not hf_token_present:
        missing.append("HF_TOKEN is not configured")
    return "; ".join(missing) if missing else "pyannote dependency and HF_TOKEN are ready"


def threed_reason(python_ready: bool, script_ready: bool) -> str:
    missing = []
    if not python_ready:
        missing.append("THREED_SPEAKER_PYTHON is missing or does not exist")
    if not script_ready:
        missing.append("THREED_SPEAKER_SCRIPT is missing or does not exist")
    return "; ".join(missing) if missing else "3D-Speaker wrapper is ready"


def recommended_commands() -> dict[str, list[str]]:
    return {
        "pyannote_setup": [
            "py -3.11 -m venv .venv-diarization",
            ".\\.venv-diarization\\Scripts\\python -m pip install --upgrade pip setuptools wheel",
            ".\\.venv-diarization\\Scripts\\python -m pip install -r requirements-diarization-experimental.txt",
            "$env:HF_TOKEN='<your local Hugging Face token>'",
            ".\\.venv-diarization\\Scripts\\python scripts\\run_diarization_engine_compare.py --engines pyannote --reports-dir data\\asr_eval\\reports\\v0_8_19_pyannote_measured",
        ],
        "three_d_speaker_setup": [
            "$env:THREED_SPEAKER_PYTHON='C:\\path\\to\\3d-speaker\\venv\\Scripts\\python.exe'",
            "$env:THREED_SPEAKER_SCRIPT='C:\\path\\to\\3d-speaker\\diarize_wrapper.py'",
            "python scripts\\run_diarization_engine_compare.py --engines three_d_speaker --reports-dir data\\asr_eval\\reports\\v0_8_19_three_d_speaker_measured",
        ],
    }


def render_markdown(payload: dict[str, object]) -> str:
    pyannote = payload["pyannote"]
    threed = payload["three_d_speaker"]
    commands = payload["recommended_commands"]
    lines = [
        "# v0.8.19 说话人分离引擎环境准备报告",
        "",
        "## 当前状态",
        "",
        "| 引擎 | 状态 | 说明 |",
        "| --- | --- | --- |",
        f"| pyannote community-1 | `{pyannote['status']}` | {pyannote['reason']} |",
        f"| 3D-Speaker | `{threed['status']}` | {threed['reason']} |",
        "",
        "## pyannote 复测命令",
        "",
        "```powershell",
        *commands["pyannote_setup"],
        "```",
        "",
        "## 3D-Speaker 复测命令",
        "",
        "```powershell",
        *commands["three_d_speaker_setup"],
        "```",
        "",
        "## 工程边界",
        "",
        "- 本脚本只记录环境准备状态，不下载公开音频、不提交模型权重、不提交 HF_TOKEN。",
        "- pyannote 和 3D-Speaker 缺失时记录为 blocked，不解释为模型效果差。",
        "- AliMeeting 公开会议样本只用于多说话人分离评测，不代表医疗问诊效果。",
        "",
    ]
    return "\n".join(lines)


def write_report(payload: dict[str, object], reports_dir: Path) -> tuple[Path, Path]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    json_path = reports_dir / "diarization_bootstrap_status.json"
    md_path = reports_dir / "diarization_bootstrap_status.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    return json_path, md_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare true diarization engine evaluation environment.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = collect_bootstrap_status()
    json_path, md_path = write_report(payload, args.reports_dir)
    print(json.dumps({"json": str(json_path), "markdown": str(md_path), **payload}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
