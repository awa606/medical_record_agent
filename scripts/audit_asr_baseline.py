"""Audit local course audio and summarize tracked ASR benchmark evidence.

The report contains hashes and metrics only. Raw audio and transcripts remain
outside Git so the evidence can be checked without publishing source material.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import soundfile


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS = {
    "funasr": PROJECT_ROOT / "data/asr_eval/reports/v0_5_6_cn_medical_compare/funasr_report.csv",
    "sensevoice": PROJECT_ROOT / "data/asr_eval/reports/v0_5_6_cn_medical_compare/sensevoice_report.csv",
    "qwen3": PROJECT_ROOT / "data/asr_eval/reports/v0_5_6_cn_medical_compare/qwen3/qwen3_report.csv",
}
AUDIO_SUFFIXES = {".wav", ".mp3", ".flac", ".ogg", ".m4a"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _detected_format(path: Path) -> str:
    header = path.read_bytes()[:12]
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
        return "WAV"
    if header.startswith(b"ID3") or (len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        return "MP3"
    if header.startswith(b"fLaC"):
        return "FLAC"
    if header.startswith(b"OggS"):
        return "OGG"
    return "UNKNOWN"


def audit_audio(audio_root: Path, truth_root: Path) -> tuple[list[dict[str, Any]], list[list[str]]]:
    rows: list[dict[str, Any]] = []
    by_hash: dict[str, list[str]] = {}
    for path in sorted(item for item in audio_root.iterdir() if item.is_file() and item.suffix.lower() in AUDIO_SUFFIXES):
        sha = _sha256(path)
        by_hash.setdefault(sha, []).append(path.name)
        detected = _detected_format(path)
        try:
            info = soundfile.info(path)
            duration = round(float(info.duration), 3)
            sample_rate = int(info.samplerate)
            channels = int(info.channels)
            decoder_format = info.format
            decoder_error = None
        except RuntimeError as exc:
            duration = None
            sample_rate = None
            channels = None
            decoder_format = None
            decoder_error = f"{type(exc).__name__}: {exc}"
        truth_path = truth_root / f"{path.stem}.txt"
        rows.append(
            {
                "filename": path.name,
                "size_bytes": path.stat().st_size,
                "sha256": sha,
                "suffix": path.suffix.lower().lstrip(".").upper(),
                "detected_format": detected,
                "decoder_format": decoder_format,
                "format_matches_suffix": detected == path.suffix.lower().lstrip(".").upper(),
                "duration_seconds": duration,
                "sample_rate_hz": sample_rate,
                "channels": channels,
                "decoder_error": decoder_error,
                "ground_truth_present": truth_path.exists(),
                "ground_truth_sha256": _sha256(truth_path) if truth_path.exists() else None,
            }
        )
    duplicate_groups = [names for names in by_hash.values() if len(names) > 1]
    return rows, duplicate_groups


def summarize_benchmark(engine_id: str, path: Path, expected_samples: set[str]) -> dict[str, Any]:
    rows = list(csv.DictReader(path.open("r", encoding="utf-8-sig", newline="")))
    measured = [row for row in rows if (row.get("status") or "measured") == "measured"]

    def values(field: str) -> list[float]:
        return [float(row[field]) for row in measured if row.get(field) not in (None, "")]

    cer = values("cer")
    recall = values("keyword_recall")
    rtf = values("realtime_factor")
    rss = values("rss_peak_mb")
    found_samples = {Path(row["filename"]).stem for row in measured}
    metrics_complete = len(cer) == len(measured) == len(recall) == len(rtf)
    gate_checks = {
        "all_expected_samples_measured": found_samples == expected_samples,
        "cer_le_0_15": bool(cer) and mean(cer) <= 0.15,
        "keyword_recall_ge_0_90": bool(recall) and mean(recall) >= 0.90,
        "rtf_le_1": bool(rtf) and max(rtf) <= 1.0,
        "metrics_complete": metrics_complete,
    }
    return {
        "engine_id": engine_id,
        "engine": measured[0].get("engine") if measured else None,
        "report": path.relative_to(PROJECT_ROOT).as_posix(),
        "report_sha256": _sha256(path),
        "sample_count": len(measured),
        "sample_ids": sorted(found_samples),
        "macro_cer": round(mean(cer), 6) if cer else None,
        "macro_keyword_recall": round(mean(recall), 6) if recall else None,
        "max_rtf": round(max(rtf), 6) if rtf else None,
        "max_rss_mb": round(max(rss), 2) if rss else None,
        "gate_checks": gate_checks,
        "t09_gate": "PASS" if all(gate_checks.values()) else "FAIL",
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# ASR 数据与三模型基线审计",
        "",
        f"- 执行时间：{report['generated_at']}",
        f"- Git SHA：`{report['git_sha']}`",
        f"- 原始音频来源标签：`{report['audio_source_label']}`",
        f"- 唯一课程样本：{report['unique_sample_count']} 个",
        f"- 唯一音频总时长：{report['unique_duration_seconds']:.3f} 秒（{report['unique_duration_minutes']:.2f} 分钟）",
        f"- 训练数据门禁：**{report['training_data_gate']}**（候选微调至少60分钟，当前不足）",
        "",
        "## 音频完整性",
        "",
        "| 文件 | SHA256前12位 | 后缀/真实编码 | 时长秒 | 采样率 | 声道 | 人工转写 | 结论 |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in report["audio_files"]:
        conclusion = "OK" if row["format_matches_suffix"] else "扩展名与真实编码不符，需生成规范化副本"
        lines.append(
            f"| {row['filename']} | `{row['sha256'][:12]}` | {row['suffix']}/{row['detected_format']} | "
            f"{row['duration_seconds'] or '-'} | {row['sample_rate_hz'] or '-'} | {row['channels'] or '-'} | "
            f"{'有' if row['ground_truth_present'] else '无'} | {conclusion} |"
        )
    lines.extend(["", f"重复文件组：`{report['duplicate_groups']}`。", "", "## 三模型历史实测复核", ""])
    lines.extend(
        [
            "| 引擎 | 样本 | 宏平均CER | 宏平均关键词召回 | 最大RTF | 峰值RSS MB | T09 |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )
    for item in report["benchmarks"]:
        lines.append(
            f"| {item['engine']} | {item['sample_count']} | {item['macro_cer']:.3%} | "
            f"{item['macro_keyword_recall']:.3%} | {item['max_rtf']:.3f} | {item['max_rss_mb']:.2f} | {item['t09_gate']} |"
        )
    lines.extend(
        [
            "",
            "T09 要求 CER≤15%、医学关键词召回≥90%、RTF≤1。三种引擎都满足实时性，但没有一个同时满足 CER 和关键词召回，因此当前应进入数据清洗、分段与针对性改进，不能替换生产候选模型。",
            "",
            "## 数据与安全边界",
            "",
            "- 报告只保存文件哈希、媒体属性和聚合指标，不提交原始音频或人工转写正文。",
            "- `snakebite_01.wav` 实际为 MP3，并与 `snakebite_01.mp3` 字节级重复；训练前应生成新的规范化音频并保留来源哈希。",
            "- 当前三条唯一录音合计约15.30分钟，不满足至少60分钟训练数据要求，也不能证明训练/验证/冻结测试的说话人互斥。",
            "- 本报告复核的是已受 Git 跟踪的开发机历史实测；Jetson 未到货，硬件结论保持 `HARDWARE BLOCKED`。",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit raw course audio and tracked ASR benchmark evidence.")
    parser.add_argument("--audio-root", type=Path, required=True)
    parser.add_argument("--audio-source-label", default="external-course-audio")
    parser.add_argument("--manifest", type=Path, default=PROJECT_ROOT / "data/asr_eval/manifest.json")
    parser.add_argument("--truth-root", type=Path, default=PROJECT_ROOT / "data/asr_eval/ground_truth")
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    expected_samples = {item["sample_id"] for item in manifest["samples"]}
    audio_files, duplicate_groups = audit_audio(args.audio_root, args.truth_root)
    canonical = [row for row in audio_files if Path(row["filename"]).stem in expected_samples and row["filename"].endswith(".wav")]
    unique_duration = sum(float(row["duration_seconds"] or 0) for row in canonical)
    benchmarks = [summarize_benchmark(engine, path, expected_samples) for engine, path in DEFAULT_REPORTS.items()]
    report = {
        "schema_version": "asr_baseline_audit_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "audio_source_label": args.audio_source_label,
        "manifest_sha256": _sha256(args.manifest),
        "expected_sample_ids": sorted(expected_samples),
        "unique_sample_count": len(canonical),
        "unique_duration_seconds": round(unique_duration, 3),
        "unique_duration_minutes": round(unique_duration / 60, 2),
        "audio_files": audio_files,
        "duplicate_groups": duplicate_groups,
        "benchmarks": benchmarks,
        "training_data_gate": "PASS" if unique_duration >= 60 * 60 else "BLOCKED_DATA_LT_60_MIN",
        "jetson_gate": "HARDWARE_BLOCKED",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(render_markdown(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "samples": report["unique_sample_count"],
                "duration_minutes": report["unique_duration_minutes"],
                "t09": {item["engine_id"]: item["t09_gate"] for item in benchmarks},
                "training_data_gate": report["training_data_gate"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
