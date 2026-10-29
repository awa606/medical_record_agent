"""Exercise preview boundaries with isolated JS events, never a model or service."""
import pytest

from tests.test_doctor_history_restore import run_browser_logic


SETUP = r'''
renderFields=()=>{}; renderBrowserRecordingPanel=()=>{}; renderNextActionPanel=()=>{};
focusNextActionPanel=()=>{}; clearActionError=()=>{}; closeInputMethodMenu=()=>{};
requireEncounterBeforeInput=()=>true; listenForEvents=()=>{};
const timers=[];
window.setTimeout=fn=>{timers.push(fn);return timers.length};
window.clearTimeout=()=>{}; // A callback already queued by the browser can still arrive.
const tick=async()=>{for(const fn of timers.splice(0))await fn();await Promise.resolve()};
const segment={segment_id:'one',speaker_id:'A',role:'患者',role_source:'manual_speaker_map',
 reviewed_by_doctor:true,text:'发热两天，没有胸痛。'};
const setInput=()=>{appState.currentAsrSessionId='session';appState.currentAudioId='audio';
 appState.liveTranscriptSegments=[{...segment}];appState.currentAsrResult=null};
const calls=[];
api=async(path,opts)=>{calls.push(path);return path.includes('/preview')
 ? {status:'preview_ready',fields:{}} : {task_id:42,status:'CREATED',events_url:'/events'}};
global.EventSource=class{constructor(){this.handlers={}} addEventListener(k,fn){this.handlers[k]=fn}
 close(){} emit(k,data){this.handlers[k]?.({data:JSON.stringify(data)})}};
'''


def run_preview(body):
    return run_browser_logic(SETUP + body, real_preview=True)


def test_upload_generation_blocks_early_and_late_stable_events_until_formal_request():
    observed = run_preview(r'''
uploadAndTranscribe=async()=>{
 setInput();listenForAsrEvents('/events');
 appState.asrEventSource.emit('segment',{audio_id:'audio',segment});await tick();
 appState.currentAsrResult={segments:[segment],role_quality:{status:'needs_review'}};
 return {audio_id:'audio'};
};
await runAudioWorkflowFromFile({},'system','generate');
const before=calls.slice();
appState.currentAsrResult.role_quality.status='passed';
appState.pendingGenerateAfterRoleReview=false;
await continueGeneratingFromTranscription({audio_id:'audio'});
appState.asrEventSource.emit('segment',{audio_id:'audio',segment:{...segment,segment_id:'late'}});
await tick();
console.log(JSON.stringify({before,calls,task:appState.currentTaskId}));
''')
    assert observed['before'] == []
    assert observed['calls'] == ['/api/audio/audio/generate-record']
    assert observed['task'] == 42


def test_transcribe_only_still_previews_trusted_stable_input():
    observed = run_preview(r'''
uploadAndTranscribe=async()=>{setInput();scheduleRecordPreview({force:true});await tick();return {audio_id:'audio'}};
await runAudioWorkflowFromFile({},'system','transcribe');
console.log(JSON.stringify(calls));
''')
    assert observed == ['/api/records/preview']


def test_provisional_unmapped_segment_does_not_block_trusted_stable_preview():
    observed = run_preview(r'''
setInput();appState.liveTranscriptSegments.push({segment_id:'partial',text:'尚未确认',provisional:true});
scheduleRecordPreview({force:true});await tick();console.log(JSON.stringify(calls));
''')
    assert observed == ['/api/records/preview']


@pytest.mark.parametrize('entry', ['record', 'record_submit', 'fixed'])
def test_generation_entry_suspends_before_capture_or_completion(entry):
    actions = {
        'record': r'''
releaseBrowserRecordingPreview=()=>{};secureBrowserRecordingContext=()=>true;
setBrowserRecordingError=()=>{};
Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
 getUserMedia:async()=>{await attempt();throw Error('isolated stop before hardware')}
}}});
await startBrowserRecording();
''',
        'record_submit': r'''
appState.browserRecordingFinalized={audio_id:'audio'};
completeBrowserRecordingUpload=async()=>{await attempt();throw Error('isolated stop before completion')};
await submitBrowserRecording();
''',
        'fixed': r'''
fetchFixedDemoAudioBuffer=async()=>{setInput();await attempt();throw Error('isolated stop before file read')};
await startFixedAudioLiveDemo();
''',
    }
    observed = run_preview(r'''
setInput();
const attempt=async()=>{scheduleRecordPreview({force:true});await tick()};
''' + actions[entry] + r'''
console.log(JSON.stringify({calls,suspended:appState.recordPreviewSuspended}));
''')
    assert observed == {'calls': [], 'suspended': True}


@pytest.mark.parametrize('change', [
    "appState.speakerMappingRequired=true",
    "appState.speakerAssignments=[{speaker_id:'A',role:'患者',requires_confirmation:true}]",
    "appState.roleReviewDirty=true",
    "appState.liveTranscriptSegments[0].text='咳嗽两天，没有胸痛。'",
    "appState.currentAsrSessionId='replacement-session'",
])
def test_queued_preview_rechecks_roles_and_input_before_sending(change):
    observed = run_preview(r'''
setInput();scheduleRecordPreview({force:true});
''' + change + r''';
await tick();console.log(JSON.stringify(calls));
''')
    assert observed == []


@pytest.mark.parametrize('outcome', ['resolve', 'reject'])
def test_old_input_response_or_error_cannot_replace_current_preview(outcome):
    observed = run_preview(r'''
setInput();let finish;
api=()=>new Promise((resolve,reject)=>{finish=''' + outcome + r'''});
const pending=fetchRecordPreview(liveConversationTextForPreview(),currentReviewSegments());
appState.liveTranscriptSegments[0].text='咳嗽两天，没有胸痛。';
finish(''' + ("{status:'preview_ready',fields:{old:true}}" if outcome == 'resolve' else "Error('old input failure')") + r''');
await pending;
console.log(JSON.stringify({preview:appState.recordPreview,status:appState.recordPreviewStatus,
 error:appState.recordPreviewError,inFlight:appState.recordPreviewInFlight}));
''')
    assert observed == {'preview': None, 'status': 'idle', 'error': '', 'inFlight': False}


def test_closed_sse_source_cannot_replace_new_input_or_schedule_preview():
    observed = run_preview(r'''
setInput();listenForAsrEvents('/old');const old=appState.asrEventSource;
listenForAsrEvents('/new');
old.emit('segment',{audio_id:'old-audio',segment:{...segment,segment_id:'old'}});
old.emit('speaker_mapping_required',{assignments:[{speaker_id:'old',requires_confirmation:true}]});
await tick();console.log(JSON.stringify({calls,audio:appState.currentAudioId,
 segments:appState.liveTranscriptSegments.length,mapping:appState.speakerMappingRequired}));
''')
    assert observed == {'calls': [], 'audio': 'audio', 'segments': 1, 'mapping': False}


def test_same_length_prefix_edit_with_same_tail_is_not_deduplicated():
    observed = run_preview(r'''
const tail='相同后文'.repeat(40);
appState.currentInputText='发热'+tail;
await fetchRecordPreview(appState.currentInputText,[]);
appState.currentInputText='咳嗽'+tail;
await fetchRecordPreview(appState.currentInputText,[]);
console.log(JSON.stringify(calls));
''')
    assert observed == ['/api/records/preview', '/api/records/preview']


@pytest.mark.parametrize('action', ['cancel', 'restart'])
def test_cancel_or_restart_recording_closes_old_stream_before_async_work(action):
    operation = r'''
Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
 getUserMedia:async()=>{old.emit('segment',{audio_id:'old-audio',segment});throw Error('no hardware')}
}}});
secureBrowserRecordingContext=()=>true;setBrowserRecordingError=()=>{};
await startBrowserRecording();
''' if action == 'restart' else r'''
deleteBrowserRecordingCleanup=async()=>{};clearBrowserRecordingQueue=async()=>{};
await cancelBrowserRecording();old.emit('segment',{audio_id:'old-audio',segment});
'''
    observed = run_preview(r'''
setInput();appState.browserRecordingSessionId='session';
cleanupBrowserRecordingCapture=()=>{};releaseBrowserRecordingPreview=()=>{};
// This fixture normally stubs stream cleanup; use the real close behavior here.
closeAsrStream=()=>{appState.asrEventSource?.close();appState.asrEventSource=null};
listenForAsrEvents('/old');const old=appState.asrEventSource;
''' + operation + r'''
console.log(JSON.stringify({audio:appState.currentAudioId,subscribed:Boolean(appState.asrEventSource)}));
''')
    assert observed == {'audio': 'audio', 'subscribed': False}


@pytest.mark.parametrize('change', ['segment', 'speaker', 'undo'])
def test_manual_transcript_or_role_change_invalidates_visible_preview(change):
    operation = {
        'segment': "updateReviewSegment(0,{text:'咳嗽两天'})",
        'speaker': "updateSpeakerRole('A','医生')",
        'undo': 'appState.lastSpeakerMergeSnapshot=speakerMergeSnapshot();undoLastSpeakerMerge()',
    }[change]
    observed = run_preview(r'''
setInput();appState.currentAsrResult={segments:[{...segment}],role_quality:{status:'passed'}};
appState.recordPreview={fields:{old:true}};renderRunContext=()=>{};
''' + operation + r''';
console.log(JSON.stringify(appState.recordPreview));
''')
    assert observed is None
