"""Exercise real browser capture lifecycle with in-memory Web Audio devices."""
from tests.test_doctor_history_restore import run_browser_logic


SETUP = r'''
clearActionError=()=>{}; requireEncounterBeforeInput=()=>true;
secureBrowserRecordingContext=()=>true; shouldUseLiveBrowserRecordingFollow=()=>false;
renderBrowserRecordingPanel=()=>{}; releaseBrowserRecordingPreview=()=>{};
window.setInterval=()=>1; window.clearInterval=()=>{};
window.clearTimeout=()=>{};
const streams=[], contexts=[], processors=[];
let acquire=async()=>{}, resume=async()=>{};
Object.defineProperty(globalThis,'navigator',{configurable:true,value:{mediaDevices:{
 getUserMedia:async()=>{
  const track={stopped:false,stop(){this.stopped=true}};
  const stream={getTracks:()=>[track],getAudioTracks:()=>[track],track};
  streams.push(stream);await acquire();return stream;
 }
}}});
window.AudioContext=class {
 constructor(){this.sampleRate=48000;this.closed=false;this.destination={};contexts.push(this)}
 async resume(){await resume()}
 async close(){this.closed=true}
 createMediaStreamSource(){return {channelCount:2,connect(){},disconnect(){}}}
 createScriptProcessor(){const p={connect(){},disconnect(){this.disconnected=true},onaudioprocess:null};
  processors.push(p);return p}
};
ensureBrowserRecordingSession=async()=>{appState.browserRecordingSessionId='recording-session';return 'recording-session'};
api=async()=>({});deleteBrowserRecordingCleanup=async()=>{};clearBrowserRecordingQueue=async()=>{};
flushBrowserRecordingChunk=async()=>{};
finalizeBrowserRecording=async()=>{appState.browserRecordingStatus='recorded'};
const frame={inputBuffer:{length:4,numberOfChannels:2,sampleRate:48000,
 getChannelData:channel=>new Float32Array(channel ? [0,0,0,0] : [1,1,1,1])}};
const ticks=async()=>{for(let i=0;i<12;i++)await Promise.resolve()};
'''


def run_capture(body):
    return run_browser_logic(SETUP + body)


def test_second_start_keeps_one_capture_and_stop_releases_every_device():
    observed = run_capture(r'''
await startBrowserRecording();
await startBrowserRecording();
for(const processor of processors)processor.onaudioprocess?.(frame);
const captured=appState.browserRecordingRecordedSamples;
const samples=Array.from(mergeBrowserRecordingChunks(appState.browserRecordingChunkBuffer));
appState.browserRecordingStartedAt=Date.now()-5000;
await stopBrowserRecording();
console.log(JSON.stringify({streams:streams.length,contexts:contexts.length,captured,samples,
 stopped:streams.every(s=>s.track.stopped),closed:contexts.every(c=>c.closed)}));
''')
    assert observed == {'streams': 1, 'contexts': 1, 'captured': 4,
                        'samples': [.5, .5, .5, .5], 'stopped': True, 'closed': True}


def test_async_duplicate_start_does_not_request_a_second_microphone():
    observed = run_capture(r'''
const releases=[];acquire=()=>new Promise(resolve=>releases.push(resolve));
const first=startBrowserRecording();await ticks();
const duplicate=startBrowserRecording();await ticks();
for(const release of releases)release();await Promise.all([first,duplicate]);
console.log(JSON.stringify({streams:streams.length,contexts:contexts.length,
 status:appState.browserRecordingStatus}));
''')
    assert observed == {'streams': 1, 'contexts': 1, 'status': 'recording'}


def test_released_callback_cannot_write_into_a_new_recording():
    observed = run_capture(r'''
await startBrowserRecording();const old=processors[0].onaudioprocess;
cleanupBrowserRecordingCapture();appState.browserRecordingStatus='idle';
await startBrowserRecording();old(frame);processors[1].onaudioprocess(frame);
console.log(JSON.stringify({samples:appState.browserRecordingRecordedSamples,
 oldStopped:streams[0].track.stopped,oldClosed:contexts[0].closed}));
''')
    assert observed == {'samples': 4, 'oldStopped': True, 'oldClosed': True}


def test_pause_resume_keeps_same_capture_and_counts_only_recording_frames():
    observed = run_capture(r'''
await startBrowserRecording();const callback=processors[0].onaudioprocess;
callback(frame);await pauseBrowserRecording();callback(frame);
await startBrowserRecording();await resumeBrowserRecording();callback(frame);
console.log(JSON.stringify({streams:streams.length,contexts:contexts.length,
 samples:appState.browserRecordingRecordedSamples,status:appState.browserRecordingStatus}));
''')
    assert observed == {'streams': 1, 'contexts': 1, 'samples': 8, 'status': 'recording'}


def test_cancelled_recovery_cannot_resurrect_capture_after_audio_context_resumes():
    observed = run_capture(r'''
appState.browserRecordingStatus='paused';appState.browserRecordingSessionId='existing';
let release;resume=()=>new Promise(resolve=>release=resolve);
const pending=resumeBrowserRecording();await ticks();
appState.browserRecordingRequestId++;cleanupBrowserRecordingCapture();
appState.browserRecordingStatus='idle';release();await pending;
console.log(JSON.stringify({status:appState.browserRecordingStatus,processors:processors.length,
 stopped:streams.every(s=>s.track.stopped),closed:contexts.every(c=>c.closed),
 attached:Boolean(appState.browserRecordingProcessor)}));
''')
    assert observed == {'status': 'idle', 'processors': 0, 'stopped': True,
                        'closed': True, 'attached': False}


def test_late_callback_after_stop_cannot_append_while_flush_is_pending():
    observed = run_capture(r'''
await startBrowserRecording();const callback=processors[0].onaudioprocess;callback(frame);
appState.browserRecordingStartedAt=Date.now()-5000;
let release;flushBrowserRecordingChunk=()=>new Promise(resolve=>release=resolve);
const stopping=stopBrowserRecording();callback(frame);release();await stopping;
console.log(JSON.stringify({samples:appState.browserRecordingRecordedSamples,
 stopped:streams.every(s=>s.track.stopped),closed:contexts.every(c=>c.closed)}));
''')
    assert observed == {'samples': 4, 'stopped': True, 'closed': True}


def test_cancel_then_new_recording_rejects_previous_capture_callback():
    observed = run_capture(r'''
await startBrowserRecording();const old=processors[0].onaudioprocess;old(frame);
await cancelBrowserRecording();await startBrowserRecording();
old(frame);processors[1].onaudioprocess(frame);
console.log(JSON.stringify({samples:appState.browserRecordingRecordedSamples,
 oldStopped:streams[0].track.stopped,oldClosed:contexts[0].closed,
 status:appState.browserRecordingStatus,session:appState.browserRecordingSessionId}));
''')
    assert observed == {'samples': 4, 'oldStopped': True, 'oldClosed': True,
                        'status': 'recording', 'session': 'recording-session'}


def test_cancel_pending_refuses_restart_until_old_session_cleanup_finishes():
    observed = run_capture(r'''
await startBrowserRecording();let release;api=()=>new Promise(resolve=>release=resolve);
const pending=cancelBrowserRecording();await ticks();
await startBrowserRecording();const before=streams.length;
release({});await pending;await startBrowserRecording();
processors.at(-1).onaudioprocess(frame);
console.log(JSON.stringify({before,streams:streams.length,samples:appState.browserRecordingRecordedSamples,
 status:appState.browserRecordingStatus,session:appState.browserRecordingSessionId}));
''')
    assert observed == {'before': 1, 'streams': 2, 'samples': 4,
                        'status': 'recording', 'session': 'recording-session'}


def test_late_microphone_permission_after_cancel_cannot_take_over_new_capture():
    observed = run_capture(r'''
let release;acquire=()=>new Promise(resolve=>release=resolve);
const oldStart=startBrowserRecording();await ticks();
await cancelBrowserRecording();acquire=async()=>{};
await startBrowserRecording();release();await oldStart;
processors[0].onaudioprocess(frame);
console.log(JSON.stringify({streams:streams.length,contexts:contexts.length,
 oldStopped:streams[0].track.stopped,currentStopped:streams[1].track.stopped,
 samples:appState.browserRecordingRecordedSamples,status:appState.browserRecordingStatus}));
''')
    assert observed == {'streams': 2, 'contexts': 1, 'oldStopped': True,
                        'currentStopped': False, 'samples': 4, 'status': 'recording'}


def test_old_cancel_response_cannot_erase_a_newer_session_owner():
    observed = run_capture(r'''
await startBrowserRecording();let release;api=()=>new Promise(resolve=>release=resolve);
const cancelling=cancelBrowserRecording();await ticks();
// A restored/new owner invalidates asynchronous work from the previous session.
appState.browserRecordingRequestId++;appState.browserRecordingSessionId='new-owner';
appState.browserRecordingStatus='recorded';appState.browserRecordingRecordedSamples=123;
release({});await cancelling;
console.log(JSON.stringify({session:appState.browserRecordingSessionId,
 status:appState.browserRecordingStatus,samples:appState.browserRecordingRecordedSamples}));
''')
    assert observed == {'session': 'new-owner', 'status': 'recorded', 'samples': 123}
