from __future__ import annotations

from scripts.bootstrap_diarization_eval import collect_bootstrap_status, render_markdown


def test_collect_bootstrap_status_reports_missing_pyannote_token_and_3d_speaker():
    payload = collect_bootstrap_status(
        env={},
        module_checker=lambda name: False,
        module_probe=lambda name: {"import_ok": False, "reason": "missing"},
        path_exists=lambda value: False,
    )

    assert payload["pyannote"]["status"] == "blocked"
    assert "pyannote.audio is not importable" in payload["pyannote"]["reason"]
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
        module_probe=lambda name: {"import_ok": True, "version": "test"},
        path_exists=lambda value: True,
    )

    assert payload["pyannote"]["status"] == "ready"
    assert payload["three_d_speaker"]["status"] == "ready"
    markdown = render_markdown(payload)
    assert "Diarization Engine Bootstrap Report" in markdown
    assert "AliMeeting public meeting samples" in markdown
