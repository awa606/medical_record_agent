/** Isolated synthetic interaction model. No network, clinical engine or production storage. */
export const FIELD_DEFS = Object.freeze([
  { key: 'chiefComplaint', label: '主诉' },
  { key: 'presentIllness', label: '现病史' },
  { key: 'allergies', label: '过敏史' },
  { key: 'diagnosis', label: '诊断意见' },
]);

export const CASES = Object.freeze([
  {
    id: 'syn-001', patient: { name: '合成患者甲', age: 32, sex: '女' },
    text: `【医生】今天哪里不舒服？
【患者】我咳嗽两天了，没有胸痛。
【医生】有没有发热？
【患者】昨晚有些发热。
【医生】咳嗽具体持续了多久？
【患者】好像也有三天了，记不太清。
【演示说明】以上为固定合成对话；过敏史未询问，病程“2天”和“3天”需要核对。`,
    fields: { chiefComplaint: '咳嗽伴发热2天', presentIllness: '患者自述咳嗽2天，昨晚发热，否认胸痛。原文另有3天的说法，病程待核对。', allergies: '本次未采集', diagnosis: '上呼吸道感染（合成示例，待医生判断）' },
    issues: { missing: '过敏史未采集，请补充或明确记录本次未采集。', conflict: '病程出现“2天”和“3天”，请核对本次问诊原文。', diagnosis: '上呼吸道感染为模拟候选，请明确采纳、排除或暂缓判断。', risk: '用药前需核对过敏史；此提示仅演示逐项核对交互。' },
  },
  {
    id: 'syn-002', patient: { name: '合成患者乙', age: 46, sex: '男' },
    text: `【医生】今天哪里不舒服？
【患者】右膝走路后疼痛一周了。
【医生】有没有外伤或者发热？
【患者】没有明确外伤，也没有发热。
【医生】持续多久了？以前确诊过膝关节病吗？
【患者】大概十天。我母亲以前有膝关节病，但我本人没有确诊过。
【演示说明】以上为固定合成对话；既往用药和过敏史未记录，家属信息不能记为患者确诊。`,
    fields: { chiefComplaint: '右膝活动后疼痛1周', presentIllness: '患者自述右膝活动后疼痛，否认明确外伤及发热；病程另述10天，需核对。母亲的膝关节病为家属信息，不能记为患者既往确诊。', allergies: '本次未采集', diagnosis: '膝关节疼痛待查（合成示例，待医生判断）' },
    issues: { missing: '过敏史未采集，请补充或明确记录本次未采集。', conflict: '病程出现“1周”和“10天”，请核对本次问诊原文。', diagnosis: '膝关节疼痛待查为模拟候选，请明确采纳、排除或暂缓判断。', risk: '既往用药未核对；此提示仅演示逐项核对交互。' },
  },
]);

export const REVIEW_OPTIONS = Object.freeze({
  missing: ['not_collected', 'supplemented'],
  conflict: ['source_verified', 'doctor_corrected'],
  diagnosis: ['adopt', 'reject', 'defer'],
  risk: ['reviewed'],
});

const clone = value => JSON.parse(JSON.stringify(value));
const emptyFields = () => Object.fromEntries(FIELD_DEFS.map(({ key }) => [key, '']));
const emptyReview = () => ({ missing: null, conflict: null, diagnosis: null, risk: null });
const emptyInput = () => ({ kind: 'text', text: '', roleConfirmed: true });
const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const hasReview = review => Object.values(review).some(Boolean);
const seedFor = id => CASES.find(item => item.id === id);

export function createInitialState() {
  return {
    schemaVersion: 1, synthetic: true, userId: 'demo-doctor', currentId: CASES[0].id,
    encounters: Object.fromEntries(CASES.map(item => [item.id, {
      id: item.id, patient: clone(item.patient), status: 'waiting', input: emptyInput(),
      task: { id: null, status: 'idle', connection: 'online', attempt: 0, input: null, error: '' },
      fields: emptyFields(), revisions: [], revision: 0, dirty: false,
      review: emptyReview(), approval: null, exports: [], recovery: null, saveConflict: false,
    }])), notice: null,
  };
}

export function currentEncounter(state) { return state.encounters[state.currentId]; }
export function reviewRemaining(encounter) { return Object.keys(REVIEW_OPTIONS).filter(key => !encounter.review[key]); }
export function canSign(e) {
  return e.status !== 'completed' && e.task.status === 'ready' && e.revision > 0 && !e.dirty
    && e.task.connection === 'online' && !e.saveConflict && !e.recovery && reviewRemaining(e).length === 0;
}
export function isSigned(e) {
  return Boolean(e.approval && e.approval.revision === e.revision && !e.dirty
    && !e.recovery && same(e.fields, e.revisions.at(-1)?.fields));
}
export function canComplete(e) { return e.status === 'active' && e.task.connection === 'online' && isSigned(e) && !e.saveConflict; }
export function hasPendingChanges(e) { return Boolean(e.recovery || e.dirty || e.saveConflict || !same(e.input, acceptedInput(e)) || (!isSigned(e) && hasReview(e.review))); }

function notice(state, text, kind = 'info') { state.notice = { kind, text }; return state; }
function failure(state, text) { return notice(state, text, 'error'); }
function acceptedInput(e) { return clone(e.revisions.at(-1)?.input || e.task.input || emptyInput()); }
function resetToSaved(e) {
  e.input = acceptedInput(e); e.fields = clone(e.revisions.at(-1)?.fields || emptyFields());
  e.dirty = false; e.saveConflict = false;
  e.review = e.approval?.revision === e.revision ? clone(e.approval.review) : emptyReview();
}
function stashDraft(e) {
  if (e.recovery || !hasPendingChanges(e)) return;
  e.recovery = { baseRevision: e.revision, input: clone(e.input), fields: clone(e.fields), dirty: e.dirty, review: clone(e.review), saveConflict: e.saveConflict };
  resetToSaved(e);
}
function pushRevision(e, origin, savedAt) {
  e.revision += 1;
  e.revisions.push({ number: e.revision, origin, fields: clone(e.fields), input: clone(e.input), savedAt });
  e.dirty = false; e.approval = null; e.review = emptyReview();
}

export function reducer(previous, action) {
  if (action?.type === 'RESET') return createInitialState();
  const state = clone(previous);
  // The store supplies the clock; direct reducer users may supply an ISO action.at.
  const at = isTimestamp(action?.at) ? action.at : null;
  state.notice = null;
  if (action?.type === 'CLEAR_NOTICE') return state;
  if (action?.type === 'SELECT') {
    if (!seedFor(action.id)) return failure(state, '只能选择本原型的合成患者。');
    state.currentId = action.id;
    return state;
  }
  const e = state.encounters[action?.encounterId || state.currentId];
  if (!e) return failure(state, '未找到本次合成就诊。');
  const asynchronous = ['GENERATION_DONE', 'GENERATION_FAILED', 'DISCONNECT', 'RECONNECT'];
  if (action?.taskId && action.taskId !== e.task.id) return failure(state, '已忽略不属于本次任务的旧响应。');
  const recoveryActions = ['RECOVER_DRAFT', 'DISCARD_RECOVERY', 'DISCARD_DRAFT', ...asynchronous];
  if (e.recovery && !recoveryActions.includes(action.type)) return failure(state, '检测到恢复草稿，请先选择恢复或放弃。');
  if (e.status === 'completed' && !['CREATE_EXPORT', 'DOWNLOAD', ...asynchronous].includes(action.type)) {
    return failure(state, '本次就诊已结束，病历保持只读。');
  }
  if (e.task.connection !== 'online' && ['GENERATE', 'RETRY', 'SAVE', 'SIGN', 'CREATE_EXPORT', 'COMPLETE'].includes(action.type)) {
    return failure(state, '模拟连接尚未恢复；可以继续本地编辑，恢复后再提交。');
  }
  switch (action.type) {
    case 'START':
      e.status = 'active';
      return notice(state, '已开始本次合成接诊。', 'success');
    case 'SET_INPUT': {
      if (e.task.status === 'processing') return failure(state, '任务正在处理，输入已固定；可继续查看。');
      if (e.task.status === 'failed') return failure(state, '失败任务的原始输入已保留，请重试原任务；重置演示后可输入新内容。');
      if (e.revision > 0) return failure(state, '本例已生成病历；原型中请编辑当前病历，或重置演示重新输入。');
      const kind = action.kind ?? e.input.kind;
      if (!['text', 'audio', 'recording'].includes(kind) || typeof action.text !== 'string' || action.text.length > 6000) return failure(state, '请输入6000字以内的合成演示文本。');
      const changed = kind !== e.input.kind || action.text !== e.input.text;
      e.input = { kind, text: action.text, roleConfirmed: kind === 'text' || (!changed && e.input.roleConfirmed) };
      if (changed && e.task.status === 'role_review') e.task.status = 'idle';
      return state;
    }
    case 'CONFIRM_ROLES':
      if (!e.input.text.trim()) return failure(state, '请先加入合成转写内容。');
      e.input.roleConfirmed = true;
      if (e.task.status === 'role_review') e.task.status = 'idle';
      return notice(state, '已确认本例说话人身份，可以生成病历。', 'success');
    case 'GENERATE':
      if (e.status !== 'active') return failure(state, '请先开始接诊。');
      if (e.revision > 0) return failure(state, '本例已有病历，请继续核对当前版本。');
      if (e.task.status === 'processing') return notice(state, '当前任务已在处理，没有重复生成。');
      if (!e.input.text.trim()) return failure(state, '请先输入合成问诊文本或选择演示音频。');
      if (!e.input.roleConfirmed) { e.task.status = 'role_review'; return notice(state, '请先确认转写中的说话人身份。'); }
      e.task.id ||= `synthetic-task-${e.id}`;
      e.task.status = 'processing'; e.task.attempt += 1; e.task.error = ''; e.task.input = clone(e.input);
      return notice(state, '正在模拟整理病历；没有调用语音或医疗模型。');
    case 'GENERATION_DONE':
      if (e.task.status !== 'processing') return failure(state, '当前没有可完成的生成任务。');
      e.fields = clone(seedFor(e.id).fields); e.input = clone(e.task.input);
      e.task.status = 'ready'; e.task.error = ''; pushRevision(e, 'synthetic-generation', at);
      return notice(state, '合成病历草稿已就绪，请核对四类待处理项。', 'success');
    case 'GENERATION_FAILED':
      if (e.task.status !== 'processing') return failure(state, '当前没有正在处理的任务。');
      e.task.status = 'failed'; e.task.error = String(action.message || '模拟生成失败，输入已保留。').slice(0, 400);
      return failure(state, e.task.error);
    case 'RETRY':
      if (e.task.status !== 'failed') return failure(state, '只有失败任务需要重试。');
      if (!e.input.roleConfirmed) { e.task.status = 'role_review'; return failure(state, '请先确认说话人身份。'); }
      e.task.status = 'processing'; e.task.attempt += 1; e.task.error = '';
      return notice(state, '正在重试原任务，输入和任务编号已保留。');
    case 'DISCONNECT':
      e.task.connection = 'reconnecting';
      return notice(state, '进度连接暂时中断；任务状态不变，正在等待恢复。');
    case 'RECONNECT':
      e.task.connection = 'online';
      return notice(state, '连接已恢复，继续查看原任务。', 'success');
    case 'EDIT_FIELD':
      if (!e.revision || e.task.status !== 'ready') return failure(state, '请先生成病历草稿。');
      if (!FIELD_DEFS.some(item => item.key === action.key) || typeof action.value !== 'string' || action.value.length > 6000) return failure(state, '字段或内容不符合合成原型格式。');
      if (e.fields[action.key] === action.value) return state;
      e.fields[action.key] = action.value;
      e.dirty = !same(e.fields, e.revisions.at(-1).fields);
      e.review = emptyReview();
      return state;
    case 'SAVE':
      if (!e.dirty) return notice(state, '没有尚未保存的病历修改。');
      if (e.saveConflict) return failure(state, '模拟版本冲突：修改仍保留，请核对冲突后再保存。');
      if (e.revisions.length >= 50) return failure(state, '本次演示版本已达上限，请重置演示。');
      pushRevision(e, 'doctor-edit', at);
      return notice(state, `已保存为第${e.revision}版，请重新核对并签署本版。`, 'success');
    case 'DISCARD_EDITS':
      if (!e.revision) return notice(state, '当前没有病历编辑，原始输入保持不变。');
      e.fields = clone(e.revisions.at(-1).fields); e.dirty = false;
      e.review = e.approval?.revision === e.revision ? clone(e.approval.review) : emptyReview();
      return notice(state, '已放弃本次病历修改，原始输入及已保存版本保持不变。');
    case 'INJECT_SAVE_CONFLICT':
      e.saveConflict = true;
      return notice(state, '已开启模拟保存冲突；不会改动任何真实版本。');
    case 'RESOLVE_SAVE_CONFLICT':
      e.saveConflict = false;
      return notice(state, '已核对并解除模拟冲突；本地修改仍保留，请保存。', 'success');
    case 'REVIEW':
      if (!e.revision || e.dirty || e.saveConflict) return failure(state, '请先保存当前修改并处理版本冲突，再核对已保存版本。');
      if (!Object.hasOwn(REVIEW_OPTIONS, action.kind) || (action.value !== null && !REVIEW_OPTIONS[action.kind].includes(action.value))) return failure(state, '请分别选择这项问题的明确处理方式。');
      if (action.kind === 'conflict' && action.value === 'doctor_corrected') {
        // A changed, saved text is evidence of an edit, not proof of clinical correctness.
        const normalize = value => String(value || '').trim().replace(/\s+/g, ' ');
        const savedIllness = normalize(e.revisions.at(-1)?.fields.presentIllness);
        if (!savedIllness || savedIllness === normalize(seedFor(e.id).fields.presentIllness)) {
          return failure(state, '尚未发现已保存的现病史修正。请先修改并保存；也可明确保留原文差异供医生判断。');
        }
      }
      e.review[action.kind] = action.value;
      e.approval = null;
      return notice(state, '本项处理已选择，尚未签署。');
    case 'SIGN':
      if (!canSign(e)) return failure(state, '请保存当前版本，并分别处理缺失、冲突、诊断和风险项后签署。');
      e.approval = { revision: e.revision, userId: state.userId, review: clone(e.review), signedAt: at };
      return notice(state, `已签署第${e.revision}版合成病历。`, 'success');
    case 'CREATE_EXPORT': {
      if (!isSigned(e) || e.saveConflict) return failure(state, '请先签署当前已保存版本。');
      const existing = e.exports.find(item => item.revision === e.revision);
      if (existing) return notice(state, `第${e.revision}版导出快照已存在，可再次下载。`);
      e.exports.push({ id: `synthetic-export-${e.id}-r${e.revision}`, revision: e.revision,
        fields: clone(e.fields), approval: clone(e.approval), status: 'generated', downloadAttempts: 0, error: '',
        filename: `${e.id}-R${e.revision}-合成演示病历.txt`, generatedAt: at });
      return notice(state, '合成导出快照已生成，尚未下载。', 'success');
    }
    case 'DOWNLOAD': {
      const snapshot = action.exportId ? e.exports.find(item => item.id === action.exportId) : e.exports.at(-1);
      if (!snapshot) return failure(state, '请先生成导出快照。');
      snapshot.downloadAttempts += 1;
      snapshot.status = action.fail ? 'failed' : 'downloaded';
      snapshot.error = action.fail ? '模拟下载失败，导出快照已保留。' : '';
      return notice(state, action.fail ? snapshot.error : '已发起浏览器下载；请在下载列表确认文件。', action.fail ? 'error' : 'success');
    }
    case 'COMPLETE':
      if (!canComplete(e)) return failure(state, '请先签署当前已保存版本并处理未保存修改。');
      e.status = 'completed';
      return notice(state, '本次合成就诊已结束；导出下载可独立完成。', 'success');
    case 'RECOVER_DRAFT': {
      if (!e.recovery) return notice(state, '没有待恢复的草稿。');
      if (e.recovery.baseRevision !== e.revision) return failure(state, '草稿基准版本不匹配，不能覆盖当前版本。');
      const draft = e.recovery;
      e.input = clone(draft.input); e.fields = clone(draft.fields); e.review = clone(draft.review);
      e.dirty = draft.dirty; e.saveConflict = draft.saveConflict; e.recovery = null;
      return notice(state, '已恢复本次合成就诊的未保存内容；正式版本未被覆盖。', 'success');
    }
    case 'DISCARD_RECOVERY':
      e.recovery = null;
      return notice(state, '已放弃恢复草稿，当前已保存版本保持不变。');
    case 'STASH_DRAFT':
      stashDraft(e);
      return notice(state, '本次合成未提交内容已准备暂存；仅本标签页存储成功后方可离开。');
    case 'DISCARD_DRAFT':
      resetToSaved(e); e.recovery = null;
      return notice(state, '已放弃本次未提交内容，已保存版本保持不变。');
    default:
      return failure(state, '本原型不支持此操作。');
  }
}

export function createStore(initial = createInitialState()) {
  let state = clone(initial);
  const listeners = new Set();
  return {
    getState: () => state,
    dispatch(action) { state = reducer(state, { at: new Date().toISOString(), ...action }); listeners.forEach(fn => fn(state)); return state; },
    subscribe(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  };
}

// Only this version's bounded synthetic schema can enter the demonstration session.
const assert = (condition, message) => { if (!condition) throw new Error(message); };
function isTimestamp(value) { return typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(value) && Number.isFinite(Date.parse(value)); }
function timestamp(value) { assert(value === null || isTimestamp(value), '时间格式无效'); }
function keys(value, allowed) {
  assert(value && typeof value === 'object' && !Array.isArray(value), '对象格式无效');
  assert(Object.keys(value).length === allowed.length && Object.keys(value).every(key => allowed.includes(key)), '不接受未知字段');
}
function text(value, limit = 6000) { assert(typeof value === 'string' && value.length <= limit, '文本格式无效'); }
function input(value) { keys(value, ['kind', 'text', 'roleConfirmed']); assert(['text', 'audio', 'recording'].includes(value.kind), '输入方式无效'); text(value.text); assert(typeof value.roleConfirmed === 'boolean', '身份状态无效'); }
function fields(value) { keys(value, FIELD_DEFS.map(item => item.key)); Object.values(value).forEach(value => text(value)); }
function review(value) { keys(value, Object.keys(REVIEW_OPTIONS)); for (const key of Object.keys(REVIEW_OPTIONS)) assert(value[key] === null || REVIEW_OPTIONS[key].includes(value[key]), '审核选择无效'); }
function approval(value, revisions) {
  if (value === null) return;
  keys(value, ['revision', 'userId', 'review', 'signedAt']); timestamp(value.signedAt);
  assert(value.userId === 'demo-doctor' && revisions.some(item => item.number === value.revision), '签署归属无效'); review(value.review);
  assert(!Object.values(value.review).includes(null), '不完整的签署');
}
function validateState(state) {
  keys(state, ['schemaVersion', 'synthetic', 'userId', 'currentId', 'encounters', 'notice']);
  assert(state.schemaVersion === 1 && state.synthetic === true && state.userId === 'demo-doctor', '仅接受本原型的合成演示会话');
  assert(Boolean(seedFor(state.currentId)), '未知就诊'); keys(state.encounters, CASES.map(item => item.id));
  if (state.notice !== null) { keys(state.notice, ['kind', 'text']); assert(['error', 'success', 'info'].includes(state.notice.kind), '提示无效'); text(state.notice.text, 500); }
  for (const seed of CASES) {
    const e = state.encounters[seed.id];
    keys(e, ['id', 'patient', 'status', 'input', 'task', 'fields', 'revisions', 'revision', 'dirty', 'review', 'approval', 'exports', 'recovery', 'saveConflict']);
    assert(e.id === seed.id && same(e.patient, seed.patient), '仅接受固定合成患者身份');
    assert(['waiting', 'active', 'completed'].includes(e.status), '就诊状态无效');
    input(e.input); fields(e.fields); review(e.review);
    assert(typeof e.dirty === 'boolean' && typeof e.saveConflict === 'boolean', '草稿状态无效');
    keys(e.task, ['id', 'status', 'connection', 'attempt', 'input', 'error']);
    assert(e.task.id === null || e.task.id === `synthetic-task-${e.id}`, '任务归属无效');
    assert(['idle', 'role_review', 'processing', 'ready', 'failed'].includes(e.task.status), '任务状态无效');
    assert(['online', 'reconnecting'].includes(e.task.connection) && Number.isInteger(e.task.attempt) && e.task.attempt >= 0 && e.task.attempt <= 1000, '连接状态无效');
    if (e.task.input !== null) input(e.task.input); text(e.task.error, 400);
    assert(Array.isArray(e.revisions) && e.revisions.length <= 50 && e.revision === e.revisions.length, '版本序列无效');
    e.revisions.forEach((r, i) => { keys(r, ['number', 'origin', 'fields', 'input', 'savedAt']); assert(r.number === i + 1 && ['synthetic-generation', 'doctor-edit'].includes(r.origin), '版本无效'); fields(r.fields); input(r.input); timestamp(r.savedAt); });
    approval(e.approval, e.revisions);
    assert(Array.isArray(e.exports) && e.exports.length <= 50, '导出列表无效');
    const ids = new Set();
    e.exports.forEach(item => {
      keys(item, ['id', 'revision', 'fields', 'approval', 'status', 'downloadAttempts', 'error', 'filename', 'generatedAt']);
      const r = e.revisions.find(r => r.number === item.revision);
      assert(r && item.id === `synthetic-export-${e.id}-r${item.revision}` && !ids.has(item.id), '导出归属无效'); ids.add(item.id);
      fields(item.fields); assert(same(r.fields, item.fields), '导出快照与版本不符'); approval(item.approval, e.revisions);
      assert(item.approval?.revision === item.revision && ['generated', 'failed', 'downloaded'].includes(item.status), '导出签署无效');
      assert(Number.isInteger(item.downloadAttempts) && item.downloadAttempts >= 0, '下载状态无效'); text(item.error, 400);
      assert(item.filename === `${e.id}-R${item.revision}-合成演示病历.txt`, '仅接受合成快照文件名'); timestamp(item.generatedAt);
    });
    if (e.recovery !== null) {
      keys(e.recovery, ['baseRevision', 'input', 'fields', 'dirty', 'review', 'saveConflict']);
      assert(e.recovery.baseRevision === e.revision && typeof e.recovery.dirty === 'boolean' && typeof e.recovery.saveConflict === 'boolean', '恢复归属无效');
      input(e.recovery.input); fields(e.recovery.fields); review(e.recovery.review);
    }
    assert(e.status !== 'completed' || (isSigned(e) && !e.saveConflict), '未签署的结束状态无效');
  }
  return state;
}

export function serialize(state) { return JSON.stringify(validateState(state)); }

export function restore(serialized) {
  try {
    assert(typeof serialized === 'string' && serialized.length <= 3000000, '会话内容无效');
    const state = clone(validateState(JSON.parse(serialized)));
    for (const e of Object.values(state.encounters)) {
      if (e.recovery || e.status === 'completed') continue;
      stashDraft(e);
    }
    return notice(state, '已读取本标签页的合成会话；未保存内容需明确选择恢复或放弃。');
  } catch {
    return failure(createInitialState(), '演示会话格式或归属不符，已拒绝恢复并打开全新合成会话。');
  }
}
