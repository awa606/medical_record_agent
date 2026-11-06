"""An explicit generation may replace only a failed task with no saved record."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.db import bind_task_to_encounter, create_record_revision_for_task, create_task, get_audit_logs, get_connection, get_encounter, get_task, update_task
from tests.auth_helpers import login_as_admin


@pytest.fixture
def failed_encounter(tmp_path, monkeypatch):
    monkeypatch.setenv('MEDICAL_RECORD_AGENT_DB', str(tmp_path / 'db.sqlite3'))
    monkeypatch.setenv('MEDICAL_RECORD_AGENT_OUTPUT_DIR', str(tmp_path / 'outputs'))
    monkeypatch.setenv('MEDICAL_RECORD_AGENT_UPLOAD_DIR', str(tmp_path / 'uploads'))
    client = TestClient(app)
    login_as_admin(client)
    encounter = client.post('/api/encounters', json={'patient_deidentified_id':'SIM-RETRY'}).json()
    client.post(f"/api/encounters/{encounter['id']}/check-in")
    old = create_task(input_type='text', status='FAILED', current_stage='failed', input_text='患者：发热。')
    bind_task_to_encounter(old, encounter['id'], owner_user_id=encounter['doctor_user_id'])
    update_task(old, result_json=json.dumps({'error_message':'transport failed','step_logs':[{'step':'extract_fields','event':'failed'}]}))
    return client, encounter, old


def test_explicit_retry_preserves_failed_task_and_blocks_second_request(failed_encounter):
    client, encounter, old = failed_encounter
    before = get_task(old)
    with patch('app.api.records.ensure_record_provider_available'), patch('app.api.records.run_record_generation_task') as run:
        response = client.post('/api/records/generate', json={'conversation_text':'患者：发热。','encounter_id':encounter['id']})
        assert response.status_code == 200, response.text
        new = response.json()['task_id']
        assert new != old and get_encounter(encounter['id'])['task_id'] == new
        assert get_task(old) == before
        assert run.call_count == 1
        second = client.post('/api/records/generate', json={'conversation_text':'患者：发热。','encounter_id':encounter['id']})
        assert second.status_code == 409 and run.call_count == 1
    audit = get_audit_logs(new)
    assert any(x['event_type'] == 'failed_task_replaced' and str(old) in x['event_detail'] for x in audit)


@pytest.mark.parametrize('status', ['CREATED','EXTRACTING_FIELDS','WAITING_DOCTOR_REVIEW','DONE'])
def test_active_or_reviewable_task_cannot_be_replaced(failed_encounter,status):
    client,encounter,old=failed_encounter
    update_task(old,status=status)
    with patch('app.api.records.ensure_record_provider_available'),patch('app.api.records.run_record_generation_task') as run:
        response=client.post('/api/records/generate',json={'conversation_text':'患者：发热。','encounter_id':encounter['id']})
        assert response.status_code == 409 and run.call_count == 0
    assert get_encounter(encounter['id'])['task_id'] == old


def test_retry_is_not_general_rebinding_permission(failed_encounter):
    _,encounter,old=failed_encounter
    new=create_task(input_type='text',status='CREATED',current_stage='created',input_text='患者：发热。')
    with pytest.raises(ValueError,match='already bound'):
        bind_task_to_encounter(new,encounter['id'],owner_user_id=encounter['doctor_user_id'])
    assert get_encounter(encounter['id'])['task_id'] == old


def test_failed_task_with_saved_record_is_protected_even_if_pointer_is_missing(failed_encounter):
    client,encounter,old=failed_encounter
    create_record_revision_for_task(old, {'fields':{},'draft':'已保存内容'}, actor_user_id=encounter['doctor_user_id'], source='doctor_review',workflow_status='draft')
    update_task(old,status='FAILED')
    with get_connection() as connection:
        connection.execute('UPDATE encounter SET current_revision_id=NULL WHERE id=?',(encounter['id'],))
    with patch('app.api.records.ensure_record_provider_available'),patch('app.api.records.run_record_generation_task') as run:
        response=client.post('/api/records/generate',json={'conversation_text':'患者：发热。','encounter_id':encounter['id']})
        assert response.status_code == 409 and run.call_count == 0


def test_audio_retry_reuses_saved_transcript_without_transcription(failed_encounter):
    from app.schemas import ASRResult
    client,encounter,old=failed_encounter
    result=ASRResult(audio_id='existing-audio',engine='funasr',text='发热。',conversation_text='[患者] 发热。')
    with patch('app.api.audio._read_audio_record',return_value=None),patch('app.api.audio._read_transcript',return_value=result),patch('app.api.audio._write_transcript'),patch('app.api.audio._require_passed_role_quality',side_effect=lambda value:value),patch('app.api.audio.ensure_record_provider_available'),patch('app.api.audio.run_record_generation_task') as run,patch('app.api.audio.create_asr_engine') as asr:
        response=client.post(f"/api/audio/existing-audio/generate-record?encounter_id={encounter['id']}")
        assert response.status_code == 200,response.text
        assert get_encounter(encounter['id'])['task_id'] == response.json()['task_id'] != old
        assert run.call_count == 1 and asr.call_count == 0
        assert get_task(old)['status'] == 'FAILED'


def test_concurrent_replacements_cannot_both_bind(failed_encounter):
    from concurrent.futures import ThreadPoolExecutor
    _,encounter,old=failed_encounter
    tasks=[create_task(input_type='text',status='CREATED',current_stage='created',input_text='患者：发热。') for _ in range(2)]
    def bind(task):
        try:
            bind_task_to_encounter(task,encounter['id'],owner_user_id=encounter['doctor_user_id'],allow_failed_replacement=True)
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(bind,tasks)) == [False,True]
    assert get_task(old)['status'] == 'FAILED'
