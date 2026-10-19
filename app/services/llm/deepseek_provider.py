"""Explicit opt-in DeepSeek demo profile with bounded, auditable online calls.

Production selection requires ONLINE_LLM_PROFILE=deepseek_demo. The existing
online provider remains unchanged. This module does not establish model quality.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib import error, parse, request
import uuid

from app.prompts.medical_record_prompts import MEDICAL_RECORD_SYSTEM_PROMPT
from app.services.llm.base import LLMProviderResponse
from app.services.llm.ollama_provider import extraction_schema, numbered_source
from app.services.privacy import anonymize_text, enabled as anonymization_enabled

MODEL = 'deepseek-flash'
ENDPOINT = 'https://api.deepseek.com/chat/completions'
INPUT_TOKEN_RESERVE = 32768
OUTPUT_TOKEN_LIMIT = 4096
INPUT_RATE_MICRO_CNY = 2
OUTPUT_RATE_MICRO_CNY = 8
CALL_RESERVE = INPUT_TOKEN_RESERVE * INPUT_RATE_MICRO_CNY + OUTPUT_TOKEN_LIMIT * OUTPUT_RATE_MICRO_CNY
BUDGET_MICRO_CNY = 20_000_000
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


class SpikeError(RuntimeError):
    pass


class BudgetLedger:
    """Atomic local accounting; failed/unknown requests retain their reservation."""

    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        lock = self.path.with_suffix('.lock')
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise SpikeError('BUDGET_LOCKED: another call or interrupted lock requires inspection') from None
        try:
            os.close(descriptor)
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding='utf-8'))
                if data.get('budget_micro_cny') != BUDGET_MICRO_CNY or data.get('rates') != {'input': 2, 'output': 8}:
                    raise SpikeError('BUDGET_CONFIG_MISMATCH')
                if not isinstance(data.get('calls'), list):
                    raise SpikeError('BUDGET_INVALID')
                for call in data['calls']:
                    if type(call.get('charged_micro_cny')) is not int or call['charged_micro_cny'] < 0:
                        raise SpikeError('BUDGET_INVALID')
            else:
                data = {'schema': 1, 'budget_micro_cny': BUDGET_MICRO_CNY,
                        'rates': {'input': 2, 'output': 8}, 'scope': 'this project tool only',
                        'requires_reconciliation': False, 'calls': []}
            yield data
            temporary = self.path.with_name(self.path.name + '.' + uuid.uuid4().hex + '.tmp')
            write_json(temporary, data)
            temporary.replace(self.path)
        finally:
            lock.unlink(missing_ok=True)

    def reserve(self, case_id: str) -> str:
        with self.locked() as data:
            if data.get('requires_reconciliation'):
                raise SpikeError('BUDGET_RECONCILIATION_REQUIRED')
            if sum(c['charged_micro_cny'] for c in data['calls']) + CALL_RESERVE > BUDGET_MICRO_CNY:
                raise SpikeError('BUDGET_EXHAUSTED')
            call_id = uuid.uuid4().hex
            data['calls'].append({'id': call_id, 'case_id': case_id, 'started_at': now(),
                                  'state': 'reserved', 'charged_micro_cny': CALL_RESERVE,
                                  'reserved_micro_cny': CALL_RESERVE})
        return call_id

    def finish(self, call_id: str, *, usage: dict | None, failure: str | None = None) -> None:
        with self.locked() as data:
            call = next(c for c in data['calls'] if c['id'] == call_id)
            if call['state'] != 'reserved':
                raise SpikeError('BUDGET_CALL_ALREADY_SETTLED')
            call['finished_at'] = now()
            if usage is None:
                call.update(state='failed_reservation_retained', failure=failure)
                return
            cost = usage['prompt_tokens'] * 2 + usage['completion_tokens'] * 8
            call['usage'] = usage
            if usage['prompt_tokens'] > INPUT_TOKEN_RESERVE or usage['completion_tokens'] > OUTPUT_TOKEN_LIMIT:
                call.update(state='requires_reconciliation', charged_micro_cny=max(cost, CALL_RESERVE))
                data['requires_reconciliation'] = True
                return
            call.update(state='settled', charged_micro_cny=cost)


def read_key(path: Path) -> str:
    """Read only the project-designated private file; no process-env fallback."""
    values = {}
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('\"\'')
    key = values.get('ONLINE_LLM_API_KEY', '')
    if not key or key.startswith(('YOUR_', '请填写', '<')):
        raise SpikeError('PRIVATE_KEY_NOT_CONFIGURED')
    if any(character.isspace() for character in key):
        raise SpikeError('PRIVATE_KEY_INVALID')
    base = values.get('ONLINE_LLM_API_BASE')
    if base and base.rstrip('/') not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
        raise SpikeError('PRIVATE_BASE_NOT_OFFICIAL')
    model = values.get('ONLINE_LLM_MODEL')
    if model and model != MODEL:
        raise SpikeError('PRIVATE_MODEL_MISMATCH')
    return key


class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise SpikeError('HTTP_REDIRECT_REJECTED')


class DeepSeekDemoProvider:
    name = 'online'
    model = MODEL
    diagnostics_enabled = True

    def __init__(self, *, api_key: str, output: Path, ledger: BudgetLedger,
                 case_id: str = 'business', endpoint: str = ENDPOINT, local_test: bool = False,
                 single_use: bool = False):
        url = parse.urlsplit(endpoint)
        if endpoint != ENDPOINT and not (local_test and url.scheme == 'http' and url.hostname == '127.0.0.1'):
            raise SpikeError('ENDPOINT_NOT_ALLOWED')
        self.api_key, self.output, self.ledger = api_key, output, ledger
        self.case_id, self.endpoint = case_id, endpoint
        self.diagnostics_root = output
        self.single_use = single_use
        self._call_lock = threading.Lock()
        self.response_metadata = {}
        self.last_diagnostic_response = None
        self.used = False

    @classmethod
    def from_environment(cls):
        if not anonymization_enabled():
            raise SpikeError('DEEPSEEK_ANONYMIZATION_REQUIRED')
        if os.environ.get('ONLINE_LLM_API_BASE', '').rstrip('/') not in {'https://api.deepseek.com', 'https://api.deepseek.com/v1'}:
            raise SpikeError('DEEPSEEK_OFFICIAL_BASE_REQUIRED')
        if os.environ.get('ONLINE_LLM_MODEL') != MODEL:
            raise SpikeError('DEEPSEEK_MODEL_MISMATCH')
        key_file = os.environ.get('ONLINE_LLM_API_KEY_FILE', '').strip()
        if key_file:
            path = Path(key_file)
            if not path.is_absolute():
                raise SpikeError('DEEPSEEK_KEY_FILE_MUST_BE_ABSOLUTE')
            try:
                api_key = read_key(path)
            except (OSError, UnicodeError):
                raise SpikeError('DEEPSEEK_KEY_FILE_UNREADABLE') from None
        else:
            api_key = os.environ.get('ONLINE_LLM_API_KEY', '').strip()
            if not api_key or api_key.startswith(('YOUR_', '请填写', '<')) or any(c.isspace() for c in api_key):
                raise SpikeError('DEEPSEEK_KEY_NOT_CONFIGURED')
        locations = {}
        for variable in ('ONLINE_LLM_BUDGET_LEDGER', 'ONLINE_LLM_DIAGNOSTICS_DIR'):
            value = os.environ.get(variable, '').strip()
            path = Path(value)
            if not value or not path.is_absolute():
                raise SpikeError(variable + '_MUST_BE_ABSOLUTE')
            locations[variable] = path
        return cls(api_key=api_key, output=locations['ONLINE_LLM_DIAGNOSTICS_DIR'],
                   ledger=BudgetLedger(locations['ONLINE_LLM_BUDGET_LEDGER']))

    def probe(self, *, timeout_seconds: float = 5) -> dict:
        """Authenticated model-list read; no inference or budget reservation."""
        endpoint = self.endpoint.rsplit('/chat/completions', 1)[0] + '/models'
        req = request.Request(endpoint, method='GET', headers={'Authorization': 'Bearer ' + self.api_key})
        try:
            opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
            with opener.open(req, timeout=min(5, max(0.1, timeout_seconds))) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise SpikeError('MODEL_LIST_TOO_LARGE')
            data = json.loads(raw)
            rows = data.get('data') if isinstance(data, dict) else None
            if not isinstance(rows, list):
                raise SpikeError('MODEL_LIST_INVALID')
            models = sorted({row['id'] for row in rows if isinstance(row, dict)
                and isinstance(row.get('id'), str) and self.api_key not in row['id']
                and re.fullmatch(r'[A-Za-z0-9_.:-]{1,128}', row['id'])})
            return {'reachable': MODEL in models, 'model': MODEL, 'models': models,
                    'error_code': None if MODEL in models else 'MODEL_NOT_LISTED', 'inference_called': False}
        except Exception as exc:
            code = str(exc) if isinstance(exc, SpikeError) else ('HTTP_' + str(exc.code) if isinstance(exc, error.HTTPError) else type(exc).__name__)
            return {'reachable': False, 'model': MODEL, 'models': [], 'error_code': code, 'inference_called': False}

    def save(self, name: str, value: object) -> None:
        # The API must not echo a credential into diagnostic artifacts.
        safe = json.dumps(value, ensure_ascii=False).replace(self.api_key, '[REDACTED]')
        write_json(self.output / name, json.loads(safe))

    def generate_fields_json(self, conversation_text: str, *, timeout_seconds: float) -> LLMProviderResponse:
        if self.single_use and self.used:
            raise SpikeError('AUTOMATIC_RETRY_FORBIDDEN')
        if not self._call_lock.acquire(blocking=False):
            raise SpikeError('DEEPSEEK_PROVIDER_BUSY')
        try:
            if not self.single_use:
                self.output = self.diagnostics_root / (datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S') + '-' + uuid.uuid4().hex)
            self.response_metadata = {}
            self.last_diagnostic_response = None
            return self._generate_fields_json(conversation_text, timeout_seconds=timeout_seconds)
        finally:
            self._call_lock.release()

    def _generate_fields_json(self, conversation_text: str, *, timeout_seconds: float) -> LLMProviderResponse:
        self.used = True
        if not anonymization_enabled():
            raise SpikeError('DEEPSEEK_ANONYMIZATION_REQUIRED')
        payload = {'model': MODEL, 'thinking': {'type': 'disabled'},
                   'response_format': {'type': 'json_object'}, 'temperature': 0,
                   'max_tokens': OUTPUT_TOKEN_LIMIT, 'stream': False,
                   'messages': [{'role': 'system', 'content': MEDICAL_RECORD_SYSTEM_PROMPT +
                       '\n输出 JSON 必须符合以下既有字段 Schema，不添加诊断建议：\n' + json.dumps(extraction_schema(), ensure_ascii=False)},
                       {'role': 'user', 'content': numbered_source(anonymize_text(conversation_text))}]}
        message_bytes = sum(len(m['content'].encode('utf-8')) for m in payload['messages'])
        # UTF-8 bytes plus 1024 protocol tokens is a conservative input bound;
        # unexpected server usage locks this ledger pending reconciliation.
        if message_bytes + 1024 > INPUT_TOKEN_RESERVE:
            raise SpikeError('INPUT_EXCEEDS_RESERVATION_BOUND')
        self.save('request.json', payload)
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        call_id = self.ledger.reserve(self.case_id)
        start = time.perf_counter()
        budget_settled = False
        req = request.Request(self.endpoint, data=body, method='POST', headers={
            'Authorization': 'Bearer ' + self.api_key, 'Content-Type': 'application/json'})
        try:
            opener = request.build_opener(request.ProxyHandler({}), NoRedirect())
            try:
                with opener.open(req, timeout=timeout_seconds) as response:
                    raw = response.read(MAX_RESPONSE_BYTES + 1)
            except error.HTTPError as exc:
                body = exc.read(MAX_RESPONSE_BYTES + 1)
                self.save('http_error.json', {'status': exc.code,
                    'body': body[:MAX_RESPONSE_BYTES].decode('utf-8', errors='replace'),
                    'truncated': len(body) > MAX_RESPONSE_BYTES})
                raise
            if len(raw) > MAX_RESPONSE_BYTES:
                raise SpikeError('RESPONSE_TOO_LARGE')
            self.save('raw_response_text.json', {'body': raw.decode('utf-8', errors='replace')})
            data = json.loads(raw)
            # Keep trace/status safe even if an upstream response echoes a key.
            data = json.loads(json.dumps(data, ensure_ascii=False).replace(self.api_key, '[REDACTED]'))
            self.last_diagnostic_response = data
            self.save('raw_response.json', data)
            if not isinstance(data, dict):
                raise SpikeError('RESPONSE_NOT_OBJECT')
            choices = data.get('choices')
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise SpikeError('RESPONSE_CHOICES_INVALID')
            choice = choices[0]
            self.response_metadata = {'request_id': data.get('id'), 'model': data.get('model'),
                'finish_reason': choice.get('finish_reason'), 'usage': data.get('usage'),
                'latency_ms': int((time.perf_counter() - start) * 1000), 'budget_call_id': call_id}
            if choice.get('finish_reason') != 'stop':
                raise SpikeError('RESPONSE_NOT_COMPLETE')
            message = choice.get('message')
            content = message.get('content') if isinstance(message, dict) else None
            if not isinstance(content, str) or not content.strip():
                raise SpikeError('RESPONSE_EMPTY')
            parsed_fields = json.loads(content)
            if not isinstance(parsed_fields, dict):
                raise SpikeError('FIELDS_NOT_OBJECT')
            usage = data.get('usage')
            if not isinstance(usage, dict) or any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('prompt_tokens', 'completion_tokens')):
                raise SpikeError('RESPONSE_USAGE_INVALID')
            if not isinstance(data.get('model'), str) or not data['model']:
                raise SpikeError('RESPONSE_MODEL_MISSING')
            self.save('model_first_output.json', parsed_fields)
            self.ledger.finish(call_id, usage=usage)
            budget_settled = True
            if usage['prompt_tokens'] > INPUT_TOKEN_RESERVE or usage['completion_tokens'] > OUTPUT_TOKEN_LIMIT:
                raise SpikeError('SERVER_USAGE_EXCEEDED_RESERVATION')
        except Exception as exc:
            # Do not leak exception bodies, URLs or echoed credentials.
            code = str(exc) if isinstance(exc, SpikeError) else ('HTTP_' + str(exc.code) if isinstance(exc, error.HTTPError) else type(exc).__name__)
            if not budget_settled:
                self.ledger.finish(call_id, usage=None, failure=code)
            self.save('failure.json', {'code': code, 'budget_call_id': call_id, 'auto_retry': False})
            raise SpikeError(code) from None
        finally:
            self.save('response_metadata.json', self.response_metadata)
        return LLMProviderResponse(provider=self.name, model=data['model'], content=content,
                                   latency_ms=self.response_metadata['latency_ms'])
