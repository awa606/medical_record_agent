from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
from unittest.mock import patch

import pytest

from app.services.llm.base import LLMProviderUnavailableError
from app.services.llm.deepseek_provider import BudgetLedger, DeepSeekDemoProvider, MODEL, SpikeError
from app.services.llm.factory import create_llm_provider, create_llm_record_generator, get_llm_status
from app.services.llm.online_provider import OnlineLLMProvider


@contextmanager
def server(*, status=200, redirect=None, models=None, content='{}'):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def reply(self, payload):
            self.send_response(status)
            if redirect:
                self.send_header('Location', redirect)
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode())

        def do_GET(self):
            calls.append(('GET', self.path))
            self.reply({'data': [{'id': name} for name in (models if models is not None else [MODEL])]})

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(('POST', self.path, body))
            self.reply({'id': 'local', 'model': MODEL, 'choices': [{'finish_reason': 'stop', 'message': {'content': content}}],
                        'usage': {'prompt_tokens': 100, 'completion_tokens': 100}})

        def log_message(self, *args):
            pass

    httpd = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f'http://127.0.0.1:{httpd.server_port}/chat/completions', calls
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


def configured_env(tmp_path):
    key_file = tmp_path / 'private.env'
    key_file.write_text('ONLINE_LLM_API_KEY=not-real-test-credential\n', encoding='utf-8')
    return {'LLM_PROVIDER': 'online', 'RECORD_PROVIDER_MODE': 'live', 'ONLINE_LLM_PROFILE': 'deepseek_demo',
            'MRA_ANONYMIZE': '1',
            'ONLINE_LLM_MODEL': MODEL, 'ONLINE_LLM_API_BASE': 'https://api.deepseek.com',
            'ONLINE_LLM_API_KEY_FILE': str(key_file), 'ONLINE_LLM_API_KEY': '',
            'ONLINE_LLM_BUDGET_LEDGER': str(tmp_path / 'ledger.json'),
            'ONLINE_LLM_DIAGNOSTICS_DIR': str(tmp_path / 'diagnostics')}


def make_local(tmp_path, endpoint):
    return DeepSeekDemoProvider(api_key='not-real-test-credential', output=tmp_path / 'diagnostics',
        ledger=BudgetLedger(tmp_path / 'ledger.json'), endpoint=endpoint, local_test=True)


def test_profile_factory_and_absolute_private_configuration(tmp_path):
    with patch.dict(os.environ, configured_env(tmp_path)):
        provider = create_llm_provider()
        assert isinstance(provider, DeepSeekDemoProvider)
        assert provider.ledger.path == tmp_path / 'ledger.json'
        assert get_llm_status(check_reachable=False)['configured']
        assert not (tmp_path / 'ledger.json').exists()


def test_profile_accepts_explicit_env_key_when_file_not_configured(tmp_path):
    env = configured_env(tmp_path)
    env.update(ONLINE_LLM_API_KEY_FILE='', ONLINE_LLM_API_KEY='not-real-env-credential')
    with patch.dict(os.environ, env):
        assert isinstance(create_llm_provider(), DeepSeekDemoProvider)


@pytest.mark.parametrize('setting,value', [
    ('ONLINE_LLM_BUDGET_LEDGER', 'relative.json'),
    ('ONLINE_LLM_DIAGNOSTICS_DIR', 'relative'),
    ('ONLINE_LLM_API_KEY_FILE', 'relative.env'),
    ('ONLINE_LLM_API_BASE', 'https://untrusted.example'),
    ('ONLINE_LLM_MODEL', 'another-model'),
])
def test_explicit_invalid_profile_never_falls_back_to_mock(tmp_path, setting, value):
    env = configured_env(tmp_path)
    env.update(RECORD_PROVIDER_MODE='demo')
    env[setting] = value
    with patch.dict(os.environ, env):
        with pytest.raises(LLMProviderUnavailableError):
            create_llm_record_generator()


def test_legacy_online_and_edge_policy_are_unchanged(tmp_path):
    env = configured_env(tmp_path)
    env.update(ONLINE_LLM_PROFILE='', ONLINE_LLM_API_KEY='test-legacy-key')
    with patch.dict(os.environ, env):
        assert isinstance(create_llm_provider(), OnlineLLMProvider)
    with patch.dict(os.environ, configured_env(tmp_path)):
        with pytest.raises(LLMProviderUnavailableError, match='Edge mode'):
            create_llm_provider(mode='edge')


def test_probe_uses_only_get_models_with_no_budget_or_diagnostic_write(tmp_path):
    with server() as (url, calls):
        provider = make_local(tmp_path, url)
        result = provider.probe(timeout_seconds=30)
    assert result == {'reachable': True, 'model': MODEL, 'models': [MODEL], 'error_code': None, 'inference_called': False}
    assert calls == [('GET', '/models')]
    assert not (tmp_path / 'ledger.json').exists()
    assert not (tmp_path / 'diagnostics').exists()


@pytest.mark.parametrize('status,redirect,models,error_code', [
    (401, None, None, 'HTTP_401'),
    (307, 'https://untrusted.example', None, 'HTTP_REDIRECT_REJECTED'),
    (200, None, ['other-model'], 'MODEL_NOT_LISTED'),
])
def test_failed_probe_returns_safe_code_no_error_body(tmp_path, status, redirect, models, error_code):
    with server(status=status, redirect=redirect, models=models) as (url, calls):
        result = make_local(tmp_path, url).probe()
    assert not result['reachable'] and result['error_code'] == error_code
    assert not result['inference_called'] and len(calls) == 1
    assert 'credential' not in json.dumps(result)
    assert not (tmp_path / 'ledger.json').exists()


def test_status_endpoint_uses_free_probe_not_generation(tmp_path):
    with server() as (url, calls), patch.dict(os.environ, configured_env(tmp_path)):
        provider = make_local(tmp_path, url)
        with patch.object(DeepSeekDemoProvider, 'from_environment', return_value=provider):
            status = get_llm_status(check_reachable=True)
    assert status['reachable'] and status['probe_inference_called'] is False
    assert calls == [('GET', '/models')]


def test_reused_provider_allows_separate_business_calls_with_distinct_diagnostics(tmp_path):
    with server() as (url, calls), patch.dict(os.environ, {'MRA_ANONYMIZE': '1', 'MEDICAL_RECORD_AGENT_DB': str(tmp_path / 'identity.sqlite3')}):
        provider = make_local(tmp_path, url)
        provider.generate_fields_json('发热两天', timeout_seconds=1)
        provider.generate_fields_json('咳嗽两天', timeout_seconds=1)
    assert len(calls) == 2
    assert len(list((tmp_path / 'diagnostics').glob('*/raw_response.json'))) == 2
    ledger = json.loads((tmp_path / 'ledger.json').read_text())
    assert len(ledger['calls']) == 2
    assert sum(row['charged_micro_cny'] for row in ledger['calls']) == 2000


def test_factory_zero_retry_overrides_legacy_five_retries_and_forbids_mock(tmp_path):
    env = configured_env(tmp_path)
    env.update(LLM_MAX_RETRIES='5', RECORD_PROVIDER_MODE='demo', MRA_ANONYMIZE='1',
               MEDICAL_RECORD_AGENT_DB=str(tmp_path / 'identity.sqlite3'))
    with server(content='malformed') as (url, calls), patch.dict(os.environ, env):
        provider = make_local(tmp_path, url)
        with patch.object(DeepSeekDemoProvider, 'from_environment', return_value=provider):
            generator = create_llm_record_generator()
            assert generator.max_retries == 0 and not generator.allow_mock_fallback
            with pytest.raises(LLMProviderUnavailableError):
                generator.extract_fields('发热两天')
    assert len(calls) == 1 and generator.attempt_count == 1


def test_profile_typo_never_silently_selects_unbudgeted_legacy_provider(tmp_path):
    env = configured_env(tmp_path)
    env.update(ONLINE_LLM_PROFILE='private-value-must-not-be-echoed', RECORD_PROVIDER_MODE='demo')
    with patch.dict(os.environ, env):
        with pytest.raises(LLMProviderUnavailableError, match='^Unsupported ONLINE_LLM_PROFILE$'):
            create_llm_record_generator()
        status = get_llm_status(check_reachable=False)
    assert not status['configured'] and not status['fallback_allowed']
    assert 'private-value-must-not-be-echoed' not in json.dumps(status)


def test_unreadable_key_file_does_not_expose_path_in_status(tmp_path):
    env = configured_env(tmp_path)
    env['ONLINE_LLM_API_KEY_FILE'] = str(tmp_path / 'secret-directory-name' / 'missing.env')
    with patch.dict(os.environ, env):
        status = get_llm_status(check_reachable=False)
    assert 'DEEPSEEK_KEY_FILE_UNREADABLE' in status['fallback_reason']
    assert 'secret-directory-name' not in json.dumps(status)


def test_model_probe_never_echoes_key_even_if_server_lists_it(tmp_path):
    with server(models=[MODEL, 'not-real-test-credential']) as (url, _):
        result = make_local(tmp_path, url).probe()
    assert result['models'] == [MODEL]
    assert 'not-real-test-credential' not in json.dumps(result)


def test_anonymization_off_refuses_profile_and_request_before_network(tmp_path):
    env = configured_env(tmp_path)
    env['MRA_ANONYMIZE'] = '0'
    with patch.dict(os.environ, env), server() as (url, calls):
        with pytest.raises(LLMProviderUnavailableError, match='DEEPSEEK_ANONYMIZATION_REQUIRED'):
            create_llm_record_generator()
        with pytest.raises(SpikeError, match='DEEPSEEK_ANONYMIZATION_REQUIRED'):
            make_local(tmp_path, url).generate_fields_json('发热两天', timeout_seconds=1)
    assert calls == [] and not (tmp_path / 'ledger.json').exists()


def test_recognized_name_and_phone_are_removed_before_request(tmp_path):
    with patch.dict(os.environ, {'MRA_ANONYMIZE': '1', 'MEDICAL_RECORD_AGENT_DB': str(tmp_path / 'private.sqlite3')}), server() as (url, calls):
        make_local(tmp_path, url).generate_fields_json('我叫张示例，联系方式13800138000，发热两天。', timeout_seconds=1)
    outgoing = calls[0][2]['messages'][1]['content']
    assert '张示例' not in outgoing and '13800138000' not in outgoing
    assert '发热两天' in outgoing
