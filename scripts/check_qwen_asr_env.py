"""Check Qwen-ASR environment separately from the general ASR benchmark."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports"
DEFAULT_JSON = DEFAULT_REPORTS_DIR / "qwen_asr_env_check.json"
DEFAULT_MD = DEFAULT_REPORTS_DIR / "qwen_asr_env_check.md"


def collect_qwen_asr_env_status() -> dict[str, Any]:
    nagisa = _module_info("nagisa")
    qwen_asr = _module_info("qwen_asr")
    model_init = _check_qwen_model_init(qwen_asr.get("available", False))
    python_version = platform.python_version()
    python_info = {
        "version": python_version,
        "implementation": platform.python_implementation(),
        "executable_name": Path(sys.executable).name,
        "executable_path": _sanitize_local_paths(sys.executable),
        "prefix": _sanitize_local_paths(sys.prefix),
        "recommended_for_qwen": "3.12",
        "matches_recommended_version": python_version.startswith("3.12."),
        "inside_qwen_venv": ".venv-qwen-asr" in _sanitize_local_paths(sys.prefix).replace("\\", "/"),
    }
    return {
        "schema_version": "v0.5.4",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "python": python_info,
        "environment": {
            "QWEN3_ASR_MODEL_ID": os.environ.get("QWEN3_ASR_MODEL_ID", "Qwen/Qwen3-ASR-0.6B"),
            "QWEN3_ASR_DEVICE": os.environ.get("QWEN3_ASR_DEVICE", "cpu"),
            "HF_HOME_configured": bool(os.environ.get("HF_HOME")),
            "MODELSCOPE_CACHE_configured": bool(os.environ.get("MODELSCOPE_CACHE")),
        },
        "modules": {
            "nagisa": nagisa,
            "qwen_asr": qwen_asr,
        },
        "model_init": model_init,
        "recommendation": _recommendation(nagisa, qwen_asr, model_init, python_info),
    }


def write_qwen_report(json_output: Path = DEFAULT_JSON, markdown_output: Path = DEFAULT_MD) -> dict[str, Any]:
    report = collect_qwen_asr_env_status()
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")
    return report


def render_markdown(report: dict[str, Any]) -> str:
    python = report.get("python") or {}
    modules = report.get("modules") or {}
    model_init = report.get("model_init") or {}
    lines = [
        "# Qwen-ASR 环境检查报告",
        "",
        "> 本报告用于 v0.5.4。它只记录 Qwen-ASR 依赖和初始化状态，不评价模型效果。",
        "",
        "## Python",
        "",
        "| 项目 | 值 |",
        "| --- | --- |",
        f"| 当前 Python | {_cell(python.get('implementation'))} {_cell(python.get('version'))} |",
        f"| 可执行文件 | {_cell(python.get('executable_name'))} |",
        f"| 执行路径 | `{_cell(python.get('executable_path'))}` |",
        f"| 环境前缀 | `{_cell(python.get('prefix'))}` |",
        f"| Qwen 建议隔离环境 | Python {_cell(python.get('recommended_for_qwen'))} |",
        f"| 是否 Python 3.12 | {_bool_cell(python.get('matches_recommended_version'))} |",
        f"| 是否 `.venv-qwen-asr` | {_bool_cell(python.get('inside_qwen_venv'))} |",
        "",
        "## 依赖状态",
        "",
        "| 依赖 | 状态 | 版本/错误 |",
        "| --- | --- | --- |",
    ]
    for name in ["nagisa", "qwen_asr"]:
        item = modules.get(name) or {}
        lines.append(f"| {name} | {_bool_cell(item.get('available'))} | {_cell(item.get('version') or item.get('error'))} |")

    lines.extend(
        [
            "",
            "## 初始化检查",
            "",
            "| 项目 | 值 |",
            "| --- | --- |",
            f"| 状态 | {_cell(model_init.get('status'))} |",
            f"| 说明 | {_cell(model_init.get('message'))} |",
            "",
            "## 建议",
            "",
            f"- {report.get('recommendation')}",
            "",
        ]
    )
    return "\n".join(lines)


def _module_info(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    info: dict[str, Any] = {"available": spec is not None, "version": None}
    if spec is None:
        return info
    try:
        module = __import__(module_name)
        info["version"] = getattr(module, "__version__", None)
    except Exception as exc:  # noqa: BLE001 - import failure is the diagnostic target.
        info["available"] = False
        info["error"] = _sanitize_local_paths(str(exc))[:300]
    return info


def _check_qwen_model_init(qwen_available: bool) -> dict[str, str]:
    if not qwen_available:
        return {"status": "skipped", "message": "qwen_asr import failed or package is missing"}
    try:
        from qwen_asr import Qwen3ASRModel

        model_id = os.environ.get("QWEN3_ASR_MODEL_ID", "Qwen/Qwen3-ASR-0.6B")
        message = f"Qwen3ASRModel import ok; model loading not attempted for {model_id}"
        return {"status": "import_ok", "message": message}
    except Exception as exc:  # noqa: BLE001 - keep diagnostic non-fatal.
        return {"status": "import_failed", "message": _sanitize_local_paths(str(exc))[:300]}


def _recommendation(
    nagisa: dict[str, Any],
    qwen_asr: dict[str, Any],
    model_init: dict[str, str],
    python_info: dict[str, Any],
) -> str:
    combined_error = " ".join(
        str(item.get("error") or item.get("message") or "")
        for item in [nagisa, qwen_asr, model_init]
    )
    if "nagisa_v001.model" in combined_error:
        if python_info.get("matches_recommended_version") and python_info.get("inside_qwen_venv"):
            return "已在 `.venv-qwen-asr` Python 3.12 中复现 `nagisa_v001.model` 读取失败；下一步应定位 `nagisa/qwen-asr` 包兼容性、模型文件权限或上游包缺陷，不再把问题归因于 Python 版本。"
        return "当前是 `nagisa_v001.model` 读取失败，重装后若仍失败，应创建 `.venv-qwen-asr` Python 3.12 隔离环境再复测。"
    if not nagisa.get("available"):
        return "优先在 `.venv-asr` 中重装 `nagisa`，若仍失败则创建 `.venv-qwen-asr` Python 3.12 隔离环境。"
    if not qwen_asr.get("available"):
        return "优先重装 `qwen-asr`，并确认与当前 Python 和依赖版本兼容。"
    if model_init.get("status") != "import_ok":
        return "Qwen-ASR 包已安装但初始化失败，建议创建 `.venv-qwen-asr` Python 3.12 并单独复测。"
    return "Qwen-ASR 基础导入已通过，可进入模型下载和真实转写复测。"


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
    parser = argparse.ArgumentParser(description="Check Qwen-ASR environment.")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()

    report = write_qwen_report(args.json_output, args.markdown_output)
    print("Qwen-ASR 环境检查完成：")
    print(f"- nagisa: {report['modules']['nagisa']['available']}")
    print(f"- qwen_asr: {report['modules']['qwen_asr']['available']}")
    print(f"- model_init: {report['model_init']['status']}")
    print(f"- report: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
