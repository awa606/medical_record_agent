"""Recompute development ASR metrics from preserved runtime transcripts and source hashes."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
from app.services.asr.evaluator import ASREvaluator
from app.services.asr.role_strategy import load_asr_manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--truth-dir',type=Path,required=True)
    args=parser.parse_args()
    manifest=load_asr_manifest()
    runtime=json.loads((args.run_dir/'asr_runtime.json').read_text(encoding='utf-8'))
    audio={r['id']:r for r in json.loads((args.run_dir/'audio_manifest.json').read_text(encoding='utf-8'))}
    evaluator=ASREvaluator()
    rows=[]
    for row in runtime['cases']:
        path=args.run_dir/row['transcript_file']
        result=json.loads(path.read_text(encoding='utf-8'))
        text='\n'.join(r.get('text','') for r in result)
        truth=args.truth_dir/(row['id']+'.txt')
        metrics=evaluator.evaluate(audio_id=row['id'],engine=runtime['engine'],
            ground_truth_text=truth.read_text(encoding='utf-8'),recognized_text=text,
            expected_keywords=manifest[row['id']]['expected_keywords']).model_dump()
        metrics.update(audio[row['id']])
        metrics.update({'transcript_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'ground_truth_sha256':hashlib.sha256(truth.read_bytes()).hexdigest(),
            'asr_seconds':row['seconds'],'rtf':row['seconds']/audio[row['id']]['duration_seconds']})
        rows.append(metrics)
    report={'scope':'Three course recordings, development benchmark; not independent frozen T09 acceptance',
        'engine':runtime['engine'],'device':runtime['device'],'model_load_seconds':runtime['load_seconds'],
        'normalization':'ASREvaluator existing speaker-label/punctuation normalization; no new alias relaxation',
        'cases':rows,'macro_cer':sum(r['cer'] for r in rows)/len(rows),
        'macro_keyword_recall':sum(r['keyword_recall'] for r in rows)/len(rows),
        'max_rtf':max(r['rtf'] for r in rows)}
    path=args.run_dir/'asr_scores.json'
    if path.exists():raise SystemExit('Refusing to overwrite existing scores')
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ['macro_cer','macro_keyword_recall','max_rtf']}))


if __name__=='__main__':main()
