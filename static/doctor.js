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
  asrChunkCurrent: 0,
  asrChunkTotal: 0,
  asrChunkStatus: "",
  asrChunkLastError: "",
  asrRetryHint: "",
  roleReviewDirty: false,
  roleReviewSaving: false,
  lastActionError: "",
  inputMenuOpen: false,
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

const SUMMARY_FIELD_KEYS = [
  "chief_complaint",
  "present_illness",
  "physical_exam",
  "treatment_plan",
];

const WORKFLOW_STEPS = [
  { key: "INPUT", label: "1.输入" },
  { key: "TRANSCRIBING", label: "2.实时转写" },
  { key: "ROLE_REVIEW", label: "3.角色校正" },
  { key: "GENERATE_RECORD", label: "4.生成病历" },
  { key: "DOCTOR_REVIEW", label: "5.医生审核" },
  { key: "EXPORT", label: "6.导出" },
];

const STATUS_TO_STEP = {
  CREATED: "INPUT",
  TRANSCRIBING: "TRANSCRIBING",
  TRANSCRIBED: "ROLE_REVIEW",
  EXTRACTING_FIELDS: "GENERATE_RECORD",
  GENERATING_DRAFT: "GENERATE_RECORD",
  SAFETY_CHECKING: "GENERATE_RECORD",
  WAITING_DOCTOR_REVIEW: "DOCTOR_REVIEW",
  doctor_review: "DOCTOR_REVIEW",
  FAILED: "ROLE_REVIEW",
  reviewed: "DOCTOR_REVIEW",
  approved: "EXPORT",
  EXPORTED: "EXPORT",
  exported: "EXPORT",
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

function compactText(value, maxLength = 92) {
  const normalized = String(value ?? "")
    .replace(/\s+/g, " ")
    .trim();
  if (!normalized) return "暂无内容";
  if (normalized.length <= maxLength) return normalized;
  return `${normalized.slice(0, maxLength)}...`;
}

function detailButton(target, label = "查看详情") {
  return `<button type="button" class="detail-link" data-open-detail="${escapeHtml(target)}">${escapeHtml(label)}</button>`;
}

function detailSection(title, body) {
  return `
    <section class="detail-section">
      <h3>${escapeHtml(title)}</h3>
      <div>${body}</div>
    </section>
  `;
}

function listPreview(items, limit = 2) {
  const values = items.filter(Boolean);
  return {
    visible: values.slice(0, limit),
    hiddenCount: Math.max(0, values.length - limit),
  };
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
  if (!nextBusy) {
    renderFooter();
    renderNextActionPanel();
  }
}

function setActionError(message) {
  appState.lastActionError = message || "";
  renderNextActionPanel();
}

function clearActionError() {
  appState.lastActionError = "";
}

function showToast(text) {
  const toast = $("toast");
  toast.textContent = text;
  toast.classList.add("active");
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove("active"), 2200);
}

function reportActionError(error) {
  const message = error?.message || String(error || "操作失败");
  setActionError(message);
  showToast(message);
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

function renderInputMethodMenu() {
  const button = $("inputMethodButton");
  const menu = $("inputMethodMenu");
  button.classList.toggle("active", appState.inputMenuOpen);
  button.setAttribute("aria-expanded", appState.inputMenuOpen ? "true" : "false");
  menu.hidden = !appState.inputMenuOpen;
}

function closeInputMethodMenu() {
  appState.inputMenuOpen = false;
  renderInputMethodMenu();
}

function toggleInputMethodMenu() {
  appState.inputMenuOpen = !appState.inputMenuOpen;
  renderInputMethodMenu();
}

function renderStartGuide() {
  $("startGuide").hidden = appState.viewMode === "doctor" || hasActiveSession();
}

function renderStepPrompt() {
  const risk = riskSummary();
  const prompt = $("stepPrompt");
  let text = "请上传问诊音频或粘贴问诊文本开始。";
  let tone = "";

  if (appState.taskStatus === "EXPORTED" || appState.taskStatus === "exported") {
    text = "病历已导出，可归档或开始下一次任务。";
  } else if (hasActiveSession() && risk.hasRisk) {
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

function workflowStepKey() {
  if (appState.taskStatus === "EXPORTED" || appState.taskStatus === "exported") return "EXPORT";
  if (isApprovedForExport()) return "EXPORT";
  if (appState.currentRecordFields || appState.currentDraft) return "DOCTOR_REVIEW";
  if (appState.currentTaskId) return "GENERATE_RECORD";
  if (appState.currentAsrResult) {
    return roleReviewRequired() || appState.roleReviewDirty ? "ROLE_REVIEW" : "GENERATE_RECORD";
  }
  if (appState.taskStatus === "TRANSCRIBING" || appState.currentAsrSessionId || appState.liveTranscriptSegments.length) {
    return "TRANSCRIBING";
  }
  return STATUS_TO_STEP[appState.taskStatus] || "INPUT";
}

function workflowAction({ key, label, tone = "secondary", disabled = false }) {
  return `<button type="button" class="${tone === "primary" ? "primary-action" : "secondary-action"}" data-workflow-action="${escapeHtml(key)}" ${disabled ? "disabled" : ""}>${escapeHtml(label)}</button>`;
}

function nextActionState() {
  const risk = riskSummary();
  const rolePending = roleReviewRequired();

  if (appState.busy) {
    return {
      tone: "active",
      title: STATUS_LABELS[appState.taskStatus] || "处理中",
      detail: appState.asrChunkStatus || "系统正在处理当前任务，请等待页面状态更新。",
      actions: [],
    };
  }

  if (appState.lastActionError) {
    return {
      tone: "danger",
      title: "请处理当前提示",
      detail: appState.lastActionError,
      actions: [
        workflowAction({ key: "upload-audio", label: "音频生成", tone: "primary" }),
        workflowAction({ key: "import-text", label: "文本生成" }),
      ],
    };
  }

  if (appState.taskStatus === "FAILED" || appState.asrLastError) {
    return {
      tone: "danger",
      title: "流程中断",
      detail: appState.asrLastError || appState.asrChunkLastError || "当前流程失败，请重新上传音频或改用文本导入继续。",
      actions: [
        workflowAction({ key: "upload-audio", label: "重新上传音频", tone: "primary" }),
        workflowAction({ key: "import-text", label: "改用文本导入" }),
      ],
    };
  }

  if (!hasActiveSession()) {
    return {
      tone: "neutral",
      title: "开始一次病历生成",
      detail: "优先上传中文问诊音频；演示兜底可选择 Mock ASR，文本导入可直接验证病历生成。",
      actions: [
        workflowAction({ key: "upload-audio", label: "音频生成", tone: "primary" }),
        workflowAction({ key: "import-text", label: "文本生成" }),
      ],
    };
  }

  if (appState.taskStatus === "TRANSCRIBING" && !appState.currentAsrResult) {
    const chunkText = appState.asrChunkTotal
      ? `当前切片 ${appState.asrChunkCurrent || 0}/${appState.asrChunkTotal}`
      : "短音频直接转写";
    return {
      tone: "active",
      title: "实时转写中",
      detail: `${chunkText}，请等待 SSE 分段文本追加到中间栏。`,
      actions: [],
    };
  }

  if (appState.currentAsrResult && (rolePending || appState.roleReviewDirty)) {
    return {
      tone: "warning",
      title: rolePending ? "请完成医生/患者角色校正" : "请保存角色校正",
      detail: "逐段确认角色和文本，保存后再使用校正文本生成病历。",
      actions: [
        workflowAction({
          key: "save-role-review",
          label: appState.roleReviewSaving ? "保存中" : "保存角色校正",
          tone: "primary",
          disabled: appState.roleReviewSaving,
        }),
      ],
    };
  }

  if (appState.currentAsrResult && !appState.currentTaskId) {
    return {
      tone: "ready",
      title: "转写已完成",
      detail: "角色已确认，可以用当前对话生成病历草稿。",
      actions: [
        workflowAction({ key: "generate-record", label: "用校正文本生成病历", tone: "primary" }),
      ],
    };
  }

  if (appState.currentTaskId && !appState.currentRecordFields) {
    return {
      tone: "active",
      title: "病历草稿生成中",
      detail: "字段抽取、草稿生成和安全校验会依次完成。",
      actions: [],
    };
  }

  if (appState.taskStatus === "EXPORTED" || appState.taskStatus === "exported") {
    return {
      tone: "ready",
      title: "导出已完成",
      detail: "Markdown / Word 文件已生成，可重新导出或开始下一次输入。",
      actions: [
        workflowAction({ key: "export-record", label: "重新导出" }),
        workflowAction({ key: "upload-audio", label: "上传新音频", tone: "primary" }),
        workflowAction({ key: "import-text", label: "粘贴新文本" }),
      ],
    };
  }

  if (isApprovedForExport()) {
    return {
      tone: "ready",
      title: "字段已确认，可以导出",
      detail: "导出前请确认候选诊断和安全校验提示已由医生审核。",
      actions: [
        workflowAction({ key: "export-record", label: "确认导出", tone: "primary" }),
      ],
    };
  }

  if (appState.currentRecordFields) {
    const missingText = risk.missing.length ? `缺失项：${risk.missing.join("、")}。` : "字段已生成。";
    return {
      tone: risk.hasError ? "danger" : risk.hasRisk ? "warning" : "ready",
      title: "请审核病历字段",
      detail: `${missingText} 保存草稿后确认字段，确认后才能导出。`,
      actions: [
        workflowAction({ key: "save-draft", label: "保存草稿" }),
        workflowAction({ key: "confirm-fields", label: "确认字段", tone: "primary" }),
      ],
    };
  }

  return {
    tone: "neutral",
    title: "等待下一步",
    detail: "可继续上传音频或粘贴文本开始新的病历生成流程。",
    actions: [
      workflowAction({ key: "upload-audio", label: "音频生成", tone: "primary" }),
      workflowAction({ key: "import-text", label: "文本生成" }),
    ],
  };
}

function renderNextActionPanel() {
  const state = nextActionState();
  $("nextActionPanel").className = `next-action-panel ${state.tone}`.trim();
  $("nextActionPanel").innerHTML = `
    <div>
      <span class="meta-label">下一步</span>
      <strong>${escapeHtml(state.title)}</strong>
      <p>${escapeHtml(state.detail)}</p>
    </div>
    <div class="next-action-buttons">
      ${state.actions.join("")}
    </div>
  `;
}

function openDrawer(panelId, title) {
  closeInputMethodMenu();
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

function openDetailDrawer(title, html) {
  const content = $("detailDrawerContent");
  if (!content) return;
  content.innerHTML = html;
  openDrawer("detailPanel", title);
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
  $("topAsrEngineSelect").value = appState.selectedEngine;
  $("audioEngineSelect").value = appState.selectedEngine;
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
  const activeKey = workflowStepKey();
  const activeIndex = WORKFLOW_STEPS.findIndex((step) => step.key === activeKey);
  $("workflowSteps").innerHTML = WORKFLOW_STEPS.map((step, index) => {
    const state = index < activeIndex ? "done" : index === activeIndex ? "active" : "";
    const label = String(step.label || "").replace(/^\d+\./, "");
    return `
      <li class="workflow-step ${state}">
        <span class="workflow-index">${index + 1}</span>
        <span class="workflow-label">${escapeHtml(label)}</span>
      </li>
    `;
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

function renderFieldDetailContent(key) {
  const fields = appState.currentRecordFields;
  if (!fields) return `<div class="empty-state">暂无病历字段。</div>`;
  const title = FIELD_DEFS.find(([itemKey]) => itemKey === key)?.[1] || "病历字段";
  const field = fields[key] || null;
  const status = fieldStatus(field, key);
  const confidence = key === "treatment_plan" ? null : field?.confidence;
  return `
    ${detailSection(title, `
      <div class="detail-kv">
        <span>状态</span>
        <strong>${escapeHtml(status.label)}</strong>
      </div>
      <div class="detail-kv">
        <span>置信度</span>
        <strong>${escapeHtml(confidence == null ? "需医生复核" : `${Math.round(confidence * 100)}%`)}</strong>
      </div>
      <div class="detail-text">${escapeHtml(fieldValue(fields, key))}</div>
    `)}
    ${detailSection("证据片段", `<div class="detail-text">${escapeHtml(fieldEvidence(field, key))}</div>`)}
  `;
}

function renderDiagnosisDetailContent(index) {
  const diagnosis = appState.currentRecordFields?.candidate_diagnoses?.[index];
  if (!diagnosis) return `<div class="empty-state">暂无候选诊断详情。</div>`;
  return `
    ${detailSection(diagnosis.name || "候选诊断", `
      <div class="detail-kv">
        <span>状态</span>
        <strong>${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong>
      </div>
      <div class="detail-kv">
        <span>置信度</span>
        <strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong>
      </div>
      <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
    `)}
    ${detailSection("诊断证据", `<div class="detail-text">${escapeHtml((diagnosis.evidence || []).map((item) => item.text).filter(Boolean).join("\n") || "暂无候选诊断证据。")}</div>`)}
  `;
}

function renderAllFieldsDetailContent() {
  const fields = appState.currentRecordFields;
  if (!fields) return `<div class="empty-state">暂无病历字段。</div>`;
  const fieldSections = FIELD_DEFS.map(([key, title]) => {
    const field = fields[key] || null;
    const status = fieldStatus(field, key);
    const confidence = key === "treatment_plan" ? null : field?.confidence;
    return detailSection(title, `
      <div class="detail-kv"><span>状态</span><strong>${escapeHtml(status.label)}</strong></div>
      <div class="detail-kv"><span>置信度</span><strong>${escapeHtml(confidence == null ? "需医生复核" : `${Math.round(confidence * 100)}%`)}</strong></div>
      <div class="detail-text">${escapeHtml(fieldValue(fields, key))}</div>
      <div class="detail-text"><strong>证据：</strong><br>${escapeHtml(fieldEvidence(field, key))}</div>
    `);
  }).join("");
  const diagnoses = fields.candidate_diagnoses || [];
  const diagnosisSection = diagnoses.length
    ? detailSection("候选诊断", diagnoses.map((diagnosis, index) => `
      <div class="diagnosis-detail">
        <span>候选 ${index + 1}</span>
        <strong>${escapeHtml(diagnosis.name || "未命名诊断")} · ${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong>
      </div>
      <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
    `).join(""))
    : "";
  return fieldSections + diagnosisSection;
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
  const displayFieldDefs = appState.viewMode === "doctor"
    ? FIELD_DEFS.filter(([key]) => SUMMARY_FIELD_KEYS.includes(key))
    : FIELD_DEFS;
  const cards = displayFieldDefs.map(([key, title]) => {
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
        <div class="field-value">${escapeHtml(compactText(fieldValue(fields, key), 86))}</div>
        <div class="field-meta">
          <span class="confidence">${confidence == null ? "需医生复核" : `置信度 ${Math.round(confidence * 100)}%`}</span>
          <button type="button" data-evidence-toggle>证据</button>
          ${detailButton(`field:${key}`, "详情")}
        </div>
        <div class="field-evidence">${escapeHtml(fieldEvidence(field, key))}</div>
      </article>
    `;
  }).join("");

  const diagnoses = appState.viewMode === "doctor" ? "" : (fields.candidate_diagnoses || []).map((diagnosis, index) => `
    <article class="field-card candidate" data-field="diagnosis-${index}">
      <div class="field-head">
        <span class="field-title">候选诊断</span>
        <span class="status-badge candidate">${diagnosis.confirmed_by_doctor ? "已确认" : "候选待确认"}</span>
      </div>
      <div class="field-value">${escapeHtml(diagnosis.name || "未命名诊断")}</div>
      <div class="field-meta">
        <span class="confidence">${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</span>
        <button type="button" data-evidence-toggle>证据</button>
        ${detailButton(`diagnosis:${index}`, "详情")}
      </div>
      <div class="field-evidence">${escapeHtml((diagnosis.evidence || []).map((item) => item.text).join("\n") || "暂无候选诊断证据。")}</div>
    </article>
  `).join("");
  const hiddenFieldCount = Math.max(0, FIELD_DEFS.length - displayFieldDefs.length);
  const summaryFooter = hiddenFieldCount || appState.viewMode === "doctor"
    ? `<button type="button" class="inline-more-button" data-open-detail="fields:all">查看全部字段、证据和候选诊断</button>`
    : "";

  const allMissingCount = missingItems().length;
  $("fieldCountBadge").textContent = allMissingCount ? `${allMissingCount}项待补充` : "待医生确认";
  $("fieldCountBadge").className = `status-badge ${allMissingCount ? "missing" : "confirmed"}`;
  $("recordFields").innerHTML = cards + diagnoses + summaryFooter;
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
  const chunkText = appState.asrChunkTotal
    ? `${appState.asrChunkCurrent || 0}/${appState.asrChunkTotal}`
    : "未启用";
  const statusText = appState.asrLastError
    ? "转写异常"
    : appState.asrChunkLastError
      ? "切片转写失败"
    : asr
      ? "转写完成"
      : appState.asrChunkStatus
        ? appState.asrChunkStatus
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
  const detailAction = rows.length ? detailButton("transcript:all", "查看全部转写") : "";
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
        <div><span>切片</span><strong>${escapeHtml(chunkText)}</strong></div>
        <div><span>分段</span><strong>${current || 0}/${total || 0}</strong></div>
        <div><span>文件</span><strong>${escapeHtml(appState.uploadedFilename || "未上传")}</strong></div>
        <div><span>校正</span><strong>${escapeHtml(reviewText)}</strong></div>
      </div>
      ${appState.asrLastError ? `<div class="safety-strip danger">${escapeHtml(appState.asrLastError)}</div>` : ""}
      ${appState.asrChunkLastError ? `<div class="safety-strip danger"><strong>失败切片</strong><br>${escapeHtml(appState.asrChunkLastError)}</div>` : ""}
      ${appState.asrRetryHint ? `<div class="safety-strip warning"><strong>重试提示</strong><br>${escapeHtml(appState.asrRetryHint)}</div>` : ""}
      ${actionButton || detailAction ? `<div class="quick-action-row">${actionButton}${detailAction}</div>` : ""}
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
  const visibleLimit = appState.viewMode === "doctor" ? 4 : rows.length;
  const visibleRows = rows.length > visibleLimit
    ? (isStreaming ? rows.slice(-visibleLimit) : rows.slice(0, visibleLimit))
    : rows;
  const hiddenCount = Math.max(0, rows.length - visibleRows.length);

  $("transcriptList").innerHTML = `
    ${renderTranscriptStatusPanel({ rows, asr, isStreaming, reviewable, unreviewedCount })}
    ${warningBlocks.map((item) => `<div class="conversation-warning">${escapeHtml(item)}</div>`).join("")}
    ${streamBlock}
    ${roleReviewBlock}
    ${asrTextBlock}
    ${conversationBlock}
    ${visibleRows.map((item, index) => `
      <div class="chat-row">
        <div class="chat-time">${escapeHtml(item.time)}</div>
        <div class="chat-card ${index === 1 ? "highlight" : ""} ${item.needsReview ? "needs-review" : ""} ${item.reviewedByDoctor ? "reviewed" : ""}" data-segment-index="${item.index}">
          ${item.editable ? `
            <div class="chat-tools">
              <select data-role-select>
                ${renderRoleOptions(item.label)}
              </select>
              <span class="status-badge ${item.needsReview ? "candidate" : item.reviewedByDoctor ? "confirmed" : "neutral"}">
                ${item.needsReview ? "待确认" : item.reviewedByDoctor ? "已校正" : "未保存"}
              </span>
              <span class="confidence">${item.confidence == null ? "置信度待评估" : `置信度 ${Math.round(item.confidence * 100)}%`}</span>
            </div>
            <textarea data-segment-text>${escapeHtml(item.text)}</textarea>
          ` : `
            <div class="chat-line">
              <span class="speaker-tag ${escapeHtml(item.speaker)}">${escapeHtml(item.label)}</span>
              <p>${escapeHtml(compactText(item.text, 92))}</p>
            </div>
          `}
        </div>
      </div>
    `).join("")}
    ${hiddenCount ? `<button type="button" class="inline-more-button" data-open-detail="transcript:all">还有 ${hiddenCount} 条转写，查看全部</button>` : ""}
  `;
}

function renderTranscriptDetailContent() {
  const rows = transcriptRows();
  if (!rows.length) return `<div class="empty-state">暂无对话转写。</div>`;
  return `
    ${detailSection("转写状态", `
      <div class="detail-kv"><span>引擎</span><strong>${escapeHtml(appState.currentAsrResult?.engine || appState.selectedEngine || "ASR")}</strong></div>
      <div class="detail-kv"><span>分段</span><strong>${rows.length} 条</strong></div>
      <div class="detail-kv"><span>切片</span><strong>${escapeHtml(appState.asrChunkTotal ? `${appState.asrChunkCurrent || 0}/${appState.asrChunkTotal}` : "未启用")}</strong></div>
    `)}
    ${detailSection("完整转写", `
      <div class="detail-transcript">
        ${rows.map((item) => `
          <div class="detail-transcript-row">
            <span>${escapeHtml(item.time)}</span>
            <strong>${escapeHtml(item.label)}</strong>
            <p>${escapeHtml(item.text)}</p>
          </div>
        `).join("")}
      </div>
    `)}
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

function assistCard({ title, badgeClass = "neutral", badgeText = "", body = "", detailTarget = "" }) {
  return `
    <section class="doctor-assist-card">
      <div class="doctor-assist-card-head">
        <h3>${escapeHtml(title)}</h3>
        <div class="doctor-assist-card-actions">
          ${badgeText ? `<span class="status-badge ${badgeClass}">${escapeHtml(badgeText)}</span>` : ""}
          ${detailTarget ? detailButton(detailTarget, "详情") : ""}
        </div>
      </div>
      <div class="doctor-assist-card-body">${body}</div>
    </section>
  `;
}

function renderCandidateDiagnosisCard(diagnoses) {
  if (!diagnoses.length) {
    return assistCard({
      title: "候选诊断",
      badgeClass: "confirmed",
      badgeText: "暂无",
      body: `<div class="empty-state">暂无候选诊断。生成病历后会在这里显示待医生确认的候选结果。</div>`,
    });
  }

  return assistCard({
    title: "候选诊断",
    badgeClass: "candidate",
    badgeText: "待医生确认",
    detailTarget: "assist:candidates",
    body: `
      <ol class="assist-number-list">
        ${listPreview(diagnoses, 1).visible.map((diagnosis, index) => `
          <li>
            <span>${index + 1}</span>
            <div>
              <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong>
              <em>${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</em>
            </div>
          </li>
        `).join("")}
      </ol>
      ${diagnoses.length > 1 ? `<div class="summary-note">另有 ${diagnoses.length - 1} 条候选诊断，点击详情查看。</div>` : ""}
    `,
  });
}

function uniqueDiagnosisItems(diagnoses, key) {
  const values = [];
  diagnoses.forEach((diagnosis) => {
    diagnosisList(diagnosis?.[key]).forEach((item) => {
      if (!values.includes(item)) values.push(item);
    });
  });
  return values;
}

function renderTreatmentRecommendationCard(fields, diagnoses) {
  const treatment = fields?.treatment_plan;
  const treatmentText = treatment?.value || treatment?.hint || "暂无明确处理建议，需医生结合问诊、查体和检查结果补充。";
  const suggestedChecks = uniqueDiagnosisItems(diagnoses, "suggested_checks");
  const medicationNotes = uniqueDiagnosisItems(diagnoses, "medication_notes");

  return assistCard({
    title: "治疗方案推荐",
    badgeClass: fields ? "candidate" : "neutral",
    badgeText: fields ? "需医生确认" : "待生成",
    detailTarget: "assist:treatment",
    body: `
      <div class="assist-plan-block">
        <span>处理建议</span>
        <strong>${escapeHtml(compactText(treatmentText, 88))}</strong>
      </div>
      <div class="assist-mini-grid">
        <div>
          <span>建议检查</span>
          <strong>${escapeHtml(compactText(suggestedChecks.slice(0, 1).join("、") || "暂无结构化建议检查", 40))}</strong>
        </div>
        <div>
          <span>用药提示</span>
          <strong>${escapeHtml(compactText(medicationNotes.slice(0, 1).join("、") || "不自动处方，需医生确认", 40))}</strong>
        </div>
      </div>
    `,
  });
}

function renderEvidenceCard(evidence, diagnoses) {
  const diagnosisReasons = diagnoses
    .map((diagnosis) => diagnosis.reason ? `${diagnosis.name || "候选诊断"}：${diagnosis.reason}` : "")
    .filter(Boolean);
  const items = [...diagnosisReasons, ...evidence].slice(0, 6);

  return assistCard({
    title: "判断证据",
    badgeClass: items.length ? "info" : "neutral",
    badgeText: items.length ? "可追溯" : "暂无",
    detailTarget: "assist:evidence",
    body: items.length
      ? listPreview(items, 1).visible.map((item) => `<div class="assist-evidence-quote">${escapeHtml(compactText(item, 72))}</div>`).join("")
        + (items.length > 1 ? `<div class="summary-note">另有 ${items.length - 1} 条证据，点击详情查看。</div>` : "")
      : `<div class="empty-state">暂无字段证据。完成转写、角色校正和病历生成后会显示来源片段。</div>`,
  });
}

function renderSafetyResultCard({ safety, missing, warnings, errors }) {
  const rows = [
    {
      tone: missing.length ? "danger" : "success",
      text: missing.length ? `存在 ${missing.length} 项未补充字段：${missing.join("、")}` : "关键字段完整性校验通过",
    },
    {
      tone: safety?.passed && !safety?.blocked ? "success" : safety ? "danger" : "warning",
      text: safety
        ? `安全校验：${safety.passed ? "通过" : "未通过"}${safety.blocked ? "，暂不可导出" : ""}`
        : "等待生成病历后执行安全校验",
    },
    ...warnings.map((item) => ({ tone: "warning", text: item })),
    ...errors.map((item) => ({ tone: "danger", text: item })),
  ];

  return assistCard({
    title: "安全校验结果",
    badgeClass: safety?.passed && !safety?.blocked && !missing.length && !errors.length ? "confirmed" : "missing",
    badgeText: safety?.passed && !safety?.blocked && !missing.length && !errors.length ? "通过" : "需复核",
    detailTarget: "assist:safety",
    body: `<div class="assist-check-list">
      ${listPreview(rows, 2).visible.map((row) => `
        <div class="assist-check-row ${row.tone}">
          <span></span>
          <strong>${escapeHtml(compactText(row.text, 72))}</strong>
        </div>
      `).join("")}
      ${rows.length > 2 ? `<div class="summary-note">另有 ${rows.length - 2} 条校验结果，点击详情查看。</div>` : ""}
    </div>`,
  });
}

function renderAssistDetailContent(section) {
  const fields = appState.currentRecordFields;
  const diagnoses = fields?.candidate_diagnoses || [];
  const evidence = allEvidence();
  const missing = missingItems();
  const risk = riskSummary();
  const safety = appState.currentSafetyCheck;
  const warnings = [...risk.warnings];
  if (appState.currentAsrResult?.role_strategy === "single_segment_needs_review") {
    warnings.unshift("医生/患者角色需人工校正");
  }
  const errors = risk.errors;

  if (section === "candidates") {
    return diagnoses.length
      ? diagnoses.map((diagnosis, index) => `
          ${detailSection(`候选诊断 ${index + 1}：${diagnosis.name || "未命名诊断"}`, `
            <div class="detail-kv"><span>状态</span><strong>${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong></div>
            <div class="detail-kv"><span>规则置信度</span><strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong></div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
          `)}
        `).join("")
      : `<div class="empty-state">暂无候选诊断。</div>`;
  }

  if (section === "treatment") {
    const treatment = fields?.treatment_plan;
    const treatmentText = treatment?.value || treatment?.hint || appState.currentDraft || "暂无明确处理建议，需医生补充。";
    const suggestedChecks = uniqueDiagnosisItems(diagnoses, "suggested_checks");
    const medicationNotes = uniqueDiagnosisItems(diagnoses, "medication_notes");
    const riskWarnings = uniqueDiagnosisItems(diagnoses, "risk_warnings");
    return `
      ${detailSection("处理建议", `<div class="detail-text">${escapeHtml(treatmentText)}</div>`)}
      ${detailSection("建议检查", `<div class="detail-text">${escapeHtml(suggestedChecks.join("\n") || "暂无结构化建议检查。")}</div>`)}
      ${detailSection("用药提示", `<div class="detail-text">${escapeHtml(medicationNotes.join("\n") || "不自动处方，需医生确认。")}</div>`)}
      ${detailSection("风险提醒", `<div class="detail-text">${escapeHtml(riskWarnings.join("\n") || "暂无结构化风险提醒。")}</div>`)}
    `;
  }

  if (section === "evidence") {
    const diagnosisReasons = diagnoses
      .map((diagnosis) => diagnosis.reason ? `${diagnosis.name || "候选诊断"}：${diagnosis.reason}` : "")
      .filter(Boolean);
    const items = [...diagnosisReasons, ...evidence];
    return items.length
      ? detailSection("全部判断证据", `
        <div class="detail-evidence-list">
          ${items.map((item) => `<div class="assist-evidence-quote">${escapeHtml(item)}</div>`).join("")}
        </div>
      `)
      : `<div class="empty-state">暂无判断证据。</div>`;
  }

  const rows = [
    missing.length ? `存在 ${missing.length} 项未补充字段：${missing.join("、")}` : "关键字段完整性校验通过",
    safety ? `安全校验：${safety.passed ? "通过" : "未通过"}${safety.blocked ? "，暂不可导出" : ""}` : "等待生成病历后执行安全校验",
    ...warnings,
    ...errors,
  ];
  return detailSection("安全校验结果", `
    <div class="detail-evidence-list">
      ${rows.map((item) => `<div class="assist-evidence-quote">${escapeHtml(item)}</div>`).join("")}
    </div>
  `);
}

function renderDoctorAssistOverview({ fields, diagnoses, evidence, missing, warnings, errors, safety }) {
  return `
    <div class="doctor-assist-overview">
      ${renderCandidateDiagnosisCard(diagnoses)}
      ${renderTreatmentRecommendationCard(fields, diagnoses)}
      ${renderEvidenceCard(evidence, diagnoses)}
      ${renderSafetyResultCard({ safety, missing, warnings, errors })}
    </div>
  `;
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

  if (appState.viewMode === "doctor") {
    $("assistPanels").innerHTML = renderDoctorAssistOverview({
      fields,
      diagnoses,
      evidence,
      missing,
      warnings,
      errors,
      safety,
    });
    return;
  }

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
  $("currentTaskLabel").textContent = "操作区";
  $("currentTaskHint").textContent = appState.currentTaskId
    ? `${STATUS_LABELS[appState.taskStatus] || appState.taskStatus || "任务已创建"} · ${appState.currentAudioId ? "音频生成" : "文本生成"}`
    : "等待输入";
  $("regenerateButton").disabled = appState.busy || !(appState.currentAsrResult || appState.currentInputText);
  $("saveDraftButton").disabled = appState.busy || !appState.currentTaskId || !appState.currentRecordFields;
  $("confirmFieldsButton").disabled = appState.busy || !appState.currentTaskId || !appState.currentRecordFields;
  $("exportButton").disabled = appState.busy || !appState.currentTaskId || !isApprovedForExport();
}

function openWorkbenchDetail(target = "") {
  const [type, value] = String(target).split(":");
  if (type === "field") {
    const title = FIELD_DEFS.find(([key]) => key === value)?.[1] || "病历字段详情";
    openDetailDrawer(title, renderFieldDetailContent(value));
    return;
  }
  if (type === "fields") {
    openDetailDrawer("全部病历字段与证据", renderAllFieldsDetailContent());
    return;
  }
  if (type === "diagnosis") {
    openDetailDrawer("候选诊断详情", renderDiagnosisDetailContent(Number(value)));
    return;
  }
  if (type === "transcript") {
    openDetailDrawer("完整对话转写", renderTranscriptDetailContent());
    return;
  }
  if (type === "assist") {
    const titleMap = {
      candidates: "候选诊断详情",
      treatment: "治疗方案推荐详情",
      evidence: "判断证据详情",
      safety: "安全校验结果详情",
    };
    openDetailDrawer(titleMap[value] || "AI 辅助详情", renderAssistDetailContent(value));
  }
}

function isApprovedForExport() {
  return appState.taskStatus === "approved" || appState.currentTask?.current_stage === "approved";
}

function renderAll() {
  renderMode();
  renderInputMethodMenu();
  renderPatientBar();
  renderRunContext();
  renderStartGuide();
  renderStepPrompt();
  renderWorkflow();
  renderNextActionPanel();
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
  appState.currentTaskId = null;
  appState.currentEvaluation = null;
  appState.currentTask = null;
  appState.currentSteps = [];
  appState.currentRecordFields = null;
  appState.currentDraft = "";
  appState.currentSafetyCheck = null;
  appState.currentAgentTrace = null;
  appState.currentInputText = "";
  appState.taskStatus = "CREATED";
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
    appState.asrChunkCurrent = 0;
    appState.asrChunkTotal = 0;
    appState.asrChunkStatus = "";
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
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
    appState.asrChunkCurrent = 0;
    appState.asrChunkTotal = 0;
    appState.asrChunkStatus = "";
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
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

  source.addEventListener("chunk_plan", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrChunkCurrent = 0;
    appState.asrChunkTotal = Number(data.total_chunks || data.chunk_count || 0);
    appState.asrChunkStatus = appState.asrChunkTotal
      ? `准备切片转写（共 ${appState.asrChunkTotal} 片）`
      : "准备切片转写";
    appState.asrStreamProgress = Number(data.progress || 0);
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
    renderAll();
  });

  source.addEventListener("chunk_started", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrChunkCurrent = Number(data.chunk_index || appState.asrChunkCurrent || 0);
    appState.asrChunkTotal = Number(data.total_chunks || appState.asrChunkTotal || 0);
    appState.asrChunkStatus = `第 ${appState.asrChunkCurrent}/${appState.asrChunkTotal || "?"} 片转写中`;
    appState.asrStreamProgress = Number(data.progress || appState.asrStreamProgress || 0);
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
    setBusy(true, appState.asrChunkStatus);
    renderAll();
  });

  source.addEventListener("chunk_completed", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrChunkCurrent = Number(data.chunk_index || appState.asrChunkCurrent || 0);
    appState.asrChunkTotal = Number(data.total_chunks || appState.asrChunkTotal || 0);
    appState.asrChunkStatus = `第 ${appState.asrChunkCurrent}/${appState.asrChunkTotal || "?"} 片已完成`;
    appState.asrStreamProgress = Number(data.progress || appState.asrStreamProgress || 0);
    renderAll();
  });

  source.addEventListener("chunk_failed", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "FAILED";
    appState.asrChunkCurrent = Number(data.chunk_index || appState.asrChunkCurrent || 0);
    appState.asrChunkTotal = Number(data.total_chunks || appState.asrChunkTotal || 0);
    appState.asrChunkStatus = `第 ${appState.asrChunkCurrent}/${appState.asrChunkTotal || "?"} 片失败`;
    appState.asrChunkLastError = data.error || "切片转写失败";
    appState.asrRetryHint = data.retry_hint || "请重新上传音频重试，或切换到稳定 fallback 模型。";
    appState.asrLastError = appState.asrChunkLastError;
    appState.asrStreamProgress = Number(data.progress || appState.asrStreamProgress || 0);
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
    appState.asrChunkStatus = appState.asrChunkTotal ? "切片转写完成" : "";
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
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
    appState.asrRetryHint = data.retry_hint || appState.asrRetryHint;
    closeAsrStream();
    setBusy(false);
    renderAll();
    const error = new Error(data.error || "ASR 实时转写失败");
    reportActionError(error);
    reject?.(error);
  });

  source.onerror = () => {
    if (!terminalReceived) {
      appState.taskStatus = "FAILED";
      const error = new Error("ASR SSE 连接异常，请检查服务日志");
      appState.asrLastError = error.message;
      reportActionError(error);
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
  appState.asrChunkCurrent = 0;
  appState.asrChunkTotal = 0;
  appState.asrChunkStatus = "";
  appState.asrChunkLastError = "";
  appState.asrRetryHint = "";
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
    reportActionError(error);
  }
}

async function submitAudio() {
  try {
    const file = $("audioFileInput").files[0];
    if (!file) throw new Error("请选择音频文件");
    const engine = $("audioEngineSelect").value;
    closeDrawer();
    resetTaskState();
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
    reportActionError(error);
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
    reportActionError(error);
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
    reportActionError(error);
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
    reportActionError(error);
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
    reportActionError(error);
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
    reportActionError(error);
  }
}

async function handleWorkflowAction(action) {
  if (action === "upload-audio") {
    openAudioGenerate();
    return;
  }
  if (action === "import-text") {
    openTextImport();
    return;
  }
  if (action === "save-role-review") {
    await saveRoleReview();
    return;
  }
  if (action === "generate-record") {
    await regenerateRecord();
    return;
  }
  if (action === "save-draft") {
    await saveDraftReview();
    return;
  }
  if (action === "confirm-fields") {
    await confirmFields();
    return;
  }
  if (action === "export-record") {
    await exportRecord();
  }
}

function handleInputMethod(method) {
  if (method === "record") {
    openReservedRecording();
    return;
  }
  if (method === "audio") {
    openAudioGenerate();
    return;
  }
  if (method === "text") {
    openTextImport();
  }
}

function openTextImport() {
  clearActionError();
  openDrawer("textImportPanel", "文本导入生成病历");
}

function openAudioTranscribe() {
  clearActionError();
  appState.audioMode = "transcribe";
  $("audioEngineSelect").value = appState.selectedEngine;
  $("audioPanelHint").textContent = "上传 MP3/WAV 预录音频，系统创建 ASR 会话并通过 SSE 实时显示分段转写。";
  $("submitAudioButton").textContent = "上传并实时转写";
  openDrawer("audioPanel", "MP3/WAV 实时转写");
}

function openAudioGenerate() {
  clearActionError();
  appState.audioMode = "generate";
  $("audioEngineSelect").value = appState.selectedEngine;
  $("audioPanelHint").textContent = "上传 MP3/WAV 预录音频，先完成 SSE 实时转写，再进入病历生成流程。";
  $("submitAudioButton").textContent = "实时转写并生成病历";
  openDrawer("audioPanel", "MP3/WAV 生成病历");
}

function openReservedRecording() {
  closeInputMethodMenu();
  setActionError("浏览器麦克风录音暂未接入。本轮请先使用“音频生成”上传 MP3/WAV，后续迭代再接入录音生成。");
  showToast("录音生成入口已预留，当前请使用音频生成");
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
    reportActionError(error);
  }
}

function bindEvents() {
  $("doctorModeButton").addEventListener("click", () => setViewMode("doctor"));
  $("debugModeButton").addEventListener("click", () => setViewMode("debug"));
  $("demoModeButton").addEventListener("click", () => setScreenshotMode(false));
  $("screenshotModeButton").addEventListener("click", () => setScreenshotMode(true));
  $("inputMethodButton").addEventListener("click", (event) => {
    event.stopPropagation();
    toggleInputMethodMenu();
  });
  $("inputMethodMenu").addEventListener("click", (event) => {
    const button = event.target.closest("[data-input-method]");
    if (!button) return;
    handleInputMethod(button.dataset.inputMethod);
  });
  document.addEventListener("click", (event) => {
    if (!appState.inputMenuOpen || event.target.closest(".input-method-menu")) return;
    closeInputMethodMenu();
  });
  $("openAudioTranscribeButton").addEventListener("click", openAudioTranscribe);
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
  $("nextActionPanel").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-workflow-action]");
    if (!button) return;
    try {
      await handleWorkflowAction(button.dataset.workflowAction);
    } catch (error) {
      setBusy(false);
      reportActionError(error);
    }
  });
  $("topAsrEngineSelect").addEventListener("change", () => {
    appState.selectedEngine = $("topAsrEngineSelect").value;
    $("audioEngineSelect").value = appState.selectedEngine;
    renderPatientBar();
  });
  $("audioEngineSelect").addEventListener("change", () => {
    appState.selectedEngine = $("audioEngineSelect").value;
    $("topAsrEngineSelect").value = appState.selectedEngine;
    renderPatientBar();
  });
  $("recordFields").addEventListener("click", (event) => {
    const detail = event.target.closest("[data-open-detail]");
    if (detail) {
      openWorkbenchDetail(detail.dataset.openDetail);
      return;
    }
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
    const detail = event.target.closest("[data-open-detail]");
    if (detail) {
      openWorkbenchDetail(detail.dataset.openDetail);
      return;
    }
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
      reportActionError(error);
    }
  });
  $("assistPanels").addEventListener("click", (event) => {
    const detail = event.target.closest("[data-open-detail]");
    if (detail) {
      openWorkbenchDetail(detail.dataset.openDetail);
      return;
    }
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
