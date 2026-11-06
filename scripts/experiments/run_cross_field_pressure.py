"""Frozen seven-case pressure checks for the cross-field research contract."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
from dataclasses import asdict
from scripts.experiments.run_cross_field_coverage import COVERAGE_CONTRACT
from scripts.experiments.clinical_fact_selection import catalog, map_selection, selection_prompt, selection_schema
from scripts.experiments.run_clinical_fact_selection import remote, OPTIONS, DIGEST, write, sha, pipeline
from scripts.experiments.run_evidence_selection import inputs
from scripts.experiments.compare_local_models import quality_checks
from app.services.field_grounding import FIELD_KEYS


def run(output: Path, container: str):
    output.mkdir(parents=True, exist_ok=False)
    os.environ['MEDICAL_RECORD_AGENT_DB'] = str(output / 'identity.sqlite3')
    tag = next(m for m in remote(container, '/api/tags')['models'] if m['name'] == 'qwen3:4b')
    assert tag['digest'] == DIGEST
    prepared = list(inputs())
    write(output / 'protocol.json', {'model_digest': DIGEST, 'options': OPTIONS, 'think': False,
        'calls': 21, 'retries': 0, 'manual_corrections': 0, 'contract': COVERAGE_CONTRACT,
        'inputs': {k: hashlib.sha256(s.encode()).hexdigest() for k,s,_,_ in prepared},
        'criterion': 'Existing quality_checks for raw mapped and final fields. Empty question/family may be safely rejected; never counted as generated draft.',
        'stop': 'Finish 21 registered first calls. Any failure rejects development/frozen expansion.'})
    results = []
    for key, source, trusted, _ in prepared:
        _, units = catalog(source)
        for repeat in range(1,4):
            payload = {'model': 'qwen3:4b', 'stream': False, 'think': False, 'options': OPTIONS, 'keep_alive': '30m',
                'format': selection_schema(units), 'messages':[{'role':'user','content':COVERAGE_CONTRACT+selection_prompt(units)}]}
            item = {'case':key,'repeat':repeat,'request':payload,'catalog':[asdict(u) for u in units]}
            started=time.monotonic()
            try:
                raw=remote(container,'/api/chat',payload)
                item['raw_ollama']=raw
                if raw.get('done_reason') == 'length': raise ValueError('OUTPUT_TRUNCATED')
                selection=json.loads(raw['message']['content'])
                mapped=map_selection(selection,units)
                item.update(selection=selection,mapped=mapped.model_dump(mode='json'),first_checks=quality_checks(key,mapped,source))
                final, stages=pipeline(item['mapped'],source)
                item['stages']=stages
                empty=not any(getattr(mapped,k).value for k in FIELD_KEYS)
                item['expected_safe_refusal']=(
                    key in {'question','family'} and empty and final is None
                    and 'LLM_NO_SUPPORTED_FACTS' in str(stages.get('error', ''))
                )
                item['final_checks']=quality_checks(key,final,source) if final else {'expected_safe_refusal':item['expected_safe_refusal']}
                item['passed']=all(item['first_checks'].values()) and all(item['final_checks'].values())
            except Exception as exc:
                item.update(passed=False,error=f'{type(exc).__name__}: {exc}')
            item['seconds']=round(time.monotonic()-started,3)
            path=output/f'{key}-r{repeat}.private.json';write(path,item)
            row={k:item.get(k) for k in ('case','repeat','seconds','passed','first_checks','final_checks','expected_safe_refusal','error')}
            row['raw_sha256']=sha(path);results.append(row)
            write(output/'results.json',results)
            print(json.dumps(row,ensure_ascii=False),flush=True)
    report={'calls':len(results),'passed':sum(r['passed'] for r in results),'gate':'PRESSURE_PASS' if all(r['passed'] for r in results) else 'REJECTED','results':results,'production_changed':False}
    write(output/'report.json',report)
    print(json.dumps({k:v for k,v in report.items() if k!='results'}))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--container',default='mra51usage8798-app-1');a=p.parse_args();run(a.output,a.container)
