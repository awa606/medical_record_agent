/* Synthetic presentation states on the actual doctor DOM. Never model/clinical evidence. */
(() => {
  const s = window.__MRA_APP_STATE__;
  const copy = value => JSON.parse(JSON.stringify(value));
  const text = '发热伴咳嗽、咽痛两天，最高体温38.2℃。没有胸痛，也没有药物过敏史。';
  s.currentEncounter = {id: 'SIM-VISUAL-001', patient_display_name: '模拟患者', patient_deidentified_id: 'SIM-VISUAL-001', check_in_status: 'checked_in'};
  const values = {chief_complaint: '发热伴咳嗽、咽痛2天', present_illness: '患者自述两天前出现发热，最高体温38.2℃，伴咳嗽和咽痛。否认胸痛。症状变化、接触史及自行用药情况需继续核对。', past_history: '本次未采集既往疾病史，待医生补充。', allergy_history: '患者否认药物过敏史。', physical_exam: '患者自测体温38.2℃；现场查体尚未完成。', auxiliary_exams: '本次尚无检查结果。'};
  for (const [key, value] of Object.entries(values)) {
    if (!s.currentRecordFields[key]) continue;
    Object.assign(s.currentRecordFields[key], {value, missing: false, status: 'partial', hint: '合成资料，待医生核对', doctor_review_status: 'pending', confirmed_by_doctor: false, source_spans: [{text, segment_id: 'sim-2', index: 0}]});
  }
  const diagnosis = s.currentRecordFields.candidate_diagnoses?.[0] || {};
  s.currentRecordFields.candidate_diagnoses = ['上呼吸道感染', '流行性感冒待排'].map(name => ({...diagnosis, name, reason: '发热、咳嗽和咽痛；病原学与查体信息不足，需医生鉴别。', evidence: [{text, segment_id: 'sim-2'}], references: [], risk_warnings: [], suggested_checks: ['按医生判断补充必要检查'], follow_up_questions: ['症状何时开始，是否接触相似症状者？'], doctor_review_status: 'pending'}));
  s.currentRecordFields.treatment_plan = {...s.currentRecordFields.treatment_plan, value: '仅为合成展示内容：补充问诊与查体，由医生决定进一步处理。不包含处方。', missing: false, status: 'partial'};
  s.currentAsrResult = {segments: [
    {segment_id: 'sim-1', speaker_id: 's0', role: '医生', role_source: 'manual', role_confidence: 1, text: '什么时候开始不舒服？有胸痛或者药物过敏吗？', start: 0, end: 5},
    {segment_id: 'sim-2', speaker_id: 's1', role: '患者', role_source: 'manual', role_confidence: 1, text, start: 5, end: 15}],
    role_quality: {status: 'passed'}, speaker_assignments: [{speaker_id: 's0', role: '医生', confirmed_by_doctor: true}, {speaker_id: 's1', role: '患者', confirmed_by_doctor: true}]};
  s.currentKnowledgeEvidence = {results: []}; s.knowledgeEvidenceStatus = 'idle';
  s.recordHighlightUntil = 0; s.lastActionError = ''; s.recordEditMode = false;
  const keys = ['currentRecordFields','currentEncounter','currentAsrResult','currentTask','taskStatus','currentTaskId','currentExportReadiness','currentInputText'];
  const baseline = Object.fromEntries(keys.map(k => [k, copy(s[k] ?? null)]));
  window.setWorkspaceReviewScene = kind => {
    if (typeof closeWorkspaceAuxiliary === 'function') closeWorkspaceAuxiliary();
    closeDrawer();
    for (const k of keys) s[k] = copy(baseline[k]);
    clearToast();
    s.recordEditMode = false; s.recordEditDirty = false; s.recordEditConflict = null; s.lastActionError = '';
    s.browserRecordingStatus = 'idle'; s.browserRecordingMessage = ''; s.recordHighlightUntil = 0;
    document.querySelector('#recordingPanel').hidden = true;
    if (kind === 'empty' || kind === 'recording' || kind === 'role') {
      s.currentRecordFields = null; s.currentTaskId = null; s.currentTask = null; s.taskStatus = 'TRANSCRIBED'; s.currentExportReadiness = null;
      if (kind !== 'role') { s.currentAsrResult = null; s.currentInputText = ''; s.liveTranscriptSegments = []; s.provisionalTranscriptSegments = []; }
    }
    if (kind === 'recording') {
      s.browserRecordingStatus = 'recording'; s.browserRecordingMessage = '模拟录音状态；未使用麦克风，未提交音频。';
      document.querySelector('#recordingPanel').hidden = false;
    }
    if (kind === 'review') { s.currentTask.current_stage = 'waiting_doctor_review'; s.currentEncounter.status = 'reviewed'; }
    if (kind === 'long') s.currentRecordFields.present_illness.value += '患者描述夜间咳嗽较明显，睡眠受影响，饮水和进食情况需进一步了解。'.repeat(12);
    if (kind === 'role') {
      s.currentAsrResult.role_quality = {status: 'needs_review', reasons: ['合成场景：说话人身份尚未确认'], pending_speaker_ids: ['s0','s1']};
      s.currentAsrResult.speaker_assignments.forEach(a => {a.role = 'unknown'; a.confirmed_by_doctor = false; a.needs_review = true;});
      s.currentAsrResult.segments.forEach(a => {a.role = 'unknown'; a.role_source = 'unknown';});
    }
    setProductView('encounter'); renderAll(); renderBrowserRecordingPanel();
    if (kind === 'conflict') {
      beginRecordEdit(); s.recordEditDirty = true; s.recordEditConflict = {code: 'REVISION_CONFLICT'};
      s.lastActionError = '合成冲突：病历已有更新，请先加载最新版本。'; renderAll();
    }
    document.querySelector('#workspaceReviewScene')?.setAttribute('data-scene', kind);
  };
  if (!document.querySelector('#workspaceReviewScene')) {
    const tools = document.createElement('label'); tools.style.cssText = 'display:flex;align-items:center;gap:8px;font-size:12px;white-space:nowrap;color:#704c12';
    tools.innerHTML = `合成数据 · 版式验收 <select id="workspaceReviewScene" aria-label="版式验收场景" style="width:120px;padding:4px;font-size:13px"><option value="draft">病历草稿</option><option value="empty">待采集</option><option value="recording">录音状态（模拟）</option><option value="long">长病历</option><option value="review">等待审核</option><option value="role">角色阻断</option><option value="conflict">Revision冲突</option></select>`;
    document.querySelector('.topbar').insertBefore(tools, document.querySelector('.top-actions'));
    tools.querySelector('select').addEventListener('change', e => window.setWorkspaceReviewScene(e.target.value));
  }
  document.title = 'MediListen · 整体布局候选（合成数据，未运行真实模型）';
  window.setWorkspaceReviewScene('draft');
})();
