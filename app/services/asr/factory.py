from __future__ import annotations

from app.services.asr.base import ASREngine
from app.services.asr.mock_engine import MockASREngine


def create_asr_engine(engine_name: str = "mock") -> ASREngine:
    normalized_name = (engine_name or "mock").strip().lower()
    if normalized_name == "mock":
        return MockASREngine()
    if normalized_name == "funasr":
        from app.services.asr.funasr_engine import FunASREngine

        return FunASREngine()
    if normalized_name == "sensevoice":
        from app.services.asr.sensevoice_engine import SenseVoiceASREngine

        return SenseVoiceASREngine()
    if normalized_name == "whisper":
        from app.services.asr.whisper_engine import WhisperASREngine

        return WhisperASREngine()
    if normalized_name == "qwen3":
        from app.services.asr.qwen3_engine import Qwen3ASREngine

        return Qwen3ASREngine()
    if normalized_name == "online":
        from app.services.asr.online_engine import OnlineASREngine

        return OnlineASREngine()
    raise ValueError(
        "Unsupported ASR engine: "
        f"{engine_name}. Expected 'mock', 'funasr', 'sensevoice', 'whisper', 'qwen3', or 'online'."
    )
