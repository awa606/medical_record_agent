"""Exercise the real restore coordinator without ASR or model calls."""
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run_browser_logic(body, *, real_preview=False):
    script = r'''
const fs = require('fs');
const location = new URL('http://localhost/static/doctor.html?session_id=saved#encounter');
const window = {location, clearTimeout, setTimeout, history: {replaceState(_s,_t,url) {
  const next = new URL(url, location); location.href = next.href;
}}};
const store = new Map([['mra-session-encounter:saved', JSON.stringify({encounterId:13,ownerId:1})]]);
const sessionStorage = {getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)};
const document = {getElementById:()=>({load(){},pause(){},removeAttribute(){}})};
let source = fs.readFileSync('static/doctor.js','utf8').replace(/\ninit\(\);\s*$/, '');
source += `
renderAll=()=>{}; renderModelAndKnowledgeStatus=()=>{}; renderAssist=()=>{}; renderDebug=()=>{};
renderAuthPanel=()=>{}; renderProductShell=()=>{};
setProductView=view=>{appState.productView=view};
setBusy=(value)=>{appState.busy=value}; showToast=()=>{}; closeDrawer=()=>{};
reportActionError=e=>{appState.lastActionError=e.message};
encounterSwitchBlocked=()=>false; refreshEncounterWorklist=async()=>{};
syncApprovalReviewStateWithRevision=()=>{}; resetRecordEditState=()=>{};
clearApprovalReviewSelections=()=>{}; resetRoleReviewState=()=>{}; resetRecordPreview=()=>{};
closeAsrStream=()=>{}; releaseAudioPlayerSource=()=>{};
buildLocalAgentTrace=()=>({local:true});
appState.authUser={id:1};
`;
eval(source + '\n(async()=>{' + process.argv[1] + '\n})().catch(e=>{console.error(e);process.exitCode=1});');
'''
    if real_preview:
        script = script.replace('resetRecordPreview=()=>{};', '')
        script = script.replace('resetRoleReviewState=()=>{};', '')
    output = subprocess.check_output(['node', '-e', script, body], cwd=ROOT,
                                     text=True, encoding='utf8', timeout=25)
    return json.loads(output)


def test_audio_refresh_restores_record_revision_before_asr_without_generation():
    result = run_browser_logic(r'''
const calls=[];
const task={id:11,current_stage:'EXPORTED',current_record_revision_id:19,
 result_json:{fields:{chief_complaint:{value:'发热'}},draft:'已保存病历',
 asr_source:{audio_id:'audio-1',segments:[{segment_id:'seg-1',text:'发热。',role:'患者'}]}}};
api=async path=>{calls.push(path);
 if(path==='/api/encounters/13')return {id:13,task_id:11,status:'exported',task};
 if(path==='/api/tasks/11')return task;
 if(path.endsWith('/steps'))return [];
 if(path.endsWith('/export-readiness'))return {revision_id:19,approved:true,exports:{txt:'saved'}};
 if(path.endsWith('/evidence')||path.includes('/trace'))return {};
 if(path==='/api/asr/sessions/saved')return {session_id:'saved',audio_id:'audio-1',status:'reviewed'};
 if(path.endsWith('/result'))return task.result_json.asr_source;
 throw Error('Unexpected call '+path);
};
await restoreAsrSessionFromUrl();
console.log(JSON.stringify({taskId:appState.currentTaskId,status:appState.taskStatus,
 revision:appState.currentTask?.current_record_revision_id,fields:appState.currentRecordFields,
 transcript:appState.currentAsrResult?.segments,calls,busy:appState.busy}));
''')
    assert result['taskId'] == 11
    assert result['revision'] == 19
    assert result['status'] == 'EXPORTED'
    assert result['fields']['chief_complaint']['value'] == '发热'
    assert result['transcript'][0]['segment_id'] == 'seg-1'
    assert not result['busy']
    assert not any('generate' in p or 'transcribe' in p for p in result['calls'])


def test_late_export_readiness_cannot_overwrite_another_encounter():
    result = run_browser_logic(r'''
appState.currentEncounter={id:13}; appState.currentTaskId=11;
let release; api=()=>new Promise(resolve=>release=resolve);
const pending=refreshExportReadiness();
appState.encounterRestoreVersion++;appState.currentEncounter={id:14};appState.currentTaskId=12;
appState.currentExportReadiness={revision_id:20};appState.currentExports={txt:'new'};
release({revision_id:19,exports:{txt:'old'}});await pending;
console.log(JSON.stringify({readiness:appState.currentExportReadiness,exports:appState.currentExports}));
''')
    assert result == {'readiness': {'revision_id': 20}, 'exports': {'txt': 'new'}}


def test_late_export_failure_does_not_clear_new_patient_approval():
    result = run_browser_logic(r'''
appState.currentEncounter={id:13};appState.currentTaskId=11;
let fail;api=()=>new Promise((_r,reject)=>fail=reject);
const pending=refreshExportReadiness();
appState.encounterRestoreVersion++;appState.currentEncounter={id:14};appState.currentTaskId=12;
appState.currentExportReadiness={revision_id:20};fail(Error('late failure'));await pending;
console.log(JSON.stringify(appState.currentExportReadiness));
''')
    assert result == {'revision_id': 20}


def test_live_reference_does_not_offer_unpersisted_success_actions():
    source = (ROOT / 'static/doctor.js').read_text(encoding='utf8')
    for action in ('mark-asked', 'add-question', 'adopt-candidate', 'defer', 'ignore'):
        assert f'data-live-clinical-action="{action}"' not in source
    assert '操作已记录' not in source


def test_timeout_clears_busy_offers_read_retry_and_never_generates():
    result = run_browser_logic(r'''
const nativeTimer=setTimeout;const delays=[];
setTimeout=(fn,ms)=>{delays.push(ms);return nativeTimer(fn,5)};
const calls=[];api=path=>{calls.push(path);return new Promise(()=>{})};
await restoreEncounter(13);
const failed={busy:appState.busy,error:appState.encounterRestoreError,target:appState.encounterRestoreTarget};
api=async path=>{calls.push(path);return {id:13,task:null}};
await handleWorkflowAction('retry-history');
console.log(JSON.stringify({failed,calls,delays,error:appState.encounterRestoreError,encounter:appState.currentEncounter.id}));
''')
    assert not result['failed']['busy']
    assert '15秒' in result['failed']['error']
    assert result['failed']['target']['encounterId'] == 13
    assert result['calls'] == ['/api/encounters/13', '/api/encounters/13']
    assert set(result['delays']) == {15000}
    assert result['error'] == ''


def test_slow_auxiliary_reads_do_not_hold_record_restore():
    result = run_browser_logic(r'''
const task={id:11,current_stage:'WAITING_DOCTOR_REVIEW',result_json:{fields:{chief_complaint:{value:'发热'}}}};
api=async path=>{
 if(path==='/api/encounters/13')return {id:13,task_id:11,task};
 if(path==='/api/tasks/11')return task;
 if(path.endsWith('/export-readiness'))return {revision_id:19};
 return new Promise(()=>{});
};
await restoreEncounter(13);
const observed={busy:appState.busy,fields:appState.currentRecordFields,knowledge:appState.knowledgeEvidenceStatus};
appState.encounterReadController.abort();
console.log(JSON.stringify(observed));
''')
    assert result == {'busy': False, 'fields': {'chief_complaint': {'value': '发热'}}, 'knowledge': 'loading'}


def test_fast_switch_discards_old_encounter_and_preserves_latest_task():
    result = run_browser_logic(r'''
let release;
api=async path=>{
 if(path==='/api/encounters/13')return new Promise(resolve=>release=resolve);
 if(path==='/api/encounters/14')return {id:14,task:{id:12,result_json:{fields:{chief_complaint:{value:'咳嗽'}}}}};
 if(path==='/api/tasks/12')return {id:12,result_json:{fields:{chief_complaint:{value:'咳嗽'}}}};
 return {};
};
const old=restoreEncounter(13);await restoreEncounter(14);
release({id:13,task:{id:11}});await old;
console.log(JSON.stringify({encounter:appState.currentEncounter.id,task:appState.currentTaskId,busy:appState.busy}));
''')
    assert result == {'encounter': 14, 'task': 12, 'busy': False}


def test_text_history_refresh_uses_encounter_url_without_asr_or_model_calls():
    result = run_browser_logic(r'''
window.location.href='http://localhost/static/doctor.html?encounter_id=13#encounter';
const calls=[];const task={id:11,input_text:'患者原话',current_stage:'EXPORTED',result_json:{fields:{chief_complaint:{value:'医生修订'}}}};
api=async path=>{calls.push(path);if(path==='/api/encounters/13')return {id:13,task};if(path==='/api/tasks/11')return task;return {}};
await restoreAsrSessionFromUrl();
console.log(JSON.stringify({input:appState.currentInputText,task:appState.currentTaskId,calls}));
''')
    assert result['input'] == '患者原话'
    assert result['task'] == 11
    assert all(path.startswith(('/api/encounters/', '/api/tasks/')) for path in result['calls'])


def test_logout_or_revision_change_invalidates_export_read_response():
    result = run_browser_logic(r'''
appState.currentEncounter={id:13};appState.currentTaskId=11;appState.currentTask={current_record_revision_id:19};
let release;api=()=>new Promise(resolve=>release=resolve);
const pending=refreshExportReadiness();appState.currentTask={current_record_revision_id:20};
appState.currentExportReadiness={revision_id:20,approved:false};
release({revision_id:19,approved:true});await pending;
console.log(JSON.stringify(appState.currentExportReadiness));
''')
    assert result == {'revision_id': 20, 'approved': False}


def test_unauthenticated_boot_does_not_read_session_or_patient():
    result = run_browser_logic(r'''
appState.authUser=null;let calls=0;api=()=>{calls++;throw Error('Must not read')};
await restoreAsrSessionFromUrl();console.log(JSON.stringify({calls}));
''')
    assert result == {'calls': 0}
