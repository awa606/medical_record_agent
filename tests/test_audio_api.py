import os
import tempfile
import unittest

from fastapi import BackgroundTasks, HTTPException
from fastapi.testclient import TestClient

from app.api.audio import (
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
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/audio/upload", route_paths)
        self.assertIn("/api/audio/{audio_id}/transcribe", route_paths)
        self.assertIn("/api/audio/{audio_id}/media", route_paths)
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

    def test_media_endpoint_supports_range_requests(self):
        uploaded = self._upload_sample("sample.wav")
        client = TestClient(app)

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

    def test_generate_record_from_audio_rejects_unmapped_speaker(self):
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

        with self.assertRaises(HTTPException) as raised:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["role_quality"]["status"], "needs_review")
        self.assertEqual(raised.exception.detail["policy_version"], "speaker-role-policy-v1")
        self.assertEqual(raised.exception.detail["reason_code"], "unmapped_speaker")
        self.assertEqual(len(raised.exception.detail["pending_confirmation"]), 1)
        self.assertIn("decisions", raised.exception.detail["role_quality"])

    def test_generate_record_from_audio_rejects_low_confidence_role(self):
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

        with self.assertRaises(HTTPException) as raised:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["role_quality"]["status"], "needs_review")
        self.assertEqual(raised.exception.detail["policy_version"], "speaker-role-policy-v1")
        self.assertEqual(
            raised.exception.detail["reason_code"],
            "rules_global_two_party_constraint",
        )
        self.assertEqual(len(raised.exception.detail["pending_confirmation"]), 1)

    def test_generate_record_from_audio_rejects_mixed_utterance(self):
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

        with self.assertRaises(HTTPException) as raised:
            generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(raised.exception.status_code, 409)
        self.assertEqual(raised.exception.detail["role_quality"]["status"], "blocked")
        self.assertEqual(raised.exception.detail["reason_code"], "mixed_utterance_candidate")

    def test_manual_speaker_map_allows_generation_after_review(self):
        uploaded = self._upload_sample("sample.wav")
        _write_transcript(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text=(
                    "\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\n"
                    "\u6211\u53d1\u70ed\u4e09\u5929"
                ),
                conversation_text=(
                    f"[{DOCTOR}] \u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\n"
                    f"[{PATIENT}] \u6211\u53d1\u70ed\u4e09\u5929"
                ),
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        role_confidence=0.98,
                        role_source="manual_speaker_map",
                        reviewed_by_doctor=True,
                        text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d",
                    ),
                    ASRSegment(
                        speaker_id="spk1",
                        role=PATIENT,
                        role_confidence=0.98,
                        role_source="manual_speaker_map",
                        reviewed_by_doctor=True,
                        text="\u6211\u53d1\u70ed\u4e09\u5929",
                    ),
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        confidence=0.98,
                        source="manual_speaker_map",
                    ),
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=PATIENT,
                        confidence=0.98,
                        source="manual_speaker_map",
                    ),
                ],
            )
        )

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(response["status"], "CREATED")

    def test_legacy_transcript_without_role_quality_is_recomputed(self):
        uploaded = self._upload_sample("sample.wav")
        _write_transcript(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text=(
                    "\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\n"
                    "\u6211\u53d1\u70ed\u4e09\u5929"
                ),
                conversation_text=(
                    f"[{DOCTOR}] \u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\n"
                    f"[{PATIENT}] \u6211\u53d1\u70ed\u4e09\u5929"
                ),
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        role_confidence=0.96,
                        role_source="speaker_context_rules",
                        text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d",
                    ),
                    ASRSegment(
                        speaker_id="spk1",
                        role=PATIENT,
                        role_confidence=0.93,
                        role_source="speaker_context_rules",
                        text="\u6211\u53d1\u70ed\u4e09\u5929",
                    ),
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        confidence=0.96,
                        source="speaker_context_rules",
                    ),
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=PATIENT,
                        confidence=0.93,
                        source="speaker_context_rules",
                    ),
                ],
                role_quality=None,
            )
        )

        response = generate_record_from_audio(uploaded.audio_id, BackgroundTasks())

        self.assertEqual(response["status"], "CREATED")

    def _upload_sample(self, filename: str):
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        fake_file.filename = filename
        try:
            return upload_audio(fake_file)
        finally:
            fake_file.close()


if __name__ == "__main__":
    unittest.main()
