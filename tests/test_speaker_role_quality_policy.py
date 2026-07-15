import unittest

from app.schemas.asr import ASRResult, ASRSegment, SpeakerRoleAssignment
from app.services.asr.role_quality import build_speaker_role_quality


DOCTOR = "\u533b\u751f"
PATIENT = "\u60a3\u8005"
OTHER = "\u5176\u4ed6"


class SpeakerRoleQualityPolicyTests(unittest.TestCase):
    def test_ollama_capped_confidence_requires_review(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u6211\u53d1\u70ed\u4e09\u5929",
                conversation_text=f"[{PATIENT}] \u6211\u53d1\u70ed\u4e09\u5929",
                segments=[
                    ASRSegment(
                        speaker_id="spk1",
                        role=PATIENT,
                        role_confidence=0.88,
                        role_source="ollama_qwen3_speaker_context",
                        text="\u6211\u53d1\u70ed\u4e09\u5929",
                    )
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=PATIENT,
                        confidence=0.88,
                        source="ollama_qwen3_speaker_context",
                    )
                ],
            )
        )

        self.assertEqual(quality.status, "needs_review")
        self.assertEqual(quality.metrics.low_confidence_clinical_role_count, 1)

    def test_two_party_constraint_confidence_requires_review(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u6211\u53d1\u70ed\u4e09\u5929",
                conversation_text=f"[{PATIENT}] \u6211\u53d1\u70ed\u4e09\u5929",
                segments=[
                    ASRSegment(
                        speaker_id="spk1",
                        role=PATIENT,
                        role_confidence=0.86,
                        role_source="global_two_party_constraint",
                        text="\u6211\u53d1\u70ed\u4e09\u5929",
                    )
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=PATIENT,
                        confidence=0.86,
                        source="global_two_party_constraint",
                    )
                ],
            )
        )

        self.assertEqual(quality.status, "needs_review")
        self.assertEqual(quality.metrics.low_confidence_clinical_role_count, 1)

    def test_manual_role_confirmation_passes_below_auto_threshold(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d",
                conversation_text=f"[{DOCTOR}] \u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d",
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        role_confidence=0.4,
                        role_source="manual_speaker_map",
                        reviewed_by_doctor=True,
                        text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d",
                    )
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        confidence=0.4,
                        source="manual_speaker_map",
                    )
                ],
            )
        )

        self.assertEqual(quality.status, "passed")
        self.assertEqual(quality.metrics.low_confidence_clinical_role_count, 0)

    def test_unmapped_speaker_requires_review(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u6211\u53d1\u70ed\u4e09\u5929",
                conversation_text="[\u8bf4\u8bdd\u4eba A] \u6211\u53d1\u70ed\u4e09\u5929",
                segments=[ASRSegment(speaker_id="spk1", role=None, text="\u6211\u53d1\u70ed\u4e09\u5929")],
            )
        )

        self.assertEqual(quality.status, "needs_review")
        self.assertEqual(quality.metrics.unmapped_speaker_count, 1)

    def test_mixed_utterance_blocks_gate(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\u6211\u53d1\u70ed\u4e09\u5929",
                conversation_text=f"[{DOCTOR}] \u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\u6211\u53d1\u70ed\u4e09\u5929",
                segments=[
                    ASRSegment(
                        speaker_id="spk0",
                        role=DOCTOR,
                        role_confidence=0.99,
                        role_source="speaker_context_rules",
                        text="\u8bf7\u95ee\u54ea\u91cc\u4e0d\u8212\u670d\uff0c\u6211\u53d1\u70ed\u4e09\u5929",
                    )
                ],
            )
        )

        self.assertEqual(quality.status, "blocked")
        self.assertEqual(quality.metrics.mixed_utterance_candidate_count, 1)

    def test_expected_role_mismatch_blocks_gate(self):
        quality = build_speaker_role_quality(
            ASRResult(
                audio_id="a1",
                engine="funasr",
                text="\u6211\u53d1\u70ed\u4e09\u5929",
                conversation_text=f"[{DOCTOR}] \u6211\u53d1\u70ed\u4e09\u5929",
                segments=[
                    ASRSegment(
                        speaker_id="spk1",
                        role=DOCTOR,
                        role_confidence=0.99,
                        role_source="speaker_context_rules",
                        text="\u6211\u53d1\u70ed\u4e09\u5929",
                    )
                ],
                speaker_assignments=[
                    SpeakerRoleAssignment(
                        speaker_id="spk1",
                        role=DOCTOR,
                        confidence=0.99,
                        source="speaker_context_rules",
                    )
                ],
            ),
            expected_roles={"spk1": PATIENT},
        )

        self.assertEqual(quality.status, "blocked")
        self.assertEqual(quality.metrics.role_accuracy, 0.0)


if __name__ == "__main__":
    unittest.main()
