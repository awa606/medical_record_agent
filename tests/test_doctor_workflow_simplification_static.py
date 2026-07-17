from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_script() -> str:
    return (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")


def read_html() -> str:
    return (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")


def test_workflow_uses_five_steps_without_role_review_step() -> None:
    script = read_script()

    assert "1.开始问诊" in script
    assert "2.智能转写" in script
    assert "3.生成病历" in script
    assert "4.医生审核" in script
    assert "5.导出" in script
    assert "3.角色校正" not in script
    assert 'TRANSCRIBED: "GENERATE_RECORD"' in script


def test_role_quality_passed_auto_continues_and_gate_errors_surface() -> None:
    script = read_script()

    assert "function roleQualityPassed" in script
    assert 'roleQualityStatus(asr) === "passed" && speakerRolesComplete(asr)' in script
    assert "if (roleQualityPassed(asr)) return false" in script
    assert "function applyRoleQualityGateError" in script
    assert "error?.detail?.role_quality" in script
    assert "role_quality: roleQuality" in script
    assert "startRecordGenerationFromAudio(transcribed.audio_id)" in script
    assert "await startRecordGenerationFromAudio(appState.currentAudioId)" in script


def test_identity_review_is_exceptional_and_only_targets_uncertain_speakers() -> None:
    script = read_script()

    assert '["needs_review", "blocked"].includes(roleQualityStatus(asr))' in script
    assert "pendingSpeakerAssignments()" in script
    assert "quality.low_confidence_clinical_roles" in script
    assert "quality.unmapped_speakers" in script
    assert 'key: rolePending ? "open-role-review" : "save-role-review"' in script
    assert 'renderTranscriptDetailContent("role-review")' in script
    assert "需要确认的说话人" in script
    assert "更正转写（可选）" in script
    assert "全局角色映射" not in script
    assert "保存角色校正" not in script


def test_diagnosis_reference_shows_two_candidates_and_hides_rule_ids_normally() -> None:
    script = read_script()

    assert "鉴别诊断参考" in script
    assert "listPreview(diagnoses, 2)" in script
    assert "依据：" in script
    assert "关注：" in script
    assert "查看完整依据" in script
    assert "仅供鉴别诊断参考，需医生判断，不能作为已确诊结论。" in script
    assert "规则匹配度" in script
    assert "规则置信度" not in script
    assert 'appState.viewMode === "debug"' in script
    assert "diagnosis.rule_id" in script


def test_doctor_review_terms_are_user_facing() -> None:
    visible = read_html() + read_script()

    for phrase in [
        "完成病历审核",
        "保存修改",
        "请审核病历内容",
        "病历审核已完成",
        "请核对病历内容及鉴别诊断参考",
        "完成医生审核后方可导出",
    ]:
        assert phrase in visible

    for phrase in [
        "确认字段",
        "正在确认字段",
        "字段已确认",
        "请审核病历字段",
        "字段已生成",
        "保存草稿",
        "确认后才能导出",
    ]:
        assert phrase not in visible
