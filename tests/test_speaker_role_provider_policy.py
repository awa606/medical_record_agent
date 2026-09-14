import unittest

from app.services.asr.speaker_role_policy import (
    ACTION_AUTO_ACCEPT,
    ACTION_BLOCKED,
    ACTION_NEEDS_REVIEW,
    speaker_role_decision,
)


DOCTOR = "\u533b\u751f"
PATIENT = "\u60a3\u8005"


class SpeakerRoleProviderPolicyTests(unittest.TestCase):
    def test_same_raw_confidence_can_resolve_differently_by_provider(self):
        rules = speaker_role_decision(
            speaker_id="spk0",
            role=DOCTOR,
            confidence=0.91,
            source="speaker_context_rules",
            speaker_count=2,
        )
        llm = speaker_role_decision(
            speaker_id="spk0",
            role=DOCTOR,
            confidence=0.91,
            source="ollama_qwen3_speaker_context",
            speaker_count=2,
        )

        self.assertEqual(rules.provider, "rules")
        self.assertEqual(rules.action, ACTION_AUTO_ACCEPT)
        self.assertEqual(llm.provider, "llm")
        self.assertEqual(llm.action, ACTION_NEEDS_REVIEW)
        self.assertLess(llm.calibrated_confidence, rules.calibrated_confidence)

    def test_rules_threshold_boundaries(self):
        auto = speaker_role_decision(
            speaker_id="spk0",
            role=DOCTOR,
            confidence=0.9,
            source="speaker_context_rules",
            speaker_count=2,
        )
        review = speaker_role_decision(
            speaker_id="spk1",
            role=PATIENT,
            confidence=0.65,
            source="speaker_context_rules",
            speaker_count=2,
        )
        blocked = speaker_role_decision(
            speaker_id="spk2",
            role=PATIENT,
            confidence=0.64,
            source="speaker_context_rules",
            speaker_count=2,
        )

        self.assertEqual(auto.action, ACTION_AUTO_ACCEPT)
        self.assertEqual(review.action, ACTION_NEEDS_REVIEW)
        self.assertEqual(blocked.action, ACTION_NEEDS_REVIEW)

    def test_unknown_provider_downgrades_to_review_even_with_high_confidence(self):
        decision = speaker_role_decision(
            speaker_id="spk0",
            role=DOCTOR,
            confidence=0.99,
            source="experimental_provider",
            speaker_count=2,
        )

        self.assertEqual(decision.provider, "unknown")
        self.assertEqual(decision.reason_code, "unknown_provider")
        self.assertEqual(decision.action, ACTION_NEEDS_REVIEW)

    def test_single_speaker_counterexample_is_blocked(self):
        decision = speaker_role_decision(
            speaker_id="spk0",
            role=None,
            confidence=0.0,
            source="single_speaker",
            speaker_count=1,
        )

        self.assertEqual(decision.predicted_role, "\u5176\u4ed6")
        self.assertEqual(decision.reason_code, "single_speaker_counterexample")
        self.assertEqual(decision.action, ACTION_BLOCKED)

    def test_manual_reviewed_source_auto_accepts(self):
        decision = speaker_role_decision(
            speaker_id="spk0",
            role=DOCTOR,
            confidence=0.4,
            source="manual_speaker_map",
            reviewed_by_doctor=True,
            speaker_count=2,
        )

        self.assertEqual(decision.provider, "manual")
        self.assertEqual(decision.action, ACTION_AUTO_ACCEPT)
        self.assertGreaterEqual(decision.calibrated_confidence, 0.99)


if __name__ == "__main__":
    unittest.main()
