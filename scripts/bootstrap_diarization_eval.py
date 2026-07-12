"""Prepare and document diarization evaluation environment readiness.

This script does not install packages, download models, or read private tokens.
It records whether pyannote and 3D-Speaker are ready, then writes exact next
commands for measured evaluation.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_21_diarization_bootstrap"

ModuleChecker = Callable[[str], bool]
ModuleProbe = Callable[[str], dict[str, Any]]
PathExists = Callable[[str], bool]


def collect_bootstrap_status(
    *,
    env: Mapping[str, str] | None = None,
    module_checker: ModuleChecker | None = None,
    module_probe: ModuleProbe | None = None,
    path_exists: PathExists | None = None,
) -> dict[str, object]:
    env = env or os.environ
    module_checker = module_checker or module_available
    module_probe = module_probe or probe_module
    path_exists = path_exists or (lambda value: Path(value).exists())

    hf_token_present = bool(env.get("HF_TOKEN"))
    pyannote_audio = module_checker("pyannote.audio")
    pyannote_metrics = module_checker("pyannote.metrics")
    pyannote_audio_probe = module_probe("pyannote.audio") if pyannote_audio else {
        "import_ok": False,
        "reason": "not installed",
    }
    pyannote_metrics_probe = module_probe("pyannote.metrics") if pyannote_metrics else {
        "import_ok": False,
        "reason": "not installed",
    }
    torch_probe = module_probe("torch") if module_checker("torch") else {"import_ok": False, "reason": "not installed"}
    torchaudio_probe = module_probe("torchaudio") if module_checker("torchaudio") else {
        "import_ok": False,
        "reason": "not installed",
    }
    numpy_probe = module_probe("numpy") if module_checker("numpy") else {"import_ok": False, "reason": "not installed"}
    pyannote_ready = bool(pyannote_audio_probe.get("import_ok") and hf_token_present)

    speaker_python = env.get("THREED_SPEAKER_PYTHON", "")
    speaker_script = env.get("THREED_SPEAKER_SCRIPT", "")
    speaker_python_ready = bool(speaker_python and path_exists(speaker_python))
    speaker_script_ready = bool(speaker_script and path_exists(speaker_script))
    threed_ready = speaker_python_ready and speaker_script_ready

    return {
        "scope": "diarization engine bootstrap",
        "python": {
            "executable": sys.executable,
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
        },
        "pyannote": {
            "status": "ready" if pyannote_ready else "blocked",
            "pyannote_audio_installed": pyannote_audio,
            "pyannote_audio_import": pyannote_audio_probe,
            "pyannote_metrics_installed": pyannote_metrics,
            "pyannote_metrics_import": pyannote_metrics_probe,
            "torch_import": torch_probe,
            "torchaudio_import": torchaudio_probe,
            "numpy_import": numpy_probe,
            "hf_token_present": hf_token_present,
            "reason": pyannote_reason(bool(pyannote_audio_probe.get("import_ok")), hf_token_present),
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


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def probe_module(name: str) -> dict[str, Any]:
    try:
        module = __import__(name, fromlist=["__name__"])
    except Exception as exc:  # pragma: no cover - exercised in integration reports
        return {"import_ok": False, "reason": f"{type(exc).__name__}: {exc}"}
    version = getattr(module, "__version__", None)
    payload: dict[str, Any] = {"import_ok": True, "version": version}
    if name == "torchaudio":
        payload["has_audio_metadata"] = hasattr(module, "AudioMetaData")
    return payload


def pyannote_reason(pyannote_audio_import_ok: bool, hf_token_present: bool) -> str:
    missing = []
    if not pyannote_audio_import_ok:
        missing.append("pyannote.audio is not importable")
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
            ".\\.venv-diarization\\Scripts\\python -m pip install -r requirements.txt",
            "$env:HF_TOKEN='<your local Hugging Face token>'",
            ".\\.venv-diarization\\Scripts\\python scripts\\run_diarization_engine_compare.py --engines pyannote --reports-dir data\\asr_eval\\reports\\v0_8_21_pyannote_measured",
        ],
        "three_d_speaker_setup": [
            "$env:THREED_SPEAKER_PYTHON='C:\\path\\to\\3d-speaker\\venv\\Scripts\\python.exe'",
            "$env:THREED_SPEAKER_SCRIPT='C:\\path\\to\\3d-speaker\\diarize_wrapper.py'",
            "python scripts\\run_diarization_engine_compare.py --engines three_d_speaker --reports-dir data\\asr_eval\\reports\\v0_8_21_three_d_speaker_measured",
        ],
    }


def render_markdown(payload: dict[str, object]) -> str:
    pyannote = payload["pyannote"]
    threed = payload["three_d_speaker"]
    commands = payload["recommended_commands"]
    lines = [
        "# Diarization Engine Bootstrap Report",
        "",
        "## Current Status",
        "",
        "| Engine | Status | Reason |",
        "| --- | --- | --- |",
        f"| pyannote community-1 | `{pyannote['status']}` | {pyannote['reason']} |",
        f"| 3D-Speaker | `{threed['status']}` | {threed['reason']} |",
        "",
        "## pyannote Retest Commands",
        "",
        "```powershell",
        *commands["pyannote_setup"],
        "```",
        "",
        "## 3D-Speaker Retest Commands",
        "",
        "```powershell",
        *commands["three_d_speaker_setup"],
        "```",
        "",
        "## Engineering Boundaries",
        "",
        "- This script records environment readiness only.",
        "- It does not download public audio, commit model weights, or commit HF_TOKEN.",
        "- Missing pyannote or 3D-Speaker dependencies are recorded as blocked, not as poor model quality.",
        "- AliMeeting public meeting samples are used only for diarization evaluation, not for medical consultation accuracy.",
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
