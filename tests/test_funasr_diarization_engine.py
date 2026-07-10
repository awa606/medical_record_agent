import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.asr.funasr_engine import FunASREngine


class FakeDiarizationModel:
    def generate(self, **_kwargs):
        return [
            {
                "text": "请问哪里不舒服？我发热三天。",
                "sentence_info": [
                    {"spk": 0, "sentence": "请问哪里不舒服？", "start": 480, "end": 1200},
                    {"spk": 1, "sentence": "我发热三天。", "start": 1200, "end": 2400},
                ],
            }
        ]


class FunASRDiarizationEngineTests(unittest.TestCase):
    def test_campp_is_enabled_in_funasr_model_pipeline(self):
        captured = {}
        fake_module = types.ModuleType("funasr")

        def auto_model(**kwargs):
            captured.update(kwargs)
            return FakeDiarizationModel()

        fake_module.AutoModel = auto_model
        with patch.dict("sys.modules", {"funasr": fake_module}):
            FunASREngine(
                hotword_path=None,
                enable_speaker_diarization=True,
            )

        self.assertEqual(captured["vad_model"], "fsmn-vad")
        self.assertEqual(captured["punc_model"], "ct-punc")
        self.assertEqual(captured["spk_model"], "cam++")

    def test_campp_sentence_output_maps_speaker_ids_and_timestamps(self):
        engine = FunASREngine(
            model_instance=FakeDiarizationModel(),
            hotword_path=None,
            enable_speaker_diarization=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "sample.wav"
            audio_path.write_bytes(b"RIFF")
            result = engine.transcribe("audio-cam", audio_path)

        self.assertEqual([segment.speaker_id for segment in result.segments], ["spk0", "spk1"])
        self.assertEqual(result.segments[0].segment_id, "audio-cam-cal-0001")
        self.assertEqual(result.segments[0].start_time, 0.48)
        self.assertEqual(result.segments[1].start_time, 1.2)
        self.assertEqual(result.duration, 2.4)


if __name__ == "__main__":
    unittest.main()
