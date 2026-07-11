from __future__ import annotations

import json
import os
import unittest
from unittest.mock import patch

from app.schemas.asr import ASRResult, ASRSegment, SpeakerRoleAssignment
from app.services.asr.speaker_role_classifier import resolve_speaker_roles


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload, ensure_ascii=False).encode("utf-8")


class SpeakerRoleClassifierTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("SPEAKER_ROLE_PROVIDER", None)

    def test_ollama_classifies_whole_unresolved_speaker(self):
        result = ASRResult(
            audio_id="audio-1",
            engine="funasr",
            text="",
            conversation_text="",
            segments=[
                ASRSegment(speaker="spk0", speaker_id="spk0", role="医生", text="请问哪里不舒服？"),
                ASRSegment(speaker="spk1", speaker_id="spk1", role="其他", text="我发热三天。"),
            ],
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk0", role="医生", confidence=0.9, source="rules"),
                SpeakerRoleAssignment(
                    speaker_id="spk1",
                    role="其他",
                    confidence=0.55,
                    source="fallback",
                    requires_confirmation=True,
                ),
            ],
        )
        os.environ["SPEAKER_ROLE_PROVIDER"] = "ollama"
        content = {
            "assignments": [
                {"speaker_id": "spk1", "role": "患者", "confidence": 0.91, "reason": "持续描述自身症状"}
            ]
        }
        with patch(
            "app.services.asr.speaker_role_classifier.request.urlopen",
            return_value=FakeResponse({"message": {"content": json.dumps(content, ensure_ascii=False)}}),
        ):
            updated = resolve_speaker_roles(result, audio_path="unused.wav")

        assignment = next(item for item in updated.speaker_assignments if item.speaker_id == "spk1")
        self.assertEqual(assignment.role, "患者")
        self.assertEqual(assignment.source, "ollama_qwen3_speaker_context")
        self.assertFalse(assignment.requires_confirmation)
        self.assertEqual(updated.segments[1].role, "患者")

    def test_rules_mode_does_not_call_ollama(self):
        os.environ["SPEAKER_ROLE_PROVIDER"] = "rules"
        result = ASRResult(
            audio_id="audio-1",
            engine="funasr",
            text="",
            conversation_text="",
            speaker_assignments=[
                SpeakerRoleAssignment(speaker_id="spk0", requires_confirmation=True)
            ],
        )
        with patch("app.services.asr.speaker_role_classifier.request.urlopen") as urlopen:
            updated = resolve_speaker_roles(result, audio_path="unused.wav")
        urlopen.assert_not_called()
        self.assertTrue(updated.speaker_assignments[0].requires_confirmation)


if __name__ == "__main__":
    unittest.main()
