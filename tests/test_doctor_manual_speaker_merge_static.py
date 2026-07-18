from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_role_options_include_all_manual_recovery_choices() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert '["医生", "医生"]' in script
    assert '["患者", "患者"]' in script
    assert '["陪同人员", "陪同人员"]' in script
    assert '["其他", "其他"]' in script
    assert '["待确认", "暂不确定"]' in script


def test_doctor_identity_review_has_manual_speaker_merge_controls() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "data-speaker-merge-source" in script
    assert "data-undo-speaker-merge" in script
    assert "/speakers/merge" in script
    assert "undoLastSpeakerMerge" in script
