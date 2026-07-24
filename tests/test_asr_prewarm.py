import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from app.services.asr.prewarm import get_prewarm_status, reset_prewarm_state_for_tests


class ASRPrewarmApiTests(unittest.TestCase):
    def setUp(self):
        reset_prewarm_state_for_tests()

    def test_default_status_is_idle(self):
        status = get_prewarm_status()
        self.assertEqual(status["status"], "idle")
        self.assertIsNone(status["last_error"])

    def test_status_endpoint_returns_service_state(self):
        with patch(
            "app.api.asr_prewarm.get_prewarm_status",
            return_value={
                "status": "ready",
                "last_error": None,
                "model_load_seconds": 1.23,
                "components": ["ParaformerStreaming"],
            },
        ):
            response = TestClient(app).get("/api/asr/prewarm/status")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_start_endpoint_can_be_mocked_without_loading_real_models(self):
        with patch(
            "app.api.asr_prewarm.start_funasr_prewarm",
            return_value={
                "status": "warming",
                "last_error": None,
                "model_load_seconds": None,
                "components": [],
            },
        ) as mocked_start:
            response = TestClient(app).post("/api/asr/prewarm/start")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "warming")
        mocked_start.assert_called_once_with(force=True)


if __name__ == "__main__":
    unittest.main()
