"""Persisted input must survive encounter reopening without using draft prose."""
import json
import subprocess
from pathlib import Path


def restored(task):
    source = Path('static/doctor.js').read_text(encoding='utf8')
    start = source.find('function restoreTaskSource(')
    if start < 0:
        start = source.index('function applyEncounterDetail(')
    code = source[start:source.index('function selectedEncounterId()', start)]
    script = "const appState={}; const resetTaskState=()=>{};\n" + code
    script += '\napplyEncounterDetail(' + json.dumps({'id':13,'task':task}) + ');'
    script += '\nconsole.log(JSON.stringify(appState));'
    return json.loads(subprocess.check_output(['node','-e',script], text=True, encoding='utf8'))


def test_reopen_text_keeps_original_not_doctor_modified_draft():
    observed = restored({'id':9, 'input_text':'[患者] 发热伴咳嗽。', 'result_json':{
        'conversation_text':'[患者] 发热伴咳嗽。', 'draft':'医生修改后的病历', 'fields':{}}})
    assert observed['currentInputText'] == '[患者] 发热伴咳嗽。'
    assert not observed.get('currentAsrResult')


def test_reopen_audio_keeps_segment_identity_role_and_timing():
    asr = {'audio_id':'anonymous-audio', 'text':'没有药物过敏史。', 'conversation_text':'[患者] 没有药物过敏史。',
           'segments':[{'segment_id':'seg-1','speaker_id':'s1','role':'患者','start':1.2,'end':3.4,'text':'没有药物过敏史。'}]}
    observed = restored({'id':10,'result_json':{'asr_source':asr,'conversation_text':asr['conversation_text']}})
    assert observed['currentAsrResult'] == asr
    assert observed['currentAudioId'] == 'anonymous-audio'


def test_missing_original_is_not_reconstructed_from_record_fields():
    observed = restored({'id':11,'result_json':{'fields':{'chief_complaint':{'value':'发热'}},'draft':'发热'}})
    assert observed['currentInputText'] == ''
    assert observed.get('transcriptRestoreStatus') == 'missing'


def test_task_input_can_restore_when_legacy_result_has_no_conversation():
    observed = restored({'id':12,'input_text':'[患者] 咳嗽两天。','result_json':{'fields':{}}})
    assert observed['currentInputText'] == '[患者] 咳嗽两天。'
