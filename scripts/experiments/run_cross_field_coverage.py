"""Single-variable research spike; never imported by a production provider.

One added contract paragraph, unchanged catalog/schema/mapper/options/scorer.
Preserves every first response; no correction, retry or deployment.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time

from scripts.experiments.clinical_fact_selection import catalog, map_selection, selection_prompt, selection_schema
from scripts.experiments.run_clinical_fact_selection import OPTIONS, EXPECTED, remote, pipeline, score, write, sha, DIGEST

COVERAGE_CONTRACT = (
    "字段分别独立覆盖事实，不是把事实分配到互斥的栏目。"
    "同一事实ID可以同时出现在多个allowed_fields允许的字段中。"
    "已经选入主诉或伴随症状的本次症状和时长，仍须同时选入现病史；"
    "现病史独立完整覆盖本次症状、时长、体温及相关阴性信息。"
    "这不允许选择家属自身事实、未回答的问题或不属于当前字段的事实。\n"
)


def run(archive: Path, output: Path, container: str, cases: list[str]) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    os.environ['MEDICAL_RECORD_AGENT_DB'] = str(output / 'isolated-identity.sqlite3')
    model = next(m for m in remote(container, '/api/tags')['models'] if m['name'] == 'qwen3:4b')
    if model['digest'] != DIGEST:
        raise RuntimeError('MODEL_DIGEST_CHANGED')
    sources = {key: json.loads((archive / f'{key}-candidate-r1.private.json').read_text(encoding='utf8'))['stages']['attempts'][0]['input'] for key in cases}
    # Original request catalog is authoritative if generator anonymization ever changed.
    for key in cases:
        original = json.loads((archive / f'{key}-candidate-r1.private.json').read_text(encoding='utf8'))
        _, units = catalog(sources[key])
        if original['request']['messages'][0]['content'] != selection_prompt(units):
            raise RuntimeError('BASE_CONTRACT_DRIFT:' + key)
    protocol = {'started_at': datetime.now(timezone.utc).isoformat(), 'cases': cases, 'repeats': 3,
        'single_variable': COVERAGE_CONTRACT, 'options': OPTIONS, 'think': False,
        'model_digest': DIGEST, 'automatic_retries': 0, 'manual_corrections': 0,
        'expected': {key: EXPECTED[key] for key in cases}, 'source_hashes': {key: hashlib.sha256(source.encode()).hexdigest() for key, source in sources.items()},
        'source_file_hashes': {str(p): sha(p) for p in [Path(__file__), Path('scripts/experiments/clinical_fact_selection.py'), Path('scripts/experiments/run_clinical_fact_selection.py')]},
        'stop': 'Run exactly three first outputs per registered case. Any failed case rejects expansion; no retry or production promotion.'}
    write(output / 'protocol.json', protocol)
    results = []
    for key, source in sources.items():
        _, units = catalog(source)
        for repeat in range(1, 4):
            payload = {'model': 'qwen3:4b', 'stream': False, 'think': False, 'options': OPTIONS, 'keep_alive': '30m',
                'format': selection_schema(units), 'messages': [{'role': 'user', 'content': COVERAGE_CONTRACT + selection_prompt(units)}]}
            item = {'case': key, 'repeat': repeat, 'request': payload, 'catalog': [asdict(u) for u in units]}
            started = time.monotonic()
            try:
                raw = remote(container, '/api/chat', payload)
                item['raw_ollama'] = raw
                if raw.get('done_reason') == 'length':
                    raise ValueError('OUTPUT_TRUNCATED')
                selection = json.loads(raw['message']['content'])
                item['selection'] = selection
                mapped = map_selection(selection, units)
                item['mapped'] = mapped.model_dump(mode='json')
                item['first_score'] = score(key, source, mapped)
                fields, stages = pipeline(item['mapped'], source)
                item['stages'] = stages
                item['final_score'] = score(key, source, fields)
                item['passed'] = item['first_score']['passed'] and item['final_score']['passed']
            except Exception as exc:
                item.update(passed=False, error=f'{type(exc).__name__}: {exc}')
            item['seconds'] = round(time.monotonic() - started, 3)
            path = output / f'{key}-r{repeat}.private.json'
            write(path, item)
            summary = {k: item.get(k) for k in ('case', 'repeat', 'passed', 'seconds', 'first_score', 'final_score', 'error')}
            summary['raw_sha256'] = sha(path)
            results.append(summary)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
            write(output / 'results.json', results)
    report = {'calls': len(results), 'passed': sum(r['passed'] for r in results), 'results': results,
        'gate': 'SPIKE_PASS_NOT_DEPLOYABLE' if all(r['passed'] for r in results) else 'REJECTED',
        'production_changed': False}
    write(output / 'report.json', report)
    return report


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--archive', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--container', default='mra51usage8798-app-1')
    p.add_argument('--cases', nargs='+', choices=tuple(EXPECTED), default=['I01'])
    args = p.parse_args()
    report = run(args.archive, args.output, args.container, args.cases)
    print(json.dumps({k: v for k, v in report.items() if k != 'results'}, ensure_ascii=False))
