"""A saved revision must invalidate the previously exported UI state."""
from tests.test_doctor_history_restore import run_browser_logic


def test_refresh_task_reloads_persisted_encounter_after_review():
    observed = run_browser_logic(r'''
Object.assign(appState, {
 currentEncounter:{id:13,task_id:9,status:'exported'},currentTaskId:9,
 approvalRevisionId:19,currentExportReadiness:{revision_id:19}
});
const requested=[];
api=async path=>{
 requested.push(path);
 if(path==='/api/encounters/13')return {id:13,task_id:9,status:'pending_review',current_revision_id:20};
 return {};
};
let renderedState;
renderAll=()=>{renderedState=derivePersistedWorkflowState({
 encounterStatus:appState.currentEncounter.status,taskStatus:appState.currentTask.status,
 currentStage:appState.currentTask.current_stage,hasTask:true,hasFields:true
})};
await refreshTask(9,{id:9,status:'WAITING_DOCTOR_REVIEW',current_stage:'reviewed',
 current_record_revision_id:20,result_json:{fields:{},draft:'synthetic'}});
console.log(JSON.stringify({renderedState,encounter:appState.currentEncounter,
 readiness:appState.currentExportReadiness,requested}));
''')
    assert observed['renderedState'] == 'pending_review'
    assert observed['encounter']['current_revision_id'] == 20
    assert observed['readiness'] is None
    assert '/api/encounters/13' in observed['requested']


def test_approval_success_clears_outdated_save_notice():
    observed = run_browser_logic(r'''
appState.currentTaskId=9;appState.recordSaveNotice='修改已保存；请审核当前版本后导出。';
pendingApprovalCount=()=>0;buildTaskApprovalPayload=async()=>({});
api=async()=>({id:9,status:'approved'});refreshTask=async()=>{};refreshExportReadiness=async()=>({});
await confirmFields();console.log(JSON.stringify(appState.recordSaveNotice));
''')
    assert observed == ''


def test_deleted_ai_candidate_is_not_reported_as_disease_exclusion():
    observed = run_browser_logic(r'''
console.log(JSON.stringify(referenceReviewStatus({doctor_review_status:'ai_candidate_deleted'})));
''')
    assert observed == '已移除AI候选'
