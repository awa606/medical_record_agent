import asyncio
import hashlib
import io
import os
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.asr_sessions import (
    _RECORDING_SESSION_LOCKS,
    _append_events,
    _asr_session_event_stream,
    _chunk_seconds_for_duration,
    _read_events,
    _read_recording_chunk_state,
    _write_session_result,
    _should_use_realtime_upload_session,
    create_asr_session,
    read_asr_session_result,
    merge_asr_session_speakers,
    update_asr_session_result,
    upload_asr_session_audio,
)
from app.api.audio import _write_transcript, read_audio_transcript
from app.main import app
from app.schemas import (
    ASRResult,
    ASRSegment,
    ASRSpeakerMergeRequest,
    ASRSegmentCorrection,
    ASRSessionCorrectionRequest,
    ASRSessionEvent,
    SpeakerRoleAssignment,
)
from app.schemas.asr import DiarizationTurn
from app.services.asr import AudioChunk
from tests.auth_helpers import create_user, login_as_admin, login_as_user


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


class FakeChunkEngine:
    name = "fake-sensevoice"

    def __init__(self, *, fail_on: int | None = None):
        self.fail_on = fail_on

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        if self.fail_on is not None and f"chunk_{self.fail_on:03d}" in audio_id:
            raise RuntimeError("fake chunk failure")
        index = int(audio_id.rsplit("_", 1)[-1])
        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=f"第{index}段转写",
            conversation_text=f"[sensevoice] 第{index}段转写",
            segments=[
                ASRSegment(
                    speaker="sensevoice",
                    text=f"第{index}段转写",
                    start_time=0.0,
                    end_time=2.0,
                )
            ],
            duration=2.0,
        )


class FakeNativeStreamingEngine:
    name = "fake-funasr-streaming"
    model_load_time_seconds = 0.01

    def transcribe_streaming(self, audio_id, audio_path, *, on_progress=None, on_segment=None):
        provisional = ASRSegment(
            segment_id=f"{audio_id}-seg-0001",
            revision=1,
            provisional=True,
            speaker="streaming",
            text="您好",
            start_time=0.0,
            end_time=0.6,
            needs_review=True,
        )
        segment = provisional.model_copy(
            update={
                "revision": 2,
                "provisional": False,
                "text": "您好，请问哪里不舒服？",
                "end_time": 2.4,
            }
        )
        if on_segment:
            on_segment(
                "segment",
                provisional,
                {"processed_audio_seconds": 0.6, "audio_duration_seconds": 9.5},
            )
            on_segment(
                "segment_update",
                segment,
                {"processed_audio_seconds": 2.4, "audio_duration_seconds": 9.5},
            )
        if on_progress:
            on_progress(
                {
                    "phase": "streaming_completed",
                    "processed_audio_seconds": 9.5,
                    "audio_duration_seconds": 9.5,
                    "progress": 1.0,
                    "progress_kind": "actual",
                    "elapsed_seconds": 0.1,
                }
            )
        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=segment.text,
            conversation_text=f"[待确认] {segment.text}",
            segments=[segment],
            duration=9.5,
            needs_review=True,
        )


class FakeReconciliationEngine:
    def transcribe(self, audio_id, audio_path):
        segments = [
            ASRSegment(
                segment_id=f"{audio_id}-cal-0001",
                speaker="spk0",
                speaker_id="spk0",
                text="请问哪里不舒服？",
                start_time=0.0,
                end_time=1.2,
            ),
            ASRSegment(
                segment_id=f"{audio_id}-cal-0002",
                speaker="spk1",
                speaker_id="spk1",
                text="我发热三天。",
                start_time=1.2,
                end_time=2.4,
            ),
        ]
        return ASRResult(
            audio_id=audio_id,
            engine="fake-funasr-cam++",
            text="请问哪里不舒服？我发热三天。",
            conversation_text="",
            segments=segments,
            duration=9.5,
        )


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


def fake_audio_chunks() -> list[AudioChunk]:
    return [
        AudioChunk(index=1, path=Path("chunk_001.wav"), start_seconds=0.0, duration_seconds=300.0),
        AudioChunk(index=2, path=Path("chunk_002.wav"), start_seconds=300.0, duration_seconds=120.0),
    ]


def browser_wav_bytes(frame_count: int = 1600, sample_rate: int = 16000, amplitude: int = 1200) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        frame = int(amplitude).to_bytes(2, "little", signed=True)
        writer.writeframes(frame * frame_count)
    return output.getvalue()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def upload_browser_recording_chunk(
    client: TestClient,
    session_id: str,
    *,
    chunk_index: int,
    payload: bytes,
    duration_seconds: str = "0.1",
):
    return client.post(
        f"/api/asr/sessions/{session_id}/chunks",
        data={
            "chunk_index": str(chunk_index),
            "sha256": sha256_bytes(payload),
            "duration_seconds": duration_seconds,
        },
        files={"file": (f"chunk-{chunk_index}.wav", payload, "audio/wav")},
    )


class ASRSessionApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = os.path.join(
            self.temp_dir.name,
            "uploads",
        )
        os.environ["MEDICAL_RECORD_AGENT_DB"] = os.path.join(
            self.temp_dir.name,
            "asr_sessions.sqlite3",
        )

    def tearDown(self):
        os.environ.pop("MEDICAL_RECORD_AGENT_UPLOAD_DIR", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        os.environ.pop("MEDICAL_RECORD_AGENT_MAX_RECORDING_CHUNK_BYTES", None)
        self.temp_dir.cleanup()

    def test_asr_session_routes_are_registered(self):
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/asr/sessions", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/audio", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/chunks", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/chunks/status", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/finalize", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/complete", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/recording", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/events", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/result", route_paths)

    def test_browser_recording_chunks_are_idempotent_and_complete_to_asr_result(self):
        client = TestClient(app)
        login_as_admin(client)
        session = client.post("/api/asr/sessions?engine=mock").json()
        session_id = session["session_id"]

        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(chunk_zero),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", chunk_zero, "audio/wav")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        self.assertFalse(upload.json()["duplicate"])
        self.assertEqual(upload.json()["chunk_count"], 1)
        self.assertEqual(upload.json()["next_chunk_index"], 1)

        duplicate = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(chunk_zero),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", chunk_zero, "audio/wav")},
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.text)
        self.assertTrue(duplicate.json()["duplicate"])
        self.assertEqual(duplicate.json()["chunk_count"], 1)

        conflicting = browser_wav_bytes(amplitude=2000)
        conflict = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(conflicting),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", conflicting, "audio/wav")},
        )
        self.assertEqual(conflict.status_code, 409)

        chunk_one = browser_wav_bytes(amplitude=1500)
        second = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "1",
                "sha256": sha256_bytes(chunk_one),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-1.wav", chunk_one, "audio/wav")},
        )
        self.assertEqual(second.status_code, 200, second.text)
        status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["chunk_count"], 2)
        self.assertEqual(status.json()["next_chunk_index"], 2)

        blocked = client.post(f"/api/asr/sessions/{session_id}/complete")
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("finalized", blocked.text)

        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 200, finalized.text)
        self.assertEqual(finalized.json()["status"], "recorded")
        self.assertEqual(finalized.json()["duration_seconds"], 0.2)
        self.assertTrue(finalized.json()["media_url"].endswith("/media"))

        second_finalize = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(second_finalize.status_code, 200, second_finalize.text)
        self.assertEqual(second_finalize.json()["audio_id"], finalized.json()["audio_id"])

        completed = client.post(f"/api/asr/sessions/{session_id}/complete")
        self.assertEqual(completed.status_code, 200, completed.text)
        self.assertEqual(completed.json()["status"], "transcribing")
        self.assertEqual(completed.json()["audio_id"], finalized.json()["audio_id"])
        second_complete = client.post(f"/api/asr/sessions/{session_id}/complete")
        self.assertEqual(second_complete.status_code, 200, second_complete.text)
        self.assertEqual(second_complete.json()["audio_id"], finalized.json()["audio_id"])
        self.assertNotIn(session_id, _RECORDING_SESSION_LOCKS)
        result = client.get(f"/api/asr/sessions/{session_id}/result")
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIn("蛇咬伤", result.json()["text"])

    def test_browser_recording_complete_rejects_missing_chunk_gap(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_one = browser_wav_bytes()
        upload = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "1",
                "sha256": sha256_bytes(chunk_one),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-1.wav", chunk_one, "audio/wav")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)

        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 409)
        self.assertEqual(finalized.json()["detail"]["missing_chunk_indices"], [0])

    def test_browser_recording_finalize_rejects_corrupt_wav_and_stays_retryable(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        corrupt_chunk = b"not-a-valid-wav"
        upload = upload_browser_recording_chunk(
            client,
            session_id,
            chunk_index=0,
            payload=corrupt_chunk,
        )
        self.assertEqual(upload.status_code, 200, upload.text)

        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 400)
        self.assertIn("invalid WAV", finalized.text)
        status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "recording")
        self.assertEqual(status.json()["chunk_count"], 1)
        state = _read_recording_chunk_state(session_id)
        self.assertEqual(state["status"], "recording")
        self.assertIn("last_finalize_error", state)

    def test_browser_recording_finalize_rejects_mismatched_wav_format_and_stays_retryable(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(sample_rate=16000)
        chunk_one = browser_wav_bytes(sample_rate=8000)
        first = upload_browser_recording_chunk(client, session_id, chunk_index=0, payload=chunk_zero)
        second = upload_browser_recording_chunk(client, session_id, chunk_index=1, payload=chunk_one)
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)

        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 400)
        self.assertIn("different WAV formats", finalized.text)
        status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "recording")
        self.assertEqual(status.json()["chunk_count"], 2)

    def test_browser_recording_finalize_can_retry_after_transient_merge_failure(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = upload_browser_recording_chunk(client, session_id, chunk_index=0, payload=chunk_zero)
        self.assertEqual(upload.status_code, 200, upload.text)

        from app.api import asr_sessions as asr_sessions_module

        real_combine = asr_sessions_module._combine_wav_chunks
        calls = {"count": 0}

        def flaky_combine(chunk_paths, destination):
            if calls["count"] == 0:
                calls["count"] += 1
                raise OSError("simulated disk write failure")
            return real_combine(chunk_paths, destination)

        with patch("app.api.asr_sessions._combine_wav_chunks", side_effect=flaky_combine):
            failed = client.post(f"/api/asr/sessions/{session_id}/finalize")
            self.assertEqual(failed.status_code, 500)
            status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
            self.assertEqual(status.json()["status"], "recording")
            self.assertEqual(status.json()["chunk_count"], 1)

            retried = client.post(f"/api/asr/sessions/{session_id}/finalize")
            self.assertEqual(retried.status_code, 200, retried.text)
            self.assertEqual(retried.json()["status"], "recorded")

    def test_browser_recording_cancel_deletes_chunks_and_unused_audio(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(chunk_zero),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", chunk_zero, "audio/wav")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 200, finalized.text)
        audio_id = finalized.json()["audio_id"]
        upload_dir = Path(os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"])
        self.assertTrue((upload_dir / f"{audio_id}.wav").exists())
        self.assertTrue((upload_dir / "asr_sessions" / session_id / "recording_chunks.json").exists())

        cancelled = client.delete(f"/api/asr/sessions/{session_id}/recording")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        self.assertEqual(cancelled.json()["status"], "cancelled")
        self.assertFalse((upload_dir / f"{audio_id}.wav").exists())
        self.assertFalse((upload_dir / f"{audio_id}.record.json").exists())
        self.assertFalse((upload_dir / "asr_sessions" / session_id / "recording_chunks").exists())
        self.assertFalse((upload_dir / "asr_sessions" / session_id / "recording_chunks.json").exists())
        status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "cancelled")

        repeat = client.delete(f"/api/asr/sessions/{session_id}/recording")
        self.assertEqual(repeat.status_code, 200, repeat.text)
        self.assertNotIn(session_id, _RECORDING_SESSION_LOCKS)

    def test_browser_recording_cancelled_session_rejects_late_chunks(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = upload_browser_recording_chunk(client, session_id, chunk_index=0, payload=chunk_zero)
        self.assertEqual(upload.status_code, 200, upload.text)

        cancelled = client.delete(f"/api/asr/sessions/{session_id}/recording")
        self.assertEqual(cancelled.status_code, 200, cancelled.text)
        late_chunk = browser_wav_bytes(amplitude=1500)
        late_upload = upload_browser_recording_chunk(client, session_id, chunk_index=1, payload=late_chunk)
        self.assertEqual(late_upload.status_code, 409)
        status = client.get(f"/api/asr/sessions/{session_id}/chunks/status")
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json()["status"], "cancelled")
        self.assertEqual(status.json()["chunk_count"], 0)

    def test_browser_recording_cancel_rejects_non_owner(self):
        admin_client = TestClient(app)
        create_user(admin_client, username="doctor-a")
        create_user(admin_client, username="doctor-b")

        owner_client = TestClient(app)
        login_as_user(owner_client, username="doctor-a")
        session_id = owner_client.post("/api/asr/sessions?engine=mock").json()["session_id"]

        other_client = TestClient(app)
        login_as_user(other_client, username="doctor-b")
        forbidden = other_client.delete(f"/api/asr/sessions/{session_id}/recording")
        self.assertEqual(forbidden.status_code, 403)

    def test_browser_recording_chunk_size_limit_returns_413(self):
        os.environ["MEDICAL_RECORD_AGENT_MAX_RECORDING_CHUNK_BYTES"] = "16"
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(chunk_zero),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", chunk_zero, "audio/wav")},
        )
        self.assertEqual(upload.status_code, 413)

    def test_browser_recording_cancel_rejects_after_complete(self):
        client = TestClient(app)
        login_as_admin(client)
        session_id = client.post("/api/asr/sessions?engine=mock").json()["session_id"]
        chunk_zero = browser_wav_bytes(amplitude=1000)
        upload = client.post(
            f"/api/asr/sessions/{session_id}/chunks",
            data={
                "chunk_index": "0",
                "sha256": sha256_bytes(chunk_zero),
                "duration_seconds": "0.1",
            },
            files={"file": ("chunk-0.wav", chunk_zero, "audio/wav")},
        )
        self.assertEqual(upload.status_code, 200, upload.text)
        finalized = client.post(f"/api/asr/sessions/{session_id}/finalize")
        self.assertEqual(finalized.status_code, 200, finalized.text)
        completed = client.post(f"/api/asr/sessions/{session_id}/complete")
        self.assertEqual(completed.status_code, 200, completed.text)

        cancelled = client.delete(f"/api/asr/sessions/{session_id}/recording")
        self.assertEqual(cancelled.status_code, 409)

    def test_session_accepts_doctor_profile_and_diarization_engine(self):
        session = create_asr_session(
            engine="funasr",
            doctor_profile_id="doctor-profile-1",
            diarization_engine="auto",
        )

        self.assertEqual(session.doctor_profile_id, "doctor-profile-1")
        self.assertEqual(session.diarization_engine, "auto")

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
        self.assertEqual(result.engine, "mock-asr-v0.2-realtime")
        self.assertGreaterEqual(len(result.segments), 1)

        legacy_transcript = read_audio_transcript(uploaded.audio_id)
        self.assertEqual(legacy_transcript.audio_id, uploaded.audio_id)

        events = _read_events(session.session_id)
        event_names = [event.event for event in events]
        self.assertEqual(event_names[:3], ["session_created", "audio_uploaded", "transcribing"])
        self.assertIn("chunk_plan", event_names)
        self.assertIn("chunk_started", event_names)
        self.assertIn("chunk_completed", event_names)
        self.assertIn("segment", event_names)
        self.assertEqual(event_names[-1], "completed")

        stream = collect_sse_chunks(session.session_id)
        self.assertIn("event: segment", stream)
        self.assertIn("event: completed", stream)

    def test_dynamic_chunk_seconds_uses_short_chunks_for_demo_length_audio(self):
        os.environ.pop("ASR_SESSION_DYNAMIC_CHUNKING", None)
        os.environ.pop("ASR_SESSION_SHORT_CHUNK_SECONDS", None)
        os.environ.pop("ASR_SESSION_CHUNK_SECONDS", None)

        self.assertEqual(_chunk_seconds_for_duration(310.0), 60)
        self.assertEqual(_chunk_seconds_for_duration(1800.0), 300)

    def test_funasr_native_streaming_is_not_limited_to_short_audio(self):
        enabled, duration = _should_use_realtime_upload_session(
            "funasr",
            Path("long.wav"),
            duration=1800.0,
        )

        self.assertTrue(enabled)
        self.assertEqual(duration, 1800.0)

    def test_funasr_realtime_upload_uses_model_native_streaming_without_temp_chunks(self):
        session = create_asr_session(engine="funasr")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")

        try:
            with (
                patch(
                    "app.api.asr_sessions._create_funasr_streaming_engine",
                    return_value=FakeNativeStreamingEngine(),
                ),
                patch(
                    "app.api.asr_sessions._create_funasr_reconciliation_engine",
                    return_value=FakeReconciliationEngine(),
                ),
                patch("app.api.asr_sessions._audio_duration_for_chunking", return_value=9.5),
                patch("app.api.asr_sessions.split_audio_to_chunks") as split_chunks,
            ):
                uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        self.assertEqual(uploaded.status, "stream_ready")
        self.assertEqual(uploaded.duration_seconds, 9.5)
        self.assertEqual(uploaded.media_url, f"/api/audio/{uploaded.audio_id}/media")
        split_chunks.assert_not_called()

        result = read_asr_session_result(session.session_id)
        self.assertEqual(result.engine, "fake-funasr-cam++")
        self.assertEqual(len(result.segments), 2)
        self.assertEqual({segment.speaker_id for segment in result.segments}, {"spk0", "spk1"})
        self.assertEqual(len({segment.segment_id for segment in result.segments}), len(result.segments))
        self.assertTrue(result.segments[0].segment_id.startswith(f"{uploaded.audio_id}-cal-0001"))

        events = _read_events(session.session_id)
        event_names = [event.event for event in events]
        self.assertNotIn("chunk_plan", event_names)
        self.assertIn("transcribing_progress", event_names)
        self.assertIn("diarization_progress", event_names)
        self.assertIn("speaker_turn", event_names)
        self.assertIn("speaker_mapping_update", event_names)
        self.assertIn("diarization_completed", event_names)
        self.assertIn("reconciliation_completed", event_names)
        self.assertEqual(event_names.count("segment"), 1)
        self.assertEqual(event_names.count("segment_update"), 1)
        self.assertLess(event_names.index("segment"), event_names.index("segment_update"))
        self.assertLess(event_names.index("segment"), event_names.index("completed"))
        first_segment = next(event for event in events if event.event == "segment")
        self.assertTrue(first_segment.data["partial"])
        self.assertEqual(first_segment.data["mode"], "model_native_streaming")
        self.assertEqual(first_segment.data["progress_kind"], "actual")

    def test_funasr_model_load_failure_marks_session_retryable_without_second_fallback_load(self):
        session = create_asr_session(engine="funasr")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")

        try:
            with (
                patch(
                    "app.api.asr_sessions._create_funasr_streaming_engine",
                    side_effect=RuntimeError("NameResolutionError: Failed to resolve modelscope.cn"),
                ),
                patch("app.api.asr_sessions._audio_duration_for_chunking", return_value=9.5),
                patch("app.api.asr_sessions.create_asr_engine") as fallback_engine,
            ):
                uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        self.assertEqual(uploaded.status, "failed")
        fallback_engine.assert_not_called()
        events = _read_events(session.session_id)
        failed = next(event for event in events if event.event == "failed")
        self.assertEqual(failed.data["error_category"], "dns_failure")
        self.assertTrue(failed.data["retryable"])
        self.assertEqual(failed.data["fallback_action"], "text_input")

    def test_upload_route_starts_background_transcription_and_streams_events(self):
        client = TestClient(app)
        login_as_admin(client)
        created = client.post("/api/asr/sessions?engine=mock")
        self.assertEqual(created.status_code, 200)
        session_id = created.json()["session_id"]

        uploaded = client.post(
            f"/api/asr/sessions/{session_id}/audio",
            files={"file": ("sample.wav", b"RIFF....WAVEfmt ", "audio/wav")},
        )

        self.assertEqual(uploaded.status_code, 200)
        self.assertEqual(uploaded.json()["status"], "transcribing")
        stream = client.get(f"/api/asr/sessions/{session_id}/events?delay_ms=0")
        self.assertEqual(stream.status_code, 200)
        self.assertIn("event: segment", stream.text)
        self.assertIn("event: completed", stream.text)
        result = client.get(f"/api/asr/sessions/{session_id}/result")
        self.assertEqual(result.status_code, 200)

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

    def test_manual_speaker_merge_persists_segments_assignments_turns_and_quality(self):
        session = create_asr_session(engine="funasr")
        result = ASRResult(
            audio_id="fever-merge",
            engine="funasr-paraformer-zh",
            text="请问哪里不舒服？\n我发热三天。\n还有咳嗽。",
            conversation_text="",
            segments=[
                ASRSegment(segment_id="seg-1", speaker="spk1", speaker_id="spk1", role="医生", role_confidence=0.96, role_source="manual", reviewed_by_doctor=True, text="请问哪里不舒服？", start_time=0.0, end_time=1.0),
                ASRSegment(segment_id="seg-2", speaker="spk2", speaker_id="spk2", role="患者", role_confidence=0.62, role_source="speaker_context_rules", needs_review=True, text="我发热三天。", start_time=1.0, end_time=2.0),
                ASRSegment(segment_id="seg-3", speaker="spk3", speaker_id="spk3", role="患者", role_confidence=0.61, role_source="speaker_context_rules", needs_review=True, text="还有咳嗽。", start_time=2.0, end_time=3.0),
            ],
            diarization_turns=[
                DiarizationTurn(start_time=0.0, end_time=1.0, speaker_id="spk1"),
                DiarizationTurn(start_time=1.0, end_time=2.0, speaker_id="spk2"),
                DiarizationTurn(start_time=2.0, end_time=3.0, speaker_id="spk3"),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk1", role="医生", confidence=0.99, source="manual"),
                SpeakerRoleAssignment(speaker_id="spk2", role="患者", confidence=0.62, source="speaker_context_rules", requires_confirmation=True),
                SpeakerRoleAssignment(speaker_id="spk3", role="患者", confidence=0.61, source="speaker_context_rules", requires_confirmation=True),
            ],
            needs_review=True,
        )
        _write_session_result(session.session_id, result)
        _write_transcript(result)

        response = merge_asr_session_speakers(
            session.session_id,
            ASRSpeakerMergeRequest(
                source_speaker="spk3",
                target_speaker="spk2",
                reviewer="doctor",
                note="患者误拆合并",
            ),
        )

        self.assertEqual(response.speaker_count_before, 3)
        self.assertEqual(response.speaker_count_after, 2)
        self.assertEqual(response.affected_segment_ids, ["seg-3"])
        merged = response.asr_result
        self.assertEqual({segment.speaker_id for segment in merged.segments}, {"spk1", "spk2"})
        self.assertEqual({turn.speaker_id for turn in merged.diarization_turns}, {"spk1", "spk2"})
        self.assertEqual({item.speaker_id for item in merged.speaker_assignments}, {"spk1", "spk2"})
        self.assertIn("[患者] 还有咳嗽。", merged.conversation_text)
        self.assertEqual(merged.role_quality.metrics.speaker_count, 2)

        stored = read_asr_session_result(session.session_id)
        self.assertEqual(stored.conversation_text, merged.conversation_text)
        legacy = read_audio_transcript("fever-merge")
        self.assertEqual(legacy.conversation_text, merged.conversation_text)

        event_names = [event.event for event in _read_events(session.session_id)]
        self.assertEqual(event_names[-1], "speakers_merged")

    def test_manual_speaker_merge_errors_are_explicit(self):
        session = create_asr_session(engine="funasr")
        result = ASRResult(
            audio_id="merge-errors",
            engine="funasr",
            text="a\nb",
            conversation_text="",
            segments=[
                ASRSegment(segment_id="a", speaker="spk1", speaker_id="spk1", text="a"),
                ASRSegment(segment_id="b", speaker="spk2", speaker_id="spk2", text="b"),
            ],
        )
        _write_session_result(session.session_id, result)

        client = TestClient(app)
        login_as_admin(client)
        same = client.post(
            f"/api/asr/sessions/{session.session_id}/speakers/merge",
            json={"source_speaker": "spk1", "target_speaker": "spk1"},
        )
        missing = client.post(
            f"/api/asr/sessions/{session.session_id}/speakers/merge",
            json={"source_speaker": "spk9", "target_speaker": "spk1"},
        )

        self.assertEqual(same.status_code, 400)
        self.assertEqual(missing.status_code, 404)

    def test_generate_record_gate_recovers_after_merge_and_role_confirmation(self):
        session = create_asr_session(engine="funasr")
        result = ASRResult(
            audio_id="merge-gate",
            engine="funasr",
            text="请问哪里不舒服？\n我发热三天。\n还有咳嗽。",
            conversation_text="",
            segments=[
                ASRSegment(segment_id="g1", speaker="spk1", speaker_id="spk1", role="医生", role_confidence=0.99, role_source="manual", reviewed_by_doctor=True, text="请问哪里不舒服？"),
                ASRSegment(segment_id="g2", speaker="spk2", speaker_id="spk2", role=None, needs_review=True, text="我发热三天。"),
                ASRSegment(segment_id="g3", speaker="spk3", speaker_id="spk3", role=None, needs_review=True, text="还有咳嗽。"),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk1", role="医生", confidence=0.99, source="manual"),
                SpeakerRoleAssignment(speaker_id="spk2", role=None, confidence=0.0, requires_confirmation=True),
                SpeakerRoleAssignment(speaker_id="spk3", role=None, confidence=0.0, requires_confirmation=True),
            ],
            needs_review=True,
        )
        _write_session_result(session.session_id, result)
        _write_transcript(result)
        client = TestClient(app)
        login_as_admin(client)

        blocked = client.post("/api/audio/merge-gate/generate-record")
        self.assertEqual(blocked.status_code, 409)

        merge_asr_session_speakers(
            session.session_id,
            ASRSpeakerMergeRequest(source_speaker="spk3", target_speaker="spk2"),
        )
        still_blocked = client.post("/api/audio/merge-gate/generate-record")
        self.assertEqual(still_blocked.status_code, 409)

        update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(
                speaker_roles=[
                    {"speaker_id": "spk1", "role": "医生"},
                    {"speaker_id": "spk2", "role": "患者"},
                ]
            ),
        )
        allowed = client.post("/api/audio/merge-gate/generate-record")
        self.assertEqual(allowed.status_code, 200)

    def test_companion_and_pending_roles_are_accepted_for_speaker_review(self):
        session = create_asr_session(engine="mock")
        result = ASRResult(
            audio_id="companion-role",
            engine="mock",
            text="医生 患者 家属",
            conversation_text="",
            segments=[
                ASRSegment(segment_id="c1", speaker="spk1", speaker_id="spk1", text="请问哪里不舒服？"),
                ASRSegment(segment_id="c2", speaker="spk2", speaker_id="spk2", text="我发热三天。"),
                ASRSegment(segment_id="c3", speaker="spk3", speaker_id="spk3", text="我是家属。"),
            ],
        )
        _write_session_result(session.session_id, result)

        response = update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(
                speaker_roles=[
                    {"speaker_id": "spk1", "role": "医生"},
                    {"speaker_id": "spk2", "role": "患者"},
                    {"speaker_id": "spk3", "role": "陪同人员"},
                ]
            ),
        )
        self.assertEqual({segment.role for segment in response.asr_result.segments}, {"医生", "患者", "陪同人员"})

        pending = update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(speaker_roles=[{"speaker_id": "spk3", "role": "暂不确定", "reviewed_by_doctor": False}]),
        )
        self.assertTrue(pending.asr_result.needs_review)
        self.assertEqual([segment for segment in pending.asr_result.segments if segment.speaker_id == "spk3"][0].role, "待确认")

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

    def test_sse_batches_500_events_without_per_event_delay_and_resumes(self):
        session = create_asr_session(engine="mock")
        progress_events = [
            ASRSessionEvent(
                id=1,
                event="transcribing_progress",
                data={"sequence": index},
            )
            for index in range(500)
        ]
        progress_events.append(
            ASRSessionEvent(id=1, event="completed", data={"status": "completed"})
        )
        _append_events(session.session_id, progress_events)

        started_at = time.perf_counter()
        stream = collect_sse_chunks(session.session_id)
        elapsed = time.perf_counter() - started_at

        self.assertLess(elapsed, 1.0)
        self.assertEqual(stream.count("event: transcribing_progress"), 500)
        self.assertEqual(stream.count("event: completed"), 1)

        stored = _read_events(session.session_id)
        resume_after = stored[-52].id
        resumed = collect_sse_chunks(session.session_id, last_event_id=resume_after)
        self.assertEqual(resumed.count("event: transcribing_progress"), 50)
        self.assertEqual(resumed.count("event: completed"), 1)
        self.assertNotIn(f"id: {resume_after}\n", resumed)

    def test_chunked_long_audio_events_include_progress(self):
        session = create_asr_session(engine="sensevoice")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            with (
                patch("app.api.asr_sessions.create_asr_engine", return_value=FakeChunkEngine()),
                patch("app.api.asr_sessions._should_use_chunked_session", return_value=(True, 420.0)),
                patch("app.api.asr_sessions.split_audio_to_chunks", return_value=fake_audio_chunks()),
            ):
                uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        self.assertEqual(uploaded.status, "stream_ready")
        result = read_asr_session_result(session.session_id)
        self.assertEqual(result.engine, "fake-sensevoice-chunked")
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(result.segments[1].start_time, 300.0)

        events = _read_events(session.session_id)
        event_names = [event.event for event in events]
        self.assertIn("chunk_plan", event_names)
        self.assertEqual(event_names.count("chunk_started"), 2)
        self.assertEqual(event_names.count("chunk_completed"), 2)
        self.assertEqual(event_names.count("segment"), 2)
        self.assertLess(event_names.index("chunk_plan"), event_names.index("segment"))

        chunk_plan = next(event for event in events if event.event == "chunk_plan")
        self.assertEqual(chunk_plan.data["total_chunks"], 2)
        first_segment = next(event for event in events if event.event == "segment")
        self.assertTrue(first_segment.data["partial"])
        self.assertEqual(first_segment.data["chunk_index"], 1)
        self.assertEqual(first_segment.data["progress"], 0.5)
        stream = collect_sse_chunks(session.session_id)
        self.assertIn("event: chunk_started", stream)
        self.assertIn("event: chunk_completed", stream)
        self.assertIn("\"partial\": true", stream)
        self.assertIn("event: completed", stream)

    def test_chunk_failure_events_include_retry_hint(self):
        session = create_asr_session(engine="sensevoice")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            with (
                patch("app.api.asr_sessions.create_asr_engine", return_value=FakeChunkEngine(fail_on=2)),
                patch("app.api.asr_sessions._should_use_chunked_session", return_value=(True, 420.0)),
                patch("app.api.asr_sessions.split_audio_to_chunks", return_value=fake_audio_chunks()),
            ):
                uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()

        self.assertEqual(uploaded.status, "failed")
        events = _read_events(session.session_id)
        event_names = [event.event for event in events]
        self.assertIn("chunk_failed", event_names)
        self.assertEqual(event_names[-1], "failed")

        failed_chunk = next(event for event in events if event.event == "chunk_failed")
        self.assertEqual(failed_chunk.data["chunk_index"], 2)
        self.assertTrue(failed_chunk.data["retryable"])
        self.assertIn("重新上传重试", failed_chunk.data["retry_hint"])

        stream = collect_sse_chunks(session.session_id)
        self.assertIn("event: chunk_failed", stream)
        self.assertIn("retry_hint", stream)
        self.assertIn("event: failed", stream)


if __name__ == "__main__":
    unittest.main()
