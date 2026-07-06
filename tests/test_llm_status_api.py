import json
import os
import unittest

from app.api.llm import read_llm_status, test_llm_connection as api_test_llm_connection
from app.main import app


ENV_KEYS = [
    "LLM_PROVIDER",
    "ONLINE_LLM_API_BASE",
    "ONLINE_LLM_API_KEY",
    "ONLINE_LLM_MODEL",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
]


class LLMStatusApiTests(unittest.TestCase):
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

    def test_llm_routes_are_registered(self):
        route_paths = {route.path for route in app.routes}

        self.assertIn("/api/llm/status", route_paths)
        self.assertIn("/api/llm/test", route_paths)

    def test_default_mock_status_is_configured_and_reachable(self):
        status = read_llm_status()

        self.assertEqual(status["provider"], "mock")
        self.assertEqual(status["model"], "mock-deterministic-extractor")
        self.assertTrue(status["configured"])
        self.assertTrue(status["reachable"])
        self.assertFalse(status["fallback"])
        self.assertNotIn("API_KEY", json.dumps(status, ensure_ascii=False))

    def test_online_status_reports_missing_config_without_key_value(self):
        os.environ["LLM_PROVIDER"] = "online"
        os.environ["ONLINE_LLM_API_KEY"] = "secret-key-not-for-output"

        status = read_llm_status()

        self.assertEqual(status["provider"], "online")
        self.assertFalse(status["configured"])
        self.assertFalse(status["reachable"])
        self.assertEqual(status["fallback_provider"], "mock")
        self.assertIn("ONLINE_LLM_API_BASE", status["fallback_reason"])
        self.assertNotIn("secret-key-not-for-output", json.dumps(status, ensure_ascii=False))

    def test_online_status_with_full_config_does_not_probe_or_expose_key(self):
        os.environ.update(
            {
                "LLM_PROVIDER": "online",
                "ONLINE_LLM_API_BASE": "https://deepseek.example.test",
                "ONLINE_LLM_API_KEY": "secret-key-not-for-output",
                "ONLINE_LLM_MODEL": "deepseek-chat",
            }
        )

        status = read_llm_status()

        self.assertTrue(status["configured"])
        self.assertFalse(status["reachable"])
        self.assertFalse(status["fallback"])
        self.assertEqual(status["model"], "deepseek-chat")
        self.assertIn("POST /api/llm/test", status["fallback_reason"])
        self.assertNotIn("secret-key-not-for-output", json.dumps(status, ensure_ascii=False))

    def test_mock_connection_test_is_reachable(self):
        status = api_test_llm_connection()

        self.assertEqual(status["provider"], "mock")
        self.assertTrue(status["reachable"])
        self.assertFalse(status["fallback"])

    def test_invalid_provider_status_falls_back_to_mock(self):
        os.environ["LLM_PROVIDER"] = "deepseek"

        status = read_llm_status()

        self.assertEqual(status["provider"], "deepseek")
        self.assertFalse(status["configured"])
        self.assertFalse(status["reachable"])
        self.assertEqual(status["fallback_provider"], "mock")
        self.assertIn("Unsupported LLM_PROVIDER", status["fallback_reason"])


if __name__ == "__main__":
    unittest.main()
