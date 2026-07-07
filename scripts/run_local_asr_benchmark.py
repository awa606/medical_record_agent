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
import tracemalloc
import wave
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


DEFAULT_ENGINES = ["mock", "funasr", "sensevoice", "whisper", "qwen3"]
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "asr_eval" / "audio"
DEFAULT_TRUTH_DIR = PROJECT_ROOT / "data" / "asr_eval" / "ground_truth"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports"
DEFAULT_KEYWORD_FILE = PROJECT_ROOT / "config" / "hotwords_medical.txt"
RUN_JSON_NAME = "local_asr_benchmark_run.json"
RUN_MD_NAME = "local_asr_benchmark_run.md"
SUMMARY_MD_NAME = "local_model_benchmark.md"
SUFFIX_PRIORITY = {".wav": 0, ".mp3": 1, ".flac": 2, ".m4a": 3, ".ogg": 4}

CSV_FIELDS = [
    "filename",
    "engine",
    "duration",
    "status",
    "error",
    "ground_truth_available",
    "transcript_non_empty",
    "segments",
    "model_load_time",
    "inference_time",
    "realtime_factor",
    "peak_memory_mb",
    "gpu_memory_mb",
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
    parser.add_argument(
        "--mode",
        choices=["strict", "smoke"],
        default="strict",
        help="strict requires ground truth; smoke allows transcription-only samples.",
    )
    parser.add_argument(
        "--evaluation-profile",
        choices=["auto", "course_medical_cn", "public_cn_smoke", "public_en_smoke", "mixed_public_smoke"],
        default="auto",
        help="Evaluation profile used in reports. auto infers from the audio directory.",
    )
    return parser.parse_args()


def run_local_asr_benchmark(
    *,
    engines: list[str],
    audio_dir: Path,
    truth_dir: Path,
    reports_dir: Path,
    keyword_file: Path = DEFAULT_KEYWORD_FILE,
    mode: str = "strict",
    evaluation_profile: str = "auto",
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    normalized_engines = _normalize_engines(engines)
    audio_files = benchmark_audio_files(audio_dir) if audio_dir.exists() else []
    keywords = load_keywords(keyword_file)
    manifest = load_asr_manifest()
    resolved_profile = _resolve_evaluation_profile(evaluation_profile, audio_dir)

    engine_results = [
        _run_one_engine(
            engine_name=engine_name,
            audio_files=audio_files,
            truth_dir=truth_dir,
            reports_dir=reports_dir,
            keywords=keywords,
            manifest=manifest,
            mode=mode,
        )
        for engine_name in normalized_engines
    ]

    run_summary = {
        "schema_version": "v0.5.4",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "evaluation_profile": resolved_profile["profile"],
        "evaluation_policy": resolved_profile["policy"],
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


def benchmark_audio_files(audio_dir: Path) -> list[Path]:
    by_stem: dict[str, Path] = {}
    for path in iter_audio_files(audio_dir):
        existing = by_stem.get(path.stem)
        if existing is None or _suffix_rank(path) < _suffix_rank(existing):
            by_stem[path.stem] = path
    return sorted(by_stem.values(), key=lambda item: item.stem)


def render_run_markdown(run_summary: dict[str, Any]) -> str:
    lines = [
        "# 本地 ASR 多引擎评测运行记录",
        "",
        "> 本记录用于 v0.5.4。它只说明哪些引擎在当前环境完成评测、哪些因依赖或配置缺失被跳过，不代表最终模型优劣。",
        "",
        "## 运行信息",
        "",
        f"- 生成时间：{run_summary.get('generated_at')}",
        f"- 音频目录：`{run_summary.get('audio_dir')}`",
        f"- 标注目录：`{run_summary.get('truth_dir')}`",
        f"- 模式：`{run_summary.get('mode', 'strict')}`",
        f"- 评测分层：`{run_summary.get('evaluation_profile', 'auto')}`",
        f"- 分层说明：{run_summary.get('evaluation_policy', '-')}",
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
            "- `smoke_measured` 表示无标注样本完成转写，只用于可用性冒烟测试。",
            "- `skipped` 表示依赖、模型或配置缺失，本轮不评价该模型效果。",
            "- `failed` 表示引擎已创建，但样本转写全部失败，需要进入 Debug Log 分析。",
            "- `course_medical_cn` 是中文医患主评测；`public_en_smoke` 只用于可选多语种冒烟验证。",
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
    mode: str,
) -> dict[str, Any]:
    started_at = time.perf_counter()
    try:
        create_started_at = time.perf_counter()
        engine = create_asr_engine(engine_name)
        model_load_time = getattr(
            engine,
            "model_load_time_seconds",
            round(time.perf_counter() - create_started_at, 3),
        )
    except Exception as exc:  # noqa: BLE001 - optional engines fail through imports/config.
        return {
            "engine": engine_name,
            "status": "skipped",
            "reason": _compact_error(exc),
            "report_file": None,
            "rows": 0,
            "failed_samples": 0,
            "model_load_time": None,
            "elapsed_seconds": round(time.perf_counter() - started_at, 3),
        }

    rows: list[dict[str, object]] = []
    sample_errors: list[dict[str, str]] = []
    evaluator = ASREvaluator()
    report_path = reports_dir / f"{engine_name}_report.csv"

    for audio_path in audio_files:
        truth_path = truth_dir / f"{audio_path.stem}.txt"
        truth_exists = truth_path.exists()
        if not truth_exists and mode == "strict":
            reason = f"missing ground truth: {truth_path.name}"
            sample_errors.append({"filename": audio_path.name, "reason": reason})
            rows.append(_failed_row(audio_path.name, getattr(engine, "name", engine_name), reason, model_load_time, False))
            continue

        peak_memory_mb: float | None = None
        gpu_memory_mb: float | None = None
        try:
            sample_started_at = time.perf_counter()
            tracemalloc.start()
            _reset_gpu_peak_memory()
            result = engine.transcribe(audio_path.stem, audio_path)
            result = apply_manifest_role_strategy(result, audio_path.stem, manifest)
            inference_time = time.perf_counter() - sample_started_at
            duration = _result_or_file_duration(result.duration, audio_path)
            peak_memory_mb = _current_peak_memory_mb()
            gpu_memory_mb = _gpu_peak_memory_mb()
            sample = manifest.get(audio_path.stem) or {}
            expected_keywords = sample.get("expected_keywords") or keywords
            evaluation = None
            if truth_exists:
                evaluation = evaluator.evaluate(
                    audio_id=audio_path.stem,
                    engine=result.engine,
                    ground_truth_text=truth_path.read_text(encoding="utf-8"),
                    recognized_text=result.text,
                    expected_keywords=expected_keywords if mode == "strict" else [],
                )
        except Exception as exc:  # noqa: BLE001 - keep remaining engines/samples runnable.
            reason = _compact_error(exc)
            sample_errors.append({"filename": audio_path.name, "reason": reason})
            rows.append(_failed_row(audio_path.name, getattr(engine, "name", engine_name), reason, model_load_time, truth_exists))
            if tracemalloc.is_tracing():
                tracemalloc.stop()
            continue
        finally:
            if tracemalloc.is_tracing():
                tracemalloc.stop()

        rows.append(
            {
                "filename": audio_path.name,
                "engine": result.engine,
                "duration": duration,
                "status": "measured" if truth_exists else "smoke_measured",
                "error": "",
                "ground_truth_available": truth_exists,
                "transcript_non_empty": bool(result.text.strip()),
                "segments": len(result.segments),
                "model_load_time": model_load_time,
                "inference_time": round(inference_time, 3),
                "realtime_factor": _realtime_factor(inference_time, duration),
                "peak_memory_mb": peak_memory_mb,
                "gpu_memory_mb": gpu_memory_mb,
                "cer": round(evaluation.cer, 6) if evaluation else "",
                "keyword_recall": round(evaluation.keyword_recall, 6) if evaluation else "",
                "recognized_keywords": "|".join(evaluation.medical_keywords["recognized"]) if evaluation else "",
                "missing_keywords": "|".join(evaluation.medical_keywords["missing"]) if evaluation else "",
            }
        )

    _write_csv(report_path, rows)
    measured_rows = [row for row in rows if _is_success_status(row.get("status"))]
    status = _engine_status(rows, sample_errors, audio_files)
    return {
        "engine": engine_name,
        "engine_output": measured_rows[0]["engine"] if measured_rows else getattr(engine, "name", engine_name),
        "status": status,
        "reason": _engine_reason(status, rows, sample_errors, audio_files),
        "report_file": report_path.name,
        "rows": len(measured_rows),
        "failed_samples": len(sample_errors),
        "sample_errors": sample_errors,
        "model_load_time": model_load_time,
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


def _resolve_evaluation_profile(profile: str, audio_dir: Path) -> dict[str, str]:
    normalized = (profile or "auto").strip().lower()
    if normalized == "auto":
        normalized_path = str(audio_dir).replace("\\", "/").lower()
        if "/video" in normalized_path or normalized_path.endswith("video"):
            normalized = "course_medical_cn"
        elif "public_smoke" in normalized_path:
            normalized = "mixed_public_smoke"
        else:
            normalized = "course_medical_cn"

    policies = {
        "course_medical_cn": "三条课程中文医患样本，是本项目 ASR 主评测，可用于医学关键词和流程效果分析。",
        "public_cn_smoke": "中文公开非医疗样本，只验证中文 ASR 可用性，不用于医学结论。",
        "public_en_smoke": "英文公开非医疗样本，只验证多语种/Whisper/ffmpeg 冒烟链路，不进入中文医患主结论。",
        "mixed_public_smoke": "公开 smoke 混合集；中文样本只作可用性辅助，英文样本只作可选多语种冒烟。",
    }
    return {"profile": normalized, "policy": policies.get(normalized, "未定义评测分层")}


def _suffix_rank(path: Path) -> int:
    return SUFFIX_PRIORITY.get(path.suffix.lower(), 100)


def _engine_status(
    rows: list[dict[str, object]],
    sample_errors: list[dict[str, str]],
    audio_files: list[Path],
) -> str:
    measured_rows = [row for row in rows if _is_success_status(row.get("status"))]
    if measured_rows:
        if all(row.get("status") == "smoke_measured" for row in measured_rows):
            return "smoke_measured_with_warnings" if sample_errors else "smoke_measured"
        if any(row.get("status") == "smoke_measured" for row in measured_rows):
            return "measured_with_smoke_and_warnings" if sample_errors else "measured_with_smoke"
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
    if status == "smoke_measured":
        return "completed smoke transcription without ground truth"
    if status == "measured_with_smoke":
        return "completed with measured and smoke-only samples"
    if status == "smoke_measured_with_warnings":
        return "completed smoke transcription with skipped or failed samples"
    if status == "measured_with_smoke_and_warnings":
        return "completed with measured, smoke-only, and failed samples"
    if status == "measured_with_warnings":
        return "completed with skipped or failed samples"
    if status == "no_samples":
        return "no audio files found"
    if status == "failed" and sample_errors:
        return sample_errors[0]["reason"]
    measured_rows = [row for row in rows if _is_success_status(row.get("status"))]
    if not measured_rows and audio_files:
        return "no successful rows"
    return status


def _failed_row(
    filename: str,
    engine: str,
    error: str,
    model_load_time: float | None,
    ground_truth_available: bool,
) -> dict[str, object]:
    return {
        "filename": filename,
        "engine": engine,
        "duration": "",
        "status": "failed",
        "error": error,
        "ground_truth_available": ground_truth_available,
        "transcript_non_empty": "",
        "segments": "",
        "model_load_time": model_load_time,
        "inference_time": "",
        "realtime_factor": "",
        "peak_memory_mb": "",
        "gpu_memory_mb": "",
        "cer": "",
        "keyword_recall": "",
        "recognized_keywords": "",
        "missing_keywords": "",
    }


def _is_success_status(status: object) -> bool:
    return status in {"measured", "smoke_measured"}


def _realtime_factor(inference_time: float, duration: float | None) -> float | str:
    if not duration or duration <= 0:
        return ""
    return round(inference_time / duration, 6)


def _result_or_file_duration(result_duration: float | None, audio_path: Path) -> float | None:
    if result_duration and result_duration > 0:
        return result_duration
    return _audio_duration_seconds(audio_path)


def _audio_duration_seconds(audio_path: Path) -> float | None:
    try:
        import soundfile as sf

        info = sf.info(str(audio_path))
        if info.duration and info.duration > 0:
            return round(float(info.duration), 3)
    except Exception:
        pass

    try:
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            sample_rate = wav_file.getframerate()
        if sample_rate > 0:
            return round(frames / float(sample_rate), 3)
    except Exception:
        return None
    return None


def _current_peak_memory_mb() -> float | None:
    if not tracemalloc.is_tracing():
        return None
    _current, peak = tracemalloc.get_traced_memory()
    return round(peak / (1024 * 1024), 2)


def _reset_gpu_peak_memory() -> None:
    try:
        import torch

        if torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
    except Exception:
        return


def _gpu_peak_memory_mb() -> float | None:
    try:
        import torch

        if torch.cuda.is_available():
            return round(torch.cuda.max_memory_allocated() / (1024 * 1024), 2)
    except Exception:
        return None
    return None


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
    message = _sanitize_local_paths(str(exc)).replace("\n", " ").strip()
    return message or exc.__class__.__name__


def _sanitize_local_paths(value: str) -> str:
    root = str(PROJECT_ROOT)
    return value.replace(root, "<PROJECT_ROOT>").replace(root.replace("\\", "/"), "<PROJECT_ROOT>")


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
        mode=args.mode,
        evaluation_profile=args.evaluation_profile,
    )
    print("本地 ASR 多引擎评测完成：")
    for item in summary["engines"]:
        print(f"- {item['engine']}: {item['status']} ({item['reason']})")
    print(f"- run report: {args.reports_dir / RUN_MD_NAME}")
    print(f"- summary: {args.reports_dir / SUMMARY_MD_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
