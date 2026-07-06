import unittest

from app.schemas.asr import ASRResult, ASRSegment
from app.services.asr.role_strategy import apply_manifest_role_strategy


class ASRRoleStrategyTests(unittest.TestCase):
    def test_single_speaker_script_split_restores_doctor_patient_turns(self):
        result = ASRResult(
            audio_id="snakebite_01",
            engine="mock",
            text="你好，哪里不舒服？我是左手手掌被咬了。现在什么感受？感觉这里有点肿痛。",
            conversation_text="",
            segments=[],
        )

        restored = apply_manifest_role_strategy(result, "snakebite_01")

        self.assertEqual(restored.role_strategy, "single_speaker_script_split")
        self.assertFalse(restored.evaluate_diarization)
        self.assertIn("[医生]", restored.conversation_text)
        self.assertIn("[患者]", restored.conversation_text)
        self.assertIn("肿痛", restored.medical_keywords["recognized"])

    def test_manual_speaker_role_map_assigns_roles(self):
        result = ASRResult(
            audio_id="chest_pain_01",
            engine="mock",
            text="哪里不舒服？胸痛。",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk0", text="哪里不舒服？"),
                ASRSegment(speaker="spk1", text="胸痛。"),
            ],
        )

        mapped = apply_manifest_role_strategy(result, "chest_pain_01")

        self.assertEqual(mapped.role_strategy, "manual_speaker_role_map")
        self.assertTrue(mapped.evaluate_diarization)
        self.assertEqual(mapped.segments[0].role, "医生")
        self.assertEqual(mapped.segments[1].role, "患者")
        self.assertIn("[医生]", mapped.conversation_text)
        self.assertIn("[患者]", mapped.conversation_text)

    def test_single_segment_two_speaker_sample_needs_manual_review(self):
        result = ASRResult(
            audio_id="fever_01",
            engine="funasr-paraformer-zh",
            text="发烧三天，淋雨后体温40度，咳嗽，有铁锈色痰，吃过布洛芬后仍反复发热。",
            conversation_text="[spk0] 发烧三天，淋雨后体温40度，咳嗽，有铁锈色痰，吃过布洛芬后仍反复发热。",
            segments=[
                ASRSegment(
                    speaker="spk0",
                    text="发烧三天，淋雨后体温40度，咳嗽，有铁锈色痰，吃过布洛芬后仍反复发热。",
                )
            ],
        )

        mapped = apply_manifest_role_strategy(result, "fever_01")

        self.assertEqual(mapped.role_strategy, "single_segment_needs_review")
        self.assertTrue(mapped.needs_review)
        self.assertTrue(mapped.segments[0].needs_review)
        self.assertIn("[待校正]", mapped.conversation_text)
        self.assertNotIn("[患者]", mapped.conversation_text)
        self.assertTrue(mapped.warnings)
        self.assertIn("speaker role mapping was not applied", mapped.warnings[0])
        self.assertIn("发烧", mapped.medical_keywords["recognized"])

    def test_qwen3_single_segment_keeps_qwen3_manual_review_warning(self):
        result = ASRResult(
            audio_id="fever_01",
            engine="qwen3-asr-0.6b",
            text="patient has fever for three days",
            conversation_text="[待校正] patient has fever for three days",
            segments=[ASRSegment(speaker="qwen3", text="patient has fever for three days")],
            warnings=[
                "Qwen3-ASR did not provide reliable speaker roles; please manually review roles."
            ],
        )

        mapped = apply_manifest_role_strategy(result, "fever_01")

        self.assertEqual(mapped.role_strategy, "single_segment_needs_review")
        self.assertTrue(mapped.needs_review)
        self.assertTrue(mapped.segments[0].needs_review)
        self.assertEqual(mapped.conversation_text, "[待校正] patient has fever for three days")
        self.assertEqual(
            mapped.warnings,
            ["Qwen3-ASR did not provide reliable speaker roles; please manually review roles."],
        )


if __name__ == "__main__":
    unittest.main()
