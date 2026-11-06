"""Exercise the real logout and edit/capture guard in Node, without HTTP/UI."""

from pathlib import Path
import json

import pytest

from tests.test_doctor_history_restore import run_browser_logic


ROOT = Path(__file__).resolve().parents[1]


def run_exit_logic(state: dict, *, reject_logout: bool = False, action: str = "logout") -> dict:
    script = (ROOT / "static/doctor.js").read_text(encoding="utf-8")
    # The shared harness deliberately stubs this guard. Restore its actual
    # implementation so these cases cannot pass against a permissive stub.
    start = script.index("function encounterSwitchBlocked(")
    stop = script.index("\nfunction detailButton(", start)
    real_guard = script[start:stop].strip()
    body = "encounterSwitchBlocked = " + real_guard + ";\n" + r'''
const calls = [], toasts = [];
let resets = 0, readInvalidations = 0, renders = 0;
Object.assign(appState, {
  authUser: {id: 1}, authStatus: 'authenticated', authMessage: '',
  busy: false, recordEditMode: false, recordEditDirty: false,
  roleReviewDirty: false, recordEditConflict: null, recordEditRecovery: null,
  browserRecordingStatus: 'idle', browserRecordingSubmitted: false,
  currentTaskId: 7,
  currentRecordFields: {chief_complaint: {value: 'synthetic local edit'}},
}, STATE);
const protectedState = () => JSON.stringify({
  user: appState.authUser, auth: appState.authStatus,
  fields: appState.currentRecordFields, dirty: appState.recordEditDirty,
  roleDirty: appState.roleReviewDirty, conflict: appState.recordEditConflict,
  recovery: appState.recordEditRecovery,
  capture: appState.browserRecordingStatus, submitted: appState.browserRecordingSubmitted,
});
const before = protectedState();
showToast = message => toasts.push(message);
beginEncounterRead = () => { readInvalidations++; };
resetTaskState = () => {
  resets++;
  appState.currentRecordFields = null;
  appState.recordEditDirty = false;
  appState.recordEditConflict = null;
  appState.recordEditRecovery = null;
};
renderAll = () => { renders++; };
globalThis.fetch = async (path, options) => {
  calls.push({path, method: options?.method});
  if (REJECT_LOGOUT) throw new Error('synthetic network failure');
  return {ok: true};
};
let error = null, blocked = null;
try {
  if (ACTION === 'logout') await logout();
  else blocked = encounterSwitchBlocked();
} catch (failure) { error = failure.message; }
console.log(JSON.stringify({calls, toasts, resets, readInvalidations, renders,
  unchanged: protectedState() === before, user: appState.authUser,
  authStatus: appState.authStatus, authMessage: appState.authMessage, error, blocked}));
'''
    body = body.replace("STATE", json.dumps(state, ensure_ascii=False))
    body = body.replace("REJECT_LOGOUT", "true" if reject_logout else "false")
    body = body.replace("ACTION", json.dumps(action))
    return run_browser_logic(body)


@pytest.mark.parametrize("state", [
    {"recordEditMode": True, "recordEditDirty": True},
    {"roleReviewDirty": True},
    {"recordEditConflict": {"error_code": "stale_record_revision"}},
    {"recordEditConflict": {"error_code": "saved_revision_refresh_failed"}},
    *[{"browserRecordingStatus": status} for status in
      ("requesting", "recording", "paused", "finalizing", "uploading")],
    {"browserRecordingStatus": "recorded", "browserRecordingSubmitted": False},
])
def test_logout_keeps_pending_edits_conflicts_and_unsubmitted_capture(state):
    result = run_exit_logic(state)
    assert result["calls"] == []
    assert result["resets"] == result["readInvalidations"] == result["renders"] == 0
    assert result["unchanged"]
    assert result["toasts"] and "退出登录" in result["toasts"][0]
    if state.get("recordEditConflict", {}).get("error_code") == "saved_revision_refresh_failed":
        assert "加载最新版本" in result["toasts"][0]
        assert "保存或取消" not in result["toasts"][0]
    assert result["error"] is None


def test_busy_logout_does_not_invalidate_an_inflight_operation():
    result = run_exit_logic({"busy": True})
    assert result["calls"] == []
    assert result["resets"] == result["readInvalidations"] == result["renders"] == 0
    assert result["unchanged"]
    assert "退出登录" in result["toasts"][0]


@pytest.mark.parametrize("state", [
    {},
    {"recordEditMode": True},
    {"browserRecordingStatus": "recorded", "browserRecordingSubmitted": True},
])
def test_clean_logout_retains_the_original_request_and_cleanup(state):
    result = run_exit_logic(state)
    assert result["calls"] == [{"path": "/api/auth/logout", "method": "POST"}]
    assert result["resets"] == result["readInvalidations"] == result["renders"] == 1
    assert result["user"] is None and result["authStatus"] == "required"
    assert result["authMessage"] == "已退出登录。"
    assert result["error"] is None


def test_clean_logout_network_failure_keeps_existing_finally_cleanup_semantics():
    result = run_exit_logic({}, reject_logout=True)
    assert result["calls"] == [{"path": "/api/auth/logout", "method": "POST"}]
    assert result["resets"] == result["readInvalidations"] == result["renders"] == 1
    assert result["user"] is None and result["authStatus"] == "required"
    assert result["error"] == "synthetic network failure"


@pytest.mark.parametrize("state", [
    {"recordEditDirty": True},
    {"browserRecordingStatus": "recording"},
])
def test_existing_switch_callers_keep_the_default_action_label(state):
    result = run_exit_logic(state, action="switch")
    assert result["blocked"] is True
    assert "切换就诊" in result["toasts"][0]
    assert "退出登录" not in result["toasts"][0]
    assert result["unchanged"] and result["calls"] == []
