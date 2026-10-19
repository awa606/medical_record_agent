"""Failed record generation must not ask doctors to repeat successful ASR."""
from tests.test_doctor_history_restore import run_browser_logic


def test_audio_generation_failure_keeps_asr_and_retries_only_generation():
    observed = run_browser_logic(r'''
const nodes=new Map();
document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',hidden:false,dataset:{}});return nodes.get(id)};
appState.currentAudioId='saved-audio';
appState.currentAsrResult={text:'发热两天',segments:[{text:'发热两天',role:'患者'}]};
appState.currentTaskId=11;appState.taskStatus='FAILED';
appState.currentTask={id:11,status:'FAILED',current_stage:'failed',error_message:'extract_fields failed: URLError',
 result_json:{step_logs:[{step:'extract_fields',event:'started'},{step:'orchestrator',event:'failed'}]}};
renderTranscriptionFailurePanel();
let generation=0,transcription=0;
regenerateRecord=async()=>{generation++};retryTranscriptionFromFailure=async()=>{transcription++};
await retryFailedTask();
console.log(JSON.stringify({display:doctorDisplayState(),stage:$('transcriptionFailureStage').textContent,
 code:$('transcriptionFailureCode').textContent,title:$('transcriptionFailureTitle').textContent,
 action:$('retryTranscriptionButton').textContent,source:$('transcriptionFailureAudioState').textContent,
 generation,transcription,segments:appState.currentAsrResult.segments.length}));
''')
    assert observed['display']['title'] == '病历生成中断'
    assert observed['stage'] == '病历字段提取'
    assert observed['code'] == 'FIELD_EXTRACTION_FAILED'
    assert '转写已完成' in observed['source']
    assert observed['action'] == '重新生成病历'
    assert observed['generation'] == 1 and observed['transcription'] == 0
    assert observed['segments'] == 1


def test_true_asr_failure_still_exposes_transcription_recovery():
    observed = run_browser_logic(r'''
const nodes=new Map();document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',dataset:{}});return nodes.get(id)};
appState.currentAudioId='saved-audio';appState.taskStatus='FAILED';
appState.asrLastError='转写超时';appState.asrFailureStage='transcription';appState.asrFailureCode='ASR_TIMEOUT';
renderTranscriptionFailurePanel();
let generation=0,transcription=0;
regenerateRecord=async()=>{generation++};retryTranscriptionFromFailure=async()=>{transcription++};
await retryFailedTask();
console.log(JSON.stringify({stage:$('transcriptionFailureStage').textContent,code:$('transcriptionFailureCode').textContent,
 action:$('retryTranscriptionButton').textContent,generation,transcription}));
''')
    assert observed['stage'] == '智能转写'
    assert observed['code'] == 'ASR_TIMEOUT'
    assert observed['action'] == '重新转写'
    assert observed['generation'] == 0 and observed['transcription'] == 1


def test_text_generation_failure_never_claims_audio_is_saved():
    observed = run_browser_logic(r'''
const nodes=new Map();document.getElementById=id=>{if(!nodes.has(id))nodes.set(id,{textContent:'',dataset:{}});return nodes.get(id)};
appState.currentTaskId=4;appState.taskStatus='FAILED';appState.currentInputText='患者：咳嗽。';
appState.currentTask={id:4,status:'FAILED',current_stage:'failed',input_type:'text'};
appState.currentSteps=[{step_name:'safety_check',status:'FAILED'}];
renderTranscriptionFailurePanel();
console.log(JSON.stringify({display:doctorDisplayState(),stage:$('transcriptionFailureStage').textContent,
 code:$('transcriptionFailureCode').textContent,source:$('transcriptionFailureAudioState').textContent}));
''')
    assert observed['stage'] == '病历安全校验'
    assert observed['code'] == 'SAFETY_CHECK_FAILED'
    assert observed['source'] == '输入原文已保留'
    assert observed['display']['inputStatus'] == '文本导入'


def test_new_asr_failure_is_not_hidden_by_an_older_failed_generation_task():
    observed = run_browser_logic(r'''
appState.currentAudioId='saved-audio';appState.taskStatus='FAILED';appState.currentTaskId=11;
appState.currentTask={id:11,status:'FAILED',current_stage:'failed',result_json:{step_logs:[{step:'extract_fields',event:'started'}]}};
appState.asrLastError='本次重新转写超时';appState.asrFailureStage='transcription';appState.asrFailureCode='ASR_TIMEOUT';
console.log(JSON.stringify(currentFailureDetail()));
''')
    assert observed['kind'] == 'transcription'
    assert observed['code'] == 'ASR_TIMEOUT'

