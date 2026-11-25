"""Local, temporary paired usability study, served from the verified r4.5 Windows distribution."""
import argparse
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import tempfile
import threading
import time
import webbrowser
import zipfile

import requests
import uvicorn
from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse

HERE = Path(__file__).resolve().parent
PACKAGE = HERE.parents[2] / '软件/中文冲突提示试用/MediListen_字段审核_Windows-x64_a2f6c31_r4.5.zip'
PACKAGE_SHA = 'f77967711c459cfec818bc71176f64d52cef3cdcb84a43f2b2133b3680c240d6'
FIXTURES = {
    'synthetic-visits.json': '81f63b9047741abcdf8ee78d412afb37334d55ec434d6b6ba6311973b59825d5',
    'import.json': 'ac177b962651633e87195f1b8cfb6c11373ad908d47dd53d12dfb407e8192502',
    'placement.js': '35325ffd6ddb62260512afb98c125c89b0b391bcc1a094c16c8ee69d0f5e51a0',
}


def verified(path, expected):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f'文件指纹与试验登记不符：{path.name}')
    return data


def prepare(root, identity, package):
    for name in list(os.environ):
        if name.startswith(('MRA_', 'MEDICAL_RECORD_AGENT_', 'ASR_', 'LLM_', 'ONLINE_LLM_', 'OLLAMA_', 'DEEPSEEK_')):
            del os.environ[name]
    os.environ.update(MEDICAL_RECORD_AGENT_DB=str(root / 'trial.sqlite3'),
                      MEDICAL_RECORD_AGENT_OUTPUT_DIR=str(root / 'output'),
                      MEDICAL_RECORD_AGENT_UPLOAD_DIR=str(root / 'upload'),
                      MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR=str(root / 'speakers'),
                      MRA_IDENTITY_MAP_PATH=str(root / 'identity.sqlite3'),
                      MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME='trial-maintainer',
                      MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD=identity['secret'],
                      MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME=identity['cookie'],
                      RECORD_PROVIDER_MODE='demo', LLM_PROVIDER='mock', ASR_PREWARM_ENABLED='0',
                      HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1')
    with zipfile.ZipFile(io.BytesIO(verified(package, PACKAGE_SHA))) as outer:
        name, = [n for n in outer.namelist() if n.endswith('/固定素材/修订工作台.zip')]
        with zipfile.ZipFile(io.BytesIO(outer.read(name))) as source:
            source.extractall(root)
    static = root / 'static'
    page = (static / 'doctor.html').read_bytes()
    if page.count(b'</body>') != 1:
        raise RuntimeError('试验装配的医生页面结构不符')
    probe = verified(HERE / 'placement.js', FIXTURES['placement.js'])
    common = (HERE / 'open-case.js').read_bytes()
    for mode in ('A', 'D'):
        script = b'(' + probe + b')("' + mode.encode() + b'");\n' + common
        (static / ('trial-' + mode + '.js')).write_bytes(script)
        page_part = b'<script src="./trial-' + mode.encode() + b'.js"></script>'
        (static / ('trial-' + mode + '.html')).write_bytes(page.replace(b'</body>', page_part + b'</body>'))


def seed(origin, identity):
    with requests.Session() as client:
        client.trust_env = False
        def post(path, payload=None):
            response = client.post(origin + path, json=payload, timeout=15)
            response.raise_for_status()
            return response.json()

        def get(path):
            response = client.get(origin + path, timeout=8)
            response.raise_for_status()
            return response.json()

        post('/api/auth/login', {'username':'trial-maintainer','password':identity['secret']})
        password = secrets.token_urlsafe(24)
        post('/api/auth/users', {'username':'trial-doctor','password':password,'role':'doctor','display_name':'合成资料评阅'})
        doc = json.loads(verified(HERE / 'import.json', FIXTURES['import.json']))
        second = {**doc, 'source_id':'synthetic-visual-layout-2',
                  'title':'合成课堂门诊资料核对用的长标题 · 初诊与复诊来源核验方式和字段记录补充说明 · 同一患者历次就诊中的当次与旧版引用',
                  'publisher':'合成教学资料','source_url':'https://example.invalid/only-layout','version':'合成摆位试验v1',
                  'usage_scope':'仅供本轮布局测量。','filename':'layout-only.md',
                  'content':'## 合成课堂书写字段核对\n主诉、现病史、既往史、过敏史、医生处理意见、辅助检查均须区分病历字段与问诊原文。初诊、复诊及当前就诊时间按记录登记。'*3}
        for document in (doc, second):
            docid = post('/api/knowledge/admin/import',document)['document_id']
            post('/api/knowledge/admin/documents/' + docid + '/enable')
        client.cookies.clear()
        post('/api/auth/login', {'username':'trial-doctor','password':password})
        assert get('/api/auth/me')['role'] == 'doctor'
        visits = json.loads(verified(HERE / 'synthetic-visits.json', FIXTURES['synthetic-visits.json']))['就诊']
        rows = visits[1]['问诊']
        cases = []
        for suffix, old_side in (('甲','左'),('乙','右')):
            def side(text):
                return text if suffix=='甲' else text.translate(str.maketrans('左右','右左'))
            transcript = '\n'.join(speaker+'：'+side(text) for _,speaker,text in rows)
            eid = post('/api/encounters', {'patient_deidentified_id':'SYN-TRIAL-'+suffix,
                                           'patient_display_name':'合成复诊'+suffix})['id']
            post(f'/api/encounters/{eid}/check-in')
            task = post('/api/records/generate', {'encounter_id':eid,'conversation_text':transcript})['task_id']
            for _ in range(120):
                record = get(f'/api/tasks/{task}')
                if record.get('current_record_revision_id'):
                    break
                time.sleep(.25)
            else:
                raise RuntimeError('合成草稿未就绪，请重新双击开始')
            def review(fields, chosen):
                ready = get(f'/api/tasks/{task}/export-readiness')
                return post(f'/api/tasks/{task}/review', {'fields':fields,'expected_revision_id':ready['revision_id'],
                            'expected_content_hash':ready['content_hash'],'source_corrected_fields':chosen})['result_json']['fields']
            fields = copy.deepcopy(record['result_json']['fields'])
            sentences = [x.strip() for x in re.split(r'[。！？!?\n]+',transcript) if x.strip()]
            for key, row in [('chief_complaint',1),('past_history',4)]:
                quote = side(rows[row][2])
                index = next(i for i, text in enumerate(sentences) if text.endswith(quote.rstrip('。！？!?')))
                fields[key].update(value=quote, missing=False,status='complete',source_spans=[{'text':quote,'index':index}],fact_ids=[],missing_elements=[])
            fields = review(fields,['chief_complaint','past_history'])
            fields['past_history']['value']='医生整理的既往'+old_side+'肩旧片。'
            fields = review(fields,[])
            assert fields['past_history']['source_spans'] and fields['past_history']['doctor_review_note'].startswith('manual_doctor_edit_v1')
            cases.append({'id':eid,'case':suffix})
        return client.cookies[identity['cookie']], cases


def run(no_browser, package):
    previous = Path.cwd()
    with tempfile.TemporaryDirectory(prefix='MediListen-AD-') as temporary, socket.socket() as listener:
        root = Path(temporary)
        identity = {'secret':secrets.token_urlsafe(26),'cookie':'mra_ab_'+secrets.token_hex(6)}
        key = secrets.token_urlsafe(24)
        prepare(root,identity,package)
        os.chdir(root)
        original_connect = socket.socket.connect
        def loopback_only(sock, address):
            if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):
                raise OSError('本合成试用仅允许本机回环连接')
            return original_connect(sock,address)
        socket.socket.connect = loopback_only
        sys.path.insert(0,str(root))
        from app.main import app
        listener.bind(('127.0.0.1',0))
        origin='http://127.0.0.1:'+str(listener.getsockname()[1])
        board_url=origin+'/study/'+key
        instance = {}
        server=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',log_level='error',access_log=False))
        @app.middleware('http')
        async def read_only(request: Request, call_next):
            if instance and request.url.path.startswith('/api/') and request.method not in ('GET','HEAD','OPTIONS'):
                if not (request.method=='POST' and request.url.path=='/api/knowledge/retrieve'):
                    return PlainTextResponse('本轮仅供阅读合成记录。',status_code=403)
            return await call_next(request)

        @app.get('/study/{token}',include_in_schema=False)
        def board(token: str):
            if token!=key or not instance:
                raise HTTPException(404)
            rows = instance['rounds']
            body = (HERE/'rounds.html').read_text(encoding='utf-8').replace('STUDY_ROWS',json.dumps(rows,ensure_ascii=False))
            response = HTMLResponse(body,headers={'Cache-Control':'no-store','Referrer-Policy':'same-origin'})
            response.set_cookie(identity['cookie'],instance['doctor'],httponly=True,samesite='strict')
            return response

        @app.post('/study/{token}/stop',include_in_schema=False)
        def stop(token: str,request:Request):
            if token!=key or request.cookies.get(identity['cookie']) != instance.get('doctor') or request.headers.get('origin') != origin:
                raise HTTPException(403)
            server.should_exit=True
            return HTMLResponse('<meta charset=utf-8><p>本次合成试用已结束。可以关闭页面。</p>')

        thread=threading.Thread(target=server.run,kwargs={'sockets':[listener]},daemon=True)
        thread.start()
        try:
            for _ in range(80):
                if server.started:break
                time.sleep(.15)
            else:raise RuntimeError('本机合成服务启动失败')
            doctor, cases=seed(origin,identity)
            order=['A','D']
            randomizer=secrets.SystemRandom()
            randomizer.shuffle(order)
            randomizer.shuffle(cases)
            rows=[{**case,'variant':mode} for case,mode in zip(cases,order)]
            for number, mode in enumerate(order,1):
                (root/'static'/f'round-{number}.html').write_bytes((root/'static'/f'trial-{mode}.html').read_bytes())
            instance.update(doctor=doctor,rounds=rows)
            print('合成试用已就绪。请保留此窗口。两个任务完成后在任务页结束试用。',flush=True)
            print(board_url,flush=True)
            if not no_browser:
                webbrowser.open(board_url,new=2)
            while thread.is_alive():
                thread.join(.3)
        finally:
            server.should_exit=True
            thread.join(15)
            socket.socket.connect=original_connect
            os.chdir(previous)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-browser',action='store_true')
    parser.add_argument('--package',type=Path,default=PACKAGE)
    args=parser.parse_args()
    try:
        run(args.no_browser, args.package.resolve())
    except KeyboardInterrupt:
        pass
