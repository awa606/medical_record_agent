import io
import json
from unittest.mock import patch

from app.schemas import MedicalRecordFields
from app.services.llm.ollama_provider import OllamaLLMProvider
from scripts.experiments.compare_local_models import capture_production_call, quality_checks


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
