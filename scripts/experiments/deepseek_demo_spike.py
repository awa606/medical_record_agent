"""Isolated, single-call DeepSeek experiment. Never used by the production factory.

Default execution is a dry-run. An explicit --execute consumes the shared local
20 CNY experiment budget. The ledger covers this tool, not other account usage.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from app.services.llm.llm_record_generator import FIELD_KEYS, LLMRecordGenerator
from app.services.privacy import anonymize_text
from app.services.llm.deepseek_provider import (
    MODEL, ENDPOINT, INPUT_TOKEN_RESERVE, OUTPUT_TOKEN_LIMIT,
    INPUT_RATE_MICRO_CNY, OUTPUT_RATE_MICRO_CNY, CALL_RESERVE,
    BUDGET_MICRO_CNY, MAX_RESPONSE_BYTES, BudgetLedger,
    DeepSeekDemoProvider, SpikeError, now, read_key as read_private_key, write_json,
)

ROOT = Path(__file__).resolve().parents[2]
ARTIFACT_ROOT = ROOT / '.artifacts' / 'online-demo-20261019'
PRIVATE_ENV = ARTIFACT_ROOT / 'private.env'


def read_key(path: Path = PRIVATE_ENV) -> str:
    return read_private_key(path)


class DeepSeekSpikeProvider(DeepSeekDemoProvider):
    """One-shot experiment wrapper around the exact production adapter."""
    def __init__(self, **kwargs):
        super().__init__(single_use=True, **kwargs)


def run_case(provider: DeepSeekSpikeProvider, text: str, output: Path) -> dict:
    """Use the unchanged production Generator and a private identity-map DB."""
    output.mkdir(parents=True, exist_ok=True)
    with patch.dict(os.environ, {'MRA_ANONYMIZE': '1',
                               'MEDICAL_RECORD_AGENT_DB': str(output / 'private-runtime' / 'spike.sqlite3')}):
        safe_text = anonymize_text(text)
        provider.save('input.json', {'case_id': provider.case_id, 'text': safe_text,
                      'sha256': hashlib.sha256(safe_text.encode('utf-8')).hexdigest()})
        generator = LLMRecordGenerator(provider=provider, requested_provider='online', requested_model=MODEL,
                                       mode='live', allow_mock_fallback=False)
        generator.max_retries = 0
        generator.timeout_seconds = 120
        generator.diagnostics_enabled = True
        report = {'case_id': provider.case_id, 'created_at': now(), 'requested_model': MODEL,
                  'research_gate': 'NEEDS MORE EVIDENCE', 'model_quality_pass': None,
                  'manual_quality_review_required': True, 'auto_retry': False}
        try:
            fields = generator.extract_fields(safe_text)
            provider.save('final_fields.json', fields.model_dump())
            report.update(pipeline_pass=True, fields={key: {'status': getattr(fields, key).status,
                           'missing': getattr(fields, key).missing} for key in FIELD_KEYS})
        except Exception as exc:
            report.update(pipeline_pass=False, error=str(exc))
        finally:
            provider.save('stages.json', generator.diagnostic_attempts)
            provider.save('trace.json', generator.get_trace())
            report['attempt_count'] = generator.attempt_count
            provider.save('report.json', report)
        return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='UTF-8 synthetic/de-identified conversation')
    parser.add_argument('--case-id', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--execute', action='store_true', help='Explicitly spend the project experiment budget')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'mode': 'dry-run', 'endpoint': ENDPOINT, 'model': MODEL,
                          'per_call_reserved_cny': CALL_RESERVE / 1_000_000, 'budget_cny': 20,
                          'key_file_exists': PRIVATE_ENV.is_file(), 'real_api_called': False}, ensure_ascii=False))
        return 0
    output = args.output.resolve()
    if not output.is_relative_to(ARTIFACT_ROOT.resolve()):
        raise SpikeError('OUTPUT_MUST_BE_IN_PRIVATE_EXPERIMENT_DIRECTORY')
    text = args.input.read_text(encoding='utf-8-sig')
    key = read_key()
    output.mkdir(parents=True, exist_ok=False)
    provider = DeepSeekSpikeProvider(api_key=key, output=output,
        ledger=BudgetLedger(ARTIFACT_ROOT / 'cost-ledger.json'), case_id=args.case_id)
    report = run_case(provider, text, output)
    print(json.dumps({'pipeline_pass': report['pipeline_pass'], 'attempt_count': report['attempt_count'],
                      'output': str(output), 'model_quality_pass': None}, ensure_ascii=False))
    return 0 if report['pipeline_pass'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(str(exc) if isinstance(exc, SpikeError) else type(exc).__name__)
        raise SystemExit(2)
