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
