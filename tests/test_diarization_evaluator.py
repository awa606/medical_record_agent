from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.schemas.asr import DiarizationTurn
from scripts.evaluate_diarization import evaluate_turns, parse_rttm


class DiarizationEvaluatorTests(unittest.TestCase):
    def test_parse_rttm_and_perfect_boundaries(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sample.rttm"
            path.write_text(
                "SPEAKER sample 1 0.000 2.000 <NA> <NA> doctor <NA> <NA>\n"
                "SPEAKER sample 1 2.000 2.000 <NA> <NA> patient <NA> <NA>\n",
                encoding="utf-8",
            )
            turns = parse_rttm(path)

        metrics = evaluate_turns(turns, turns)
        self.assertEqual(len(turns), 2)
        self.assertEqual(metrics.speaker_count_error, 0)
        self.assertEqual(metrics.boundary_f1, 1.0)
        self.assertEqual(metrics.mixed_utterance_rate, 0.0)
        self.assertEqual(metrics.role_consistency, 1.0)

    def test_mixed_utterance_rate_detects_cross_speaker_turn(self):
        reference = [
            DiarizationTurn(start_time=0.0, end_time=2.0, speaker_id="doctor"),
            DiarizationTurn(start_time=2.0, end_time=4.0, speaker_id="patient"),
        ]
        hypothesis = [
            DiarizationTurn(start_time=0.0, end_time=4.0, speaker_id="speaker_0"),
        ]

        metrics = evaluate_turns(reference, hypothesis)

        self.assertEqual(metrics.speaker_count_error, -1)
        self.assertEqual(metrics.boundary_f1, 0.0)
        self.assertEqual(metrics.mixed_utterance_rate, 1.0)
        self.assertEqual(metrics.role_consistency, 0.5)


if __name__ == "__main__":
    unittest.main()
