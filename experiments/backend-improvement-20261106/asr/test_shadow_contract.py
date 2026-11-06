"""Synthetic contract controls; results are not ASR or diarization scores."""
from __future__ import annotations

import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

from shadow_contract import EventLedger, score_saved_turns, sortformer_turns


def event(revision=1, observed=2500, **changes):
    segment = {"segment_id": "s1", "revision": revision, "provisional": True,
               "start_time": 0., "end_time": 2., "text": "我有咳嗽", "speaker_id": "streaming", "role": None}
    segment.update(changes)
    return {"session_id": "test", "clock": "capture_relative_monotonic_ms", "observed_ms": observed, "segment": segment}


class EventContractTests(unittest.TestCase):
    def test_later_role_does_not_rewrite_first_text_or_history(self):
        ledger = EventLedger("test")
        original = event()
        frozen = copy.deepcopy(original)
        ledger.add(original)
        ledger.add(event(2, 2800, provisional=False))
        ledger.add(event(3, 5000, provisional=False, speaker_id="speaker_1", role="患者", role_action="auto_accept"))
        self.assertEqual(original, frozen)
        self.assertIsNone(ledger.history[0]["segment"]["role"])
        result = ledger.summary()
        self.assertEqual(result["first_text_seconds"], 2.5)
        self.assertAlmostEqual(result["first_stable_delay_p95_seconds"], .8)
        self.assertEqual(result["first_observed_accepted_role_seconds"], 5.)
        self.assertIsNone(result["role_accuracy"])
        self.assertIsNone(result["patient_subject_accuracy"])

    def test_stable_text_is_not_accepted_clinical_role(self):
        ledger = EventLedger("test")
        ledger.add(event(provisional=False))
        ledger.add(event(2, 2800, provisional=False, role="患者", role_action="auto_accept"))
        self.assertEqual(ledger.summary()["current_stable_segments_without_accepted_role"], 1)
        self.assertIsNone(ledger.summary()["first_observed_accepted_role_seconds"])

    def test_duplicate_and_late_old_revision_do_not_override(self):
        ledger = EventLedger("test")
        ledger.add(event())
        ledger.add(event(2, 2700, text="我有咳嗽两天", provisional=False))
        self.assertEqual(ledger.add(event(2, 2800, text="我有咳嗽两天", provisional=False)), "duplicate_ignored")
        self.assertEqual(ledger.add(event(1, 2900)), "stale_ignored")
        self.assertEqual(ledger.latest["s1"]["text"], "我有咳嗽两天")

    def test_same_revision_changed_evidence_rejected(self):
        ledger = EventLedger("test")
        ledger.add(event())
        with self.assertRaisesRegex(ValueError, "same revision"):
            ledger.add(event(text="否认咳嗽"))

    def test_cross_session_and_mismatched_clock_rejected(self):
        for override in [{"session_id": "another"}, {"clock": "unix_epoch_ms"}]:
            with self.subTest(override=override), self.assertRaises(ValueError):
                EventLedger("test").add({**event(), **override})

    def test_invalid_audio_clock_or_interval_rejected(self):
        for sample in [event(observed=500), event(start_time=-1), event(end_time=0), event(observed=float('nan'))]:
            with self.subTest(sample=sample), self.assertRaises(ValueError):
                EventLedger("test").add(sample)

    def test_observation_clock_cannot_move_backwards(self):
        ledger = EventLedger("test")
        ledger.add(event(observed=3000))
        with self.assertRaisesRegex(ValueError, "backwards"):
            ledger.add(event(2, 2900))

    def test_revoked_role_is_unresolved_now_but_arrival_history_is_preserved(self):
        ledger = EventLedger("test")
        ledger.add(event(provisional=False, speaker_id="speaker_0", role="患者", role_action="auto_accept"))
        ledger.add(event(2, 3000, provisional=False, speaker_id="unknown", role=None))
        result = ledger.summary()
        self.assertEqual(result["current_stable_segments_without_accepted_role"], 1)
        self.assertEqual(result["first_observed_accepted_role_seconds"], 2.5)

    def test_malformed_speaker_role_fields_rejected_at_ingest(self):
        for changes in [{"speaker_id": []}, {"role": []}, {"role_action": []}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                EventLedger("test").add(event(**changes))

    def test_nemo_adapter_keeps_generic_identity_only(self):
        result = sortformer_turns(["0.1 1.5 speaker_0", "1.5 2.0 speaker_1"])
        self.assertEqual(result[1]["speaker_id"], "speaker_1")
        self.assertNotIn("role", result[0])
        for text in ["0 1", "2 1 speaker_0", "nan 1 speaker_0"]:
            with self.subTest(text=text), self.assertRaises(ValueError):
                sortformer_turns([text])


class ScoringAdapterTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.rttm = Path(self.folder.name) / "reference.rttm"
        self.rttm.write_text("SPEAKER control 1 0.0 1.0 <NA> <NA> a <NA> <NA>\nSPEAKER control 1 1.0 1.0 <NA> <NA> b <NA> <NA>\n", encoding="utf-8")
        self.provenance = {"truth_kind": "human_reviewed_rttm", "reference_rttm_sha256": hashlib.sha256(self.rttm.read_bytes()).hexdigest(),
                           "audio_sha256": "a" * 64, "hypothesis_audio_sha256": "a" * 64, "audio_duration_seconds": 2.}
        self.turns = sortformer_turns(["0 1 speaker_0", "1 2 speaker_1"])

    def tearDown(self):
        self.folder.cleanup()

    def test_scoring_reuses_existing_metrics_not_runtime_or_role_claims(self):
        result = score_saved_turns(self.rttm, self.turns, self.provenance)
        self.assertEqual(result["boundary_f1"], 1.)
        self.assertEqual(result["speaker_count_error"], 0)
        self.assertEqual(result["mixed_utterance_rate"], 0.)
        self.assertEqual(result["model_calls"], 0)
        self.assertIsNone(result["medical_role_accuracy"])
        self.assertIsNone(result["rtf"])

    def test_rejects_tts_equal_time_truth_and_wrong_audio(self):
        for changes in [{"truth_kind": "tts_equal_duration"}, {"hypothesis_audio_sha256": "b" * 64}, {"audio_duration_seconds": 1.}]:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                score_saved_turns(self.rttm, self.turns, {**self.provenance, **changes})

    def test_reference_tampering_rejected(self):
        self.rttm.write_text(self.rttm.read_text(encoding="utf-8") + "# changed\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            score_saved_turns(self.rttm, self.turns, self.provenance)

    def test_multiple_audio_files_in_one_rttm_rejected(self):
        self.rttm.write_text(self.rttm.read_text(encoding="utf-8").replace("SPEAKER control 1 1.0", "SPEAKER another 1 1.0"), encoding="utf-8")
        self.provenance["reference_rttm_sha256"] = hashlib.sha256(self.rttm.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "one audio"):
            score_saved_turns(self.rttm, self.turns, self.provenance)


if __name__ == "__main__":
    unittest.main()
