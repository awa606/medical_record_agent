"""Run local ASR benchmarks across available engines.

This script intentionally does not install dependencies or download model
weights. Each engine is evaluated independently so a missing optional model
dependency is recorded as a skipped engine instead of breaking the whole run.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.asr import (  # noqa: E402
    ASREvaluator,
    apply_manifest_role_strategy,
    create_asr_engine,
    load_asr_manifest,
)
from scripts.evaluate_asr import iter_audio_files, load_keywords  # noqa: E402
from scripts.summarize_asr_benchmark import summarize_benchmark  # noqa: E402


DEFAULT_ENGINES = ["mock", "funasr", "qwen3"]
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "asr_eval" / "audio"
DEFAULT_TRUTH_DIR = PROJECT_ROOT / "data" / "asr_eval" / "ground_truth"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports"
DEFAULT_KEYWORD_FILE = PROJECT_ROOT / "config" / "hotwords_medical.txt"
RUN_JSON_NAME = "local_asr_benchmark_run.json"
RUN_MD_NAME = "local_asr_benchmark_run.md"
SUMMARY_MD_NAME = "local_model_benchmark.md"

CSV_FIELDS = [
    "filename",
    "engine",
    "duration",
    "inference_time",
    "cer",
    "keyword_recall",
    "recognized_keywords",
    "missing_keywords",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local ASR benchmark engines.")
    parser.add_argument(
        "--engines",
        nargs="+",
        default=DEFAULT_ENGINES,
        help="Engines to evaluate. Supports space-separated or comma-separated values.",
    )
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--truth-dir", type=Path, default=DEFAULT_TRUTH_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--keyword-file", type=Path, default=DEFAULT_KEYWORD_FILE)
    return parser.parse_args()


def run_local_asr_benchmark(
    *,
    engines: list[str],
    audio_dir: Path,
    truth_dir: Path,
    reports_dir: Path,
    keyword_file: Path = DEFAULT_KEYWORD_FILE,
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    normalized_engines = _normalize_engines(engines)
    audio_files = iter_audio_files(audio_dir) if audio_dir.exists() else []
    keywords = load_keywords(keyword_file)
    manifest = load_asr_manifest()

    engine_results = [
        _run_one_engine(
            engine_name=engine_name,
            audio_files=audio_files,
            truth_dir=truth_dir,
            reports_dir=reports_dir,
            keywords=keywords,
            manifest=manifest,
        )
        for engine_name in normalized_engines
    ]

    run_summary = {
        "schema_version": "v0.5.1",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "audio_dir": _relative_or_name(audio_dir),
        "truth_dir": _relative_or_name(truth_dir),
        "reports_dir": _relative_or_name(reports_dir),
        "sample_count": len(audio_files),
        "engines": engine_results,
    }
    _write_json(reports_dir / RUN_JSON_NAME, run_summary)
    (reports_dir / RUN_MD_NAME).write_text(render_run_markdown(run_summary), encoding="utf-8")
    summarize_benchmark(reports_dir, reports_dir / SUMMARY_MD_NAME)
    return run_summary


def render_run_markdown(run_summary: dict[str, Any]) -> str:
    lines = [
        "# 本地 ASR 多引擎评测运行记录",
        "",
        "> 本记录用于 v0.5.1。它只说明哪些引擎在当前环境完成评测、哪些因依赖或配置缺失被跳过，不代表最终模型优劣。",
        "",
        "## 运行信息",
        "",
        f"- 生成时间：{run_summary.get('generated_at')}",
        f"- 音频目录：`{run_summary.get('audio_dir')}`",
        f"- 标注目录：`{run_summary.get('truth_dir')}`",
        f"- 样本数量：{run_summary.get('sample_count')}",
        "",
        "## 引擎状态",
        "",
        "| 引擎 | 状态 | 报告 | 样本数 | 失败样本 | 说明 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in run_summary.get("engines", []):
        lines.append(
            "| {engine} | {status} | {report} | {rows} | {failed} | {reason} |".format(
                engine=_cell(item.get("engine")),
                status=_cell(item.get("status")),
                report=f"`{item.get('report_file')}`" if item.get("report_file") else "-",
                rows=item.get("rows", 0),
                failed=item.get("failed_samples", 0),
                reason=_cell(item.get("reason")),
            )
        )

    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- `measured` 表示当前环境完成了该引擎评测并生成 CSV。",
            "- `skipped` 表示依赖、模型或配置缺失，本轮不评价该模型效果。",
            "- `failed` 表示引擎已创建，但样本转写全部失败，需要进入 Debug Log 分析。",
            "",
        ]
    )
    return "\n".join(lines)


def _run_one_engine(
    *,
    engine_name: str,
    audio_files: list[Path],
    truth_dir: Path,
    reports_dir: Path,
    keywords: list[str],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        engine = create_asr_engine(engine_name)
    except Exception as exc:  # noqa: BLE001 - optional engines fail through imports/config.
        return {
            "engine": engine_name,
            "status": "skipped",
            "reason": _compact_error(exc),
            "report_file": None,
            "rows": 0,
            "failed_samples": 0,
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        }

    rows: list[dict[str, object]] = []
    sample_errors: list[dict[str, str]] = []
    evaluator = ASREvaluator()
    report_path = reports_dir / f"{engine_name}_report.csv"

    for audio_path in audio_files:
        truth_path = truth_dir / f"{audio_path.stem}.txt"
        if not truth_path.exists():
            sample_errors.append(
                {
                    "filename": audio_path.name,
                    "reason": f"missing ground truth: {truth_path.name}",
                }
            )
            continue

        try:
            sample_started_at = time.perf_counter()
            result = engine.transcribe(audio_path.stem, audio_path)
            result = apply_manifest_role_strategy(result, audio_path.stem, manifest)
            inference_time = time.perf_counter() - sample_started_at
            sample = manifest.get(audio_path.stem) or {}
            expected_keywords = sample.get("expected_keywords") or keywords
            evaluation = evaluator.evaluate(
                audio_id=audio_path.stem,
                engine=result.engine,
                ground_truth_text=truth_path.read_text(encoding="utf-8"),
                recognized_text=result.text,
                expected_keywords=expected_keywords,
            )
        except Exception as exc:  # noqa: BLE001 - keep remaining engines/samples runnable.
            sample_errors.append({"filename": audio_path.name, "reason": _compact_error(exc)})
            continue

        rows.append(
            {
                "filename": audio_path.name,
                "engine": result.engine,
                "duration": result.duration,
                "inference_time": round(inference_time, 3),
                "cer": round(evaluation.cer, 6),
                "keyword_recall": round(evaluation.keyword_recall, 6),
                "recognized_keywords": "|".join(evaluation.medical_keywords["recognized"]),
                "missing_keywords": "|".join(evaluation.medical_keywords["missing"]),
            }
        )

    _write_csv(report_path, rows)
    status = _engine_status(rows, sample_errors, audio_files)
    return {
        "engine": engine_name,
        "engine_output": rows[0]["engine"] if rows else getattr(engine, "name", engine_name),
        "status": status,
        "reason": _engine_reason(status, rows, sample_errors, audio_files),
        "report_file": report_path.name,
        "rows": len(rows),
        "failed_samples": len(sample_errors),
        "sample_errors": sample_errors,
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
    }


def _normalize_engines(values: list[str]) -> list[str]:
    engines: list[str] = []
    for value in values:
        for item in value.split(","):
            engine = item.strip().lower()
            if engine and engine not in engines:
                engines.append(engine)
    return engines or list(DEFAULT_ENGINES)


def _engine_status(
    rows: list[dict[str, object]],
    sample_errors: list[dict[str, str]],
    audio_files: list[Path],
) -> str:
    if rows:
        return "measured_with_warnings" if sample_errors else "measured"
    if not audio_files:
        return "no_samples"
    if sample_errors:
        return "failed"
    return "no_rows"


def _engine_reason(
    status: str,
    rows: list[dict[str, object]],
    sample_errors: list[dict[str, str]],
    audio_files: list[Path],
) -> str:
    if status == "measured":
        return "completed"
    if status == "measured_with_warnings":
        return "completed with skipped or failed samples"
    if status == "no_samples":
        return "no audio files found"
    if status == "failed" and sample_errors:
        return sample_errors[0]["reason"]
    if not rows and audio_files:
        return "no successful rows"
    return status


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_or_name(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return path.name


def _compact_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    return message or exc.__class__.__name__


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def main() -> int:
    args = parse_args()
    summary = run_local_asr_benchmark(
        engines=args.engines,
        audio_dir=args.audio_dir,
        truth_dir=args.truth_dir,
        reports_dir=args.reports_dir,
        keyword_file=args.keyword_file,
    )
    print("本地 ASR 多引擎评测完成：")
    for item in summary["engines"]:
        print(f"- {item['engine']}: {item['status']} ({item['reason']})")
    print(f"- run report: {args.reports_dir / RUN_MD_NAME}")
    print(f"- summary: {args.reports_dir / SUMMARY_MD_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
