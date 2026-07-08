"""Prepare synthetic long-audio samples for ASR stability tests.

The generated audio is for engineering stability only. It is built by
concatenating existing course sample audio and optional silence padding; it is
not evidence for real outpatient consultation duration or clinical accuracy.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE_AUDIO_DIR = PROJECT_ROOT / "video"
DEFAULT_SOURCE_TRUTH_DIR = PROJECT_ROOT / "data" / "asr_eval" / "ground_truth"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "data" / "asr_eval" / "long_audio_stability"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_5_8_long_audio_stability"
DEFAULT_QWEN_RUNTIME_DIR = Path(os.environ.get("QWEN_ASCII_RUNTIME_DIR", r"C:\mra_qwen_runtime"))
DEFAULT_SOURCE_IDS = ["fever_01", "chest_pain_01", "snakebite_01"]
DEFAULT_TARGETS = {
    "long_16min_course_cn": 16 * 60,
    "long_30min_course_cn": 30 * 60,
}
SUPPORTED_SUFFIXES = [".wav", ".mp3", ".flac", ".m4a", ".ogg"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare long ASR stability samples.")
    parser.add_argument("--source-audio-dir", type=Path, default=DEFAULT_SOURCE_AUDIO_DIR)
    parser.add_argument("--source-truth-dir", type=Path, default=DEFAULT_SOURCE_TRUTH_DIR)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--reports-dir", type=Path, default=DEFAULT_REPORTS_DIR)
    parser.add_argument("--source-ids", nargs="+", default=DEFAULT_SOURCE_IDS)
    parser.add_argument(
        "--target",
        action="append",
        default=[],
        help="Target in sample_id=seconds form. Defaults to 16min and 30min samples.",
    )
    parser.add_argument(
        "--qwen-runtime-dir",
        type=Path,
        default=DEFAULT_QWEN_RUNTIME_DIR / "long_audio_stability",
        help="ASCII runtime copy target for Qwen3-ASR. Use --no-qwen-copy to skip.",
    )
    parser.add_argument("--no-qwen-copy", action="store_true")
    parser.add_argument("--ffmpeg", type=Path, default=None)
    parser.add_argument("--ffprobe", type=Path, default=None)
    return parser.parse_args()


def prepare_long_audio_samples(
    *,
    source_audio_dir: Path = DEFAULT_SOURCE_AUDIO_DIR,
    source_truth_dir: Path = DEFAULT_SOURCE_TRUTH_DIR,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    reports_dir: Path = DEFAULT_REPORTS_DIR,
    source_ids: list[str] | None = None,
    targets: dict[str, int] | None = None,
    qwen_runtime_dir: Path | None = DEFAULT_QWEN_RUNTIME_DIR / "long_audio_stability",
    ffmpeg_path: Path | None = None,
    ffprobe_path: Path | None = None,
) -> dict[str, Any]:
    source_ids = source_ids or DEFAULT_SOURCE_IDS
    targets = targets or DEFAULT_TARGETS
    ffmpeg = resolve_binary("ffmpeg", ffmpeg_path)
    ffprobe = resolve_binary("ffprobe", ffprobe_path)
    audio_dir = output_root / "audio"
    truth_dir = output_root / "ground_truth"
    tmp_dir = output_root / "tmp"
    reports_dir.mkdir(parents=True, exist_ok=True)
    audio_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    for keep_dir in [audio_dir, truth_dir, tmp_dir]:
        (keep_dir / ".gitkeep").touch(exist_ok=True)

    sources = load_source_items(source_ids, source_audio_dir, source_truth_dir, ffprobe)
    samples: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(dir=tmp_dir) as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        normalized = normalize_sources(sources, temp_dir, ffmpeg)
        for sample_id, target_seconds in targets.items():
            plan = build_sample_plan(sources, target_seconds)
            output_audio = audio_dir / f"{sample_id}.wav"
            output_truth = truth_dir / f"{sample_id}.txt"
            materialize_sample(
                sample_id=sample_id,
                plan=plan,
                normalized_sources=normalized,
                output_audio=output_audio,
                output_truth=output_truth,
                temp_dir=temp_dir,
                ffmpeg=ffmpeg,
            )
            actual_seconds = probe_duration(output_audio, ffprobe)
            samples.append(
                {
                    "sample_id": sample_id,
                    "target_seconds": target_seconds,
                    "actual_seconds": round(actual_seconds, 3),
                    "audio_file": relative_or_name(output_audio),
                    "ground_truth_file": relative_or_name(output_truth),
                    "segments": [
                        {
                            "type": segment["type"],
                            "source_id": segment.get("source_id", ""),
                            "duration_seconds": round(float(segment["duration_seconds"]), 3),
                        }
                        for segment in plan
                    ],
                }
            )

    manifest = {
        "schema_version": "v0.5.8",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "synthetic course-sample long-audio stability test",
        "policy": (
            "The samples are concatenated from course demo audio and optional silence. "
            "They test ASR throughput, memory, CPU, and failure handling; they do not "
            "represent real consultation duration or clinical correctness."
        ),
        "source_audio_dir": relative_or_name(source_audio_dir),
        "source_truth_dir": relative_or_name(source_truth_dir),
        "sources": [
            {
                "sample_id": item["sample_id"],
                "audio_file": relative_or_name(item["audio_path"]),
                "truth_file": relative_or_name(item["truth_path"]),
                "duration_seconds": round(float(item["duration_seconds"]), 3),
            }
            for item in sources
        ],
        "samples": samples,
    }
    write_json(reports_dir / "long_audio_samples_manifest.json", manifest)
    (reports_dir / "long_audio_samples_manifest.md").write_text(
        render_manifest_markdown(manifest),
        encoding="utf-8",
    )
    if qwen_runtime_dir is not None:
        copy_for_qwen_runtime(qwen_runtime_dir, audio_dir, truth_dir)
        manifest["qwen_runtime_dir"] = str(qwen_runtime_dir)
        write_json(reports_dir / "long_audio_samples_manifest.json", manifest)
        (reports_dir / "long_audio_samples_manifest.md").write_text(
            render_manifest_markdown(manifest),
            encoding="utf-8",
        )
    return manifest


def parse_targets(values: list[str]) -> dict[str, int]:
    if not values:
        return dict(DEFAULT_TARGETS)
    targets: dict[str, int] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"target must use sample_id=seconds form: {value}")
        sample_id, seconds = value.split("=", 1)
        targets[sample_id.strip()] = int(seconds)
    return targets


def load_source_items(
    source_ids: list[str],
    source_audio_dir: Path,
    source_truth_dir: Path,
    ffprobe: Path,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for sample_id in source_ids:
        audio_path = find_audio(source_audio_dir, sample_id)
        truth_path = source_truth_dir / f"{sample_id}.txt"
        if audio_path is None:
            raise FileNotFoundError(f"missing source audio for {sample_id} in {source_audio_dir}")
        if not truth_path.exists():
            raise FileNotFoundError(f"missing source ground truth: {truth_path}")
        items.append(
            {
                "sample_id": sample_id,
                "audio_path": audio_path,
                "truth_path": truth_path,
                "truth_text": truth_path.read_text(encoding="utf-8").strip(),
                "duration_seconds": probe_duration(audio_path, ffprobe),
            }
        )
    return items


def build_sample_plan(source_items: list[dict[str, Any]], target_seconds: int) -> list[dict[str, Any]]:
    if target_seconds <= 0:
        raise ValueError("target_seconds must be positive")
    if not source_items:
        raise ValueError("source_items must not be empty")

    plan: list[dict[str, Any]] = []
    total = 0.0
    max_overshoot_seconds = 15.0
    while total < target_seconds:
        appended = False
        for item in source_items:
            duration = float(item["duration_seconds"])
            if total + duration <= target_seconds + max_overshoot_seconds:
                plan.append(
                    {
                        "type": "source",
                        "source_id": item["sample_id"],
                        "duration_seconds": duration,
                        "truth_text": item["truth_text"],
                    }
                )
                total += duration
                appended = True
                if total >= target_seconds:
                    return plan
            else:
                remaining = target_seconds - total
                if remaining > 1.0:
                    plan.append({"type": "silence", "duration_seconds": remaining, "truth_text": ""})
                    return plan
                return plan
        if not appended:
            remaining = target_seconds - total
            if remaining > 1.0:
                plan.append({"type": "silence", "duration_seconds": remaining, "truth_text": ""})
            return plan
    return plan


def normalize_sources(sources: list[dict[str, Any]], temp_dir: Path, ffmpeg: Path) -> dict[str, Path]:
    normalized: dict[str, Path] = {}
    for item in sources:
        output_path = temp_dir / f"{item['sample_id']}_normalized.wav"
        run_command(
            [
                str(ffmpeg),
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(item["audio_path"]),
                "-ac",
                "1",
                "-ar",
                "16000",
                "-sample_fmt",
                "s16",
                str(output_path),
            ]
        )
        normalized[item["sample_id"]] = output_path
    return normalized


def materialize_sample(
    *,
    sample_id: str,
    plan: list[dict[str, Any]],
    normalized_sources: dict[str, Path],
    output_audio: Path,
    output_truth: Path,
    temp_dir: Path,
    ffmpeg: Path,
) -> None:
    concat_paths: list[Path] = []
    truth_parts: list[str] = []
    silence_index = 0
    for index, segment in enumerate(plan, start=1):
        if segment["type"] == "source":
            source_id = str(segment["source_id"])
            concat_paths.append(normalized_sources[source_id])
            truth_text = str(segment.get("truth_text") or "").strip()
            if truth_text:
                truth_parts.append(truth_text)
        else:
            silence_index += 1
            silence_path = temp_dir / f"{sample_id}_silence_{silence_index}.wav"
            run_command(
                [
                    str(ffmpeg),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-f",
                    "lavfi",
                    "-i",
                    "anullsrc=r=16000:cl=mono",
                    "-t",
                    str(round(float(segment["duration_seconds"]), 3)),
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-sample_fmt",
                    "s16",
                    str(silence_path),
                ]
            )
            concat_paths.append(silence_path)

    concat_list = temp_dir / f"{sample_id}_concat.txt"
    concat_list.write_text(
        "".join(f"file '{path.as_posix()}'\n" for path in concat_paths),
        encoding="utf-8",
    )
    run_command(
        [
            str(ffmpeg),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_list),
            "-c",
            "copy",
            str(output_audio),
        ]
    )
    output_truth.write_text("\n\n".join(truth_parts).strip() + "\n", encoding="utf-8")


def copy_for_qwen_runtime(qwen_runtime_dir: Path, audio_dir: Path, truth_dir: Path) -> None:
    qwen_audio = qwen_runtime_dir / "audio"
    qwen_truth = qwen_runtime_dir / "ground_truth"
    qwen_audio.mkdir(parents=True, exist_ok=True)
    qwen_truth.mkdir(parents=True, exist_ok=True)
    for path in audio_dir.glob("*.wav"):
        shutil.copy2(path, qwen_audio / path.name)
    for path in truth_dir.glob("*.txt"):
        shutil.copy2(path, qwen_truth / path.name)


def render_manifest_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# v0.5.8 长音频稳定性样本清单",
        "",
        "> 本清单只说明稳定性测试样本如何生成。16 分钟是待验证的场景假设，30 分钟是压力测试场景；二者都不代表中国门诊平均问诊时长。",
        "",
        "## 生成策略",
        "",
        f"- 生成时间：{manifest.get('generated_at')}",
        f"- 源音频目录：`{manifest.get('source_audio_dir')}`",
        f"- 源标注目录：`{manifest.get('source_truth_dir')}`",
        "- 样本来源：课程演示中文医患音频拼接，必要时补静音。",
        "- 使用边界：只用于 ASR 吞吐、内存、CPU、失败恢复和长音频流程稳定性。",
    ]
    if manifest.get("qwen_runtime_dir"):
        lines.append(f"- Qwen ASCII 运行区副本：`{manifest.get('qwen_runtime_dir')}`")

    lines.extend(
        [
            "",
            "## 源样本",
            "",
            "| 样本 | 音频 | 标注 | 时长秒 |",
            "| --- | --- | --- | ---: |",
        ]
    )
    for item in manifest.get("sources", []):
        lines.append(
            f"| {item['sample_id']} | `{item['audio_file']}` | `{item['truth_file']}` | {item['duration_seconds']} |"
        )

    lines.extend(
        [
            "",
            "## 长音频样本",
            "",
            "| 样本 | 目标秒 | 实际秒 | 音频 | 标注 | 拼接段数 |",
            "| --- | ---: | ---: | --- | --- | ---: |",
        ]
    )
    for item in manifest.get("samples", []):
        lines.append(
            f"| {item['sample_id']} | {item['target_seconds']} | {item['actual_seconds']} | "
            f"`{item['audio_file']}` | `{item['ground_truth_file']}` | {len(item.get('segments', []))} |"
        )

    lines.extend(["", "## 注意事项", "", "- CER 可作为同一拼接标注下的粗略参考，但本轮更关注完成状态、RTF、RSS、CPU 和失败原因。", "- 音频文件不提交 GitHub；脚本、报告和轻量清单可提交。", ""])
    return "\n".join(lines)


def find_audio(audio_dir: Path, sample_id: str) -> Path | None:
    for suffix in SUPPORTED_SUFFIXES:
        candidate = audio_dir / f"{sample_id}{suffix}"
        if candidate.exists():
            return candidate
    return None


def resolve_binary(name: str, explicit: Path | None = None) -> Path:
    candidates = []
    if explicit is not None:
        candidates.append(explicit)
    project_tool = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / f"{name}.exe"
    candidates.append(project_tool)
    system = shutil.which(name)
    if system:
        candidates.append(Path(system))
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    raise FileNotFoundError(f"{name} not found. Run scripts/setup_ffmpeg_portable.py first.")


def probe_duration(audio_path: Path, ffprobe: Path) -> float:
    completed = run_command(
        [
            str(ffprobe),
            "-hide_banner",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(audio_path),
        ],
        capture=True,
    )
    return float((completed.stdout or "0").strip())


def run_command(command: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        check=True,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def relative_or_name(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    args = parse_args()
    manifest = prepare_long_audio_samples(
        source_audio_dir=args.source_audio_dir,
        source_truth_dir=args.source_truth_dir,
        output_root=args.output_root,
        reports_dir=args.reports_dir,
        source_ids=args.source_ids,
        targets=parse_targets(args.target),
        qwen_runtime_dir=None if args.no_qwen_copy else args.qwen_runtime_dir,
        ffmpeg_path=args.ffmpeg,
        ffprobe_path=args.ffprobe,
    )
    print("Long-audio stability samples prepared:")
    for sample in manifest["samples"]:
        print(f"- {sample['sample_id']}: {sample['actual_seconds']}s")
    print(f"- manifest: {args.reports_dir / 'long_audio_samples_manifest.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
