'use strict';

/**
 * Prepared acceptance flow. This module DOES NOT launch or connect a browser.
 * Run only after the user authorizes independent Playwright browser validation.
 * Caller owns browser/context/page lifecycle and must navigate page to this prototype.
 * State changes happen through visible UI controls only. evaluate() reads only.
 * runIsolation expects runFullFlow's completed A / unused B synthetic fixture.
 */
const playwright = require('C:/Users/AWA007/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs = require('node:fs/promises');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');

const STORAGE = 'medilisten-reference-workbench-v1';
const MANUAL_CHIEF = '合成手改：咳嗽伴发热，病程待核对 · A-ONLY-20261106';
const B_MARKER = '乙专属合成标记：B-ONLY-20261106';
const EXPECTED_LINES = [
  '今天哪里不舒服？', '我咳嗽两天了，没有胸痛。', '有没有发热？',
  '昨晚有些发热。', '咳嗽具体持续了多久？', '好像也有三天了，记不太清。',
];

async function readState(page) {
  return page.evaluate(key => {
    const stored = sessionStorage.getItem(key);
    const captured = sessionStorage.getItem(key + '-capture');
    return {
      state: stored ? JSON.parse(stored) : null,
      captures: captured ? JSON.parse(captured).captures : null,
    };
  }, STORAGE);
}

async function current(page) {
  const data = await readState(page);
  assert.ok(data.state, 'prototype session state must exist');
  return { ...data, encounter: data.state.encounters[data.state.currentId] };
}

async function diagnostic(page) {
  return page.evaluate(() => ({
    title: document.title,
    cssViewport: { width: innerWidth, height: innerHeight },
    devicePixelRatio,
    documentWidth: document.documentElement.scrollWidth,
    horizontalOverflow: document.documentElement.scrollWidth > innerWidth + 1,
    focus: {
      tag: document.activeElement?.tagName,
      key: document.activeElement?.getAttribute('data-focus'),
      inDialog: !!document.activeElement?.closest('[role="dialog"]'),
    },
    recordScrollTop: document.querySelector('.record-scroll')?.scrollTop ?? null,
    patientText: document.querySelector('.patient-identity')?.textContent ?? null,
  }));
}

async function waitForRead(page, predicate, description, timeoutMs = 8000) {
  const end = Date.now() + timeoutMs;
  let latest;
  do {
    latest = await readState(page);
    if (predicate(latest)) return latest;
    await page.waitForTimeout(100);
  } while (Date.now() < end);
  throw new Error('Timed out observing: ' + description + '\nLast state: ' + JSON.stringify(latest));
}

function selector(action, attributes = {}) {
  assert.match(action, /^[a-z-]+$/);
  const extra = Object.entries(attributes).map(([key, value]) => {
    assert.match(key, /^[a-z-]+$/);
    assert.match(String(value), /^[a-zA-Z0-9_-]+$/);
    return '[data-' + key + '="' + value + '"]';
  }).join('');
  return '[data-action="' + action + '"]' + extra + ':visible';
}

async function clickAction(scope, action, attributes = {}) {
  const locator = scope.locator(selector(action, attributes));
  await locator.waitFor({ state: 'visible', timeout: 5000 });
  assert.equal(await locator.count(), 1, 'action must resolve to exactly one visible control: ' + action);
  assert.equal(await locator.isEnabled(), true, 'action must be enabled: ' + action);
  await locator.click();
}

async function closeDialog(page) {
  await page.getByRole('dialog').getByRole('button', { name: '关闭面板', exact: true }).click();
  await page.getByRole('dialog').waitFor({ state: 'hidden' });
}

async function goHome(page, expectLeave = false) {
  await clickAction(page.locator('.global-nav'), 'home');
  if (expectLeave) {
    const dialog = page.getByRole('dialog', { name: '保留这次接诊的内容', exact: true });
    await dialog.waitFor({ state: 'visible' });
    await clickAction(dialog, 'confirm-leave');
  }
  await page.locator('.queue-page').waitFor({ state: 'visible' });
}

async function reloadWithObservedPrompt(page) {
  const observed = [];
  const pending = [];
  let unexpected = null;
  const listener = dialog => {
    observed.push({ type: dialog.type(), message: dialog.message() });
    if (dialog.type() !== 'beforeunload') unexpected = dialog.type();
    pending.push(dialog.type() === 'beforeunload' ? dialog.accept() : dialog.dismiss());
  };
  page.on('dialog', listener);
  try {
    await page.reload({ waitUntil: 'domcontentloaded' });
    await Promise.all(pending);
  } finally {
    page.off('dialog', listener);
  }
  assert.equal(unexpected, null, 'unexpected browser dialog during reload');
  return observed;
}

async function makeRecorder({ page, evidenceDir, name }) {
  assert.ok(page, 'caller must pass page');
  assert.ok(evidenceDir && path.isAbsolute(evidenceDir), 'evidenceDir must be absolute');
  await fs.mkdir(evidenceDir, { recursive: true });
  const dir = await fs.mkdtemp(path.join(evidenceDir, name + '-')); // Never overwrite a prior failed run.
  const report = {
    suite: name, startedAt: new Date().toISOString(), timezone: 'Asia/Shanghai',
    pageUrl: page.url(), status: 'RUNNING',
    fixture: 'fixed synthetic cases only',
    zoom: 'Not inferred from CSS viewport or DPR; native zoom is verified separately.',
    steps: [], pageErrors: [],
  };
  const errorListener = error => report.pageErrors.push(String(error));
  page.on('pageerror', errorListener);
  const reportPath = path.join(dir, 'results.json');
  const write = () => fs.writeFile(reportPath, JSON.stringify(report, null, 2) + '\n', 'utf8');
  await write();
  return {
    report, dir,
    async step(label, operation, screenshot = true) {
      const index = String(report.steps.length + 1).padStart(2, '0');
      const item = { index, label, startedAt: new Date().toISOString(), status: 'RUNNING' };
      report.steps.push(item);
      await write();
      try {
        const details = await operation();
        item.details = details ?? null;
        item.dom = await diagnostic(page);
        if (screenshot) {
          item.screenshot = index + '-passed.png';
          await page.screenshot({ path: path.join(dir, item.screenshot), fullPage: true, animations: 'disabled' });
        }
        item.status = 'PASS';
        item.finishedAt = new Date().toISOString();
        await write();
        return details;
      } catch (error) {
        item.status = 'FAIL';
        item.error = { name: error.name, message: error.message, stack: error.stack };
        item.finishedAt = new Date().toISOString();
        item.screenshot = index + '-FAILED.png';
        try {
          await page.screenshot({ path: path.join(dir, item.screenshot), fullPage: true, animations: 'disabled' });
        } catch (captureError) {
          item.screenshotFailure = String(captureError);
        }
        report.status = 'FAIL';
        report.finishedAt = new Date().toISOString();
        await write();
        page.off('pageerror', errorListener);
        throw error;
      }
    },
    async finish() {
      if (report.pageErrors.length) {
        report.status = 'FAIL';
        report.finishedAt = new Date().toISOString();
        await write();
        page.off('pageerror', errorListener);
        throw new Error('Browser page errors: ' + report.pageErrors.join('\n'));
      }
      report.status = 'PASS';
      report.finishedAt = new Date().toISOString();
      await write();
      page.off('pageerror', errorListener);
      return { reportPath, report };
    },
  };
}

async function runFullFlow({ context, page, evidenceDir }) {
  assert.equal(page.context(), context, 'page must belong to the supplied context');
  assert.ok(playwright.chromium, 'bundled Playwright API must be available');
  const rec = await makeRecorder({ page, evidenceDir, name: 'full-flow' });
  let taskId;
  await rec.step('Reset only the synthetic prototype through its visible UI', async () => {
    await clickAction(page, 'scenarios');
    await clickAction(page.getByRole('dialog'), 'reset');
    await clickAction(page.getByRole('dialog'), 'confirm-reset');
    await page.locator('.queue-page').waitFor({ state: 'visible' });
    const data = await readState(page);
    assert.equal(data.state.encounters['syn-001'].revision, 0);
    assert.equal(data.state.encounters['syn-002'].revision, 0);
    return { resetBy: 'visible reset-confirm UI' };
  });
  await rec.step('Select A, start simulated recording, pause and confirm speakers', async () => {
    await clickAction(page, 'select', { id: 'syn-001' });
    await clickAction(page, 'capture-start');
    await clickAction(page.locator('.action-buttons'), 'capture-pause');
    await clickAction(page.locator('.action-buttons'), 'capture-roles');
    await clickAction(page.getByRole('dialog'), 'capture-confirm-roles');
    const data = await current(page);
    assert.equal(data.state.currentId, 'syn-001');
    assert.equal(data.captures['syn-001'].status, 'paused');
    assert.equal(data.captures['syn-001'].roleConfirmed, true);
  });
  await rec.step('Reveal the six original conversation lines using Next sentence', async () => {
    for (let count = 0; count < 6; count += 1) {
      const data = await readState(page);
      if (data.captures['syn-001'].revealed === 6) break;
      await clickAction(page.locator('.action-buttons'), 'capture-next');
    }
    const data = await readState(page);
    assert.equal(data.captures['syn-001'].revealed, 6);
    assert.equal(data.captures['syn-001'].status, 'paused');
    const rendered = await page.locator('.source-panel .source-line p').allTextContents();
    assert.deepEqual(rendered, EXPECTED_LINES);
    assert.match(await page.locator('.action-status').innerText(), /本例对话已播完/);
    assert.equal(await page.locator(selector('capture-resume')).count(), 0);
    return { renderedLines: rendered };
  });
  await rec.step('Locate source evidence and return; open assistance and test keyboard closure', async () => {
    const before = await diagnostic(page);
    await clickAction(page, 'evidence', { key: 'chiefComplaint' });
    const modal = page.getByRole('dialog');
    if (await modal.isVisible()) {
      assert.ok(await modal.locator('.source-line.selected').count() > 0);
      await page.keyboard.press('Escape');
    } else {
      assert.ok(await page.locator('.source-panel .source-line.selected').count() > 0);
    }
    assert.equal((await diagnostic(page)).recordScrollTop, before.recordScrollTop);
    const assistantInline = page.locator(selector('assistant-detail', { section: 'reference' }));
    const assistantTrigger = await assistantInline.isVisible() ? 'assistant-reference' : 'capture-assistant';
    if (assistantTrigger === 'assistant-reference') await clickAction(page, 'assistant-detail', { section: 'reference' });
    else await clickAction(page.locator('.record-tools'), 'capture-assistant');
    await page.getByRole('dialog').waitFor({ state: 'visible' });
    await page.keyboard.press('Tab');
    assert.equal((await diagnostic(page)).focus.inDialog, true);
    await page.keyboard.press('Shift+Tab');
    assert.equal((await diagnostic(page)).focus.inDialog, true);
    await page.keyboard.press('Escape');
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    assert.equal((await diagnostic(page)).focus.key, assistantTrigger);
    return { recordScrollBefore: before.recordScrollTop, recordScrollAfter: (await diagnostic(page)).recordScrollTop };
  });
  await rec.step('Manually edit A temporary chief complaint', async () => {
    await clickAction(page, 'capture-edit');
    const input = page.locator('[data-input="capture-field"][data-key="chiefComplaint"]');
    await input.fill(MANUAL_CHIEF);
    assert.equal(await input.inputValue(), MANUAL_CHIEF);
    await clickAction(page.locator('.action-buttons'), 'capture-edit-done');
    const data = await readState(page);
    assert.equal(data.captures['syn-001'].overrides.chiefComplaint, MANUAL_CHIEF);
  });
  await rec.step('Inject one generation failure and preserve the temporary draft during processing', async () => {
    await clickAction(page, 'scenarios');
    await clickAction(page.getByRole('dialog'), 'fail-next');
    await clickAction(page.locator('.action-buttons'), 'capture-finish');
    const data = await current(page);
    taskId = data.encounter.task.id;
    assert.equal(data.encounter.task.status, 'processing');
    assert.match(await page.locator('#section-chiefComplaint').innerText(), /A-ONLY-20261106/);
    assert.equal(await page.locator('.source-panel .source-line').count(), 6);
    return { taskId, attempt: data.encounter.task.attempt };
  });
  await rec.step('Observe the explicit generation failure without losing original input or manual draft', async () => {
    const data = await waitForRead(page, value => value.state.encounters['syn-001'].task.status === 'failed', 'generation failure');
    assert.equal(data.state.encounters['syn-001'].task.id, taskId);
    assert.match(data.state.encounters['syn-001'].input.text, /咳嗽具体持续了多久/);
    assert.match(await page.locator('#section-chiefComplaint').innerText(), /A-ONLY-20261106/);
    assert.equal(await page.locator('.source-panel .source-line').count(), 6);
  });
  await rec.step('Retry the same task, reload before completion, and wait for an explicit recovery choice', async () => {
    await clickAction(page.locator('.action-buttons'), 'retry');
    const before = await current(page);
    assert.equal(before.encounter.task.id, taskId);
    assert.equal(before.encounter.task.attempt, 2);
    const dialogs = await reloadWithObservedPrompt(page);
    await clickAction(page, 'select', { id: 'syn-001' });
    await page.locator(selector('capture-recover')).waitFor({ state: 'visible' });
    // Deliberate observation interval: the model's normal generation delay is 3 seconds.
    await page.waitForTimeout(3500);
    const data = await current(page);
    assert.equal(data.encounter.revision, 0, 'refresh must not silently apply the generation result');
    assert.equal(data.encounter.task.id, taskId);
    assert.equal(data.captures['syn-001'].needsRecovery, true);
    assert.equal(data.captures['syn-001'].overrides.chiefComplaint, MANUAL_CHIEF);
    return { taskId, revision: data.encounter.revision, browserDialogsActuallyObserved: dialogs };
  });
  await rec.step('Explicitly recover, obtain version 1 and retain the unsaved manual edit', async () => {
    await clickAction(page, 'capture-recover');
    const data = await waitForRead(page, value => value.state.encounters['syn-001'].revision === 1 && value.state.encounters['syn-001'].dirty, 'version 1 plus protected manual edit');
    const e = data.state.encounters['syn-001'];
    assert.equal(e.fields.chiefComplaint, MANUAL_CHIEF);
    assert.notEqual(e.revisions[0].fields.chiefComplaint, MANUAL_CHIEF);
    assert.equal(e.approval, null);
    return { revision: e.revision, dirty: e.dirty, savedChief: e.revisions[0].fields.chiefComplaint, currentChief: e.fields.chiefComplaint };
  });
  await rec.step('Save the manual edit as a distinct version 2', async () => {
    await clickAction(page.locator('.action-buttons'), 'save');
    const data = await current(page);
    assert.equal(data.encounter.revision, 2);
    assert.equal(data.encounter.dirty, false);
    assert.equal(data.encounter.revisions[1].fields.chiefComplaint, MANUAL_CHIEF);
    assert.equal(data.encounter.approval, null);
    assert.equal(await page.locator(selector('sign')).count(), 0, 'signature must not be offered before all reviews');
  });
  for (const [kind, value] of [['conflict', 'source_verified'], ['missing', 'not_collected'], ['diagnosis', 'defer'], ['risk', 'reviewed']]) {
    await rec.step('Review the ' + kind + ' item in its field context', async () => {
      await clickAction(page.locator('.action-buttons'), 'next-issue');
      await page.locator('#issue-' + kind).waitFor({ state: 'visible' });
      await clickAction(page.locator('#issue-' + kind), 'review', { kind, value });
      const data = await current(page);
      assert.equal(data.encounter.review[kind], value);
      assert.equal(data.encounter.approval, null);
      return { review: data.encounter.review };
    });
  }
  await rec.step('Sign version 2 only after all four review decisions', async () => {
    await clickAction(page.locator('.action-buttons'), 'sign');
    const data = await current(page);
    assert.equal(data.encounter.approval.revision, 2);
    assert.equal(Object.values(data.encounter.approval.review).filter(Boolean).length, 4);
    assert.equal(await page.locator('.field-issue').count(), 0);
    return { approval: data.encounter.approval };
  });
  await rec.step('Read both history versions without editing or replacing the current record', async () => {
    await clickAction(page, 'history');
    const dialog = page.getByRole('dialog', { name: '历史版本', exact: true });
    const select = dialog.locator('[data-input="history"]');
    await select.selectOption('0');
    assert.equal(await select.inputValue(), '0');
    assert.equal((await dialog.locator('.history-grid section').first().innerText()).includes(MANUAL_CHIEF), false);
    await select.selectOption('1');
    assert.equal(await select.inputValue(), '1');
    assert.match(await dialog.locator('.history-grid section').first().innerText(), /A-ONLY-20261106/);
    assert.equal(await dialog.locator('textarea').count(), 0);
    await page.keyboard.press('Escape');
    assert.equal((await current(page)).encounter.revision, 2);
  });
  await rec.step('Generate a receipt, download the real TXT, and verify the downloaded contents', async () => {
    await clickAction(page.locator('.action-buttons'), 'export');
    const dialog = page.getByRole('dialog', { name: '病历文件已生成', exact: true });
    assert.match(await dialog.innerText(), /合成患者甲 \/ syn-001/);
    assert.match(await dialog.innerText(), /版本 2/);
    const downloadPromise = page.waitForEvent('download', { timeout: 12000 });
    await clickAction(dialog, 'download');
    const download = await downloadPromise;
    const filename = download.suggestedFilename();
    assert.equal(filename, 'syn-001-R2-合成演示病历.txt');
    const file = path.join(rec.dir, path.basename(filename));
    await download.saveAs(file);
    assert.equal(await download.failure(), null);
    const bytes = await fs.readFile(file);
    const text = bytes.toString('utf8');
    assert.match(text, /MediListen 合成演示病历/);
    assert.match(text, /合成患者甲 \/ syn-001/);
    assert.match(text, /版本 2/);
    assert.ok(text.includes(MANUAL_CHIEF));
    assert.match(text, /本版核对决定/);
    for (const value of ['已核对，保留原文差异', '本次未采集', '待进一步评估', '已核对提醒']) assert.ok(text.includes(value), value);
    assert.equal(text.includes(B_MARKER), false);
    return { filename, path: file, bytes: bytes.length, sha256: crypto.createHash('sha256').update(bytes).digest('hex') };
  });
  await rec.step('Complete A, return to the list, reopen read-only, reload and reopen again', async () => {
    await clickAction(page.getByRole('dialog'), 'complete');
    await page.locator('.queue-page').waitFor({ state: 'visible' });
    const row = page.locator('tr').filter({ has: page.locator('[data-action="select"][data-id="syn-001"]') });
    assert.match(await row.innerText(), /已完成/);
    await clickAction(page, 'select', { id: 'syn-001' });
    assert.equal((await current(page)).encounter.status, 'completed');
    assert.equal(await page.locator('#main textarea').count(), 0);
    assert.equal(await page.locator(selector('edit')).count(), 0);
    const dialogs = await reloadWithObservedPrompt(page);
    await clickAction(page, 'select', { id: 'syn-001' });
    const e = (await current(page)).encounter;
    assert.equal(e.status, 'completed');
    assert.equal(e.revision, 2);
    assert.equal(e.approval.revision, 2);
    assert.equal(e.fields.chiefComplaint, MANUAL_CHIEF);
    assert.equal(await page.locator('#main textarea').count(), 0);
    return { status: e.status, revision: e.revision, browserDialogsActuallyObserved: dialogs };
  });
  return rec.finish();
}

async function runIsolation({ context, page, evidenceDir }) {
  assert.equal(page.context(), context);
  const rec = await makeRecorder({ page, evidenceDir, name: 'patient-isolation' });
  await rec.step('Check prerequisite fixture without changing model data', async () => {
    const data = await readState(page);
    assert.equal(data.state.encounters['syn-001'].status, 'completed', 'runFullFlow must have completed A');
    assert.equal(data.state.encounters['syn-001'].fields.chiefComplaint, MANUAL_CHIEF);
    assert.equal(data.state.encounters['syn-002'].revision, 0);
    return { currentPatient: data.state.currentId };
  });
  for (let round = 1; round <= 3; round += 1) {
    const marker = B_MARKER + ' · 第' + round + '次切换';
    await rec.step('Round ' + round + ': open B, recover only its prior draft, then edit B text', async () => {
      await goHome(page);
      await clickAction(page, 'select', { id: 'syn-002' });
      if (round > 1) {
        await page.locator(selector('recover')).waitFor({ state: 'visible' });
        await clickAction(page, 'recover');
      }
      await clickAction(page, 'text-input');
      const input = page.getByRole('dialog').locator('[data-input="conversation"]');
      if (round === 1) assert.equal(await input.inputValue(), '');
      else assert.equal(await input.inputValue(), B_MARKER + ' · 第' + (round - 1) + '次切换');
      await input.fill(marker);
      assert.equal(await input.inputValue(), marker);
      await closeDialog(page);
      assert.equal((await current(page)).encounter.input.text, marker);
    });
    await rec.step('Round ' + round + ': stash B through the departure guard and verify A is unchanged', async () => {
      await goHome(page, true);
      const stashed = await readState(page);
      assert.equal(stashed.state.encounters['syn-002'].recovery.input.text, marker);
      await clickAction(page, 'select', { id: 'syn-001' });
      const data = await current(page);
      assert.equal(data.state.currentId, 'syn-001');
      assert.equal(data.encounter.fields.chiefComplaint, MANUAL_CHIEF);
      assert.equal(data.encounter.revision, 2);
      assert.equal(data.encounter.approval.revision, 2);
      assert.equal(data.encounter.input.text.includes(B_MARKER), false);
      assert.equal((await page.locator('#main').innerText()).includes(B_MARKER), false);
      assert.equal(await page.locator('#main textarea').count(), 0);
      return { round, ARevision: data.encounter.revision, BRecoveryText: data.state.encounters['syn-002'].recovery.input.text };
    });
  }
  return rec.finish();
}

async function run(options) {
  const fullFlow = await runFullFlow(options);
  const isolation = await runIsolation(options);
  return { fullFlow, isolation };
}

module.exports = { run, runFullFlow, runIsolation, readState, diagnostic, MANUAL_CHIEF, B_MARKER };
