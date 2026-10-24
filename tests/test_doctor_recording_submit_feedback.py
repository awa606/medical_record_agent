"""Recording feedback follows real role and task boundaries, without service calls."""
from tests.test_doctor_history_restore import run_browser_logic


SETUP = r'''
requireEncounterBeforeInput=()=>true; renderBrowserRecordingPanel=()=>{};
focusNextActionPanel=()=>{}; focusRecordWorkspace=()=>{};
appState.browserRecordingFinalized={audio_id:'audio'};
appState.currentAudioId='audio';
const toasts=[];showToast=message=>toasts.push(message);
completeBrowserRecordingUpload=async()=>({audio_id:'audio'});
'''


def test_role_blocked_recording_does_not_claim_draft_or_submit_old_task():
    observed = run_browser_logic(SETUP + r'''
appState.currentTaskId=99; // A previously opened task is not this recording's result.
roleReviewRequired=()=>true;roleReviewPendingCount=()=>3;
await submitBrowserRecording();
console.log(JSON.stringify({message:appState.browserRecordingMessage,
 submitted:appState.browserRecordingSubmitted,pending:appState.pendingGenerateAfterRoleReview,toasts}));
''')
    assert "确认说话人身份" in observed["message"]
    assert "病历尚未生成" in observed["message"]
    assert not observed["submitted"]
    assert observed["pending"]
    assert not any("草稿已生成" in message for message in observed["toasts"])


def test_created_recording_task_waits_for_real_completed_event():
    observed = run_browser_logic(SETUP + r'''
roleReviewRequired=()=>false;listenForEvents=()=>{};
api=async()=>({task_id:42,status:'CREATED',events_url:'/events'});
await submitBrowserRecording();
console.log(JSON.stringify({message:appState.browserRecordingMessage,
 submitted:appState.browserRecordingSubmitted,task:appState.currentTaskId,toasts}));
''')
    assert "请等待草稿结果" in observed["message"]
    assert "已生成" not in observed["message"]
    assert observed["submitted"] and observed["task"] == 42
    assert not any("草稿已生成" in message for message in observed["toasts"])


def test_recording_upload_failure_keeps_error_feedback():
    observed = run_browser_logic(SETUP + r'''
completeBrowserRecordingUpload=async()=>{throw Error('本次上传失败')};
await submitBrowserRecording();
console.log(JSON.stringify({message:appState.browserRecordingMessage,
 submitted:appState.browserRecordingSubmitted,error:appState.lastActionError}));
''')
    assert observed == {"message": "上传失败：本次上传失败", "submitted": False, "error": "本次上传失败"}


def _terminal_feedback(event, *, state=""):
    return run_browser_logic(SETUP + r'''
global.EventSource=class{constructor(){this.handlers={}}addEventListener(k,fn){this.handlers[k]=fn}close(){}};
appState.currentTaskId=42;appState.browserRecordingSubmitted=true;
appState.browserRecordingMessage='录音转写完成，病历生成任务已提交，请等待草稿结果。';
refreshTask=async()=>{};
''' + state + r'''
listenForEvents(42,'/events');
await appState.eventSource.handlers[''' + repr(event) + r''']({data:JSON.stringify({task_id:42})});
console.log(JSON.stringify({message:appState.browserRecordingMessage,status:appState.taskStatus,toasts}));
''')


def test_real_completed_recording_event_announces_draft_ready():
    observed = _terminal_feedback("WAITING_DOCTOR_REVIEW")
    assert observed["message"] == "病历草稿已生成，可在工作区继续修改、审核和导出。"
    assert observed["status"] == "WAITING_DOCTOR_REVIEW"
    assert "病历草稿已生成，请修改并完成审核" in observed["toasts"]


def test_failed_recording_event_does_not_leave_pending_or_success_message():
    observed = _terminal_feedback("FAILED")
    assert observed["message"] == "病历生成失败，录音和转写已保留，请查看失败提示。"
    assert observed["status"] == "FAILED"
    assert not any("草稿已生成" in message for message in observed["toasts"])


def test_completion_after_role_confirmation_updates_recording_message():
    observed = _terminal_feedback("WAITING_DOCTOR_REVIEW", state="appState.browserRecordingSubmitted=false;")
    assert observed["message"].startswith("病历草稿已生成")


def test_another_audio_task_does_not_replace_this_recording_message():
    observed = _terminal_feedback("WAITING_DOCTOR_REVIEW", state="appState.currentAudioId='another-audio';")
    assert observed["message"] == "录音转写完成，病历生成任务已提交，请等待草稿结果。"
