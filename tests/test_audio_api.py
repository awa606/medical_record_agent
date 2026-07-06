import os
import tempfile
import unittest

from fastapi import BackgroundTasks, HTTPException

from app.api.audio import (
    evaluate_audio,
    generate_record_from_audio,
    read_audio_transcript,
    transcribe_audio,
    upload_audio,
)
from app.api.tasks import read_task
from app.main import app
from app.schemas import ASREvaluationRequest


class FakeUploadFile:
    filename = "sample.wav"
    content_type = "audio/wav"

    def __init__(self, content: bytes):
        self.file = tempfile.SpooledTemporaryFile()
        self.file.write(content)
        self.file.seek(0)

    def close(self):
        self.file.close()


class AudioApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "audio.sqlite3",
        )
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = os.path.join(
            self.temp_dir.name,
            "uploads",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_UPLOAD_DIR", None)
        self.temp_dir.cleanup()

    def test_audio_routes_are_registered(self):
        route_paths = {route.path for route in app.routes}

        self.assertIn("/api/audio/upload", route_paths)
        self.assertIn("/api/audio/{audio_id}/transcribe", route_paths)
        self.assertIn("/api/audio/{audio_id}/transcript", route_paths)
        self.assertIn("/api/audio/{audio_id}/evaluate", route_paths)
        self.assertIn("/api/audio/{audio_id}/generate-record", route_paths)

    def test_upload_transcribe_and_read_transcript(self):
        uploaded = self._upload_sample("sample.wav")

        self.assertEqual(uploaded.status, "uploaded")
        self.assertTrue(os.path.exists(uploaded.path))

        transcribed = transcribe_audio(uploaded.audio_id, engine="mock")
        asr_result = transcribed["asr_result"]

        self.assertEqual(transcribed["status"], "completed")
        self.assertEqual(asr_result["engine"], "mock-asr-v0.2")
        self.assertIn("蛇咬伤", asr_result["text"])
        self.assertIn("[医生]", asr_result["conversation_text"])
        self.assertEqual(asr_result["medical_keywords"]["missing"], [])

        transcript = read_audio_transcript(uploaded.audio_id)
        self.assertEqual(transcript.audio_id, uploaded.audio_id)
        self.assertIn("[患者]", transcript.conversation_text)

    def test_snakebite_manifest_restores_single_speaker_script(self):
        uploaded = self._upload_sample("snakebite_01.wav")
        transcribed = transcribe_audio(uploaded.audio_id, engine="mock")
        asr_result = transcribed["asr_result"]

        self.assertEqual(asr_result["manifest_sample_id"], "snakebite_01")
        self.assertEqual(asr_result["role_strategy"], "single_speaker_script_split")
        self.assertFalse(asr_result["evaluate_diarization"])
        self.assertIn("[医生]", asr_result["conversation_text"])
        self.assertIn("[患者]", asr_result["conversation_text"])

    def test_evaluate_audio_returns_cer_and_keywords(self):
        uploaded = self._upload_sample("sample.wav")
        transcribe_audio(uploaded.audio_id, engine="mock")

        result = evaluate_audio(
            uploaded.audio_id,
            ASREvaluationRequest(
                ground_truth_text="左手蛇咬伤后肿痛两个小时",
                expected_keywords=["蛇咬伤", "肿痛", "不存在关键词"],
            ),
        )

        self.assertGreaterEqual(result.cer, 0)
        self.assertIn("不存在关键词", result.medical_keywords["missing"])

    def test_generate_record_from_audio_requires_transcript(self):
        uploaded = self._upload_sample("sample.wav")

        with self.assertRaises(HTTPException) as context:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(context.exception.status_code, 404)

    def test_generate_record_from_audio_creates_text_task(self):
        uploaded = self._upload_sample("sample.wav")
        transcribe_audio(uploaded.audio_id, engine="mock")

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertIsInstance(response["task_id"], int)
        self.assertEqual(response["status"], "CREATED")
        task = read_task(response["task_id"])
        self.assertEqual(task["status"], "CREATED")
        self.assertIn("[医生]", task["input_text"])

    def _upload_sample(self, filename: str):
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        fake_file.filename = filename
        try:
            return upload_audio(fake_file)
        finally:
            fake_file.close()


if __name__ == "__main__":
    unittest.main()
