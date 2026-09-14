import json
import os
import unittest

from app.schemas import MedicalRecordFields
from app.services.llm import LLMProviderUnavailableError, create_llm_provider, create_llm_record_generator
from app.services.llm.base import LLMProviderResponse
from app.services.llm.json_repair import parse_json_object
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm.mock_provider import MockLLMProvider


ENV_KEYS = [
    "LLM_PROVIDER",
    "ONLINE_LLM_API_BASE",
    "ONLINE_LLM_API_KEY",
    "ONLINE_LLM_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_RETRIES",
    "RECORD_PROVIDER_MODE",
]


def _field(value):
    return {
        "value": value,
        "missing": False,
        "hint": None,
        "confidence": 0.82,
        "source_spans": [{"text": value, "index": 0}],
    }


def _missing(hint="建议补问"):
    return {
        "value": None,
        "missing": True,
        "hint": hint,
        "confidence": None,
        "source_spans": [],
    }


def _valid_llm_payload():
    return {
        "fields": {
            "chief_complaint": _field("发热3天"),
            "present_illness": _field("3天前开始发热，伴咳嗽。"),
            "previous_treatment": _field("服用布洛芬"),
            "accompanying_symptoms": _field("咳嗽、咳痰"),
            "past_history": _missing(),
            "allergy_history": _missing(),
            "physical_exam": _missing("待医生查体补充"),
            "candidate_diagnoses": [
                {
                    "name": "发热待查",
                    "status": "候选，待医生确认",
                    "evidence": [{"text": "发热3天", "index": 0}],
                }
            ],
        }
    }


class StaticProvider:
    name = "online"
    model = "unit-model"

    def __init__(self, content):
        self.content = content
        self.calls = 0

    def generate_fields_json(self, conversation_text, *, timeout_seconds):
        self.calls += 1
        return LLMProviderResponse(
            provider=self.name,
            model=self.model,
            content=self.content,
            latency_ms=12,
        )


class LLMAdapterTests(unittest.TestCase):
    def setUp(self):
        self.original_env = {key: os.environ.get(key) for key in ENV_KEYS}
        for key in ENV_KEYS:
            os.environ.pop(key, None)

    def tearDown(self):
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_default_provider_is_mock(self):
        provider = create_llm_provider()

        self.assertIsInstance(provider, MockLLMProvider)

    def test_json_repair_extracts_fenced_json(self):
        parsed = parse_json_object('```json\n{"fields": {"a": 1,},}\n```')

        self.assertEqual(parsed["fields"]["a"], 1)

    def test_llm_response_maps_to_medical_record_fields(self):
        provider = StaticProvider(json.dumps(_valid_llm_payload(), ensure_ascii=False))
        generator = LLMRecordGenerator(provider=provider)

        fields = generator.extract_fields("发热3天，服用布洛芬。")

        self.assertIsInstance(fields, MedicalRecordFields)
        self.assertEqual(fields.chief_complaint.value, "发热3天")
        self.assertEqual(fields.candidate_diagnoses[0].status, "候选/待医生确认")
        trace = generator.get_trace()
        self.assertEqual(trace["llm_provider"], "online")
        self.assertEqual(trace["model"], "unit-model")
        self.assertFalse(trace["fallback"])

    def test_invalid_llm_json_falls_back_to_mock(self):
        provider = StaticProvider("not json")
        generator = LLMRecordGenerator(provider=provider)

        fields = generator.extract_fields("发热3天，最高体温40℃，服用布洛芬。")

        self.assertEqual(fields.chief_complaint.value, "发热3天")
        trace = generator.get_trace()
        self.assertTrue(trace["fallback"])
        self.assertEqual(trace["actual_provider"], "mock")
        self.assertIn("field extraction failed", trace["fallback_reason"])

    def test_online_missing_config_uses_mock_fallback_without_api_key(self):
        os.environ["LLM_PROVIDER"] = "online"
        generator = create_llm_record_generator()

        fields = generator.extract_fields("发热3天，最高体温40℃，服用布洛芬。")

        self.assertEqual(fields.chief_complaint.value, "发热3天")
        trace = generator.get_trace()
        self.assertEqual(trace["llm_provider"], "online")
        self.assertEqual(trace["actual_provider"], "mock")
        self.assertTrue(trace["fallback"])
        self.assertIn("ONLINE_LLM_API_BASE", trace["fallback_reason"])
        self.assertNotIn("Bearer", trace["fallback_reason"])

    def test_invalid_provider_name_falls_back_in_record_generator(self):
        os.environ["LLM_PROVIDER"] = "typo"
        generator = create_llm_record_generator()

        fields = generator.extract_fields("发热3天，最高体温40℃，服用布洛芬。")

        self.assertEqual(fields.chief_complaint.value, "发热3天")
        trace = generator.get_trace()
        self.assertEqual(trace["llm_provider"], "typo")
        self.assertTrue(trace["fallback"])
        self.assertIn("Unsupported LLM_PROVIDER", trace["fallback_reason"])

    def test_live_mode_rejects_mock_provider(self):
        os.environ["RECORD_PROVIDER_MODE"] = "live"

        with self.assertRaises(LLMProviderUnavailableError):
            create_llm_record_generator()

    def test_live_mode_rejects_missing_online_config_without_mock_fallback(self):
        os.environ["RECORD_PROVIDER_MODE"] = "live"
        os.environ["LLM_PROVIDER"] = "online"

        with self.assertRaises(LLMProviderUnavailableError) as raised:
            create_llm_record_generator()

        self.assertIn("ONLINE_LLM_API_BASE", str(raised.exception))

    def test_invalid_record_provider_mode_raises_provider_unavailable(self):
        os.environ["RECORD_PROVIDER_MODE"] = "production"

        with self.assertRaises(LLMProviderUnavailableError) as raised:
            create_llm_record_generator()

        self.assertIn("Unsupported RECORD_PROVIDER_MODE", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
