import {CASES, createInitialState, createStore, serialize, restore, currentEncounter, reviewRemaining, hasPendingChanges, isSigned, canSign, canComplete} from './model.mjs';

const STORAGE = 'medilisten-synthetic-prototype-v1';
const root = document.querySelector('#app');
const dialogs = document.querySelector('#dialogs');
const toast = document.querySelector('#toast');
let storageOK = true;
let initial;
try { const saved = sessionStorage.getItem(STORAGE); initial = saved ? restore(saved) : createInitialState(); } catch { storageOK = false; }
const store = createStore(initial || createInitialState());
const ui = {view:'home', pin:false, modal:null, focus:null, filter:'all', search:'', editing:false, empty:false, sourceIndex:-1, evidence:null, historyIndex:null, failNext:false, metrics:{clicks:0, evidenceOpens:0, panelSwitches:0, startedAt:null}};
const timers = new Map();
const labels = {chiefComplaint:'主诉',presentIllness:'现病史',allergies:'过敏史',diagnosis:'初步诊断'};
const issueLabels = {missing:'未采集信息',conflict:'原文与草稿不一致',diagnosis:'候选诊断',risk:'重要提醒'};
const issueField = {missing:'allergies',conflict:'presentIllness',diagnosis:'diagnosis',risk:'diagnosis'};
const decisionLabels = {not_collected:'本次未采集',supplemented:'已补充',source_verified:'已核对，保留原文差异',doctor_corrected:'医生已修正',adopt:'保留',reject:'不采纳',defer:'待进一步评估',reviewed:'已核对提醒'};
const esc = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const btn = (text,action,cls='secondary',attrs='') => '<button type="button" class="'+cls+'" data-action="'+action+'" '+(attrs.includes('data-focus=')?'':'data-focus="'+action+'" ')+attrs+'>'+text+'</button>';
const eNow = () => currentEncounter(store.getState());
const caseFor = e => Array.isArray(CASES) ? CASES.find(c=>c.id===e.id) : CASES[e.id];
const asText = value => typeof value === 'object' ? (value?.description || value?.text || value?.message || JSON.stringify(value)) : value;
const isApproved = isSigned;
const hasPending = hasPendingChanges;
const phase = e => e.status==='completed' ? '本次接诊已完成' : e.recovery ? '有待恢复内容' : e.dirty ? '修改尚未保存' : isApproved(e) ? '已签署 · 可导出' : e.task.status==='processing' ? '正在整理病历' : e.task.status==='failed' ? '整理未完成' : e.revision ? '待核对病历' : '待采集问诊';
const time = value => value ? new Date(value).toLocaleString('zh-CN',{hour12:false}) : '本次演示';

function persist() {
  try { sessionStorage.setItem(STORAGE, serialize(store.getState())); storageOK=true; return true; }
  catch { storageOK=false; return false; }
}
let toastTimer;
let lastNotice;
function notify(text) { clearTimeout(toastTimer); toast.textContent=text; toastTimer=setTimeout(()=>{toast.textContent='';},5000); }
function focusSnapshot() {
  const a=document.activeElement;
  return a && {key:a.dataset.focus, start:a.selectionStart,end:a.selectionEnd};
}
function focusRestore(saved) {
  if (!saved?.key) return;
  const target=[...document.querySelectorAll('[data-focus]')].find(el=>el.dataset.focus===saved.key);
  if(target){target.focus({preventScroll:true}); if(saved.start!=null && target.setSelectionRange) target.setSelectionRange(saved.start,saved.end);}
}
function render() {
  const saved=focusSnapshot();
  const recordScroll=document.querySelector('.record-scroll')?.scrollTop || 0;
  const modalScroll=document.querySelector('.modal-body')?.scrollTop || 0;
  const s=store.getState(),e=eNow();
  root.innerHTML='<div class="app-shell"><header class="topbar"><a class="brand" href="#" data-action="home"><img src="./assets/medilisten.png" alt=""><strong>MediListen</strong></a><span class="prototype-badge">交互原型 · 仅合成病例</span><div class="top-actions">'+btn('试用说明','help','text-button')+btn('演示场景','scenarios','text-button')+'</div></header><div class="app-layout"><nav class="sidebar" aria-label="工作区"><p class="eyebrow">医生工作区</p>'+btn('今日接诊','home',ui.view==='home'?'active':'text-button')+btn('当前病历','encounter',ui.view==='encounter'?'active':'text-button','aria-disabled="'+(!e || e.status==='waiting')+'"')+'<p class="sidebar-note">AI 辅助整理<br>病历由医生核对</p></nav><main id="main" class="main" tabindex="-1">'+(!storageOK?'<div class="recovery-banner" role="alert">演示暂存不可用。请先保存修改；刷新后未保存内容无法恢复。</div>':'')+(ui.view==='home'?home(s):encounter(e))+'</main></div></div>';
  root.inert=!!ui.modal;
  dialogs.innerHTML=ui.modal?modalContent(e):'';
  focusRestore(saved);
  if(document.querySelector('.record-scroll')) document.querySelector('.record-scroll').scrollTop=recordScroll;
  if(document.querySelector('.modal-body')) document.querySelector('.modal-body').scrollTop=modalScroll;
  if(s.notice?.text && s.notice!==lastNotice){lastNotice=s.notice;notify(s.notice.text);}else if(!s.notice && lastNotice){clearTimeout(toastTimer);toast.textContent='';lastNotice=null;}
}

function home(s) {
  const encounters=Object.values(s.encounters);
  const visible=encounters.filter(e=>(ui.filter==='all'||(ui.filter==='active'?e.status==='active':e.status==='completed')) && (e.patient.name+e.id).includes(ui.search));
  const active=encounters.find(e=>e.status==='active');
  return '<div class="page-header"><div><p class="eyebrow">今日接诊</p><h1 class="page-title">每一次接诊，清楚继续</h1><p class="muted">选择患者开始问诊，或接着核对尚未完成的病历。</p></div>'+(active?btn('继续 '+esc(active.patient.name)+' 的接诊','select','primary','data-id="'+active.id+'"'):'')+'</div><div class="toolbar"><label class="search-label">查找患者<input type="search" data-input="search" data-focus="search" value="'+esc(ui.search)+'" placeholder="姓名或演示就诊编号"></label><div class="filters" aria-label="就诊状态">'+[['all','全部'],['active','接诊中'],['completed','已完成']].map(([id,title])=>btn(title,'filter','filter '+(ui.filter===id?'active':''),'data-value="'+id+'" aria-pressed="'+(ui.filter===id)+'" data-focus="filter-'+id+'"')).join('')+'</div></div>'+(ui.empty||!visible.length?'<section class="empty-state"><h2>这里还没有就诊任务</h2><p class="muted">先选择一位演示患者，体验完整的采集与核对流程。</p>'+btn(ui.empty?'载入演示患者':'查看全部就诊',ui.empty?'load-cases':'all','primary')+'</section>':'<section class="encounter-list" aria-label="今日患者">'+visible.map(e=>'<article class="encounter-row"><div class="patient-info"><h2>'+esc(e.patient.name)+' <span class="status-pill">合成病例</span></h2><p class="muted">'+esc(e.patient.sex)+' · '+esc(e.patient.age)+'岁 · '+esc(e.id)+'</p></div><div><span class="status-pill '+(isApproved(e)?'success':'')+'">'+phase(e)+'</span><p class="muted">'+(e.revision?'版本 '+e.revision+(e.dirty?' · 有未保存修改':' · 已保存'):'尚未建立病历')+'</p></div>'+btn(e.status==='completed'?'查看病历':e.status==='waiting'?'开始接诊':'继续接诊','select',e.status==='waiting'?'primary':'secondary','data-id="'+e.id+'" data-focus="select-'+e.id+'"')+'</article>').join('')+'</section>')+'<p class="prototype-note">这是独立的交互试用：所有病例及处理结果均为固定演示内容，不连接业务数据库或模型。</p>';
}

function encounter(e) {
  if(!e) return '<p>请先选择就诊。</p>';
  const remaining=reviewRemaining(e);
  return '<header class="patient-bar"><div class="patient-identity"><strong>'+esc(e.patient.name)+'</strong><span class="status-pill">合成病例</span><span class="patient-meta">'+esc(e.patient.sex)+' · '+e.patient.age+'岁 · 就诊 '+e.id+'</span></div><span class="status-pill">'+phase(e)+'</span></header><div class="phase-line" aria-label="当前接诊进度"><span class="phase '+(!e.revision?'active':'')+'">采集问诊</span><span class="phase '+(e.revision&&!isApproved(e)?'active':'')+'">核对病历</span><span class="phase '+(isApproved(e)?'active':'')+'">签署与导出</span><div class="workspace-tools">'+btn(innerWidth<900?'查看原文':ui.pin?'收起原文':'固定原文并排','pin','text-button','aria-pressed="'+ui.pin+'"')+btn('诊疗参考','reference','text-button')+'</div></div>'+recoveryBanner(e)+(e.task.connection==='reconnecting'?'<div class="connection-banner" role="status"><div><strong>暂时无法获取进度</strong><p>正在保留当前任务，连接恢复后继续查看。不会重复生成。</p></div>'+btn('重新连接','reconnect')+'</div>':'')+'<div class="workspace '+(ui.pin?'with-source':'')+'">'+(ui.pin?sourcePanel(e):'')+'<section class="record-panel" aria-label="当前病历"><div class="record-header"><h1>门诊病历</h1><div><span class="muted">'+(e.dirty?'修改未保存':e.revision?'版本 '+e.revision+' · 已保存':'尚未生成')+'</span> '+(e.revision?btn('历史版本','history','text-button'):'')+'</div></div>'+(e.revision?'<nav class="section-nav" aria-label="病历章节">'+btn('病史','section','text-button','data-target="history"')+btn('过敏与用药','section','text-button','data-target="allergy"')+btn('诊断','section','text-button','data-target="diagnosis"')+'</nav>':'')+'<div class="record-scroll">'+(!e.revision?intake(e):record(e,remaining))+'</div></section></div>'+actionBar(e,remaining);
}
function recoveryBanner(e) {
  return e.recovery?'<section class="recovery-banner" role="alert"><div><strong>发现本次就诊未提交的内容</strong><p>当前显示已保存的版本。你可以恢复未保存输入、编辑或审核选择，恢复不会覆盖正式版本。</p></div>'+btn('恢复本次内容','recover','primary')+btn('放弃恢复内容','discard-recovery','secondary')+'</section>':'';
}
function intake(e) {
  if(e.task.status==='processing') return '<div class="empty-state"><span class="status-pill">正在整理</span><h2>问诊内容已收到</h2><p>正在整理病历草稿，你仍可查看原文。</p><p class="muted">这是固定演示结果，约 3 秒后完成。</p>'+btn('查看输入原文','source','secondary')+'</div>';
  if(e.task.status==='failed') return '<div class="empty-state"><h2>这次整理未完成</h2><p>原始输入已保留，可以查看后重试。</p>'+btn('重试整理','retry','primary')+btn('查看输入原文','source')+'</div>';
  if(e.task.status==='role_review') return '<div class="empty-state"><h2>先核对说话人</h2><p>请核对原文中的医生和患者身份，确认后再生成草稿。</p>'+btn('核对说话人','roles','primary')+'</div>';
  return '<div class="empty-state"><p class="eyebrow">本次问诊</p><h2>从问诊内容开始</h2><p class="muted">选择一种采集方式，完成后在这里核对病历。</p><div class="input-options">'+btn('输入问诊文本','text-input','primary',''+(e.recovery?'disabled':''))+btn('上传问诊音频','audio-input','secondary',e.recovery?'disabled':'')+btn('录音问诊','record-input','secondary',e.recovery?'disabled':'')+'</div>'+(e.input.text?'<p class="muted">本次就诊有未提交输入，重新打开可继续。</p>':'')+'</div>';
}
function sourcePanel(e) {
  return '<aside class="source-panel" aria-label="问诊原文"><div class="record-header"><h2>问诊原文</h2>'+btn('收起','pin','text-button')+'</div><p class="muted source-note">只读对照 · '+(e.input.kind==='text'?'文本输入':'合成音频转写')+'</p>'+sourceLines(e)+'</aside>';
}
function sourceLines(e) {
  const lines=(e.input.text||'尚未输入问诊内容').split('\n').filter(Boolean);
  return '<div class="source-lines">'+lines.map((line,i)=>'<div class="source-line '+(ui.sourceIndex===i?'selected':'')+'" data-source-index="'+i+'"><span class="source-role">'+(/^【医生】/.test(line)?'医生':/^【患者】/.test(line)?'患者':/^【演示说明】/.test(line)?'演示说明 · 非患者原话':'原文')+'</span><p>'+esc(line.replace(/^\[.*?\]\s*|^【.*?】\s*/,''))+'</p></div>').join('')+'</div>';
}
function record(e,remaining) {
  return '<div class="review-summary"><div><strong>'+(isApproved(e)?'当前版本已签署':remaining.length?'还有 '+remaining.length+' 项需要核对':'已核对，等待签署')+'</strong><span class="muted">'+(e.dirty?' 请先保存修改':isApproved(e)?(e.status==='completed'?' 本次接诊已结束，只读查看':' 修改后需要重新核对签署'):' 选择只在签署后正式提交')+'</span></div>'+(!isApproved(e)&&remaining.length?btn('下一待核对项','next-issue','secondary'):isApproved(e)?btn('查看签署记录','signature','text-button'):'')+'</div>'+Object.keys(labels).map(key=>field(e,key)).join('');
}
function field(e,key) {
  const group=key==='chiefComplaint'?'history':key==='allergies'?'allergy':key==='diagnosis'?'diagnosis':null;
  const issues=Object.keys(issueField).filter(kind=>issueField[kind]===key);
  return (group?'<div id="section-'+group+'" class="section-anchor"></div>':'')+'<article class="field" id="field-'+key+'" aria-label="'+labels[key]+'"><div class="field-head"><h2>'+labels[key]+'</h2><span class="status-pill '+(isApproved(e)?'success':'')+'">'+(isApproved(e)?'本版已确认':e.dirty?'编辑中':'待医生核对')+'</span></div>'+(ui.editing?'<label class="form-field"><span class="sr-only">编辑'+labels[key]+'</span><textarea data-input="field" data-key="'+key+'" data-focus="edit-'+key+'" rows="'+(key==='presentIllness'?4:2)+'">'+esc(e.fields[key])+'</textarea></label>':'<p class="field-value">'+esc(e.fields[key])+'</p>')+'<div class="field-actions">'+btn('原文','evidence','text-button','data-key="'+key+'" data-focus="evidence-'+key+'"')+(!ui.editing&&e.status!=='completed'?btn('修改','edit','text-button','data-key="'+key+'" data-focus="edit-button-'+key+'"'):'')+'</div>'+(ui.evidence===key?'<div class="inline-evidence"><strong>对应问诊原话</strong><p>'+esc(evidenceText(e,key))+'</p><span class="muted">原文仅供核对，医生修改单独保存。</span></div>':'')+(!ui.editing?issues.map(kind=>issue(e,kind)).join(''):'')+'</article>';
}
function evidenceText(e,key) {
  if(key==='allergies')return '本次未采集过敏史，没有对应患者原话。不能将未采集理解为无过敏。';
  if(key==='diagnosis')return '初步诊断属于待医生判断的意见，不是患者已确认事实。请结合完整问诊核对。';
  return (e.input.text||'').split('\n').filter(line=>/^【患者】/.test(line)).join('\n')||'本次未采集对应原文。';
}
function issue(e,kind) {
  const value=e.review[kind];
  if(isApproved(e)) return '<p class="muted reviewed-note">'+issueLabels[kind]+' · '+esc(decisionLabels[value]||'本版已签署')+'</p>';
  if(value) return '<div class="field-issue resolved"><strong>'+issueLabels[kind]+' · '+esc(decisionLabels[value])+'</strong><span class="muted"> 待签署</span>'+btn('重新核对','undo-review','text-button','data-kind="'+kind+'" data-focus="undo-'+kind+'"')+'</div>';
  const choices={missing:[['not_collected','确认本次未采集']],conflict:[['source_verified','已核对，保留差异'],['doctor_corrected','已按原文修正']],diagnosis:[['adopt','保留候选'],['reject','不采纳'],['defer','暂缓判断']],risk:[['reviewed','已核对此提醒']]};
  return '<div class="field-issue" id="issue-'+kind+'" tabindex="-1"><strong>'+issueLabels[kind]+'</strong><p>'+esc(asText(caseFor(e)?.issues?.[kind])||'请结合问诊原文逐项核对。')+'</p><div class="issue-actions">'+choices[kind].map(([v,t])=>btn(t,'review','secondary','data-kind="'+kind+'" data-value="'+v+'" data-focus="review-'+kind+'-'+v+'" '+(e.dirty?'disabled':''))).join('')+'</div></div>';
}
function actionBar(e,remaining) {
  let actions='';
  if(e.recovery) actions=btn('恢复本次内容','recover','primary');
  else if(ui.editing) actions=btn('放弃本次修改','discard-edit')+btn('保存修改','save','primary',e.dirty?'':'disabled');
  else if(isApproved(e)) actions=btn('导出病历','export','primary')+(e.status==='completed'?btn('返回接诊列表','home'):btn('完成接诊，返回列表','complete','secondary',canComplete(e)?'':'disabled'));
  else if(e.revision) actions=btn('编辑病历','edit','secondary')+(canSign(e)?btn('签署当前版本','sign','primary'):btn('继续核对 '+remaining.length+' 项','next-issue','primary'));
  return '<footer class="action-bar"><span role="status">'+(e.saveConflict?'保存冲突 · 本地修改已保留':e.dirty?'修改未保存':isApproved(e)?'版本 '+e.revision+' 已签署':e.revision?'版本 '+e.revision+' 已保存 · 待签署':'输入只用于当前就诊')+'</span><div>'+actions+'</div></footer>';
}

function modalContent(e) {
  const m=ui.modal;let title='',body='',footer='';
  if(['text','audio','recording'].includes(m.type)) {
    title=m.type==='text'?'输入问诊文本':m.type==='audio'?'上传问诊音频':'录音问诊';
    body='<p class="patient-context">'+esc(e.patient.name)+' · 就诊 '+e.id+'</p>';
    if(m.type==='text') body+='<label class="form-field"><span>问诊内容</span><textarea data-input="conversation" data-focus="conversation" rows="10" placeholder="在这里输入或粘贴本次问诊。演示时请使用下方合成样例。">'+esc(e.input.text)+'</textarea></label>'+btn('载入合成样例','sample','text-button')+'<p class="muted">关闭面板会保留在本次就诊，切换患者不会带走这份输入。此处输入不参与推理，生成时使用本病例的固定演示草稿。</p>';
    if(m.type==='audio') body+='<label class="form-field"><span>演示音频</span><select data-input="audio" data-focus="audio"><option value="">请选择演示音频</option><option value="sample" '+(e.input.text?'selected':'')+'>合成问诊样例 · 固定转写演示</option></select></label><p class="muted">本原型使用固定转写，不上传本机文件。</p><details><summary>高级选项</summary><p>声纹与引擎配置保留给后续生产评审。当前仅验证上传后的核对流程。</p></details>';
    if(m.type==='recording') body+='<div class="empty-state"><h2>'+(m.recording?'正在模拟录音…':'准备开始问诊')+'</h2><p>不调用麦克风。停止后载入固定合成转写。</p>'+btn(m.recording?'停止模拟录音':'开始模拟录音',m.recording?'stop-recording':'start-recording',m.recording?'danger':'primary')+'</div>';
    footer=btn('关闭','close')+btn('开始整理病历','generate','primary',e.recovery||m.recording?'disabled':'');
  } else if(m.type==='roles') {
    title='核对说话人';body='<p>请核对医生提问和患者回答的归属。这里是固定的合成转写。</p>'+sourceLines(e);footer=btn('返回','close')+btn('身份正确，继续整理','confirm-roles','primary');
  } else if(m.type==='source') {title='问诊原文';body=sourceLines(e);footer=btn('返回病历','close','primary');
  } else if(m.type==='reference') {title='诊疗参考';body='<p>参考内容帮助医生判断，不会自动写入患者事实。</p><h3>当前病例的核对重点</h3><p>结合原文检查症状、持续时间、否定信息与过敏史；未询问的内容应保持未采集。</p><p class="muted">这是一段交互演示说明，不是临床指南或诊疗建议。</p>';footer=btn('返回病历','close','primary');
  } else if(m.type==='history') {
    title='历史版本';const revisions=e.revisions;const index=ui.historyIndex??Math.max(0,revisions.length-2);const old=revisions[index];
    body='<p>只读对照，不替换当前病历。</p><label class="form-field">选择版本<select data-input="history" data-focus="history">'+revisions.map((r,i)=>'<option value="'+i+'" '+(i===index?'selected':'')+'>版本 '+(r.revision||r.number||i+1)+'</option>').join('')+'</select></label><div class="history-grid"><section><h3>所选版本</h3>'+Object.keys(labels).map(key=>'<h4>'+labels[key]+'</h4><p>'+esc(old?.fields?.[key])+'</p>').join('')+'</section><section><h3>当前版本 '+e.revision+'</h3>'+Object.keys(labels).map(key=>'<h4>'+labels[key]+'</h4><p>'+esc(e.revisions.at(-1)?.fields[key])+'</p>').join('')+'</section></div>';footer=btn('返回当前病历','close','primary');
  } else if(m.type==='signature') {title='签署记录';body='<p>就诊 '+e.id+' · 版本 '+e.revision+'</p><p>本页演示医生已确认当前保存版本。</p>'+Object.entries(e.review).map(([k,v])=>'<p>'+issueLabels[k]+'：'+esc(decisionLabels[v])+'</p>').join('');footer=btn('返回病历','close','primary');
  } else if(m.type==='export') {
    title='病历文件已生成';const x=e.exports.at(-1);
    body='<div class="receipt"><p class="status-pill success">版本已签署 · 文件已生成</p><dl class="receipt-grid"><div class="receipt-item"><dt>患者 / 就诊</dt><dd>'+esc(e.patient.name)+' / '+e.id+'</dd></div><div class="receipt-item"><dt>病历版本</dt><dd>版本 '+x?.revision+'</dd></div><div class="receipt-item"><dt>签署时间</dt><dd>'+time(x?.approval?.signedAt)+'</dd></div><div class="receipt-item"><dt>生成时间</dt><dd>'+time(x?.generatedAt)+'</dd></div><div class="receipt-item"><dt>文件</dt><dd>'+esc(x?.filename||e.id+'-R'+e.revision+'-演示病历.txt')+'</dd></div></dl><p class="muted">下载的是带“合成演示”标记的文本文件；生产 PDF 排版不在本原型中模拟。</p><p role="status">'+(x?.status==='failed'?'下载未开始，文件仍可重试。':x?.status==='downloaded'?'已发起浏览器下载，请在下载列表确认。':'文件已准备好，尚未下载。')+'</p></div>';footer=btn('返回病历','close')+btn('下载演示病历','download','primary')+(e.status==='completed'?btn('返回接诊列表','home'):btn('完成接诊','complete'));
  } else if(m.type==='leave') {title='保留这次接诊的内容';body='<p>'+esc(e.patient.name)+' 的未提交内容会保留在本次就诊。继续切换不会保存或签署病历。</p>';footer=btn('留在本次就诊','close','primary')+btn('暂存并离开','confirm-leave')+btn('放弃未提交内容并离开','discard-leave','danger');
  } else if(m.type==='discard-edit') {title='放弃本次修改？';body='<p>将恢复最近保存的版本，未保存编辑会被丢弃。你也可以继续编辑。</p>';footer=btn('继续编辑','close','primary')+btn('确认放弃修改','confirm-discard','danger');
  } else if(m.type==='save-conflict') {title='保存版本需要核对';body='<p>模拟发现服务器有较新版本。当前编辑已保留，尚未覆盖任何保存版本。</p><p>原型中可解除模拟冲突，再继续保存；生产流程须展示实际版本差异。</p>';footer=btn('保留编辑，返回','close','primary')+btn('解除模拟冲突','resolve-conflict');
  } else if(m.type==='help') {title='试用这条接诊流程';body='<ol><li>选择一位合成患者，载入文本样例。</li><li>整理后查看原文，修改并保存病历。</li><li>处理四类核对项目，签署当前版本。</li><li>生成文件、下载并完成本次接诊。</li></ol><p>可在“演示场景”中检查断连、失败、冲突和刷新恢复。</p><p>仅合成病例会暂存在当前浏览器标签页。刷新后须明确恢复未提交内容；浏览器可能恢复已关闭标签页的会话；明确清除请使用重置演示。请勿输入真实患者资料。</p><p>原文可固定并排；窄屏通过原文面板核对并返回。</p>';footer=btn('开始试用','close','primary');
  } else if(m.type==='scenarios') {title='演示场景';body='<p>这些按钮只改变原型的合成状态，不影响业务系统。</p><div class="scenario-grid">'+btn('空就诊列表','empty')+btn('载入演示患者','load-cases')+btn('模拟连接中断','disconnect')+btn('恢复连接','reconnect')+btn('下次生成失败','fail-next')+btn('模拟保存冲突','inject-conflict')+btn('模拟下载失败','fail-download')+btn('查看本次操作计数','metrics')+btn('重置全部演示','reset','danger')+'</div>';footer=btn('返回','close','primary');
  } else if(m.type==='metrics') {title='本次原型操作记录';body='<p>点击次数：'+ui.metrics.clicks+'</p><p>原文查看：'+ui.metrics.evidenceOpens+'</p><p>辅助面板打开：'+ui.metrics.panelSwitches+'</p><p class="muted">计数从本次载入页面开始，刷新重置；不是医生效率或满意度结果。</p>';footer=btn('返回','close','primary');}
  return '<div class="modal-backdrop"><section class="modal '+(['history','roles'].includes(m.type)?'wide':'')+'" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="modal-header"><h2 id="dialog-title" tabindex="-1">'+title+'</h2>'+btn('关闭','close','text-button','aria-label="关闭面板"')+'</header><div class="modal-body">'+body+'</div><footer class="modal-footer">'+footer+'</footer></section></div>';
}

function openModal(type,extra={}) {
  ui.focus=focusSnapshot();ui.modal={type,...extra};ui.metrics.panelSwitches++;render();
  const target=dialogs.querySelector('textarea,select')||dialogs.querySelector('#dialog-title');target?.focus();
}
function closeModal() {ui.modal=null;render();focusRestore(ui.focus);}
function choose(id) {store.dispatch({type:'SELECT',id});if(eNow().status==='waiting')store.dispatch({type:'START'});ui.view='encounter';ui.editing=false;ui.evidence=null;render();document.querySelector('#main')?.focus();}
function navigate(target,id) {
  if(ui.view==='encounter' && hasPending(eNow()) && !eNow().recovery && (target==='home'||id!==eNow().id)) {openModal('leave',{target,id});return;}
  if(id) choose(id);else {ui.view=target;render();}
}
function generate() {
  if(!eNow().input.text.trim()){notify('请先输入问诊文本或选择演示音频。');return;}
  closeModal();store.dispatch({type:'GENERATE'});
  if(eNow().task.status==='role_review')openModal('roles');
}
function scheduleGeneration(s) {
  for(const e of Object.values(s.encounters)) {
    if(e.task.status!=='processing'||timers.has(e.task.id))continue;
    const id=e.task.id,encounterId=e.id,fail=ui.failNext;ui.failNext=false;
    timers.set(id,setTimeout(()=>{timers.delete(id);store.dispatch({type:fail?'GENERATION_FAILED':'GENERATION_DONE',taskId:id,encounterId});},3000));
  }
}
function goIssue() {
  const kind=reviewRemaining(eNow())[0];if(!kind)return;
  const el=document.getElementById('issue-'+kind);el?.scrollIntoView({block:'center',behavior:'smooth'});el?.focus({preventScroll:true});
}
function download() {
  const e=eNow(),x=e.exports.at(-1);if(!x)return;
  if(!isApproved(e)){notify('请先签署当前版本。');return;}
  const text=['MediListen 合成演示病历 · 不用于诊疗',e.patient.name+' / '+e.id,'版本 '+x.revision,'',...Object.keys(labels).map(k=>labels[k]+'：'+x.fields[k]),'', '本版核对决定（合成演示）',...Object.entries(x.approval.review).map(([k,v])=>issueLabels[k]+'：'+decisionLabels[v])].join('\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=x.filename||e.id+'-R'+x.revision+'-演示病历.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);store.dispatch({type:'DOWNLOAD',exportId:x.id});
}

document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');if(!target||target.disabled)return;event.preventDefault();ui.metrics.clicks++;
  const a=target.dataset.action,e=eNow();
  switch(a){
    case 'home':if(ui.modal)closeModal();navigate('home');break;
    case 'encounter':if(e.status==='waiting'){notify('请先从今日接诊选择患者。');break;}ui.view='encounter';render();break;
    case 'select':navigate('encounter',target.dataset.id);break;
    case 'confirm-leave':{const m=ui.modal;store.dispatch({type:'STASH_DRAFT'});if(!persist()){notify('暂存失败，请继续本次接诊。');break;}closeModal();if(m.id)choose(m.id);else{ui.view=m.target;render();}break;}
    case 'discard-leave':{const m=ui.modal;store.dispatch({type:'DISCARD_DRAFT'});closeModal();if(m.id)choose(m.id);else{ui.view=m.target;render();}break;}
    case 'filter':ui.filter=target.dataset.value;render();break;
    case 'all':ui.filter='all';ui.search='';render();break;
    case 'empty':ui.empty=true;ui.view='home';closeModal();break;
    case 'load-cases':ui.empty=false;ui.filter='all';ui.search='';ui.view='home';closeModal();break;
    case 'text-input':openModal('text');break;
    case 'audio-input':openModal('audio');break;
    case 'record-input':openModal('recording');break;
    case 'start-recording':ui.modal.recording=true;render();break;
    case 'stop-recording':ui.modal.recording=false;store.dispatch({type:'SET_INPUT',kind:'recording',text:caseFor(e).text});notify('模拟录音已结束，请继续整理。');break;
    case 'sample':store.dispatch({type:'SET_INPUT',kind:'text',text:caseFor(e).text});break;
    case 'generate':generate();break;
    case 'roles':openModal('roles');break;
    case 'confirm-roles':closeModal();store.dispatch({type:'CONFIRM_ROLES'});store.dispatch({type:'GENERATE'});break;
    case 'retry':store.dispatch({type:'RETRY'});break;
    case 'pin':if(innerWidth<900){openModal('source');break;}ui.pin=!ui.pin;render();break;
    case 'source':openModal('source');break;
    case 'reference':openModal('reference');break;
    case 'evidence':ui.evidence=ui.evidence===target.dataset.key?null:target.dataset.key;ui.sourceIndex=['allergies','diagnosis'].includes(target.dataset.key)?-1:(e.input.text||'').split('\n').filter(Boolean).findIndex(line=>/^【患者】/.test(line));ui.metrics.evidenceOpens++;render();if(ui.pin)document.querySelector('.source-line.selected')?.scrollIntoView({block:'nearest'});break;
    case 'section':document.getElementById('section-'+target.dataset.target)?.scrollIntoView({block:'start',behavior:'smooth'});break;
    case 'next-issue':goIssue();break;
    case 'edit':if(e.status==='completed'){notify('已完成的就诊保持只读。');break;}if(e.recovery){notify('请先处理待恢复内容。');break;}ui.editing=true;ui.editKey=target.dataset.key||'chiefComplaint';render();document.querySelector('[data-focus="edit-'+(target.dataset.key||'chiefComplaint')+'"]')?.focus();break;
    case 'save':store.dispatch({type:'SAVE'});if(eNow().saveConflict)openModal('save-conflict');else if(!eNow().dirty){ui.editing=false;render();document.querySelector('[data-focus="edit-button-'+(ui.editKey||'chiefComplaint')+'"]')?.focus({preventScroll:true});}break;
    case 'discard-edit':if(e.dirty)openModal('discard-edit');else{ui.editing=false;render();}break;
    case 'confirm-discard':store.dispatch({type:'DISCARD_EDITS'});ui.editing=false;closeModal();break;
    case 'undo-review':store.dispatch({type:'REVIEW',kind:target.dataset.kind,value:null});break;
    case 'review':store.dispatch({type:'REVIEW',kind:target.dataset.kind,value:target.dataset.value});break;
    case 'sign':store.dispatch({type:'SIGN'});render();document.querySelector('.record-scroll')?.scrollTo({top:0});break;
    case 'export':{store.dispatch({type:'CREATE_EXPORT'});const next=eNow();if(store.getState().notice?.kind!=='error' && isApproved(next) && next.exports.some(x=>x.revision===next.revision))openModal('export');break;}
    case 'download':download();break;
    case 'complete':store.dispatch({type:'COMPLETE'});if(eNow().status==='completed'){ui.view='home';closeModal();}break;
    case 'recover':store.dispatch({type:'RECOVER_DRAFT'});ui.editing=eNow().dirty;render();break;
    case 'discard-recovery':store.dispatch({type:'DISCARD_RECOVERY'});break;
    case 'history':ui.historyIndex=null;openModal('history');break;
    case 'signature':openModal('signature');break;
    case 'disconnect':store.dispatch({type:'DISCONNECT'});closeModal();break;
    case 'reconnect':store.dispatch({type:'RECONNECT'});closeModal();break;
    case 'fail-next':ui.failNext=true;closeModal();notify('下一次整理将模拟失败，原始输入会保留。');break;
    case 'inject-conflict':store.dispatch({type:'INJECT_SAVE_CONFLICT'});closeModal();notify('下一次保存将显示模拟冲突。');break;
    case 'resolve-conflict':store.dispatch({type:'RESOLVE_SAVE_CONFLICT'});closeModal();break;
    case 'fail-download':if(e.exports.length){store.dispatch({type:'DOWNLOAD',fail:true});openModal('export');}else{notify('请先签署并生成演示文件。');}break;
    case 'reset':openModal('reset-confirm');dialogs.querySelector('.modal-body').innerHTML='<p>将清除这两个合成病例的演示进度。真实业务数据不受影响。</p>';dialogs.querySelector('.modal-header h2').textContent='重置演示？';dialogs.querySelector('.modal-footer').innerHTML=btn('保留进度','close','primary')+btn('确认重置演示','confirm-reset','danger');break;
    case 'confirm-reset':for(const timer of timers.values())clearTimeout(timer);timers.clear();store.dispatch({type:'RESET'});ui.view='home';ui.editing=false;ui.empty=false;ui.pin=false;closeModal();break;
    case 'scenarios':case 'help':case 'metrics':openModal(a);break;
    case 'close':closeModal();break;
  }
});
document.addEventListener('input',event=>{
  const el=event.target;
  if(el.dataset.input==='search'){ui.search=el.value;render();}
  if(el.dataset.input==='conversation')store.dispatch({type:'SET_INPUT',kind:'text',text:el.value});
  if(el.dataset.input==='field')store.dispatch({type:'EDIT_FIELD',key:el.dataset.key,value:el.value});
});
document.addEventListener('change',event=>{
  const el=event.target;
  if(el.dataset.input==='audio')store.dispatch({type:'SET_INPUT',kind:'audio',text:el.value?caseFor(eNow()).text:''});
  if(el.dataset.input==='history'){ui.historyIndex=Number(el.value);render();}
});
document.addEventListener('keydown',event=>{
  if(!ui.modal)return;
  if(event.key==='Escape'){event.preventDefault();closeModal();return;}
  if(event.key==='Tab'){
    const focusables=[...dialogs.querySelectorAll('button:not(:disabled),input,select,textarea,[tabindex="0"]')].filter(el=>el.getClientRects().length);
    if(!focusables.length)return;const first=focusables[0],last=focusables.at(-1);
    if(event.shiftKey&&(document.activeElement===first||!focusables.includes(document.activeElement))){event.preventDefault();last.focus();}
    else if(!event.shiftKey&&(document.activeElement===last||!focusables.includes(document.activeElement))){event.preventDefault();first.focus();}
  }
});
let resizeTimer;
window.addEventListener('resize',()=>{clearTimeout(resizeTimer);resizeTimer=setTimeout(render,100);});
window.addEventListener('beforeunload',event=>{
  persist();if(Object.values(store.getState().encounters).some(e=>hasPending(e)&&(!e.recovery||!storageOK))){event.preventDefault();event.returnValue='';}
});
store.subscribe(state=>{persist();render();scheduleGeneration(state);});
render();scheduleGeneration(store.getState());
