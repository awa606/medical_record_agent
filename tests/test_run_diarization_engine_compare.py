from __future__ import annotations

from scripts.run_diarization_engine_compare import run_diarization_engine_compare


def test_run_diarization_engine_compare_writes_summary_and_engine_reports(tmp_path):
    audio = tmp_path / "three_speaker_alimeeting_01.wav"
    audio.write_bytes(b"fake")
    rttm = tmp_path / "three_speaker_alimeeting_01.rttm"
    rttm.write_text(
        "SPEAKER three_speaker_alimeeting_01 1 0.000 1.000 <NA> <NA> A <NA> <NA>\n"
        "SPEAKER three_speaker_alimeeting_01 1 1.000 1.000 <NA> <NA> B <NA> <NA>\n"
        "SPEAKER three_speaker_alimeeting_01 1 2.000 1.000 <NA> <NA> C <NA> <NA>\n",
        encoding="utf-8",
    )
    asr_result = tmp_path / "asr.json"
    asr_result.write_text("{}", encoding="utf-8")

    def fake_evaluator(**kwargs):
        if kwargs["engine_name"] == "pyannote":
            return {
                "engine": "pyannote_community_1",
                "status": "skipped",
                "reason": "HF_TOKEN is required",
            }
        return {
            "engine": kwargs["engine_name"],
            "status": "measured",
            "turn_count": 3,
            "speaker_count_error": 0,
            "boundary_f1": 1.0,
            "mixed_utterance_rate": 0.0,
            "role_consistency": 1.0,
            "rtf": 0.2,
            "rss_peak_mb": 512.0,
        }

    summary = run_diarization_engine_compare(
        audio_path=audio,
        reference_rttm=rttm,
        asr_result=asr_result,
        reports_dir=tmp_path / "reports",
        engines=["funasr_campp", "pyannote"],
        evaluator=fake_evaluator,
    )

    assert summary["reference_speaker_count"] == 3
    assert summary["best_candidate"]["engine"] == "funasr_campp"
    assert summary["results"][0]["quality_gate"]["decision"] == "candidate_for_role_mapping"
    assert summary["results"][1]["quality_gate"]["decision"] == "blocked"
    assert (tmp_path / "reports" / "funasr_campp_three_speaker_alimeeting_01.json").exists()
    assert (tmp_path / "reports" / "pyannote_three_speaker_alimeeting_01.json").exists()
    markdown = (tmp_path / "reports" / "diarization_engine_compare_summary.md").read_text(encoding="utf-8")
    assert "AliMeeting" in markdown
    assert "not medical consultation accuracy evidence" in markdown


def test_run_diarization_engine_compare_handles_no_measured_engine(tmp_path):
    audio = tmp_path / "three_speaker_alimeeting_01.wav"
    audio.write_bytes(b"fake")
    rttm = tmp_path / "three_speaker_alimeeting_01.rttm"
    rttm.write_text(
        "SPEAKER three_speaker_alimeeting_01 1 0.000 1.000 <NA> <NA> A <NA> <NA>\n",
        encoding="utf-8",
    )

    def fake_evaluator(**kwargs):
        return {"engine": kwargs["engine_name"], "status": "skipped", "reason": "not configured"}

    summary = run_diarization_engine_compare(
        audio_path=audio,
        reference_rttm=rttm,
        asr_result=None,
        reports_dir=tmp_path / "reports",
        engines=["three_d_speaker"],
        evaluator=fake_evaluator,
    )

    assert summary["best_candidate"] is None
    assert summary["results"][0]["quality_gate"]["decision"] == "blocked"
    markdown = (tmp_path / "reports" / "diarization_engine_compare_summary.md").read_text(encoding="utf-8")
    assert "No measured engine passed the quality gate" in markdown


def test_run_diarization_engine_compare_rejects_high_mixed_rate(tmp_path):
    audio = tmp_path / "three_speaker_alimeeting_01.wav"
    audio.write_bytes(b"fake")
    rttm = tmp_path / "three_speaker_alimeeting_01.rttm"
    rttm.write_text(
        "SPEAKER three_speaker_alimeeting_01 1 0.000 1.000 <NA> <NA> A <NA> <NA>\n"
        "SPEAKER three_speaker_alimeeting_01 1 1.000 1.000 <NA> <NA> B <NA> <NA>\n",
        encoding="utf-8",
    )

    def fake_evaluator(**kwargs):
        return {
            "engine": kwargs["engine_name"],
            "status": "measured",
            "turn_count": 2,
            "speaker_count_error": 0,
            "boundary_f1": 1.0,
            "mixed_utterance_rate": 0.8,
            "role_consistency": 0.9,
        }

    summary = run_diarization_engine_compare(
        audio_path=audio,
        reference_rttm=rttm,
        asr_result=None,
        reports_dir=tmp_path / "reports",
        engines=["funasr_campp"],
        evaluator=fake_evaluator,
    )

    assert summary["best_candidate"] is None
    assert summary["results"][0]["quality_gate"]["decision"] == "reject_for_role_mapping"
    assert "mixed_utterance_rate" in summary["results"][0]["quality_gate"]["reason"]
