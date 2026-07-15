import json
import tempfile
import unittest
from pathlib import Path

from app.schemas.asr import ASRResult, ASRSegment, SpeakerRoleAssignment
from scripts.validate_speaker_role_quality import validate_speaker_role_quality


class SpeakerRoleQualityGateTests(unittest.TestCase):
    def test_requires_review_when_speakers_are_unresolved(self):
        result = ASRResult(
            audio_id="a1",
            engine="funasr",
            text="请问哪里不舒服？我发热三天。",
            conversation_text="[说话人 A] 请问哪里不舒服？\n[说话人 B] 我发热三天。",
            segments=[
                ASRSegment(speaker_id="spk0", role=None, role_confidence=0.0, text="请问哪里不舒服？"),
                ASRSegment(speaker_id="spk1", role=None, role_confidence=0.0, text="我发热三天。"),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk0", role=None, confidence=0.0, requires_confirmation=True),
                SpeakerRoleAssignment(speaker_id="spk1", role=None, confidence=0.0, requires_confirmation=True),
            ],
        )

        report = validate_speaker_role_quality(result, max_manual_confirmation_rate=1.0)

        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["quality_gate"]["low_confidence_clinical_role_count"], 0)
        self.assertEqual(report["quality_gate"]["unresolved_assignment_count"], 2)

    def test_fails_when_low_confidence_role_is_displayed_as_doctor_or_patient(self):
        result = ASRResult(
            audio_id="a1",
            engine="funasr",
            text="请问哪里不舒服？",
            conversation_text="[医生] 请问哪里不舒服？",
            segments=[
                ASRSegment(
                    segment_id="seg-1",
                    speaker_id="spk0",
                    role="医生",
                    role_confidence=0.62,
                    role_source="speaker_context_rules",
                    text="请问哪里不舒服？",
                )
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(
                    speaker_id="spk0",
                    role="医生",
                    confidence=0.62,
                    source="speaker_context_rules",
                )
            ],
        )

        report = validate_speaker_role_quality(result)

        self.assertEqual(report["status"], "needs_review")
        self.assertEqual(report["quality_gate"]["low_confidence_clinical_role_count"], 1)
        self.assertIn("低置信度", report["recommendations"][0])

    def test_uses_expected_roles_when_provided(self):
        result = ASRResult(
            audio_id="a1",
            engine="funasr",
            text="请问哪里不舒服？我发热三天。",
            conversation_text="[医生] 请问哪里不舒服？\n[患者] 我发热三天。",
            segments=[
                ASRSegment(speaker_id="spk0", role="医生", role_confidence=0.96, role_source="manual", text="请问哪里不舒服？"),
                ASRSegment(speaker_id="spk1", role="患者", role_confidence=0.96, role_source="manual", text="我发热三天。"),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk0", role="医生", confidence=0.96, source="manual"),
                SpeakerRoleAssignment(speaker_id="spk1", role="患者", confidence=0.96, source="manual"),
            ],
        )

        report = validate_speaker_role_quality(
            result,
            expected_roles={"spk0": "医生", "spk1": "患者"},
        )

        self.assertEqual(report["status"], "passed")
        self.assertEqual(report["summary"]["role_accuracy"], 1.0)

    def test_cli_writes_report(self):
        from scripts.validate_speaker_role_quality import main
        import sys

        result = ASRResult(
            audio_id="a1",
            engine="funasr",
            text="请问哪里不舒服？",
            conversation_text="[说话人 A] 请问哪里不舒服？",
            segments=[ASRSegment(speaker_id="spk0", role=None, text="请问哪里不舒服？")],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk0", role=None, confidence=0.0, requires_confirmation=True)
            ],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            input_path = temp_path / "asr.json"
            output_path = temp_path / "report.json"
            input_path.write_text(json.dumps(result.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
            old_argv = sys.argv
            try:
                sys.argv = [
                    "validate_speaker_role_quality.py",
                    "--asr-result",
                    str(input_path),
                    "--output-json",
                    str(output_path),
                    "--max-manual-confirmation-rate",
                    "1",
                ]
                self.assertEqual(main(), 2)
            finally:
                sys.argv = old_argv

            self.assertTrue(output_path.exists())
            payload = json.loads(output_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "needs_review")


if __name__ == "__main__":
    unittest.main()
