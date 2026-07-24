from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_static(name: str) -> str:
    return (ROOT / "static" / name).read_text(encoding="utf-8")


def function_body(script: str, name: str) -> str:
    marker = f"function {name}"
    start = script.index(marker)
    next_function = script.find("\nfunction ", start + len(marker))
    if next_function == -1:
        next_function = len(script)
    return script[start:next_function]


def test_doctor_approval_panel_renders_revision_and_itemized_actions() -> None:
    js = read_static("doctor.js")
    css = read_static("doctor-ui-v2.css")

    assert "function renderApprovalChecklist" in js
    assert "当前版本 #" in js
    assert "data-approval-confirm-regular" in js
    assert "data-approval-missing-key" in js
    assert "data-approval-diagnosis-index" in js
    assert "data-approval-risk-key" in js
    assert "缺失项处理" in js
    assert "候选诊断处理" in js
    assert "高风险与冲突确认" in js
    assert ".approval-checklist" in css
    assert ".approval-item.high-risk" in css


def test_doctor_approval_submit_uses_explicit_payload_not_empty_post() -> None:
    js = read_static("doctor.js")
    confirm_body = function_body(js, "confirmFields")
    payload_body = function_body(js, "buildTaskApprovalPayload")

    assert "const payload = await buildTaskApprovalPayload()" in confirm_body
    assert 'headers: { "Content-Type": "application/json" }' in confirm_body
    assert "body: JSON.stringify(payload)" in confirm_body
    assert 'approve`, { method: "POST" })' not in confirm_body
    assert "revision_id" in payload_body
    assert "content_hash" in payload_body
    assert "confirm_all_regular_fields" in payload_body
    assert "high_risk_conflicts" in payload_body
    assert 'item.key.startsWith("field:")' in payload_body
    assert 'action: "confirm_content"' in payload_body


def test_doctor_approval_state_resets_when_revision_changes() -> None:
    js = read_static("doctor.js")
    refresh_body = function_body(js, "refreshTask")
    reset_body = function_body(js, "resetTaskState")

    assert "function syncApprovalReviewStateWithRevision" in js
    assert "function clearApprovalReviewSelections" in js
    assert "syncApprovalReviewStateWithRevision(null)" in refresh_body
    assert "clearApprovalReviewSelections()" in reset_body
    assert "appState.currentExportReadiness = null" in refresh_body
