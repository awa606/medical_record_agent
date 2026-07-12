from __future__ import annotations

import json

from app.schemas.asr import ASRResult, ASRSegment
from scripts.apply_diarization_turns_to_asr_result import apply_diarization_turns_to_asr_result


def test_apply_diarization_turns_splits_mixed_asr_segment(tmp_path):
    asr_result = ASRResult(
        audio_id="three_speaker_alimeeting_01",
        engine="funasr",
        text="speaker one speaker two",
        conversation_text="",
        segments=[
            ASRSegment(
                segment_id="mixed-1",
                speaker="spk0",
                speaker_id="spk0",
                text="speaker one speaker two",
                start_time=0.0,
                end_time=4.0,
            )
        ],
    )
    asr_path = tmp_path / "asr_result.json"
    asr_path.write_text(json.dumps(asr_result.model_dump(mode="json")), encoding="utf-8")
    turns_path = tmp_path / "turns.json"
    turns_path.write_text(
        json.dumps(
            {
                "engine": "pyannote_community_1",
                "status": "measured",
                "hypothesis_turns": [
                    {"start_time": 0.0, "end_time": 2.0, "speaker_id": "SPEAKER_00"},
                    {"start_time": 2.0, "end_time": 4.0, "speaker_id": "SPEAKER_01"},
                ],
            }
        ),
        encoding="utf-8",
    )
    rttm = tmp_path / "reference.rttm"
    rttm.write_text(
        "SPEAKER sample 1 0.000 2.000 <NA> <NA> A <NA> <NA>\n"
        "SPEAKER sample 1 2.000 2.000 <NA> <NA> B <NA> <NA>\n",
        encoding="utf-8",
    )

    payload = apply_diarization_turns_to_asr_result(
        asr_result_path=asr_path,
        turns_report_path=turns_path,
        reference_rttm=rttm,
        reports_dir=tmp_path / "reports",
    )

    assert payload["status"] == "measured"
    assert payload["segment_count_before"] == 1
    assert payload["segment_count_after"] >= 2
    assert payload["after_metrics"]["mixed_utterance_rate"] == 0.0
    aligned = json.loads((tmp_path / "reports" / "three_speaker_alimeeting_01_aligned_asr_result.json").read_text(encoding="utf-8"))
    assert len(aligned["segments"]) >= 2


def test_apply_diarization_turns_skips_report_without_turns(tmp_path):
    asr_path = tmp_path / "asr_result.json"
    asr_path.write_text(
        ASRResult(audio_id="a", engine="funasr", text="", conversation_text="").model_dump_json(),
        encoding="utf-8",
    )
    turns_path = tmp_path / "turns.json"
    turns_path.write_text(
        json.dumps({"engine": "pyannote", "status": "skipped", "reason": "HF_TOKEN is required"}),
        encoding="utf-8",
    )

    payload = apply_diarization_turns_to_asr_result(
        asr_result_path=asr_path,
        turns_report_path=turns_path,
        reference_rttm=None,
        reports_dir=tmp_path / "reports",
    )

    assert payload["status"] == "skipped"
    assert "no hypothesis_turns" in payload["reason"]
    assert (tmp_path / "reports" / "alignment_summary.md").exists()
