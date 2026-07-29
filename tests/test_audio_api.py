import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from app.api.audio import (
    _read_audio_record,
    _write_transcript,
    evaluate_audio,
    generate_record_from_audio,
    read_audio_transcript,
    transcribe_audio,
    upload_audio,
)
from app.api.tasks import read_task
from app.main import app
from app.schemas import ASREvaluationRequest, ASRResult, ASRSegment, SpeakerRoleAssignment
from app.services.asr import AudioChunk
from app.services.asr.auto_roles import AUTO_ROLE_WARNING
from tests.auth_helpers import login_as_admin


DOCTOR = "\u533b\u751f"
PATIENT = "\u60a3\u8005"


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
        self.original_env = {
            key: os.environ.get(key)
            for key in [
                "LLM_PROVIDER",
                "RECORD_PROVIDER_MODE",
                "ONLINE_LLM_API_BASE",
                "ONLINE_LLM_API_KEY",
                "ONLINE_LLM_MODEL",
                "OLLAMA_BASE_URL",
                "OLLAMA_MODEL",
                "MEDICAL_RECORD_AGENT_ASR_ENGINE",
                "ASR_ENGINE",
                "ASR_DEBUG_ENGINE_SELECTOR_ENABLED",
                "MEDILISTEN_DEMO_AUDIO_PATH",
            ]
        }
        for key in self.original_env:
            os.environ.pop(key, None)
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
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp_dir.cleanup()

    def test_audio_routes_are_registered(self):
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/audio/upload", route_paths)
        self.assertIn("/api/audio/demo/fever-01", route_paths)
        self.assertIn("/api/audio/{audio_id}/transcribe", route_paths)
        self.assertIn("/api/audio/{audio_id}/media", route_paths)
        self.assertIn("/api/audio/{audio_id}/transcript", route_paths)
        self.assertIn("/api/audio/{audio_id}/evaluate", route_paths)
        self.assertIn("/api/audio/{audio_id}/generate-record", route_paths)

    def test_demo_fever_audio_uses_configured_readonly_path(self):
        demo_audio = os.path.join(self.temp_dir.name, "fever_01.wav")
        with open(demo_audio, "wb") as handle:
            handle.write(b"RIFF\x24\x00\x00\x00WAVEfmt ")
        os.environ["MEDILISTEN_DEMO_AUDIO_PATH"] = demo_audio

        client = TestClient(app)
        login_as_admin(client)
        response = client.get("/api/audio/demo/fever-01")

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.content, b"RIFF\x24\x00\x00\x00WAVEfmt ")
        self.assertIn("audio", response.headers.get("content-type", ""))
        self.assertIn("inline", response.headers.get("content-disposition", ""))
        self.assertNotIn("attachment", response.headers.get("content-disposition", ""))

    def test_upload_transcribe_and_read_transcript(self):
        uploaded = self._upload_sample("sample.wav")

        self.assertEqual(uploaded.status, "uploaded")
        self.assertTrue(os.path.exists(uploaded.path))

        transcribed = transcribe_audio(uploaded.audio_id, engine="mock")
        asr_result = transcribed["asr_result"]

        self.assertEqual(transcribed["status"], "completed")
        self.assertEqual(transcribed["backend"], "mock")
        self.assertEqual(transcribed["model"], "mock-asr-v0.2")
        self.assertEqual(transcribed["recognition_mode"], "fast")
        self.assertEqual(transcribed["audio_duration_seconds"], 25.0)
        self.assertGreaterEqual(transcribed["processing_duration_seconds"], 0.0)
        self.assertIsNotNone(transcribed["rtf"])
        self.assertTrue(transcribed["request_id"])
        self.assertTrue(transcribed["started_at"])
        self.assertTrue(transcribed["completed_at"])
        self.assertEqual(asr_result["engine"], "mock-asr-v0.2")
        self.assertEqual(asr_result["backend"], "mock")
        self.assertEqual(asr_result["model"], "mock-asr-v0.2")
        self.assertEqual(asr_result["request_id"], transcribed["request_id"])
        self.assertEqual(asr_result["started_at"], transcribed["started_at"])
        self.assertEqual(asr_result["completed_at"], transcribed["completed_at"])
        self.assertIn("蛇咬伤", asr_result["text"])
        self.assertIn("[医生]", asr_result["conversation_text"])
        self.assertEqual(asr_result["medical_keywords"]["missing"], [])

        transcript = read_audio_transcript(uploaded.audio_id)
        self.assertEqual(transcript.audio_id, uploaded.audio_id)
        self.assertEqual(transcript.backend, "mock")
        self.assertEqual(transcript.model, "mock-asr-v0.2")
        self.assertEqual(transcript.request_id, transcribed["request_id"])
        self.assertEqual(transcript.completed_at, transcribed["completed_at"])
        self.assertIn("[患者]", transcript.conversation_text)

    def test_media_endpoint_supports_range_requests(self):
        uploaded = self._upload_sample("sample.wav")
        client = TestClient(app)
        login_as_admin(client)

        response = client.get(
            f"/api/audio/{uploaded.audio_id}/media",
            headers={"Range": "bytes=2-5"},
        )

        self.assertEqual(response.status_code, 206)
        self.assertEqual(response.headers["accept-ranges"], "bytes")
        self.assertTrue(response.headers["content-range"].startswith("bytes 2-5/"))
        self.assertEqual(response.content, b"FF..")

    def test_snakebite_manifest_restores_single_speaker_script(self):
        uploaded = self._upload_sample("snakebite_01.wav")
        transcribed = transcribe_audio(uploaded.audio_id, engine="mock")
        asr_result = transcribed["asr_result"]

        self.assertEqual(asr_result["manifest_sample_id"], "snakebite_01")
        self.assertEqual(asr_result["role_strategy"], "automatic_provisional_roles")
        self.assertFalse(asr_result["evaluate_diarization"])
        self.assertNotIn("[医生]", asr_result["conversation_text"])
        self.assertEqual({segment["speaker_id"] for segment in asr_result["segments"]}, {"script"})
        self.assertEqual({segment["role"] for segment in asr_result["segments"]}, {PATIENT})
        self.assertTrue(any(segment["role_warning"] == AUTO_ROLE_WARNING for segment in asr_result["segments"]))

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

    def test_funasr_transcribe_returns_structured_retryable_failure(self):
        uploaded = self._upload_sample("sample.wav")
        with patch("app.api.audio.create_asr_engine", side_effect=RuntimeError("NameResolutionError: Failed to resolve modelscope.cn")):
            with self.assertRaises(HTTPException) as context:
                transcribe_audio(uploaded.audio_id, engine="funasr")

        self.assertEqual(context.exception.status_code, 503)
        detail = context.exception.detail
        self.assertEqual(detail["error_category"], "dns_failure")
        self.assertTrue(detail["retryable"])
        self.assertEqual(detail["fallback_action"], "text_input")
        self.assertIn("FunASR", detail["message"])

    def test_funasr_type_error_returns_safe_structured_failure_and_preserves_audio(self):
        uploaded = self._upload_sample("sample.wav")

        class BrokenFunASR:
            def transcribe(self, _audio_id, _audio_path):
                raise TypeError("None argument after ** must be a mapping, not NoneType")

        with patch("app.api.audio.create_asr_engine", return_value=BrokenFunASR()):
            with self.assertRaises(HTTPException) as context:
                transcribe_audio(uploaded.audio_id, engine="funasr")

        self.assertEqual(context.exception.status_code, 503)
        detail = context.exception.detail
        self.assertEqual(detail["error_code"], "ASR_RESULT_INVALID")
        self.assertEqual(detail["stage"], "transcription")
        self.assertTrue(detail["audio_preserved"])
        self.assertTrue(detail["retryable"])
        self.assertNotIn("NoneType", detail["message"])
        self.assertIn("NoneType", detail["technical_detail"])
        record = _read_audio_record(uploaded.audio_id)
        self.assertEqual(record.status, "failed")
        self.assertTrue(os.path.exists(record.path))

        with self.assertRaises(HTTPException) as generate_context:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())
        self.assertEqual(generate_context.exception.status_code, 404)

    def test_public_audio_follow_uses_chunk_pipeline(self):
        uploaded = self._upload_sample("sample.wav")
        calls: list[str] = []

        class FakeChunkEngine:
            name = "fake-chunk"

            def transcribe(self, audio_id, audio_path):
                if "_chunk_" not in audio_id:
                    raise AssertionError("follow mode must not transcribe full audio")
                calls.append(audio_id)
                return ASRResult(
                    audio_id=audio_id,
                    engine="fake-chunk",
                    text=f"text {len(calls)}",
                    conversation_text=f"[spk1] text {len(calls)}",
                    segments=[
                        ASRSegment(
                            speaker="spk1",
                            speaker_id="spk1",
                            role=PATIENT,
                            role_confidence=0.88,
                            role_source="fake",
                            text=f"text {len(calls)}",
                            start_time=0.0,
                            end_time=1.0,
                        )
                    ],
                    duration=3.0,
                )

        def fake_split(audio_path, temp_dir, chunk_seconds):
            first = temp_dir / "chunk_001.wav"
            second = temp_dir / "chunk_002.wav"
            first.write_bytes(b"RIFF....WAVEfmt ")
            second.write_bytes(b"RIFF....WAVEfmt ")
            return [
                AudioChunk(index=1, path=first, start_seconds=0.0, duration_seconds=3.0),
                AudioChunk(index=2, path=second, start_seconds=3.0, duration_seconds=3.0),
            ]

        with patch("app.api.asr_sessions._audio_duration_for_chunking", return_value=6.0), \
             patch("app.api.asr_sessions.split_audio_to_chunks", side_effect=fake_split), \
             patch("app.api.asr_sessions.create_asr_engine", return_value=FakeChunkEngine()), \
             patch("app.api.audio.create_asr_engine", side_effect=AssertionError("full transcribe must not be called")):
            response = transcribe_audio(uploaded.audio_id, engine="mock", recognition_mode="follow")

        self.assertEqual(response["recognition_mode"], "follow")
        self.assertIn("session_id", response)
        self.assertEqual(calls, [f"{uploaded.audio_id}_chunk_001", f"{uploaded.audio_id}_chunk_002"])

    def test_public_audio_follow_with_background_task_returns_before_asr_work(self):
        uploaded = self._upload_sample("sample.wav")
        background_tasks = BackgroundTasks()

        with patch("app.api.asr_sessions._audio_duration_for_chunking", return_value=6.0), \
             patch("app.api.asr_sessions._should_use_chunked_session", return_value=(True, 6.0)), \
             patch("app.api.asr_sessions._run_asr_session_transcription", side_effect=AssertionError("ASR must be scheduled, not run inline")):
            response = transcribe_audio(
                uploaded.audio_id,
                background_tasks=background_tasks,
                engine="mock",
                recognition_mode="follow",
            )

        self.assertEqual(response["recognition_mode"], "follow")
        self.assertEqual(response["status"], "transcribing")
        self.assertIn("events_url", response)
        record = _read_audio_record(uploaded.audio_id)
        self.assertEqual(record.status, "transcribing")

    def test_unsupported_backend_does_not_fallback_to_fake_follow(self):
        uploaded = self._upload_sample("sample.wav")
        with self.assertRaises(HTTPException) as context:
            transcribe_audio(uploaded.audio_id, engine="online", recognition_mode="follow")

        self.assertEqual(context.exception.status_code, 422)
        self.assertEqual(context.exception.detail["error_code"], "follow_not_supported_by_backend")

    def test_explicit_funasr_request_is_rejected_when_configured_engine_is_mock(self):
        os.environ["MEDICAL_RECORD_AGENT_ASR_ENGINE"] = "mock"
        client = TestClient(app)
        login_as_admin(client)

        uploaded = client.post(
            "/api/audio/upload?recognition_mode=fast",
            files={"file": ("sample.wav", b"RIFF....WAVEfmt ", "audio/wav")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)

        response = client.post(
            f"/api/audio/{uploaded.json()['audio_id']}/transcribe?recognition_mode=fast&engine=funasr",
        )

        self.assertEqual(response.status_code, 409, response.text)
        detail = response.json()["detail"]
        self.assertEqual(detail["error_code"], "asr_engine_unavailable")
        self.assertEqual(detail["requested_engine"], "funasr")
        self.assertEqual(detail["effective_engine"], "mock")
        self.assertFalse(detail["fallback"])
        self.assertEqual(detail["fallback_reason"], "requested_engine_not_active")

    def test_omitted_transcribe_engine_uses_configured_backend(self):
        os.environ["MEDICAL_RECORD_AGENT_ASR_ENGINE"] = "funasr"

        class FakeConfiguredFunASR:
            name = "fake-funasr"

            def transcribe(self, audio_id, audio_path):
                return ASRResult(
                    audio_id=audio_id,
                    engine=self.name,
                    text="demo fever transcript",
                    conversation_text="[patient] demo fever transcript",
                    segments=[
                        ASRSegment(
                            speaker="spk1",
                            text="demo fever transcript",
                            start_time=0.0,
                            end_time=1.0,
                        )
                    ],
                    duration=1.0,
                )

        client = TestClient(app)
        login_as_admin(client)
        uploaded = client.post(
            "/api/audio/upload?recognition_mode=fast",
            files={"file": ("sample.wav", b"RIFF....WAVEfmt ", "audio/wav")},
        )
        self.assertEqual(uploaded.status_code, 200, uploaded.text)

        with patch("app.api.audio.create_asr_engine", return_value=FakeConfiguredFunASR()):
            response = client.post(
                f"/api/audio/{uploaded.json()['audio_id']}/transcribe?recognition_mode=fast",
            )

        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertEqual(payload["backend"], "funasr")
        self.assertEqual(payload["model"], "fake-funasr")

    def test_generate_record_from_audio_creates_text_task(self):
        uploaded = self._upload_sample("sample.wav")
        transcribe_audio(uploaded.audio_id, engine="mock")

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertIsInstance(response["task_id"], int)
        self.assertEqual(response["status"], "CREATED")
        task = read_task(response["task_id"])
        self.assertEqual(task["status"], "CREATED")
        self.assertIn("[医生]", task["input_text"])

    def test_generate_record_from_audio_returns_503_when_live_provider_unavailable(self):
        uploaded = self._upload_sample("sample.wav")
        transcribe_audio(uploaded.audio_id, engine="mock")
        os.environ["RECORD_PROVIDER_MODE"] = "live"

        with self.assertRaises(HTTPException) as raised:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(raised.exception.status_code, 503)
        self.assertFalse(raised.exception.detail["fallback"])
        self.assertEqual(raised.exception.detail["mode"], "live")

    def test_generate_record_from_audio_auto_assigns_unmapped_speaker(self):
        uploaded = self._upload_sample("sample.wav")
        _write_transcript(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text="我发热三天",
                conversation_text="[说话人 A] 我发热三天",
                segments=[ASRSegment(speaker_id="spk1", role=None, text="我发热三天")],
                speaker_assignments=[
                    SpeakerRoleAssignment(speaker_id="spk1", role=None, confidence=0.0, requires_confirmation=True)
                ],
            )
        )

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())
        transcript = read_audio_transcript(uploaded.audio_id)

        self.assertEqual(response["status"], "CREATED")
        self.assertFalse(transcript.needs_review)
        self.assertEqual(transcript.segments[0].role, PATIENT)
        self.assertEqual(transcript.segments[0].role_source, "auto_provisional_single_speaker")
        self.assertEqual(transcript.segments[0].role_warning, AUTO_ROLE_WARNING)

    def test_generate_record_from_audio_auto_warns_low_confidence_role(self):
        uploaded = self._upload_sample("sample.wav")
        _write_transcript(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text="我发热三天",
                conversation_text=f"[{PATIENT}] 我发热三天",
                segments=[
                    ASRSegment(
                        speaker_id="spk1",
                        role=PATIENT,
                        role_confidence=0.86,
                        role_source="global_two_party_constraint",
                        text="我发热三天",
                    )
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=PATIENT,
                        confidence=0.86,
                        source="global_two_party_constraint",
                    )
                ],
            )
        )

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())
        transcript = read_audio_transcript(uploaded.audio_id)

        self.assertEqual(response["status"], "CREATED")
        self.assertFalse(transcript.needs_review)
        self.assertEqual(transcript.segments[0].role, PATIENT)
        self.assertEqual(transcript.segments[0].role_warning, AUTO_ROLE_WARNING)
        self.assertIn(AUTO_ROLE_WARNING, transcript.warnings)

    def test_generate_record_from_audio_preserves_mixed_utterance_quality(self):
        uploaded = self._upload_sample("sample.wav")
        mixed_text = "请问哪里不舒服，我发热三天"
        _write_transcript(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text=mixed_text,
                conversation_text=f"[{DOCTOR}] {mixed_text}",
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        role_confidence=0.99,
                        role_source="speaker_context_rules",
                        text=mixed_text,
                    )
                ],
            )
        )

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())
        transcript = read_audio_transcript(uploaded.audio_id)

        self.assertEqual(response["status"], "CREATED")
        self.assertFalse(transcript.needs_review)
        self.assertEqual(transcript.role_quality.status, "blocked")

    def _upload_sample(self, filename: str):
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        fake_file.filename = filename
        try:
            return upload_audio(fake_file)
        finally:
            fake_file.close()


if __name__ == "__main__":
    unittest.main()
