import test from 'node:test';
import assert from 'node:assert/strict';
import { CASES, createStore, currentEncounter } from './model.mjs';
import { createCapture, captureReducer as r, captureSnapshot as view, captureHasPending,
  serializeCaptures, restoreCaptures } from './capture.mjs';

const AT = '2026-11-06T03:10:00.000Z';
const action = (c, type, extra = {}) => r(c, { type, at: AT, ...extra });
const map = () => Object.fromEntries(CASES.map(item => [item.id, createCapture(item.id)]));
const start = (id = 'syn-001') => action(action(createCapture(id), 'CONFIRM_ROLES'), 'START');
const next = (c, n = 1) => { while (n-- > 0) c = action(c, 'NEXT'); return c; };

test('capture state belongs to a fixed encounter and rejects a cross-encounter event', () => {
  const captures = map();
  captures['syn-001'] = next(start(), 2);
  const before = structuredClone(captures['syn-001']);
  const ignored = action(before, 'NEXT', { encounterId: 'syn-002' });
  assert.equal(ignored.revealed, 2);
  assert.match(ignored.notice, /不属于本次就诊/);
  assert.equal(captures['syn-002'].revealed, 0);
  assert.deepEqual(captures['syn-001'], before);
  assert.throws(() => createCapture('real-patient'), /固定/);
});

test('unconfirmed voices show transcript labels but cannot populate patient facts or references', () => {
  let c = next(action(createCapture('syn-001'), 'START'), 6);
  assert.equal(view(c).lines[0].role, '说话人 A');
  assert.equal(view(c).lines[1].role, '说话人 B');
  assert.ok(Object.values(view(c).fields).every(value => value === ''));
  assert.equal(view(c).reference, null);
  assert.equal(view(c).canFinish, false);
  assert.equal(action(c, 'BEGIN_EDIT').editing, false);
  assert.equal(action(c, 'FINISH').status, 'running');
  c = action(c, 'CONFIRM_ROLES');
  assert.equal(view(c).lines[1].role, '患者');
  assert.match(view(c).fields.presentIllness, /3天/);
  assert.equal(view(c).canFinish, true);
});

test('only revealed, role-confirmed source statements enter each temporary draft', () => {
  let c = next(start(), 1);
  assert.equal(view(c).fields.chiefComplaint, '');
  c = next(c);
  assert.equal(view(c).fields.chiefComplaint, '咳嗽2天');
  assert.doesNotMatch(view(c).fields.presentIllness, /昨晚发热|3天/);
  assert.equal(view(c).reference, null);
  c = next(c, 2);
  assert.match(view(c).fields.presentIllness, /昨晚发热/);
  assert.doesNotMatch(view(c).fields.presentIllness, /3天/);
  assert.equal(view(c).reference.title, '发热待查');
  assert.equal(view(c).fields.diagnosis, '待医生补充');
  c = next(c, 2);
  assert.match(view(c).conflict, /2天.*3天/);
  assert.deepEqual(view(c).sourceIndices.presentIllness, [1, 3, 5]);
  assert.deepEqual(view(c).sourceIndices.allergies, []);
  assert.deepEqual(view(c).sourceIndices.diagnosis, []);
});

test('paused playback freezes elapsed and lines; NEXT is a deliberate paused single step', () => {
  let c = action(start(), 'TICK', { seconds: 4 });
  assert.equal(c.revealed, 1);
  c = action(c, 'PAUSE');
  const paused = action(c, 'TICK', { seconds: 12 });
  assert.equal(paused.elapsed, 4);
  assert.equal(paused.revealed, 1);
  c = action(c, 'NEXT');
  assert.equal(c.status, 'paused');
  assert.equal(c.revealed, 2);
  c = action(action(c, 'RESUME'), 'TICK', { seconds: 4 });
  assert.equal(c.revealed, 3);
  assert.equal(c.elapsed, 8);
});

test('disconnect preserves same capture and freezes source and derived output without backfill', () => {
  let c = next(start(), 2);
  const fields = view(c).fields;
  c = action(c, 'DISCONNECT');
  c = action(c, 'TICK', { seconds: 20 });
  c = action(c, 'NEXT');
  assert.equal(c.revealed, 2);
  assert.equal(c.elapsed, 20);
  assert.deepEqual(view(c).fields, fields);
  assert.equal(view(c).canFinish, false);
  c = action(c, 'RECONNECT');
  assert.equal(c.revealed, 2);
  c = action(c, 'TICK', { seconds: 4 });
  assert.equal(c.revealed, 3);
  assert.equal(c.encounterId, 'syn-001');
});

test('manual edits survive subsequent lines and queued updates require explicit merge', () => {
  let c = next(start(), 2);
  c = action(c, 'BEGIN_EDIT');
  c = action(c, 'EDIT_FIELD', { key: 'chiefComplaint', value: '医生核对后的临时主诉' });
  c = next(c, 2);
  assert.equal(c.appliedCount, 2);
  assert.equal(view(c).pending, true);
  assert.doesNotMatch(view(c).fields.presentIllness, /昨晚发热/);
  assert.equal(action(c, 'APPLY_PENDING').appliedCount, 2);
  c = action(c, 'END_EDIT');
  c = next(c, 2);
  assert.equal(c.appliedCount, 2, 'another line must not silently accept a queued merge');
  assert.equal(view(c).canFinish, false);
  c = action(c, 'APPLY_PENDING');
  assert.equal(c.appliedCount, 6);
  assert.equal(view(c).pending, false);
  assert.equal(view(c).fields.chiefComplaint, '医生核对后的临时主诉');
  assert.match(view(c).fields.presentIllness, /3天/);
  assert.equal(view(c).canFinish, true);
});

test('a manual field remains protected after merge and later automatic updates', () => {
  let c = next(start(), 2);
  c = action(c, 'BEGIN_EDIT');
  c = action(c, 'EDIT_FIELD', { key: 'presentIllness', value: '医生自填演示内容' });
  c = next(c);
  c = action(action(c, 'END_EDIT'), 'APPLY_PENDING');
  c = next(c, 3);
  assert.equal(view(c).fields.presentIllness, '医生自填演示内容');
  assert.equal(view(c).editedFields.presentIllness, '医生自填演示内容');
  assert.match(view(c).conflict, /2天/);
});

test('finishing never fills unplayed source, then supplies only the matching complete fixed case', () => {
  let c = next(start('syn-002'), 2);
  c = action(c, 'FINISH');
  assert.equal(c.status, 'running');
  assert.equal(c.revealed, 2);
  assert.equal(view(c).finishedText, '');
  c = action(next(c, 4), 'FINISH');
  assert.equal(c.status, 'finished');
  assert.equal(view(c).finishedText, CASES[1].text);
  assert.doesNotMatch(view(c).finishedText, /咳嗽/);
  assert.equal(action(c, 'NEXT').revealed, 6);
  assert.match(view(c).fields.presentIllness, /母亲.*家属信息/);
});

test('refresh restores both encounters inert, requires explicit recovery and preserves overrides', () => {
  const captures = map();
  let c = next(start(), 2);
  c = action(c, 'BEGIN_EDIT');
  c = action(c, 'EDIT_FIELD', { key: 'allergies', value: '合成手动待核对内容' });
  captures['syn-001'] = next(c, 2);
  captures['syn-002'] = next(start('syn-002'), 2);
  const restored = restoreCaptures(serializeCaptures(captures));
  assert.equal(restored['syn-001'].needsRecovery, true);
  assert.equal(restored['syn-001'].status, 'paused');
  assert.equal(restored['syn-001'].editing, false);
  assert.equal(action(restored['syn-001'], 'NEXT').revealed, 4);
  assert.equal(action(restored['syn-001'], 'RESUME').status, 'paused');
  const recovered = action(restored['syn-001'], 'RECOVER');
  assert.equal(recovered.needsRecovery, false);
  assert.equal(recovered.status, 'paused');
  assert.equal(view(recovered).fields.allergies, '合成手动待核对内容');
  assert.equal(view(recovered).pending, true);
  assert.equal(restored['syn-002'].needsRecovery, true);
});

test('discarding one recovery clears that capture without affecting the other case', () => {
  const captures = map();
  captures['syn-001'] = next(start(), 2);
  captures['syn-002'] = next(start('syn-002'), 4);
  const restored = restoreCaptures(serializeCaptures(captures));
  restored['syn-001'] = action(restored['syn-001'], 'DISCARD_RECOVERY');
  assert.equal(restored['syn-001'].status, 'idle');
  assert.equal(captureHasPending(restored['syn-001']), false);
  assert.equal(restored['syn-002'].revealed, 4);
  assert.equal(restored['syn-002'].needsRecovery, true);
});

test('finished capture refresh retains data but does not silently submit it to the record model', () => {
  const captures = map();
  captures['syn-001'] = action(next(start(), 6), 'FINISH');
  const restored = restoreCaptures(serializeCaptures(captures));
  assert.equal(restored['syn-001'].needsRecovery, true);
  assert.equal(restored['syn-001'].status, 'finished');
  assert.equal(action(restored['syn-001'], 'RECOVER').needsRecovery, false);
  assert.equal(currentEncounter(createStore().getState()).revision, 0);
});

test('untrusted storage rejects wrong user, injected fields, case reassignment and impossible role facts', () => {
  const clean = serializeCaptures(map());
  for (const mutate of [
    p => { p.userId = 'another-doctor'; },
    p => { p.captures['syn-001'].encounterId = 'syn-002'; },
    p => { p.captures['syn-001'].productionPatient = 'fake'; },
    p => { p.captures['syn-001'].appliedCount = 1; },
    p => { p.captures['syn-001'].overrides = { password: 'bad' }; },
    p => { p.captures['syn-001'].status = 'finished'; },
  ]) {
    const payload = JSON.parse(clean); mutate(payload);
    assert.throws(() => restoreCaptures(JSON.stringify(payload)));
  }
});

test('view is a copy and cannot mutate capture state or source data', () => {
  const c = next(start(), 2);
  const v = view(c);
  v.overrides.presentIllness = 'altered';
  v.lines[1].text = 'altered';
  assert.deepEqual(c.overrides, {});
  assert.match(view(c).lines[1].text, /咳嗽/);
});

test('fixed model handoff retains explicit temporary doctor edits as a new saved revision', () => {
  let c = next(start('syn-002'), 2);
  c = action(c, 'BEGIN_EDIT');
  c = action(c, 'EDIT_FIELD', { key: 'chiefComplaint', value: '右膝活动后疼痛，病程待确认（合成修订）' });
  c = next(c, 4);
  c = action(action(c, 'END_EDIT'), 'APPLY_PENDING');
  c = action(c, 'FINISH');
  const result = view(c);
  const store = createStore();
  store.dispatch({ type: 'SELECT', id: c.encounterId });
  store.dispatch({ type: 'START' });
  store.dispatch({ type: 'SET_INPUT', kind: 'recording', text: result.finishedText });
  store.dispatch({ type: 'CONFIRM_ROLES' });
  store.dispatch({ type: 'GENERATE' });
  store.dispatch({ type: 'GENERATION_DONE' });
  for (const [key, value] of Object.entries(result.editedFields)) store.dispatch({ type: 'EDIT_FIELD', key, value });
  store.dispatch({ type: 'SAVE' });
  const e = currentEncounter(store.getState());
  assert.equal(e.id, 'syn-002');
  assert.equal(e.revision, 2);
  assert.equal(e.fields.chiefComplaint, result.editedFields.chiefComplaint);
  assert.equal(e.revisions[0].fields.chiefComplaint, CASES[1].fields.chiefComplaint);
  assert.equal(e.approval, null);
  assert.equal(store.getState().encounters['syn-001'].revision, 0);
});
