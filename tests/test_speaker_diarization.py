import unittest

from app.api.asr_sessions import _apply_segment_corrections
from app.schemas.asr import (
    ASRResult,
    ASRSegment,
    ASRSegmentCorrection,
    ASRSessionCorrectionRequest,
    ASRSpeakerRoleCorrection,
)
from app.services.asr.speaker_diarization import enhance_speaker_diarization


class SpeakerDiarizationAssistTests(unittest.TestCase):
    def test_long_single_segment_is_split_into_reviewable_role_turns(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="你好，请问哪里不舒服？我发热三天，还有咳嗽。有没有胸闷？有一点胸闷，没有过敏。",
            conversation_text="",
            segments=[
                ASRSegment(
                    speaker="spk0",
                    text="你好，请问哪里不舒服？我发热三天，还有咳嗽。有没有胸闷？有一点胸闷，没有过敏。",
                )
            ],
        )

        enhanced = enhance_speaker_diarization(result)
        roles = [segment.role for segment in enhanced.segments]

        self.assertGreaterEqual(len(enhanced.segments), 3)
        self.assertIn("医生", roles)
        self.assertIn("患者", roles)
        self.assertTrue(enhanced.needs_review)
        self.assertIn("[医生]", enhanced.conversation_text)
        self.assertIn("[患者]", enhanced.conversation_text)
        self.assertTrue(enhanced.warnings)

    def test_two_speaker_segments_get_role_map_confidence(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="sensevoice",
            text="请问哪里不舒服？我发热三天。",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk0", text="请问哪里不舒服？有没有发热？"),
                ASRSegment(speaker="spk1", text="我发热三天，还有咳嗽。"),
            ],
        )

        enhanced = enhance_speaker_diarization(result)

        speaker_roles = {segment.speaker: segment.role for segment in enhanced.segments}
        speaker_sources = {segment.speaker: segment.role_source for segment in enhanced.segments}
        speaker_confidence = {segment.speaker: segment.role_confidence for segment in enhanced.segments}

        self.assertEqual(speaker_roles["spk0"], "医生")
        self.assertEqual(speaker_roles["spk1"], "患者")
        self.assertEqual(speaker_sources["spk0"], "speaker_map")
        self.assertGreater(speaker_confidence["spk0"] or 0, 0.5)

    def test_manual_role_correction_is_marked_as_doctor_reviewed(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="mock",
            text="我发热三天。",
            conversation_text="",
            segments=[ASRSegment(speaker="spk1", role="待确认", text="我发热三天。")],
        )

        corrected = _apply_segment_corrections(
            result,
            ASRSessionCorrectionRequest(
                segments=[
                    ASRSegmentCorrection(index=0, role="患者", text="我发热三天。", reviewed_by_doctor=True)
                ],
            ),
        )

        self.assertEqual(corrected.segments[0].role, "患者")
        self.assertEqual(corrected.segments[0].role_source, "manual")
        self.assertEqual(corrected.segments[0].role_confidence, 0.98)
        self.assertFalse(corrected.needs_review)

    def test_global_speaker_role_correction_updates_every_turn(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="请问哪里不舒服？还有其他症状吗？",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk0", speaker_id="spk0", text="请问哪里不舒服？"),
                ASRSegment(speaker="spk1", speaker_id="spk1", text="我发热三天。"),
                ASRSegment(speaker="spk0", speaker_id="spk0", text="还有其他症状吗？"),
            ],
        )

        corrected = _apply_segment_corrections(
            result,
            ASRSessionCorrectionRequest(
                speaker_roles=[
                    ASRSpeakerRoleCorrection(
                        speaker_id="spk0",
                        role="医生",
                        reviewed_by_doctor=True,
                    )
                ]
            ),
        )

        doctor_turns = [segment for segment in corrected.segments if segment.speaker_id == "spk0"]
        self.assertEqual(len(doctor_turns), 2)
        self.assertTrue(all(segment.role == "医生" for segment in doctor_turns))
        self.assertTrue(all(segment.role_source == "manual_speaker_map" for segment in doctor_turns))


if __name__ == "__main__":
    unittest.main()
