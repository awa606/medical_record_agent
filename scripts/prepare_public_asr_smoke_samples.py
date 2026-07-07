"""Prepare small non-medical public audio samples for ASR smoke tests."""

from __future__ import annotations

import argparse
import json
import shutil
import tarfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASE_DIR = PROJECT_ROOT / "data" / "asr_eval" / "public_smoke"
DEFAULT_AUDIO_DIR = DEFAULT_BASE_DIR / "audio"
DEFAULT_TRUTH_DIR = DEFAULT_BASE_DIR / "ground_truth"
DEFAULT_CACHE_DIR = DEFAULT_BASE_DIR / "cache"
DEFAULT_REPORTS_DIR = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "public_smoke"
DEFAULT_MANIFEST_JSON = DEFAULT_REPORTS_DIR / "public_samples_manifest.json"
DEFAULT_MANIFEST_MD = DEFAULT_REPORTS_DIR / "public_samples_manifest.md"

QWEN_SAMPLES = [
    {
        "sample_id": "qwen_asr_zh",
        "url": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_zh.wav",
        "filename": "qwen_asr_zh.wav",
        "language": "zh",
        "evaluation_group": "public_cn_smoke",
        "evaluation_priority": "中文公开冒烟样本",
        "scene": "non_medical_public",
        "medical_relevance": "none",
        "role_conclusion_policy": "不用于医生/患者角色正确性结论",
        "source": "Qwen3-ASR official repository sample",
        "license": "Sample distributed by Qwen3-ASR project for model usage examples; use as smoke-test reference only.",
        "ground_truth": None,
    },
    {
        "sample_id": "qwen_asr_en",
        "url": "https://qianwen-res.oss-cn-beijing.aliyuncs.com/Qwen3-ASR-Repo/asr_en.wav",
        "filename": "qwen_asr_en.wav",
        "language": "en",
        "evaluation_group": "public_en_smoke",
        "evaluation_priority": "可选多语种冒烟样本",
        "scene": "non_medical_public",
        "medical_relevance": "none",
        "role_conclusion_policy": "不进入中文医患主结论",
        "source": "Qwen3-ASR official repository sample",
        "license": "Sample distributed by Qwen3-ASR project for model usage examples; use as smoke-test reference only.",
        "ground_truth": None,
    },
]

MINI_LIBRISPEECH_URL = "https://www.openslr.org/resources/31/dev-clean-2.tar.gz"


def prepare_public_smoke_samples(
    *,
    limit: int,
    audio_dir: Path = DEFAULT_AUDIO_DIR,
    truth_dir: Path = DEFAULT_TRUTH_DIR,
    cache_dir: Path = DEFAULT_CACHE_DIR,
    include_mini_librispeech: bool = True,
) -> dict[str, Any]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    truth_dir.mkdir(parents=True, exist_ok=True)
    cache_dir.mkdir(parents=True, exist_ok=True)

    samples: list[dict[str, Any]] = []
    for item in QWEN_SAMPLES[: max(limit, 0)]:
        destination = audio_dir / item["filename"]
        _download_if_missing(item["url"], destination)
        samples.append(_sample_record(item, destination, has_ground_truth=False))

    remaining = max(limit - len(samples), 0)
    if include_mini_librispeech and remaining > 0:
        samples.extend(
            _prepare_mini_librispeech(
                remaining=remaining,
                audio_dir=audio_dir,
                truth_dir=truth_dir,
                cache_dir=cache_dir,
            )
        )

    manifest = {
        "schema_version": "v0.5.5",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "non_medical_public_asr_smoke_test",
        "evaluation_policy": {
            "primary_group": "course_medical_cn",
            "public_chinese_group": "public_cn_smoke",
            "optional_multilingual_group": "public_en_smoke",
            "note": "v0.5.4 以后中文医患课程样本是主评测；英文公开样本只保留为可选多语种 smoke。",
        },
        "note": "Audio files and ground-truth text are local-only and ignored by Git; reports are lightweight evidence.",
        "samples": samples,
    }
    return manifest


def write_manifest(manifest: dict[str, Any], json_output: Path, markdown_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(manifest), encoding="utf-8")


def render_markdown(manifest: dict[str, Any]) -> str:
    lines = [
        "# 中文优先公开 ASR 冒烟测试样本记录",
        "",
        "> 本记录用于 v0.5.5。音频和标注文本只保存在本地忽略目录，不提交 GitHub。",
        "",
        "## 评测分层",
        "",
        "| 分层 | 用途 | 是否进入中文医患主结论 |",
        "| --- | --- | --- |",
        "| `course_medical_cn` | 三条课程中文医患样本，作为本项目 ASR 主评测。 | 是 |",
        "| `public_cn_smoke` | 中文公开样本，只验证中文 ASR 可用性。 | 只作为辅助证据 |",
        "| `public_en_smoke` | 英文公开样本，只验证多语种/Whisper/ffmpeg 冒烟链路。 | 否 |",
        "",
        "## 样本清单",
        "",
        "| 样本 | 语言 | 分层 | 优先级 | 是否有标注 | 是否医疗 | 角色结论 | 来源 | 许可证/说明 |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for sample in manifest.get("samples", []):
        lines.append(
            "| {sample_id} | {language} | {group} | {priority} | {truth} | {medical} | {role_policy} | {source} | {license} |".format(
                sample_id=_cell(sample.get("sample_id")),
                language=_cell(sample.get("language")),
                group=_cell(sample.get("evaluation_group")),
                priority=_cell(sample.get("evaluation_priority")),
                truth="是" if sample.get("has_ground_truth") else "否",
                medical=_cell(sample.get("medical_relevance")),
                role_policy=_cell(sample.get("role_conclusion_policy")),
                source=_cell(sample.get("source")),
                license=_cell(sample.get("license")),
            )
        )
    lines.extend(
        [
            "",
            "## 边界",
            "",
            "- 中文医患课程样本才是本项目 ASR 主评测对象。",
            "- 非医疗公开样本只用于 ASR 可用性、耗时和通用转写冒烟测试。",
            "- 英文公开样本只保留为可选多语种 smoke，不进入中文医患效果结论。",
            "- 非医疗样本不用于医学诊断、医学关键词召回或医生/患者角色正确性结论。",
            "",
        ]
    )
    return "\n".join(lines)


def _prepare_mini_librispeech(
    *,
    remaining: int,
    audio_dir: Path,
    truth_dir: Path,
    cache_dir: Path,
) -> list[dict[str, Any]]:
    archive_path = cache_dir / "mini_librispeech_dev-clean-2.tar.gz"
    _download_if_missing(MINI_LIBRISPEECH_URL, archive_path)
    transcripts = _read_librispeech_transcripts(archive_path)
    samples: list[dict[str, Any]] = []

    with tarfile.open(archive_path, "r:gz") as archive:
        flac_members = [member for member in archive.getmembers() if member.isfile() and member.name.endswith(".flac")]
        for member in flac_members:
            utterance_id = Path(member.name).stem
            transcript = transcripts.get(utterance_id)
            if not transcript:
                continue
            sample_id = f"mini_librispeech_{utterance_id}"
            audio_path = audio_dir / f"{sample_id}.flac"
            truth_path = truth_dir / f"{sample_id}.txt"
            if not audio_path.exists():
                source = archive.extractfile(member)
                if source is None:
                    continue
                with source, audio_path.open("wb") as target:
                    shutil.copyfileobj(source, target)
            truth_path.write_text(transcript + "\n", encoding="utf-8")
            samples.append(
                {
                    "sample_id": sample_id,
                    "filename": audio_path.name,
                    "ground_truth_file": truth_path.name,
                    "language": "en",
                    "evaluation_group": "public_en_smoke",
                    "evaluation_priority": "可选多语种冒烟样本",
                    "scene": "non_medical_public",
                    "medical_relevance": "none",
                    "role_conclusion_policy": "不进入中文医患主结论",
                    "source": "Mini LibriSpeech dev-clean-2, OpenSLR SLR31",
                    "license": "CC BY 4.0",
                    "has_ground_truth": True,
                    "url": MINI_LIBRISPEECH_URL,
                }
            )
            if len(samples) >= remaining:
                break
    return samples


def _read_librispeech_transcripts(archive_path: Path) -> dict[str, str]:
    transcripts: dict[str, str] = {}
    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            if not member.isfile() or not member.name.endswith(".trans.txt"):
                continue
            extracted = archive.extractfile(member)
            if extracted is None:
                continue
            content = extracted.read().decode("utf-8", errors="replace")
            for line in content.splitlines():
                if not line.strip():
                    continue
                utterance_id, _, text = line.partition(" ")
                if utterance_id and text:
                    transcripts[utterance_id] = text.strip()
    return transcripts


def _download_if_missing(url: str, destination: Path) -> None:
    if destination.exists() and destination.stat().st_size > 0:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=180) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _sample_record(item: dict[str, Any], destination: Path, *, has_ground_truth: bool) -> dict[str, Any]:
    return {
        "sample_id": item["sample_id"],
        "filename": destination.name,
        "language": item["language"],
        "evaluation_group": item.get("evaluation_group"),
        "evaluation_priority": item.get("evaluation_priority"),
        "scene": item.get("scene"),
        "medical_relevance": item.get("medical_relevance"),
        "role_conclusion_policy": item.get("role_conclusion_policy"),
        "source": item["source"],
        "license": item["license"],
        "has_ground_truth": has_ground_truth,
        "url": item["url"],
    }


def _cell(value: Any) -> str:
    if value is None or value == "":
        return "-"
    return str(value).replace("|", "\\|")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare non-medical public ASR smoke samples.")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--audio-dir", type=Path, default=DEFAULT_AUDIO_DIR)
    parser.add_argument("--truth-dir", type=Path, default=DEFAULT_TRUTH_DIR)
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE_DIR)
    parser.add_argument("--skip-mini-librispeech", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_MANIFEST_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_MANIFEST_MD)
    args = parser.parse_args()

    manifest = prepare_public_smoke_samples(
        limit=max(args.limit, 0),
        audio_dir=args.audio_dir,
        truth_dir=args.truth_dir,
        cache_dir=args.cache_dir,
        include_mini_librispeech=not args.skip_mini_librispeech,
    )
    write_manifest(manifest, args.json_output, args.markdown_output)
    print("中文优先公开 ASR 冒烟样本准备完成：")
    print(f"- samples: {len(manifest['samples'])}")
    print(f"- audio dir: {args.audio_dir}")
    print(f"- report: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
