from __future__ import annotations

import tempfile
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from app.services.asr.funasr_streaming_engine import FunASRStreamingEngine, StreamingConfig


class FakeStreamingModel:
    def __init__(self, texts: list[str]) -> None:
        self.texts = iter(texts)
        self.calls: list[dict[str, object]] = []

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        return [{"text": next(self.texts)}]


class FunASRStreamingEngineTests(unittest.TestCase):
    def test_streaming_engine_uses_registered_model_key_and_disables_update_check(self):
        module = types.ModuleType("funasr")
        calls = []

        class FakeAutoModel:
            def __init__(self, **kwargs):
                calls.append(kwargs)

        module.AutoModel = FakeAutoModel
        with patch.dict(sys.modules, {"funasr": module}):
            engine = FunASRStreamingEngine(hotword_path=None)

        self.assertEqual(engine.model_id, "ParaformerStreaming")
        self.assertEqual(calls[0]["model"], "ParaformerStreaming")
        self.assertTrue(calls[0]["disable_update"])

    def test_streaming_updates_use_actual_audio_time_and_stable_segment_id(self):
        model = FakeStreamingModel(["您好", "哪里不舒服？", "我发热三天。"])
        engine = FunASRStreamingEngine(
            model_instance=model,
            hotword_path=None,
            config=StreamingConfig(chunk_size=(0, 1, 0), segment_seconds=30.0),
        )
        chunks = [np.zeros(960, dtype=np.float32) for _ in range(3)]
        engine._iter_pcm_chunks = lambda _path: iter(chunks)  # type: ignore[method-assign]
        engine._probe_duration = lambda _path: 0.18  # type: ignore[method-assign]
        progress_events: list[dict[str, object]] = []
        segment_events: list[tuple[str, object, dict[str, object]]] = []

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"RIFF")
            result = engine.transcribe_streaming(
                "audio-1",
                audio_path,
                on_progress=progress_events.append,
                on_segment=lambda name, segment, data: segment_events.append((name, segment, data)),
            )

        self.assertEqual([event[0] for event in segment_events], ["segment", "segment_update", "segment"])
        first_id = segment_events[0][1].segment_id
        self.assertEqual(first_id, segment_events[1][1].segment_id)
        self.assertNotEqual(first_id, segment_events[2][1].segment_id)
        self.assertTrue(segment_events[0][1].provisional)
        self.assertTrue(segment_events[1][1].provisional)
        self.assertTrue(all(segment.provisional for segment in result.segments))
        self.assertEqual(result.duration, 0.18)
        self.assertEqual(len(result.segments), 2)
        self.assertEqual(progress_events[-1]["progress"], 1.0)
        self.assertEqual(progress_events[-1]["progress_kind"], "actual")
        self.assertTrue(model.calls[-1]["is_final"])

    def test_streaming_text_can_finalize_by_elapsed_audio_window(self):
        model = FakeStreamingModel(["患者出现", "持续发热"])
        engine = FunASRStreamingEngine(
            model_instance=model,
            hotword_path=None,
            config=StreamingConfig(chunk_size=(0, 1, 0), segment_seconds=0.1),
        )
        engine._iter_pcm_chunks = lambda _path: iter(  # type: ignore[method-assign]
            [np.zeros(960, dtype=np.float32), np.zeros(960, dtype=np.float32)]
        )
        engine._probe_duration = lambda _path: 0.12  # type: ignore[method-assign]

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"RIFF")
            result = engine.transcribe_streaming("audio-2", audio_path)

        self.assertEqual(len(result.segments), 1)
        self.assertTrue(result.segments[0].provisional)
        self.assertEqual(result.segments[0].start_time, 0.0)
        self.assertEqual(result.segments[0].end_time, 0.12)


if __name__ == "__main__":
    unittest.main()
