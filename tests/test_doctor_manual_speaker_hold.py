"""Group-level deferrals must be deliberate, durable, and separate from confirmed roles."""
from tests.test_doctor_history_restore import run_browser_logic


def test_group_hold_is_the_only_sent_map_and_cancels_pending_automatic_generation():
    result = run_browser_logic(r"""
const segments=[{speaker_id:"A",role:"患者",text:"甲"},{speaker_id:"B",role:"医生",text:"乙"}];
appState.currentAsrResult={segments,role_quality:{status:"passed"}};
appState.pendingGenerateAfterRoleReview=true;
resetRecordPreview=()=>{};renderAll=()=>{};
updateSpeakerRole("B","待确认");
console.log(JSON.stringify({maps:speakerRolesForReviewSave(),required:roleReviewRequired(),
  auto:appState.pendingGenerateAfterRoleReview,roles:segments.map(s=>s.role)}));
""")
    assert result == {'maps': [{'speaker_id': 'B', 'role': '待确认', 'reviewed_by_doctor': False}],
                      'required': True, 'auto': False, 'roles': ['患者', '医生']}


def test_only_the_persisted_manual_hold_is_shown_without_making_a_new_mapping():
    result = run_browser_logic(r"""
appState.currentAsrResult={speaker_assignments:[
  {speaker_id:"safe",role:"待确认",requires_confirmation:true,source:"manual_draft"},
  {speaker_id:"auto",role:"待确认",requires_confirmation:true,source:"rules"},
]};
const groups=transcriptSpeakerGroups(["safe","auto"].map(id=>({speakerId:id,label:"待确认"})));
console.log(JSON.stringify({shown:groups.map(g=>g.savedPending),maps:speakerRolesForReviewSave()}));
""")
    assert result == {'shown': [True, False], 'maps': []}


def test_matching_session_review_changes_the_controls_without_replacing_the_saved_record_source():
    result = run_browser_logic(r"""
const prior={speaker_id:"B",role:"陪同人员",source:"manual_speaker_map",confidence:0.99};
const pending={...prior,role:"待确认",source:"manual_draft",requires_confirmation:true};
appState.currentAsrResult={speaker_assignments:[prior],role_quality:{status:"passed"}};
appState.currentAsrSessionId="session1";appState.currentAudioId="audio1";
appState.sessionRoleReview={sessionId:"session1",audioId:"audio1",speaker_assignments:[pending],role_quality:{status:"needs_review"}};
const rows=[{speakerId:"B",label:"陪同人员"}];
const same=transcriptSpeakerGroups(rows)[0].savedPending && roleReviewRequired();
appState.currentAsrSessionId="session2";
const other=transcriptSpeakerGroups(rows)[0].savedPending;
appState.currentAsrSessionId="session1";appState.currentAudioId="audio2";
console.log(JSON.stringify({same,other,wrongAudio:transcriptSpeakerGroups(rows)[0].savedPending,prior:appState.currentAsrResult.speaker_assignments[0].role}));
""")
    assert result == {'same': True, 'other': False, 'wrongAudio': False, 'prior': '陪同人员'}
