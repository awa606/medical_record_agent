from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


VALID_SPLITS = {"calibration", "test"}
REQUIRED_SAMPLE_FIELDS = {
    "sample_id",
    "scenario_type",
    "split",
    "audio_ref",
    "sha256",
    "duration_sec",
    "speaker_count",
    "annotation_path",
    "annotation_version",
}
REQUIRED_ANNOTATION_FIELDS = {
    "sample_id",
    "annotation_version",
    "privacy",
    "transcript",
    "speaker_turns",
    "speaker_roles",
    "medical_keywords",
    "medical_record_fields",
    "evidence_spans",
    "baseline_prediction",
}


class DatasetValidationError(ValueError):
    """Raised when the frozen speaker-role dataset is incomplete or inconsistent."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_dataset(manifest_path: Path, *, verify_hashes: bool = True) -> dict[str, Any]:
    manifest_path = manifest_path.resolve()
    manifest_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise DatasetValidationError("manifest.samples must be a non-empty list")

    seen_ids: set[str] = set()
    loaded_samples: list[dict[str, Any]] = []
    for sample in samples:
        missing = REQUIRED_SAMPLE_FIELDS - set(sample)
        if missing:
            raise DatasetValidationError(f"sample missing fields: {sorted(missing)}")

        sample_id = str(sample["sample_id"])
        if sample_id in seen_ids:
            raise DatasetValidationError(f"duplicate sample_id: {sample_id}")
        seen_ids.add(sample_id)

        split = str(sample["split"])
        if split not in VALID_SPLITS:
            raise DatasetValidationError(f"{sample_id}: invalid split {split!r}")

        audio_path = manifest_dir / str(sample["audio_ref"])
        if verify_hashes:
            if not audio_path.exists():
                raise DatasetValidationError(f"{sample_id}: audio_ref does not exist: {audio_path}")
            actual_hash = sha256_file(audio_path)
            if actual_hash != sample["sha256"]:
                raise DatasetValidationError(
                    f"{sample_id}: sha256 mismatch for {sample['audio_ref']}: "
                    f"expected {sample['sha256']}, got {actual_hash}"
                )

        annotation_path = manifest_dir / str(sample["annotation_path"])
        if not annotation_path.exists():
            raise DatasetValidationError(f"{sample_id}: annotation_path does not exist: {annotation_path}")
        annotation = load_json(annotation_path)
        _validate_annotation(sample, annotation)

        loaded_samples.append(
            {
                "manifest": sample,
                "annotation": annotation,
                "audio_hash_status": "verified" if verify_hashes else "not_checked",
            }
        )

    split_counts = {split: 0 for split in sorted(VALID_SPLITS)}
    for item in loaded_samples:
        split_counts[item["manifest"]["split"]] += 1
    if not split_counts["calibration"] or not split_counts["test"]:
        raise DatasetValidationError("manifest must contain both calibration and test samples")

    return {
        "dataset_version": manifest.get("dataset_version"),
        "schema_version": manifest.get("schema_version"),
        "manifest_path": str(manifest_path),
        "samples": loaded_samples,
    }


def evaluate_dataset(manifest_path: Path, *, verify_hashes: bool = True) -> dict[str, Any]:
    dataset = load_dataset(manifest_path, verify_hashes=verify_hashes)
    role_total = 0
    role_correct = 0
    accepted_total = 0
    high_confidence_errors: list[dict[str, Any]] = []
    manual_required_total = 0
    speaker_count_correct = 0
    keyword_total = 0
    keyword_hits = 0
    mixed_segments = 0
    segment_total = 0

    split_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}

    for item in dataset["samples"]:
        sample = item["manifest"]
        annotation = item["annotation"]
        split_counts[sample["split"]] = split_counts.get(sample["split"], 0) + 1
        scenario_counts[sample["scenario_type"]] = scenario_counts.get(sample["scenario_type"], 0) + 1

        truth_roles = {str(k): str(v) for k, v in annotation["speaker_roles"].items()}
        prediction = annotation["baseline_prediction"]
        predicted_roles = {str(k): str(v) for k, v in prediction.get("speaker_roles", {}).items()}
        accepted = {str(value) for value in prediction.get("auto_accepted_speakers", [])}

        for speaker_id, truth_role in truth_roles.items():
            role_total += 1
            predicted_role = predicted_roles.get(speaker_id)
            if predicted_role == truth_role:
                role_correct += 1
            if speaker_id in accepted:
                accepted_total += 1
                if predicted_role != truth_role:
                    high_confidence_errors.append(
                        {
                            "sample_id": sample["sample_id"],
                            "speaker_id": speaker_id,
                            "expected": truth_role,
                            "predicted": predicted_role,
                        }
                    )
            else:
                manual_required_total += 1

        predicted_speaker_count = int(prediction.get("predicted_speaker_count", len(predicted_roles)))
        if predicted_speaker_count == int(sample["speaker_count"]):
            speaker_count_correct += 1

        expected_keywords = {str(value) for value in annotation.get("medical_keywords", [])}
        predicted_keywords = {str(value) for value in prediction.get("medical_keywords", [])}
        keyword_total += len(expected_keywords)
        keyword_hits += len(expected_keywords & predicted_keywords)

        transcript = annotation.get("transcript", [])
        segment_total += len(transcript)
        mixed_segments += sum(1 for segment in transcript if segment.get("mixed_utterance"))

    sample_count = len(dataset["samples"])
    report = {
        "dataset_version": dataset["dataset_version"],
        "schema_version": dataset["schema_version"],
        "manifest_path": _display_path(Path(dataset["manifest_path"])),
        "sample_count": sample_count,
        "split_counts": split_counts,
        "scenario_counts": scenario_counts,
        "metrics": {
            "role_accuracy": _ratio(role_correct, role_total),
            "auto_accept_coverage": _ratio(accepted_total, role_total),
            "high_confidence_error_count": len(high_confidence_errors),
            "manual_confirmation_rate": _ratio(manual_required_total, role_total),
            "speaker_count_accuracy": _ratio(speaker_count_correct, sample_count),
            "mixed_utterance_rate": _ratio(mixed_segments, segment_total),
            "keyword_recall": _ratio(keyword_hits, keyword_total),
        },
        "high_confidence_errors": high_confidence_errors,
        "hash_status": {
            "verified_count": sum(1 for item in dataset["samples"] if item["audio_hash_status"] == "verified"),
            "failed_count": 0,
        },
    }
    return report


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    lines = [
        "# v1.5 冻结临床多说话人评测集基线报告",
        "",
        f"- 数据版本：`{report['dataset_version']}`",
        f"- Schema 版本：`{report['schema_version']}`",
        f"- 样本数：{report['sample_count']}",
        f"- calibration/test：{report['split_counts'].get('calibration', 0)} / {report['split_counts'].get('test', 0)}",
        "",
        "## 指标",
        "",
        f"- 角色准确率：{metrics['role_accuracy']}",
        f"- 自动通过覆盖率：{metrics['auto_accept_coverage']}",
        f"- 高置信错误数：{metrics['high_confidence_error_count']}",
        f"- 人工确认率：{metrics['manual_confirmation_rate']}",
        f"- speaker 数量准确率：{metrics['speaker_count_accuracy']}",
        f"- 混合语句率：{metrics['mixed_utterance_rate']}",
        f"- 医学关键词召回率：{metrics['keyword_recall']}",
        "",
        "## 场景覆盖",
        "",
    ]
    lines.extend(f"- `{key}`：{value}" for key, value in sorted(report["scenario_counts"].items()))
    if report["high_confidence_errors"]:
        lines.extend(["", "## 高置信错误", ""])
        for item in report["high_confidence_errors"]:
            lines.append(
                f"- {item['sample_id']} / {item['speaker_id']}: "
                f"expected={item['expected']}, predicted={item['predicted']}"
            )
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_path: Path, markdown_output: Path | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path = markdown_output or output_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def _validate_annotation(sample: dict[str, Any], annotation: dict[str, Any]) -> None:
    missing = REQUIRED_ANNOTATION_FIELDS - set(annotation)
    if missing:
        raise DatasetValidationError(f"{sample['sample_id']}: annotation missing fields: {sorted(missing)}")
    if annotation["sample_id"] != sample["sample_id"]:
        raise DatasetValidationError(f"{sample['sample_id']}: annotation sample_id mismatch")
    if annotation["annotation_version"] != sample["annotation_version"]:
        raise DatasetValidationError(f"{sample['sample_id']}: annotation_version mismatch")
    privacy = annotation["privacy"]
    if not privacy.get("synthetic") or privacy.get("contains_real_patient_data"):
        raise DatasetValidationError(f"{sample['sample_id']}: annotation must be synthetic and privacy-safe")
    if len(annotation["speaker_roles"]) != int(sample["speaker_count"]):
        raise DatasetValidationError(f"{sample['sample_id']}: speaker_count does not match speaker_roles")
    if not annotation["transcript"]:
        raise DatasetValidationError(f"{sample['sample_id']}: transcript must not be empty")
    if not annotation["speaker_turns"]:
        raise DatasetValidationError(f"{sample['sample_id']}: speaker_turns must not be empty")
    if not annotation["baseline_prediction"].get("speaker_roles"):
        raise DatasetValidationError(f"{sample['sample_id']}: baseline_prediction.speaker_roles is required")


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _display_path(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the frozen clinical speaker-role dataset.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--skip-hash-check", action="store_true")
    args = parser.parse_args()

    try:
        report = evaluate_dataset(args.manifest, verify_hashes=not args.skip_hash_check)
    except DatasetValidationError as exc:
        print(f"dataset validation failed: {exc}", file=sys.stderr)
        return 2

    write_report(report, args.output, args.markdown_output)
    print(json.dumps({"status": "ok", "output": str(args.output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
