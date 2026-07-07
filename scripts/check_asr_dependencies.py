"""Write a lightweight dependency report for local ASR benchmark engines."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports"
DEFAULT_JSON = DEFAULT_REPORTS_DIR / "asr_dependency_check.json"
DEFAULT_MD = DEFAULT_REPORTS_DIR / "asr_dependency_check.md"


def collect_asr_dependency_status() -> dict[str, Any]:
    modules = {
        "torch": _module_info("torch"),
        "torchaudio": _module_info("torchaudio"),
        "funasr": _module_info("funasr"),
        "qwen_asr": _module_info("qwen_asr"),
        "whisper": _module_info("whisper"),
        "soundfile": _module_info("soundfile"),
    }
    modules["ffmpeg"] = _ffmpeg_info()
    modules["sensevoice"] = {
        "available": modules["funasr"]["available"],
        "version": modules["funasr"].get("version"),
        "note": "SenseVoice uses funasr.AutoModel with FunAudioLLM/SenseVoiceSmall.",
    }
    return {
        "schema_version": "v0.5.2",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable_name": Path(sys.executable).name,
        },
        "cuda": _cuda_info(modules["torch"]["available"]),
        "modules": modules,
        "environment": {
            "SENSEVOICE_MODEL_ID": os.environ.get("SENSEVOICE_MODEL_ID", "FunAudioLLM/SenseVoiceSmall"),
            "SENSEVOICE_DEVICE": os.environ.get("SENSEVOICE_DEVICE", "cpu"),
            "SENSEVOICE_LANGUAGE": os.environ.get("SENSEVOICE_LANGUAGE", "zh"),
            "WHISPER_MODEL": os.environ.get("WHISPER_MODEL", "base"),
            "WHISPER_DEVICE": os.environ.get("WHISPER_DEVICE", "cpu"),
            "WHISPER_LANGUAGE": os.environ.get("WHISPER_LANGUAGE", "zh"),
            "QWEN3_ASR_MODEL_ID": os.environ.get("QWEN3_ASR_MODEL_ID", "Qwen/Qwen3-ASR-0.6B"),
            "QWEN3_ASR_DEVICE": os.environ.get("QWEN3_ASR_DEVICE", "cpu"),
            "HF_HOME_configured": bool(os.environ.get("HF_HOME")),
            "MODELSCOPE_CACHE_configured": bool(os.environ.get("MODELSCOPE_CACHE")),
        },
    }


def write_dependency_report(
    json_output: Path = DEFAULT_JSON,
    markdown_output: Path = DEFAULT_MD,
) -> dict[str, Any]:
    report = collect_asr_dependency_status()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    python = report.get("python") or {}
    cuda = report.get("cuda") or {}
    modules = report.get("modules") or {}
    environment = report.get("environment") or {}

    lines = [
        "# ASR 本地依赖检查报告",
        "",
        "> 本报告用于 v0.5.2 多模型 ASR 评测。它只检查依赖和环境变量，不下载模型，不调用真实患者数据。",
        "",
        "## Python 与 CUDA",
        "",
        "| 项目 | 当前值 |",
        "| --- | --- |",
        f"| Python | {_cell(python.get('implementation'))} {_cell(python.get('version'))} |",
        f"| Python 可执行文件 | {_cell(python.get('executable_name'))} |",
        f"| CUDA 可用 | {_bool_cell(cuda.get('available'))} |",
        f"| GPU 数量 | {_cell(cuda.get('device_count'))} |",
        "",
        "## 依赖状态",
        "",
        "| 依赖 | 状态 | 版本/说明 |",
        "| --- | --- | --- |",
    ]
    for name in ["torch", "torchaudio", "funasr", "sensevoice", "qwen_asr", "whisper", "soundfile", "ffmpeg"]:
        item = modules.get(name) or {}
        lines.append(
            f"| {name} | {_bool_cell(item.get('available'))} | {_cell(item.get('version') or item.get('note') or item.get('error'))} |"
        )

    lines.extend(
        [
            "",
            "## 模型环境变量",
            "",
            "| 变量 | 当前值 |",
            "| --- | --- |",
        ]
    )
    for key, value in environment.items():
        lines.append(f"| `{key}` | {_cell(value)} |")
    lines.append("")
    return "\n".join(lines)


def _module_info(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    info: dict[str, Any] = {"available": spec is not None, "version": None}
    if spec is None:
        return info
    try:
        module = __import__(module_name)
        info["version"] = getattr(module, "__version__", None)
    except Exception as exc:  # noqa: BLE001 - dependency import failures are benchmark data.
        info["available"] = False
        info["error"] = _sanitize_local_paths(str(exc))[:200]
    return info


def _ffmpeg_info() -> dict[str, Any]:
    executable = shutil.which("ffmpeg")
    info: dict[str, Any] = {"available": executable is not None, "version": None}
    if executable is None:
        return info
    try:
        completed = subprocess.run(
            [executable, "-version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        first_line = (completed.stdout or completed.stderr).splitlines()[0]
        info["version"] = first_line[:160]
    except Exception as exc:  # noqa: BLE001 - keep dependency check non-fatal.
        info["error"] = _sanitize_local_paths(str(exc))[:200]
    return info


def _cuda_info(torch_available: bool) -> dict[str, Any]:
    info: dict[str, Any] = {"available": False, "device_count": 0, "devices": []}
    if not torch_available:
        return info
    try:
        import torch

        available = bool(torch.cuda.is_available())
        count = int(torch.cuda.device_count()) if available else 0
        info.update(
            {
                "available": available,
                "device_count": count,
                "devices": [torch.cuda.get_device_name(index) for index in range(count)],
            }
        )
    except Exception as exc:  # noqa: BLE001 - dependency check must keep running.
        info["error"] = _sanitize_local_paths(str(exc))[:200]
    return info


def _sanitize_local_paths(value: str) -> str:
    root = str(PROJECT_ROOT)
    return value.replace(root, "<PROJECT_ROOT>").replace(root.replace("\\", "/"), "<PROJECT_ROOT>")


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def _bool_cell(value: Any) -> str:
    return "可用" if bool(value) else "不可用"


def main() -> int:
    parser = argparse.ArgumentParser(description="Check local ASR benchmark dependencies.")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    report = write_dependency_report(args.json_output, args.markdown_output)
    modules = report["modules"]
    print("ASR 依赖检查完成：")
    for name in ["torch", "funasr", "sensevoice", "whisper", "qwen_asr", "ffmpeg"]:
        print(f"- {name}: {modules[name]['available']}")
    print(f"- json: {args.json_output}")
    print(f"- markdown: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
