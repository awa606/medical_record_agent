import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas import ASRResult, ASRSegment
from app.services.asr.chunking import (
    AudioChunk,
    ChunkTranscription,
    build_chunk_plan,
    merge_chunk_transcriptions,
    split_audio_to_chunks,
)


class ASRChunkingTests(unittest.TestCase):
    def test_build_chunk_plan_splits_remainder(self):
        plan = build_chunk_plan(total_seconds=725, chunk_seconds=300)

        self.assertEqual(plan, [(0.0, 300.0), (300.0, 300.0), (600.0, 125.0)])

    def test_merge_chunk_transcriptions_offsets_segment_times(self):
        chunk_one = AudioChunk(index=1, path=Path("chunk_001.wav"), start_seconds=0.0, duration_seconds=300.0)
        chunk_two = AudioChunk(index=2, path=Path("chunk_002.wav"), start_seconds=300.0, duration_seconds=120.0)
        first = ASRResult(
            audio_id="first",
            engine="fake",
            text="first text",
            conversation_text="[spk0] first text",
            segments=[ASRSegment(speaker="spk0", text="first text", start_time=1.0, end_time=3.0)],
            medical_keywords={"expected": ["fever"], "recognized": ["fever"], "missing": []},
        )
        second = ASRResult(
            audio_id="second",
            engine="fake",
            text="second text",
            conversation_text="[spk0] second text",
            segments=[ASRSegment(speaker="spk0", text="second text", start_time=2.0, end_time=4.0)],
            medical_keywords={"expected": ["fever", "cough"], "recognized": [], "missing": ["cough"]},
        )

        merged = merge_chunk_transcriptions(
            "long_audio",
            [
                ChunkTranscription(chunk=chunk_two, result=second),
                ChunkTranscription(chunk=chunk_one, result=first),
            ],
            original_duration=420.0,
        )

        self.assertEqual(merged.audio_id, "long_audio")
        self.assertEqual(merged.engine, "fake-chunked")
        self.assertEqual(merged.text, "first text\nsecond text")
        self.assertEqual(merged.duration, 420.0)
        self.assertEqual(merged.segments[1].start_time, 302.0)
        self.assertEqual(merged.segments[1].end_time, 304.0)
        self.assertEqual(merged.medical_keywords["recognized"], ["fever"])
        self.assertEqual(merged.medical_keywords["missing"], ["cough"])

    def test_split_audio_to_chunks_requires_ffmpeg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio = root / "sample.wav"
            audio.write_bytes(b"fake audio")

            with patch("app.services.asr.chunking.find_ffmpeg_executable", return_value=None):
                with self.assertRaises(FileNotFoundError) as context:
                    split_audio_to_chunks(audio, root / "chunks")

        self.assertIn("ffmpeg not found", str(context.exception))


if __name__ == "__main__":
    unittest.main()
