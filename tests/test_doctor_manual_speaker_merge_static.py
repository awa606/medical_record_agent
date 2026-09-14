from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_speaker_tools_are_debug_only_recovery_controls() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "data-speaker-merge-source" in script
    assert "data-undo-speaker-merge" in script
    assert "/speakers/merge" in script
    assert "undoLastSpeakerMerge" in script
    assert 'appState.currentAsrResult && appState.roleReviewDirty && appState.viewMode === "debug"' in script
    assert '"open-role-review"' not in script
