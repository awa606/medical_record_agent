from __future__ import annotations

from scripts.bootstrap_diarization_eval import collect_bootstrap_status, render_markdown


def test_collect_bootstrap_status_reports_missing_pyannote_token_and_3d_speaker():
    payload = collect_bootstrap_status(
        env={},
        module_checker=lambda name: False,
        path_exists=lambda value: False,
    )

    assert payload["pyannote"]["status"] == "blocked"
    assert "pyannote.audio is not installed" in payload["pyannote"]["reason"]
    assert "HF_TOKEN is not configured" in payload["pyannote"]["reason"]
    assert payload["three_d_speaker"]["status"] == "blocked"
    assert "THREED_SPEAKER_PYTHON" in payload["three_d_speaker"]["reason"]


def test_collect_bootstrap_status_can_report_ready_engines():
    payload = collect_bootstrap_status(
        env={
            "HF_TOKEN": "token",
            "THREED_SPEAKER_PYTHON": "python.exe",
            "THREED_SPEAKER_SCRIPT": "diarize_wrapper.py",
        },
        module_checker=lambda name: name in {"pyannote.audio", "pyannote.metrics"},
        path_exists=lambda value: True,
    )

    assert payload["pyannote"]["status"] == "ready"
    assert payload["three_d_speaker"]["status"] == "ready"
    markdown = render_markdown(payload)
    assert "v0.8.19 说话人分离引擎环境准备报告" in markdown
    assert "AliMeeting 公开会议样本只用于多说话人分离评测" in markdown
