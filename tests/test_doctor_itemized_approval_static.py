from pathlib import Path

from tests.test_doctor_history_restore import run_browser_logic


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
    rendered = run_browser_logic(r'''
const nodes = new Map();
document.getElementById = id => {
  if (!nodes.has(id)) nodes.set(id, {innerHTML:'',textContent:'',className:''});
  return nodes.get(id);
};
appState.currentTaskId=11;
appState.currentTask={id:11,current_record_revision_id:81};
appState.currentEncounter={id:13,current_revision:{id:81,revision_no:2}};
appState.currentExportReadiness={revision_id:81,revision_number:2,approved:false};
appState.currentRecordFields=Object.fromEntries(FIELD_DEFS.map(([key])=>[key,
  {value:null,missing:true,status:'missing',hint:'未记录',source_spans:[]}]));
appState.currentRecordFields.chief_complaint={value:'发热2天',missing:false,status:'complete',source_spans:[]};
renderFields();
const saved=nodes.get('recordFields').innerHTML;
appState.currentTask={id:11,current_record_revision_id:82};
renderFields();
console.log(JSON.stringify({saved,unknown: nodes.get('recordFields').innerHTML}));
''')
    assert "当前版本 #2" in rendered["saved"]
    assert "当前版本 #81" not in rendered["saved"]
    assert "医生分项审核 · 版本 #2" in rendered["saved"]
    assert "医生分项审核 · 版本 #81" not in rendered["saved"]
    assert 'data-open-detail="history:record"' in rendered["saved"]
    assert "历史版本" in rendered["saved"]
    assert "当前版本 待核验" in rendered["unknown"]
    assert "当前版本 #82" not in rendered["unknown"]
    assert "医生分项审核 · 版本 待核验" in rendered["unknown"]
    assert "医生分项审核 · 版本 #82" not in rendered["unknown"]
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
