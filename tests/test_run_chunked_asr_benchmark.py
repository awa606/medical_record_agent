import csv
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.schemas import ASRResult, ASRSegment
from app.services.asr.chunking import AudioChunk
from scripts.run_chunked_asr_benchmark import run_chunked_asr_benchmark


class FakeChunkEngine:
    name = "fake-asr"
    model_load_time_seconds = 0.123

    def __init__(self, fail_on_chunk: int | None = None) -> None:
        self.fail_on_chunk = fail_on_chunk

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        chunk_index = int(audio_path.stem.rsplit("_", 1)[-1])
        if self.fail_on_chunk == chunk_index:
            raise RuntimeError("chunk exploded")
        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text=f"chunk {chunk_index}",
            conversation_text=f"[spk0] chunk {chunk_index}",
            segments=[
                ASRSegment(
                    speaker="spk0",
                    text=f"chunk {chunk_index}",
                    start_time=1.0,
                    end_time=2.0,
                )
            ],
        )


def fake_split_audio_to_chunks(audio_path: Path, output_dir: Path, *, chunk_seconds: int = 300, **_: object):
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks = []
    for index, start in enumerate([0.0, 300.0], start=1):
        path = output_dir / f"{audio_path.stem}_chunk_{index:03d}.wav"
        path.write_bytes(b"fake")
        chunks.append(AudioChunk(index=index, path=path, start_seconds=start, duration_seconds=300.0))
    return chunks


class RunChunkedASRBenchmarkTests(unittest.TestCase):
    def test_chunked_runner_records_measured_sample(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "long.wav").write_bytes(b"fake audio")
            (truth_dir / "long.txt").write_text("chunk 1 chunk 2", encoding="utf-8")

            with patch("scripts.run_chunked_asr_benchmark.create_asr_engine", return_value=FakeChunkEngine()):
                with patch("scripts.run_chunked_asr_benchmark.split_audio_to_chunks", side_effect=fake_split_audio_to_chunks):
                    with patch("scripts.run_chunked_asr_benchmark._audio_duration_seconds", return_value=600.0):
                        summary = run_chunked_asr_benchmark(
                            engines=["sensevoice"],
                            audio_dir=audio_dir,
                            truth_dir=truth_dir,
                            reports_dir=reports_dir,
                            chunk_seconds=300,
                        )

            self.assertEqual(summary["schema_version"], "v0.5.9")
            self.assertEqual(summary["engines"][0]["status"], "measured")
            rows = list(csv.DictReader((reports_dir / "sensevoice_chunked_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(rows[0]["status"], "measured")
            self.assertEqual(rows[0]["chunk_count"], "2")
            self.assertEqual(rows[0]["failed_chunks"], "0")
            self.assertIn("chunk_status/", rows[0]["chunk_status_file"])
            chunk_status = json.loads((reports_dir / rows[0]["chunk_status_file"]).read_text(encoding="utf-8"))
            self.assertEqual(chunk_status["chunk_count"], 2)
            self.assertEqual(chunk_status["failed_chunks"], 0)
            self.assertTrue((reports_dir / "local_model_benchmark.md").exists())

    def test_chunked_runner_records_failed_chunk_without_losing_status(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            audio_dir = root / "audio"
            truth_dir = root / "truth"
            reports_dir = root / "reports"
            audio_dir.mkdir()
            truth_dir.mkdir()
            (audio_dir / "long.wav").write_bytes(b"fake audio")
            (truth_dir / "long.txt").write_text("chunk 1 chunk 2", encoding="utf-8")

            with patch(
                "scripts.run_chunked_asr_benchmark.create_asr_engine",
                return_value=FakeChunkEngine(fail_on_chunk=2),
            ):
                with patch("scripts.run_chunked_asr_benchmark.split_audio_to_chunks", side_effect=fake_split_audio_to_chunks):
                    with patch("scripts.run_chunked_asr_benchmark._audio_duration_seconds", return_value=600.0):
                        summary = run_chunked_asr_benchmark(
                            engines=["sensevoice"],
                            audio_dir=audio_dir,
                            truth_dir=truth_dir,
                            reports_dir=reports_dir,
                            chunk_seconds=300,
                        )

            self.assertEqual(summary["engines"][0]["status"], "failed")
            rows = list(csv.DictReader((reports_dir / "sensevoice_chunked_report.csv").open("r", encoding="utf-8-sig")))
            self.assertEqual(rows[0]["status"], "failed")
            self.assertEqual(rows[0]["chunk_count"], "2")
            self.assertEqual(rows[0]["failed_chunks"], "1")
            self.assertIn("chunk exploded", rows[0]["error"])
            chunk_status = json.loads((reports_dir / rows[0]["chunk_status_file"]).read_text(encoding="utf-8"))
            self.assertEqual(chunk_status["chunks"][1]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
