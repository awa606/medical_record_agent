"""Exercise a real local service without changing formal project status.

Automated review actions verify the approval protocol, not clinical sign-off.
Audio replay is explicitly different from physical microphone acceptance.
"""
from __future__ import annotations
import argparse
import hashlib
import http.cookiejar
import json
import os
from pathlib import Path
import time
from urllib import request, error

KEYS = ('chief_complaint','present_illness','previous_treatment','accompanying_symptoms','past_history','allergy_history','physical_exam')


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--base-url',default='http://127.0.0.1:2780')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--mode',choices=['privacy','audio'],required=True)
    parser.add_argument('--audio',type=Path)
    parser.add_argument('--count',type=int,default=5)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit('Refusing to overwrite results')
    args.output.mkdir(parents=True)
    opener=request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(method,path,data=None,*,body=None,content_type='application/json'):
        payload=json.dumps(data,ensure_ascii=False).encode() if data is not None else body
        req=request.Request(args.base_url+path,method=method,data=payload,headers={'Content-Type':content_type})
        try:
            with opener.open(req,timeout=600) as response:code,raw=response.status,response.read()
        except error.HTTPError as exc:code,raw=exc.code,exc.read()
        try:return code,json.loads(raw)
        except ValueError:return code,raw.decode('utf-8',errors='replace')
    code,_=call('POST','/api/auth/login',{'username':'admin','password':os.environ['MRA_LOOP_ADMIN_PASSWORD']})
    if code!=200:raise SystemExit(f'Local test login failed: HTTP {code}')
    report={'mode':args.mode,'review_actor':'authenticated local test admin; automated protocol test, not a physician sign-off',
            'input_method':'uploaded prerecorded course audio' if args.mode=='audio' else 'synthetic identity text',
            'physical_microphone_verified':False,'cases':[]}
    def save():
        (args.output/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if args.mode=='audio':
        code,ready=call('GET','/ready')
        report['readiness_before']=ready
        if code!=200:
            report['blocked']='Selected local models are not ready; retry into a new output directory after warmup.'
            save();raise SystemExit(report['blocked'])
    for number in range(args.count):
        start=time.perf_counter()
        row={'run':number+1,'success':False}
        try:
            forbidden=[]
            if args.mode=='privacy':
                name=['王小明','李小华','张晓红','赵文静','陈子安'][number%5]
                phone=f'1380013{number:04d}'
                identity=f'11010119900101{number:03d}X'
                forbidden=[name,phone,identity]
                text=f'患者：姓名：{name}，电话{phone}，身份证{identity}。患者：发热3天，体温39℃。'
                row['input_sha256']=hashlib.sha256(text.encode()).hexdigest()
                code,created=call('POST','/api/records/generate',{'conversation_text':text})
            else:
                if not args.audio:raise ValueError('--audio required')
                raw=args.audio.read_bytes();boundary='MRAReplayBoundary20260914'
                row.update({'audio_sha256':hashlib.sha256(raw).hexdigest(),'repeated_sample':number>0})
                body=(f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{args.audio.name}"\r\nContent-Type: audio/wav\r\n\r\n'.encode()+raw+f'\r\n--{boundary}--\r\n'.encode())
                code,uploaded=call('POST','/api/audio/upload',body=body,content_type=f'multipart/form-data; boundary={boundary}')
                assert code==200, f'upload HTTP {code}'
                audio_id=uploaded['audio_id'];row['audio_id']=audio_id
                code,transcribed=call('POST',f'/api/audio/{audio_id}/transcribe?engine=funasr')
                row['asr_http']=code
                if code!=200:raise RuntimeError(f'ASR HTTP {code}: {str(transcribed)[:300]}')
                row['asr_seconds']=transcribed.get('processing_duration_seconds')
                row['asr_engine']=transcribed.get('model')
                row['role_quality']=transcribed.get('asr_result',{}).get('role_quality')
                (args.output/f'asr-{number+1:02d}.json').write_text(json.dumps(transcribed,ensure_ascii=False,indent=2),encoding='utf-8')
                code,created=call('POST',f'/api/audio/{audio_id}/generate-record')
            row['generation_http']=code
            if code!=200:raise RuntimeError(f'generation HTTP {code}: {str(created)[:300]}')
            task_id=created['task_id'];row['task_id']=task_id
            generated_start=time.perf_counter()
            while time.perf_counter()-generated_start<600:
                _,task=call('GET',f'/api/tasks/{task_id}')
                if task['status'] in {'WAITING_DOCTOR_REVIEW','FAILED'}:break
                time.sleep(.5)
            row['generation_seconds']=round(time.perf_counter()-generated_start,3)
            if task['status']!='WAITING_DOCTOR_REVIEW':raise RuntimeError(f'task status {task["status"]}')
            fields=task['result_json']['fields'];trace=task['result_json'].get('llm_trace',{})
            row['trace']=trace
            assert not trace.get('fallback') and trace.get('llm_provider')=='ollama'
            row['nonempty_fields']=sum(bool(fields[k].get('value')) and not fields[k]['missing'] for k in KEYS)
            row['conflicting_fields']=[k for k in KEYS if fields[k]['status']=='conflicting']
            # Keep conflicts visible; never delete fields to manufacture a successful export.
            row['unapproved_export_http']=call('POST',f'/api/tasks/{task_id}/export')[0]
            assert row['unapproved_export_http']!=200
            _,revision=call('GET',f'/api/tasks/{task_id}/export-readiness')
            if row['conflicting_fields']:raise RuntimeError('Evidence conflicts require clinician correction')
            code,reviewed=call('POST',f'/api/tasks/{task_id}/review',{'fields':fields,
                'expected_revision_id':revision['revision_id'],'expected_content_hash':revision['content_hash']})
            assert code==200, f'review HTTP {code}'
            _,latest=call('GET',f'/api/tasks/{task_id}/export-readiness')
            payload={'revision_id':latest['revision_id'],'content_hash':latest['content_hash'],
                     'confirm_all_regular_fields':True,'fields':[{'key':k,'action':'accept_missing','note':'自动化协议测试；非临床签字'} for k in KEYS if fields[k]['missing'] or not fields[k].get('value')],
                     'diagnoses':[{'index':i,'action':'delete_ai_candidate'} for i in range(len(fields.get('candidate_diagnoses',[])))]}
            stale={**payload,'revision_id':revision['revision_id'],'content_hash':revision['content_hash']}
            row['stale_approval_http']=call('POST',f'/api/tasks/{task_id}/approve',stale)[0]
            assert row['stale_approval_http']==409
            code,approved=call('POST',f'/api/tasks/{task_id}/approve',payload)
            row['approval_http']=code
            assert code==200, f'approval HTTP {code}: {str(approved)[:300]}'
            row['duplicate_approval_http']=call('POST',f'/api/tasks/{task_id}/approve',payload)[0]
            assert row['duplicate_approval_http']==409
            code,exported=call('POST',f'/api/tasks/{task_id}/export')
            row['export_http']=code
            assert code==200, f'export HTTP {code}'
            code,markdown=call('GET',f'/api/tasks/{task_id}/exports/markdown')
            assert code==200
            _,steps=call('GET',f'/api/tasks/{task_id}/steps')
            surfaces=json.dumps([task,reviewed,approved,exported,steps],ensure_ascii=False)+str(markdown)
            row['identity_leaks']=sum(item in surfaces for item in forbidden)
            assert row['identity_leaks']==0
            row['export_sha256']=hashlib.sha256(str(markdown).encode()).hexdigest()
            (args.output/f'run-{number+1:02d}.json').write_text(json.dumps({'task':task,'approved':approved,'steps':steps},ensure_ascii=False,indent=2),encoding='utf-8')
            # Editing must revoke the old approval even when only a review note changes.
            fields['chief_complaint']['hint']='自动化复核备注：仍以转写证据为准'
            _,latest=call('GET',f'/api/tasks/{task_id}/export-readiness')
            code,_=call('POST',f'/api/tasks/{task_id}/review',{'fields':fields,'expected_revision_id':latest['revision_id'],'expected_content_hash':latest['content_hash']})
            assert code==200
            row['export_after_edit_http']=call('POST',f'/api/tasks/{task_id}/export')[0]
            assert row['export_after_edit_http']!=200
            row['success']=True
        except Exception as exc:
            row['error']=str(exc)[:400]
        row['total_seconds']=round(time.perf_counter()-start,3)
        report['cases'].append(row);save()
        print(json.dumps({k:row.get(k) for k in ('run','success','error','generation_seconds','asr_seconds','total_seconds')}),flush=True)
    report['summary']={'passed':sum(r['success'] for r in report['cases']),'total':len(report['cases']),
        'mock_fallbacks':sum(bool(r.get('trace',{}).get('fallback')) for r in report['cases']),
        'note':'Protocol test evidence only. No formal task, physician confirmation, or Alpha gate is changed.'}
    save();print(json.dumps(report['summary']),flush=True)


if __name__=='__main__':main()
