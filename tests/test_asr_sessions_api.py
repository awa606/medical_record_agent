import asyncio
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.asr_sessions import (
    _append_events,
    _asr_session_event_stream,
    _chunk_seconds_for_duration,
    _read_events,
    _write_session_result,
    _should_use_realtime_upload_session,
    create_asr_session,
    read_asr_session_result,
    update_asr_session_result,
    upload_asr_session_audio,
)
from app.api.audio import _write_transcript, read_audio_transcript
from app.main import app
from app.schemas import (
    ASRResult,
    ASRSegment,
    ASRSegmentCorrection,
    ASRSpeakerRoleCorrection,
    ASRSessionCorrectionRequest,
    ASRSessionEvent,
    SpeakerRoleAssignment,
)
from app.services.asr.role_quality import attach_speaker_role_quality
from app.services.asr import AudioChunk


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
        route_paths = set(app.openapi()["paths"])

        self.assertIn("/api/asr/sessions", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/audio", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/events", route_paths)
        self.assertIn("/api/asr/sessions/{session_id}/result", route_paths)

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
        self.assertIn("speaker_mapping_required", event_names)
        mapping_events = [event for event in events if event.event == "speaker_mapping_required"]
        self.assertEqual(len(mapping_events), 1)
        self.assertEqual(len(mapping_events[-1].data["pending_confirmation"]), 2)
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

    def test_upload_route_starts_background_transcription_and_streams_events(self):
        client = TestClient(app)
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

    def test_speaker_role_review_clears_one_global_confirmation_set(self):
        session = create_asr_session(engine="mock")
        fake_file = FakeUploadFile(b"RIFF....WAVEfmt ")
        try:
            uploaded = upload_asr_session_audio(session.session_id, fake_file)
        finally:
            fake_file.close()
        pending_result = attach_speaker_role_quality(
            ASRResult(
                audio_id=uploaded.audio_id,
                engine="funasr",
                text="请问哪里不舒服\n我发热三天",
                conversation_text="[医生] 请问哪里不舒服\n[患者] 我发热三天",
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role="医生",
                        role_confidence=0.66,
                        role_source="speaker_context_rules",
                        text="请问哪里不舒服",
                    ),
                    ASRSegment(
                        speaker_id="spk1",
                        role="患者",
                        role_confidence=0.86,
                        role_source="global_two_party_constraint",
                        text="我发热三天",
                    ),
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk0",
                        role="医生",
                        confidence=0.66,
                        source="speaker_context_rules",
                    ),
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role="患者",
                        confidence=0.86,
                        source="global_two_party_constraint",
                    ),
                ],
            )
        )
        self.assertEqual(pending_result.role_quality.status, "needs_review")
        self.assertEqual(len(pending_result.role_quality.pending_confirmation), 2)
        _write_session_result(session.session_id, pending_result)
        _write_transcript(pending_result)

        response = update_asr_session_result(
            session.session_id,
            ASRSessionCorrectionRequest(
                speaker_roles=[
                    ASRSpeakerRoleCorrection(speaker_id="spk0", role="医生"),
                    ASRSpeakerRoleCorrection(speaker_id="spk1", role="患者"),
                ],
                reviewer="doctor",
            ),
        )

        self.assertEqual(response.asr_result.role_quality.status, "passed")
        self.assertEqual(response.asr_result.role_quality.pending_confirmation, [])
        self.assertTrue(response.asr_result.reviewed_by_doctor)

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
