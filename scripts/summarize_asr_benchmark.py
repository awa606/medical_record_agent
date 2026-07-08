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
    hardware_path = _report_input_path(reports_dir, "hardware_profile.json")
    run_status_path = reports_dir / RUN_STATUS_FILE
    hardware = _load_json(hardware_path) if hardware_path.exists() else {}
    runtime_profiles = _load_runtime_profiles(reports_dir, hardware_path)
    run_status = _load_json(run_status_path) if run_status_path.exists() else {}
    csv_reports = sorted(reports_dir.rglob("*_report.csv"))
    engines = [_summarize_csv(path, reports_dir) for path in csv_reports]
    summary = {
        "hardware_profile": hardware,
        "runtime_profiles": runtime_profiles,
        "run_status": run_status,
        "csv_reports": [_relative_report_path(path, reports_dir) for path in csv_reports],
        "engines": engines,
        "status": _benchmark_status(hardware, engines, run_status),
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_markdown(summary), encoding="utf-8")
    return summary


def _report_input_path(reports_dir: Path, filename: str) -> Path:
    local_path = reports_dir / filename
    if local_path.exists():
        return local_path
    parent_path = reports_dir.parent / filename
    return parent_path if parent_path.exists() else local_path


def _load_runtime_profiles(reports_dir: Path, primary_hardware_path: Path) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    primary = primary_hardware_path.resolve() if primary_hardware_path.exists() else None
    for path in sorted(reports_dir.rglob("hardware_profile.json")):
        if primary is not None and path.resolve() == primary:
            continue
        data = _load_json(path)
        data["report_file"] = _relative_report_path(path, reports_dir)
        profiles.append(data)
    return profiles


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
        "> 本报告用于 v0.5.7 中文医患样本多模型 ASR 对比与 Qwen3 补测。当前结果只代表本机开发基线，不代表医院电脑或边缘端最终性能。",
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
        _dependency_row("Whisper", dependencies.get("whisper")),
        _dependency_row("ffmpeg", dependencies.get("ffmpeg")),
        f"| Ollama CLI | {_bool_cell((dependencies.get('ollama_cli') or {}).get('available'))} | 只检查命令是否存在，不调用服务 |",
        "",
        "## 额外运行环境",
        "",
        "| 报告 | Python | FunASR | Qwen-ASR | Whisper | CUDA | 说明 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    runtime_profiles = summary.get("runtime_profiles") or []
    if runtime_profiles:
        for profile in runtime_profiles:
            lines.append(_runtime_profile_row(profile))
    else:
        lines.append("| 无 | - | - | - | - | - | 未发现子目录硬件档案 |")

    lines.extend(
        [
            "",
            "## 多引擎运行状态",
            "",
            f"- 运行模式：`{run_status.get('mode', 'strict')}`",
            f"- 评测分层：`{run_status.get('evaluation_profile', '未记录')}`",
            f"- 分层说明：{_cell(run_status.get('evaluation_policy'))}",
            "",
            "| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |",
            "| --- | --- | --- | ---: | ---: | --- |",
        ]
    )
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
            "| 报告 | 引擎 | 成功样本 | Smoke 样本 | 失败样本 | 平均 CER | 平均关键词召回 | 平均耗时秒 | 平均 RTF | 平均 CPU% | 标准化 CPU% | 峰值 RSS MB | 状态 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    engines = summary.get("engines") or []
    if engines:
        for item in engines:
            lines.append(
                "| {report} | {engine} | {samples} | {smoke} | {failed} | {cer} | {recall} | {time} | {rtf} | {cpu} | {cpu_norm} | {rss} | {status} |".format(
                    report=item["report_file"],
                    engine=item["engine"],
                    samples=item["sample_count"],
                    smoke=item["smoke_count"],
                    failed=item["failed_count"],
                    cer=_number_cell(item["avg_cer"]),
                    recall=_number_cell(item["avg_keyword_recall"]),
                    time=_number_cell(item["avg_inference_time"]),
                    rtf=_number_cell(item["avg_realtime_factor"]),
                    cpu=_number_cell(item["avg_cpu_process_percent"]),
                    cpu_norm=_number_cell(item["avg_cpu_normalized_percent"]),
                    rss=_number_cell(item["max_rss_peak_mb"]),
                    status=item["status"],
                )
            )
    else:
        lines.append("| 无 | 待评测 | 0 | 0 | 0 | - | - | - | - | - | - | - | no_csv_reports |")

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
            "- 修复 `skipped` 引擎的系统依赖、Python 包导入、模型下载或资源问题后复跑，不把环境阻塞写成模型效果差。",
            "- 当前已实测引擎继续作为本机开发 baseline，最终选型必须等待医院 PC 或边缘端复测。",
            "",
        ]
    )
    return "\n".join(lines)


def _summarize_csv(path: Path, reports_dir: Path) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    report_file = _relative_report_path(path, reports_dir)
    if not rows:
        return {
            "report_file": report_file,
            "engine": "unknown",
            "sample_count": 0,
            "smoke_count": 0,
            "failed_count": 0,
            "avg_cer": None,
            "avg_keyword_recall": None,
            "avg_inference_time": None,
            "avg_realtime_factor": None,
            "avg_cpu_process_percent": None,
            "avg_cpu_normalized_percent": None,
            "max_rss_peak_mb": None,
            "status": "no_rows",
        }
    measured_rows = [
        row for row in rows if (row.get("status") or "measured") == "measured"
    ]
    smoke_rows = [row for row in rows if row.get("status") == "smoke_measured"]
    success_rows = measured_rows + smoke_rows
    failed_rows = [row for row in rows if row.get("status") == "failed"]
    metric_rows = success_rows or rows
    measured_metric_rows = measured_rows or []
    return {
        "report_file": report_file,
        "engine": (success_rows[0] if success_rows else rows[0]).get("engine") or "unknown",
        "sample_count": len(success_rows),
        "smoke_count": len(smoke_rows),
        "failed_count": len(failed_rows),
        "avg_cer": _average(measured_metric_rows, "cer"),
        "avg_keyword_recall": _average(measured_metric_rows, "keyword_recall"),
        "avg_inference_time": _average(metric_rows, "inference_time"),
        "avg_realtime_factor": _average(metric_rows, "realtime_factor"),
        "avg_cpu_process_percent": _average(metric_rows, "cpu_process_percent"),
        "avg_cpu_normalized_percent": _average(metric_rows, "cpu_normalized_percent"),
        "max_rss_peak_mb": _maximum(metric_rows, "rss_peak_mb"),
        "status": _csv_status(measured_rows, smoke_rows, failed_rows),
    }


def _average(rows: list[dict[str, str]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row.get(key) or ""))
        except ValueError:
            continue
    return round(mean(values), 6) if values else None


def _maximum(rows: list[dict[str, str]], key: str) -> float | None:
    values: list[float] = []
    for row in rows:
        try:
            values.append(float(row.get(key) or ""))
        except ValueError:
            continue
    return round(max(values), 6) if values else None


def _relative_report_path(path: Path, reports_dir: Path) -> str:
    try:
        return path.relative_to(reports_dir).as_posix()
    except ValueError:
        return path.name


def _csv_status(
    measured_rows: list[dict[str, str]],
    smoke_rows: list[dict[str, str]],
    failed_rows: list[dict[str, str]],
) -> str:
    if measured_rows and smoke_rows and failed_rows:
        return "measured_with_smoke_and_failed_samples"
    if measured_rows and smoke_rows:
        return "measured_with_smoke"
    if smoke_rows and failed_rows:
        return "smoke_measured_with_failed_samples"
    if measured_rows and failed_rows:
        return "measured_with_failed_samples"
    if measured_rows:
        return "measured"
    if smoke_rows:
        return "smoke_measured"
    if failed_rows:
        return "failed"
    return "no_rows"


def _benchmark_status(
    hardware: dict[str, Any],
    engines: list[dict[str, Any]],
    run_status: dict[str, Any] | None = None,
) -> str:
    measured = [item for item in engines if item.get("sample_count", 0) > 0]
    smoke_only = measured and all(item.get("status") == "smoke_measured" for item in measured)
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
    if smoke_only:
        return "smoke_measured"
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
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dependency_row(name: str, data: dict[str, Any] | None) -> str:
    data = data or {}
    status = _bool_cell(data.get("available"))
    version = data.get("version") or data.get("error") or "未检测到版本"
    if data.get("source"):
        version = f"{version}; source={data.get('source')}"
    return f"| {name} | {status} | {_cell(version)} |"


def _runtime_profile_row(profile: dict[str, Any]) -> str:
    dependencies = profile.get("dependencies") or {}
    python = profile.get("python") or {}
    gpu = profile.get("gpu") or {}
    report_file = profile.get("report_file") or "hardware_profile.json"
    python_value = f"{_cell(python.get('implementation'))} {_cell(python.get('version'))}"
    note = (profile.get("benchmark_status") or {}).get("current_machine_role") or "子目录运行环境"
    return (
        f"| `{report_file}` | {python_value} | "
        f"{_bool_cell((dependencies.get('funasr') or {}).get('available'))} | "
        f"{_bool_cell((dependencies.get('qwen_asr') or {}).get('available'))} | "
        f"{_bool_cell((dependencies.get('whisper') or {}).get('available'))} | "
        f"{_bool_cell(gpu.get('torch_cuda_available'))} | {_cell(note)} |"
    )


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
