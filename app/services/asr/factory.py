from __future__ import annotations

import os
from app.services.asr.base import ASREngine
from app.services.asr.mock_engine import MockASREngine


def create_asr_engine(engine_name: str = "mock") -> ASREngine:
    normalized_name = (engine_name or "mock").strip().lower()
    if os.getenv("RECORD_PROVIDER_MODE") == "edge" and normalized_name in {"mock", "online"}:
        raise RuntimeError("Edge mode rejects mock or online ASR")
    if normalized_name == "mock":
        return MockASREngine()
    if normalized_name == "funasr":
        if os.getenv('RECORD_PROVIDER_MODE') in {'edge', 'live'}:
            # Use the same instance loaded by session reconciliation/prewarm.
            from app.api.asr_sessions import _create_funasr_reconciliation_engine
            return _create_funasr_reconciliation_engine()
        from app.services.asr.funasr_engine import FunASREngine

        return FunASREngine(enable_speaker_diarization=os.getenv('RECORD_PROVIDER_MODE') == 'edge',
                            device=os.getenv('FUNASR_DEVICE', 'cpu'))
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
