import builtins
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from app.services.asr import (
    MockASREngine,
    OnlineASREngine,
    Qwen3ASREngine,
    SenseVoiceASREngine,
    WhisperASREngine,
    create_asr_engine,
    normalize_online_asr_response,
)
from app.services.asr.qwen3_engine import DEPENDENCY_ERROR, ROLE_REVIEW_WARNING
from app.services.asr.sensevoice_engine import DEPENDENCY_ERROR as SENSEVOICE_DEPENDENCY_ERROR
from app.services.asr.whisper_engine import DEPENDENCY_ERROR as WHISPER_DEPENDENCY_ERROR


class ASRFactoryTests(unittest.TestCase):
    def test_create_mock_engine(self):
        engine = create_asr_engine("mock")

        self.assertIsInstance(engine, MockASREngine)
        self.assertEqual(engine.name, "mock-asr-v0.2")

    def test_create_default_engine_is_mock(self):
        engine = create_asr_engine()

        self.assertIsInstance(engine, MockASREngine)

    def test_unknown_engine_raises_clear_error(self):
        with self.assertRaises(ValueError) as context:
            create_asr_engine("unknown")

        self.assertIn("Unsupported ASR engine", str(context.exception))
        self.assertIn("mock", str(context.exception))
        self.assertIn("funasr", str(context.exception))
        self.assertIn("sensevoice", str(context.exception))
        self.assertIn("whisper", str(context.exception))
        self.assertIn("qwen3", str(context.exception))
        self.assertIn("online", str(context.exception))

    def test_qwen3_engine_requires_optional_dependencies(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "qwen_asr":
                raise ImportError("missing qwen_asr")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError) as context:
                create_asr_engine("qwen3")

        self.assertEqual(str(context.exception), DEPENDENCY_ERROR)

    def test_create_qwen3_engine_with_fake_dependency(self):
        module = types.ModuleType("qwen_asr")

        class FakeQwen3ASRModel:
            @classmethod
            def from_pretrained(cls, *_args, **_kwargs):
                return cls()

            def transcribe(self, _audio_path):
                return {"text": "fake qwen3 transcript"}

        module.Qwen3ASRModel = FakeQwen3ASRModel
        with patch.dict(sys.modules, {"qwen_asr": module}):
            engine = create_asr_engine("qwen3")

        self.assertIsInstance(engine, Qwen3ASREngine)
        self.assertEqual(engine.name, "qwen3-asr-0.6b")

    def test_qwen3_engine_response_maps_to_asr_result(self):
        class FakeModel:
            def transcribe(self, _audio_path):
                return {
                    "text": "patient has fever for three days",
                    "segments": [
                        {
                            "speaker": "spk0",
                            "text": "patient has fever",
                            "start": 0.0,
                            "end": 1.4,
                            "confidence": 0.9,
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "fever_01.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")
            result = Qwen3ASREngine(
                model_instance=FakeModel(),
                hotword_path=None,
            ).transcribe("audio-qwen3", audio_path)

        self.assertEqual(result.audio_id, "audio-qwen3")
        self.assertEqual(result.engine, "qwen3-asr-0.6b")
        self.assertEqual(result.text, "patient has fever for three days")
        self.assertEqual(result.conversation_text, "[待校正] patient has fever for three days")
        self.assertEqual(result.segments[0].speaker, "spk0")
        self.assertIsNone(result.segments[0].role)
        self.assertEqual(result.duration, 1.4)
        self.assertEqual(result.medical_keywords["missing"], [])
        self.assertEqual(result.warnings, [ROLE_REVIEW_WARNING])

    def test_sensevoice_engine_requires_optional_dependencies(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "funasr":
                raise ImportError("missing funasr")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fake_import):
            with self.assertRaises(RuntimeError) as context:
                create_asr_engine("sensevoice")

        self.assertEqual(str(context.exception), SENSEVOICE_DEPENDENCY_ERROR)

    def test_sensevoice_engine_response_maps_to_asr_result(self):
        class FakeModel:
            def generate(self, **_kwargs):
                return [
                    {
                        "sentence_info": [
                            {
                                "spk": "speaker-0",
                                "sentence": "患者发热三天",
                                "start": 0,
                                "end": 1200,
                            }
                        ]
                    }
                ]

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "fever_01.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")
            result = SenseVoiceASREngine(
                model_instance=FakeModel(),
                hotword_path=None,
                postprocess=lambda value: value,
            ).transcribe("audio-sensevoice", audio_path)

        self.assertEqual(result.audio_id, "audio-sensevoice")
        self.assertEqual(result.engine, "sensevoice-small")
        self.assertEqual(result.text, "患者发热三天")
        self.assertEqual(result.segments[0].speaker, "speaker-0")
        self.assertEqual(result.segments[0].end_time, 1.2)
        self.assertTrue(result.segments[0].needs_review)

    def test_whisper_engine_requires_optional_dependencies(self):
        original_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "whisper":
                raise ImportError("missing whisper")
            return original_import(name, *args, **kwargs)

        with patch("app.services.asr.whisper_engine.ensure_ffmpeg_on_path", return_value=Path("ffmpeg.exe")):
            with patch("builtins.__import__", side_effect=fake_import):
                with self.assertRaises(RuntimeError) as context:
                    create_asr_engine("whisper")

        self.assertEqual(str(context.exception), WHISPER_DEPENDENCY_ERROR)

    def test_whisper_engine_response_maps_to_asr_result(self):
        class FakeModel:
            def transcribe(self, *_args, **_kwargs):
                return {
                    "text": "患者发热三天",
                    "segments": [
                        {
                            "text": "患者发热三天",
                            "start": 0.0,
                            "end": 1.5,
                        }
                    ],
                }

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "fever_01.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")
            result = WhisperASREngine(
                model_instance=FakeModel(),
                hotword_path=None,
            ).transcribe("audio-whisper", audio_path)

        self.assertEqual(result.audio_id, "audio-whisper")
        self.assertEqual(result.engine, "whisper-base")
        self.assertEqual(result.text, "患者发热三天")
        self.assertEqual(result.segments[0].speaker, "whisper")
        self.assertEqual(result.duration, 1.5)

    def test_whisper_engine_auto_language_passes_none_to_model(self):
        class FakeModel:
            language_arg = "not-called"

            def transcribe(self, *_args, **kwargs):
                self.language_arg = kwargs.get("language")
                return {"text": "hello", "segments": [{"text": "hello", "start": 0.0, "end": 1.0}]}

        model = FakeModel()
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "public.wav"
            audio_path.write_bytes(b"RIFF....WAVEfmt ")
            WhisperASREngine(
                model_instance=model,
                hotword_path=None,
                language="auto",
            ).transcribe("audio-whisper-auto", audio_path)

        self.assertIsNone(model.language_arg)

    def test_online_engine_requires_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeError) as context:
                create_asr_engine("online")

        self.assertIn("ONLINE_ASR_API_URL", str(context.exception))
        self.assertIn("ONLINE_ASR_API_KEY", str(context.exception))
        self.assertIn("当前选择的是在线 ASR，不是在线 LLM", str(context.exception))
        self.assertIn("如果要测试 DeepSeek", str(context.exception))
        self.assertIn("ASR 选择 FunASR 后上传生成病历", str(context.exception))

    def test_create_online_engine_from_environment(self):
        with patch.dict(
            "os.environ",
            {
                "ONLINE_ASR_API_URL": "https://asr.example.test/transcribe",
                "ONLINE_ASR_API_KEY": "test-key-from-env",
            },
            clear=True,
        ):
            engine = create_asr_engine("online")

        self.assertIsInstance(engine, OnlineASREngine)
        self.assertEqual(engine.name, "online")

    def test_online_engine_response_maps_to_asr_result(self):
        engine = OnlineASREngine(
            api_url="https://asr.example.test/transcribe",
            api_key="test-key-from-env",
        )

        result = engine._result_from_response(
            "audio-1",
            {
                "text": "发热三天",
                "conversation_text": "[待校正] 发热三天",
                "segments": [{"speaker": "spk0", "text": "发热三天"}],
                "medical_keywords": {
                    "expected": ["发热"],
                    "recognized": ["发热"],
                    "missing": [],
                },
            },
        )

        self.assertEqual(result.audio_id, "audio-1")
        self.assertEqual(result.engine, "online")
        self.assertEqual(result.text, "发热三天")
        self.assertEqual(result.segments[0].speaker, "spk0")
        self.assertEqual(result.medical_keywords["recognized"], ["发热"])

    def test_normalize_online_asr_response_maps_nested_provider_json(self):
        result = normalize_online_asr_response(
            {
                "provider": "vendor-asr",
                "data": {
                    "transcript": "patient has fever for three days",
                    "utterances": [
                        {
                            "spk": "speaker-0",
                            "role": "patient",
                            "utterance": "patient has fever",
                            "start": 0.0,
                            "end": 1.2,
                            "conf": 0.91,
                        }
                    ],
                    "keywords": ["fever"],
                    "audio_duration": 1.5,
                },
            },
            audio_id="audio-2",
        )

        self.assertEqual(result.audio_id, "audio-2")
        self.assertEqual(result.engine, "vendor-asr")
        self.assertEqual(result.text, "patient has fever for three days")
        self.assertEqual(result.segments[0].speaker, "speaker-0")
        self.assertEqual(result.segments[0].role, "patient")
        self.assertEqual(result.segments[0].confidence, 0.91)
        self.assertEqual(result.duration, 1.5)
        self.assertEqual(result.medical_keywords["recognized"], ["fever"])

    def test_mock_engine_creation_still_does_not_require_online_environment(self):
        with patch.dict("os.environ", {}, clear=True):
            engine = create_asr_engine("mock")

        self.assertIsInstance(engine, MockASREngine)


if __name__ == "__main__":
    unittest.main()
