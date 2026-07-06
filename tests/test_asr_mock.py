import tempfile
import unittest
from pathlib import Path

from app.services.asr import MockASREngine


class MockASRTests(unittest.TestCase):
    def test_mock_asr_returns_snake_bite_transcript(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")

            result = MockASREngine().transcribe("audio-1", audio_path)

        self.assertEqual(result.audio_id, "audio-1")
        self.assertEqual(result.engine, "mock-asr-v0.2")
        self.assertIn("蛇咬伤", result.text)
        self.assertIn("[医生]", result.conversation_text)
        self.assertIn("[患者]", result.conversation_text)
        self.assertGreaterEqual(len(result.segments), 2)
        self.assertEqual(result.medical_keywords["missing"], [])


if __name__ == "__main__":
    unittest.main()
