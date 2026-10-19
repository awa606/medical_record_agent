from contextlib import contextmanager
import json
import os
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading
from unittest.mock import patch

import pytest

from scripts.experiments.deepseek_demo_spike import (
    BUDGET_MICRO_CNY, CALL_RESERVE, INPUT_TOKEN_RESERVE, MODEL,
    BudgetLedger, DeepSeekSpikeProvider, SpikeError, read_key, run_case,
)


def fields_payload():
    absent = {'value': None, 'missing': True, 'hint': None, 'confidence': None, 'source_spans': []}
    data = {key: dict(absent) for key in ('chief_complaint', 'present_illness', 'previous_treatment',
             'accompanying_symptoms', 'past_history', 'allergy_history', 'physical_exam')}
    for key in ('chief_complaint', 'present_illness'):
        data[key] = {'value': '发热3天', 'missing': False, 'hint': None, 'confidence': 0.9,
                     'source_spans': [{'text': '发热3天', 'index': 0}]}
    data['candidate_diagnoses'] = []
    return data


def response_payload(**changes):
    data = {'id': 'fake-local-request', 'model': 'deepseek-flash-test',
            'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(fields_payload(), ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 1000, 'completion_tokens': 200, 'total_tokens': 1200}}
    data.update(changes)
    return data


@contextmanager
def fake_server(payload, status=200, redirect=None):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers['Content-Length']))
            calls.append({'path': self.path, 'body': json.loads(body), 'authorization': self.headers.get('Authorization')})
            self.send_response(status)
            if redirect:
                self.send_header('Location', redirect)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port) + '/chat/completions', calls
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


def provider_for(tmp_path, endpoint):
    return DeepSeekSpikeProvider(api_key='test-only-not-a-real-key', output=tmp_path / 'run',
        ledger=BudgetLedger(tmp_path / 'ledger.json'), case_id='TEST-01', endpoint=endpoint, local_test=True)


def ledger_calls(tmp_path):
    return json.loads((tmp_path / 'ledger.json').read_text(encoding='utf-8'))['calls']


def test_http_contract_complete_generator_and_actual_usage(tmp_path):
    with fake_server(response_payload()) as (url, calls):
        provider = provider_for(tmp_path, url)
        result = run_case(provider, '发热3天', tmp_path / 'run')
    assert len(calls) == 1
    body = calls[0]['body']
    assert body['model'] == MODEL
    assert body['thinking'] == {'type': 'disabled'}
    assert body['response_format'] == {'type': 'json_object'}
    assert body['temperature'] == 0 and body['max_tokens'] == 4096 and body['stream'] is False
    assert 'source_spans' in body['messages'][0]['content']
    assert '[0] 发热3天' in body['messages'][1]['content']
    assert calls[0]['path'] == '/chat/completions'
    assert calls[0]['authorization'] == 'Bearer test-only-not-a-real-key'
    assert result['pipeline_pass'] is True
    assert result['attempt_count'] == 1
    assert result['model_quality_pass'] is None
    assert ledger_calls(tmp_path)[0]['charged_micro_cny'] == 3600
    stages = json.loads((tmp_path / 'run' / 'stages.json').read_text(encoding='utf-8'))[0]
    assert {'raw_response', 'reconciled', 'evidence_validated', 'grounded'}.issubset(stages)
    assert json.loads((tmp_path / 'run' / 'trace.json').read_text(encoding='utf-8'))['model'] == 'deepseek-flash-test'
    for artifact in (tmp_path / 'run').glob('*.json'):
        assert 'test-only-not-a-real-key' not in artifact.read_text(encoding='utf-8')


@pytest.mark.parametrize('payload, expected', [
    (response_payload(choices=[{'finish_reason': 'length', 'message': {'content': '{}'}}]), 'RESPONSE_NOT_COMPLETE'),
    (response_payload(choices=[{'finish_reason': 'stop', 'message': {'content': ''}}]), 'RESPONSE_EMPTY'),
    (response_payload(choices=[]), 'RESPONSE_CHOICES_INVALID'),
    (response_payload(usage=None), 'RESPONSE_USAGE_INVALID'),
    (response_payload(usage={'prompt_tokens': True, 'completion_tokens': 1}), 'RESPONSE_USAGE_INVALID'),
    (response_payload(model=''), 'RESPONSE_MODEL_MISSING'),
    (response_payload(choices=[{'finish_reason': 'stop', 'message': {'content': 'broken json'}}]), 'JSONDecodeError'),
])
def test_invalid_response_is_one_call_and_reservation_retained(tmp_path, payload, expected):
    with fake_server(payload) as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热3天', tmp_path / 'run')
    assert result['pipeline_pass'] is False
    assert result['attempt_count'] == 1
    assert len(calls) == 1
    assert expected in result['error']
    assert ledger_calls(tmp_path)[0]['state'] == 'failed_reservation_retained'
    assert ledger_calls(tmp_path)[0]['charged_micro_cny'] == CALL_RESERVE


@pytest.mark.parametrize('http_status', [401, 429, 500, 503])
def test_http_failure_no_retry_or_secret_in_artifacts(tmp_path, http_status):
    with fake_server({'error': 'test-only-not-a-real-key'}, status=http_status) as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热3天', tmp_path / 'run')
    assert len(calls) == 1 and result['pipeline_pass'] is False
    assert 'HTTP_' + str(http_status) in result['error']
    assert ledger_calls(tmp_path)[0]['charged_micro_cny'] == CALL_RESERVE
    for artifact in (tmp_path / 'run').glob('*.json'):
        assert 'test-only-not-a-real-key' not in artifact.read_text(encoding='utf-8')


def test_redirect_rejected_without_following_or_refund(tmp_path):
    with fake_server({}, status=307, redirect='http://127.0.0.1:1/stolen') as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热3天', tmp_path / 'run')
    assert len(calls) == 1 and result['pipeline_pass'] is False
    assert 'HTTP_REDIRECT_REJECTED' in result['error']
    assert ledger_calls(tmp_path)[0]['charged_micro_cny'] == CALL_RESERVE


def test_over_budget_is_rejected_before_http_and_exact_20_cny(tmp_path):
    ledger = BudgetLedger(tmp_path / 'ledger.json')
    count = BUDGET_MICRO_CNY // CALL_RESERVE
    for number in range(count):
        ledger.reserve(str(number))
    with fake_server(response_payload()) as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热3天', tmp_path / 'run')
    assert len(calls) == 0 and result['pipeline_pass'] is False
    assert 'BUDGET_EXHAUSTED' in result['error']
    assert len(ledger_calls(tmp_path)) == count
    assert sum(c['charged_micro_cny'] for c in ledger_calls(tmp_path)) <= BUDGET_MICRO_CNY


def test_concurrent_or_interrupted_lock_never_starts_call(tmp_path):
    (tmp_path / 'ledger.lock').write_text('pending', encoding='utf-8')
    with pytest.raises(SpikeError, match='BUDGET_LOCKED'):
        BudgetLedger(tmp_path / 'ledger.json').reserve('blocked')


def test_reported_tokens_above_reserve_locks_future_calls(tmp_path):
    payload = response_payload(usage={'prompt_tokens': INPUT_TOKEN_RESERVE + 1, 'completion_tokens': 200})
    with fake_server(payload) as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热3天', tmp_path / 'run')
    assert len(calls) == 1 and result['pipeline_pass'] is False
    assert ledger_calls(tmp_path)[0]['state'] == 'requires_reconciliation'
    with pytest.raises(SpikeError, match='BUDGET_RECONCILIATION_REQUIRED'):
        BudgetLedger(tmp_path / 'ledger.json').reserve('must-not-run')


def test_long_input_rejected_before_http_and_budget(tmp_path):
    with fake_server(response_payload()) as (url, calls):
        result = run_case(provider_for(tmp_path, url), '发热' * 10000, tmp_path / 'run')
    assert result['pipeline_pass'] is False and calls == []
    assert 'INPUT_EXCEEDS_RESERVATION_BOUND' in result['error']
    assert not (tmp_path / 'ledger.json').exists()


def test_only_designated_private_file_no_environment_fallback(tmp_path):
    private = tmp_path / 'private.env'
    private.write_text('ONLINE_LLM_API_BASE=https://api.deepseek.com\nONLINE_LLM_MODEL=deepseek-flash\nONLINE_LLM_API_KEY=local-test-key\n', encoding='utf-8')
    with patch.dict(os.environ, {'ONLINE_LLM_API_KEY': 'wrong-environment-key'}):
        assert read_key(private) == 'local-test-key'
        private.write_text('ONLINE_LLM_API_KEY=\n', encoding='utf-8')
        with pytest.raises(SpikeError, match='PRIVATE_KEY_NOT_CONFIGURED'):
            read_key(private)


def test_foreign_endpoint_and_private_base_rejected(tmp_path):
    with pytest.raises(SpikeError, match='ENDPOINT_NOT_ALLOWED'):
        provider_for(tmp_path, 'https://not-deepseek.example/chat/completions')
    private = tmp_path / 'private.env'
    private.write_text('ONLINE_LLM_API_KEY=local-test-key\nONLINE_LLM_API_BASE=https://not-deepseek.example\n', encoding='utf-8')
    with pytest.raises(SpikeError, match='PRIVATE_BASE_NOT_OFFICIAL'):
        read_key(private)


def test_no_second_call_even_if_caller_retries(tmp_path):
    with fake_server(response_payload()) as (url, calls):
        provider = provider_for(tmp_path, url)
        run_case(provider, '发热3天', tmp_path / 'run')
        with pytest.raises(SpikeError, match='AUTOMATIC_RETRY_FORBIDDEN'):
            provider.generate_fields_json('发热3天', timeout_seconds=1)
    assert len(calls) == 1


def test_ledger_shared_between_instances_cannot_reserve_past_remaining_budget(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    ledger = BudgetLedger(tmp_path / 'ledger.json')
    for number in range(BUDGET_MICRO_CNY // CALL_RESERVE - 1):
        ledger.reserve(str(number))
    start = threading.Barrier(2)

    def reserve_one(name):
        start.wait()
        try:
            BudgetLedger(tmp_path / 'ledger.json').reserve(name)
            return True
        except SpikeError:
            return False

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(reserve_one, ('instance-a', 'instance-b')))
    assert outcomes.count(True) == 1
    assert sum(row['charged_micro_cny'] for row in ledger_calls(tmp_path)) <= BUDGET_MICRO_CNY


def test_credential_echo_is_redacted_from_metadata_and_generator_trace(tmp_path):
    payload = response_payload(id='test-only-not-a-real-key')
    with fake_server(payload) as (url, _):
        provider = provider_for(tmp_path, url)
        result = run_case(provider, '发热3天', tmp_path / 'run')
    assert result['pipeline_pass']
    assert provider.response_metadata['request_id'] == '[REDACTED]'
    assert 'test-only-not-a-real-key' not in json.dumps(provider.last_diagnostic_response)


def test_timeout_keeps_reservation_and_makes_no_automatic_retry(tmp_path):
    from app.services.llm import deepseek_provider
    with fake_server(response_payload()) as (url, calls):
        provider = provider_for(tmp_path, url)
        with patch.object(deepseek_provider.request, 'build_opener') as opener:
            opener.return_value.open.side_effect = TimeoutError('server echoed test-only-not-a-real-key')
            result = run_case(provider, '发热3天', tmp_path / 'run')
            assert opener.return_value.open.call_count == 1
    assert not result['pipeline_pass'] and 'TimeoutError' in result['error']
    assert 'test-only-not-a-real-key' not in result['error']
    assert ledger_calls(tmp_path)[0]['charged_micro_cny'] == CALL_RESERVE
    assert ledger_calls(tmp_path)[0]['state'] == 'failed_reservation_retained'
