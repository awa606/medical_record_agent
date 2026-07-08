"""Run Qwen3-ASR course medical benchmark one sample per subprocess.

Qwen3-ASR can exit the Python process on long CPU-only samples. This wrapper
keeps each sample isolated so one crash does not discard the whole benchmark.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.run_local_asr_benchmark import CSV_FIELDS, _audio_duration_seconds  # noqa: E402
from scripts.summarize_asr_benchmark import summarize_benchmark  # noqa: E402


DEFAULT_RUNTIME_DIR = Path(os.environ.get("QWEN_ASCII_RUNTIME_DIR", r"C:\mra_qwen_runtime"))
DEFAULT_AUDIO_DIR = DEFAULT_RUNTIME_DIR / "course_medical_cn" / "audio"
DEFAULT_TRUTH_DIR = DEFAULT_RUNTIME_DIR / "course_medical_cn" / "ground_truth"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_5_6_cn_medical_compare" / "qwen3"
DEFAULT_SAMPLE_IDS = ["snakebite_01", "fever_01", "chest_pain_01"]
RUN_JSON_NAME = "qwen3_split_run.json"
RUN_MD_NAME = "qwen3_split_run.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run Qwen3-ASR benchmark one sample at a time.")
    parser.add_argument("--sample-ids", nargs="+", default=DEFAULT_SAMPLE_IDS)
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--truth-dir", type=Path, default=DEFAULT_TRUTH_DIR)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--timeout-seconds", type=int, default=2400)
    parser.add_argument("--python-executable", type=Path, default=Path(sys.executable))
    parser.add_argument("--keep-staging", action="store_true")
    return parser.parse_args()


def run_split_benchmark(
    *,
    sample_ids: list[str],
    audio_dir: Path,
    truth_dir: Path,
    reports_dir: Path,
    timeout_seconds: int = 2400,
    python_executable: Path = Path(sys.executable),
    keep_staging: bool = False,
) -> dict[str, Any]:
    reports_dir.mkdir(parents=True, exist_ok=True)
    staging_root = reports_dir / "_staging"
    sample_reports_dir = reports_dir / "samples"
    sample_reports_dir.mkdir(parents=True, exist_ok=True)
    staging_root.mkdir(parents=True, exist_ok=True)

    samples = [
        _run_one_sample_subprocess(
            sample_id=sample_id,
            audio_dir=audio_dir,
            truth_dir=truth_dir,
            reports_dir=reports_dir,
            sample_reports_dir=sample_reports_dir,
            staging_root=staging_root,
            timeout_seconds=timeout_seconds,
            python_executable=python_executable,
        )
        for sample_id in sample_ids
    ]

    merged_rows = _merge_sample_rows(samples, reports_dir, audio_dir, truth_dir)
    _write_csv(reports_dir / "qwen3_report.csv", merged_rows)
    run_summary = {
        "schema_version": "v0.5.7",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "engine": "qwen3",
        "mode": "strict",
        "evaluation_profile": "course_medical_cn",
        "audio_dir": _display_path(audio_dir),
        "truth_dir": _display_path(truth_dir),
        "reports_dir": _display_path(reports_dir),
        "sample_count": len(sample_ids),
        "samples": samples,
        "rows": len([row for row in merged_rows if row.get("status") == "measured"]),
        "failed_samples": len([row for row in merged_rows if row.get("status") == "failed"]),
    }
    _write_json(reports_dir / RUN_JSON_NAME, run_summary)
    (reports_dir / RUN_MD_NAME).write_text(render_split_markdown(run_summary), encoding="utf-8")
    try:
        summarize_benchmark(reports_dir, reports_dir / "local_model_benchmark.md")
    finally:
        if not keep_staging:
            _cleanup_staging(staging_root)
    return run_summary


def render_split_markdown(run_summary: dict[str, Any]) -> str:
    lines = [
        "# Qwen3-ASR 分样本评测记录",
        "",
        "> 本记录用于 v0.5.7。每条样本在独立子进程中运行，长音频崩溃时保留已完成样本和失败原因。",
        "",
        "## 运行信息",
        "",
        f"- 生成时间：{run_summary.get('generated_at')}",
        f"- 音频目录：`{run_summary.get('audio_dir')}`",
        f"- 标注目录：`{run_summary.get('truth_dir')}`",
        f"- 报告目录：`{run_summary.get('reports_dir')}`",
        f"- 样本数量：{run_summary.get('sample_count')}",
        f"- 成功样本：{run_summary.get('rows')}",
        f"- 失败样本：{run_summary.get('failed_samples')}",
        "",
        "## 样本状态",
        "",
        "| 样本 | 状态 | 退出码 | 耗时秒 | 报告 | 错误 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for sample in run_summary.get("samples", []):
        lines.append(
            "| {sample} | {status} | {code} | {elapsed} | {report} | {error} |".format(
                sample=_cell(sample.get("sample_id")),
                status=_cell(sample.get("status")),
                code=_cell(sample.get("returncode")),
                elapsed=_cell(sample.get("elapsed_seconds")),
                report=f"`{sample.get('report_file')}`" if sample.get("report_file") else "-",
                error=_cell(sample.get("error")),
            )
        )
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- `measured` 表示该样本完成同口径 CER、关键词召回、RTF、CPU/RSS 记录。",
            "- `failed` 表示子进程异常退出、超时或没有生成可合并 CSV，不代表 Qwen3-ASR 模型效果差。",
            "- 长音频失败时，优先记录资源与稳定性问题，后续再评估切片策略或 GPU/边缘端部署。",
            "",
        ]
    )
    return "\n".join(lines)


def _run_one_sample_subprocess(
    *,
    sample_id: str,
    audio_dir: Path,
    truth_dir: Path,
    reports_dir: Path,
    sample_reports_dir: Path,
    staging_root: Path,
    timeout_seconds: int,
    python_executable: Path,
) -> dict[str, Any]:
    sample_dir = sample_reports_dir / sample_id
    sample_dir.mkdir(parents=True, exist_ok=True)
    staging_audio_dir = staging_root / sample_id / "audio"
    staging_truth_dir = staging_root / sample_id / "ground_truth"
    staging_audio_dir.mkdir(parents=True, exist_ok=True)
    staging_truth_dir.mkdir(parents=True, exist_ok=True)

    audio_path = _find_audio(audio_dir, sample_id)
    truth_path = truth_dir / f"{sample_id}.txt"
    child_report_file = sample_dir / "qwen3_report.csv"
    sample_report_file = sample_dir / f"{sample_id}_qwen3_sample.csv"
    stdout_path = sample_dir / "stdout.txt"
    stderr_path = sample_dir / "stderr.txt"
    if audio_path is None:
        error = f"missing audio for sample: {sample_id}"
        _write_text(stdout_path, "")
        _write_text(stderr_path, error)
        return _failed_sample(sample_id, None, 0.0, error, audio_path, truth_path, reports_dir, stdout_path, stderr_path)
    if not truth_path.exists():
        error = f"missing ground truth: {truth_path.name}"
        _write_text(stdout_path, "")
        _write_text(stderr_path, error)
        return _failed_sample(sample_id, None, 0.0, error, audio_path, truth_path, reports_dir, stdout_path, stderr_path)

    _link_or_copy(audio_path, staging_audio_dir / audio_path.name)
    _link_or_copy(truth_path, staging_truth_dir / truth_path.name)

    command = [
        str(python_executable),
        str(PROJECT_ROOT / "scripts" / "run_local_asr_benchmark.py"),
        "--engines",
        "qwen3",
        "--mode",
        "strict",
        "--evaluation-profile",
        "course_medical_cn",
        "--audio-dir",
        str(staging_audio_dir),
        "--truth-dir",
        str(staging_truth_dir),
        "--reports-dir",
        str(sample_dir),
    ]
    env = _qwen_env()
    started_at = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            cwd=str(PROJECT_ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
        elapsed = round(time.perf_counter() - started_at, 3)
        _write_text(stdout_path, completed.stdout or "")
        _write_text(stderr_path, completed.stderr or "")
        if completed.returncode != 0:
            error = f"qwen3 subprocess exited with code {completed.returncode}"
            return _failed_sample(
                sample_id,
                completed.returncode,
                elapsed,
                error,
                audio_path,
                truth_path,
                reports_dir,
                stdout_path,
                stderr_path,
            )
    except subprocess.TimeoutExpired as exc:
        elapsed = round(time.perf_counter() - started_at, 3)
        _write_text(stdout_path, _decode_timeout_output(exc.stdout))
        _write_text(stderr_path, _decode_timeout_output(exc.stderr) + f"\nTimeout after {timeout_seconds} seconds")
        error = f"qwen3 subprocess timed out after {timeout_seconds} seconds"
        return _failed_sample(sample_id, None, elapsed, error, audio_path, truth_path, reports_dir, stdout_path, stderr_path)

    rows = _read_rows(child_report_file)
    if not rows:
        error = "qwen3 subprocess completed but no CSV rows were generated"
        return _failed_sample(sample_id, 0, elapsed, error, audio_path, truth_path, reports_dir, stdout_path, stderr_path)
    _replace_file(child_report_file, sample_report_file)
    status = "measured" if any(row.get("status") == "measured" for row in rows) else rows[0].get("status", "failed")
    return {
        "sample_id": sample_id,
        "status": status,
        "returncode": 0,
        "elapsed_seconds": elapsed,
        "report_file": _relative_to_reports(sample_report_file, reports_dir),
        "stdout_file": _relative_to_reports(stdout_path, reports_dir),
        "stderr_file": _relative_to_reports(stderr_path, reports_dir),
        "error": rows[0].get("error", ""),
    }


def _merge_sample_rows(
    samples: list[dict[str, Any]],
    reports_dir: Path,
    audio_dir: Path,
    truth_dir: Path,
) -> list[dict[str, object]]:
    merged: list[dict[str, object]] = []
    for sample in samples:
        report_file = sample.get("report_file")
        if report_file:
            rows = _read_rows(reports_dir / str(report_file))
            if rows:
                merged.extend(rows)
                continue
        merged.append(_failure_row_from_sample(sample, audio_dir, truth_dir))
    return merged


def _failure_row_from_sample(sample: dict[str, Any], audio_dir: Path, truth_dir: Path) -> dict[str, object]:
    sample_id = str(sample.get("sample_id") or "unknown")
    audio_path = _find_audio(audio_dir, sample_id)
    duration = _audio_duration_seconds(audio_path) if audio_path else ""
    return {
        field: ""
        for field in CSV_FIELDS
    } | {
        "filename": f"{sample_id}.wav",
        "engine": "qwen3",
        "duration": duration or "",
        "status": "failed",
        "error": sample.get("error") or "qwen3 split sample failed",
        "ground_truth_available": (truth_dir / f"{sample_id}.txt").exists(),
    }


def _failed_sample(
    sample_id: str,
    returncode: int | None,
    elapsed_seconds: float,
    error: str,
    audio_path: Path | None,
    truth_path: Path,
    reports_dir: Path,
    stdout_path: Path,
    stderr_path: Path,
) -> dict[str, Any]:
    return {
        "sample_id": sample_id,
        "status": "failed",
        "returncode": returncode,
        "elapsed_seconds": elapsed_seconds,
        "report_file": None,
        "stdout_file": _relative_to_reports(stdout_path, reports_dir),
        "stderr_file": _relative_to_reports(stderr_path, reports_dir),
        "error": error,
        "audio_exists": audio_path is not None,
        "truth_exists": truth_path.exists(),
    }


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        return list(csv.DictReader(csv_file))


def _write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _find_audio(audio_dir: Path, sample_id: str) -> Path | None:
    for suffix in [".wav", ".mp3", ".flac", ".m4a", ".ogg"]:
        candidate = audio_dir / f"{sample_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _link_or_copy(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        return
    try:
        os.link(source, target)
    except OSError:
        import shutil

        shutil.copy2(source, target)


def _cleanup_staging(staging_root: Path) -> None:
    import shutil

    resolved = staging_root.resolve()
    if resolved.name != "_staging":
        raise RuntimeError(f"refusing to remove unexpected staging directory: {resolved}")
    if staging_root.exists():
        shutil.rmtree(staging_root, ignore_errors=True)


def _replace_file(source: Path, target: Path) -> None:
    if target.exists():
        target.unlink()
    source.replace(target)


def _qwen_env() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("HF_HOME", str(DEFAULT_RUNTIME_DIR / "model_cache"))
    env.setdefault("MODELSCOPE_CACHE", str(DEFAULT_RUNTIME_DIR / "model_cache" / "modelscope"))
    env.setdefault("QWEN3_ASR_DEVICE", "cpu")
    return env


def _decode_timeout_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _relative_to_reports(path: Path, reports_dir: Path) -> str:
    try:
        return path.relative_to(reports_dir).as_posix()
    except ValueError:
        return path.name


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|").replace("\n", " ")


def main() -> int:
    args = parse_args()
    summary = run_split_benchmark(
        sample_ids=args.sample_ids,
        audio_dir=args.audio_dir,
        truth_dir=args.truth_dir,
        reports_dir=args.reports_dir,
        timeout_seconds=args.timeout_seconds,
        python_executable=args.python_executable,
        keep_staging=args.keep_staging,
    )
    print("Qwen3-ASR 分样本评测完成：")
    for sample in summary["samples"]:
        print(f"- {sample['sample_id']}: {sample['status']} ({sample.get('error') or 'ok'})")
    print(f"- merged CSV: {args.reports_dir / 'qwen3_report.csv'}")
    print(f"- run report: {args.reports_dir / RUN_MD_NAME}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
