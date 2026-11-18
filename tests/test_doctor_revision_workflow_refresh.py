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


def test_current_export_file_requires_the_active_approval_and_revision():
    observed = run_browser_logic(r'''
Object.assign(appState, {currentEncounter:{id:13}, currentTaskId:9,
 currentTask:{id:9, current_record_revision_id:19, result_json:{
   record_revision:{id:19,content_hash:'hash19'},export_event:{revision_id:19,approval_id:2}
 }}});
const ready={task_id:9, ready:true, approval_id:2, revision_id:19, content_hash:'hash19',
 current_stage:'EXPORTED', exports:{pdf_path:'legacy.pdf'}};
const bound = changes => Boolean(currentExportFile({...ready, ...changes}));
const states=[bound({}),bound({current_stage:'approved'}),bound({ready:false}),
 bound({task_id:10}),bound({revision_id:20}),bound({approval_id:3}),bound({content_hash:'other'}),
 bound({exports:null})];
delete appState.currentTask.result_json.export_event;
states.push(bound({})); // Legacy metadata, protected download will look up the event.
console.log(JSON.stringify(states));
''')
    assert observed == [True, False, False, False, False, False, False, False, True]
