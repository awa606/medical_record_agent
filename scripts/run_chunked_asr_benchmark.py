"""Run chunked long-audio ASR benchmarks.

This runner wraps existing ASR engines without changing the ASREngine
interface. It splits each long audio file into fixed-size WAV chunks, runs the
selected engine on each chunk, merges the result, and records per-chunk status
for stability debugging.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import tempfile
import time
import tracemalloc
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.asr import (  # noqa: E402
    ASREvaluator,
    ChunkTranscription,
    apply_manifest_role_strategy,
    create_asr_engine,
    load_asr_manifest,
    merge_chunk_transcriptions,
    split_audio_to_chunks,
)
from scripts.evaluate_asr import load_keywords  # noqa: E402
from scripts.run_local_asr_benchmark import (  # noqa: E402
    CSV_FIELDS,
    DEFAULT_KEYWORD_FILE,
    _ResourceSampler,
    _audio_duration_seconds,
    _compact_error,
    _current_peak_memory_mb,
    _empty_resource_metrics,
    _gpu_peak_memory_mb,
    _normalize_engines,
    _realtime_factor,
    _reset_gpu_peak_memory,
    benchmark_audio_files,
)
from scripts.summarize_asr_benchmark import summarize_benchmark  # noqa: E402


DEFAULT_ENGINES = ["sensevoice", "funasr"]
DEFAULT_AUDIO_DIR = PROJECT_ROOT / "data" / "asr_eval" / "long_audio_stability" / "audio"
DEFAULT_TRUTH_DIR = PROJECT_ROOT / "data" / "asr_eval" / "long_audio_stability" / "ground_truth"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_5_9_chunked_long_audio"
RUN_JSON_NAME = "chunked_asr_benchmark_run.json"
RUN_MD_NAME = "chunked_asr_benchmark_run.md"
SUMMARY_MD_NAME = "local_model_benchmark.md"
CHUNK_STATUS_DIR_NAME = "chunk_status"
CHUNKED_CSV_FIELDS = CSV_FIELDS + [
    "chunk_seconds",
    "chunk_count",
    "failed_chunks",
    "chunk_status_file",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run chunked long-audio ASR benchmarks.")
    parser.add_argument("--engines", nargs="+", default=DEFAULT_ENGINES)
    parser.add_argument("--chunk-seconds", type=int, default=300)
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--truth-dir", type=Path, default=DEFAULT_TRUTH_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--keyword-file", type=Path, default=DEFAULT_KEYWORD_FILE)
    parser.add_argument("--mode", choices=["strict", "smoke"], default="strict")
    parser.add_argument(
        "--evaluation-profile",
        choices=["course_medical_cn", "public_cn_smoke", "public_en_smoke", "mixed_public_smoke"],
        default="course_medical_cn",
    )
    return parser.parse_args()


def run_chunked_asr_benchmark(
    *,
    engines: list[str],
    audio_dir: Path,
    truth_dir: Path,
    reports_dir: Path,
    keyword_file: Path = DEFAULT_KEYWORD_FILE,
    mode: str = "strict",
    evaluation_profile: str = "course_medical_cn",
    chunk_seconds: int = 300,
) -> dict[str, Any]:
    if chunk_seconds <= 0:
        raise ValueError("chunk_seconds must be positive")

    reports_dir.mkdir(parents=True, exist_ok=True)
    chunk_status_dir = reports_dir / CHUNK_STATUS_DIR_NAME
    chunk_status_dir.mkdir(parents=True, exist_ok=True)
    audio_files = benchmark_audio_files(audio_dir) if audio_dir.exists() else []
    keywords = load_keywords(keyword_file)
    manifest = load_asr_manifest()
    engine_results = [
        _run_one_engine(
            engine_name=engine_name,
            audio_files=audio_files,
            truth_dir=truth_dir,
            reports_dir=reports_dir,
            chunk_status_dir=chunk_status_dir,
            keywords=keywords,
            manifest=manifest,
            mode=mode,
            chunk_seconds=chunk_seconds,
        )
        for engine_name in _normalize_engines(engines)
    ]

    run_summary = {
        "schema_version": "v0.5.9",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": mode,
        "evaluation_profile": evaluation_profile,
        "evaluation_policy": (
            "16/30 分钟课程中文医患拼接样本，仅用于长音频稳定性、资源占用和切片恢复验证。"
        ),
        "audio_dir": _relative_or_name(audio_dir),
        "truth_dir": _relative_or_name(truth_dir),
        "reports_dir": _relative_or_name(reports_dir),
        "chunk_seconds": chunk_seconds,
        "sample_count": len(audio_files),
        "engines": engine_results,
    }
    _write_json(reports_dir / RUN_JSON_NAME, run_summary)
    (reports_dir / RUN_MD_NAME).write_text(render_run_markdown(run_summary), encoding="utf-8")
    summarize_benchmark(reports_dir, reports_dir / SUMMARY_MD_NAME)
    return run_summary


def render_run_markdown(run_summary: dict[str, Any]) -> str:
    lines = [
        "# v0.5.9 长音频切片 ASR 评测运行记录",
        "",
        "> 本记录用于验证 16/30 分钟中文医患拼接音频在切片转写后的稳定性。该结果只代表当前开发机，不代表医院 PC 最终性能。",
        "",
        "## 运行信息",
        "",
        f"- 生成时间：{run_summary.get('generated_at')}",
        f"- 音频目录：`{run_summary.get('audio_dir')}`",
        f"- 标注目录：`{run_summary.get('truth_dir')}`",
        f"- 切片时长：`{run_summary.get('chunk_seconds')}` 秒",
        f"- 样本数量：{run_summary.get('sample_count')}",
        f"- 模式：`{run_summary.get('mode')}`",
        "",
        "## 引擎状态",
        "",
        "| 引擎 | 状态 | 报告 | 成功样本 | 失败样本 | 说明 |",
        "| --- | --- | --- | ---: | ---: | --- |",
    ]
    for item in run_summary.get("engines", []):
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

    lines.extend(
        [
            "",
            "## 判读边界",
            "",
            "- `measured` 表示所有切片均转写并合并成功，且有人工标注可计算 CER。",
            "- `failed` 表示至少一个样本没有得到完整合并结果；具体失败切片见 `chunk_status/` JSON。",
            "- 切片结果用于稳定性验证，不改变默认 ASR 模型，也不证明医学诊断正确性。",
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
    chunk_status_dir: Path,
    keywords: list[str],
    manifest: dict[str, Any],
    mode: str,
    chunk_seconds: int,
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
    except Exception as exc:  # noqa: BLE001
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
    report_path = reports_dir / f"{engine_name}_chunked_report.csv"

    for audio_path in audio_files:
        truth_path = truth_dir / f"{audio_path.stem}.txt"
        truth_exists = truth_path.exists()
        if not truth_exists and mode == "strict":
            reason = f"missing ground truth: {truth_path.name}"
            sample_errors.append({"filename": audio_path.name, "reason": reason})
            rows.append(
                _failed_row(
                    filename=audio_path.name,
                    engine=getattr(engine, "name", engine_name),
                    error=reason,
                    model_load_time=model_load_time,
                    ground_truth_available=False,
                    chunk_seconds=chunk_seconds,
                    chunk_count=0,
                    failed_chunks=0,
                    chunk_status_file="",
                )
            )
            continue

        row, chunk_status = _run_one_sample(
            engine=engine,
            engine_name=engine_name,
            audio_path=audio_path,
            truth_path=truth_path,
            truth_exists=truth_exists,
            keywords=keywords,
            manifest=manifest,
            evaluator=evaluator,
            model_load_time=model_load_time,
            chunk_seconds=chunk_seconds,
        )
        chunk_status_file = chunk_status_dir / f"{engine_name}_{audio_path.stem}_chunks.json"
        _write_json(chunk_status_file, chunk_status)
        row["chunk_status_file"] = _relative_report_path(chunk_status_file, reports_dir)
        rows.append(row)
        if row.get("status") == "failed":
            sample_errors.append({"filename": audio_path.name, "reason": str(row.get("error") or "failed")})

    _write_csv(report_path, rows)
    success_rows = [row for row in rows if row.get("status") in {"measured", "smoke_measured"}]
    status = _engine_status(success_rows, sample_errors, audio_files)
    return {
        "engine": engine_name,
        "engine_output": success_rows[0]["engine"] if success_rows else getattr(engine, "name", engine_name),
        "status": status,
        "reason": _engine_reason(status, sample_errors, audio_files),
        "report_file": report_path.name,
        "rows": len(success_rows),
        "failed_samples": len(sample_errors),
        "sample_errors": sample_errors,
        "model_load_time": model_load_time,
        "elapsed_seconds": round(time.perf_counter() - started_at, 3),
    }


def _run_one_sample(
    *,
    engine: Any,
    engine_name: str,
    audio_path: Path,
    truth_path: Path,
    truth_exists: bool,
    keywords: list[str],
    manifest: dict[str, Any],
    evaluator: ASREvaluator,
    model_load_time: float | None,
    chunk_seconds: int,
) -> tuple[dict[str, object], dict[str, Any]]:
    chunk_records: list[dict[str, Any]] = []
    resource_metrics = _empty_resource_metrics()
    peak_memory_mb: float | None = None
    gpu_memory_mb: float | None = None
    sample_started_at = time.perf_counter()
    original_duration = _audio_duration_seconds(audio_path)

    try:
        with tempfile.TemporaryDirectory(prefix=f"{audio_path.stem}_chunks_") as temp_dir_name:
            temp_dir = Path(temp_dir_name)
            tracemalloc.start()
            _reset_gpu_peak_memory()
            with _ResourceSampler() as resource_sampler:
                chunks = split_audio_to_chunks(audio_path, temp_dir, chunk_seconds=chunk_seconds)
                transcriptions: list[ChunkTranscription] = []
                for chunk in chunks:
                    chunk_started_at = time.perf_counter()
                    record: dict[str, Any] = {
                        "index": chunk.index,
                        "path": chunk.path.name,
                        "start_seconds": chunk.start_seconds,
                        "duration_seconds": chunk.duration_seconds,
                    }
                    try:
                        result = engine.transcribe(f"{audio_path.stem}_chunk_{chunk.index:03d}", chunk.path)
                        transcriptions.append(ChunkTranscription(chunk=chunk, result=result))
                        record.update(
                            {
                                "status": "measured",
                                "engine": result.engine,
                                "segments": len(result.segments),
                                "text_length": len(result.text),
                                "elapsed_seconds": round(time.perf_counter() - chunk_started_at, 3),
                            }
                        )
                    except Exception as exc:  # noqa: BLE001
                        record.update(
                            {
                                "status": "failed",
                                "error": _compact_error(exc),
                                "elapsed_seconds": round(time.perf_counter() - chunk_started_at, 3),
                            }
                        )
                    chunk_records.append(record)
                failed_chunks = [record for record in chunk_records if record.get("status") == "failed"]
                if failed_chunks:
                    raise RuntimeError(
                        f"{len(failed_chunks)} chunk(s) failed; first: {failed_chunks[0].get('error')}"
                    )
                merged = merge_chunk_transcriptions(
                    audio_path.stem,
                    transcriptions,
                    original_duration=original_duration,
                    engine_name=f"{getattr(engine, 'name', engine_name)}-chunked",
                )
                merged = apply_manifest_role_strategy(merged, audio_path.stem, manifest)
            inference_time = time.perf_counter() - sample_started_at
            peak_memory_mb = _current_peak_memory_mb()
            gpu_memory_mb = _gpu_peak_memory_mb()
            resource_metrics = resource_sampler.metrics(inference_time)
    except Exception as exc:  # noqa: BLE001
        if tracemalloc.is_tracing():
            tracemalloc.stop()
        row = _failed_row(
            filename=audio_path.name,
            engine=getattr(engine, "name", engine_name),
            error=_compact_error(exc),
            model_load_time=model_load_time,
            ground_truth_available=truth_exists,
            chunk_seconds=chunk_seconds,
            chunk_count=len(chunk_records),
            failed_chunks=len([record for record in chunk_records if record.get("status") == "failed"]),
            chunk_status_file="",
        )
        return row, _chunk_status_payload(audio_path, chunk_seconds, chunk_records, row)
    finally:
        if tracemalloc.is_tracing():
            tracemalloc.stop()

    sample = manifest.get(audio_path.stem) or {}
    expected_keywords = sample.get("expected_keywords") or keywords
    evaluation = None
    if truth_exists:
        evaluation = evaluator.evaluate(
            audio_id=audio_path.stem,
            engine=merged.engine,
            ground_truth_text=truth_path.read_text(encoding="utf-8"),
            recognized_text=merged.text,
            expected_keywords=expected_keywords if truth_exists else [],
        )

    row = {
        "filename": audio_path.name,
        "engine": merged.engine,
        "duration": original_duration or merged.duration or "",
        "status": "measured" if truth_exists else "smoke_measured",
        "error": "",
        "ground_truth_available": truth_exists,
        "transcript_non_empty": bool(merged.text.strip()),
        "segments": len(merged.segments),
        "model_load_time": model_load_time,
        "inference_time": round(inference_time, 3),
        "realtime_factor": _realtime_factor(inference_time, original_duration or merged.duration),
        "peak_memory_mb": peak_memory_mb,
        "gpu_memory_mb": gpu_memory_mb,
        **resource_metrics,
        "cer": round(evaluation.cer, 6) if evaluation else "",
        "keyword_recall": round(evaluation.keyword_recall, 6) if evaluation else "",
        "recognized_keywords": "|".join(evaluation.medical_keywords["recognized"]) if evaluation else "",
        "missing_keywords": "|".join(evaluation.medical_keywords["missing"]) if evaluation else "",
        "chunk_seconds": chunk_seconds,
        "chunk_count": len(chunk_records),
        "failed_chunks": 0,
        "chunk_status_file": "",
    }
    return row, _chunk_status_payload(audio_path, chunk_seconds, chunk_records, row)


def _chunk_status_payload(
    audio_path: Path,
    chunk_seconds: int,
    chunk_records: list[dict[str, Any]],
    row: dict[str, object],
) -> dict[str, Any]:
    return {
        "schema_version": "v0.5.9",
        "audio_file": audio_path.name,
        "chunk_seconds": chunk_seconds,
        "chunk_count": len(chunk_records),
        "failed_chunks": len([record for record in chunk_records if record.get("status") == "failed"]),
        "sample_status": row.get("status"),
        "sample_error": row.get("error"),
        "chunks": chunk_records,
    }


def _failed_row(
    *,
    filename: str,
    engine: str,
    error: str,
    model_load_time: float | None,
    ground_truth_available: bool,
    chunk_seconds: int,
    chunk_count: int,
    failed_chunks: int,
    chunk_status_file: str,
) -> dict[str, object]:
    row = {
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
        "rss_start_mb": "",
        "rss_peak_mb": "",
        "rss_delta_mb": "",
        "cpu_time_seconds": "",
        "cpu_process_percent": "",
        "cpu_normalized_percent": "",
        "cer": "",
        "keyword_recall": "",
        "recognized_keywords": "",
        "missing_keywords": "",
        "chunk_seconds": chunk_seconds,
        "chunk_count": chunk_count,
        "failed_chunks": failed_chunks,
        "chunk_status_file": chunk_status_file,
    }
    return row


def _engine_status(
    success_rows: list[dict[str, object]],
    sample_errors: list[dict[str, str]],
    audio_files: list[Path],
) -> str:
    if success_rows and sample_errors:
        return "measured_with_warnings"
    if success_rows:
        return "measured"
    if not audio_files:
        return "no_samples"
    if sample_errors:
        return "failed"
    return "no_rows"


def _engine_reason(status: str, sample_errors: list[dict[str, str]], audio_files: list[Path]) -> str:
    if status == "measured":
        return "all chunked samples completed"
    if status == "measured_with_warnings":
        return "some samples completed, some failed"
    if status == "no_samples":
        return "no audio files found"
    if sample_errors:
        return sample_errors[0]["reason"]
    if audio_files:
        return "no successful rows"
    return status


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CHUNKED_CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _relative_or_name(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _relative_report_path(path: Path, reports_dir: Path) -> str:
    try:
        return path.relative_to(reports_dir).as_posix()
    except ValueError:
        return path.name


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def main() -> int:
    args = parse_args()
    summary = run_chunked_asr_benchmark(
        engines=args.engines,
        chunk_seconds=args.chunk_seconds,
        audio_dir=args.audio_dir,
        truth_dir=args.truth_dir,
        reports_dir=args.reports_dir,
        keyword_file=args.keyword_file,
        mode=args.mode,
        evaluation_profile=args.evaluation_profile,
    )
    print("长音频切片 ASR 评测完成：")
    for item in summary["engines"]:
        print(f"- {item['engine']}: {item['status']} ({item['reason']})")
    print(f"- run report: {args.reports_dir / RUN_MD_NAME}")
    print(f"- summary: {args.reports_dir / SUMMARY_MD_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
