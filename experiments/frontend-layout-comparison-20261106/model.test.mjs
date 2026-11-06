import test from 'node:test';
import assert from 'node:assert/strict';
import { CASES, createStore, createInitialState, currentEncounter, reducer, serialize, restore,
  reviewRemaining, canSign, isSigned, canComplete } from './model.mjs';

function ready(store = createStore(), kind = 'text') {
  store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind, text: CASES.find(c => c.id === store.getState().currentId).text });
  if (kind !== 'text') store.dispatch({ type: 'CONFIRM_ROLES' });
  store.dispatch({ type: 'GENERATE' });
  store.dispatch({ type: 'GENERATION_DONE' });
  return store;
}
function reviewed(store) {
  for (const [kind, value] of Object.entries({ missing: 'not_collected', conflict: 'source_verified', diagnosis: 'defer', risk: 'reviewed' })) {
    store.dispatch({ type: 'REVIEW', kind, value });
  }
  return store;
}
function signed(store = ready()) { reviewed(store); store.dispatch({ type: 'SIGN' }); return store; }
const e = store => currentEncounter(store.getState());

test('switching patients isolates unsubmitted input without submitting it', () => {
  const store = createStore();
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: '合成甲的未提交输入' });
  store.dispatch({ type: 'SELECT', id: 'syn-002' });
  assert.equal(e(store).input.text, '');
  assert.equal(e(store).task.id, null);
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: '合成乙的未提交输入' });
  store.dispatch({ type: 'SELECT', id: 'syn-001' });
  assert.equal(e(store).input.text, '合成甲的未提交输入');
  assert.equal(store.getState().encounters['syn-002'].input.text, '合成乙的未提交输入');
});

test('edit and unsigned review choices remain owned by their encounter', () => {
  const store = reviewed(ready());
  store.dispatch({ type: 'SELECT', id: 'syn-002' }); ready(store);
  assert.equal(reviewRemaining(e(store)).length, 4);
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '合成乙修订' });
  store.dispatch({ type: 'SELECT', id: 'syn-001' });
  assert.equal(reviewRemaining(e(store)).length, 0);
  assert.equal(e(store).dirty, false);
  assert.equal(e(store).fields.chiefComplaint, CASES[0].fields.chiefComplaint);
  assert.equal(store.getState().encounters['syn-002'].fields.chiefComplaint, '合成乙修订');
});

test('audio role gate blocks generation until explicit identity confirmation', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'audio', text: CASES[0].text });
  store.dispatch({ type: 'GENERATE' });
  assert.equal(e(store).task.status, 'role_review');
  assert.equal(e(store).task.id, null);
  store.dispatch({ type: 'CONFIRM_ROLES' }); store.dispatch({ type: 'GENERATE' });
  assert.equal(e(store).task.status, 'processing');
  assert.equal(e(store).task.attempt, 1);
});

test('changing confirmed audio input invalidates role confirmation', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'audio', text: CASES[0].text });
  store.dispatch({ type: 'CONFIRM_ROLES' });
  store.dispatch({ type: 'SET_INPUT', kind: 'audio', text: '不同的合成转写' });
  store.dispatch({ type: 'GENERATE' });
  assert.equal(e(store).task.status, 'role_review');
});

test('disconnect, reconnect and duplicate generation preserve one running task', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: CASES[0].text });
  store.dispatch({ type: 'GENERATE' }); const id = e(store).task.id;
  store.dispatch({ type: 'DISCONNECT' });
  assert.equal(e(store).task.status, 'processing');
  assert.equal(e(store).task.connection, 'reconnecting');
  store.dispatch({ type: 'GENERATE' }); store.dispatch({ type: 'RECONNECT' });
  assert.equal(e(store).task.id, id); assert.equal(e(store).task.attempt, 1);
  store.dispatch({ type: 'GENERATION_DONE', taskId: id });
  store.dispatch({ type: 'GENERATION_DONE', taskId: id });
  assert.equal(e(store).revision, 1);
});

test('late response cannot populate the wrong patient', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: CASES[0].text });
  store.dispatch({ type: 'GENERATE' }); const id = e(store).task.id;
  store.dispatch({ type: 'SELECT', id: 'syn-002' });
  store.dispatch({ type: 'GENERATION_DONE', taskId: id });
  assert.equal(e(store).revision, 0);
  store.dispatch({ type: 'GENERATION_DONE', taskId: id, encounterId: 'syn-001' });
  assert.equal(store.getState().encounters['syn-001'].revision, 1);
  assert.equal(e(store).revision, 0);
});

test('failed generation retains input and retries the same task', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: CASES[0].text });
  store.dispatch({ type: 'GENERATE' }); const id = e(store).task.id;
  store.dispatch({ type: 'GENERATION_FAILED' });
  assert.equal(e(store).task.status, 'failed'); assert.equal(e(store).input.text, CASES[0].text);
  store.dispatch({ type: 'RETRY' });
  assert.equal(e(store).task.id, id); assert.equal(e(store).task.attempt, 2);
  store.dispatch({ type: 'GENERATION_DONE' }); assert.equal(e(store).revision, 1);
});

test('four independent review decisions are required to sign', () => {
  const store = ready();
  for (const [kind, value] of [['missing', 'not_collected'], ['conflict', 'source_verified'], ['diagnosis', 'reject']]) {
    store.dispatch({ type: 'REVIEW', kind, value }); store.dispatch({ type: 'SIGN' });
    assert.equal(e(store).approval, null);
  }
  assert.deepEqual(reviewRemaining(e(store)), ['risk']);
  store.dispatch({ type: 'REVIEW', kind: 'risk', value: 'reviewed' });
  assert.equal(canSign(e(store)), true);
  store.dispatch({ type: 'SIGN' }); assert.equal(isSigned(e(store)), true);
});

test('review refuses generic confirmation and dirty content', () => {
  const store = ready();
  store.dispatch({ type: 'REVIEW', kind: 'all', value: 'confirmed' });
  assert.equal(reviewRemaining(e(store)).length, 4);
  store.dispatch({ type: 'EDIT_FIELD', key: 'allergies', value: '合成补录内容' });
  store.dispatch({ type: 'REVIEW', kind: 'missing', value: 'supplemented' });
  assert.equal(e(store).review.missing, null);
  store.dispatch({ type: 'SIGN' }); assert.equal(e(store).approval, null);
});

test('save creates a distinct revision and invalidates previous approval', () => {
  const store = signed(); const original = structuredClone(e(store).revisions[0]);
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '医生修订的合成主诉' });
  assert.equal(isSigned(e(store)), false);
  store.dispatch({ type: 'SAVE' });
  assert.equal(e(store).revision, 2); assert.equal(e(store).approval, null);
  assert.equal(reviewRemaining(e(store)).length, 4);
  assert.deepEqual(e(store).revisions[0], original);
  assert.equal(e(store).revisions[1].fields.chiefComplaint, '医生修订的合成主诉');
});

test('save conflict preserves edits and does not append a revision', () => {
  const store = ready();
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: '冲突中保留的合成修改' });
  store.dispatch({ type: 'INJECT_SAVE_CONFLICT' }); store.dispatch({ type: 'SAVE' });
  assert.equal(e(store).revision, 1); assert.equal(e(store).dirty, true);
  assert.equal(e(store).fields.presentIllness, '冲突中保留的合成修改');
  assert.equal(canSign(e(store)), false);
  store.dispatch({ type: 'RESOLVE_SAVE_CONFLICT' }); store.dispatch({ type: 'SAVE' });
  assert.equal(e(store).revision, 2);
});

test('refresh requires explicit recovery and cannot overwrite a saved version', () => {
  const store = ready(); const saved = structuredClone(e(store).revisions[0]);
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: '尚未保存的合成编辑' });
  const restored = createStore(restore(serialize(store.getState())));
  assert.equal(e(restored).fields.presentIllness, saved.fields.presentIllness);
  assert.equal(e(restored).recovery.fields.presentIllness, '尚未保存的合成编辑');
  restored.dispatch({ type: 'SAVE' }); assert.equal(e(restored).revision, 1);
  restored.dispatch({ type: 'RECOVER_DRAFT' });
  assert.equal(e(restored).fields.presentIllness, '尚未保存的合成编辑');
  assert.equal(e(restored).dirty, true); assert.deepEqual(e(restored).revisions[0], saved);
  restored.dispatch({ type: 'SAVE' }); assert.equal(e(restored).revision, 2);
});

test('discard recovery preserves saved signature and record', () => {
  const store = signed();
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '将放弃的合成编辑' });
  const restored = createStore(restore(serialize(store.getState())));
  assert.equal(isSigned(e(restored)), false);
  restored.dispatch({ type: 'DISCARD_RECOVERY' });
  assert.equal(e(restored).fields.chiefComplaint, CASES[0].fields.chiefComplaint);
  assert.equal(isSigned(e(restored)), true); assert.equal(e(restored).revision, 1);
});

test('unsubmitted input and unsigned choices restore only after separate decisions for each patient', () => {
  const store = reviewed(ready());
  store.dispatch({ type: 'SELECT', id: 'syn-002' });
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: '合成乙的未提交原文' });
  const restored = createStore(restore(serialize(store.getState())));
  assert.equal(e(restored).input.text, '');
  restored.dispatch({ type: 'DISCARD_RECOVERY' }); assert.equal(e(restored).input.text, '');
  restored.dispatch({ type: 'SELECT', id: 'syn-001' });
  assert.equal(reviewRemaining(e(restored)).length, 4);
  restored.dispatch({ type: 'RECOVER_DRAFT' });
  assert.equal(reviewRemaining(e(restored)).length, 0); assert.equal(e(restored).approval, null);
});

test('repeated refresh retains the pending recovery without auto applying it', () => {
  const store = ready(); store.dispatch({ type: 'EDIT_FIELD', key: 'allergies', value: '合成待恢复' });
  const once = restore(serialize(store.getState()));
  const twice = restore(serialize(once));
  assert.deepEqual(twice.encounters['syn-001'].recovery, once.encounters['syn-001'].recovery);
  assert.equal(twice.encounters['syn-001'].fields.allergies, CASES[0].fields.allergies);
});

test('export generation, failed download and successful retry are separate', () => {
  const store = signed(); store.dispatch({ type: 'CREATE_EXPORT' });
  assert.equal(e(store).exports[0].status, 'generated');
  store.dispatch({ type: 'DOWNLOAD', fail: true });
  assert.equal(e(store).exports[0].status, 'failed'); assert.equal(isSigned(e(store)), true);
  store.dispatch({ type: 'DOWNLOAD' });
  assert.equal(e(store).exports[0].status, 'downloaded'); assert.equal(e(store).exports[0].downloadAttempts, 2);
  store.dispatch({ type: 'CREATE_EXPORT' }); assert.equal(e(store).exports.length, 1);
});

test('historical export snapshot remains bound to signed revision after new edits', () => {
  const store = signed(); store.dispatch({ type: 'CREATE_EXPORT' });
  const snapshot = structuredClone(e(store).exports[0]);
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '另一合成版本' }); store.dispatch({ type: 'SAVE' });
  store.dispatch({ type: 'CREATE_EXPORT' });
  assert.equal(e(store).exports.length, 1); assert.deepEqual(e(store).exports[0], snapshot);
  reviewed(store); store.dispatch({ type: 'SIGN' }); store.dispatch({ type: 'CREATE_EXPORT' });
  assert.deepEqual(e(store).exports.map(item => item.revision), [1, 2]);
  assert.equal(e(store).exports[0].fields.chiefComplaint, CASES[0].fields.chiefComplaint);
});

test('encounter completion requires signature but does not require export', () => {
  const store = ready(); store.dispatch({ type: 'COMPLETE' });
  assert.equal(e(store).status, 'active');
  signed(store); assert.equal(canComplete(e(store)), true);
  store.dispatch({ type: 'COMPLETE' });
  assert.equal(e(store).status, 'completed'); assert.equal(e(store).exports.length, 0);
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '不应写入' });
  assert.equal(e(store).fields.chiefComplaint, CASES[0].fields.chiefComplaint);
  store.dispatch({ type: 'CREATE_EXPORT' }); store.dispatch({ type: 'DOWNLOAD' });
  assert.equal(e(store).exports[0].status, 'downloaded');
});

test('a download cannot mark an unsigned or dirty encounter complete', () => {
  const store = signed(); store.dispatch({ type: 'CREATE_EXPORT' });
  store.dispatch({ type: 'EDIT_FIELD', key: 'allergies', value: '合成编辑' });
  store.dispatch({ type: 'DOWNLOAD' }); store.dispatch({ type: 'COMPLETE' });
  assert.equal(e(store).status, 'active'); assert.equal(e(store).dirty, true);
});

test('serialization rejects foreign user, identity, extra fields and malformed versions', () => {
  const base = ready().getState();
  const cases = [
    state => { state.userId = 'another-user'; },
    state => { state.encounters['syn-001'].patient.name = '非固定身份'; },
    state => { state.token = 'unexpected'; },
    state => { state.encounters['syn-001'].revision = 100; },
    state => { state.synthetic = false; },
  ];
  for (const change of cases) {
    const changed = structuredClone(base); change(changed);
    assert.throws(() => serialize(changed));
    const restored = restore(JSON.stringify(changed));
    assert.equal(restored.notice.kind, 'error'); assert.equal(currentEncounter(restored).revision, 0);
  }
  assert.equal(restore('not json').notice.kind, 'error');
});

test('serialization rejects an export whose contents do not match its revision', () => {
  const store = signed(); store.dispatch({ type: 'CREATE_EXPORT' });
  const state = structuredClone(store.getState()); state.encounters['syn-001'].exports[0].fields.chiefComplaint = '被替换的快照';
  assert.throws(() => serialize(state));
});

test('reducer leaves previous state untouched and store subscriptions can be removed', () => {
  const before = createInitialState(); const serialized = JSON.stringify(before);
  const after = reducer(before, { type: 'START' });
  assert.equal(JSON.stringify(before), serialized); assert.equal(currentEncounter(after).status, 'active');
  const store = createStore(); let calls = 0; const unsubscribe = store.subscribe(() => calls++);
  store.dispatch({ type: 'START' }); unsubscribe(); store.dispatch({ type: 'CLEAR_NOTICE' });
  assert.equal(calls, 1);
});

test('offline local editing remains possible while save, signing and export are blocked', () => {
  const store = signed(); store.dispatch({ type: 'DISCONNECT' });
  store.dispatch({ type: 'CREATE_EXPORT' }); assert.equal(e(store).exports.length, 0);
  store.dispatch({ type: 'COMPLETE' }); assert.equal(e(store).status, 'active');
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '断连期间合成编辑' });
  assert.equal(e(store).dirty, true);
  store.dispatch({ type: 'SAVE' }); assert.equal(e(store).revision, 1);
  store.dispatch({ type: 'RECONNECT' }); store.dispatch({ type: 'SAVE' });
  assert.equal(e(store).revision, 2); assert.equal(e(store).approval, null);
});

test('stashing for an in-app departure requires explicit restore on return', () => {
  const store = createStore();
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: '合成 A-1105 暂存哨兵' });
  store.dispatch({ type: 'STASH_DRAFT' });
  store.dispatch({ type: 'SELECT', id: 'syn-002' }); assert.equal(e(store).input.text, '');
  store.dispatch({ type: 'SELECT', id: 'syn-001' }); assert.equal(e(store).input.text, '');
  assert.equal(e(store).recovery.input.text, '合成 A-1105 暂存哨兵');
  store.dispatch({ type: 'RECOVER_DRAFT' }); assert.equal(e(store).input.text, '合成 A-1105 暂存哨兵');
  store.dispatch({ type: 'DISCARD_DRAFT' }); assert.equal(e(store).input.text, '');
});

test('an individual unsigned review decision can be withdrawn', () => {
  const store = reviewed(ready());
  store.dispatch({ type: 'REVIEW', kind: 'diagnosis', value: null });
  assert.deepEqual(reviewRemaining(e(store)), ['diagnosis']);
  assert.equal(canSign(e(store)), false);
});

test('discard edits preserves source input and saved revisions', () => {
  const store = signed(); const before = structuredClone(e(store));
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: '将被放弃的合成修改' });
  store.dispatch({ type: 'DISCARD_EDITS' });
  assert.deepEqual(e(store).fields, before.fields);
  assert.deepEqual(e(store).input, before.input);
  assert.deepEqual(e(store).revisions, before.revisions);
  assert.equal(e(store).dirty, false); assert.equal(isSigned(e(store)), true);
});

test('receipt metadata roundtrips and export names stay bound to their revision', () => {
  const store = reviewed(ready()); const at = '2026-11-05T08:30:00.000Z';
  store.dispatch({ type: 'SIGN', at }); store.dispatch({ type: 'CREATE_EXPORT', at });
  assert.equal(e(store).approval.signedAt, at);
  assert.equal(e(store).exports[0].generatedAt, at);
  assert.equal(e(store).exports[0].filename, 'syn-001-R1-合成演示病历.txt');
  assert.match(e(store).revisions[0].savedAt, /^\d{4}-\d{2}-\d{2}T/);
  const loaded = restore(serialize(store.getState()));
  assert.equal(currentEncounter(loaded).approval.signedAt, at);
  const invalid = structuredClone(store.getState());
  invalid.encounters['syn-001'].exports[0].filename = 'syn-002-R1-合成演示病历.txt';
  assert.throws(() => serialize(invalid));
});

test('claiming a corrected conflict requires a changed, nonempty, saved present illness', () => {
  const store = ready();
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, null);
  assert.equal(store.getState().notice.kind, 'error');
  store.dispatch({ type: 'EDIT_FIELD', key: 'chiefComplaint', value: '只修改主诉不算现病史修正' });
  store.dispatch({ type: 'SAVE' });
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, null);
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: CASES[0].fields.presentIllness + '  ' });
  store.dispatch({ type: 'SAVE' });
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, null);
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: '' });
  store.dispatch({ type: 'SAVE' });
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, null);
  store.dispatch({ type: 'EDIT_FIELD', key: 'presentIllness', value: '合成演示：核对后记录咳嗽3天，昨晚发热，否认胸痛。' });
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, null, 'unsaved correction must not be accepted');
  store.dispatch({ type: 'SAVE' });
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'doctor_corrected' });
  assert.equal(e(store).review.conflict, 'doctor_corrected');
});

test('explicitly retaining a source difference does not silently correct or save any field', () => {
  const store = ready(); const fields = structuredClone(e(store).fields);
  store.dispatch({ type: 'REVIEW', kind: 'conflict', value: 'source_verified' });
  assert.equal(e(store).review.conflict, 'source_verified');
  assert.deepEqual(e(store).fields, fields);
  assert.equal(e(store).revision, 1); assert.equal(e(store).approval, null);
});

test('refresh restores a processing task and accepted input without issuing duplicate generation', () => {
  const store = createStore(); store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'text', text: CASES[0].text });
  store.dispatch({ type: 'GENERATE' });
  const task = structuredClone(e(store).task);
  store.dispatch({ type: 'DISCONNECT' }); store.dispatch({ type: 'SELECT', id: 'syn-002' });
  const restored = createStore(restore(serialize(store.getState())));
  const processing = restored.getState().encounters['syn-001'];
  assert.equal(restored.getState().currentId, 'syn-002');
  assert.equal(processing.task.id, task.id); assert.equal(processing.task.status, 'processing');
  assert.equal(processing.task.attempt, 1); assert.equal(processing.task.connection, 'reconnecting');
  assert.equal(processing.input.text, CASES[0].text); assert.equal(processing.recovery, null);
  assert.equal(currentEncounter(restored.getState()).input.text, '');
  restored.dispatch({ type: 'RECONNECT', encounterId: 'syn-001' });
  restored.dispatch({ type: 'GENERATE', encounterId: 'syn-001' });
  assert.equal(restored.getState().encounters['syn-001'].task.attempt, 1);
  restored.dispatch({ type: 'GENERATION_DONE', encounterId: 'syn-001', taskId: task.id });
  restored.dispatch({ type: 'GENERATION_DONE', encounterId: 'syn-001', taskId: task.id });
  assert.equal(restored.getState().encounters['syn-001'].revision, 1);
  assert.equal(currentEncounter(restored.getState()).revision, 0);
});
