import asyncio
import os
import tempfile
import unittest

from app.api.asr_sessions import (
    _asr_session_event_stream,
    _read_events,
    create_asr_session,
    read_asr_session_result,
    upload_asr_session_audio,
)
from app.api.audio import read_audio_transcript
from app.main import app


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
