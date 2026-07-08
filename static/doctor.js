const appState = {
  currentTaskId: null,
  currentAudioId: null,
  currentAsrSessionId: null,
  currentAsrResult: null,
  liveTranscriptSegments: [],
  currentEvaluation: null,
  currentTask: null,
  currentSteps: [],
  currentRecordFields: null,
  currentDraft: "",
  currentSafetyCheck: null,
  currentAgentTrace: null,
  currentLlmStatus: null,
  currentInputText: "",
  selectedEngine: "funasr",
  assistTab: "ai",
  viewMode: "doctor",
  screenshotMode: false,
  audioMode: "transcribe",
  uploadedFilename: "",
  taskStatus: "CREATED",
  busy: false,
  eventSource: null,
  asrEventSource: null,
  asrStreamProgress: 0,
  asrStreamCurrentSegment: 0,
  asrStreamTotalSegments: 0,
  asrLastError: "",
  roleReviewDirty: false,
  roleReviewSaving: false,
};

const FIELD_DEFS = [
  ["chief_complaint", "主诉"],
  ["present_illness", "现病史"],
  ["previous_treatment", "既往处理"],
  ["accompanying_symptoms", "伴随症状"],
  ["past_history", "既往史"],
  ["allergy_history", "过敏史"],
  ["physical_exam", "查体"],
  ["treatment_plan", "处理建议"],
];

const WORKFLOW_STEPS = [
  { key: "CREATED", label: "1.输入/上传" },
  { key: "TRANSCRIBED", label: "2.对话转写" },
  { key: "GENERATING_DRAFT", label: "3.病历草稿" },
  { key: "WAITING_DOCTOR_REVIEW", label: "4.医生审核" },
  { key: "EXPORTED", label: "5.确认导出" },
];

const STATUS_TO_STEP = {
  CREATED: "CREATED",
  TRANSCRIBING: "TRANSCRIBED",
  TRANSCRIBED: "TRANSCRIBED",
  EXTRACTING_FIELDS: "GENERATING_DRAFT",
  GENERATING_DRAFT: "GENERATING_DRAFT",
  SAFETY_CHECKING: "GENERATING_DRAFT",
  WAITING_DOCTOR_REVIEW: "WAITING_DOCTOR_REVIEW",
  doctor_review: "WAITING_DOCTOR_REVIEW",
  FAILED: "WAITING_DOCTOR_REVIEW",
  reviewed: "WAITING_DOCTOR_REVIEW",
  approved: "WAITING_DOCTOR_REVIEW",
  EXPORTED: "EXPORTED",
  exported: "EXPORTED",
};

const STATUS_LABELS = {
  CREATED: "任务已创建",
  TRANSCRIBING: "实时转写中",
  TRANSCRIBED: "转写完成",
  EXTRACTING_FIELDS: "字段抽取中",
  GENERATING_DRAFT: "草稿生成中",
  SAFETY_CHECKING: "安全校验中",
  WAITING_DOCTOR_REVIEW: "等待医生审核",
  doctor_review: "等待医生审核",
  FAILED: "任务失败",
  reviewed: "草稿已保存",
  approved: "字段已确认",
  EXPORTED: "已导出",
  exported: "已导出",
};

const ENGINE_LABELS = {
  funasr: "FunASR",
  sensevoice: "SenseVoice Small",
  whisper: "Whisper Base",
  mock: "Mock ASR",
  qwen3: "Qwen3-ASR 0.6B",
  online: "Online ASR",
  "funasr-local": "FunASR",
  "sensevoice-small": "SenseVoice Small",
  "whisper-base": "Whisper Base",
  "mock-asr-v0.2": "Mock ASR",
  "qwen3-asr-0.6b": "Qwen3-ASR 0.6B",
};

const ROLE_OPTIONS = [
  ["医生", "医生"],
  ["患者", "患者"],
  ["待确认", "待确认"],
];

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data.detail;
    if (typeof detail === "string") throw new Error(detail);
    if (detail?.errors) throw new Error(detail.errors.join(" "));
    throw new Error(JSON.stringify(detail || data));
  }
  return data;
}

function renderJson(element, value) {
  if (!element) return;
  element.textContent = value ? JSON.stringify(value, null, 2) : "-";
}

function setBusy(nextBusy, message = "") {
  appState.busy = nextBusy;
  document.querySelectorAll("button").forEach((button) => {
    if (button.id !== "closeDrawerButton") button.disabled = nextBusy;
  });
  if (message) {
    $("currentTaskHint").textContent = message;
  }
}

function showToast(text) {
  const toast = $("toast");
  toast.textContent = text;
  toast.classList.add("active");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("active"), 2200);
}

function runLogCommand() {
  const taskId = appState.currentTaskId || "xxx";
  const audioId = appState.currentAudioId || "xxx";
  return `python scripts/save_run_log.py --task-id ${taskId} --audio-id ${audioId} --title fever_01_demo`;
}

async function copyRunLogCommand() {
  const command = runLogCommand();
  try {
    await navigator.clipboard.writeText(command);
    showToast("运行日志命令已复制");
  } catch (_error) {
    showToast(command);
  }
}

function renderRunContext() {
  $("currentTaskIdValue").textContent = appState.currentTaskId || "-";
  $("currentAudioIdValue").textContent = appState.currentAudioId || "-";
  $("runLogCommand").textContent = runLogCommand();
}

function hasActiveSession() {
  return Boolean(
    appState.currentTaskId
      || appState.currentAudioId
      || appState.currentAsrSessionId
      || appState.currentAsrResult
      || appState.liveTranscriptSegments.length
      || appState.currentRecordFields
      || appState.currentDraft
      || appState.currentInputText,
  );
}

function riskSummary() {
  const missing = missingItems();
  const diagnoses = appState.currentRecordFields?.candidate_diagnoses || [];
  const safety = appState.currentSafetyCheck;
  const warnings = [...(appState.currentAsrResult?.warnings || []), ...(safety?.warnings || [])];
  const errors = safety?.errors || [];
  const evaluationMissing = appState.currentEvaluation?.medical_keywords?.missing || [];
  const roleNeedsReview = appState.currentAsrResult?.role_strategy === "single_segment_needs_review";
  return {
    hasRisk: missing.length > 0
      || diagnoses.length > 0
      || warnings.length > 0
      || errors.length > 0
      || evaluationMissing.length > 0
      || roleNeedsReview
      || Boolean(safety && (!safety.passed || safety.blocked)),
    hasError: errors.length > 0 || Boolean(safety?.blocked) || Boolean(safety && !safety.passed),
    missing,
    diagnoses,
    warnings,
    errors,
    evaluationMissing,
    roleNeedsReview,
  };
}

function renderMode() {
  const isDebug = appState.viewMode === "debug";
  document.body.classList.toggle("debug-mode", isDebug);
  document.body.classList.toggle("doctor-mode", !isDebug);
  document.body.classList.toggle("screenshot-mode", appState.screenshotMode);
  $("doctorModeButton").classList.toggle("active", !isDebug);
  $("debugModeButton").classList.toggle("active", isDebug);
  $("demoModeButton").classList.toggle("active", !appState.screenshotMode);
  $("screenshotModeButton").classList.toggle("active", appState.screenshotMode);
}

function setViewMode(mode) {
  appState.viewMode = mode === "debug" ? "debug" : "doctor";
  if (appState.viewMode === "doctor" && appState.assistTab === "trace") {
    appState.assistTab = "ai";
  }
  renderAll();
}

function setScreenshotMode(enabled) {
  appState.screenshotMode = Boolean(enabled);
  renderMode();
}

function renderStartGuide() {
  $("startGuide").hidden = hasActiveSession();
}

function renderStepPrompt() {
  const risk = riskSummary();
  const prompt = $("stepPrompt");
  let text = "请上传问诊音频或粘贴问诊文本开始。";
  let tone = "";

  if (hasActiveSession() && risk.hasRisk) {
    text = "请优先处理红色/黄色提示。";
    tone = risk.hasError ? "danger" : "risk";
  } else if (appState.taskStatus === "WAITING_DOCTOR_REVIEW" || appState.taskStatus === "reviewed" || appState.taskStatus === "approved") {
    text = "请确认字段和候选诊断，确认后才能导出。";
  } else if (appState.currentDraft || appState.taskStatus === "GENERATING_DRAFT" || appState.taskStatus === "SAFETY_CHECKING") {
    text = "病历草稿已生成，请逐项核对字段。";
  } else if (appState.taskStatus === "TRANSCRIBED" || appState.currentAsrResult) {
    text = "对话已转写，请核对医生/患者角色。";
  }

  prompt.textContent = text;
  prompt.className = `step-prompt ${tone}`.trim();
}

function openDrawer(panelId, title) {
  $("drawerTitle").textContent = title;
  $("drawerBackdrop").classList.add("active");
  $("drawer").classList.add("active");
  $("drawer").setAttribute("aria-hidden", "false");
  document.querySelectorAll(".drawer-panel").forEach((panel) => panel.classList.remove("active"));
  $(panelId).classList.add("active");
}

function closeDrawer() {
  $("drawerBackdrop").classList.remove("active");
  $("drawer").classList.remove("active");
  $("drawer").setAttribute("aria-hidden", "true");
}

function renderPatientBar() {
  const llm = llmDisplayState();
  $("patientName").textContent = "模拟患者";
  $("patientProfile").textContent = "女 / 32岁";
  $("sessionId").textContent = appState.currentTaskId
    ? `T-${appState.currentTaskId}`
    : appState.currentAsrSessionId
      ? `S-${appState.currentAsrSessionId.slice(0, 8)}`
      : appState.currentAudioId
        ? `A-${appState.currentAudioId}`
        : "未创建";
  $("recordingStatus").textContent = appState.uploadedFilename || "未上传";
  $("asrEngine").textContent = ENGINE_LABELS[appState.selectedEngine] || appState.selectedEngine;
  $("llmProvider").textContent = llm.provider;
  $("llmModel").textContent = llm.model;
  $("llmFallback").textContent = llm.fallbackLabel;
  $("reviewStatus").textContent = STATUS_LABELS[appState.taskStatus] || appState.taskStatus || "等待输入";
}

function llmDisplayState() {
  const traceLlm = appState.currentAgentTrace?.llm;
  const status = appState.currentLlmStatus || {};
  const provider = traceLlm?.llm_provider || status.provider || "mock";
  const model = traceLlm?.model || status.model || "mock-deterministic-extractor";
  const fallback = traceLlm?.fallback ?? status.fallback ?? false;
  const checked = status.checked ?? Boolean(traceLlm);
  const configured = status.configured ?? true;
  let fallbackLabel = "否";
  if (!configured || fallback) {
    fallbackLabel = `是：${status.fallback_provider || traceLlm?.actual_provider || "mock"}`;
  } else if (!checked && provider !== "mock") {
    fallbackLabel = "未测试";
  }
  return {
    provider,
    model,
    fallback,
    fallbackLabel,
    fallback_reason: traceLlm?.fallback_reason || status.fallback_reason || null,
  };
}

function renderWorkflow() {
  const activeKey = STATUS_TO_STEP[appState.taskStatus] || "CREATED";
  const activeIndex = WORKFLOW_STEPS.findIndex((step) => step.key === activeKey);
  $("workflowSteps").innerHTML = WORKFLOW_STEPS.map((step, index) => {
    const state = index < activeIndex ? "done" : index === activeIndex ? "active" : "";
    return `<li class="workflow-step ${state}">${escapeHtml(step.label)}</li>`;
  }).join("");
}

function fieldStatus(field, key) {
  if (key === "treatment_plan") {
    return appState.currentDraft
      ? { key: "candidate", label: "候选待确认" }
      : { key: "missing", label: "待补充" };
  }
  if (!field || field.missing || (!field.value && field.hint)) return { key: "missing", label: "待补充" };
  if (field.confirmed_by_doctor) return { key: "confirmed", label: "已确认" };
  if (typeof field.confidence === "number" && field.confidence < 0.7) return { key: "low", label: "低置信度" };
  return { key: "confirmed", label: "已确认" };
}

function fieldValue(fields, key) {
  if (key === "treatment_plan") {
    return appState.currentDraft ? "处理建议已生成在右栏病历草稿中，需医生确认后写入。" : "待医生补充处理建议";
  }
  const field = fields?.[key];
  return field?.value || field?.hint || "暂无内容";
}

function fieldEvidence(field, key) {
  if (key === "treatment_plan") return "处理建议来自 AI 病历草稿，需医生结合诊疗规范确认。";
  const spans = field?.source_spans || [];
  return spans.length ? spans.map((span) => span.text).filter(Boolean).join("\n") : "暂无证据片段，需结合原始转写复核。";
}

function diagnosisList(items) {
  if (!Array.isArray(items)) return [];
  return items.map((item) => String(item || "").trim()).filter(Boolean);
}

function diagnosisConfidence(diagnosis = {}) {
  if (diagnosis.confidence == null) return "规则置信度待评估";
  return `规则置信度 ${Math.round(Number(diagnosis.confidence) * 100)}%`;
}

function renderDiagnosisDetailLine(label, value) {
  if (!value) return "";
  return `
    <div class="diagnosis-detail">
      <span>${escapeHtml(label)}</span>
      <strong>${escapeHtml(value)}</strong>
    </div>
  `;
}

function renderDiagnosisDetailList(label, items) {
  const values = diagnosisList(items);
  if (!values.length) return "";
  return renderDiagnosisDetailLine(label, values.join("；"));
}

function renderDiagnosisDetails(diagnosis = {}) {
  const ruleText = [diagnosis.rule_id, diagnosisConfidence(diagnosis)].filter(Boolean).join(" · ");
  const details = [
    renderDiagnosisDetailLine("规则", ruleText),
    renderDiagnosisDetailLine("触发原因", diagnosis.reason),
    renderDiagnosisDetailList("建议检查", diagnosis.suggested_checks),
    renderDiagnosisDetailList("用药提示", diagnosis.medication_notes),
    renderDiagnosisDetailList("风险提醒", diagnosis.risk_warnings),
    renderDiagnosisDetailList("建议补问", diagnosis.follow_up_questions),
  ].join("");
  return details || `<div class="diagnosis-detail"><span>规则说明</span><strong>暂无扩展说明，需医生结合原始转写复核。</strong></div>`;
}

function renderFields() {
  const fields = appState.currentRecordFields;
  if (!fields) {
    $("fieldCountBadge").textContent = "待生成";
    $("fieldCountBadge").className = "status-badge neutral";
    $("recordFields").innerHTML = `<div class="empty-state">暂无病历字段。请点击“文本导入”或“上传生成病历”。</div>`;
    return;
  }

  let missingCount = 0;
  const cards = FIELD_DEFS.map(([key, title]) => {
    const field = fields[key] || null;
    const status = fieldStatus(field, key);
    if (status.key === "missing") missingCount += 1;
    const confidence = key === "treatment_plan" ? null : field?.confidence;
    return `
      <article class="field-card ${status.key}" data-field="${key}">
        <div class="field-head">
          <span class="field-title">${escapeHtml(title)}</span>
          <span class="status-badge ${status.key}">${escapeHtml(status.label)}</span>
        </div>
        <div class="field-value">${escapeHtml(fieldValue(fields, key))}</div>
        <div class="field-meta">
          <span class="confidence">${confidence == null ? "需医生复核" : `置信度 ${Math.round(confidence * 100)}%`}</span>
          <button type="button" data-evidence-toggle>证据</button>
        </div>
        <div class="field-evidence">${escapeHtml(fieldEvidence(field, key))}</div>
      </article>
    `;
  }).join("");

  const diagnoses = (fields.candidate_diagnoses || []).map((diagnosis, index) => `
    <article class="field-card candidate" data-field="diagnosis-${index}">
      <div class="field-head">
        <span class="field-title">候选诊断</span>
        <span class="status-badge candidate">${diagnosis.confirmed_by_doctor ? "已确认" : "候选待确认"}</span>
      </div>
      <div class="field-value">${escapeHtml(diagnosis.name || "未命名诊断")}</div>
      <div class="field-meta">
        <span class="confidence">${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</span>
        <button type="button" data-evidence-toggle>证据</button>
      </div>
      <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
      <div class="field-evidence">${escapeHtml((diagnosis.evidence || []).map((item) => item.text).join("\n") || "暂无候选诊断证据。")}</div>
    </article>
  `).join("");

  $("fieldCountBadge").textContent = missingCount ? `${missingCount}项待补充` : "待医生确认";
  $("fieldCountBadge").className = `status-badge ${missingCount ? "missing" : "confirmed"}`;
  $("recordFields").innerHTML = cards + diagnoses;
}

function classifySpeaker(line, segment = {}) {
  const raw = `${segment.role || ""} ${segment.speaker || ""} ${line}`.toLowerCase();
  if (raw.includes("医生") || raw.includes("doctor")) return "doctor";
  if (raw.includes("患者") || raw.includes("patient")) return "patient";
  return "unknown";
}

function roleLabelFromSegment(segment = {}, fallbackLine = "") {
  const speaker = classifySpeaker(fallbackLine, segment);
  if (speaker === "doctor") return "医生";
  if (speaker === "patient") return "患者";
  return "待确认";
}

function speakerClassFromRole(role) {
  if (role === "医生") return "doctor";
  if (role === "患者") return "patient";
  return "unknown";
}

function segmentTime(segment = {}, index = 0) {
  return segment.start_time != null ? `${Number(segment.start_time).toFixed(1)}s` : `00:${String(index * 8).padStart(2, "0")}`;
}

function conversationFromSegments(segments = []) {
  return segments
    .map((segment) => `[${segment.role || "待确认"}] ${segment.text || ""}`)
    .join("\n");
}

function textFromSegments(segments = []) {
  return segments.map((segment) => segment.text || "").filter(Boolean).join("\n");
}

function currentReviewSegments() {
  if (appState.currentAsrResult?.segments?.length) return appState.currentAsrResult.segments;
  return appState.liveTranscriptSegments;
}

function syncAsrTextFromSegments() {
  const segments = currentReviewSegments();
  if (!segments.length || !appState.currentAsrResult) return;
  appState.currentAsrResult.segments = segments;
  appState.currentAsrResult.text = textFromSegments(segments);
  appState.currentAsrResult.conversation_text = conversationFromSegments(segments);
  appState.currentAsrResult.needs_review = segments.some((segment) => segment.needs_review || segment.role === "待确认" || !segment.reviewed_by_doctor);
}

function transcriptRowsFromText(text) {
  const normalized = String(text || "")
    .replace(/\s*(\[(?:医生|患者|doctor|patient|待校正)\])/gi, "\n$1")
    .trim();
  return normalized
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => ({
      index,
      editable: false,
      time: `00:${String(index * 8).padStart(2, "0")}`,
      speaker: classifySpeaker(line),
      label: classifySpeaker(line) === "doctor" ? "医生" : classifySpeaker(line) === "patient" ? "患者" : "待确认",
      text: line.replace(/^\[(医生|患者|doctor|patient|待校正)\]\s*/i, ""),
    }));
}

function transcriptRows() {
  if (appState.liveTranscriptSegments.length) {
    return appState.liveTranscriptSegments.map((segment, index) => {
      const label = roleLabelFromSegment(segment, segment.text || "");
      return {
        index,
        editable: Boolean(appState.currentAsrResult),
        time: segmentTime(segment, index),
        speaker: speakerClassFromRole(label),
        label,
        text: segment.text || "",
        confidence: segment.confidence,
        needsReview: Boolean(segment.needs_review || label === "待确认"),
        reviewedByDoctor: Boolean(segment.reviewed_by_doctor),
      };
    });
  }
  const asr = appState.currentAsrResult;
  if (asr?.segments?.length > 1) {
    return asr.segments.map((segment, index) => {
      const label = roleLabelFromSegment(segment, segment.text || "");
      return {
        index,
        editable: true,
        time: segmentTime(segment, index),
        speaker: speakerClassFromRole(label),
        label,
        text: segment.text || "",
        confidence: segment.confidence,
        needsReview: Boolean(segment.needs_review || label === "待确认"),
        reviewedByDoctor: Boolean(segment.reviewed_by_doctor),
      };
    });
  }
  if (asr) return transcriptRowsFromText(asr.conversation_text || asr.text || "");
  return transcriptRowsFromText(appState.currentInputText);
}

function renderRoleOptions(selectedRole) {
  return ROLE_OPTIONS.map(([value, label]) => (
    `<option value="${escapeHtml(value)}" ${selectedRole === value ? "selected" : ""}>${escapeHtml(label)}</option>`
  )).join("");
}

function asrProgressPercent() {
  const progress = Math.max(0, Math.min(1, Number(appState.asrStreamProgress || 0)));
  return Math.round(progress * 100);
}

function renderTranscriptStatusPanel({ rows, asr, isStreaming, reviewable, unreviewedCount }) {
  const progress = asrProgressPercent();
  const total = appState.asrStreamTotalSegments || asr?.segments?.length || rows.length || 0;
  const current = asr
    ? total
    : Math.min(appState.asrStreamCurrentSegment || rows.length || 0, total || rows.length || 0);
  const statusText = appState.asrLastError
    ? "转写异常"
    : asr
      ? "转写完成"
      : isStreaming
        ? "转写中"
        : rows.length
          ? "待校正"
          : "等待输入";
  const canGenerateFromTranscript = Boolean(asr && !appState.currentTaskId && !appState.currentRecordFields);
  const actionButton = asr
    ? roleReviewRequired()
      ? `<button type="button" class="secondary-action" data-save-role-review ${appState.roleReviewSaving ? "disabled" : ""}>保存角色校正</button>`
      : canGenerateFromTranscript
        ? `<button type="button" class="primary-action" data-generate-from-transcript>用校正文本生成病历</button>`
        : ""
    : "";
  const reviewText = reviewable
    ? unreviewedCount
      ? `${unreviewedCount} 段待确认`
      : "角色已确认"
    : "完成转写后校正";
  return `
    <section class="transcript-status-panel ${appState.asrLastError ? "danger" : isStreaming ? "active" : asr ? "done" : ""}" aria-label="转写状态">
      <div class="transcript-status-head">
        <div>
          <span class="meta-label">当前状态</span>
          <strong>${escapeHtml(statusText)}</strong>
        </div>
        <span class="status-badge ${appState.asrLastError ? "missing" : asr ? "confirmed" : isStreaming ? "info" : "neutral"}">${escapeHtml(asr?.engine || appState.selectedEngine || "ASR")}</span>
      </div>
      <div class="progress-track" aria-label="转写进度">
        <span style="width: ${progress}%"></span>
      </div>
      <div class="status-metrics">
        <div><span>进度</span><strong>${progress}%</strong></div>
        <div><span>分段</span><strong>${current || 0}/${total || 0}</strong></div>
        <div><span>文件</span><strong>${escapeHtml(appState.uploadedFilename || "未上传")}</strong></div>
        <div><span>校正</span><strong>${escapeHtml(reviewText)}</strong></div>
      </div>
      ${appState.asrLastError ? `<div class="safety-strip danger">${escapeHtml(appState.asrLastError)}</div>` : ""}
      ${actionButton ? `<div class="quick-action-row">${actionButton}</div>` : ""}
    </section>
  `;
}

function renderTranscript() {
  const asr = appState.currentAsrResult;
  const rows = transcriptRows();
  const warningBlocks = [];
  const isStreaming = appState.currentAsrSessionId && appState.taskStatus === "TRANSCRIBING" && !asr;
  if (asr?.role_strategy === "single_segment_needs_review") {
    warningBlocks.push("当前 ASR 返回单段长文本，医生/患者角色需人工校正。");
  }
  (asr?.warnings || []).forEach((warning) => warningBlocks.push(warning));

  if (!rows.length && !asr && !appState.currentAsrSessionId) {
    $("transcriptBadge").textContent = "待转写";
    $("transcriptList").innerHTML = `<div class="empty-state">暂无对话转写。可导入文本或上传音频。</div>`;
    return;
  }

  $("transcriptBadge").textContent = asr
    ? `${asr.engine || appState.selectedEngine} · ${asr.segments?.length || 0}段`
    : isStreaming
      ? `SSE · ${rows.length}段 · ${asrProgressPercent()}%`
      : `${rows.length}条`;

  const streamBlock = appState.currentAsrSessionId
    ? `<div class="safety-strip debug-only ${asr ? "success" : "warning"}"><strong>SSE 实时转写</strong><br>会话 ${escapeHtml(appState.currentAsrSessionId)} · ${asr ? "已完成" : `进行中 ${asrProgressPercent()}%`}</div>`
    : "";
  const asrTextBlock = asr?.text
    ? `<div class="safety-strip debug-only"><strong>ASRResult.text</strong><br>${escapeHtml(asr.text)}</div>`
    : "";
  const conversationBlock = asr?.conversation_text
    ? `<div class="safety-strip debug-only"><strong>conversation_text</strong><br>${escapeHtml(asr.conversation_text)}</div>`
    : "";
  const reviewable = Boolean(appState.currentAsrSessionId && asr?.segments?.length);
  const unreviewedCount = rows.filter((item) => item.needsReview || !item.reviewedByDoctor).length;
  const roleReviewBlock = reviewable
    ? `
      <div class="role-review-bar ${unreviewedCount ? "pending" : "reviewed"}">
        <div>
          <strong>${unreviewedCount ? `${unreviewedCount} 段待确认` : "角色已确认"}</strong>
          <span>${appState.roleReviewDirty ? "存在未保存校正" : "校正结果会用于后续病历生成"}</span>
        </div>
        <button type="button" data-save-role-review ${appState.roleReviewSaving ? "disabled" : ""}>
          ${appState.roleReviewSaving ? "保存中" : "保存角色校正"}
        </button>
      </div>
    `
    : "";

  $("transcriptList").innerHTML = `
    ${renderTranscriptStatusPanel({ rows, asr, isStreaming, reviewable, unreviewedCount })}
    ${warningBlocks.map((item) => `<div class="conversation-warning">${escapeHtml(item)}</div>`).join("")}
    ${streamBlock}
    ${roleReviewBlock}
    ${asrTextBlock}
    ${conversationBlock}
    ${rows.map((item, index) => `
      <div class="chat-row">
        <div class="chat-time">${escapeHtml(item.time)}</div>
        <div class="chat-card ${index === 1 ? "highlight" : ""} ${item.needsReview ? "needs-review" : ""} ${item.reviewedByDoctor ? "reviewed" : ""}" data-segment-index="${item.index}">
          <div class="chat-tools">
            <select data-role-select ${item.editable ? "" : "disabled"}>
              ${renderRoleOptions(item.label)}
            </select>
            <span class="status-badge ${item.needsReview ? "candidate" : item.reviewedByDoctor ? "confirmed" : "neutral"}">
              ${item.needsReview ? "待确认" : item.reviewedByDoctor ? "已校正" : "未保存"}
            </span>
            <span class="confidence">${item.confidence == null ? "置信度待评估" : `置信度 ${Math.round(item.confidence * 100)}%`}</span>
          </div>
          <textarea data-segment-text ${item.editable ? "" : "disabled"}>${escapeHtml(item.text)}</textarea>
        </div>
      </div>
    `).join("")}
  `;
}

function missingItems() {
  const fields = appState.currentRecordFields;
  if (!fields) return [];
  return FIELD_DEFS.filter(([key]) => fieldStatus(fields[key], key).key === "missing").map(([, label]) => label);
}

function allEvidence() {
  const fields = appState.currentRecordFields;
  if (!fields) return [];
  const evidence = [];
  FIELD_DEFS.forEach(([key, label]) => {
    if (key === "treatment_plan") return;
    (fields[key]?.source_spans || []).forEach((span) => {
      if (span.text) evidence.push(`${label}：${span.text}`);
    });
  });
  (fields.candidate_diagnoses || []).forEach((diagnosis) => {
    (diagnosis.evidence || []).forEach((span) => {
      if (span.text) evidence.push(`候选诊断 ${diagnosis.name}：${span.text}`);
    });
  });
  return evidence.slice(0, 8);
}

function renderEvaluationBlock() {
  const evaluation = appState.currentEvaluation;
  if (!evaluation) {
    return `<div class="empty-state">暂无 ASR 评测结果。完成音频转写后点击“ASR评测”。</div>`;
  }
  const keywords = evaluation.medical_keywords || {};
  return `
    <div class="metric-grid">
      <div class="metric-card"><span>CER</span><strong>${Number(evaluation.cer ?? 0).toFixed(4)}</strong></div>
      <div class="metric-card"><span>keyword_recall</span><strong>${Number(evaluation.keyword_recall ?? 0).toFixed(2)}</strong></div>
    </div>
    <div class="safety-strip success"><strong>recognized</strong><br>${escapeHtml((keywords.recognized || []).join("、") || "无")}</div>
    <div class="safety-strip ${keywords.missing?.length ? "warning" : "success"}"><strong>missing</strong><br>${escapeHtml((keywords.missing || []).join("、") || "无")}</div>
  `;
}

function buildLocalAgentTrace() {
  const asr = appState.currentAsrResult;
  const task = appState.currentTask || {};
  const llmStatus = appState.currentLlmStatus || {};
  const llmFallback = llmStatus.configured === false || llmStatus.checked
    ? Boolean(llmStatus.fallback)
    : false;
  const inputType = asr && asr.audio_id !== "text-import" ? "audio" : "text";
  const plan = inputType === "audio"
    ? ["ASR_TRANSCRIBE", "FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK", "DOCTOR_REVIEW"]
    : ["TEXT_INPUT_NORMALIZE", "FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK", "DOCTOR_REVIEW"];
  return {
    agent_mode: "Plan-and-Execute + Human-in-the-loop",
    input_type: inputType,
    perception: inputType === "audio"
      ? {
          source: "audio_asr",
          asr_engine: asr?.engine || appState.selectedEngine,
          audio_id: asr?.audio_id || appState.currentAudioId,
          role_strategy: asr?.role_strategy || null,
          warnings: asr?.warnings || [],
          segments_count: asr?.segments?.length || 0,
        }
      : {
          source: "text_input",
          text_length: (appState.currentInputText || asr?.conversation_text || "").length,
          warnings: [],
        },
    llm: {
      llm_provider: llmStatus.provider || "mock",
      model: llmStatus.model || "mock-deterministic-extractor",
      latency_ms: null,
      fallback: llmFallback,
      fallback_reason: llmFallback ? llmStatus.fallback_reason || null : null,
      actual_provider: llmFallback ? "mock" : llmStatus.provider || "mock",
    },
    plan,
    executed_steps: (appState.currentSteps || []).map((step) => ({
      step: {
        extract_fields: "FIELD_EXTRACTION",
        generate_draft: "DRAFT_GENERATION",
        safety_check: "SAFETY_CHECK",
      }[step.step_name] || String(step.step_name || "UNKNOWN_STEP").toUpperCase(),
      status: step.status || "UNKNOWN",
      duration_ms: step.duration_ms ?? null,
    })),
    decision: {
      next_state: task.status || appState.taskStatus || "CREATED",
      export_allowed: false,
      reason: "doctor_review_required",
      human_in_the_loop_required: true,
      doctor_review_required: true,
      safety_passed: appState.currentSafetyCheck?.passed ?? null,
      safety_blocked: appState.currentSafetyCheck?.blocked ?? null,
    },
  };
}

function currentAgentTrace() {
  return appState.currentAgentTrace || buildLocalAgentTrace();
}

function assistDetails({ title, badgeClass = "neutral", badgeText = "-", body = "", open = false, tone = "" }) {
  return `
    <details class="assist-block assist-details ${tone}" ${open ? "open" : ""}>
      <summary class="assist-title">
        <h3>${escapeHtml(title)}</h3>
        <span class="status-badge ${badgeClass}">${escapeHtml(badgeText)}</span>
      </summary>
      <div class="assist-body">
        ${body}
      </div>
    </details>
  `;
}

function renderAgentTraceSummary({ open = false } = {}) {
  const trace = currentAgentTrace();
  const perception = trace.perception || {};
  const llm = trace.llm || {};
  const decision = trace.decision || {};
  const perceptionText = trace.input_type === "audio"
    ? `${perception.asr_engine || "ASR"} / role_strategy=${perception.role_strategy || "none"}`
    : `${perception.source || "text_input"} / length=${perception.text_length || 0}`;
  return assistDetails({
    title: "Agent 决策轨迹",
    badgeClass: "info",
    badgeText: "Trace",
    open,
    body: `
        <div class="safety-strip"><strong>输入类型</strong><br>${escapeHtml(trace.input_type)}</div>
        <div class="safety-strip"><strong>感知结果</strong><br>${escapeHtml(perceptionText)}</div>
        <div class="safety-strip ${llm.fallback ? "warning" : "success"}"><strong>LLM Provider</strong><br>${escapeHtml(llm.llm_provider || "mock")} / ${escapeHtml(llm.model || "mock-deterministic-extractor")}</div>
        <div class="safety-strip ${llm.fallback ? "warning" : ""}"><strong>LLM Fallback</strong><br>${llm.fallback ? `已兜底：${escapeHtml(llm.fallback_reason || "unknown")}` : `未触发，latency=${escapeHtml(String(llm.latency_ms ?? "-"))}ms`}</div>
        <div class="safety-strip"><strong>计划步骤</strong><br>${escapeHtml((trace.plan || []).join(" -> "))}</div>
        <div class="safety-strip"><strong>当前状态</strong><br>${escapeHtml(decision.next_state || "-")}</div>
        <div class="safety-strip danger"><strong>导出决策</strong><br>禁止自动导出：${escapeHtml(decision.reason || "doctor_review_required")}</div>
        <div class="safety-strip warning"><strong>医生审核边界</strong><br>Human-in-the-loop required before final export</div>
    `,
  });
}

async function refreshAgentTrace(taskId) {
  if (!taskId) {
    appState.currentAgentTrace = buildLocalAgentTrace();
    return;
  }
  const suffix = appState.currentAudioId
    ? `?audio_id=${encodeURIComponent(appState.currentAudioId)}`
    : "";
  try {
    appState.currentAgentTrace = await api(`/api/tasks/${taskId}/trace${suffix}`);
  } catch (_error) {
    appState.currentAgentTrace = buildLocalAgentTrace();
  }
}

async function refreshLlmStatus({ test = false } = {}) {
  try {
    appState.currentLlmStatus = await api(
      test ? "/api/llm/test" : "/api/llm/status",
      { method: test ? "POST" : "GET" },
    );
    renderPatientBar();
    renderDebug();
    return appState.currentLlmStatus;
  } catch (error) {
    appState.currentLlmStatus = {
      provider: "unknown",
      model: "not_configured",
      configured: false,
      reachable: false,
      checked: test,
      fallback_provider: "mock",
      fallback: true,
      fallback_reason: error.message,
    };
    renderPatientBar();
    return appState.currentLlmStatus;
  }
}

function saveBehaviorBlock() {
  return assistDetails({
    title: "草稿保存说明",
    badgeClass: "info",
    badgeText: "SQLite",
    open: false,
    body: `
        <div class="storage-note">
          <strong>“保存草稿到SQLite”会调用 <code>POST /api/tasks/{task_id}/review</code>。</strong>
          <ul>
            <li>写入 SQLite：是，更新当前 Task 的审核结果并记录审计日志。</li>
            <li>保存病历字段：是，保存医生端当前字段卡片内容。</li>
            <li>保存 ASRResult：不是此按钮负责；转写完成时已保存在 <code>data/uploads/{audio_id}.transcript.json</code>。</li>
            <li>保存 Agent Trace：不单独写库；可通过 <code>/api/tasks/{task_id}/trace</code> 和调试抽屉查看。</li>
            <li>生成文件：不会；只有点击“确认导出”后才写入 <code>data/outputs/</code>。</li>
          </ul>
        </div>
        <div class="safety-strip">
          <strong>草稿查看位置</strong><br>
          doctor.html 左侧字段卡片 / debug.html Task JSON 的 result_json / docs/dev_logs/runs/ 运行日志 / 导出后的 data/outputs/
        </div>
    `,
  });
}

function runLogBlock() {
  return assistDetails({
    title: "演示运行日志",
    badgeClass: "info",
    badgeText: "Run Log",
    open: false,
    body: `
        <div class="safety-strip"><strong>task_id</strong><br>${escapeHtml(appState.currentTaskId || "-")}</div>
        <div class="safety-strip"><strong>audio_id</strong><br>${escapeHtml(appState.currentAudioId || "-")}</div>
        <div class="safety-strip"><strong>生成命令</strong><br><code>${escapeHtml(runLogCommand())}</code></div>
    `,
  });
}

function renderAssist() {
  const fields = appState.currentRecordFields;
  const safety = appState.currentSafetyCheck;
  const missing = missingItems();
  const diagnoses = fields?.candidate_diagnoses || [];
  const evidence = allEvidence();
  const risk = riskSummary();
  const warnings = risk.warnings;
  if (appState.currentAsrResult?.role_strategy === "single_segment_needs_review") {
    warnings.unshift("医生/患者角色需人工校正");
  }
  const errors = risk.errors;
  const safetyHasRisk = warnings.length > 0 || errors.length > 0 || Boolean(safety && (!safety.passed || safety.blocked));
  const evaluationMissing = risk.evaluationMissing;
  const trace = currentAgentTrace();
  const traceLlm = trace.llm || {};
  const traceHasRisk = Boolean(traceLlm.fallback)
    || errors.length > 0
    || Boolean(safety?.blocked)
    || Boolean(safety && !safety.passed)
    || missing.length > 0
    || evaluationMissing.length > 0
    || Boolean(trace.decision?.safety_blocked);
  const tabs = [
    ["ai", "AI辅助"],
    ["evidence", "证据与评测"],
    ["safety", "安全校验"],
  ];
  if (appState.viewMode === "debug") {
    tabs.splice(2, 0, ["trace", "Agent Trace"]);
  }
  const activeTab = tabs.some(([key]) => key === appState.assistTab) ? appState.assistTab : "ai";

  const aiContent = `
    ${assistDetails({
      title: "缺失项提醒",
      badgeClass: missing.length ? "missing" : "confirmed",
      badgeText: missing.length ? `${missing.length}项` : "无",
      open: missing.length > 0,
      tone: missing.length ? "risk-danger" : "normal-success",
      body: missing.length ? `<div class="safety-strip danger">${escapeHtml(missing.join("、"))}</div>` : `<div class="safety-strip success">暂无结构化字段缺失。</div>`,
    })}

    ${assistDetails({
      title: "候选诊断",
      badgeClass: diagnoses.length ? "candidate" : "confirmed",
      badgeText: diagnoses.length ? "待确认" : "暂无",
      open: diagnoses.length > 0,
      tone: diagnoses.length ? "risk-warning" : "normal-success",
      body: diagnoses.length ? diagnoses.map((diagnosis) => `
          <div class="diagnosis-card">
            <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong>
            <div class="diagnosis-status">${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
          </div>
        `).join("") : `<div class="safety-strip success">暂无候选诊断。</div>`,
    })}

    ${assistDetails({
      title: "病历草稿",
      badgeClass: appState.currentDraft ? "info" : "neutral",
      badgeText: appState.currentDraft ? "已生成" : "待生成",
      open: false,
      body: `<div class="draft-block">${escapeHtml(appState.currentDraft || "暂无病历草稿。")}</div>`,
    })}
    ${saveBehaviorBlock()}
  `;

  const evidenceContent = `
    ${assistDetails({
      title: "字段证据",
      badgeClass: "info",
      badgeText: evidence.length ? "可追溯" : "暂无",
      open: false,
      body: evidence.length ? evidence.map((item) => `<button type="button" class="evidence-chip">${escapeHtml(item)}</button>`).join("") : `<div class="empty-state">暂无字段证据。</div>`,
    })}

    ${appState.viewMode === "debug" ? assistDetails({
      title: "ASR评测摘要",
      badgeClass: evaluationMissing.length ? "candidate" : "info",
      badgeText: "CER / Recall",
      open: evaluationMissing.length > 0,
      tone: evaluationMissing.length ? "risk-warning" : "",
      body: renderEvaluationBlock(),
    }) : ""}
    ${appState.viewMode === "debug" ? runLogBlock() : ""}
  `;

  const safetyContent = `
    ${assistDetails({
      title: "安全校验结果",
      badgeClass: safety?.passed && !safety?.blocked ? "confirmed" : "missing",
      badgeText: safety ? (safety.passed && !safety.blocked ? "通过" : "需处理") : "待校验",
      open: safetyHasRisk,
      tone: safetyHasRisk ? "risk-danger" : "normal-success",
      body: `
        ${warnings.map((item) => `<div class="safety-strip warning">${escapeHtml(item)}</div>`).join("")}
        ${errors.map((item) => `<div class="safety-strip danger">${escapeHtml(item)}</div>`).join("")}
        ${safety ? `<div class="safety-strip ${safety.passed && !safety.blocked ? "success" : "danger"}">安全校验：${safety.passed ? "通过" : "未通过"}${safety.blocked ? " / 阻止导出" : ""}</div>` : `<div class="empty-state">暂无AI校验结果。</div>`}
      `,
    })}
  `;

  const contentByTab = {
    ai: aiContent,
    evidence: evidenceContent,
    trace: `${renderAgentTraceSummary({ open: traceHasRisk })}${runLogBlock()}`,
    safety: safetyContent,
  };

  $("assistPanels").innerHTML = `
    <div class="assist-tabs" role="tablist" aria-label="右栏分区">
      ${tabs.map(([key, label]) => `
        <button type="button" class="assist-tab ${key === activeTab ? "active" : ""}" data-assist-tab="${key}" role="tab" aria-selected="${key === activeTab ? "true" : "false"}">
          ${escapeHtml(label)}
        </button>
      `).join("")}
    </div>
    ${contentByTab[activeTab]}
  `;
}

function renderDebug() {
  const debugRunLog = $("debugRunLogCommand");
  if (debugRunLog) debugRunLog.textContent = runLogCommand();
  renderJson($("debugAsrJson"), appState.currentAsrResult);
  renderJson($("debugAgentTraceJson"), currentAgentTrace());
  renderJson($("debugTaskJson"), appState.currentTask);
  renderJson($("debugStepsJson"), appState.currentSteps);
  renderJson($("debugSafetyJson"), appState.currentSafetyCheck);
}

function renderFooter() {
  $("currentTaskLabel").textContent = `当前任务：${STATUS_LABELS[appState.taskStatus] || appState.taskStatus || "等待输入"}`;
  $("currentTaskHint").textContent = appState.currentTaskId
    ? `任务 ${appState.currentTaskId} · ${appState.currentAudioId ? `音频 ${appState.currentAudioId}` : "文本导入"}`
    : "可通过文本导入或上传音频生成病历。";
  $("regenerateButton").disabled = appState.busy || !(appState.currentAsrResult || appState.currentInputText);
  $("saveDraftButton").disabled = appState.busy || !appState.currentTaskId || !appState.currentRecordFields;
  $("confirmFieldsButton").disabled = appState.busy || !appState.currentTaskId || !appState.currentRecordFields;
  $("exportButton").disabled = appState.busy || !appState.currentTaskId || !isApprovedForExport();
}

function isApprovedForExport() {
  return appState.taskStatus === "approved" || appState.currentTask?.current_stage === "approved";
}

function renderAll() {
  renderMode();
  renderPatientBar();
  renderRunContext();
  renderStartGuide();
  renderStepPrompt();
  renderWorkflow();
  renderFields();
  renderTranscript();
  renderAssist();
  renderDebug();
  renderFooter();
}

function closeAsrStream() {
  if (appState.asrEventSource) {
    appState.asrEventSource.close();
    appState.asrEventSource = null;
  }
}

function resetRoleReviewState() {
  appState.roleReviewDirty = false;
  appState.roleReviewSaving = false;
}

function resetTaskState({ keepAsr = false } = {}) {
  appState.currentEvaluation = null;
  appState.currentTask = null;
  appState.currentSteps = [];
  appState.currentRecordFields = null;
  appState.currentDraft = "";
  appState.currentSafetyCheck = null;
  appState.currentAgentTrace = null;
  appState.currentInputText = "";
  if (!keepAsr) {
    closeAsrStream();
    appState.currentAsrResult = null;
    appState.currentAudioId = null;
    appState.currentAsrSessionId = null;
    appState.liveTranscriptSegments = [];
    appState.asrStreamProgress = 0;
    appState.asrStreamCurrentSegment = 0;
    appState.asrStreamTotalSegments = 0;
    appState.asrLastError = "";
    resetRoleReviewState();
    appState.uploadedFilename = "";
  }
}

async function refreshTask(taskId, taskFromEvent = null) {
  const task = taskFromEvent || await api(`/api/tasks/${taskId}`);
  const steps = await api(`/api/tasks/${taskId}/steps`);
  appState.currentTask = task;
  appState.currentSteps = steps;
  appState.currentTaskId = task.id || task.task_id || taskId;
  appState.taskStatus = task.current_stage || task.status || appState.taskStatus;
  const result = task.result_json || {};
  appState.currentRecordFields = result.fields || appState.currentRecordFields;
  appState.currentDraft = result.draft || appState.currentDraft;
  appState.currentSafetyCheck = result.safety_check || appState.currentSafetyCheck;
  await refreshAgentTrace(appState.currentTaskId);
  renderAll();
}

function listenForEvents(taskId, eventsUrl) {
  if (appState.eventSource) appState.eventSource.close();
  const source = new EventSource(eventsUrl);
  appState.eventSource = source;
  let terminalReceived = false;

  ["CREATED", "EXTRACTING_FIELDS", "GENERATING_DRAFT", "SAFETY_CHECKING", "DEGRADED"].forEach((status) => {
    source.addEventListener(status, (event) => {
      const data = JSON.parse(event.data);
      appState.currentTaskId = data.task_id;
      appState.taskStatus = data.status;
      appState.currentTask = { ...(appState.currentTask || {}), id: data.task_id, status: data.status, current_stage: data.current_stage };
      renderAll();
    });
  });

  source.addEventListener("WAITING_DOCTOR_REVIEW", async (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    appState.taskStatus = "WAITING_DOCTOR_REVIEW";
    await refreshTask(data.task_id, data.task);
    source.close();
    appState.eventSource = null;
    setBusy(false);
    showToast("病历已生成，等待医生审核");
  });

  source.addEventListener("FAILED", async (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    appState.taskStatus = "FAILED";
    await refreshTask(data.task_id, data.task);
    source.close();
    appState.eventSource = null;
    setBusy(false);
    showToast("任务失败");
  });

  source.onerror = () => {
    if (!terminalReceived) {
      appState.taskStatus = "FAILED";
      showToast("SSE 连接异常，请到调试页查看任务日志");
    }
    source.close();
    appState.eventSource = null;
    setBusy(false);
    renderAll();
  };
}

function listenForAsrEvents(eventsUrl, { resolve, reject } = {}) {
  closeAsrStream();
  const separator = eventsUrl.includes("?") ? "&" : "?";
  const source = new EventSource(`${eventsUrl}${separator}delay_ms=220`);
  appState.asrEventSource = source;
  let terminalReceived = false;

  source.addEventListener("session_created", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAsrSessionId = data.session_id || appState.currentAsrSessionId;
    appState.taskStatus = "CREATED";
    appState.asrStreamProgress = 0;
    appState.asrStreamCurrentSegment = 0;
    appState.asrStreamTotalSegments = 0;
    appState.asrLastError = "";
    renderAll();
  });

  source.addEventListener("audio_uploaded", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.uploadedFilename = data.filename || appState.uploadedFilename;
    appState.taskStatus = "TRANSCRIBING";
    renderAll();
  });

  source.addEventListener("transcribing", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.taskStatus = "TRANSCRIBING";
    setBusy(true, "正在实时转写音频...");
    renderAll();
  });

  source.addEventListener("segment", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrStreamProgress = Number(data.progress || appState.asrStreamProgress || 0);
    appState.asrStreamCurrentSegment = Number(data.index ?? appState.liveTranscriptSegments.length) + 1;
    appState.asrStreamTotalSegments = Number(data.total || appState.asrStreamTotalSegments || 0);
    if (data.segment) {
      appState.liveTranscriptSegments = [
        ...appState.liveTranscriptSegments,
        data.segment,
      ];
    }
    renderAll();
  });

  source.addEventListener("completed", (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.currentAsrResult = data.asr_result;
    appState.liveTranscriptSegments = data.asr_result?.segments || appState.liveTranscriptSegments;
    appState.taskStatus = "TRANSCRIBED";
    appState.asrStreamProgress = 1;
    appState.asrStreamTotalSegments = data.segments || data.asr_result?.segments?.length || appState.asrStreamTotalSegments || appState.liveTranscriptSegments.length;
    appState.asrStreamCurrentSegment = appState.asrStreamTotalSegments;
    appState.asrLastError = "";
    appState.currentEvaluation = null;
    resetRoleReviewState();
    closeAsrStream();
    setBusy(false);
    renderAll();
    showToast("音频实时转写完成");
    resolve?.({ audio_id: data.audio_id, asr_result: data.asr_result });
  });

  source.addEventListener("failed", (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    appState.taskStatus = "FAILED";
    appState.asrLastError = data.error || "ASR 实时转写失败";
    closeAsrStream();
    setBusy(false);
    renderAll();
    const error = new Error(data.error || "ASR 实时转写失败");
    showToast(error.message);
    reject?.(error);
  });

  source.onerror = () => {
    if (!terminalReceived) {
      appState.taskStatus = "FAILED";
      const error = new Error("ASR SSE 连接异常，请检查服务日志");
      appState.asrLastError = error.message;
      showToast(error.message);
      reject?.(error);
    }
    closeAsrStream();
    setBusy(false);
    renderAll();
  };
}

async function createRecordTask(conversationText) {
  resetTaskState();
  appState.currentInputText = conversationText;
  appState.currentAsrResult = {
    audio_id: "text-import",
    engine: "text-import",
    text: conversationText,
    conversation_text: conversationText,
    segments: [],
    duration: null,
    medical_keywords: {},
    warnings: [],
  };
  appState.taskStatus = "CREATED";
  renderAll();
  setBusy(true, "正在创建病历生成任务...");
  const created = await api("/api/records/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_text: conversationText }),
  });
  appState.currentTaskId = created.task_id;
  appState.taskStatus = created.status;
  appState.currentTask = { id: created.task_id, status: created.status };
  renderAll();
  listenForEvents(created.task_id, created.events_url);
}

function updateReviewSegment(index, patch) {
  const segments = currentReviewSegments();
  const segment = segments[index];
  if (!segment) return;
  if (patch.role !== undefined) segment.role = patch.role;
  if (patch.text !== undefined) segment.text = patch.text;
  segment.reviewed_by_doctor = true;
  segment.needs_review = !segment.role || segment.role === "待确认";
  appState.roleReviewDirty = true;
  syncAsrTextFromSegments();
  renderRunContext();
  renderDebug();
}

function roleReviewRequired() {
  const asr = appState.currentAsrResult;
  const segments = currentReviewSegments();
  return Boolean(
    asr?.needs_review
      || asr?.role_strategy === "single_segment_needs_review"
      || segments.some((segment) => segment.needs_review || !segment.role || segment.role === "待确认"),
  );
}

async function saveRoleReview({ silent = false } = {}) {
  if (!appState.currentAsrSessionId || !appState.currentAsrResult?.segments?.length) {
    if (!silent) showToast("暂无可保存的角色校正结果");
    return appState.currentAsrResult;
  }

  syncAsrTextFromSegments();
  appState.roleReviewSaving = true;
  renderAll();
  try {
    const segments = appState.currentAsrResult.segments.map((segment, index) => ({
      index,
      role: segment.role || "待确认",
      text: segment.text || "",
      reviewed_by_doctor: Boolean(segment.reviewed_by_doctor && segment.role && segment.role !== "待确认"),
    }));

    const response = await api(`/api/asr/sessions/${appState.currentAsrSessionId}/result`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer: "doctor",
        segments,
      }),
    });
    appState.currentAsrResult = response.asr_result;
    appState.liveTranscriptSegments = response.asr_result.segments || [];
    appState.currentAudioId = response.audio_id || appState.currentAudioId;
    appState.roleReviewDirty = false;
    if (!silent) showToast("角色校正已保存");
    return response.asr_result;
  } finally {
    appState.roleReviewSaving = false;
    renderAll();
  }
}

async function uploadAndTranscribe(file, engine) {
  if (!file) throw new Error("请选择音频文件");
  appState.selectedEngine = engine;
  appState.uploadedFilename = "上传中";
  appState.taskStatus = "CREATED";
  appState.currentAsrResult = null;
  appState.liveTranscriptSegments = [];
  appState.asrStreamProgress = 0;
  appState.asrStreamCurrentSegment = 0;
  appState.asrStreamTotalSegments = 0;
  appState.asrLastError = "";
  renderAll();

  setBusy(true, "正在创建 ASR 实时转写会话...");
  const session = await api(`/api/asr/sessions?engine=${encodeURIComponent(engine)}`, { method: "POST" });
  appState.currentAsrSessionId = session.session_id;
  renderAll();

  const form = new FormData();
  form.append("file", file);
  setBusy(true, "正在上传音频...");
  const uploaded = await api(`/api/asr/sessions/${session.session_id}/audio`, { method: "POST", body: form });
  appState.currentAudioId = uploaded.audio_id;
  appState.uploadedFilename = uploaded.filename || uploaded.audio_id;
  appState.taskStatus = "TRANSCRIBING";
  renderAll();

  setBusy(true, `正在使用 ${ENGINE_LABELS[engine] || engine} 实时转写...`);
  return new Promise((resolve, reject) => {
    listenForAsrEvents(uploaded.events_url, { resolve, reject });
  });
}

async function submitTextImport() {
  try {
    const text = $("conversationInput").value.trim();
    if (!text) throw new Error("请输入问诊文本");
    closeDrawer();
    await createRecordTask(text);
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

async function submitAudio() {
  try {
    closeDrawer();
    resetTaskState();
    const file = $("audioFileInput").files[0];
    const engine = $("audioEngineSelect").value;
    appState.selectedEngine = engine;
    const transcribed = await uploadAndTranscribe(file, engine);
    if (appState.audioMode === "generate") {
      if (roleReviewRequired()) {
        setBusy(false);
        showToast("转写完成，请先确认医生/患者角色后再生成病历");
        return;
      }
      setBusy(true, "正在从转写文本生成病历...");
      const created = await api(`/api/audio/${transcribed.audio_id}/generate-record`, { method: "POST" });
      appState.currentTaskId = created.task_id;
      appState.taskStatus = created.status;
      appState.currentTask = { id: created.task_id, status: created.status };
      renderAll();
      listenForEvents(created.task_id, created.events_url);
    } else {
      setBusy(false);
      renderAll();
    }
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

async function runEvaluation() {
  try {
    if (!appState.currentAudioId) throw new Error("暂无可评测的音频转写");
    const expectedKeywords = $("keywordsInput").value
      .split(/[\n,，]+/)
      .map((item) => item.trim())
      .filter(Boolean);
    appState.currentEvaluation = await api(`/api/audio/${appState.currentAudioId}/evaluate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ground_truth_text: $("groundTruthInput").value || " ",
        expected_keywords: expectedKeywords,
      }),
    });
    $("evaluationDrawerResult").innerHTML = renderEvaluationBlock();
    renderAll();
    showToast("ASR 评测完成");
  } catch (error) {
    $("evaluationDrawerResult").innerHTML = `<div class="safety-strip danger">${escapeHtml(error.message)}</div>`;
    showToast(error.message);
  }
}

async function regenerateRecord() {
  try {
    if (appState.roleReviewDirty) {
      await saveRoleReview({ silent: true });
    }
    if (roleReviewRequired()) {
      throw new Error("请先完成医生/患者角色校正");
    }
    const text = appState.currentAsrResult?.conversation_text || appState.currentInputText || $("conversationInput").value.trim();
    if (!text) throw new Error("暂无可重新生成的对话文本");
    await createRecordTask(text);
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

async function saveDraftReview() {
  try {
    if (!appState.currentTaskId || !appState.currentRecordFields) throw new Error("暂无可保存的病历字段");
    setBusy(true, "正在保存草稿到 SQLite...");
    appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: appState.currentRecordFields }),
    });
    await refreshTask(appState.currentTaskId, appState.currentTask);
    setBusy(false);
    showToast("草稿已保存到 SQLite");
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

async function confirmFields() {
  try {
    if (!appState.currentTaskId) throw new Error("暂无可确认的任务");
    setBusy(true, "正在确认字段...");
    appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/approve`, { method: "POST" });
    appState.taskStatus = "approved";
    await refreshTask(appState.currentTaskId, appState.currentTask);
    setBusy(false);
    showToast("字段已确认");
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

async function exportRecord() {
  try {
    if (!appState.currentTaskId) throw new Error("暂无可导出的任务");
    setBusy(true, "正在导出...");
    const result = await api(`/api/tasks/${appState.currentTaskId}/export`, { method: "POST" });
    appState.taskStatus = "EXPORTED";
    renderAll();
    setBusy(false);
    showToast(`导出完成：${Object.values(result.exports || {}).join(" / ")}`);
  } catch (error) {
    setBusy(false);
    showToast(error.message);
  }
}

function openTextImport() {
  openDrawer("textImportPanel", "文本导入生成病历");
}

function openAudioTranscribe() {
  appState.audioMode = "transcribe";
  $("audioPanelHint").textContent = "上传 MP3/WAV 预录音频，系统创建 ASR 会话并通过 SSE 实时显示分段转写。";
  $("submitAudioButton").textContent = "上传并实时转写";
  openDrawer("audioPanel", "MP3/WAV 实时转写");
}

function openAudioGenerate() {
  appState.audioMode = "generate";
  $("audioPanelHint").textContent = "上传 MP3/WAV 预录音频，先完成 SSE 实时转写，再进入病历生成流程。";
  $("submitAudioButton").textContent = "实时转写并生成病历";
  openDrawer("audioPanel", "MP3/WAV 生成病历");
}

function openEvaluation() {
  const expected = appState.currentAsrResult?.medical_keywords?.expected || [];
  if (expected.length && !$("keywordsInput").value.trim()) {
    $("keywordsInput").value = expected.join("\n");
  }
  $("evaluationDrawerResult").innerHTML = renderEvaluationBlock();
  openDrawer("evaluationPanel", "ASR 评测");
}

function openDebug() {
  renderDebug();
  openDrawer("debugPanel", "医生端调试详情");
}

async function testLlmConnection() {
  try {
    const status = await refreshLlmStatus({ test: true });
    const message = status.reachable
      ? `LLM自检通过：${status.provider} / ${status.model}`
      : `LLM自检未通过，运行时将使用 ${status.fallback_provider || "mock"} 兜底`;
    showToast(message);
    renderAll();
  } catch (error) {
    showToast(error.message);
  }
}

function bindEvents() {
  $("doctorModeButton").addEventListener("click", () => setViewMode("doctor"));
  $("debugModeButton").addEventListener("click", () => setViewMode("debug"));
  $("demoModeButton").addEventListener("click", () => setScreenshotMode(false));
  $("screenshotModeButton").addEventListener("click", () => setScreenshotMode(true));
  $("openTextImportButton").addEventListener("click", openTextImport);
  $("openAudioTranscribeButton").addEventListener("click", openAudioTranscribe);
  $("openAudioGenerateButton").addEventListener("click", openAudioGenerate);
  $("guideUploadAudioButton").addEventListener("click", openAudioGenerate);
  $("guideTextImportButton").addEventListener("click", openTextImport);
  $("openEvaluationButton").addEventListener("click", openEvaluation);
  $("testLlmButton").addEventListener("click", testLlmConnection);
  $("openDebugButton").addEventListener("click", openDebug);
  $("copyRunLogCommandButton").addEventListener("click", copyRunLogCommand);
  $("closeDrawerButton").addEventListener("click", closeDrawer);
  $("drawerBackdrop").addEventListener("click", closeDrawer);
  $("submitTextButton").addEventListener("click", submitTextImport);
  $("submitAudioButton").addEventListener("click", submitAudio);
  $("submitEvaluationButton").addEventListener("click", runEvaluation);
  $("audioEngineSelect").addEventListener("change", () => {
    appState.selectedEngine = $("audioEngineSelect").value;
    renderPatientBar();
  });
  $("recordFields").addEventListener("click", (event) => {
    if (event.target.matches("[data-evidence-toggle]")) {
      event.target.closest(".field-card").classList.toggle("open");
    }
  });
  $("transcriptList").addEventListener("change", (event) => {
    const roleSelect = event.target.closest("[data-role-select]");
    if (!roleSelect) return;
    const card = roleSelect.closest("[data-segment-index]");
    updateReviewSegment(Number(card.dataset.segmentIndex), { role: roleSelect.value });
    renderTranscript();
  });
  $("transcriptList").addEventListener("input", (event) => {
    const textInput = event.target.closest("[data-segment-text]");
    if (!textInput) return;
    const card = textInput.closest("[data-segment-index]");
    updateReviewSegment(Number(card.dataset.segmentIndex), { text: textInput.value });
  });
  $("transcriptList").addEventListener("click", async (event) => {
    const generateButton = event.target.closest("[data-generate-from-transcript]");
    if (generateButton) {
      await regenerateRecord();
      return;
    }
    const saveButton = event.target.closest("[data-save-role-review]");
    if (!saveButton) return;
    try {
      await saveRoleReview();
    } catch (error) {
      showToast(error.message);
    }
  });
  $("assistPanels").addEventListener("click", (event) => {
    const tabButton = event.target.closest("[data-assist-tab]");
    if (!tabButton) return;
    appState.assistTab = tabButton.dataset.assistTab;
    renderAssist();
  });
  $("regenerateButton").addEventListener("click", regenerateRecord);
  $("saveDraftButton").addEventListener("click", saveDraftReview);
  $("confirmFieldsButton").addEventListener("click", confirmFields);
  $("exportButton").addEventListener("click", exportRecord);
}

function init() {
  bindEvents();
  renderAll();
  refreshLlmStatus();
}

init();
