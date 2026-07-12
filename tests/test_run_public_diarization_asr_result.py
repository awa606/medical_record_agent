from pathlib import Path

from app.schemas.asr import ASRResult, ASRSegment, DiarizationTurn
from scripts.run_public_diarization_asr_result import (
    ENHANCED_RESULT_NAME,
    RAW_RESULT_NAME,
    run_public_diarization_asr_result,
)


class _FakeEngine:
    name = "fake_funasr"

    def transcribe(self, audio_id: str, audio_path: Path) -> ASRResult:
        return ASRResult(
            audio_id=audio_id,
            engine=self.name,
            text="doctor asks patient answers",
            conversation_text="",
            duration=4.0,
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
                DiarizationTurn(start_time=0.0, end_time=2.0, speaker_id="spk0", confidence=0.9),
                DiarizationTurn(start_time=2.0, end_time=4.0, speaker_id="spk1", confidence=0.9),
            ],
        )


def test_run_public_diarization_asr_result_writes_raw_and_enhanced(tmp_path):
    audio = tmp_path / "three_speaker_alimeeting_01.wav"
    audio.write_bytes(b"fake")
    reports = tmp_path / "reports"

    payload = run_public_diarization_asr_result(
        audio_path=audio,
        report_dir=reports,
        engine_name="fake",
        engine_factory=lambda _name: _FakeEngine(),
    )

    assert payload["status"] == "measured"
    assert (reports / RAW_RESULT_NAME).exists()
    assert (reports / ENHANCED_RESULT_NAME).exists()
    enhanced = ASRResult.model_validate_json((reports / ENHANCED_RESULT_NAME).read_text(encoding="utf-8"))
    assert len(enhanced.segments) >= 2
    assert enhanced.segments[0].speaker_id == "spk0"
    assert enhanced.segments[1].speaker_id == "spk1"


def test_run_public_diarization_asr_result_records_missing_audio(tmp_path):
    payload = run_public_diarization_asr_result(
        audio_path=tmp_path / "missing.wav",
        report_dir=tmp_path / "reports",
        engine_name="fake",
        engine_factory=lambda _name: _FakeEngine(),
    )

    assert payload["status"] == "skipped"
    assert "audio file not found" in payload["error"]
