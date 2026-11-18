"""Local classroom replay service. Run through the classroom launcher."""
from pathlib import Path
import os, sys, json, hashlib, datetime, socket
HERE = Path(__file__).resolve().parent
D = HERE / '冻结资产'
SRC = D / 'source'
os.chdir(SRC)
sys.path.insert(0, str(SRC))
run = Path(os.environ['COURSE_RUNTIME'])
port = int(os.environ['COURSE_PORT'])
def h(b):return hashlib.sha256(b).hexdigest()
for path,expected in json.loads((D/'frozen-sha256.json').read_text(encoding='utf8')).items():
 if h((D/path).read_bytes())!=expected:raise SystemExit('演示资产校验失败：'+path)

for name in ('uploads','outputs','speaker-profiles','logs'): (run/name).mkdir(parents=True,exist_ok=True)
c=json.loads((run/'本机账户.json').read_text(encoding='utf8'))
for k in list(os.environ):
 if k.startswith(('ONLINE_LLM_','OLLAMA_','MEDICAL_RECORD_AGENT_','MRA_','ASR_','DEEPSEEK_')):os.environ.pop(k)
os.environ.update(MEDICAL_RECORD_AGENT_DB=str(run/'candidate.sqlite3'),MEDICAL_RECORD_AGENT_UPLOAD_DIR=str(run/'uploads'),MEDICAL_RECORD_AGENT_OUTPUT_DIR=str(run/'outputs'),MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR=str(run/'speaker-profiles'),MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME=f'medilisten_course_{port}',
 MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_USERNAME=c['admin_username'],MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD=c['admin_password'],MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_DISPLAY_NAME='本机演示维护账号',
 RECORD_PROVIDER_MODE='demo',LLM_PROVIDER='mock',LLM_MAX_RETRIES='0',ASR_ENGINE='mock',MEDICAL_RECORD_AGENT_ASR_ENGINE='mock',ASR_PREWARM_ENABLED='0',MEDICAL_RECORD_AGENT_REQUIRE_FUNASR='0',MRA_ANONYMIZE='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',MRA_IDENTITY_MAP_PATH=str(run/'synthetic-identities.sqlite3'))
# Explicitly reject non-loopback outbound network; this process never uses an external model.
connect0=socket.socket.connect
def local_connect(sock, address):
 if isinstance(address,tuple) and address[0] not in ('127.0.0.1','::1','localhost'):raise OSError('独立回放入口禁止外部网络请求')
 return connect0(sock,address)
socket.socket.connect=local_connect
replay=json.loads((D/'fixtures/input.json').read_text(encoding='utf8'))
source=replay['text'];assert h(source.encode())==replay['sha256']
def normalize(s):return s.replace('\r\n','\n').strip()
raw=json.loads(json.loads((D/'fixtures/raw_response_text.json').read_text(encoding='utf8'))['body'])
response=raw['choices'][0]['message']['content'];assert json.loads(response)==json.loads((D/'fixtures/model_first_output.json').read_text(encoding='utf8'))
from app.services.llm.base import LLMProviderResponse,LLMProviderUnavailableError
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.llm import factory
import app.services,app.services.llm
class Replay:
 name='saved-deepseek-replay'
 model='deepseek-flash / 已保存首响应（非在线）'
 def generate_fields_json(self,conversation_text,*,timeout_seconds):
  exact=normalize(conversation_text)==normalize(source)
  row={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'event':'matched' if exact else 'rejected','model_calls':0}
  with (run/'replay-events.jsonl').open('a',encoding='utf8') as f:f.write(json.dumps(row)+'\n')
  if not exact:raise LLMProviderUnavailableError('此入口只回放试用卡上的固定合成原文。已保留输入；其他问诊需切换真实在线入口。')
  return LLMProviderResponse(provider=self.name,model=self.model,content=response,latency_ms=0)
def generator(*a,**k):
 g=LLMRecordGenerator(provider=Replay(),requested_provider=Replay.name,requested_model=Replay.model,mode='demo',allow_mock_fallback=False);g.max_retries=0;return g
def status(*a,**k):
 return {'provider':Replay.name,'model':Replay.model,'mode':'demo','configured':True,'reachable':True,'fallback':False,'fallback_allowed':False,'fallback_reason':None,'checked':True}
factory.get_llm_status=status;factory.create_llm_record_generator=generator;factory.create_llm_provider=lambda *a,**k:Replay();app.services.create_llm_record_generator=generator;app.services.llm.create_llm_record_generator=generator
from app.main import app
from starlette.responses import JSONResponse
@app.middleware('http')
async def no_simulated_asr(request,call_next):
 path=request.url.path
 if path.startswith(('/api/audio','/api/asr/','/api/llm/test')):
  return JSONResponse(status_code=409,content={'detail':'独立回放版仅演示固定合成文本的病历审核。录音、上传和在线生成需使用对应的实时服务。'})
 return await call_next(request)
from fastapi.responses import HTMLResponse, FileResponse
from starlette.requests import Request
from starlette.responses import Response

@app.middleware('http')
async def course_presentation(request: Request, call_next):
    if request.url.path == '/static/doctor.html':
        content = (SRC/'static/doctor.html').read_text(encoding='utf8')
        content = content.replace('</head>', '<link rel="stylesheet" href="/course/projector.css?v=1"></head>')
        return HTMLResponse(content, headers={'Cache-Control': 'no-store'})
    if request.url.path == '/course/projector.css':
        return FileResponse(HERE/'投影.css', media_type='text/css')
    if request.url.path == '/course/identity':
        return JSONResponse({'service':'medilisten-course-replay-20261118','variant':'classroom-projection-1','port':port})
    return await call_next(request)

import uvicorn
uvicorn.run(app, host='127.0.0.1', port=port, log_level='warning', access_log=False)
