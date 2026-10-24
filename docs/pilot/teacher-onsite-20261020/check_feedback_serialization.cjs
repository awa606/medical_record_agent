// 仅验证反馈序列化，不控制浏览器，也不声称验证下载落盘。
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const input = process.argv[2];
if (!input) throw new Error('提供已生成的 trial.js 路径');
const handlers = new Map();
const status = {textContent: ''};
const form = {addEventListener() {}, reset() {}};
let exportedBlob = null;
let clicked = false;
const fields = [
  ['trial_id', '工具验收样例（非教师反馈）'],
  ['date', ''], ['encounter', ''], ['runtime_version', ''],
  ['task_1', '独立完成'], ['answer5', '仅验证导出内容，不属于教师评价']
];
const ctx = {
  console, Blob, Date, JSON,
  FormData: class {entries() {return fields[Symbol.iterator]();}},
  URL: {createObjectURL(blob) {exportedBlob=blob;return 'blob:local-unit-test';},revokeObjectURL() {}},
  setTimeout(fn) {fn();},confirm() {return false;},
  document: {
    querySelectorAll() {return [];}, querySelector() {return form;},
    getElementById(id) {return id==='feedbackStatus'?status:{addEventListener(event,fn) {handlers.set(id,fn);}};},
    createElement() {return {click() {clicked=true;},remove() {}};},
    body:{appendChild() {}}
  }
};
vm.runInNewContext(fs.readFileSync(input, 'utf8'), ctx);
handlers.get('exportFeedback')();
assert(clicked);
exportedBlob.text().then(text => {
  const payload=JSON.parse(text);
  assert.equal(payload.trial_id,fields[0][1]);
  assert.equal(payload.task_1,'独立完成');
  assert.equal(payload.encounter,'');
  for(let i=2;i<=8;i++) assert.equal(payload['task_'+i],undefined);
  assert.equal(payload.feedback_schema,'medilisten-teacher-v1');
  assert.match(status.textContent,/下载列表确认/);
  console.log(JSON.stringify({serialization:'PASS',unselected_tasks_not_fabricated:true,browser_download:'NOT_TESTED'},null,2));
});
