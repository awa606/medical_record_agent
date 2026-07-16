from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.role_quality import attach_speaker_role_quality
from app.services.asr.speaker_diarization import enhance_speaker_diarization
from app.services.asr.speaker_role_policy import (
    CURRENT_SPEAKER_ROLE_POLICY_VERSION,
    DEFAULT_PROVIDER_POLICIES,
    provider_config_payload,
)


VALID_SPLITS = {"calibration", "test"}
VALID_SPLIT_ARGS = {"all", *VALID_SPLITS}
VALID_ACTIONS = {"auto_accept", "needs_review", "blocked"}
PRODUCT_PROVIDERS = {"rules", "voiceprint", "llm"}
GENERATION_PROVIDERS = {"rules"}
SPEECH_AUDIO_SUFFIXES = {".wav", ".flac"}
DISALLOWED_TRUTH_KEYS = {
    "baseline_prediction",
    "prediction",
    "predictions",
    "speaker_decisions",
}

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
REQUIRED_TRUTH_FIELDS = {
    "sample_id",
    "annotation_version",
    "privacy",
    "transcript",
    "speaker_turns",
    "speaker_roles",
    "medical_keywords",
    "medical_record_fields",
    "evidence_spans",
}
REQUIRED_PREDICTION_FIELDS = {
    "sample_id",
    "provider",
    "provider_version",
    "policy_version",
    "git_commit",
    "generated_at",
    "speaker_decisions",
    "predicted_speaker_count",
    "medical_keywords",
}
REQUIRED_DECISION_FIELDS = {
    "speaker_id",
    "predicted_role",
    "provider",
    "provider_version",
    "policy_version",
    "git_commit",
    "raw_confidence",
    "calibrated_confidence",
    "reason_code",
    "action",
}

ROLE_ALIASES = {
    "doctor": "doctor",
    "医生": "doctor",
    "physician": "doctor",
    "patient": "patient",
    "患者": "patient",
    "family": "other",
    "家属": "other",
    "relative": "other",
    "other": "other",
    "其他": "other",
}
VALID_ROLES = set(ROLE_ALIASES.values())

DOCTOR_MARKERS = {
    "请问",
    "多久",
    "哪里",
    "有没有",
    "建议",
    "需要",
    "检查",
    "测量",
    "复诊",
    "处方",
    "先做",
    "用药",
    "诊断",
}
PATIENT_MARKERS = {
    "我",
    "疼",
    "痛",
    "发热",
    "发烧",
    "咳嗽",
    "胸闷",
    "头晕",
    "腹泻",
    "恶心",
    "过敏",
    "昨天",
    "今天",
    "不舒服",
}
FAMILY_MARKERS = {
    "他",
    "她",
    "孩子",
    "母亲",
    "父亲",
    "老人",
    "家属",
    "我们家",
    "我妈妈",
    "我爸爸",
    "陪",
}
STRONG_FAMILY_MARKERS = {"家属", "陪", "我们家", "母亲", "父亲", "孩子", "老人"}
MEDICAL_KEYWORD_CATALOG = {
    "发热",
    "发烧",
    "咳嗽",
    "胸痛",
    "胸闷",
    "头晕",
    "腹痛",
    "腹泻",
    "恶心",
    "过敏",
    "高血压",
    "糖尿病",
    "外伤",
    "咽痛",
    "胃痛",
    "哮喘",
    "血压",
}


class ExecutableDatasetValidationError(ValueError):
    """Raised when the executable speaker-role dataset is invalid."""


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def is_lfs_pointer(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            prefix = handle.read(128)
    except OSError:
        return False
    return prefix.startswith(b"version https://git-lfs.github.com/spec/v1")


def load_dataset(
    manifest_path: Path,
    *,
    verify_hashes: bool = True,
    split: str = "all",
) -> dict[str, Any]:
    if split not in VALID_SPLIT_ARGS:
        raise ExecutableDatasetValidationError(f"invalid split {split!r}")

    manifest_path = manifest_path.resolve()
    manifest_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    if manifest.get("audio_storage") != "git_lfs":
        raise ExecutableDatasetValidationError("manifest.audio_storage must be git_lfs")

    samples = manifest.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ExecutableDatasetValidationError("manifest.samples must be a non-empty list")

    seen_ids: set[str] = set()
    loaded_samples: list[dict[str, Any]] = []
    all_split_counts = {key: 0 for key in sorted(VALID_SPLITS)}
    for sample in samples:
        missing = REQUIRED_SAMPLE_FIELDS - set(sample)
        if missing:
            raise ExecutableDatasetValidationError(f"sample missing fields: {sorted(missing)}")

        sample_id = str(sample["sample_id"])
        if sample_id in seen_ids:
            raise ExecutableDatasetValidationError(f"duplicate sample_id: {sample_id}")
        seen_ids.add(sample_id)

        sample_split = str(sample["split"])
        if sample_split not in VALID_SPLITS:
            raise ExecutableDatasetValidationError(f"{sample_id}: invalid split {sample_split!r}")
        all_split_counts[sample_split] += 1

        audio_path = (manifest_dir / str(sample["audio_ref"])).resolve()
        if audio_path.suffix.lower() not in SPEECH_AUDIO_SUFFIXES:
            raise ExecutableDatasetValidationError(f"{sample_id}: audio_ref must be WAV or FLAC")
        if verify_hashes:
            if not audio_path.exists():
                raise ExecutableDatasetValidationError(f"{sample_id}: audio_ref does not exist: {audio_path}")
            if is_lfs_pointer(audio_path):
                raise ExecutableDatasetValidationError(
                    f"{sample_id}: audio_ref is a Git LFS pointer; run `git lfs pull` before evaluation"
                )
            actual_hash = sha256_file(audio_path)
            if actual_hash != sample["sha256"]:
                raise ExecutableDatasetValidationError(
                    f"{sample_id}: sha256 mismatch for {sample['audio_ref']}: "
                    f"expected {sample['sha256']}, got {actual_hash}"
                )

        annotation_path = (manifest_dir / str(sample["annotation_path"])).resolve()
        if not annotation_path.exists():
            raise ExecutableDatasetValidationError(
                f"{sample_id}: annotation_path does not exist: {annotation_path}"
            )
        annotation = load_json(annotation_path)
        _validate_truth_annotation(sample, annotation)

        if split != "all" and sample_split != split:
            continue

        loaded_samples.append(
            {
                "manifest": sample,
                "annotation": annotation,
                "audio_path": audio_path,
                "annotation_path": annotation_path,
                "audio_hash_status": "verified" if verify_hashes else "not_checked",
            }
        )

    if not all_split_counts["calibration"] or not all_split_counts["test"]:
        raise ExecutableDatasetValidationError("manifest must contain both calibration and test samples")
    if not loaded_samples:
        raise ExecutableDatasetValidationError(f"no samples selected for split {split!r}")

    return {
        "dataset_version": manifest.get("dataset_version"),
        "schema_version": manifest.get("schema_version"),
        "audio_storage": manifest.get("audio_storage"),
        "manifest_path": str(manifest_path),
        "manifest_dir": str(manifest_dir),
        "selected_split": split,
        "all_split_counts": all_split_counts,
        "samples": loaded_samples,
    }


def default_prediction_dir(manifest_path: Path, provider: str) -> Path:
    return manifest_path.resolve().parent / "predictions" / provider


def generate_rules_prediction_artifacts(
    dataset: dict[str, Any],
    *,
    prediction_dir: Path,
    git_commit: str | None = None,
    provider_version: str | None = None,
    policy_version: str = CURRENT_SPEAKER_ROLE_POLICY_VERSION,
) -> list[Path]:
    git_commit = git_commit or current_git_commit()
    provider_version = provider_version or DEFAULT_PROVIDER_POLICIES["rules"].provider_version
    generated_paths: list[Path] = []
    for item in dataset["samples"]:
        sample = item["manifest"]
        annotation = item["annotation"]
        prediction = _build_rules_prediction(
            sample,
            annotation,
            git_commit=git_commit,
            provider_version=provider_version,
            policy_version=policy_version,
        )
        output_path = prediction_dir / f"{sample['sample_id']}.prediction.json"
        write_json(output_path, prediction)
        generated_paths.append(output_path)
    return generated_paths


def evaluate_dataset(
    manifest_path: Path,
    *,
    provider: str = "rules",
    prediction_dir: Path | None = None,
    verify_hashes: bool = True,
    split: str = "all",
    auto_accept_threshold: float | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(manifest_path, verify_hashes=verify_hashes, split=split)
    prediction_dir = prediction_dir or default_prediction_dir(manifest_path, provider)
    predictions = _load_prediction_artifacts(dataset, prediction_dir=prediction_dir, provider=provider)
    return evaluate_loaded_dataset(
        dataset,
        predictions=predictions,
        provider=provider,
        auto_accept_threshold=auto_accept_threshold,
    )


def evaluate_loaded_dataset(
    dataset: dict[str, Any],
    *,
    predictions: dict[str, dict[str, Any]],
    provider: str,
    auto_accept_threshold: float | None = None,
) -> dict[str, Any]:
    role_total = 0
    role_correct = 0
    auto_accept_total = 0
    auto_accept_correct = 0
    review_required_total = 0
    high_confidence_errors: list[dict[str, Any]] = []
    speaker_count_correct = 0
    keyword_total = 0
    keyword_hits = 0
    mixed_segments = 0
    segment_total = 0
    split_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}

    provider_versions: set[str] = set()
    policy_versions: set[str] = set()
    git_commits: set[str] = set()
    provider_configs: set[str] = set()

    for item in dataset["samples"]:
        sample = item["manifest"]
        annotation = item["annotation"]
        sample_id = sample["sample_id"]
        prediction = predictions[sample_id]
        provider_versions.add(str(prediction["provider_version"]))
        policy_versions.add(str(prediction["policy_version"]))
        git_commits.add(str(prediction["git_commit"]))
        if "provider_config" in prediction:
            provider_configs.add(json.dumps(prediction["provider_config"], ensure_ascii=False, sort_keys=True))

        split_counts[sample["split"]] = split_counts.get(sample["split"], 0) + 1
        scenario_counts[sample["scenario_type"]] = scenario_counts.get(sample["scenario_type"], 0) + 1

        truth_roles = {
            str(speaker_id): canonical_role(role)
            for speaker_id, role in annotation["speaker_roles"].items()
        }
        decisions = {
            str(decision["speaker_id"]): decision
            for decision in prediction["speaker_decisions"]
        }
        for speaker_id, truth_role in truth_roles.items():
            role_total += 1
            decision = decisions.get(speaker_id)
            predicted_role = canonical_role(decision["predicted_role"]) if decision else None
            if predicted_role == truth_role:
                role_correct += 1
            action = _effective_action(decision, auto_accept_threshold=auto_accept_threshold)
            if action == "auto_accept":
                auto_accept_total += 1
                if predicted_role == truth_role:
                    auto_accept_correct += 1
                else:
                    high_confidence_errors.append(
                        {
                            "sample_id": sample_id,
                            "speaker_id": speaker_id,
                            "expected": truth_role,
                            "predicted": predicted_role,
                            "calibrated_confidence": decision.get("calibrated_confidence") if decision else None,
                            "reason_code": decision.get("reason_code") if decision else "missing_decision",
                        }
                    )
            else:
                review_required_total += 1

        if int(prediction["predicted_speaker_count"]) == int(sample["speaker_count"]):
            speaker_count_correct += 1

        expected_keywords = set(_normalize_keywords(annotation.get("medical_keywords", [])))
        predicted_keywords = set(_normalize_keywords(prediction.get("medical_keywords", [])))
        keyword_total += len(expected_keywords)
        keyword_hits += len(expected_keywords & predicted_keywords)

        transcript = annotation.get("transcript", [])
        segment_total += len(transcript)
        mixed_segments += sum(1 for segment in transcript if bool(segment.get("mixed_utterance")))

    sample_count = len(dataset["samples"])
    metrics = {
        "role_accuracy": _ratio(role_correct, role_total),
        "auto_accept_accuracy": _ratio(auto_accept_correct, auto_accept_total)
        if auto_accept_total
        else None,
        "auto_accept_coverage": _ratio(auto_accept_total, role_total),
        "high_confidence_error_count": len(high_confidence_errors),
        "manual_confirmation_rate": _ratio(review_required_total, role_total),
        "speaker_count_accuracy": _ratio(speaker_count_correct, sample_count),
        "mixed_utterance_rate": _ratio(mixed_segments, segment_total),
        "keyword_recall": _ratio(keyword_hits, keyword_total),
    }
    confidence_intervals = {
        "role_accuracy": _wilson_interval(role_correct, role_total),
        "auto_accept_accuracy": _wilson_interval(auto_accept_correct, auto_accept_total),
        "auto_accept_coverage": _wilson_interval(auto_accept_total, role_total),
        "manual_confirmation_rate": _wilson_interval(review_required_total, role_total),
        "speaker_count_accuracy": _wilson_interval(speaker_count_correct, sample_count),
        "mixed_utterance_rate": _wilson_interval(mixed_segments, segment_total),
        "keyword_recall": _wilson_interval(keyword_hits, keyword_total),
    }
    counts_as_product_accuracy = provider in PRODUCT_PROVIDERS
    provider_report = {
        "provider": provider,
        "evaluation_mode": "oracle_transcript_role_decision",
        "audio_pipeline_evaluated": False,
        "evaluation_policy_override": {
            "auto_accept_threshold": auto_accept_threshold,
        }
        if auto_accept_threshold is not None
        else None,
        "provider_versions": sorted(provider_versions),
        "policy_versions": sorted(policy_versions),
        "git_commits": sorted(git_commits),
        "provider_configs": [json.loads(config) for config in sorted(provider_configs)],
        "counts_as_product_accuracy": counts_as_product_accuracy,
        "sample_count": sample_count,
        "split_counts": split_counts,
        "scenario_counts": scenario_counts,
        "metrics": metrics,
        "confidence_intervals_95": confidence_intervals,
        "high_confidence_errors": high_confidence_errors,
        "hash_status": {
            "verified_count": sum(
                1 for item in dataset["samples"] if item["audio_hash_status"] == "verified"
            ),
            "failed_count": 0,
        },
    }
    return {
        "dataset_version": dataset["dataset_version"],
        "schema_version": dataset["schema_version"],
        "evaluation_mode": "oracle_transcript_role_decision",
        "audio_pipeline_evaluated": False,
        "evaluation_policy_override": {
            "auto_accept_threshold": auto_accept_threshold,
        }
        if auto_accept_threshold is not None
        else None,
        "audio_pipeline_note": (
            "WAV/FLAC files are verified for data provenance and future end-to-end "
            "evaluation entry points; this report evaluates role decisions from oracle transcripts."
        ),
        "manifest_path": _display_path(Path(dataset["manifest_path"])),
        "selected_split": dataset["selected_split"],
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "providers": [provider],
        "provider_reports": {provider: provider_report},
        "sample_count": sample_count,
        "split_counts": split_counts,
        "scenario_counts": scenario_counts,
        "metrics": metrics,
        "confidence_intervals_95": confidence_intervals,
        "counts_as_product_accuracy": counts_as_product_accuracy,
        "mock_excluded_from_product_metrics": provider == "mock",
        "high_confidence_errors": high_confidence_errors,
        "hash_status": provider_report["hash_status"],
    }


def calibrate_loaded_dataset(
    dataset: dict[str, Any],
    *,
    predictions: dict[str, dict[str, Any]],
    provider: str,
) -> dict[str, Any]:
    if dataset["selected_split"] != "calibration":
        raise ExecutableDatasetValidationError("calibration may only use the calibration split")
    if provider == "mock":
        raise ExecutableDatasetValidationError("mock predictions cannot be used for product calibration")

    thresholds = [round(value / 100, 2) for value in range(50, 100)]
    candidates = [
        _score_candidate_threshold(dataset, predictions, threshold=threshold)
        for threshold in thresholds
    ]
    safe_candidates = [
        item
        for item in candidates
        if (
            item["high_confidence_error_count"] == 0
            and item["auto_accept_accuracy"] is not None
            and item["auto_accept_accuracy"] >= 0.95
        )
    ]
    if safe_candidates:
        selected = max(
            safe_candidates,
            key=lambda item: (item["auto_accept_coverage"], item["auto_accept_accuracy"], item["threshold"]),
        )
        selection_status = "selected_safe_candidate"
    else:
        zero_error = [item for item in candidates if item["high_confidence_error_count"] == 0]
        selected = max(
            zero_error or candidates,
            key=lambda item: (
                item["auto_accept_accuracy"] or 0.0,
                item["auto_accept_coverage"],
                item["threshold"],
            ),
        )
        selection_status = "no_candidate_met_all_targets"

    return {
        "mode": "calibration",
        "provider": provider,
        "dataset_version": dataset["dataset_version"],
        "split": dataset["selected_split"],
        "test_truth_used": False,
        "selection_priority": [
            "high_confidence_error_count == 0",
            "auto_accept_accuracy >= 0.95",
            "maximize auto_accept_coverage",
        ],
        "targets": {
            "high_confidence_error_count": 0,
            "auto_accept_accuracy": 0.95,
            "auto_accept_coverage": 0.7,
        },
        "selection_status": selection_status,
        "selected_policy": {
            "provider": provider,
            "policy_version": CURRENT_SPEAKER_ROLE_POLICY_VERSION,
            "auto_accept_threshold": selected["threshold"],
            "review_threshold": DEFAULT_PROVIDER_POLICIES[provider].review_threshold
            if provider in DEFAULT_PROVIDER_POLICIES
            else None,
            "target_auto_accept_coverage_met": selected["auto_accept_coverage"] >= 0.7,
            "coverage_note": (
                "Coverage target was not forced because zero high-confidence errors take priority."
                if selected["auto_accept_coverage"] < 0.7
                else "Coverage target met under safety constraints."
            ),
        },
        "selected_metrics": selected,
        "candidate_thresholds": candidates,
    }


def _score_candidate_threshold(
    dataset: dict[str, Any],
    predictions: dict[str, dict[str, Any]],
    *,
    threshold: float,
) -> dict[str, Any]:
    role_total = 0
    auto_total = 0
    auto_correct = 0
    high_confidence_errors = 0
    review_total = 0
    blocked_total = 0
    for item in dataset["samples"]:
        sample = item["manifest"]
        annotation = item["annotation"]
        prediction = predictions[sample["sample_id"]]
        truth_roles = {
            str(speaker_id): canonical_role(role)
            for speaker_id, role in annotation["speaker_roles"].items()
        }
        decisions = {
            str(decision["speaker_id"]): decision
            for decision in prediction["speaker_decisions"]
        }
        for speaker_id, truth_role in truth_roles.items():
            role_total += 1
            decision = decisions.get(speaker_id)
            action = _candidate_action(decision, threshold=threshold)
            predicted_role = canonical_role(decision["predicted_role"]) if decision else None
            if action == "auto_accept":
                auto_total += 1
                if predicted_role == truth_role:
                    auto_correct += 1
                else:
                    high_confidence_errors += 1
            elif action == "blocked":
                blocked_total += 1
            else:
                review_total += 1
    return {
        "threshold": threshold,
        "speaker_decision_count": role_total,
        "auto_accept_count": auto_total,
        "auto_accept_accuracy": _ratio(auto_correct, auto_total) if auto_total else None,
        "auto_accept_coverage": _ratio(auto_total, role_total),
        "manual_confirmation_rate": _ratio(review_total, role_total),
        "blocked_rate": _ratio(blocked_total, role_total),
        "high_confidence_error_count": high_confidence_errors,
    }


def _candidate_action(decision: dict[str, Any] | None, *, threshold: float) -> str:
    if not decision:
        return "blocked"
    if decision["action"] == "blocked":
        return "blocked"
    if decision["reason_code"] in {"single_speaker_counterexample", "mixed_utterance_candidate"}:
        return "blocked"
    calibrated = decision.get("calibrated_confidence")
    if isinstance(calibrated, (int, float)) and calibrated >= threshold:
        return "auto_accept"
    return "needs_review"


def _effective_action(
    decision: dict[str, Any] | None,
    *,
    auto_accept_threshold: float | None,
) -> str:
    if auto_accept_threshold is None:
        return decision["action"] if decision else "blocked"
    return _candidate_action(decision, threshold=auto_accept_threshold)


def render_markdown(report: dict[str, Any]) -> str:
    provider = report["providers"][0]
    provider_report = report["provider_reports"][provider]
    metrics = provider_report["metrics"]
    ci = provider_report["confidence_intervals_95"]
    lines = [
        "# executable_clinical_v1 speaker-role baseline",
        "",
        f"- dataset_version: `{report['dataset_version']}`",
        f"- schema_version: `{report['schema_version']}`",
        f"- evaluation_mode: `{report['evaluation_mode']}`",
        f"- audio_pipeline_evaluated: `{report['audio_pipeline_evaluated']}`",
        f"- evaluation_policy_override: `{report.get('evaluation_policy_override')}`",
        f"- provider: `{provider}`",
        f"- product_accuracy: `{provider_report['counts_as_product_accuracy']}`",
        f"- sample_count: {provider_report['sample_count']}",
        f"- selected_split: `{report['selected_split']}`",
        "",
        "## Metrics",
        "",
        "| metric | value | 95% CI |",
        "| --- | ---: | --- |",
    ]
    for key in [
        "role_accuracy",
        "auto_accept_accuracy",
        "auto_accept_coverage",
        "manual_confirmation_rate",
        "speaker_count_accuracy",
        "mixed_utterance_rate",
        "keyword_recall",
    ]:
        interval = ci[key]
        lines.append(f"| {key} | {metrics[key]} | [{interval['low']}, {interval['high']}] |")
    lines.extend(
        [
            f"| high_confidence_error_count | {metrics['high_confidence_error_count']} | - |",
            "",
            "## Scenario coverage",
            "",
        ]
    )
    for key, value in sorted(provider_report["scenario_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Split coverage", ""])
    for key, value in sorted(provider_report["split_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    if provider_report["high_confidence_errors"]:
        lines.extend(["", "## High confidence errors", ""])
        for item in provider_report["high_confidence_errors"]:
            lines.append(
                f"- `{item['sample_id']}` / `{item['speaker_id']}`: "
                f"expected={item['expected']}, predicted={item['predicted']}"
            )
    return "\n".join(lines) + "\n"


def write_report(report: dict[str, Any], output_path: Path, markdown_output: Path | None = None) -> None:
    write_json(output_path, report)
    markdown_path = markdown_output or output_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def canonical_role(role: Any) -> str:
    normalized = ROLE_ALIASES.get(str(role).strip().lower())
    if not normalized:
        normalized = ROLE_ALIASES.get(str(role).strip())
    if normalized not in VALID_ROLES:
        raise ExecutableDatasetValidationError(f"invalid role {role!r}")
    return normalized


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "unknown"
    commit = result.stdout.strip() or "unknown"
    dirty_checks = [
        subprocess.run(["git", "diff", "--quiet"], cwd=PROJECT_ROOT, check=False),
        subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=PROJECT_ROOT, check=False),
    ]
    if any(check.returncode != 0 for check in dirty_checks):
        return f"{commit}-dirty"
    return commit


def _build_rules_prediction(
    sample: dict[str, Any],
    annotation: dict[str, Any],
    *,
    git_commit: str,
    provider_version: str,
    policy_version: str,
) -> dict[str, Any]:
    provider = "rules"
    asr_result = _asr_result_from_truth(sample, annotation)
    asr_result = enhance_speaker_diarization(asr_result)
    asr_result = attach_speaker_role_quality(asr_result)
    quality = asr_result.role_quality
    if quality is None:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: role quality was not generated")

    decisions = []
    for decision in quality.decisions:
        item = decision.model_dump(mode="json")
        item["provider_version"] = provider_version
        item["policy_version"] = policy_version
        item["git_commit"] = git_commit
        decisions.append(item)

    return {
        "sample_id": sample["sample_id"],
        "provider": provider,
        "provider_version": provider_version,
        "policy_version": policy_version,
        "provider_config": provider_config_payload(),
        "git_commit": git_commit,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "source": "production_rules_oracle_transcript",
        "evaluation_mode": "oracle_transcript_role_decision",
        "audio_pipeline_evaluated": False,
        "predicted_speaker_count": quality.metrics.speaker_count,
        "speaker_decisions": decisions,
        "medical_keywords": sorted(_extract_keywords(asr_result.text)),
    }


def _asr_result_from_truth(sample: dict[str, Any], annotation: dict[str, Any]) -> ASRResult:
    segments = [
        ASRSegment(
            segment_id=str(turn.get("turn_id") or f"{sample['sample_id']}-turn-{index:03d}"),
            speaker=str(turn["speaker_id"]),
            speaker_id=str(turn["speaker_id"]),
            text=str(turn.get("text") or ""),
            start_time=float(turn["start_sec"]),
            end_time=float(turn["end_sec"]),
            overlap=bool(turn.get("overlap") or turn.get("mixed_utterance")),
        )
        for index, turn in enumerate(annotation["transcript"], start=1)
    ]
    text = "\n".join(segment.text for segment in segments if segment.text.strip())
    conversation_text = "\n".join(
        f"[{segment.speaker_id}] {segment.text}" for segment in segments if segment.text.strip()
    )
    return ASRResult(
        audio_id=str(sample["sample_id"]),
        engine="oracle_transcript",
        text=text,
        conversation_text=conversation_text,
        segments=segments,
        manifest_sample_id=str(sample["sample_id"]),
        scenario=str(sample["scenario_type"]),
        speaker_mode="oracle_transcript",
    )


def _infer_role_from_text(text: str, *, speaker_count: int, mixed_rate: float) -> tuple[str, float, str]:
    if speaker_count == 1:
        return "other", 0.94, "single_speaker_counterexample"

    scores = {
        "doctor": _marker_score(text, DOCTOR_MARKERS),
        "patient": _marker_score(text, PATIENT_MARKERS),
        "family": _marker_score(text, FAMILY_MARKERS),
    }
    if speaker_count >= 3 and any(marker in text for marker in STRONG_FAMILY_MARKERS):
        predicted_role = "family"
    elif speaker_count >= 3 and scores["family"] > 0 and scores["family"] >= max(scores.values()):
        predicted_role = "family"
    else:
        predicted_role = max(scores, key=lambda key: scores[key])
    score = scores[predicted_role]
    if score <= 0:
        predicted_role = "other"
        score = 1

    base = 0.62 + min(0.32, score * 0.055)
    if predicted_role == "doctor" and "?" in text:
        base += 0.03
    if predicted_role == "family" and speaker_count < 3:
        base -= 0.12
    if mixed_rate >= 0.25:
        base -= 0.07
    reason = f"rules_{predicted_role}_markers"
    if mixed_rate >= 0.25:
        reason = f"{reason}_mixed_context"
    return predicted_role, max(0.0, min(0.98, base)), reason


def _marker_score(text: str, markers: set[str]) -> int:
    return sum(text.count(marker) for marker in markers)


def _action_from_confidence(confidence: float, role: str, speaker_count: int) -> str:
    if speaker_count == 1 and role == "other":
        return "blocked"
    if confidence >= 0.9:
        return "auto_accept"
    if confidence >= 0.65:
        return "needs_review"
    return "blocked"


def _extract_keywords(text: str) -> set[str]:
    return {keyword for keyword in MEDICAL_KEYWORD_CATALOG if keyword in text}


def _load_prediction_artifacts(
    dataset: dict[str, Any],
    *,
    prediction_dir: Path,
    provider: str,
) -> dict[str, dict[str, Any]]:
    predictions: dict[str, dict[str, Any]] = {}
    for item in dataset["samples"]:
        sample_id = item["manifest"]["sample_id"]
        path = prediction_dir / f"{sample_id}.prediction.json"
        if not path.exists():
            raise ExecutableDatasetValidationError(f"{sample_id}: missing prediction artifact: {path}")
        prediction = load_json(path)
        _validate_prediction_artifact(sample_id, prediction, provider=provider)
        predictions[sample_id] = prediction
    return predictions


def _validate_truth_annotation(sample: dict[str, Any], annotation: dict[str, Any]) -> None:
    forbidden = DISALLOWED_TRUTH_KEYS & set(annotation)
    if forbidden:
        raise ExecutableDatasetValidationError(
            f"{sample['sample_id']}: truth annotation contains prediction fields: {sorted(forbidden)}"
        )
    missing = REQUIRED_TRUTH_FIELDS - set(annotation)
    if missing:
        raise ExecutableDatasetValidationError(
            f"{sample['sample_id']}: truth annotation missing fields: {sorted(missing)}"
        )
    if annotation["sample_id"] != sample["sample_id"]:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: annotation sample_id mismatch")
    if annotation["annotation_version"] != sample["annotation_version"]:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: annotation_version mismatch")

    privacy = annotation["privacy"]
    if not privacy.get("synthetic") or privacy.get("contains_real_patient_data"):
        raise ExecutableDatasetValidationError(
            f"{sample['sample_id']}: annotation must be synthetic and privacy-safe"
        )

    speaker_roles = annotation["speaker_roles"]
    if not isinstance(speaker_roles, dict) or len(speaker_roles) != int(sample["speaker_count"]):
        raise ExecutableDatasetValidationError(
            f"{sample['sample_id']}: speaker_count does not match speaker_roles"
        )
    speaker_ids = {str(speaker_id) for speaker_id in speaker_roles}
    for role in speaker_roles.values():
        canonical_role(role)

    transcript = annotation["transcript"]
    if not isinstance(transcript, list) or not transcript:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: transcript must not be empty")
    for turn in transcript:
        for key in ("turn_id", "speaker_id", "text", "start_sec", "end_sec"):
            if key not in turn:
                raise ExecutableDatasetValidationError(
                    f"{sample['sample_id']}: transcript turn missing {key}"
                )
        if str(turn["speaker_id"]) not in speaker_ids:
            raise ExecutableDatasetValidationError(
                f"{sample['sample_id']}: transcript speaker_id is not in speaker_roles"
            )

    speaker_turns = annotation["speaker_turns"]
    if not isinstance(speaker_turns, list) or not speaker_turns:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: speaker_turns must not be empty")

    if not annotation["medical_keywords"]:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: medical_keywords must not be empty")
    if not annotation["medical_record_fields"]:
        raise ExecutableDatasetValidationError(
            f"{sample['sample_id']}: medical_record_fields must not be empty"
        )
    if not annotation["evidence_spans"]:
        raise ExecutableDatasetValidationError(f"{sample['sample_id']}: evidence_spans must not be empty")


def _validate_prediction_artifact(sample_id: str, prediction: dict[str, Any], *, provider: str) -> None:
    missing = REQUIRED_PREDICTION_FIELDS - set(prediction)
    if missing:
        raise ExecutableDatasetValidationError(
            f"{sample_id}: prediction artifact missing fields: {sorted(missing)}"
        )
    if prediction["sample_id"] != sample_id:
        raise ExecutableDatasetValidationError(f"{sample_id}: prediction sample_id mismatch")
    if prediction["provider"] != provider:
        raise ExecutableDatasetValidationError(
            f"{sample_id}: prediction provider {prediction['provider']!r} does not match {provider!r}"
        )
    decisions = prediction["speaker_decisions"]
    if not isinstance(decisions, list) or not decisions:
        raise ExecutableDatasetValidationError(f"{sample_id}: speaker_decisions must be a non-empty list")

    seen_speakers: set[str] = set()
    for decision in decisions:
        missing_decision = REQUIRED_DECISION_FIELDS - set(decision)
        if missing_decision:
            raise ExecutableDatasetValidationError(
                f"{sample_id}: speaker decision missing fields: {sorted(missing_decision)}"
            )
        speaker_id = str(decision["speaker_id"])
        if speaker_id in seen_speakers:
            raise ExecutableDatasetValidationError(f"{sample_id}: duplicate speaker decision {speaker_id}")
        seen_speakers.add(speaker_id)

        if decision["provider"] != prediction["provider"]:
            raise ExecutableDatasetValidationError(f"{sample_id}: decision provider mismatch")
        if decision["provider_version"] != prediction["provider_version"]:
            raise ExecutableDatasetValidationError(f"{sample_id}: decision provider_version mismatch")
        if decision["policy_version"] != prediction["policy_version"]:
            raise ExecutableDatasetValidationError(f"{sample_id}: decision policy_version mismatch")
        if decision["git_commit"] != prediction["git_commit"]:
            raise ExecutableDatasetValidationError(f"{sample_id}: decision git_commit mismatch")

        canonical_role(decision["predicted_role"])
        if decision["action"] not in VALID_ACTIONS:
            raise ExecutableDatasetValidationError(
                f"{sample_id}: invalid action {decision['action']!r}"
            )
        for confidence_key in ("raw_confidence", "calibrated_confidence"):
            confidence = decision[confidence_key]
            if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                raise ExecutableDatasetValidationError(
                    f"{sample_id}: {confidence_key} must be between 0 and 1"
                )


def _normalize_keywords(values: list[Any]) -> list[str]:
    normalized: list[str] = []
    for value in values:
        if isinstance(value, str):
            normalized.append(value)
        elif isinstance(value, dict) and "text" in value:
            normalized.append(str(value["text"]))
        else:
            normalized.append(str(value))
    return normalized


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _wilson_interval(successes: int, total: int) -> dict[str, Any]:
    if total == 0:
        return {"low": 0.0, "high": 0.0, "numerator": successes, "denominator": total}
    z = 1.96
    phat = successes / total
    denominator = 1 + z * z / total
    centre = phat + z * z / (2 * total)
    margin = z * math.sqrt((phat * (1 - phat) + z * z / (4 * total)) / total)
    low = (centre - margin) / denominator
    high = (centre + margin) / denominator
    return {
        "low": round(max(0.0, low), 4),
        "high": round(min(1.0, high), 4),
        "numerator": successes,
        "denominator": total,
    }


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate executable clinical speaker-role data.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--provider", default="rules")
    parser.add_argument("--prediction-dir", type=Path)
    parser.add_argument("--generate-predictions", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--skip-hash-check", action="store_true")
    parser.add_argument("--split", choices=sorted(VALID_SPLIT_ARGS), default="all")
    parser.add_argument("--calibrate", action="store_true")
    parser.add_argument("--auto-accept-threshold", type=float)
    parser.add_argument("--git-commit")
    args = parser.parse_args()

    if args.calibrate and args.split != "calibration":
        print("calibration mode may only use --split calibration", file=sys.stderr)
        return 2
    if args.generate_predictions and args.provider not in GENERATION_PROVIDERS:
        print(
            f"prediction generation is only implemented for: {sorted(GENERATION_PROVIDERS)}",
            file=sys.stderr,
        )
        return 2
    if args.auto_accept_threshold is not None and not 0 <= args.auto_accept_threshold <= 1:
        print("--auto-accept-threshold must be between 0 and 1", file=sys.stderr)
        return 2

    prediction_dir = args.prediction_dir or default_prediction_dir(args.manifest, args.provider)
    try:
        dataset = load_dataset(args.manifest, verify_hashes=not args.skip_hash_check, split=args.split)
        if args.generate_predictions:
            generate_rules_prediction_artifacts(
                dataset,
                prediction_dir=prediction_dir,
                git_commit=args.git_commit,
            )
        predictions = _load_prediction_artifacts(dataset, prediction_dir=prediction_dir, provider=args.provider)
        report = evaluate_loaded_dataset(
            dataset,
            predictions=predictions,
            provider=args.provider,
            auto_accept_threshold=args.auto_accept_threshold,
        )
        if args.calibrate:
            report["calibration"] = calibrate_loaded_dataset(
                dataset,
                predictions=predictions,
                provider=args.provider,
            )
    except ExecutableDatasetValidationError as exc:
        print(f"dataset validation failed: {exc}", file=sys.stderr)
        return 2

    write_report(report, args.output, args.markdown_output)
    print(
        json.dumps(
            {
                "status": "ok",
                "provider": args.provider,
                "output": str(args.output),
                "counts_as_product_accuracy": report["counts_as_product_accuracy"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
