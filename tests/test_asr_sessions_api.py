import asyncio
import os
import tempfile
import unittest

from app.api.asr_sessions import (
    _asr_session_event_stream,
    _read_events,
    create_asr_session,
    read_asr_session_result,
    update_asr_session_result,
    upload_asr_session_audio,
)
from app.api.audio import read_audio_transcript
from app.main import app
from app.schemas import ASRSegmentCorrection, ASRSessionCorrectionRequest


class FakeUploadFile:
    def __init__(
        self,
        content: bytes,
        filename: str = "sample.wav",
        content_type: str = "audio/wav",
    ):
        self.filename = filename
        self.content_type = content_type
        self.file = tempfile.SpooledTemporaryFile()
        self.file.write(content)
        self.file.seek(0)

    def close(self):
        self.file.close()


def collect_sse_chunks(session_id: str, last_event_id: int = 0) -> str:
    async def collect() -> str:
        chunks = []
        async for chunk in _asr_session_event_stream(
            session_id,
            last_event_id=last_event_id,
            delay_ms=0,
        ):
            chunks.append(chunk)
        return "".join(chunks)

    return asyncio.run(collect())


class ASRSessionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = os.path.join(
            self.temp_dir.name,
            "uploads",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_UPLOAD_DIR", None)
        self.temp_dir.cleanup()

    def test_asr_session_routes_are_registered(self):
        route_paths = {route.path for route in app.routes}

        self.assertIn("/api/asr/sessions", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/audio", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/events", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/result", route_paths)

    def test_upload_mp3_builds_stream_events_and_result(self):
        session = create_asr_session(engine="mock")
        fake_file = FakeUploadFile(
            b"ID3 mock mp3 content",
            filename="sample.mp3",
            content_type="audio/mpeg",
        )
        try:
            uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        self.assertEqual(uploaded.status, "stream_ready")
        self.assertEqual(uploaded.session_id, session.session_id)
        self.assertEqual(uploaded.events_url, f"/api/asr/sessions/{session.session_id}/events")

        result = read_asr_session_result(session.session_id)
        self.assertEqual(result.audio_id, uploaded.audio_id)
        self.assertEqual(result.engine, "mock-asr-v0.2")
        self.assertGreaterEqual(len(result.segments), 1)

        legacy_transcript = read_audio_transcript(uploaded.audio_id)
        self.assertEqual(legacy_transcript.audio_id, uploaded.audio_id)

        events = _read_events(session.session_id)
        event_names = [event.event for event in events]
        self.assertEqual(event_names[:3], ["session_created", "audio_uploaded", "transcribing"])
        self.assertIn("segment", event_names)
        self.assertEqual(event_names[-1], "completed")

        stream = collect_sse_chunks(session.session_id)
        self.assertIn("event: segment", stream)
        self.assertIn("event: completed", stream)

    def test_role_review_updates_segments_result_and_legacy_transcript(self):
        session = create_asr_session(engine="mock")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()
        original = read_asr_session_result(session.session_id)
        corrections = [
            ASRSegmentCorrection(
                index=index,
                role="医生" if index % 2 == 0 else "患者",
                text=segment.text,
            )
            for index, segment in enumerate(original.segments)
        ]
        corrections[0].text = "您好，请问哪里不舒服？"
        corrections[1].text = "左手被咬伤后肿痛两个小时。"

        response = update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(
                reviewer="doctor",
                segments=corrections,
            ),
        )

        self.assertEqual(response.status, "reviewed")
        self.assertEqual(response.audio_id, uploaded.audio_id)
        self.assertEqual(response.asr_result.role_strategy, "manual_reviewed")
        self.assertTrue(response.asr_result.reviewed_by_doctor)
        self.assertFalse(response.asr_result.needs_review)
        self.assertEqual(response.asr_result.segments[0].role, "医生")
        self.assertEqual(response.asr_result.segments[1].role, "患者")
        self.assertIn("[医生] 您好，请问哪里不舒服？", response.asr_result.conversation_text)
        self.assertIn("[患者] 左手被咬伤后肿痛两个小时。", response.asr_result.conversation_text)

        result = read_asr_session_result(session.session_id)
        self.assertEqual(result.conversation_text, response.asr_result.conversation_text)

        legacy_transcript = read_audio_transcript(uploaded.audio_id)
        self.assertEqual(legacy_transcript.conversation_text, response.asr_result.conversation_text)

        event_names = [event.event for event in _read_events(session.session_id)]
        self.assertEqual(event_names[-1], "role_reviewed")

    def test_role_review_allows_pending_review_role(self):
        session = create_asr_session(engine="mock")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        response = update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(
                segments=[
                    ASRSegmentCorrection(
                        index=0,
                        role="待确认",
                        text="这一句还不能确认是谁说的。",
                        reviewed_by_doctor=False,
                    )
                ],
            ),
        )

        self.assertTrue(response.asr_result.needs_review)
        self.assertTrue(response.asr_result.segments[0].needs_review)
        self.assertEqual(response.asr_result.segments[0].role, "待确认")

    def test_sse_reconnect_skips_sent_events(self):
        session = create_asr_session(engine="mock")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        stream = collect_sse_chunks(session.session_id, last_event_id=3)

        self.assertNotIn("event: session_created", stream)
        self.assertNotIn("event: audio_uploaded", stream)
        self.assertIn("event: segment", stream)
        self.assertIn("event: completed", stream)


if __name__ == "__main__":
    unittest.main()
