from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.evaluate_clinical_e2e_dataset import (
    ClinicalE2EEvaluationError,
    evaluate_loaded_dataset,
    load_dataset,
)


DATASET_MANIFEST = Path("data/clinical_e2e/field_disease_pack_v1/manifest.json")
SCRIPT_PATH = Path("scripts/evaluate_clinical_e2e_dataset.py")


def test_seed_dataset_has_development_and_final_check_splits() -> None:
    dataset = load_dataset(DATASET_MANIFEST)

    assert dataset["dataset_version"] == "field_disease_pack_v1"
    assert dataset["evaluation_mode"] == "text_to_record_disease_pack"
    assert dataset["all_split_counts"] == {"development": 40, "final_check": 20}
    assert len(dataset["cases"]) == 60


def test_seed_dataset_split_filter_keeps_final_check_separate() -> None:
    final_check = load_dataset(DATASET_MANIFEST, split="final_check")
    development = load_dataset(DATASET_MANIFEST, split="development")

    assert {item["case"]["split"] for item in final_check["cases"]} == {"final_check"}
    assert {item["case"]["split"] for item in development["cases"]} == {"development"}
    assert not {item["case"]["case_id"] for item in final_check["cases"]} & {
        item["case"]["case_id"] for item in development["cases"]
    }


def test_cli_writes_json_report(tmp_path: Path) -> None:
    output = tmp_path / "clinical_e2e_report.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--manifest",
            str(DATASET_MANIFEST),
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["sample_count"] == 60
    assert report["audio_pipeline_evaluated"] is False
    assert "clinical_fact_accuracy" in report["metrics"]
    assert "hard_gates" in report
    assert report["split_counts"] == {"development": 40, "final_check": 20}


def test_invalid_case_split_fails_validation(tmp_path: Path) -> None:
    case_path = tmp_path / "bad.json"
    case_path.write_text(
        json.dumps(
            {
                "case_id": "bad-case",
                "split": "training",
                "scenario_type": "bad",
                "privacy": {"synthetic": True, "contains_real_patient_data": False},
                "segments": [{"segment_id": "seg-1", "speaker_id": "spk1", "role": "患者", "text": "我发烧。"}],
                "expected": _minimal_expected(),
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_version": "unit",
                "schema_version": "unit",
                "evaluation_mode": "text_to_record_disease_pack",
                "cases": [{"case_id": "bad-case", "split": "training", "case_path": "bad.json"}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ClinicalE2EEvaluationError, match="invalid split"):
        load_dataset(manifest_path)


def test_hard_gate_reports_forbidden_content_candidate_evidence_and_danger_signal() -> None:
    case = {
        "case_id": "unit-hard-gate",
        "split": "development",
        "scenario_type": "danger_signal",
        "privacy": {"synthetic": True, "contains_real_patient_data": False},
        "segments": [{"segment_id": "seg-1", "speaker_id": "spk1", "role": "患者", "text": "发热39度，胸痛。"}],
        "expected": {
            **_minimal_expected(),
            "forbidden_content": ["编造病程"],
            "candidate_diagnoses": [{"name": "发热待查", "requires_evidence": True}],
            "risk_signals": [{"name": "chest_pain", "warning_keywords": ["胸痛"]}],
        },
    }
    dataset = {
        "dataset_version": "unit",
        "schema_version": "unit",
        "evaluation_mode": "text_to_record_disease_pack",
        "manifest_path": str(DATASET_MANIFEST),
        "selected_split": "all",
        "all_split_counts": {"development": 1, "final_check": 1},
        "cases": [{"manifest": {"case_id": "unit-hard-gate"}, "case": case, "case_path": Path("unit.json")}],
    }

    report = evaluate_loaded_dataset(dataset, runner=_fake_unsafe_runner)

    assert report["hard_gates"]["passed"] is False
    assert report["metrics"]["unsupported_content_count"] == 1
    assert report["metrics"]["candidate_without_evidence_count"] == 1
    assert report["metrics"]["confirmed_diagnosis_phrase_count"] == 1
    assert report["metrics"]["danger_signal_missed_count"] == 1


def test_duplicate_case_id_fails_validation(tmp_path: Path) -> None:
    case = {
        "case_id": "dup",
        "split": "development",
        "scenario_type": "unit",
        "privacy": {"synthetic": True, "contains_real_patient_data": False},
        "segments": [{"segment_id": "seg-1", "speaker_id": "spk1", "role": "患者", "text": "我发烧。"}],
        "expected": _minimal_expected(),
    }
    (tmp_path / "case.json").write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "dataset_version": "unit",
                "schema_version": "unit",
                "evaluation_mode": "text_to_record_disease_pack",
                "cases": [
                    {"case_id": "dup", "split": "development", "case_path": "case.json"},
                    {"case_id": "dup", "split": "final_check", "case_path": "case.json"},
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with pytest.raises(ClinicalE2EEvaluationError, match="duplicate case_id"):
        load_dataset(manifest_path)


def _minimal_expected() -> dict:
    return {
        "facts": [],
        "field_status": {},
        "required_content": [],
        "forbidden_content": [],
        "candidate_diagnoses": [],
        "forbidden_candidate_diagnoses": [],
        "follow_up_questions_any": [],
        "risk_signals": [],
        "applicable_packs": [],
    }


def _fake_unsafe_runner(_case: dict) -> dict:
    missing_field = {
        "value": None,
        "missing": True,
        "status": "missing",
        "hint": "建议补问",
        "confidence": None,
        "source_spans": [],
        "missing_elements": [],
        "fact_ids": [],
        "confirmed_by_doctor": False,
    }
    fields = {
        key: dict(missing_field)
        for key in [
            "chief_complaint",
            "present_illness",
            "previous_treatment",
            "accompanying_symptoms",
            "past_history",
            "allergy_history",
            "physical_exam",
        ]
    }
    fields["chief_complaint"] = {
        "value": "发热三天，编造病程",
        "missing": False,
        "status": "partial",
        "hint": None,
        "confidence": 0.5,
        "source_spans": [{"text": "发热39度，胸痛。", "index": 0}],
        "missing_elements": ["持续时间"],
        "fact_ids": ["fact-1"],
        "confirmed_by_doctor": False,
    }
    return {
        "conversation_text": "[患者] 发热39度，胸痛。",
        "facts": [{"type": "symptom", "name": "发热", "assertion": "present"}],
        "fields": fields,
        "candidate_diagnoses": [
            {
                "name": "发热待查",
                "status": "候选/待医生确认",
                "evidence": [],
                "reason": "缺少证据的候选",
                "rule_id": "FEVER_RESP_V1_FEVER_WORKUP",
                "confidence": 0.7,
                "suggested_checks": [],
                "medication_notes": [],
                "risk_warnings": [],
                "follow_up_questions": [],
                "confirmed_by_doctor": False,
            }
        ],
        "draft": "诊断为发热待查，存在编造病程。",
        "provider_trace": {"llm_provider": "mock", "actual_provider": "mock", "model": "unit", "mode": "demo"},
    }
