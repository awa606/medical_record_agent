import {CASES, createInitialState, createStore, serialize, restore, currentEncounter, reviewRemaining, hasPendingChanges, isSigned, canSign, canComplete} from './model.mjs';
import {createCapture,captureReducer,captureSnapshot,captureHasPending,serializeCaptures,restoreCaptures} from './capture.mjs';

const STORAGE='medilisten-boundary-workbench-v1';
const CAPTURE_STORAGE=STORAGE+'-capture';
const root=document.querySelector('#app'),dialogs=document.querySelector('#dialogs'),toast=document.querySelector('#toast');
const split=()=>window.matchMedia('(min-width: 900px)').matches;
let storageOK=true,initial;
let captures=Object.fromEntries(CASES.map(c=>[c.id,createCapture(c.id)]));
try {const saved=sessionStorage.getItem(STORAGE); initial=saved?restore(saved):createInitialState();const recording=sessionStorage.getItem(CAPTURE_STORAGE);if(recording)captures=restoreCaptures(recording);}catch{storageOK=false;}
const store=createStore(initial||createInitialState());
const ui={view:'home',modal:null,focus:null,filter:'all',search:'',editing:false,empty:false,sourceIndices:[],evidence:null,activeIssue:null,historyIndex:null,failNext:false,stress:false,updatedFields:new Set(),metrics:{clicks:0,evidenceOpens:0,panelSwitches:0,startedAt:null}};
const timers=new Map();
const labels={chiefComplaint:'主诉',presentIllness:'现病史',allergies:'既往与过敏',diagnosis:'诊断意见'};
const issueLabels={missing:'过敏史未采集',conflict:'病程信息有差异',diagnosis:'候选诊断待判断',risk:'问诊信息待核对'};
const issueField={missing:'allergies',conflict:'presentIllness',diagnosis:'diagnosis',risk:'diagnosis'};
const decisionLabels={not_collected:'本次未采集',supplemented:'已补充',source_verified:'已核对，保留原文差异',doctor_corrected:'医生已修正',adopt:'保留',reject:'不采纳',defer:'待进一步评估',reviewed:'已核对提醒'};
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const btn=(text,action,cls='secondary',attrs='')=>'<button type="button" class="'+cls+'" data-action="'+action+'" '+(attrs.includes('data-focus=')?'':'data-focus="'+action+'" ')+attrs+'>'+text+'</button>';
const eNow=()=>currentEncounter(store.getState());
const caseFor=e=>CASES.find(c=>c.id===e.id);
const asText=value=>typeof value==='object'?(value?.description||value?.text||value?.message||JSON.stringify(value)):value;
const isApproved=isSigned;
const hasPending=e=>hasPendingChanges(e)||(!e.revision&&captureHasPending(captures[e.id]));
const live=e=>!e.revision&&captures[e.id]?.status!=='idle';
const cap=e=>captureSnapshot(captures[e.id]);
const time=value=>value?new Date(value).toLocaleString('zh-CN',{hour12:false}):'本次演示';
const clock=value=>value?new Date(value).toLocaleTimeString('zh-CN',{hour12:false}):'尚未更新';
const duration=seconds=>String(Math.floor(seconds/60)).padStart(2,'0')+':'+String(seconds%60).padStart(2,'0');
const motionBehavior=()=>window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth';
const phase=e=>e.status==='completed'?'本次接诊已完成':(e.recovery||(!e.revision&&cap(e).needsRecovery))?'有待恢复内容':e.dirty?'修改尚未保存':isApproved(e)?'本版已签署':e.task.status==='processing'?'正在整理病历':e.task.status==='failed'?'整理未完成':e.revision?'核对中 · '+reviewRemaining(e).length+'项待处理':live(e)?'采集中 · 临时草稿':'等待采集';
function persist(){try{sessionStorage.setItem(STORAGE,serialize(store.getState()));sessionStorage.setItem(CAPTURE_STORAGE,serializeCaptures(captures));storageOK=true;return true;}catch{storageOK=false;return false;}}
function markCaptureUpdates(before,after,id){
 if(id!==eNow().id)return;
 const previous=captureSnapshot(before),next=captureSnapshot(after);
 for(const key of Object.keys(labels))if(previous.fields[key]!==next.fields[key]&&!Object.hasOwn(next.editedFields,key))ui.updatedFields.add(key);
}
function sendCapture(type,extra={},id=eNow().id){const before=captures[id];captures[id]=captureReducer(before,{type,at:new Date().toISOString(),...extra});if(type!=='EDIT_FIELD')markCaptureUpdates(before,captures[id],id);persist();render();if(captures[id].notice)notify(captures[id].notice);}
let toastTimer,lastNotice;
function notify(text){clearTimeout(toastTimer);toast.textContent=text;toastTimer=setTimeout(()=>{toast.textContent='';},5000);}
function focusSnapshot(){const a=document.activeElement;return a&&{key:a.dataset.focus,start:a.selectionStart,end:a.selectionEnd};}
function focusRestore(saved){if(!saved?.key)return;const scope=ui.modal?dialogs:root;const target=[...scope.querySelectorAll('[data-focus]')].find(el=>el.dataset.focus===saved.key&&el.getClientRects().length&&!el.disabled);if(target){target.focus({preventScroll:true});if(saved.start!=null&&target.setSelectionRange)target.setSelectionRange(saved.start,saved.end);}else{(ui.modal?dialogs.querySelector('#dialog-title'):(root.querySelector('.action-buttons .primary:not(:disabled)')||root.querySelector('#main')))?.focus({preventScroll:true});}}
function render(){
 const saved=focusSnapshot();const openedDetails=new Set([...document.querySelectorAll('details[open]')].map(d=>d.querySelector('summary')?.dataset.focus||d.querySelector('summary')?.textContent));const scrolls=Object.fromEntries(['.record-scroll','.modal-body','.source-panel .source-lines','.assistant-body','.modal .source-lines'].map(selector=>[selector,document.querySelector(selector)?.scrollTop||0]));
 const s=store.getState(),e=eNow();
 root.innerHTML='<div class="app-shell boundary-workbench"><header class="topbar"><a class="brand" href="#" data-action="home" data-focus="brand"><img src="./assets/medilisten.png" alt=""><span>MediListen</span></a><nav class="global-nav" aria-label="主要导航">'+btn('今日接诊','home',ui.view==='home'?'nav-item active':'nav-item')+btn('当前病历','encounter',ui.view==='encounter'?'nav-item active':'nav-item')+'</nav><div class="top-actions">'+btn('试用说明','help','text-button')+btn('演示控制','scenarios','text-button')+'</div></header><main id="main" data-focus="main" class="main '+(ui.view==='home'?'queue-main':'encounter-main')+'" tabindex="-1">'+(!storageOK?'<div class="recovery-banner" role="alert">演示暂存不可用，请保留页面。刷新后未保存内容可能无法恢复。</div>':'')+(ui.view==='home'?home(s):encounter(e))+'</main></div>';
 root.inert=!!ui.modal;dialogs.innerHTML=ui.modal?modalContent(e):'';for(const d of document.querySelectorAll('details'))if(openedDetails.has(d.querySelector('summary')?.dataset.focus||d.querySelector('summary')?.textContent))d.open=true;focusRestore(saved);
 for(const [selector,v]of Object.entries(scrolls)){const el=document.querySelector(selector);if(el)el.scrollTop=v;}
 ui.updatedFields.clear();
 setTimeout(()=>document.querySelectorAll('.capture-updated').forEach(el=>el.classList.remove('capture-updated')),180);
 if(s.notice?.text&&s.notice!==lastNotice){lastNotice=s.notice;notify(s.notice.text);}
}
function home(s){
 const encounters=Object.values(s.encounters),visible=encounters.filter(e=>(ui.filter==='all'||e.status===ui.filter)&&(e.patient.name+e.id).includes(ui.search));
 const active=s.encounters[s.currentId]?.status==='active'?s.encounters[s.currentId]:encounters.find(e=>e.status==='active');
 return '<section class="queue-page"><div class="page-header"><div class="title-line"><h1>今日接诊</h1><span class="muted">'+new Date().toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'long'})+'</span></div>'+btn('登记演示患者','register','secondary')+'</div>'+(active&&!ui.empty?'<div class="continue-strip"><span class="strip-label">当前接诊</span><strong>'+esc(active.patient.name)+'</strong><span>'+esc(active.patient.sex)+' · '+active.patient.age+'岁</span><span class="muted">'+phase(active)+'</span>'+btn('继续接诊','select','primary','data-id="'+active.id+'"')+'</div>':'<div class="welcome-line"><p>选择患者，开始本次问诊。</p><span class="muted">两份固定合成病例，可放心试用交互</span></div>')+'<div class="toolbar"><label class="search-label"><span class="sr-only">查找患者</span><input type="search" data-input="search" data-focus="search" value="'+esc(ui.search)+'" placeholder="搜索姓名或就诊编号"></label><div class="filters" aria-label="就诊状态">'+[['all','全部'],['waiting','待接诊'],['active','接诊中'],['completed','已完成']].map(([id,title])=>btn(title+' <span>'+(ui.empty?0:encounters.filter(e=>id==='all'||e.status===id).length)+'</span>','filter','filter '+(ui.filter===id?'active':''),'data-value="'+id+'" aria-pressed="'+(ui.filter===id)+'" data-focus="filter-'+id+'"')).join('')+'</div>'+btn('刷新','refresh','text-button')+'</div>'+(ui.empty||!visible.length?'<section class="empty-state"><h2>暂时没有匹配的就诊</h2><p class="muted">'+(ui.empty?'载入演示患者，开始体验采集与核对。':'调整搜索条件，或查看全部就诊。')+'</p>'+btn(ui.empty?'载入演示患者':'查看全部就诊',ui.empty?'load-cases':'all','primary')+'</section>':'<div class="table-wrap"><table class="encounter-table"><thead><tr><th>患者</th><th>就诊编号</th><th>状态</th><th>当前进度</th><th>操作</th></tr></thead><tbody>'+visible.map((e,i)=>'<tr class="'+(e.status==='active'?'current-row':'')+'"><td><strong>'+esc(e.patient.name)+'</strong><span class="patient-detail">'+e.patient.sex+' · '+e.patient.age+'岁</span></td><td>'+e.id+'</td><td>'+({waiting:'待接诊',active:'接诊中',completed:'已完成'}[e.status])+'</td><td>'+phase(e)+(e.revision?'<span class="patient-detail">第'+e.revision+'版 · '+(e.dirty?'未保存修改':'已保存')+'</span>':'')+'</td><td>'+btn(e.status==='completed'?'查看病历':e.status==='waiting'?'开始接诊':'查看','select',!active&&i===0?'primary':'text-button','data-id="'+e.id+'" data-focus="select-'+e.id+'"')+'</td></tr>').join('')+'</tbody></table></div>')+'<div class="list-footer"><span>共 '+(ui.empty?0:visible.length)+' 次就诊</span><span>固定合成病例 · 不用于诊疗</span></div></section>';
}
function hasVisibleDraft(e){const v=cap(e);return !e.revision&&v.roleConfirmed&&Object.values(v.fields).some(value=>String(value||'').trim());}
function generationNotice(e){
 if(e.task.status==='processing')return '<div class="record-status generation-notice" role="status"><span class="status-indicator" aria-hidden="true"></span><span>'+ (cap(e).needsRecovery?'整理暂停，等待恢复选择':e.task.connection==='online'?'正在整理病历':'连接恢复中，整理暂缓') +' · '+(hasVisibleDraft(e)?'保留当前临时稿与原文':'原文已保留，尚无可显示的病历')+'</span></div>';
 if(e.task.status==='failed')return '<div class="record-status generation-notice failed" role="alert"><span>整理未完成 · '+(hasVisibleDraft(e)?'临时稿与原文已保留':'原文已保留')+'</span></div>';
 return '';
}
function encounter(e){
 const remaining=reviewRemaining(e),v=cap(e),isLive=live(e),taskPending=['processing','failed'].includes(e.task.status);
 const state=v.needsRecovery&&!e.revision?'待恢复临时稿':e.revision?(e.dirty?'修改未保存':'第'+e.revision+'版 · '+(isApproved(e)?'已签署':'已保存')):isLive?'临时稿 · 待核对':'等待采集';
 const editAction=e.revision&&!ui.editing&&e.status!=='completed'?btn('编辑病历','edit'):isLive&&v.status!=='finished'&&!taskPending&&!v.editing&&v.roleConfirmed&&!v.needsRecovery?btn('编辑临时稿','capture-edit'):'';
 const tools=editAction+btn('问诊原文','source','secondary narrow-tool')+btn('问诊辅助','capture-assistant','secondary narrow-tool');
 const content=e.revision?record(e,remaining):(isLive&&(!taskPending||hasVisibleDraft(e)))?captureDocument(e):intake(e);
 return '<header class="patient-bar"><div class="patient-identity"><strong>'+esc(e.patient.name)+'</strong><span>'+e.patient.sex+' · '+e.patient.age+'岁</span><span class="patient-meta">就诊 '+e.id+'</span><span class="status-pill">合成演示</span></div><div class="patient-state"><span class="'+(e.dirty?'warning-text':'')+'" role="status">'+state+'</span>'+(e.revision?btn('历史版本','history','text-button'):'')+'</div></header>'+recoveryBanner(e)+(e.task.connection==='reconnecting'&&!taskPending?'<div class="connection-banner" role="status"><span>连接中断，保留当前任务与内容。</span>'+btn('恢复模拟连接','reconnect')+'</div>':'')+'<div class="workspace"><section class="record-panel panel" aria-label="当前病历"><header class="record-header"><div><div class="title-line"><h1>门诊病历</h1><span class="record-phase">'+phase(e)+'</span></div><p class="record-meta">'+(isLive?'草稿更新 '+clock(v.updatedAt):e.revision?'本次问诊记录':'记录随问诊展开')+'</p></div><div class="record-tools">'+tools+'</div></header>'+generationNotice(e)+'<div class="record-scroll">'+content+stressDocument(e)+'</div></section><div class="aux-column">'+sourcePanel(e)+assistantPanel(e)+'</div></div>'+actionBar(e,remaining);
}
function stressDocument(e){
 if(!ui.stress)return '';
 const fields=e.revision?e.fields:cap(e).fields;
 const text=fields.presentIllness||'固定合成显示样例：患者自述症状，具体持续时间及相关信息待核对。';
 return '<section class="stress-note"><h2>长内容显示样例</h2><p class="muted">以下重复合成片段仅检查滚动，不会保存、签署或导出。</p>'+Array.from({length:12},(_,i)=>'<p class="field-value">显示片段 '+(i+1)+' · '+esc(text)+'</p>').join('')+'</section>';
}
function recoveryBanner(e){const c=captures[e.id];return e.recovery?'<section class="recovery-banner" role="alert"><div><strong>有本次就诊未提交的内容</strong><p>当前显示已保存版本。恢复稿不会覆盖正式版本。</p></div>'+btn('恢复本次内容','recover','primary')+btn('放弃恢复内容','discard-recovery')+'</section>':c.needsRecovery&&!e.revision?'<section class="recovery-banner" role="alert"><div><strong>发现待恢复的采集草稿</strong><p>恢复后继续本次采集或整理；手动修改仍需保存。</p></div>'+btn('恢复采集草稿','capture-recover','primary')+btn('放弃采集草稿','capture-discard')+'</section>':'';}
function intake(e){
 if(e.task.status==='processing')return '<div class="empty-state"><span class="status-pill">正在整理</span><h2>正在形成可核对的病历</h2><p>'+ (e.task.connection==='online'?'原文已保留，约 3 秒后显示固定演示结果。':'连接恢复后继续获取当前任务结果。') +'</p>'+btn('查看原文','source')+'</div>';
 if(e.task.status==='failed')return '<div class="empty-state"><h2>这次整理未完成</h2><p>输入已保留，可以查看后重试原任务。</p>'+btn('重试整理','retry','primary')+btn('查看原文','source')+'</div>';
 if(e.task.status==='role_review')return '<div class="empty-state"><h2>先核对说话人</h2><p>确认医生提问与患者回答的归属后，继续整理。</p>'+btn('核对说话人','roles','primary')+'</div>';
 return '<div class="intake-start"><span class="eyebrow">开始本次问诊</span><h2>边问诊，边查看病历草稿</h2><p>模拟录音会逐句显示原文，同时更新临时病历与问诊提示。</p>'+btn('开始模拟录音','capture-start','primary',e.recovery?'disabled':'')+'<div class="alternative-input"><span>也可以</span>'+btn('输入问诊文本','text-input','text-button')+btn('选择演示音频','audio-input','text-button')+'</div><p class="prototype-note">本演示不调用麦克风或医疗模型。请使用合成内容。</p>'+(e.input.text?'<p class="muted">本次就诊有未提交输入，重新打开可继续。</p>':'')+'</div>';
}
function captureDocument(e){
 const v=cap(e),canMerge=!['processing','failed'].includes(e.task.status)&&v.status!=='finished';
 return (!v.roleConfirmed?'<div class="quiet-notice"><strong>先确认说话人</strong><p>原文正在逐句显示。确认身份后，开始整理临时病历与问诊提示。</p>'+btn('核对说话人','capture-roles','secondary')+'</div>':'')+(v.pending?'<div class="pending-note" role="status">有新的问诊内容待合并，手动修改保持不变。'+(!v.editing&&canMerge?btn('合并新增内容','capture-merge','text-button'):'')+'</div>':'')+Object.keys(labels).map(key=>'<article class="field '+(ui.updatedFields.has(key)?'capture-updated':'')+'" tabindex="-1" id="section-'+key+'"><div class="field-head"><h2>'+labels[key]+'</h2>'+((v.sourceIndices[key]||[]).length?btn('原文 · '+v.sourceIndices[key].length,'evidence','text-button','data-key="'+key+'" data-focus="evidence-'+key+'"'):'')+'</div>'+(v.editing?'<label class="form-field"><span class="sr-only">编辑临时'+labels[key]+'</span><textarea rows="'+(key==='presentIllness'?4:2)+'" data-input="capture-field" data-key="'+key+'" data-focus="capture-edit-'+key+'">'+esc(v.fields[key]||'')+'</textarea></label>':'<p class="field-value '+(!v.fields[key]?'placeholder-text':'')+'">'+esc(v.fields[key]||(!v.roleConfirmed?'确认说话人后开始整理':key==='diagnosis'?'待医生补充；辅助参考不会自动写入诊断':'等待更多问诊内容'))+'</p>')+(key==='presentIllness'&&v.conflict?'<p class="inline-warning"><strong>病程待核对</strong> · '+esc(v.conflict)+'</p>':'')+'</article>').join('');
}
function assistantPanel(e){return '<aside class="assistant-panel panel" aria-label="问诊辅助"><header class="panel-header"><h2>问诊辅助</h2><span class="panel-caution">待医生判断</span></header><div class="assistant-body">'+assistantContent(e)+'</div></aside>';}
function assistantContent(e,expanded=false){
 const v=cap(e),ready=e.revision>0,known=ready||v.roleConfirmed;
 const questions=ready?[!e.review.conflict?'核对本次症状开始时间':'',!e.review.missing?'补充或确认本次未采集过敏史':'',!e.review.risk?asText(caseFor(e).issues.risk):''].filter(Boolean):v.questions;
 const reference=ready?{title:caseFor(e).fields.diagnosis,body:'固定合成候选，待医生判断；不会自动写入患者事实。',evidence:'本候选来自本例固定演示结果。请结合本次原文核对；本原型未检索临床指南。'}:v.reference;
 const meta=ready?(isApproved(e)?'本版已签署，以下参考仍为合成演示':'核对阶段 · 参考与病历分开'):(v.connection==='reconnecting'?'提示更新暂停，保留中断前内容':v.updatedAt?'更新于 '+clock(v.updatedAt):'采集后提供本例提示');
 if(!expanded)return '<section class="aux-summary"><div class="aux-heading"><h3>待追问'+(known&&questions.length?' <span>'+questions.length+' 项</span>':'')+'</h3>'+btn('展开','assistant-detail','text-button','data-section="questions" data-focus="assistant-questions" aria-label="展开待追问"')+'</div><p>'+esc(!known?'确认说话人后更新':questions[0]||(ready?'本版核对事项已处理':'等待更多问诊内容'))+'</p></section><section class="aux-summary"><div class="aux-heading"><h3>诊疗参考</h3>'+btn('依据','assistant-detail','text-button','data-section="reference" data-focus="assistant-reference" aria-label="查看诊疗参考与依据"')+'</div><p class="reference-title">'+esc(known&&reference?reference.title:'等待更多问诊信息')+'</p></section>'+(v.connection==='reconnecting'?'<p class="record-meta">提示更新暂停，内容保留</p>':'');
 return '<p class="record-meta">'+meta+'</p><section class="aux-section"><h3>待追问</h3>'+(!known?'<p class="muted">确认说话人后更新问诊提示。</p>':questions.length?'<ul>'+questions.map(q=>'<li>'+esc(q)+'</li>').join('')+'</ul>':'<p class="muted">'+(ready?'本版核对事项已处理。':'等待更多问诊内容。')+'</p>')+'</section><section class="aux-section"><h3>诊疗参考</h3>'+(known&&reference?'<p class="diagnosis-status">待医生判断 · 合成示例</p><strong class="reference-title">'+esc(reference.title)+'</strong><p>'+esc(reference.body)+'</p><details><summary data-focus="reference-details">查看依据与限制</summary><p>'+esc(reference.evidence)+'</p><p class="muted">不是诊疗建议，不自动写入确诊；医生须自行核对。</p></details>':'<p class="muted">采集更多信息后显示本例固定参考；不会自动形成诊断。</p>')+'</section>'+(ui.stress?'<section class="aux-section stress-note"><h3>长内容显示样例</h3><p class="muted">仅检查滚动，不写入病历。</p>'+Array.from({length:8},(_,i)=>'<p>显示提示 '+(i+1)+'：核对当前就诊、信息来源与待确认事项。本段为重复合成文字。</p>').join('')+'</section>':'');
}
function sourcePanel(e){
 const v=cap(e),isLive=live(e)&&!e.revision;
 const meta=isLive?(v.roleConfirmed?'说话人已确认':'说话人待确认')+' · '+v.revealed+' / '+v.totalLines+' 句':(e.input.roleConfirmed?'说话人已确认':'说话人待确认')+' · '+sourceData(e).length+' 句';
 return '<aside class="source-panel panel" aria-label="问诊原文"><header class="panel-header"><div><h2>问诊原文</h2><p class="record-meta">'+meta+'</p></div><span class="status-pill">只读</span></header>'+sourceLines(e)+'</aside>';
}
function sourceData(e){if(live(e)&&!e.revision&&e.task.status!=='ready')return cap(e).lines;return(e.input.text||'').split('\n').filter(Boolean).map((line,index)=>({index,role:/^【医生】/.test(line)?'医生':/^【患者】/.test(line)?'患者':/^【演示说明】/.test(line)?'演示说明':'原文',text:line.replace(/^\[.*?\]\s*|^【.*?】\s*/,'')}));}
function sourceLines(e){
 const lines=sourceData(e),warning=e.revision&&e.input.text!==caseFor(e).text?'<p class="quiet-notice">这份病历为固定合成结果，与自填文本没有自动证据映射；以下输入不能视为生成结果的依据。</p>':'';
 const content=lines.length?lines.map(line=>'<div class="source-line '+(ui.sourceIndices.includes(line.index)?'selected':'')+'" data-source-index="'+line.index+'"><span class="source-role">'+esc(line.role)+'</span><p>'+esc(line.text)+'</p></div>').join(''):'<p class="muted">问诊开始后，原文会显示在这里。</p>';
 const stress=ui.stress?'<section class="stress-note"><h3>长原文显示样例</h3><p class="muted">以下重复合成片段仅检查滚动，不作为病历来源。</p>'+Array.from({length:14},(_,i)=>'<div class="source-line"><span class="source-role">显示片段 '+(i+1)+'</span><p>'+esc(lines[i%Math.max(lines.length,1)]?.text||'固定合成问诊文字，仅检查滚动。')+'</p></div>').join('')+'</section>':'';
 return '<div class="source-lines">'+warning+content+stress+'</div>';
}
function record(e,remaining){return (isApproved(e)?'<div class="signed-note"><span>第'+e.revision+'版已签署</span>'+btn('查看签署记录','signature','text-button')+'</div>':'')+Object.keys(labels).map(key=>field(e,key)).join('');}
function field(e,key){const issues=Object.keys(issueField).filter(kind=>issueField[kind]===key);return '<article class="field" tabindex="-1" id="section-'+key+'" aria-label="'+labels[key]+'"><div class="field-head"><h2>'+labels[key]+'</h2>'+btn(['allergies','diagnosis'].includes(key)?'核对说明':(evidenceIndices(e,key).length?'原文 · '+evidenceIndices(e,key).length:'查看输入原文'),'evidence','text-button','data-key="'+key+'" data-focus="evidence-'+key+'"')+'</div>'+(ui.editing?'<label class="form-field"><span class="sr-only">编辑'+labels[key]+'</span><textarea data-input="field" data-key="'+key+'" data-focus="edit-'+key+'" rows="'+(key==='presentIllness'?4:2)+'">'+esc(e.fields[key])+'</textarea></label>':(key==='diagnosis'?'<p class="diagnosis-status">'+(e.fields.diagnosis===caseFor(e).fields.diagnosis?({adopt:'已核对候选 · 非自动确诊',reject:'该候选不采纳',defer:'候选暂缓判断'}[e.review.diagnosis]||'待判断候选 · 尚未确诊'):(isApproved(e)?'医生已签署':'医生编辑 · 待签署'))+'</p>':'')+'<p class="field-value">'+esc(e.fields[key])+'</p>')+(ui.evidence===key&&['allergies','diagnosis'].includes(key)?'<p class="inline-evidence">'+esc(evidenceText(e,key))+'</p>':'')+(!ui.editing?issues.map(kind=>issue(e,kind)).join(''):'')+'</article>';}
function evidenceIndices(e,key){if(live(e)&&!e.revision)return cap(e).sourceIndices[key]||[];if(['allergies','diagnosis'].includes(key)||e.input.text!==caseFor(e).text)return [];return sourceData(e).filter(line=>line.role==='患者'&&(key==='presentIllness'||line.index===1||line.index===5||(e.id==='syn-001'&&line.index===3))).map(line=>line.index);}
function evidenceText(e,key){if(key==='allergies')return '本次未采集过敏史，没有对应患者原话；未采集不代表无过敏。';if(key==='diagnosis')return '诊断意见须由医生判断，不能把辅助参考作为患者已确诊事实。';return sourceData(e).filter(l=>evidenceIndices(e,key).includes(l.index)).map(l=>l.text).join('\n')||'本次未采集对应原文。';}
function issue(e,kind){const value=e.review[kind],active=ui.activeIssue===kind;if(isApproved(e))return '';if(value)return '<div class="resolved"><span>'+issueLabels[kind]+' · '+esc(decisionLabels[value])+'</span>'+btn('重新核对','undo-review','text-button','data-kind="'+kind+'" data-focus="undo-'+kind+'"')+'</div>';if(!active)return '<div class="issue-collapsed"><span>'+issueLabels[kind]+'</span>'+btn('核对此项','open-issue','text-button','data-kind="'+kind+'" data-focus="open-'+kind+'"')+'</div>';const choices={missing:[['not_collected','确认本次未采集']],conflict:[['source_verified','保留原文差异'],['doctor_corrected','已按原文修正']],diagnosis:[['adopt','保留候选'],['reject','不采纳'],['defer','暂缓判断']],risk:[['reviewed','已核对此提醒']]};return '<div class="field-issue '+(kind==='conflict'?'warning-issue':'')+'" id="issue-'+kind+'" tabindex="-1"><strong>'+issueLabels[kind]+'</strong><p>'+esc(asText(caseFor(e).issues[kind]))+'</p><div class="issue-actions">'+choices[kind].map(([v,t])=>btn(t,'review','secondary','data-kind="'+kind+'" data-value="'+v+'" data-focus="review-'+kind+'-'+v+'" '+(e.dirty?'disabled':''))).join('')+'</div></div>';}
function actionBar(e,remaining){
 let actions='',status='',v=cap(e);
 if(e.recovery||(!e.revision&&v.needsRecovery))return '<footer class="action-bar"><span>请先处理上方恢复草稿</span></footer>';
 if(e.task.status==='processing'){status='正在整理 · 原文与当前内容保留';if(e.task.connection==='reconnecting')actions=btn('恢复模拟连接','reconnect','primary');}
 else if(e.task.status==='failed'){status='整理失败 · 内容已保留';actions=btn('重试整理','retry','primary');}
 else if(live(e)&&!e.revision){
  const played=v.revealed>=v.totalLines;
  status='<strong>'+(played?'本例对话已播完':({running:'模拟录音中',paused:'模拟已暂停',finished:'采集已结束'}[v.status]||'准备录音'))+'</strong> <span class="timer">'+duration(v.elapsed)+'</span><span class="recording-meta">'+v.revealed+' / '+v.totalLines+' 句 · '+(v.roleConfirmed?'身份已确认':'身份待确认')+'</span>';
  if(v.editing)actions=btn('结束临时编辑','capture-edit-done','primary');
  else if(v.connection==='reconnecting')actions=btn('恢复模拟连接','reconnect','primary');
  else if(v.status==='finished')actions=btn('继续整理病历','capture-finish','primary');
  else if(!v.roleConfirmed)actions=(!played?btn('暂停','capture-pause','secondary',v.status==='running'?'':'disabled'):'')+btn('确认说话人','capture-roles','primary');
  else if(played)actions=v.pending?btn('合并新增内容','capture-merge','primary'):btn('结束采集，进入核对','capture-finish','primary',v.canFinish?'':'disabled');
  else actions=btn(v.status==='running'?'暂停':'继续播放',v.status==='running'?'capture-pause':'capture-resume','secondary')+btn('下一句','capture-next','secondary',v.revealed>=v.totalLines?'disabled':'')+(v.pending?btn('合并新增内容','capture-merge','primary'):btn('结束采集，进入核对','capture-finish','primary',v.canFinish?'':'disabled'));
 }else if(ui.editing){status='正在编辑 · '+(e.dirty?'修改未保存':'尚无修改');actions=btn('放弃本次修改','discard-edit')+btn('保存修改','save','primary',e.dirty?'':'disabled');}
 else if(e.status==='completed'){status='本次接诊已完成 · 第'+e.revision+'版';actions=btn('导出回执','export')+btn('返回接诊列表','home','primary');}
 else if(isApproved(e)){status='第'+e.revision+'版已签署';const exported=e.exports.some(x=>x.revision===e.revision);actions=exported?btn('查看导出回执','export')+btn('完成接诊，返回列表','complete','primary',canComplete(e)?'':'disabled'):btn('导出病历','export','primary');}
 else if(e.revision){status='<strong>已核对 '+(4-remaining.length)+' / 4</strong><span class="recording-meta">决定尚未提交</span>';actions=canSign(e)?btn('签署第'+e.revision+'版','sign','primary'):btn('下一待核对项','next-issue','primary');}
 else status=e.task.status==='processing'?'固定合成草稿整理中':'输入仅用于当前就诊';
 return '<footer class="action-bar"><div class="action-status" role="status">'+status+'</div><div class="action-buttons">'+actions+'</div></footer>';
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
  } else if(m.type==='capture-assistant') {title='问诊辅助';body='<p class="patient-context">'+esc(e.patient.name)+' · 就诊 '+e.id+'</p>'+assistantContent(e,true);footer=btn('返回病历','close','primary');
  } else if(m.type==='capture-roles') {title='确认说话人';body='<p class="patient-context">'+esc(e.patient.name)+' · 就诊 '+e.id+'</p><p>本合成对话的说话人 A 为医生，说话人 B 为患者。确认后才开始整理临时病历。</p>'+sourceLines(e);footer=btn('返回','close')+btn('A 是医生，B 是患者','capture-confirm-roles','primary');
  } else if(m.type==='register') {title='登记演示患者';body='<p>本原型仅使用两位固定合成患者，避免真实资料进入演示会话。</p><p>返回列表后可选择患者甲或患者乙开始接诊。</p>';footer=btn('返回','close')+btn('显示演示患者','load-cases','primary');
  } else if(m.type==='roles') {
    title='核对说话人';body='<p>请核对医生提问和患者回答的归属。这里是固定的合成转写。</p>'+sourceLines(e);footer=btn('返回','close')+btn('身份正确，继续整理','confirm-roles','primary');
  } else if(m.type==='source') {title='问诊原文';body='<p class="patient-context">'+esc(e.patient.name)+' · 就诊 '+e.id+'</p>'+sourceLines(e)+(live(e)&&Object.keys(cap(e).editedFields).length?'<p class="muted">原文用于核对采集上下文，不代表手动修改已被验证。</p>':'');footer=btn('返回病历','close','primary');
  } else if(m.type==='reference') {title='诊疗参考';body='<p>参考内容帮助医生判断，不会自动写入患者事实。</p><h3>当前病例的核对重点</h3><p>结合原文检查症状、持续时间、否定信息与过敏史；未询问的内容应保持未采集。</p><p class="muted">这是一段交互演示说明，不是临床指南或诊疗建议。</p>';footer=btn('返回病历','close','primary');
  } else if(m.type==='history') {
    title='历史版本';const revisions=e.revisions;const index=ui.historyIndex??Math.max(0,revisions.length-2);const old=revisions[index];
    body='<p>只读对照，不替换当前病历。</p><label class="form-field">选择版本<select data-input="history" data-focus="history">'+revisions.map((r,i)=>'<option value="'+i+'" '+(i===index?'selected':'')+'>版本 '+(r.revision||r.number||i+1)+'</option>').join('')+'</select></label><div class="history-grid"><section><h3>所选版本</h3>'+Object.keys(labels).map(key=>'<h4>'+labels[key]+'</h4><p>'+esc(old?.fields?.[key])+'</p>').join('')+'</section><section><h3>当前版本 '+e.revision+'</h3>'+Object.keys(labels).map(key=>'<h4>'+labels[key]+'</h4><p>'+esc(e.revisions.at(-1)?.fields[key])+'</p>').join('')+'</section></div>';footer=btn('返回当前病历','close','primary');
  } else if(m.type==='signature') {title='签署记录';body='<p>就诊 '+e.id+' · 版本 '+e.revision+'</p><p>本页演示医生已确认当前保存版本。</p>'+Object.entries(e.review).map(([k,v])=>'<p>'+issueLabels[k]+'：'+esc(decisionLabels[v])+'</p>').join('');footer=btn('返回病历','close','primary');
  } else if(m.type==='export') {
    title='病历文件已生成';const x=e.exports.find(x=>x.revision===e.revision);
    const feedback=x?.status==='failed'?'下载未开始，文件仍可重试。':x?.status==='downloaded'?'已发起浏览器下载，请在下载列表确认。':'文件已准备好，尚未下载。';
    body='<div class="receipt"><p class="download-state" role="status">'+feedback+'</p><p class="status-pill success">版本已签署 · 文件已生成</p><dl class="receipt-grid"><div class="receipt-item"><dt>患者 / 就诊</dt><dd>'+esc(e.patient.name)+' / '+e.id+'</dd></div><div class="receipt-item"><dt>病历版本</dt><dd>版本 '+x?.revision+'</dd></div><div class="receipt-item"><dt>签署时间</dt><dd>'+time(x?.approval?.signedAt)+'</dd></div><div class="receipt-item"><dt>生成时间</dt><dd>'+time(x?.generatedAt)+'</dd></div><div class="receipt-item"><dt>文件</dt><dd>'+esc(x?.filename||e.id+'-R'+e.revision+'-演示病历.txt')+'</dd></div></dl><p class="muted">下载的是带“合成演示”标记的文本文件；生产 PDF 排版不在本原型中模拟。</p></div>';footer=btn('返回病历','close')+(e.status==='completed'?btn('再次下载','download')+btn('返回接诊列表','home','primary'):x?.status==='downloaded'?btn('再次下载','download')+btn('完成接诊','complete','primary'):btn(x?.status==='failed'?'重试下载':'下载演示病历','download','primary')+btn('完成接诊','complete'));
  } else if(m.type==='leave') {title='保留这次接诊的内容';body='<p>'+esc(e.patient.name)+' 的未提交内容会保留在本次就诊。继续切换不会保存或签署病历。</p>';footer=btn('留在本次就诊','close','primary')+btn('暂存并离开','confirm-leave')+btn('放弃未提交内容并离开','discard-leave','danger');
  } else if(m.type==='discard-edit') {title='放弃本次修改？';body='<p>将恢复最近保存的版本，未保存编辑会被丢弃。你也可以继续编辑。</p>';footer=btn('继续编辑','close','primary')+btn('确认放弃修改','confirm-discard','danger');
  } else if(m.type==='save-conflict') {title='保存版本需要核对';body='<p>模拟发现服务器有较新版本。当前编辑已保留，尚未覆盖任何保存版本。</p><p>原型中可解除模拟冲突，再继续保存；生产流程须展示实际版本差异。</p>';footer=btn('保留编辑，返回','close','primary')+btn('解除模拟冲突','resolve-conflict');
  } else if(m.type==='help') {title='试用这条接诊流程';body='<ol><li>选择一位合成患者，开始模拟录音并确认说话人。</li><li>每四秒显示一句，也可暂停后点击下一句；观察病历和问诊辅助更新。</li><li>结束采集后进入核对，也可从文本或演示音频开始。</li><li>整理后查看原文，修改并保存病历。</li><li>处理四类核对项目，签署当前版本。</li><li>生成文件、下载并完成本次接诊。</li></ol><p>可在“演示场景”中检查断连、失败、冲突和刷新恢复。</p><p>仅合成病例会暂存在当前浏览器标签页。刷新后须明确恢复未提交内容；浏览器可能恢复已关闭标签页的会话；明确清除请使用重置演示。请勿输入真实患者资料。</p><p>原文可固定并排；窄屏通过原文面板核对并返回。</p>';footer=btn('开始试用','close','primary');
  } else if(m.type==='scenarios') {title='演示场景';body='<p>这些按钮只改变原型的合成状态，不影响业务系统。</p><div class="scenario-grid">'+btn('空就诊列表','empty')+btn('载入演示患者','load-cases')+btn('模拟连接中断','disconnect')+btn('恢复连接','reconnect')+btn('下次生成失败','fail-next')+btn('模拟保存冲突','inject-conflict')+btn('模拟下载失败','fail-download')+btn(ui.stress?'关闭长内容样例':'显示长内容样例','stress')+btn('查看本次操作计数','metrics')+btn('重置全部演示','reset','danger')+'</div>';footer=btn('返回','close','primary');
  } else if(m.type==='replace-input') {title='改用模拟录音？';body='<p>本次就诊已有未提交的文本或演示音频。开始模拟录音会清除这份输入，随后使用固定合成问诊。</p>';footer=btn('保留原输入','close','primary')+btn('清除输入，开始模拟','confirm-capture-start');
  } else if(m.type==='reset-confirm') {title='重置演示？';body='<p>将清除这两个合成病例的演示进度。真实业务数据不受影响。</p>';footer=btn('保留进度','close','primary')+btn('确认重置演示','confirm-reset','danger');
  } else if(m.type==='metrics') {title='本次原型操作记录';body='<p>点击次数：'+ui.metrics.clicks+'</p><p>原文查看：'+ui.metrics.evidenceOpens+'</p><p>辅助面板打开：'+ui.metrics.panelSwitches+'</p><p class="muted">计数从本次载入页面开始，刷新重置；不是医生效率或满意度结果。</p>';footer=btn('返回','close','primary');}
  return '<div class="modal-backdrop"><section class="modal '+(['history','roles'].includes(m.type)?'wide':'')+'" role="dialog" aria-modal="true" aria-labelledby="dialog-title"><header class="modal-header"><h2 id="dialog-title" data-focus="dialog-title" tabindex="-1">'+title+'</h2>'+btn('关闭','close','text-button','aria-label="关闭面板"')+'</header><div class="modal-body">'+body+'</div><footer class="modal-footer">'+footer+'</footer></section></div>';
}

function openModal(type,extra={}) {
  if(!ui.modal)ui.focus=focusSnapshot();ui.modal={type,...extra};ui.metrics.panelSwitches++;render();
  const target=dialogs.querySelector('textarea,select')||dialogs.querySelector('#dialog-title');target?.focus();
}
function closeModal() {ui.modal=null;render();focusRestore(ui.focus);}
function choose(id) {store.dispatch({type:'SELECT',id});if(eNow().status==='waiting')store.dispatch({type:'START'});ui.view='encounter';ui.editing=false;ui.evidence=null;ui.activeIssue=null;ui.sourceIndices=[];render();document.querySelector('#main')?.focus();}
function navigate(target,id) {
  if(ui.view==='encounter' && hasPending(eNow()) && !eNow().recovery && (target==='home'||id!==eNow().id)) {openModal('leave',{target,id});return;}
  if(id) choose(id);else {ui.view=target;render();}
}
function finishCapture(){
  if(captures[eNow().id].status!=='finished')sendCapture('FINISH');
  const e=eNow(),v=cap(e);if(v.status!=='finished'||v.needsRecovery||!v.finishedText)return;
  store.dispatch({type:'SET_INPUT',kind:'recording',text:v.finishedText});
  store.dispatch({type:'CONFIRM_ROLES'});store.dispatch({type:'GENERATE'});
}
function generate() {
  if(!eNow().input.text.trim()){notify('请先输入问诊文本或选择演示音频。');return;}
  closeModal();store.dispatch({type:'GENERATE'});
  if(eNow().task.status==='role_review')openModal('roles');
}
function scheduleGeneration(s) {
  for(const e of Object.values(s.encounters)) {
    if(e.task.status!=='processing'||timers.has(e.task.id)||captures[e.id].needsRecovery)continue;
    const id=e.task.id,encounterId=e.id,fail=ui.failNext;ui.failNext=false;
    timers.set(id,setTimeout(()=>{
      timers.delete(id);store.dispatch({type:fail?'GENERATION_FAILED':'GENERATION_DONE',taskId:id,encounterId});
      const now=store.getState().encounters[encounterId];
      if(!fail&&now.task.status==='ready'&&captures[encounterId].status==='finished'){
        const edits=captureSnapshot(captures[encounterId]).editedFields;
        for(const [key,value]of Object.entries(edits))store.dispatch({type:'EDIT_FIELD',key,value,encounterId});
        captures[encounterId]=createCapture(encounterId);persist();
        if(eNow().id===encounterId){ui.editing=store.getState().encounters[encounterId].dirty;render();if(ui.editing)notify('临时手动修改已带入当前病历，尚未保存。请核对并保存。');}
      }
    },3000));
  }
}
function goIssue() {
  const kind=['conflict','missing','diagnosis','risk'].find(k=>!eNow().review[k]);if(!kind)return;ui.activeIssue=kind;render();
   const el=document.getElementById('issue-'+kind);el?.scrollIntoView({block:'center',behavior:motionBehavior()});el?.focus({preventScroll:true});
}
function download() {
  const e=eNow(),x=e.exports.find(x=>x.revision===e.revision);if(!x)return;
  if(!isApproved(e)){notify('请先签署当前版本。');return;}
  const text=['MediListen 合成演示病历 · 不用于诊疗',e.patient.name+' / '+e.id,'版本 '+x.revision,'',...Object.keys(labels).map(k=>labels[k]+'：'+x.fields[k]),'', '本版核对决定（合成演示）',...Object.entries(x.approval.review).map(([k,v])=>issueLabels[k]+'：'+decisionLabels[v])].join('\n');
  const url=URL.createObjectURL(new Blob([text],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download=x.filename||e.id+'-R'+x.revision+'-演示病历.txt';a.click();setTimeout(()=>URL.revokeObjectURL(url),3000);store.dispatch({type:'DOWNLOAD',exportId:x.id});
}

document.addEventListener('click',event=>{
  const target=event.target.closest('[data-action]');if(!target||target.disabled)return;event.preventDefault();ui.metrics.clicks++;
  const a=target.dataset.action,e=eNow();
  switch(a){
    case 'stress':ui.stress=!ui.stress;closeModal();notify(ui.stress?'已显示长内容样例；不写入病历、保存或导出。':'已恢复本例内容。');break;
    case 'capture-assistant':openModal('capture-assistant');break;
    case 'assistant-detail':openModal('capture-assistant');if(target.dataset.section==='reference'){const section=dialogs.querySelectorAll('.aux-section')[1];section?.querySelector('details')?.setAttribute('open','');section?.scrollIntoView({block:'start',behavior:motionBehavior()});}break;
    case 'home':if(ui.modal)closeModal();navigate('home');break;
    case 'encounter':if(e.status==='waiting'){notify('请先从今日接诊选择患者。');break;}ui.view='encounter';render();break;
    case 'select':navigate('encounter',target.dataset.id);break;
    case 'confirm-leave':{const m=ui.modal;if(live(e))sendCapture('PAUSE');store.dispatch({type:'STASH_DRAFT'});if(!persist()){notify('暂存失败，请继续本次接诊。');break;}closeModal();if(m.id)choose(m.id);else{ui.view=m.target;render();}break;}
    case 'discard-leave':{const m=ui.modal;captures[e.id]=createCapture(e.id);store.dispatch({type:'DISCARD_DRAFT'});closeModal();if(m.id)choose(m.id);else{ui.view=m.target;render();}break;}
    case 'filter':ui.filter=target.dataset.value;render();break;
    case 'all':ui.filter='all';ui.search='';render();break;
    case 'empty':ui.empty=true;closeModal();navigate('home');break;
    case 'load-cases':ui.empty=false;ui.filter='all';ui.search='';closeModal();navigate('home');break;
    case 'text-input':openModal('text');break;
    case 'audio-input':openModal('audio');break;
    case 'record-input':case 'capture-start':if(e.recovery){notify('请先处理恢复内容。');break;}if(e.input.text.trim()&&captures[e.id].status==='idle'){openModal('replace-input');break;}sendCapture('START');render();break;
    case 'confirm-capture-start':store.dispatch({type:'SET_INPUT',kind:'recording',text:''});closeModal();sendCapture('START');render();break;
    case 'capture-pause':sendCapture('PAUSE');break;
    case 'capture-resume':sendCapture('RESUME');break;
    case 'capture-next':sendCapture('NEXT');break;
    case 'capture-roles':openModal('capture-roles');break;
    case 'capture-confirm-roles':closeModal();sendCapture('CONFIRM_ROLES');break;
    case 'capture-edit':sendCapture('BEGIN_EDIT');document.querySelector('[data-focus="capture-edit-chiefComplaint"]')?.focus();break;
    case 'capture-edit-done':sendCapture('END_EDIT');break;
    case 'capture-merge':sendCapture('APPLY_PENDING');break;
    case 'capture-recover':sendCapture('RECOVER');scheduleGeneration(store.getState());break;
    case 'capture-discard':sendCapture('DISCARD_RECOVERY');scheduleGeneration(store.getState());break;
    case 'capture-finish':finishCapture();break;
    case 'start-recording':ui.modal.recording=true;render();break;
    case 'stop-recording':ui.modal.recording=false;store.dispatch({type:'SET_INPUT',kind:'recording',text:caseFor(e).text});notify('模拟录音已结束，请继续整理。');break;
    case 'sample':store.dispatch({type:'SET_INPUT',kind:'text',text:caseFor(e).text});break;
    case 'generate':generate();break;
    case 'roles':openModal('roles');break;
    case 'confirm-roles':closeModal();store.dispatch({type:'CONFIRM_ROLES'});store.dispatch({type:'GENERATE'});break;
    case 'retry':store.dispatch({type:'RETRY'});break;
    case 'source':openModal('source');break;
    case 'reference':openModal('reference');break;
    case 'evidence':ui.evidence=target.dataset.key;ui.sourceIndices=evidenceIndices(e,target.dataset.key);ui.metrics.evidenceOpens++;if(['allergies','diagnosis'].includes(target.dataset.key)){render();break;}if(!split()){openModal('source');}else{render();}document.querySelector((ui.modal?'.modal ':'.source-panel ')+'.source-line.selected')?.scrollIntoView({block:'nearest',behavior:motionBehavior()});break;
    case 'open-issue':ui.activeIssue=target.dataset.kind;render();document.getElementById('issue-'+ui.activeIssue)?.focus({preventScroll:true});break;
    case 'section':document.getElementById('section-'+target.dataset.target)?.scrollIntoView({block:'start',behavior:motionBehavior()});break;
    case 'next-issue':goIssue();break;
    case 'edit':if(e.status==='completed'){notify('已完成的就诊保持只读。');break;}if(e.recovery){notify('请先处理待恢复内容。');break;}ui.editing=true;ui.editKey=target.dataset.key||'chiefComplaint';render();document.querySelector('[data-focus="edit-'+(target.dataset.key||'chiefComplaint')+'"]')?.focus();break;
    case 'save':store.dispatch({type:'SAVE'});if(eNow().saveConflict)openModal('save-conflict');else if(!eNow().dirty){ui.editing=false;render();document.querySelector('[data-focus="edit"]')?.focus({preventScroll:true});}break;
    case 'discard-edit':if(e.dirty)openModal('discard-edit');else{ui.editing=false;render();}break;
    case 'confirm-discard':store.dispatch({type:'DISCARD_EDITS'});ui.editing=false;closeModal();break;
    case 'undo-review':ui.activeIssue=target.dataset.kind;store.dispatch({type:'REVIEW',kind:target.dataset.kind,value:null});break;
    case 'review':store.dispatch({type:'REVIEW',kind:target.dataset.kind,value:target.dataset.value});if(eNow().review[target.dataset.kind])document.querySelector('[data-focus="'+(canSign(eNow())?'sign':'next-issue')+'"]')?.focus({preventScroll:true});break;
    case 'sign':store.dispatch({type:'SIGN'});render();document.querySelector('.record-scroll')?.scrollTo({top:0});document.querySelector('[data-focus="export"]')?.focus({preventScroll:true});break;
    case 'export':{store.dispatch({type:'CREATE_EXPORT'});const next=eNow();if(store.getState().notice?.kind!=='error' && isApproved(next) && next.exports.some(x=>x.revision===next.revision))openModal('export');break;}
    case 'download':download();break;
    case 'complete':store.dispatch({type:'COMPLETE'});if(eNow().status==='completed'){ui.view='home';closeModal();document.querySelector('#main')?.focus();}break;
    case 'recover':store.dispatch({type:'RECOVER_DRAFT'});ui.editing=eNow().dirty;render();break;
    case 'discard-recovery':store.dispatch({type:'DISCARD_RECOVERY'});break;
    case 'history':ui.historyIndex=null;openModal('history');break;
    case 'signature':openModal('signature');break;
    case 'disconnect':if(live(e)&&!e.revision)sendCapture('DISCONNECT');store.dispatch({type:'DISCONNECT'});closeModal();break;
    case 'reconnect':if(live(e)&&!e.revision)sendCapture('RECONNECT');store.dispatch({type:'RECONNECT'});closeModal();break;
    case 'fail-next':ui.failNext=true;closeModal();notify('下一次整理将模拟失败，原始输入会保留。');break;
    case 'inject-conflict':store.dispatch({type:'INJECT_SAVE_CONFLICT'});closeModal();notify('下一次保存将显示模拟冲突。');break;
    case 'resolve-conflict':store.dispatch({type:'RESOLVE_SAVE_CONFLICT'});closeModal();break;
    case 'fail-download':if(e.exports.some(x=>x.revision===e.revision)){store.dispatch({type:'DOWNLOAD',exportId:e.exports.find(x=>x.revision===e.revision).id,fail:true});openModal('export');}else{notify('请先签署并生成演示文件。');}break;
    case 'reset':openModal('reset-confirm');break;
    case 'confirm-reset':for(const timer of timers.values())clearTimeout(timer);timers.clear();captures=Object.fromEntries(CASES.map(c=>[c.id,createCapture(c.id)]));store.dispatch({type:'RESET'});ui.view='home';ui.editing=false;ui.empty=false;ui.activeIssue=null;ui.sourceIndices=[];closeModal();break;
    case 'register':case 'scenarios':case 'help':case 'metrics':openModal(a);break;
    case 'refresh':render();notify('演示列表已刷新，当前进度保持不变。');break;
    case 'close':closeModal();break;
  }
});
document.addEventListener('input',event=>{
  const el=event.target;
  if(el.dataset.input==='search'){ui.search=el.value;render();}
  if(el.dataset.input==='conversation')store.dispatch({type:'SET_INPUT',kind:'text',text:el.value});
  if(el.dataset.input==='field')store.dispatch({type:'EDIT_FIELD',key:el.dataset.key,value:el.value});
  if(el.dataset.input==='capture-field')sendCapture('EDIT_FIELD',{key:el.dataset.key,value:el.value});
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
    const focusables=[...dialogs.querySelectorAll('button:not(:disabled),input,select,textarea,summary,[tabindex="0"]')].filter(el=>el.getClientRects().length);
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
setInterval(()=>{
  let changed=false,redraw=false;
  for(const [id,c]of Object.entries(captures))if(c.status==='running'&&!c.needsRecovery){
    let next=captureReducer(c,{type:'TICK',at:new Date().toISOString()});
    if(next.revealed>=captureSnapshot(next).totalLines)next=captureReducer(next,{type:'PAUSE'});
    captures[id]=next;changed=true;
     if(id===eNow().id&&(next.revealed!==c.revealed||next.appliedCount!==c.appliedCount)){markCaptureUpdates(c,next,id);redraw=true;}
  }
  if(changed){persist();if(redraw)render();else{const timer=document.querySelector('.timer');if(timer)timer.textContent=duration(captures[eNow().id].elapsed);}}
},1000);
