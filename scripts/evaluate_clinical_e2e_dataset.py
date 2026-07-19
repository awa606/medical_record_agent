from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Callable, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas import CandidateDiagnosis, MedicalField, MedicalRecordFields  # noqa: E402
from app.services import LLMProviderUnavailableError, create_llm_record_generator  # noqa: E402
from app.services.clinical_facts import ClinicalFact, extract_clinical_facts  # noqa: E402
from app.services.fever_respiratory_pack import PACK_VERSION as FEVER_RESPIRATORY_PACK_VERSION  # noqa: E402


VALID_SPLITS = {"development", "final_check"}
VALID_SPLIT_ARGS = {"all", *VALID_SPLITS}
FIELD_KEYS = [
    "chief_complaint",
    "present_illness",
    "previous_treatment",
    "accompanying_symptoms",
    "past_history",
    "allergy_history",
    "physical_exam",
]
REQUIRED_MANIFEST_FIELDS = {"dataset_version", "schema_version", "evaluation_mode", "cases"}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "split",
    "scenario_type",
    "privacy",
    "segments",
    "expected",
}
REQUIRED_SEGMENT_FIELDS = {"segment_id", "speaker_id", "role", "text"}
REQUIRED_EXPECTED_FIELDS = {
    "facts",
    "field_status",
    "required_content",
    "forbidden_content",
    "candidate_diagnoses",
    "forbidden_candidate_diagnoses",
    "follow_up_questions_any",
    "risk_signals",
    "applicable_packs",
}
CONFIRMED_DIAGNOSIS_RE = re.compile(r"(诊断为|确诊为|最终诊断)")


class ClinicalE2EEvaluationError(ValueError):
    """Raised when the clinical E2E evaluation dataset or report is invalid."""


Runner = Callable[[dict[str, Any]], dict[str, Any]]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_dataset(manifest_path: Path, *, split: str = "all") -> dict[str, Any]:
    if split not in VALID_SPLIT_ARGS:
        raise ClinicalE2EEvaluationError(f"invalid split {split!r}")

    manifest_path = manifest_path.resolve()
    manifest_dir = manifest_path.parent
    manifest = load_json(manifest_path)
    missing_manifest = REQUIRED_MANIFEST_FIELDS - set(manifest)
    if missing_manifest:
        raise ClinicalE2EEvaluationError(f"manifest missing fields: {sorted(missing_manifest)}")
    if manifest.get("evaluation_mode") != "text_to_record_disease_pack":
        raise ClinicalE2EEvaluationError("manifest.evaluation_mode must be text_to_record_disease_pack")

    case_refs = manifest.get("cases")
    if not isinstance(case_refs, list) or not case_refs:
        raise ClinicalE2EEvaluationError("manifest.cases must be a non-empty list")

    seen_ids: set[str] = set()
    all_split_counts = {key: 0 for key in sorted(VALID_SPLITS)}
    loaded: list[dict[str, Any]] = []
    for ref in case_refs:
        if not isinstance(ref, dict):
            raise ClinicalE2EEvaluationError("manifest.cases items must be objects")
        for key in ("case_id", "split", "case_path"):
            if key not in ref:
                raise ClinicalE2EEvaluationError(f"manifest case ref missing {key}")
        case_id = str(ref["case_id"])
        if case_id in seen_ids:
            raise ClinicalE2EEvaluationError(f"duplicate case_id: {case_id}")
        seen_ids.add(case_id)
        case_split = str(ref["split"])
        if case_split not in VALID_SPLITS:
            raise ClinicalE2EEvaluationError(f"{case_id}: invalid split {case_split!r}")
        all_split_counts[case_split] += 1

        case_path = (manifest_dir / str(ref["case_path"])).resolve()
        if not case_path.exists():
            raise ClinicalE2EEvaluationError(f"{case_id}: case_path does not exist: {case_path}")
        case = load_json(case_path)
        _validate_case(case, expected_case_id=case_id, expected_split=case_split)
        if split == "all" or case_split == split:
            loaded.append({"manifest": ref, "case": case, "case_path": case_path})

    if not all_split_counts["development"] or not all_split_counts["final_check"]:
        raise ClinicalE2EEvaluationError("manifest must contain both development and final_check samples")
    if not loaded:
        raise ClinicalE2EEvaluationError(f"no cases selected for split {split!r}")

    return {
        "dataset_version": manifest["dataset_version"],
        "schema_version": manifest["schema_version"],
        "evaluation_mode": manifest["evaluation_mode"],
        "manifest_path": str(manifest_path),
        "manifest_dir": str(manifest_dir),
        "selected_split": split,
        "all_split_counts": all_split_counts,
        "cases": loaded,
    }


def evaluate_dataset(
    manifest_path: Path,
    *,
    split: str = "all",
    use_env_provider: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    dataset = load_dataset(manifest_path, split=split)
    return evaluate_loaded_dataset(dataset, use_env_provider=use_env_provider, runner=runner)


def evaluate_loaded_dataset(
    dataset: dict[str, Any],
    *,
    use_env_provider: bool = False,
    runner: Runner | None = None,
) -> dict[str, Any]:
    runner = runner or _run_production_chain
    case_reports: list[dict[str, Any]] = []
    aggregate = _empty_aggregate()
    split_counts: dict[str, int] = {}
    scenario_counts: dict[str, int] = {}
    provider_traces: list[dict[str, Any]] = []

    with _provider_environment(use_env_provider):
        for item in dataset["cases"]:
            case = item["case"]
            split = str(case["split"])
            split_counts[split] = split_counts.get(split, 0) + 1
            scenario = str(case["scenario_type"])
            scenario_counts[scenario] = scenario_counts.get(scenario, 0) + 1

            actual = runner(case)
            provider_traces.append(actual["provider_trace"])
            case_report = evaluate_case(case, actual)
            case_reports.append(case_report)
            _accumulate(aggregate, case_report)

    metrics = _aggregate_metrics(aggregate)
    hard_gate = {
        "passed": all(
            metrics[key] == 0
            for key in [
                "unsupported_content_count",
                "candidate_without_evidence_count",
                "confirmed_diagnosis_phrase_count",
                "danger_signal_missed_count",
            ]
        ),
        "unsupported_content_count": metrics["unsupported_content_count"],
        "candidate_without_evidence_count": metrics["candidate_without_evidence_count"],
        "confirmed_diagnosis_phrase_count": metrics["confirmed_diagnosis_phrase_count"],
        "danger_signal_missed_count": metrics["danger_signal_missed_count"],
    }
    return {
        "dataset_version": dataset["dataset_version"],
        "schema_version": dataset["schema_version"],
        "evaluation_mode": dataset["evaluation_mode"],
        "audio_pipeline_evaluated": False,
        "selected_split": dataset["selected_split"],
        "manifest_path": _display_path(Path(dataset["manifest_path"])),
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "sample_count": len(case_reports),
        "split_counts": split_counts,
        "all_split_counts": dataset["all_split_counts"],
        "scenario_counts": scenario_counts,
        "fever_respiratory_pack_version": FEVER_RESPIRATORY_PACK_VERSION,
        "provider_mode": "environment" if use_env_provider else "demo_mock_default",
        "provider_traces": _summarize_provider_traces(provider_traces),
        "metrics": metrics,
        "hard_gates": hard_gate,
        "cases": case_reports,
        "notes": [
            "This report evaluates text/role segments to clinical fields and disease-pack references.",
            "It does not evaluate ASR, diarization, speaker-role calibration, browser recording, or edge deployment.",
            "final_check cases are reported separately and must not be used to tune rules after freezing.",
        ],
    }


def evaluate_case(case: dict[str, Any], actual: dict[str, Any]) -> dict[str, Any]:
    expected = case["expected"]
    facts = actual["facts"]
    fields = actual["fields"]
    candidates = actual["candidate_diagnoses"]
    draft = actual.get("draft") or ""

    fact_results = [_evaluate_fact(expected_fact, facts) for expected_fact in expected["facts"]]
    field_status_results = [
        {
            "field": key,
            "expected": status,
            "actual": _field_dict(fields, key).get("status"),
            "matched": _field_dict(fields, key).get("status") == status,
        }
        for key, status in expected["field_status"].items()
    ]
    required_content_results = [
        _evaluate_required_content(item, fields=fields, candidates=candidates, draft=draft)
        for item in expected["required_content"]
    ]
    forbidden_content_results = [
        _evaluate_forbidden_content(item, fields=fields, candidates=candidates, draft=draft)
        for item in expected["forbidden_content"]
    ]
    candidate_results = [
        _evaluate_expected_candidate(item, candidates)
        for item in expected["candidate_diagnoses"]
    ]
    forbidden_candidate_results = [
        _evaluate_forbidden_candidate(item, candidates)
        for item in expected["forbidden_candidate_diagnoses"]
    ]
    follow_up_results = [
        _evaluate_text_any(question, _candidate_texts(candidates, "follow_up_questions"))
        for question in expected["follow_up_questions_any"]
    ]
    risk_signal_results = [
        _evaluate_risk_signal(signal, candidates)
        for signal in expected["risk_signals"]
    ]

    non_missing_fields = [
        _field_dict(fields, key)
        for key in FIELD_KEYS
        if not _field_dict(fields, key).get("missing")
    ]
    field_with_evidence_count = sum(1 for field in non_missing_fields if field.get("source_spans"))
    field_with_fact_ids_count = sum(1 for field in non_missing_fields if field.get("fact_ids"))
    candidate_without_evidence = [
        candidate["name"]
        for candidate in candidates
        if not candidate.get("evidence")
    ]
    all_output_text = _all_output_text(fields=fields, candidates=candidates, draft=draft)
    confirmed_diagnosis_phrases = CONFIRMED_DIAGNOSIS_RE.findall(all_output_text)
    unexpected_fever_pack_candidates = [
        candidate["name"]
        for candidate in candidates
        if _is_fever_pack_candidate(candidate)
        and candidate["name"] not in {item["name"] for item in expected["candidate_diagnoses"]}
    ]

    hard_gate_failures = []
    hard_gate_failures.extend(
        f"unsupported_content:{item['text']}" for item in forbidden_content_results if item["found"]
    )
    hard_gate_failures.extend(
        f"candidate_without_evidence:{name}" for name in candidate_without_evidence
    )
    hard_gate_failures.extend(
        f"confirmed_diagnosis_phrase:{phrase}" for phrase in confirmed_diagnosis_phrases
    )
    hard_gate_failures.extend(
        f"danger_signal_missed:{item['name']}" for item in risk_signal_results if not item["warned"]
    )

    return {
        "case_id": case["case_id"],
        "split": case["split"],
        "scenario_type": case["scenario_type"],
        "applicable_packs": expected["applicable_packs"],
        "conversation_text": actual["conversation_text"],
        "provider_trace": actual["provider_trace"],
        "actual": {
            "facts": facts,
            "field_status": {key: _field_dict(fields, key).get("status") for key in FIELD_KEYS},
            "candidate_diagnoses": candidates,
        },
        "checks": {
            "facts": fact_results,
            "field_status": field_status_results,
            "required_content": required_content_results,
            "forbidden_content": forbidden_content_results,
            "candidate_diagnoses": candidate_results,
            "forbidden_candidate_diagnoses": forbidden_candidate_results,
            "follow_up_questions": follow_up_results,
            "risk_signals": risk_signal_results,
        },
        "counts": {
            "expected_fact_total": len(fact_results),
            "expected_fact_matched": sum(1 for item in fact_results if item["matched"]),
            "assertion_fact_total": sum(
                1 for item in fact_results if item["expected"].get("assertion") in {"absent", "resolved"}
            ),
            "assertion_fact_matched": sum(
                1
                for item in fact_results
                if item["expected"].get("assertion") in {"absent", "resolved"} and item["matched"]
            ),
            "field_status_total": len(field_status_results),
            "field_status_correct": sum(1 for item in field_status_results if item["matched"]),
            "required_content_total": len(required_content_results),
            "required_content_hit": sum(1 for item in required_content_results if item["matched"]),
            "unsupported_content_count": sum(1 for item in forbidden_content_results if item["found"]),
            "expected_candidate_total": len(candidate_results),
            "expected_candidate_hit": sum(1 for item in candidate_results if item["matched"]),
            "actual_candidate_total": len(candidates),
            "candidate_with_evidence_count": sum(1 for item in candidates if item.get("evidence")),
            "candidate_without_evidence_count": len(candidate_without_evidence),
            "unexpected_fever_pack_candidate_count": len(unexpected_fever_pack_candidates),
            "follow_up_total": len(follow_up_results),
            "follow_up_hit": sum(1 for item in follow_up_results if item["matched"]),
            "risk_signal_total": len(risk_signal_results),
            "risk_signal_warned": sum(1 for item in risk_signal_results if item["warned"]),
            "danger_signal_missed_count": sum(1 for item in risk_signal_results if not item["warned"]),
            "non_missing_field_count": len(non_missing_fields),
            "field_with_evidence_count": field_with_evidence_count,
            "field_with_fact_ids_count": field_with_fact_ids_count,
            "confirmed_diagnosis_phrase_count": len(confirmed_diagnosis_phrases),
        },
        "hard_gate_passed": not hard_gate_failures,
        "hard_gate_failures": hard_gate_failures,
    }


def write_report(report: dict[str, Any], output_path: Path, markdown_output: Path | None = None) -> None:
    write_json(output_path, report)
    markdown_path = markdown_output or output_path.with_suffix(".md")
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    hard_gates = report["hard_gates"]
    lines = [
        "# field_disease_pack_v1 baseline",
        "",
        f"- dataset_version: `{report['dataset_version']}`",
        f"- schema_version: `{report['schema_version']}`",
        f"- evaluation_mode: `{report['evaluation_mode']}`",
        f"- audio_pipeline_evaluated: `{report['audio_pipeline_evaluated']}`",
        f"- sample_count: {report['sample_count']}",
        f"- selected_split: `{report['selected_split']}`",
        f"- provider_mode: `{report['provider_mode']}`",
        f"- hard_gate_passed: `{hard_gates['passed']}`",
        "",
        "## Metrics",
        "",
        "| metric | value |",
        "| --- | ---: |",
    ]
    for key in [
        "clinical_fact_accuracy",
        "assertion_accuracy",
        "field_status_accuracy",
        "field_content_accuracy",
        "field_evidence_coverage",
        "field_fact_link_coverage",
        "candidate_recall",
        "candidate_evidence_completeness",
        "follow_up_question_recall",
        "danger_signal_recall",
        "unsupported_content_count",
        "candidate_without_evidence_count",
        "confirmed_diagnosis_phrase_count",
        "danger_signal_missed_count",
        "unexpected_fever_pack_candidate_count",
    ]:
        lines.append(f"| {key} | {metrics[key]} |")
    lines.extend(["", "## Split coverage", ""])
    for key, value in sorted(report["split_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## Scenario coverage", ""])
    for key, value in sorted(report["scenario_counts"].items()):
        lines.append(f"- `{key}`: {value}")
    failing_cases = [case for case in report["cases"] if not case["hard_gate_passed"]]
    lines.extend(["", "## Hard Gate Failures", ""])
    if not failing_cases:
        lines.append("- None")
    else:
        for case in failing_cases:
            lines.append(f"- `{case['case_id']}`: {', '.join(case['hard_gate_failures'])}")
    lines.extend(["", "## Notes", ""])
    lines.extend(f"- {item}" for item in report["notes"])
    return "\n".join(lines) + "\n"


def _validate_case(case: dict[str, Any], *, expected_case_id: str, expected_split: str) -> None:
    missing = REQUIRED_CASE_FIELDS - set(case)
    if missing:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: case missing fields: {sorted(missing)}")
    if case["case_id"] != expected_case_id:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: case_id mismatch")
    if case["split"] != expected_split:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: split mismatch")
    if case["split"] not in VALID_SPLITS:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: invalid split {case['split']!r}")

    privacy = case["privacy"]
    if not isinstance(privacy, dict) or not privacy.get("synthetic") or privacy.get("contains_real_patient_data"):
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: cases must be synthetic and privacy-safe")

    segments = case["segments"]
    if not isinstance(segments, list) or not segments:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: segments must be a non-empty list")
    seen_segments: set[str] = set()
    for segment in segments:
        missing_segment = REQUIRED_SEGMENT_FIELDS - set(segment)
        if missing_segment:
            raise ClinicalE2EEvaluationError(
                f"{expected_case_id}: segment missing fields: {sorted(missing_segment)}"
            )
        segment_id = str(segment["segment_id"])
        if segment_id in seen_segments:
            raise ClinicalE2EEvaluationError(f"{expected_case_id}: duplicate segment_id {segment_id}")
        seen_segments.add(segment_id)
        if not str(segment["text"]).strip():
            raise ClinicalE2EEvaluationError(f"{expected_case_id}: segment text must not be empty")

    expected = case["expected"]
    if not isinstance(expected, dict):
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: expected must be an object")
    missing_expected = REQUIRED_EXPECTED_FIELDS - set(expected)
    if missing_expected:
        raise ClinicalE2EEvaluationError(
            f"{expected_case_id}: expected missing fields: {sorted(missing_expected)}"
        )
    if not isinstance(expected["field_status"], dict):
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: expected.field_status must be an object")
    invalid_fields = set(expected["field_status"]) - set(FIELD_KEYS)
    if invalid_fields:
        raise ClinicalE2EEvaluationError(f"{expected_case_id}: invalid field keys: {sorted(invalid_fields)}")


def _run_production_chain(case: dict[str, Any]) -> dict[str, Any]:
    conversation_text = _conversation_text(case["segments"])
    generator = create_llm_record_generator()
    fields = generator.extract_fields(conversation_text)
    draft = generator.generate_draft(fields)
    facts = extract_clinical_facts(conversation_text)
    return {
        "conversation_text": conversation_text,
        "facts": [_fact_to_dict(fact) for fact in facts],
        "fields": fields.model_dump(mode="json"),
        "candidate_diagnoses": [
            diagnosis.model_dump(mode="json") for diagnosis in fields.candidate_diagnoses
        ],
        "draft": draft,
        "provider_trace": generator.get_trace(),
    }


@contextlib.contextmanager
def _provider_environment(use_env_provider: bool) -> Iterable[None]:
    if use_env_provider:
        yield
        return
    managed = {
        "RECORD_PROVIDER_MODE": "demo",
        "LLM_PROVIDER": "mock",
    }
    previous = {key: os.environ.get(key) for key in managed}
    try:
        for key, value in managed.items():
            os.environ[key] = value
        yield
    finally:
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _conversation_text(segments: list[dict[str, Any]]) -> str:
    lines = []
    for segment in segments:
        role = str(segment.get("role") or "未知")
        text = str(segment["text"]).strip()
        lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def _fact_to_dict(fact: ClinicalFact | dict[str, Any]) -> dict[str, Any]:
    if isinstance(fact, dict):
        return dict(fact)
    return {
        "fact_id": fact.fact_id,
        "type": fact.type,
        "name": fact.name,
        "assertion": fact.assertion,
        "value": fact.value,
        "unit": fact.unit,
        "evidence": fact.evidence,
        "source_span": fact.source_span.model_dump(mode="json"),
    }


def _evaluate_fact(expected: dict[str, Any], actual_facts: list[dict[str, Any]]) -> dict[str, Any]:
    matched = [
        fact for fact in actual_facts
        if all(fact.get(key) == value for key, value in expected.items() if value is not None)
    ]
    return {"expected": expected, "matched": bool(matched), "actual_matches": matched[:3]}


def _field_dict(fields: dict[str, Any] | MedicalRecordFields, key: str) -> dict[str, Any]:
    if isinstance(fields, MedicalRecordFields):
        field = getattr(fields, key)
        return field.model_dump(mode="json")
    return dict(fields.get(key) or {})


def _evaluate_required_content(
    item: dict[str, Any],
    *,
    fields: dict[str, Any],
    candidates: list[dict[str, Any]],
    draft: str,
) -> dict[str, Any]:
    target = str(item["target"])
    expected_values = [str(value) for value in item.get("contains", [])]
    text = _target_text(target, fields=fields, candidates=candidates, draft=draft)
    missing = [value for value in expected_values if value not in text]
    return {
        "target": target,
        "contains": expected_values,
        "matched": not missing,
        "missing": missing,
    }


def _evaluate_forbidden_content(
    item: str | dict[str, Any],
    *,
    fields: dict[str, Any],
    candidates: list[dict[str, Any]],
    draft: str,
) -> dict[str, Any]:
    if isinstance(item, dict):
        text = str(item.get("contains") or item.get("text") or "")
        target = str(item.get("target") or "all")
    else:
        text = str(item)
        target = "all"
    haystack = _target_text(target, fields=fields, candidates=candidates, draft=draft)
    return {"target": target, "text": text, "found": bool(text and text in haystack)}


def _evaluate_expected_candidate(
    item: dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    matched = [
        candidate for candidate in candidates
        if candidate.get("name") == item.get("name")
        and (not item.get("rule_id") or candidate.get("rule_id") == item.get("rule_id"))
    ]
    requires_evidence = bool(item.get("requires_evidence", True))
    has_evidence = bool(matched and matched[0].get("evidence"))
    return {
        "name": item.get("name"),
        "rule_id": item.get("rule_id"),
        "matched": bool(matched) and (has_evidence or not requires_evidence),
        "has_evidence": has_evidence,
    }


def _evaluate_forbidden_candidate(
    item: str | dict[str, Any],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    name = str(item.get("name") if isinstance(item, dict) else item)
    found = any(candidate.get("name") == name for candidate in candidates)
    return {"name": name, "found": found}


def _evaluate_text_any(expected: str | dict[str, Any], values: list[str]) -> dict[str, Any]:
    if isinstance(expected, dict):
        name = str(expected.get("name") or expected.get("text") or "")
        keywords = [str(value) for value in expected.get("keywords", [])] or [name]
    else:
        name = str(expected)
        keywords = [name]
    haystack = "\n".join(values)
    matched = any(keyword and keyword in haystack for keyword in keywords)
    return {"name": name, "keywords": keywords, "matched": matched}


def _evaluate_risk_signal(signal: dict[str, Any], candidates: list[dict[str, Any]]) -> dict[str, Any]:
    warnings = _candidate_texts(candidates, "risk_warnings")
    keywords = [str(value) for value in signal.get("warning_keywords", [])]
    warned = bool(keywords and any(keyword in "\n".join(warnings) for keyword in keywords))
    return {
        "name": signal.get("name"),
        "warning_keywords": keywords,
        "warned": warned,
    }


def _target_text(
    target: str,
    *,
    fields: dict[str, Any],
    candidates: list[dict[str, Any]],
    draft: str,
) -> str:
    if target == "all":
        return _all_output_text(fields=fields, candidates=candidates, draft=draft)
    if target in FIELD_KEYS:
        field = _field_dict(fields, target)
        return "\n".join(
            [
                str(field.get("value") or ""),
                str(field.get("hint") or ""),
                "\n".join(str(item) for item in field.get("missing_elements") or []),
            ]
        )
    if target in {"candidate_diagnoses", "diagnoses"}:
        return _candidate_all_text(candidates)
    if target == "follow_up_questions":
        return "\n".join(_candidate_texts(candidates, "follow_up_questions"))
    if target == "risk_warnings":
        return "\n".join(_candidate_texts(candidates, "risk_warnings"))
    if target == "suggested_checks":
        return "\n".join(_candidate_texts(candidates, "suggested_checks"))
    if target == "draft":
        return draft
    raise ClinicalE2EEvaluationError(f"unknown required/forbidden content target {target!r}")


def _all_output_text(*, fields: dict[str, Any], candidates: list[dict[str, Any]], draft: str) -> str:
    parts = [draft]
    for key in FIELD_KEYS:
        field = _field_dict(fields, key)
        parts.extend(
            [
                str(field.get("value") or ""),
                str(field.get("hint") or ""),
                "\n".join(str(item) for item in field.get("missing_elements") or []),
            ]
        )
    parts.append(_candidate_all_text(candidates))
    return "\n".join(parts)


def _candidate_all_text(candidates: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for candidate in candidates:
        parts.extend(
            [
                str(candidate.get("name") or ""),
                str(candidate.get("status") or ""),
                str(candidate.get("reason") or ""),
                str(candidate.get("rule_id") or ""),
            ]
        )
        for key in ["suggested_checks", "medication_notes", "risk_warnings", "follow_up_questions"]:
            parts.extend(str(item) for item in candidate.get(key) or [])
        for span in candidate.get("evidence") or []:
            parts.append(str(span.get("text") or ""))
    return "\n".join(parts)


def _candidate_texts(candidates: list[dict[str, Any]], key: str) -> list[str]:
    values: list[str] = []
    for candidate in candidates:
        values.extend(str(item) for item in candidate.get(key) or [])
    return values


def _is_fever_pack_candidate(candidate: dict[str, Any]) -> bool:
    rule_id = str(candidate.get("rule_id") or "")
    reason = str(candidate.get("reason") or "")
    return rule_id.startswith("FEVER_RESP_V1_") or FEVER_RESPIRATORY_PACK_VERSION in reason


def _empty_aggregate() -> dict[str, int]:
    return {
        "expected_fact_total": 0,
        "expected_fact_matched": 0,
        "assertion_fact_total": 0,
        "assertion_fact_matched": 0,
        "field_status_total": 0,
        "field_status_correct": 0,
        "required_content_total": 0,
        "required_content_hit": 0,
        "unsupported_content_count": 0,
        "expected_candidate_total": 0,
        "expected_candidate_hit": 0,
        "actual_candidate_total": 0,
        "candidate_with_evidence_count": 0,
        "candidate_without_evidence_count": 0,
        "unexpected_fever_pack_candidate_count": 0,
        "follow_up_total": 0,
        "follow_up_hit": 0,
        "risk_signal_total": 0,
        "risk_signal_warned": 0,
        "danger_signal_missed_count": 0,
        "non_missing_field_count": 0,
        "field_with_evidence_count": 0,
        "field_with_fact_ids_count": 0,
        "confirmed_diagnosis_phrase_count": 0,
    }


def _accumulate(aggregate: dict[str, int], case_report: dict[str, Any]) -> None:
    for key, value in case_report["counts"].items():
        aggregate[key] = aggregate.get(key, 0) + int(value)


def _aggregate_metrics(counts: dict[str, int]) -> dict[str, Any]:
    return {
        "clinical_fact_accuracy": _ratio(counts["expected_fact_matched"], counts["expected_fact_total"]),
        "assertion_accuracy": _ratio(counts["assertion_fact_matched"], counts["assertion_fact_total"]),
        "field_status_accuracy": _ratio(counts["field_status_correct"], counts["field_status_total"]),
        "field_content_accuracy": _ratio(counts["required_content_hit"], counts["required_content_total"]),
        "field_evidence_coverage": _ratio(counts["field_with_evidence_count"], counts["non_missing_field_count"]),
        "field_fact_link_coverage": _ratio(counts["field_with_fact_ids_count"], counts["non_missing_field_count"]),
        "candidate_recall": _ratio(counts["expected_candidate_hit"], counts["expected_candidate_total"]),
        "candidate_evidence_completeness": _ratio(
            counts["candidate_with_evidence_count"], counts["actual_candidate_total"]
        ),
        "follow_up_question_recall": _ratio(counts["follow_up_hit"], counts["follow_up_total"]),
        "danger_signal_recall": _ratio(counts["risk_signal_warned"], counts["risk_signal_total"]),
        **counts,
    }


def _ratio(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _summarize_provider_traces(traces: list[dict[str, Any]]) -> dict[str, Any]:
    providers = sorted({str(trace.get("llm_provider")) for trace in traces if trace})
    actual_providers = sorted({str(trace.get("actual_provider")) for trace in traces if trace})
    models = sorted({str(trace.get("model")) for trace in traces if trace})
    fallback_count = sum(1 for trace in traces if trace.get("fallback"))
    reasons = sorted({str(trace.get("fallback_reason")) for trace in traces if trace.get("fallback_reason")})
    modes = sorted({str(trace.get("mode")) for trace in traces if trace})
    return {
        "requested_providers": providers,
        "actual_providers": actual_providers,
        "models": models,
        "modes": modes,
        "fallback_count": fallback_count,
        "fallback_reasons": reasons,
    }


def _display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate text-to-record clinical field and disease-pack data.")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path)
    parser.add_argument("--split", choices=sorted(VALID_SPLIT_ARGS), default="all")
    parser.add_argument("--use-env-provider", action="store_true")
    parser.add_argument("--fail-on-hard-gate", action="store_true")
    args = parser.parse_args()

    try:
        report = evaluate_dataset(
            args.manifest,
            split=args.split,
            use_env_provider=args.use_env_provider,
        )
    except (ClinicalE2EEvaluationError, LLMProviderUnavailableError) as exc:
        print(f"clinical e2e evaluation failed: {exc}", file=sys.stderr)
        return 2

    write_report(report, args.output, args.markdown_output)
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(args.output),
                "sample_count": report["sample_count"],
                "hard_gate_passed": report["hard_gates"]["passed"],
            },
            ensure_ascii=False,
        )
    )
    if args.fail_on_hard_gate and not report["hard_gates"]["passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
