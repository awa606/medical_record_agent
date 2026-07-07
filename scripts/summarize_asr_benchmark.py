"""Summarize ASR benchmark CSV files and hardware profile into Markdown."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from statistics import mean
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports"
DEFAULT_OUTPUT = DEFAULT_REPORTS_DIR / "local_model_benchmark.md"
RUN_STATUS_FILE = "local_asr_benchmark_run.json"


def summarize_benchmark(
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    output_path: Path = DEFAULT_OUTPUT,
) -> dict[str, Any]:
    hardware_path = reports_dir / "hardware_profile.json"
    run_status_path = reports_dir / RUN_STATUS_FILE
    hardware = _load_json(hardware_path) if hardware_path.exists() else {}
    run_status = _load_json(run_status_path) if run_status_path.exists() else {}
    csv_reports = sorted(reports_dir.glob("*_report.csv"))
    engines = [_summarize_csv(path) for path in csv_reports]
    summary = {
        "hardware_profile": hardware,
        "run_status": run_status,
        "csv_reports": [str(path.name) for path in csv_reports],
        "engines": engines,
        "status": _benchmark_status(hardware, engines, run_status),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def render_markdown(summary: dict[str, Any]) -> str:
    hardware = summary.get("hardware_profile") or {}
    system = hardware.get("system") or {}
    python = hardware.get("python") or {}
    gpu = hardware.get("gpu") or {}
    dependencies = hardware.get("dependencies") or {}
    run_status = summary.get("run_status") or {}

    lines = [
        "# 本地模型与边缘端评测基线报告",
        "",
        "> 本报告用于 v0.5.1 评测框架验收。当前结果只代表本机开发基线，不代表医院电脑或边缘端最终性能。",
        "",
        "## 硬件配置",
        "",
        "| 项目 | 当前值 |",
        "| --- | --- |",
        f"| OS | {_cell(system.get('os'))} {_cell(system.get('os_release'))} |",
        f"| CPU 逻辑核心 | {_cell(system.get('cpu_logical_cores'))} |",
        f"| 内存 | {_cell(system.get('memory_total_gb'))} GB |",
        f"| Python | {_cell(python.get('implementation'))} {_cell(python.get('version'))} |",
        f"| CUDA 可用 | {_bool_cell(gpu.get('torch_cuda_available'))} |",
        f"| GPU 数量 | {_cell(gpu.get('cuda_device_count'))} |",
        "",
        "## 依赖状态",
        "",
        "| 依赖 | 状态 | 说明 |",
        "| --- | --- | --- |",
        _dependency_row("torch", dependencies.get("torch")),
        _dependency_row("FunASR", dependencies.get("funasr")),
        _dependency_row("Qwen-ASR", dependencies.get("qwen_asr")),
        f"| Ollama CLI | {_bool_cell((dependencies.get('ollama_cli') or {}).get('available'))} | 只检查命令是否存在，不调用服务 |",
        "",
        "## 多引擎运行状态",
        "",
        "| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    engine_runs = run_status.get("engines") or []
    if engine_runs:
        for item in engine_runs:
            report = f"`{item.get('report_file')}`" if item.get("report_file") else "-"
            lines.append(
                "| {engine} | {status} | {report} | {rows} | {failed} | {reason} |".format(
                    engine=_cell(item.get("engine")),
                    status=_cell(item.get("status")),
                    report=report,
                    rows=item.get("rows", 0),
                    failed=item.get("failed_samples", 0),
                    reason=_cell(item.get("reason")),
                )
            )
    else:
        lines.append("| 未运行 | no_run_status | - | 0 | 0 | 尚未生成多引擎运行记录 |")

    lines.extend(
        [
            "",
            "## ASR 评测结果",
            "",
            "| 报告 | 引擎 | 样本数 | 平均 CER | 平均关键词召回 | 平均耗时秒 | 状态 |",
            "| --- | --- | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    engines = summary.get("engines") or []
    if engines:
        for item in engines:
            lines.append(
                "| {report} | {engine} | {samples} | {cer} | {recall} | {time} | {status} |".format(
                    report=item["report_file"],
                    engine=item["engine"],
                    samples=item["sample_count"],
                    cer=_number_cell(item["avg_cer"]),
                    recall=_number_cell(item["avg_keyword_recall"]),
                    time=_number_cell(item["avg_inference_time"]),
                    status=item["status"],
                )
            )
    else:
        lines.append("| 无 | 待评测 | 0 | - | - | - | no_csv_reports |")

    lines.extend(
        [
            "",
            "## 结论",
            "",
            f"- 当前机器角色：{_cell((hardware.get('benchmark_status') or {}).get('current_machine_role'))}。",
            f"- 医院 PC 配置：{_cell((hardware.get('benchmark_status') or {}).get('hospital_pc_profile'))}。",
            f"- 边缘端配置：{_cell((hardware.get('benchmark_status') or {}).get('edge_device_profile'))}。",
            f"- 评测状态：{summary.get('status')}。",
            "",
            "## 后续动作",
            "",
            "- 在普通医院 Windows 办公 PC 上运行同一组命令，补充真实基线。",
            "- 安装 FunASR 或 Qwen3-ASR 后复跑对应引擎，不把依赖缺失写成模型效果差。",
            "- 进入 v0.5.2 后再比较 SenseVoice、Whisper 或多说话人分离路线。",
            "",
        ]
    )
    return "\n".join(lines)


def _summarize_csv(path: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    if not rows:
        return {
            "report_file": path.name,
            "engine": "unknown",
            "sample_count": 0,
            "avg_cer": None,
            "avg_keyword_recall": None,
            "avg_inference_time": None,
            "status": "no_rows",
        }
    return {
        "report_file": path.name,
        "engine": rows[0].get("engine") or "unknown",
        "sample_count": len(rows),
        "avg_cer": _average(rows, "cer"),
        "avg_keyword_recall": _average(rows, "keyword_recall"),
        "avg_inference_time": _average(rows, "inference_time"),
        "status": "measured",
    }


def _average(rows: list[dict[str, str]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row.get(key) or ""))
        except ValueError:
            continue
    return round(mean(values), 6) if values else None


def _benchmark_status(
    hardware: dict[str, Any],
    engines: list[dict[str, Any]],
    run_status: dict[str, Any] | None = None,
) -> str:
    measured = [item for item in engines if item.get("sample_count", 0) > 0]
    dependencies = hardware.get("dependencies") or {}
    run_engines = (run_status or {}).get("engines") or []
    skipped = [item for item in run_engines if item.get("status") == "skipped"]
    failed = [item for item in run_engines if item.get("status") == "failed"]
    real_engine_status = {
        item.get("engine"): item.get("status")
        for item in run_engines
        if item.get("engine") in {"funasr", "qwen3"}
    }
    run_real_asr_skipped = bool(real_engine_status) and all(
        status == "skipped" for status in real_engine_status.values()
    )
    missing_real_asr = not (dependencies.get("funasr") or {}).get("available") and not (
        dependencies.get("qwen_asr") or {}
    ).get("available")
    if measured and (missing_real_asr or run_real_asr_skipped):
        return "mock_measured_real_asr_dependency_missing"
    if measured and skipped:
        return "measured_with_skipped_optional_engines"
    if measured:
        return "measured"
    if failed:
        return "engine_failed_no_measured_rows"
    if skipped:
        return "framework_ready_engines_skipped"
    return "framework_ready_no_samples"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _dependency_row(name: str, data: dict[str, Any] | None) -> str:
    data = data or {}
    status = _bool_cell(data.get("available"))
    version = data.get("version") or data.get("error") or "未检测到版本"
    return f"| {name} | {status} | {_cell(version)} |"


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def _bool_cell(value: Any) -> str:
    return "可用" if bool(value) else "不可用"


def _number_cell(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize ASR benchmark reports.")
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    summary = summarize_benchmark(args.reports_dir, args.output)
    print("ASR 评测汇总完成：")
    print(f"- CSV reports: {len(summary['csv_reports'])}")
    print(f"- status: {summary['status']}")
    print(f"- output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
