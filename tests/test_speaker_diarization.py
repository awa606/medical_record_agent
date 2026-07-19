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
    def test_single_speaker_script_is_not_faked_as_doctor_and_patient(self):
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
        self.assertEqual(len(enhanced.segments), 1)
        self.assertIsNone(enhanced.segments[0].role)
        self.assertTrue(enhanced.needs_review)
        self.assertEqual(len(enhanced.speaker_assignments), 1)
        self.assertTrue(enhanced.speaker_assignments[0].requires_confirmation)
        self.assertIn("[说话人 A]", enhanced.conversation_text)
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
        self.assertEqual(speaker_sources["spk0"], "speaker_context_rules")
        self.assertGreater(speaker_confidence["spk0"] or 0, 0.5)

    def test_short_filler_cluster_is_merged_into_adjacent_primary_speaker(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="请问哪里不舒服？嗯，我发热三天。",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk1", text="请问哪里不舒服？", start_time=0.0, end_time=4.0),
                ASRSegment(speaker="spk0", text="嗯", start_time=4.0, end_time=4.4),
                ASRSegment(speaker="spk2", text="我发热三天。", start_time=4.4, end_time=8.5),
            ],
        )

        enhanced = enhance_speaker_diarization(result)

        self.assertEqual(len({segment.speaker_id for segment in enhanced.segments}), 2)
        self.assertEqual({item.role for item in enhanced.speaker_assignments}, {"医生", "患者"})
        self.assertNotIn("待确认", {segment.role for segment in enhanced.segments})

    def test_short_meaningful_third_speaker_is_not_auto_merged(self):
        result = ASRResult(
            audio_id="three_person_visit",
            engine="funasr",
            text="医生问诊，患者回答，家属补充。",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk1", text="请问哪里不舒服？有没有发热？", start_time=0.0, end_time=4.0),
                ASRSegment(speaker="spk2", text="我发热三天，头也很痛。", start_time=4.2, end_time=8.2),
                ASRSegment(speaker="spk3", text="她昨天晚上还吐了一次。", start_time=8.4, end_time=10.1),
            ],
        )

        enhanced = enhance_speaker_diarization(result)

        self.assertEqual({segment.speaker_id for segment in enhanced.segments}, {"spk1", "spk2", "spk3"})
        self.assertEqual(len(enhanced.speaker_assignments), 3)
        self.assertTrue(enhanced.needs_review)
        self.assertTrue(any(item.speaker_id == "spk3" and item.requires_confirmation for item in enhanced.speaker_assignments))

    def test_same_speaker_short_filler_and_answer_are_merged(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="您今年多少岁？嗯，二十四岁。",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk0", text="您今年多少岁？", start_time=0.0, end_time=2.0),
                ASRSegment(speaker="spk1", text="嗯，", start_time=2.1, end_time=2.3),
                ASRSegment(speaker="spk1", text="二十四岁。", start_time=2.3, end_time=3.0),
            ],
        )

        enhanced = enhance_speaker_diarization(result)
        patient_turns = [segment for segment in enhanced.segments if segment.role == "患者"]

        self.assertEqual(len(patient_turns), 1)
        self.assertEqual(patient_turns[0].text, "嗯，二十四岁。")

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


    def test_mixed_segment_is_split_by_diarization_turns(self):
        from app.schemas.asr import DiarizationTurn

        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="doctor asks patient answers",
            conversation_text="",
            segments=[
                ASRSegment(
                    segment_id="mixed-1",
                    speaker="spk0",
                    speaker_id="spk0",
                    text="doctor asks patient answers",
                    start_time=0.0,
                    end_time=4.0,
                )
            ],
            diarization_turns=[
                DiarizationTurn(start_time=0.0, end_time=2.0, speaker_id="spk0", confidence=0.91),
                DiarizationTurn(start_time=2.0, end_time=4.0, speaker_id="spk1", confidence=0.88),
            ],
        )

        enhanced = enhance_speaker_diarization(result)

        self.assertGreaterEqual(len(enhanced.segments), 2)
        self.assertEqual(enhanced.segments[0].speaker_id, "spk0")
        self.assertEqual(enhanced.segments[1].speaker_id, "spk1")
        self.assertEqual(enhanced.segments[0].start_time, 0.0)
        self.assertEqual(enhanced.segments[0].end_time, 2.0)
        self.assertEqual(enhanced.segments[1].start_time, 2.0)
        self.assertEqual(enhanced.segments[1].end_time, 4.0)
        self.assertTrue(all(segment.original_text == "doctor asks patient answers" for segment in enhanced.segments[:2]))

    def test_segment_is_not_split_without_diarization_turns(self):
        result = ASRResult(
            audio_id="demo_audio",
            engine="funasr",
            text="doctor asks patient answers",
            conversation_text="",
            segments=[
                ASRSegment(
                    segment_id="mixed-1",
                    speaker="spk0",
                    speaker_id="spk0",
                    text="doctor asks patient answers",
                    start_time=0.0,
                    end_time=4.0,
                )
            ],
        )

        enhanced = enhance_speaker_diarization(result)

        self.assertEqual(len(enhanced.segments), 1)
        self.assertEqual(enhanced.segments[0].segment_id, "mixed-1")
        self.assertEqual(enhanced.segments[0].speaker_id, "spk0")


if __name__ == "__main__":
    unittest.main()
