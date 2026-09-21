from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_manual_speaker_merge_stays_debug_only_while_identity_review_is_conditional() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "data-speaker-merge-source" in script
    assert "data-undo-speaker-merge" in script
    assert "/speakers/merge" in script
    assert "undoLastSpeakerMerge" in script
    assert 'appState.currentAsrResult && appState.roleReviewDirty && appState.viewMode === "debug"' in script
    assert 'key: "open-role-review", label: "确认说话人身份"' in script
    assert 'appState.currentAsrResult && roleReviewRequired() && appState.viewMode !== "debug"' in script
