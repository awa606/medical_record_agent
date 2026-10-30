import io
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.schemas import MedicalRecordFields
from app.services.llm.ollama_provider import OllamaLLMProvider
from scripts.experiments.compare_local_models import capture_production_call, comparison_verdict, explicit_no_facts_refusal, quality_checks


def blank():
    return MedicalRecordFields.model_validate({})


def test_missing_case11_is_failure_not_evaluator_exception():
    assert not all(quality_checks("case11", blank(), "患者：头痛。").values())


def test_whole_sentence_in_every_field_cannot_pass_as_understanding():
    source = "患者今天发热三十八点二度，伴有咳嗽和咽痛，没有胸痛，也没有药物过敏史。"
    field = {"value": source, "missing": False, "source_spans": [{"text": source, "index": 0}]}
    fields = MedicalRecordFields.model_validate({key: field for key in (
        "chief_complaint", "present_illness", "previous_treatment", "accompanying_symptoms",
        "past_history", "allergy_history", "physical_exam")})
    assert quality_checks("realtek13", fields, source)["citations_match_input_and_index"]
    assert not quality_checks("realtek13", fields, source)["four_expected_fields"]


def test_accurately_quoted_doctor_question_is_still_not_patient_fact():
    fields = MedicalRecordFields.model_validate({"chief_complaint": {
        "value": "有没有胸痛", "missing": False, "source_spans": [{"text": "有没有胸痛", "index": 0}]}})
    assert not quality_checks("question", fields, "医生：有没有胸痛？")["no_patient_fact"]


def test_allergy_does_not_count_as_prior_treatment():
    fields = MedicalRecordFields.model_validate({"previous_treatment": {
        "value": "没有花生过敏", "missing": False, "source_spans": [{"text": "没有花生过敏", "index": 0}]}})
    assert not quality_checks("negative_allergy", fields, "患者：我没有花生过敏。")["allergy_only"]


def test_capture_preserves_production_payload_only_model_differs():
    requests = []
    def transport(req, **kwargs):
        if isinstance(req, str):
            return io.BytesIO(json.dumps({"models": [{"name": m, "digest": "a" * 64}
                for m in ["qwen3:4b", "qwen3:8b"]]}).encode())
        requests.append(json.loads(req.data))
        return io.BytesIO(json.dumps({"message": {"content": "{}"}, "done_reason": "stop"}).encode())
    with patch("urllib.request.urlopen", side_effect=transport):
        for model in ["qwen3:4b", "qwen3:8b"]:
            result, error, captured = capture_production_call(
                OllamaLLMProvider(base_url="http://isolated:11434", model=model), "患者：头痛。", 10)
            assert result.content == "{}" and error is None and len(captured) == 1
    assert requests[0].pop("model") == "qwen3:4b"
    assert requests[1].pop("model") == "qwen3:8b"
    assert requests[0] == requests[1]
    assert requests[0]["options"] == {"temperature": 0, "num_ctx": 8192, "num_predict": 2048}


def test_truncation_keeps_raw_response_and_does_not_retry():
    def transport(req, **kwargs):
        if isinstance(req, str):
            return io.BytesIO(b'{"models":[]}')
        return io.BytesIO(b'{"message":{"content":"{}"},"done_reason":"length"}')
    with patch("urllib.request.urlopen", side_effect=transport):
        result, error, captured = capture_production_call(
            OllamaLLMProvider(base_url="http://isolated:11434", model="qwen3:4b"), "患者：头痛。", 10)
    assert result is None and "LLM_OUTPUT_TRUNCATED" in error
    assert len(captured) == 1 and captured[0]["response"]["done_reason"] == "length"


def test_comparison_rejects_pipeline_fact_loss_even_when_first_output_passes(tmp_path, monkeypatch):
    """The runner's aggregate must include the actual Generator result."""
    from scripts.experiments import compare_local_models as comparison

    source = "患者：我没有花生过敏。"
    raw = {"allergy_history": {"value": "我没有花生过敏", "missing": False,
        "source_spans": [{"text": "我没有花生过敏", "index": 0}]}}

    class LosesAllergy:
        def __init__(self, provider, **kwargs):
            self.provider = provider
            self.field_repairs = []

        def extract_fields(self, text):
            self.provider.calls += 1
            return blank()

    monkeypatch.setattr(comparison, "inputs", lambda: [("negative_allergy", source, [], None)])
    monkeypatch.setattr(comparison, "anonymize_text", lambda text: text)
    monkeypatch.setattr(comparison, "ground_fields", lambda fields, *args: fields)
    monkeypatch.setattr(comparison, "LLMRecordGenerator", LosesAllergy)
    monkeypatch.setattr(comparison, "OllamaLLMProvider", lambda **kwargs: object())
    monkeypatch.setattr(comparison.request, "urlopen", lambda *args, **kwargs: io.BytesIO(
        json.dumps({"models": [{"name": "qwen3:4b", "digest": "a" * 64}]}).encode()))
    monkeypatch.setattr(comparison, "capture_production_call", lambda *args: (
        SimpleNamespace(content=json.dumps(raw)), None,
        [{"request": {"model": "qwen3:4b"}, "response": {"done_reason": "stop"}}]))
    output = tmp_path / "comparison"
    monkeypatch.setattr("sys.argv", ["compare", "--model", "qwen3:4b", "--url", "http://unused",
        "--expected-digest", "a" * 64, "--output", str(output), "--base-sha", "b" * 40,
        "--deadline", "2099-01-01T00:00:00+00:00"])

    comparison.main()

    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert all(all(row["first_output_checks"].values()) for row in report["calls"])
    assert report["passed"] == 0
    assert report["stage_counts"]["first_output_passed"] == 3
    assert report["stage_counts"]["pipeline_passed"] == 0


@pytest.mark.parametrize("key", ["question", "family"])
def test_expected_refusal_is_separate_from_a_generated_draft(key):
    from app.services.llm.llm_record_generator import ExtractionOutputError

    fields = blank()
    result = comparison_verdict(key, "医生：有没有胸痛？", fields,
        quality_checks(key, fields, "医生：有没有胸痛？"), {},
        pipeline_error=ExtractionOutputError("LLM_NO_SUPPORTED_FACTS: 未找到可用病历信息"))
    assert result["passed"] and result["expected_safe_refusal"]
    assert not result["generated_draft"]


@pytest.mark.parametrize("error", [
    ValueError("LLM_NO_SUPPORTED_FACTS: wrong exception type"),
    RuntimeError("network unavailable"),
    None,
])
def test_other_failures_are_not_successful_refusals(error):
    result = comparison_verdict("question", "医生：有没有胸痛？", blank(),
        {"no_patient_fact": True}, {}, pipeline_error=error)
    assert not result["passed"]
    assert not result["expected_safe_refusal"]


def test_empty_contradiction_and_false_raw_facts_cannot_count_as_refusal():
    from app.services.llm.llm_record_generator import ExtractionOutputError

    error = ExtractionOutputError("LLM_OUTPUT_CONTRADICTION: all fields rejected")
    assert not comparison_verdict("family", "患者：我父亲发热。", blank(),
        {"no_patient_fact": True}, {}, pipeline_error=error)["passed"]
    fields = MedicalRecordFields.model_validate({"chief_complaint": {"value": "发热", "missing": False}})
    error = ExtractionOutputError("LLM_NO_SUPPORTED_FACTS: all fields removed")
    result = comparison_verdict("family", "患者：我父亲发热。", fields,
        {"no_patient_fact": False}, {}, pipeline_error=error)
    assert not result["passed"] and not result["expected_safe_refusal"]


def test_pipeline_conflict_fails_even_if_legacy_token_checks_pass():
    source = "患者：我没有花生过敏。"
    raw = MedicalRecordFields.model_validate({"allergy_history": {"value": "我没有花生过敏",
        "missing": False, "source_spans": [{"text": "我没有花生过敏", "index": 0}]}})
    final = raw.model_copy(deep=True)
    final.allergy_history.status = "conflicting"
    assert all(quality_checks("negative_allergy", final, source).values())
    result = comparison_verdict("negative_allergy", source, raw,
        quality_checks("negative_allergy", raw, source), {}, final)
    assert result["first_output_passed"] and not result["pipeline_passed"]
    assert not result["passed"]


def test_correct_first_and_pipeline_results_still_pass():
    source = "患者：我没有花生过敏。"
    fields = MedicalRecordFields.model_validate({"allergy_history": {"value": "我没有花生过敏",
        "missing": False, "source_spans": [{"text": "我没有花生过敏", "index": 0}]}})
    result = comparison_verdict("negative_allergy", source, fields,
        quality_checks("negative_allergy", fields, source), {}, fields.model_copy(deep=True))
    assert result["passed"] and result["generated_draft"]
    assert not result["expected_safe_refusal"]


def test_comparison_recognizes_real_generator_wrapped_empty_refusal(tmp_path, monkeypatch):
    from scripts.experiments import compare_local_models as comparison

    raw = blank().model_dump(mode="json")
    monkeypatch.setattr(comparison, "inputs", lambda: [("question", "医生：有没有胸痛？", [], None)])
    monkeypatch.setattr(comparison, "anonymize_text", lambda text: text)
    monkeypatch.setattr("app.services.llm.llm_record_generator.anonymize_text", lambda text: text)
    monkeypatch.setattr(comparison, "OllamaLLMProvider", lambda **kwargs: object())
    monkeypatch.setattr(comparison.request, "urlopen", lambda *args, **kwargs: io.BytesIO(
        json.dumps({"models": [{"name": "qwen3:4b", "digest": "a" * 64}]}).encode()))
    monkeypatch.setattr(comparison, "capture_production_call", lambda *args: (
        SimpleNamespace(content=json.dumps(raw)), None,
        [{"request": {"model": "qwen3:4b"}, "response": {"done_reason": "stop"}}]))
    output = tmp_path / "wrapped-refusal"
    monkeypatch.setattr("sys.argv", ["compare", "--model", "qwen3:4b", "--url", "http://unused",
        "--expected-digest", "a" * 64, "--output", str(output), "--base-sha", "b" * 40,
        "--deadline", "2099-01-01T00:00:00+00:00"])
    comparison.main()
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["passed"] == 3
    assert report["stage_counts"]["expected_safe_refusal"] == 3
    assert report["stage_counts"]["generated_draft"] == 0


@pytest.mark.parametrize("diagnostics", [
    [],
    [{"error": "LLM_NO_SUPPORTED_FACTS: transport words only"}],
    [{"error": "LLM_NO_SUPPORTED_FACTS: transport words only", "raw_response": "{}",
      "reconciled": {}, "evidence_validated": {}, "grounded": {}}],
])
def test_wrapped_provider_error_needs_completed_empty_grounding(diagnostics):
    from app.services.llm.base import LLMProviderUnavailableError

    error = LLMProviderUnavailableError("recorded-output-replay field extraction failed: LLM_NO_SUPPORTED_FACTS: transport words only")
    assert not explicit_no_facts_refusal(error, diagnostics, "recorded-output-replay")
