/**
 * Deterministic, synthetic conversation playback. No microphone, ASR, model or API.
 * Every state belongs to one fixed CASE. Views are temporary drafts, never revisions.
 * TICK advances one second by default; every four running/connected seconds reveals
 * a line. NEXT manually reveals one line, including while paused. FINISH never
 * invents skipped lines. Browser callers supply action.at if a clock is desired.
 */
import { CASES, FIELD_DEFS } from './model.mjs';

const clone = value => JSON.parse(JSON.stringify(value));
const fieldKeys = FIELD_DEFS.map(field => field.key);
const seed = id => CASES.find(item => item.id === id);
const emptyFields = () => Object.fromEntries(fieldKeys.map(key => [key, '']));
const sourceLines = id => seed(id).text.split('\n').filter(line => /^【(医生|患者)】/.test(line)).map((line, index) => ({
  id: `${id}-line-${index}`, index,
  role: /^【医生】/.test(line) ? '医生' : '患者',
  text: line.replace(/^【[^】]+】/, ''),
}));
const stamp = at => typeof at === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z$/.test(at) && Number.isFinite(Date.parse(at));
const say = (c, message) => { c.notice = message; return c; };
const pending = c => c.roleConfirmed && c.revealed > c.appliedCount;

export function createCapture(encounterId) {
  if (!seed(encounterId)) throw new Error('仅支持固定的合成就诊。');
  return { schemaVersion: 1, synthetic: true, encounterId, status: 'idle', elapsed: 0,
    revealed: 0, appliedCount: 0, roleConfirmed: false, connection: 'online',
    editing: false, overrides: {}, needsRecovery: false, updatedAt: null, notice: null };
}

function applyVisible(c, at) {
  if (!c.roleConfirmed || c.editing || c.connection !== 'online') return;
  c.appliedCount = c.revealed;
  if (stamp(at)) c.updatedAt = at;
}

function advance(c, at) {
  if (c.revealed >= sourceLines(c.encounterId).length) return say(c, '合成对话已播放完，可以结束采集。');
  const waitingForMerge = pending(c);
  c.revealed += 1;
  if (!waitingForMerge) applyVisible(c, at);
  return c;
}

/** Reducer never mutates its input; an encounterId mismatch is ignored. */
export function captureReducer(previous, action) {
  const c = clone(previous);
  c.notice = null;
  if (action?.encounterId && action.encounterId !== c.encounterId) return say(c, '已忽略不属于本次就诊的采集事件。');
  if (action?.type === 'RESET') return createCapture(c.encounterId);
  if (c.needsRecovery && !['RECOVER', 'DISCARD_RECOVERY'].includes(action?.type)) return say(c, '请先恢复或放弃本次临时采集草稿。');
  if (action?.type === 'RECOVER') {
    if (!c.needsRecovery) return c;
    c.needsRecovery = false;
    c.status = c.status === 'finished' ? 'finished' : 'paused';
    c.editing = false;
    return say(c, '已恢复本次临时草稿；仍未形成正式版本。');
  }
  if (action?.type === 'DISCARD_RECOVERY') return createCapture(c.encounterId);
  if (c.status === 'finished') return say(c, '本次模拟采集已结束，内容保持只读。');
  switch (action?.type) {
    case 'START':
      if (c.status !== 'idle') return say(c, '本次模拟采集已经开始，请继续当前播放。');
      c.status = 'running';
      return say(c, '模拟录音已开始；没有启用麦克风。');
    case 'PAUSE':
      if (c.status === 'running') c.status = 'paused';
      return c;
    case 'RESUME':
      if (c.status === 'paused') c.status = 'running';
      return c;
    case 'TICK': {
      if (c.status !== 'running') return c;
      const seconds = action.seconds ?? 1;
      if (!Number.isInteger(seconds) || seconds < 1 || seconds > 60) return say(c, '模拟时钟步长无效。');
      for (let i = 0; i < seconds; i += 1) {
        c.elapsed += 1;
        if (c.connection === 'online' && c.elapsed % 4 === 0) advance(c, action.at);
      }
      return c;
    }
    case 'NEXT':
      if (!['running', 'paused'].includes(c.status)) return say(c, '请先开始模拟采集。');
      if (c.connection !== 'online') return say(c, '连接恢复后继续播放原对话，不补写中断期间的内容。');
      return advance(c, action.at);
    case 'CONFIRM_ROLES':
      c.roleConfirmed = true;
      applyVisible(c, action.at);
      return say(c, '已确认本例医生与患者身份，临时草稿可随问诊更新。');
    case 'DISCONNECT':
      c.connection = 'reconnecting';
      return say(c, '模拟连接中断，原文和派生内容保留在最后一次更新。');
    case 'RECONNECT':
      c.connection = 'online';
      return say(c, '模拟连接恢复，继续同一次采集。');
    case 'BEGIN_EDIT':
      if (!c.roleConfirmed || c.appliedCount < 2) return say(c, '确认说话人并出现患者内容后，才可修改临时草稿。');
      c.editing = true;
      return c;
    case 'EDIT_FIELD':
      if (!c.editing) return say(c, '请先进入临时病历编辑。');
      if (!fieldKeys.includes(action.key) || typeof action.value !== 'string' || action.value.length > 6000) return say(c, '临时字段格式无效。');
      c.overrides[action.key] = action.value;
      return c;
    case 'END_EDIT':
      c.editing = false;
      return say(c, pending(c) ? '手动修改已保留，新的问诊内容等待合并。' : '手动修改已保留在临时草稿，尚未保存为正式版本。');
    case 'APPLY_PENDING':
      if (c.editing) return say(c, '请先结束编辑，再合并新的问诊内容。');
      if (c.connection !== 'online') return say(c, '连接恢复后再合并临时更新。');
      applyVisible(c, action.at);
      return say(c, '新的问诊内容已纳入，手动修改字段保持原样，请核对。');
    case 'FINISH':
      if (!captureSnapshot(c).canFinish) return say(c, '请播放完整合成对话、确认说话人并处理待合并内容后结束采集。');
      c.status = 'finished';
      return say(c, '模拟采集已结束，将使用本例固定结果进入核对。');
    default:
      return say(c, '不支持此采集操作。');
  }
}

function derived(c) {
  const count = c.roleConfirmed ? c.appliedCount : 0;
  const fields = emptyFields();
  const sourceIndices = Object.fromEntries(fieldKeys.map(key => [key, []]));
  let questions = [], reference = null, conflict = '';
  if (count < 2) return { fields, sourceIndices, questions, reference, conflict };
  fields.allergies = '本次尚未采集';
  fields.diagnosis = '待医生补充';
  sourceIndices.chiefComplaint = [1];
  sourceIndices.presentIllness = [1];
  if (c.encounterId === 'syn-001') {
    fields.chiefComplaint = count < 4 ? '咳嗽2天' : count < 6 ? '咳嗽2天，昨晚发热' : '咳嗽伴发热，病程待核对';
    fields.presentIllness = '患者自述咳嗽2天，否认胸痛。';
    questions = ['补充体温信息', '确认过敏史'];
    if (count >= 4) {
      fields.presentIllness = '患者自述咳嗽2天，昨晚发热，否认胸痛。';
      sourceIndices.chiefComplaint.push(3);
      sourceIndices.presentIllness.push(3);
      reference = { title: '发热待查', body: '固定合成参考方向，待医生判断。', evidence: '患者提到发热；本例尚未提供体温及查体信息。', sourceIndices: [3] };
    }
    if (count >= 6) {
      fields.presentIllness = '患者自述咳嗽2天，昨晚发热，否认胸痛。随后提及可能持续3天，具体病程待确认。';
      sourceIndices.chiefComplaint.push(5);
      sourceIndices.presentIllness.push(5);
      conflict = '病程出现“2天”和“3天”两种说法，待核对。';
      questions = ['确认症状开始时间', '补充体温信息', '确认过敏史'];
    }
  } else {
    fields.chiefComplaint = count < 6 ? '右膝活动后疼痛1周' : '右膝活动后疼痛，病程待核对';
    fields.presentIllness = '患者自述右膝走路后疼痛1周。';
    questions = ['确认既往用药', '确认过敏史'];
    if (count >= 4) {
      fields.presentIllness = '患者自述右膝活动后疼痛1周，否认明确外伤及发热。';
      sourceIndices.presentIllness.push(3);
      reference = { title: '膝关节疼痛待查', body: '固定合成参考方向，待医生判断。', evidence: '患者提及活动后膝痛；本例未提供查体及检查信息。', sourceIndices: [1, 3] };
    }
    if (count >= 6) {
      fields.presentIllness = '患者自述右膝活动后疼痛，否认明确外伤及发热；病程另述10天，需核对。母亲的膝关节病为家属信息，患者本人尚未确诊。';
      sourceIndices.chiefComplaint.push(5);
      sourceIndices.presentIllness.push(5);
      conflict = '病程出现“1周”和“10天”两种说法，待核对。';
      questions = ['确认疼痛开始时间', '确认既往用药', '确认过敏史'];
    }
  }
  return { fields, sourceIndices, questions, reference, conflict };
}

/** View is an independent copy. Unknown speakers never acquire patient fact labels. */
export function captureSnapshot(c) {
  const result = derived(c);
  if (c.roleConfirmed) Object.assign(result.fields, c.overrides);
  const totalLines = sourceLines(c.encounterId).length;
  const canFinish = ['running', 'paused'].includes(c.status) && c.revealed === totalLines && c.roleConfirmed
    && c.connection === 'online' && !c.editing && !pending(c) && !c.needsRecovery;
  return { ...clone(c), ...result,
    lines: sourceLines(c.encounterId).slice(0, c.revealed).map(line => ({ ...line,
      role: c.roleConfirmed ? line.role : line.index % 2 ? '说话人 B' : '说话人 A' })),
    pending: pending(c), canFinish, totalLines, progress: c.revealed / totalLines,
    finishedText: c.status === 'finished' ? seed(c.encounterId).text : '',
    editedFields: clone(c.overrides),
  };
}
export const captureView = captureSnapshot;
export function captureHasPending(c) { return Boolean(c && (c.needsRecovery || c.status !== 'idle')); }

function assert(condition, message) { if (!condition) throw new Error(message); }
function exactKeys(value, keys) {
  assert(value && typeof value === 'object' && !Array.isArray(value), '采集对象无效');
  assert(Object.keys(value).length === keys.length && Object.keys(value).every(key => keys.includes(key)), '采集字段无效');
}
function validate(c, id) {
  const base = createCapture(id);
  exactKeys(c, Object.keys(base));
  assert(c.schemaVersion === 1 && c.synthetic === true && c.encounterId === id, '采集归属无效');
  assert(['idle', 'running', 'paused', 'finished'].includes(c.status), '采集状态无效');
  assert(Number.isInteger(c.elapsed) && c.elapsed >= 0 && c.elapsed <= 86400, '模拟计时无效');
  assert(Number.isInteger(c.revealed) && c.revealed >= 0 && c.revealed <= sourceLines(id).length, '原文进度无效');
  assert(Number.isInteger(c.appliedCount) && c.appliedCount >= 0 && c.appliedCount <= c.revealed, '派生进度无效');
  assert(typeof c.roleConfirmed === 'boolean' && typeof c.editing === 'boolean' && typeof c.needsRecovery === 'boolean', '采集标志无效');
  assert(['online', 'reconnecting'].includes(c.connection), '采集连接无效');
  assert(c.updatedAt === null || stamp(c.updatedAt), '采集更新时间无效');
  assert(c.notice === null || typeof c.notice === 'string' && c.notice.length <= 500, '采集消息无效');
  assert(c.overrides && typeof c.overrides === 'object' && !Array.isArray(c.overrides), '编辑对象无效');
  assert(Object.keys(c.overrides).every(key => fieldKeys.includes(key) && typeof c.overrides[key] === 'string' && c.overrides[key].length <= 6000), '临时编辑无效');
  assert(c.roleConfirmed || c.appliedCount === 0 && !c.editing && Object.keys(c.overrides).length === 0, '未确认角色不能有派生草稿');
  assert(c.status !== 'idle' || c.revealed === 0 && c.appliedCount === 0 && c.elapsed === 0 && !c.editing && Object.keys(c.overrides).length === 0, '未开始采集不能包含问诊内容');
  assert(c.status !== 'finished' || c.revealed === 6 && c.appliedCount === 6 && c.roleConfirmed && !c.editing && c.connection === 'online', '已完成采集不完整');
}

/** Storage is explicitly limited to the two fixed synthetic cases in this tab. */
export function serializeCaptures(captures) {
  const ids = CASES.map(item => item.id);
  exactKeys(captures, ids);
  for (const id of ids) validate(captures[id], id);
  return JSON.stringify({ schemaVersion: 1, synthetic: true, userId: 'demo-doctor', captures });
}

/** Restored active or finished content is inert until an explicit RECOVER. */
export function restoreCaptures(serialized) {
  assert(typeof serialized === 'string' && serialized.length <= 120000, '采集会话大小无效');
  const payload = JSON.parse(serialized);
  exactKeys(payload, ['schemaVersion', 'synthetic', 'userId', 'captures']);
  assert(payload.schemaVersion === 1 && payload.synthetic === true && payload.userId === 'demo-doctor', '仅支持本原型的合成采集会话');
  serializeCaptures(payload.captures);
  const captures = clone(payload.captures);
  for (const c of Object.values(captures)) {
    c.notice = null;
    if (c.status === 'idle') continue;
    c.needsRecovery = true;
    if (c.status === 'running') c.status = 'paused';
    c.editing = false;
  }
  return captures;
}
