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
  displayScale: "standard",
  screenshotMode: false,
  audioMode: "transcribe",
  pendingGenerateAfterRoleReview: false,
  uploadedFilename: "",
  taskStatus: "CREATED",
  busy: false,
  eventSource: null,
  asrEventSource: null,
  asrStreamProgress: 0,
  asrProgressEstimated: false,
  asrElapsedSeconds: 0,
  asrFirstSegmentAt: "",
  asrLastSegmentAt: "",
  asrVisibleAudioSeconds: 0,
  asrStreamCurrentSegment: 0,
  asrStreamTotalSegments: 0,
  asrPhase: "idle",
  asrProgressKind: "indeterminate",
  asrProcessedAudioSeconds: 0,
  asrAudioDurationSeconds: 0,
  diarizationStatus: "idle",
  asrLastError: "",
  asrChunkCurrent: 0,
  asrChunkTotal: 0,
  asrChunkStatus: "",
  asrChunkLastError: "",
  asrRetryHint: "",
  roleReviewDirty: false,
  roleReviewSaving: false,
  speakerRoleCorrections: {},
  lastActionError: "",
  inputMenuOpen: false,
  recordPreview: null,
  recordPreviewStatus: "idle",
  recordPreviewUpdatedAt: "",
  recordPreviewError: "",
  recordPreviewTimer: null,
  recordPreviewLastRunAt: 0,
  recordPreviewLastSignature: "",
  recordPreviewInFlight: false,
  recordPreviewRequestId: 0,
  recordPreviewAbortController: null,
  audioObjectUrl: "",
  audioMediaUrl: "",
  audioDurationSeconds: 0,
  audioCurrentTime: 0,
  audioPlaying: false,
  audioMuted: false,
  audioVolume: 1,
  audioPlaybackRate: 1,
  audioSeekDragging: false,
  transcriptPacing: "fast",
  activeTranscriptSegmentId: "",
};

const RECORD_PREVIEW_MIN_CHARS = 10;
const RECORD_PREVIEW_MIN_SEGMENTS = 1;
const RECORD_PREVIEW_MIN_INTERVAL_MS = 2000;
const RECORD_PREVIEW_DEBOUNCE_MS = 450;

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
  "past_history",
  "allergy_history",
  "physical_exam",
  "treatment_plan",
];

const DRAFT_FIELD_DEFS = [
  ["chief_complaint", "主诉"],
  ["present_illness", "现病史"],
  ["past_history", "既往史"],
  ["allergy_history", "过敏史"],
  ["physical_exam", "查体"],
  ["preliminary_diagnosis", "初步诊断"],
  ["treatment_plan", "处理建议"],
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
  ["其他", "其他"],
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
    if (button.id !== "closeDrawerButton" && button.dataset.busyAllowed !== "true") {
      button.disabled = nextBusy;
    }
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
      || appState.recordPreview
      || appState.currentInputText,
  );
}

function isRecordPreviewActive() {
  return Boolean(!appState.currentRecordFields && appState.recordPreview?.fields_preview);
}

function activeRecordFields() {
  return appState.currentRecordFields || appState.recordPreview?.fields_preview || null;
}

function activeDraftText() {
  return appState.currentDraft || appState.recordPreview?.draft_preview || "";
}

function activeSafetyCheck() {
  return appState.currentSafetyCheck || appState.recordPreview?.safety_preview || null;
}

function previewTreatmentText() {
  const plan = appState.recordPreview?.treatment_plan;
  if (!isRecordPreviewActive() || !plan) return "";
  const items = [];
  if (plan.suggested_checks?.length) items.push(`建议检查：${plan.suggested_checks.join("；")}`);
  if (plan.medication_notes?.length) items.push(`用药提示：${plan.medication_notes.join("；")}`);
  if (plan.risk_warnings?.length) items.push(`风险提醒：${plan.risk_warnings.join("；")}`);
  if (plan.follow_up_questions?.length) items.push(`建议补问：${plan.follow_up_questions.join("；")}`);
  return items.join("\n");
}

function previewRecognizedLabels() {
  const updates = appState.recordPreview?.structured_updates || [];
  return updates
    .filter((item) => item.status === "preview" && item.value_preview)
    .map((item) => item.label)
    .slice(0, 4);
}

function previewNoticeText() {
  if (!isRecordPreviewActive()) return "";
  const labels = previewRecognizedLabels();
  const stageLabel = appState.recordPreview?.ready_for_formal_generation
    ? "已可正式生成"
    : appState.recordPreview?.preview_stage === "collecting"
      ? "正在收集信息"
      : "结构化预览更新中";
  const recognized = labels.length ? ` · 已识别：${labels.join("、")}` : "";
  return `实时预览，需医生确认 · ${stageLabel}${recognized}`;
}

function riskSummary() {
  const missing = missingItems();
  const diagnoses = activeRecordFields()?.candidate_diagnoses || [];
  const safety = activeSafetyCheck();
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
  document.body.classList.toggle("standard-mode", appState.displayScale !== "care");
  document.body.classList.toggle("care-mode", appState.displayScale === "care");
  $("doctorModeButton").classList.toggle("active", !isDebug);
  $("debugModeButton").classList.toggle("active", isDebug);
  $("demoModeButton").classList.toggle("active", !appState.screenshotMode);
  $("screenshotModeButton").classList.toggle("active", appState.screenshotMode);
  $("standardModeButton").classList.toggle("active", appState.displayScale !== "care");
  $("careModeButton").classList.toggle("active", appState.displayScale === "care");
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

function setDisplayScale(mode) {
  appState.displayScale = mode === "care" ? "care" : "standard";
  renderAll();
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
    const pendingCount = roleReviewPendingCount();
    const pendingText = pendingCount
      ? `仍有 ${pendingCount} 段角色待确认，请在校正抽屉中选择医生或患者。`
      : "角色已逐段确认，请保存校正结果。";
    const resumeText = appState.pendingGenerateAfterRoleReview
      ? "保存后将自动继续生成病历。"
      : "保存后可继续生成病历。";
    return {
      tone: "warning",
      title: rolePending ? "请完成医生/患者角色校正" : "请保存角色校正",
      detail: `${pendingText}${resumeText}`,
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
    return activeDraftText()
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
    return previewTreatmentText()
      || (activeDraftText() ? "处理建议已生成，需医生确认后写入正式病历。" : "待医生补充处理建议");
  }
  const field = fields?.[key];
  return field?.value || field?.hint || "暂无内容";
}

function fieldEvidence(field, key) {
  if (key === "treatment_plan") return "处理建议来自 AI 病历草稿，需医生结合诊疗规范确认。";
  const spans = field?.source_spans || [];
  return spans.length ? spans.map((span) => span.text).filter(Boolean).join("\n") : "暂无证据片段，需结合原始转写复核。";
}

function draftDiagnoses(fields = {}) {
  return Array.isArray(fields?.candidate_diagnoses) ? fields.candidate_diagnoses : [];
}

function draftFieldStatus(fields, key) {
  if (!fields) return { key: "neutral", label: "待生成" };
  if (key === "preliminary_diagnosis") {
    return draftDiagnoses(fields).length
      ? { key: "candidate", label: "待确认" }
      : { key: "missing", label: "待补充" };
  }
  return fieldStatus(fields?.[key] || null, key);
}

function draftFieldValue(fields, key) {
  if (!fields) return "";
  if (key === "preliminary_diagnosis") {
    return draftDiagnoses(fields)
      .map((diagnosis) => diagnosis.name || "")
      .filter(Boolean)
      .join("；");
  }
  return fieldValue(fields, key);
}

function draftFieldEvidence(fields, key) {
  if (!fields) return "暂无证据片段。";
  if (key === "preliminary_diagnosis") {
    const evidence = draftDiagnoses(fields)
      .flatMap((diagnosis) => diagnosis.evidence || [])
      .map((item) => item.text)
      .filter(Boolean);
    return evidence.length ? evidence.join("\n") : "暂无候选诊断证据，需医生结合原始转写复核。";
  }
  return fieldEvidence(fields?.[key] || null, key);
}

function draftFieldConfidence(fields, key) {
  if (!fields) return "等待生成";
  if (key === "treatment_plan") return "需医生复核";
  if (key === "preliminary_diagnosis") {
    const diagnoses = draftDiagnoses(fields);
    if (!diagnoses.length) return "需医生补充";
    return diagnoses.map((diagnosis) => diagnosisConfidence(diagnosis)).join("；");
  }
  const confidence = fields?.[key]?.confidence;
  return confidence == null ? "需医生复核" : `置信度 ${Math.round(confidence * 100)}%`;
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
  const fields = activeRecordFields();
  if (!fields) return `<div class="empty-state">暂无病历字段。</div>`;
  const title = DRAFT_FIELD_DEFS.find(([itemKey]) => itemKey === key)?.[1]
    || FIELD_DEFS.find(([itemKey]) => itemKey === key)?.[1]
    || "病历字段";
  if (key === "preliminary_diagnosis") {
    const diagnoses = draftDiagnoses(fields);
    return diagnoses.length
      ? diagnoses.map((diagnosis, index) => `
          ${detailSection(`初步诊断 ${index + 1}：${diagnosis.name || "未命名诊断"}`, `
            <div class="detail-kv"><span>状态</span><strong>${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong></div>
            <div class="detail-kv"><span>置信度</span><strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong></div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
          `)}
        `).join("")
      : `<div class="empty-state">暂无初步诊断。生成病历后会显示候选诊断摘要，需医生确认。</div>`;
  }
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
  const diagnosis = activeRecordFields()?.candidate_diagnoses?.[index];
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
  const fields = activeRecordFields();
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
  const fields = activeRecordFields();
  const isPreview = isRecordPreviewActive();
  if (!fields) {
    $("fieldCountBadge").textContent = "待生成";
    $("fieldCountBadge").className = "status-badge neutral";
  }

  let missingCount = 0;
  const displayFieldDefs = appState.viewMode === "doctor" ? DRAFT_FIELD_DEFS : FIELD_DEFS;
  const cards = displayFieldDefs.map(([key, title]) => {
    const status = appState.viewMode === "doctor"
      ? draftFieldStatus(fields, key)
      : fieldStatus(fields?.[key] || null, key);
    if (status.key === "missing") missingCount += 1;
    const value = appState.viewMode === "doctor" ? draftFieldValue(fields, key) : fieldValue(fields, key);
    const evidence = appState.viewMode === "doctor" ? draftFieldEvidence(fields, key) : fieldEvidence(fields?.[key] || null, key);
    const confidence = appState.viewMode === "doctor"
      ? draftFieldConfidence(fields, key)
      : key === "treatment_plan" ? "需医生复核" : fields?.[key]?.confidence == null ? "需医生复核" : `置信度 ${Math.round(fields[key].confidence * 100)}%`;
    const meta = fields ? `
        <div class="field-meta">
          <span class="confidence">${escapeHtml(confidence)}</span>
          <button type="button" data-evidence-toggle>证据</button>
          ${detailButton(`field:${key}`, "详情")}
        </div>
        <div class="field-evidence">${escapeHtml(evidence)}</div>
    ` : "";
    return `
      <article class="field-card ${status.key} ${value ? "has-value" : "is-empty"}" data-field="${key}">
        <div class="field-head">
          <span class="field-title">${escapeHtml(title)}</span>
          <span class="status-badge ${status.key}">${escapeHtml(status.label)}</span>
        </div>
        <div class="field-value">${value ? escapeHtml(value) : `<span class="draft-placeholder" aria-hidden="true">&nbsp;</span>`}</div>
        ${meta}
      </article>
    `;
  }).join("");

  const diagnoses = appState.viewMode === "doctor" ? "" : (fields?.candidate_diagnoses || []).map((diagnosis, index) => `
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
  const summaryFooter = fields && (hiddenFieldCount || appState.viewMode === "doctor")
    ? `<button type="button" class="inline-more-button" data-open-detail="fields:all">查看全部字段、证据和候选诊断</button>`
    : "";

  const draftLegend = appState.viewMode === "doctor" ? `
    <div class="draft-legend" aria-label="病历草稿图示">
      <span><i class="legend-dot confirmed"></i>已确认</span>
      <span><i class="legend-dot missing"></i>待补充</span>
      <span><i class="legend-dot low"></i>低置信度</span>
      <span><i class="legend-icon">✎</i>编辑</span>
      <span><i class="legend-icon">↔</i>证据追溯</span>
    </div>
  ` : "";

  if (fields) {
    const allMissingCount = missingItems().length;
    $("fieldCountBadge").textContent = isPreview
      ? "实时预览"
      : allMissingCount ? `${allMissingCount}项待补充` : "待医生确认";
    $("fieldCountBadge").className = `status-badge ${isPreview ? "info" : allMissingCount ? "missing" : "confirmed"}`;
  }
  const previewNotice = isPreview
    ? `<div class="preview-notice">${escapeHtml(previewNoticeText())}；正式生成病历后会替换为审核版结果。</div>`
    : "";
  $("recordFields").innerHTML = previewNotice + cards + diagnoses + summaryFooter + draftLegend;
}

function classifySpeaker(line, segment = {}) {
  const raw = `${segment.role || ""} ${segment.speaker || ""} ${line}`.toLowerCase();
  if (raw.includes("医生") || raw.includes("doctor")) return "doctor";
  if (raw.includes("患者") || raw.includes("patient")) return "patient";
  if (raw.includes("其他") || raw.includes("other")) return "other";
  const inferred = inferLowConfidenceRole(line);
  if (inferred === "医生") return "doctor";
  if (inferred === "患者") return "patient";
  return "unknown";
}

function roleLabelFromSegment(segment = {}, fallbackLine = "") {
  const speaker = classifySpeaker(fallbackLine, segment);
  if (speaker === "doctor") return "医生";
  if (speaker === "patient") return "患者";
  if (speaker === "other") return "其他";
  return "待确认";
}

function inferLowConfidenceRole(text = "") {
  const value = String(text || "");
  if (!value.trim()) return "待确认";
  const doctorKeywords = ["请问", "哪里", "什么时候", "有没有", "是否", "怎么了", "哪里不舒服", "做什么工作", "多大", "用过什么药", "过敏", "查体", "检查", "处理过"];
  const patientKeywords = ["我", "嗯", "是的", "没有", "发烧", "发热", "咳嗽", "头晕", "胸闷", "疼", "痛", "不舒服", "吃了", "用了", "之前", "小时", "天前"];
  const doctorScore = doctorKeywords.reduce((score, keyword) => score + (value.includes(keyword) ? 1 : 0), 0);
  const patientScore = patientKeywords.reduce((score, keyword) => score + (value.includes(keyword) ? 1 : 0), 0);
  if (doctorScore > patientScore) return "医生";
  if (patientScore > doctorScore) return "患者";
  return "待确认";
}

function segmentWithInferredRole(segment = {}) {
  if (segment.role && segment.role !== "待确认") return segment;
  const inferredRole = inferLowConfidenceRole(segment.text || "");
  return {
    ...segment,
    role: inferredRole,
    role_confidence: segment.role_confidence ?? (inferredRole === "待确认" ? 0.4 : 0.58),
    role_source: segment.role_source || "frontend_text_rule",
    role_note: segment.role_note || (inferredRole === "待确认" ? "角色待确认" : "低置信度初判，需医生校正"),
    needs_review: true,
  };
}

function speakerClassFromRole(role) {
  if (role === "医生") return "doctor";
  if (role === "患者") return "patient";
  if (role === "其他") return "other";
  return "unknown";
}

function formatRelativeTime(seconds = 0) {
  const totalSeconds = Math.max(0, Math.floor(Number(seconds) || 0));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
  }
  return `${String(minutes).padStart(2, "0")}:${String(secs).padStart(2, "0")}`;
}

function segmentTime(segment = {}) {
  const startTime = segment.start_time ?? segment.start ?? segment.offset;
  return startTime != null ? formatRelativeTime(startTime) : "--:--";
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

function compactSegmentText(segment = {}) {
  return String(segment.text || "").trim().replace(/\s+/g, " ");
}

function transcriptSegmentKey(segment = {}, fallbackIndex = 0) {
  if (segment.segment_id) return `id:${segment.segment_id}`;
  const text = compactSegmentText(segment);
  const start = segment.start_time ?? segment.start ?? segment.offset;
  const end = segment.end_time ?? segment.end;
  if (start != null || end != null) {
    return `${Number(start ?? 0).toFixed(2)}:${Number(end ?? 0).toFixed(2)}:${text}`;
  }
  const explicitIndex = segment.index ?? segment.segment_index ?? fallbackIndex;
  return `${explicitIndex}:${text}`;
}

function segmentStartsAt(segment = {}) {
  const start = segment.start_time ?? segment.start ?? segment.offset;
  const value = Number(start);
  return Number.isFinite(value) ? value : null;
}

function segmentEndsAt(segment = {}) {
  const end = segment.end_time ?? segment.end;
  const value = Number(end);
  if (Number.isFinite(value)) return value;
  return segmentStartsAt(segment);
}

function mergeTranscriptSegments(preferredSegments = [], fallbackSegments = []) {
  const byKey = new Map();
  const addSegment = (segment, index) => {
    if (!segment || !compactSegmentText(segment)) return;
    const key = transcriptSegmentKey(segment, index);
    const existing = byKey.get(key);
    const existingRevision = Number(existing?.revision || 0);
    const nextRevision = Number(segment.revision || 0);
    if (!existing || nextRevision >= existingRevision) byKey.set(key, segment);
  };

  fallbackSegments.forEach(addSegment);
  preferredSegments.forEach(addSegment);

  return [...byKey.values()].sort((left, right) => {
    const leftStart = segmentStartsAt(left);
    const rightStart = segmentStartsAt(right);
    if (leftStart == null || rightStart == null) return 0;
    return leftStart - rightStart;
  });
}

function finalTranscriptSegments(finalSegments = [], liveSegments = []) {
  const cleanFinal = finalSegments.filter((segment) => compactSegmentText(segment));
  const cleanLive = liveSegments.filter((segment) => compactSegmentText(segment));
  return cleanFinal.length ? mergeTranscriptSegments(cleanFinal, []) : mergeTranscriptSegments(cleanLive, []);
}

function upsertLiveTranscriptSegment(segment) {
  appState.liveTranscriptSegments = mergeTranscriptSegments([segment], appState.liveTranscriptSegments);
}

function liveConversationTextForPreview() {
  const segments = currentReviewSegments();
  if (segments.length) {
    return segments
      .map((segment) => {
        const displaySegment = segmentWithInferredRole(segment);
        const role = displaySegment.role || "待确认";
        const text = displaySegment.text || "";
        return text ? `[${role}] ${text}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return appState.currentInputText || appState.currentAsrResult?.conversation_text || appState.currentAsrResult?.text || "";
}

function previewSignature(text, segments) {
  return `${segments.length}:${text.length}:${text.slice(-120)}`;
}

async function fetchRecordPreview(text, segments) {
  if (!text.trim() || appState.currentRecordFields) return;
  const signature = previewSignature(text, segments);
  if (signature === appState.recordPreviewLastSignature) return;
  appState.recordPreviewAbortController?.abort();
  const controller = new AbortController();
  const requestId = appState.recordPreviewRequestId + 1;
  appState.recordPreviewRequestId = requestId;
  appState.recordPreviewAbortController = controller;
  appState.recordPreviewInFlight = true;
  appState.recordPreviewStatus = "loading";
  appState.recordPreviewError = "";
  appState.recordPreviewLastRunAt = Date.now();
  renderFields();
  renderAssist();
  try {
    const response = await api("/api/records/preview", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        conversation_text: text,
        source: appState.currentAsrSessionId ? "asr_partial" : "text_preview",
        segments,
      }),
      signal: controller.signal,
    });
    if (requestId !== appState.recordPreviewRequestId) return;
    appState.recordPreview = response;
    appState.recordPreviewStatus = response.status || "preview_ready";
    appState.recordPreviewUpdatedAt = response.updated_at || "";
    appState.recordPreviewLastSignature = signature;
    appState.recordPreviewLastRunAt = Date.now();
  } catch (error) {
    if (error?.name === "AbortError" || requestId !== appState.recordPreviewRequestId) return;
    appState.recordPreviewStatus = "failed";
    appState.recordPreviewError = error?.message || "实时预览暂不可用，转写继续。";
  } finally {
    if (requestId === appState.recordPreviewRequestId) {
      appState.recordPreviewInFlight = false;
      appState.recordPreviewAbortController = null;
      renderAll();
    }
  }
}

function scheduleRecordPreview({ force = false } = {}) {
  if (appState.currentRecordFields) return;
  const segments = currentReviewSegments().map(segmentWithInferredRole);
  const text = liveConversationTextForPreview();
  if (!force && segments.length < RECORD_PREVIEW_MIN_SEGMENTS && text.length < RECORD_PREVIEW_MIN_CHARS) return;
  const now = Date.now();
  const delay = force
    ? 0
    : Math.max(RECORD_PREVIEW_DEBOUNCE_MS, RECORD_PREVIEW_MIN_INTERVAL_MS - (now - appState.recordPreviewLastRunAt));
  if (appState.recordPreviewTimer) window.clearTimeout(appState.recordPreviewTimer);
  appState.recordPreviewTimer = window.setTimeout(() => {
    appState.recordPreviewTimer = null;
    fetchRecordPreview(text, segments);
  }, delay);
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
      sourceSegment: null,
      segmentId: `text-${index}`,
      startTime: null,
      endTime: null,
      speakerId: null,
      time: "--:--",
      speaker: classifySpeaker(line),
      label: classifySpeaker(line) === "doctor" ? "医生" : classifySpeaker(line) === "patient" ? "患者" : "待确认",
      text: line.replace(/^\[(医生|患者|doctor|patient|待校正)\]\s*/i, ""),
    }));
}

function transcriptRows() {
  if (appState.liveTranscriptSegments.length) {
    return appState.liveTranscriptSegments.map((segment, index) => {
      const displaySegment = segmentWithInferredRole(segment);
      const label = roleLabelFromSegment(displaySegment, displaySegment.text || "");
      return {
        index,
        editable: Boolean(appState.currentAsrResult),
        sourceSegment: segment,
        segmentId: segment.segment_id || `live-${index}`,
        startTime: segmentStartsAt(segment),
        endTime: segmentEndsAt(segment),
        speakerId: segment.speaker_id || segment.speaker || null,
        provisional: Boolean(segment.provisional),
        time: segmentTime(segment),
        speaker: speakerClassFromRole(label),
        label,
        text: segment.text || "",
        confidence: segment.confidence,
        roleConfidence: displaySegment.role_confidence,
        roleSource: displaySegment.role_source,
        roleNote: displaySegment.role_note,
        needsReview: Boolean(displaySegment.needs_review || label === "待确认"),
        reviewedByDoctor: Boolean(segment.reviewed_by_doctor),
      };
    });
  }
  const asr = appState.currentAsrResult;
  if (asr?.segments?.length) {
    return asr.segments.map((segment, index) => {
      const displaySegment = segmentWithInferredRole(segment);
      const label = roleLabelFromSegment(displaySegment, displaySegment.text || "");
      return {
        index,
        editable: true,
        sourceSegment: segment,
        segmentId: segment.segment_id || `result-${index}`,
        startTime: segmentStartsAt(segment),
        endTime: segmentEndsAt(segment),
        speakerId: segment.speaker_id || segment.speaker || null,
        provisional: Boolean(segment.provisional),
        time: segmentTime(segment),
        speaker: speakerClassFromRole(label),
        label,
        text: segment.text || "",
        confidence: segment.confidence,
        roleConfidence: displaySegment.role_confidence,
        roleSource: displaySegment.role_source,
        roleNote: displaySegment.role_note,
        needsReview: Boolean(displaySegment.needs_review || label === "待确认"),
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

function roleConfidenceText(item) {
  if (item.roleConfidence != null) {
    const prefix = item.roleNote || "角色置信度";
    return `${prefix} ${Math.round(Number(item.roleConfidence) * 100)}%`;
  }
  if (item.roleNote) return item.roleNote;
  if (item.confidence != null) return `转写置信度 ${Math.round(Number(item.confidence) * 100)}%`;
  return "角色置信度待评估";
}

function asrProgressPercent() {
  const progress = Math.max(0, Math.min(1, Number(appState.asrStreamProgress || 0)));
  return Math.round(progress * 100);
}

function asrPhaseLabel() {
  const labels = {
    idle: "等待音频",
    model_loading: "模型加载中",
    model_ready: "模型已就绪",
    streaming: "实时转写中",
    streaming_completed: "文字转写完成",
    speaker_calibration: "角色与标点校准中",
    speaker_calibration_completed: "说话人校准完成",
    speaker_calibration_failed: "说话人校准需人工复核",
    streaming_fallback: "流式不可用，正在分段识别",
    completed: "转写完成",
  };
  return labels[appState.asrPhase] || "转写处理中";
}

function releaseAudioPlayerSource() {
  const audio = $("consultationAudio");
  audio?.pause();
  if (appState.audioObjectUrl) URL.revokeObjectURL(appState.audioObjectUrl);
  appState.audioObjectUrl = "";
  appState.audioMediaUrl = "";
  appState.audioDurationSeconds = 0;
  appState.audioCurrentTime = 0;
  appState.audioPlaying = false;
  appState.activeTranscriptSegmentId = "";
  if (audio) {
    audio.removeAttribute("src");
    audio.load();
  }
}

function updateSessionUrl(sessionId = "") {
  const url = new URL(window.location.href);
  if (sessionId) {
    url.searchParams.set("session_id", sessionId);
  } else {
    url.searchParams.delete("session_id");
  }
  window.history.replaceState({}, "", `${url.pathname}${url.search}${url.hash}`);
}

function prepareAudioPlayer(file) {
  releaseAudioPlayerSource();
  if (!file || !URL?.createObjectURL) return;
  appState.audioObjectUrl = URL.createObjectURL(file);
  const audio = $("consultationAudio");
  audio.src = appState.audioObjectUrl;
  audio.volume = appState.audioVolume;
  audio.playbackRate = appState.audioPlaybackRate;
  audio.load();
  renderAudioPlayer();
}

function applyUploadedAudioMetadata(uploaded = {}) {
  appState.audioMediaUrl = uploaded.media_url || appState.audioMediaUrl;
  appState.audioDurationSeconds = Number(uploaded.duration_seconds || appState.audioDurationSeconds || 0);
  const audio = $("consultationAudio");
  if (audio && !appState.audioObjectUrl && appState.audioMediaUrl) {
    audio.src = appState.audioMediaUrl;
    audio.load();
  }
  if (appState.currentAsrSessionId) updateSessionUrl(appState.currentAsrSessionId);
}

async function restoreAsrSessionFromUrl() {
  const sessionId = new URLSearchParams(window.location.search).get("session_id");
  if (!sessionId) return;
  try {
    const session = await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}`);
    appState.currentAsrSessionId = session.session_id;
    appState.currentAudioId = session.audio_id;
    appState.uploadedFilename = session.filename || "已恢复音频";
    appState.selectedEngine = session.engine || appState.selectedEngine;
    appState.audioMediaUrl = session.audio_id ? `/api/audio/${encodeURIComponent(session.audio_id)}/media` : "";
    if (appState.audioMediaUrl) {
      const audio = $("consultationAudio");
      audio.src = appState.audioMediaUrl;
      audio.load();
    }
    if (["stream_ready", "reviewed"].includes(session.status)) {
      const result = await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/result`);
      appState.currentAsrResult = result;
      appState.liveTranscriptSegments = result.segments || [];
      appState.audioDurationSeconds = Number(result.duration || 0);
      appState.asrAudioDurationSeconds = Number(result.duration || 0);
      appState.asrProcessedAudioSeconds = Number(result.duration || 0);
      appState.asrStreamProgress = 1;
      appState.asrProgressKind = "actual";
      appState.asrPhase = "completed";
      appState.taskStatus = "TRANSCRIBED";
    } else if (session.status === "transcribing") {
      appState.taskStatus = "TRANSCRIBING";
      appState.asrPhase = "model_loading";
      listenForAsrEvents(session.events_url || `/api/asr/sessions/${sessionId}/events`);
    }
    $("topAsrEngineSelect").value = appState.selectedEngine;
    $("audioEngineSelect").value = appState.selectedEngine;
    renderAll();
  } catch (error) {
    appState.asrLastError = `会话恢复失败：${error?.message || error}`;
    renderAll();
  }
}

function seekConsultationAudio(seconds, { autoplay = false } = {}) {
  const audio = $("consultationAudio");
  if (!audio?.src || !Number.isFinite(Number(seconds))) return;
  const duration = Number.isFinite(audio.duration) ? audio.duration : appState.audioDurationSeconds;
  audio.currentTime = Math.max(0, Math.min(Number(seconds), duration || Number(seconds)));
  appState.audioCurrentTime = audio.currentTime;
  if (autoplay) audio.play().catch(() => undefined);
  renderTranscript();
}

function activeTranscriptSegment(rows) {
  const currentTime = appState.audioCurrentTime;
  const timedRows = rows.filter((row) => row.startTime != null);
  if (!timedRows.length) return null;
  return [...timedRows]
    .reverse()
    .find((row) => currentTime >= row.startTime && (row.endTime == null || currentTime < row.endTime + 0.35))
    || [...timedRows].reverse().find((row) => currentTime >= row.startTime)
    || null;
}

function visibleTranscriptRows(rows) {
  if (appState.transcriptPacing !== "follow") return rows;
  return rows.filter((row) => row.startTime != null && row.startTime <= appState.audioCurrentTime + 0.2);
}

function speakerDisplayLabel(row, speakerCount) {
  if (!row.speakerId || speakerCount < 2) return row.label;
  const match = String(row.speakerId).match(/(\d+)$/);
  const suffix = match
    ? String.fromCharCode(65 + Math.min(Number(match[1]), 25))
    : String(row.speakerId).replace(/^speaker[-_]?|^spk/i, "").toUpperCase();
  return `${row.label} · ${suffix || row.speakerId}`;
}

function renderAudioPlayer() {
  const shell = $("consultationAudioPlayer");
  const audio = $("consultationAudio");
  if (!shell || !audio) return;
  const hasSource = Boolean(appState.audioObjectUrl || appState.audioMediaUrl || audio.src);
  shell.hidden = !hasSource;
  if (!hasSource) return;

  const duration = Number.isFinite(audio.duration) ? audio.duration : appState.audioDurationSeconds;
  const currentTime = Number.isFinite(audio.currentTime) ? audio.currentTime : appState.audioCurrentTime;
  appState.audioDurationSeconds = duration || appState.audioDurationSeconds;
  appState.audioCurrentTime = currentTime || 0;
  $("audioPlayPauseButton").textContent = audio.paused ? "▶" : "Ⅱ";
  $("audioPlayPauseButton").setAttribute("aria-label", audio.paused ? "播放音频" : "暂停音频");
  $("audioTimeLabel").textContent = `${formatRelativeTime(currentTime)} / ${formatRelativeTime(duration || 0)}`;
  if (!appState.audioSeekDragging) {
    $("audioSeekRange").value = duration ? String(Math.round(currentTime / duration * 1000)) : "0";
  }
  $("audioVolumeRange").value = String(audio.volume);
  $("audioPlaybackRate").value = String(audio.playbackRate || appState.audioPlaybackRate || 1);
  $("audioMuteButton").textContent = audio.muted || audio.volume === 0 ? "🔇" : "🔊";
  shell.querySelectorAll("[data-transcript-pace]").forEach((button) => {
    button.classList.toggle("active", button.dataset.transcriptPace === appState.transcriptPacing);
  });
  const processed = Number(appState.asrProcessedAudioSeconds || 0);
  const progressText = appState.asrProgressKind === "actual" && appState.taskStatus === "TRANSCRIBING"
    ? `${asrPhaseLabel()} · 已处理 ${formatRelativeTime(processed)} / ${formatRelativeTime(appState.asrAudioDurationSeconds || duration || 0)}`
    : asrPhaseLabel();
  $("audioProcessingSummary").textContent = progressText;
}

function updateTranscriptPlaybackHighlight() {
  const active = activeTranscriptSegment(transcriptRows());
  appState.activeTranscriptSegmentId = active?.segmentId || "";
  document.querySelectorAll(".transcript-table-row[data-segment-id]").forEach((row) => {
    row.classList.toggle("transcript-row-active", row.dataset.segmentId === appState.activeTranscriptSegmentId);
  });
}

function handleAudioTimeUpdate() {
  const audio = $("consultationAudio");
  if (!audio) return;
  appState.audioCurrentTime = Number(audio.currentTime || 0);
  if (appState.transcriptPacing === "follow") {
    renderTranscript();
  } else {
    renderAudioPlayer();
    updateTranscriptPlaybackHighlight();
  }
}

function toggleAudioPlayback() {
  const audio = $("consultationAudio");
  if (!audio?.src) return;
  if (audio.paused) {
    audio.play().catch((error) => reportActionError(error));
  } else {
    audio.pause();
  }
}

function renderTranscriptStatusPanel({ rows, asr, isStreaming, reviewable, unreviewedCount }) {
  const progress = asrProgressPercent();
  const total = appState.asrStreamTotalSegments || asr?.segments?.length || rows.length || 0;
  const current = asr
    ? total
    : Math.min(appState.asrStreamCurrentSegment || rows.length || 0, total || rows.length || 0);
  const statusText = appState.asrLastError
    ? "转写异常"
    : appState.asrChunkLastError
      ? "转写失败"
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
  const detailAction = rows.length ? detailButton("transcript:all", "查看全部转写") : "";
  const reviewText = reviewable
    ? unreviewedCount
      ? `${unreviewedCount} 段待确认`
      : "角色已确认"
    : "完成转写后校正";
  const elapsed = appState.asrElapsedSeconds
    ? ` · 已用时 ${Math.round(appState.asrElapsedSeconds)} 秒`
    : "";
  const progressLabel = isStreaming
    ? `${progress}%${appState.asrProgressEstimated ? " 估算" : ""} · ${current || rows.length || 0}段${elapsed}`
    : asr
      ? `${total || rows.length || 0}段 · ${reviewText}`
      : rows.length
        ? `${rows.length}条 · ${reviewText}`
        : "等待音频或文本输入";
  return `
    <section class="transcript-status-panel compact ${appState.asrLastError ? "danger" : isStreaming ? "active" : asr ? "done" : ""}" aria-label="转写状态">
      <div class="transcript-status-head">
        <div>
          <strong>${escapeHtml(statusText)}</strong>
          <span class="transcript-status-detail">${escapeHtml(progressLabel)}</span>
        </div>
        <span class="status-badge ${appState.asrLastError ? "missing" : asr ? "confirmed" : isStreaming ? "info" : "neutral"}">${escapeHtml(ENGINE_LABELS[asr?.engine || appState.selectedEngine] || asr?.engine || appState.selectedEngine || "ASR")}</span>
      </div>
      <div class="progress-track" aria-label="转写进度">
        <span style="width: ${progress}%"></span>
      </div>
      ${appState.asrLastError ? `<div class="safety-strip danger">${escapeHtml(appState.asrLastError)}</div>` : ""}
      ${appState.asrChunkLastError ? `<div class="safety-strip danger">${escapeHtml(appState.asrChunkLastError)}</div>` : ""}
      ${appState.asrRetryHint ? `<div class="safety-strip warning"><strong>重试提示</strong><br>${escapeHtml(appState.asrRetryHint)}</div>` : ""}
      ${actionButton || detailAction ? `<div class="quick-action-row">${actionButton}${detailAction}</div>` : ""}
    </section>
  `;
}

function renderTranscript() {
  const asr = appState.currentAsrResult;
  const rows = transcriptRows();
  const isStreaming = appState.currentAsrSessionId && appState.taskStatus === "TRANSCRIBING" && !asr;
  const hasTranscriptIssue = Boolean(appState.asrLastError || appState.asrChunkLastError);
  const progressPercent = asrProgressPercent();
  renderAudioPlayer();

  if (!rows.length && !asr && !appState.currentAsrSessionId) {
    $("transcriptBadge").textContent = "待转写";
    $("transcriptList").innerHTML = `<div class="empty-state transcript-empty">暂无对话转写。上传音频后，识别完成的句子会逐行显示。</div>`;
    return;
  }

  const progressLabel = appState.asrProgressKind === "actual" ? ` · ${progressPercent}%` : "";
  $("transcriptBadge").textContent = asr
    ? `转写完成 · ${rows.length}段`
    : isStreaming
      ? `${asrPhaseLabel()}${progressLabel} · ${rows.length}段`
      : `${rows.length}条`;

  const visibleRows = visibleTranscriptRows(rows);
  const activeSegment = activeTranscriptSegment(rows);
  appState.activeTranscriptSegmentId = activeSegment?.segmentId || "";
  const speakerCount = new Set(rows.map((row) => row.speakerId).filter(Boolean)).size;
  const streamingEmptyBlock = isStreaming && !rows.length
    ? `
      <div class="empty-state transcript-empty transcribing-empty" aria-live="polite">
        <div class="transcribing-empty-spinner" aria-hidden="true"></div>
        <div class="transcribing-empty-copy">
          <strong>${escapeHtml(asrPhaseLabel())}</strong>
          <span>${appState.asrProgressKind === "actual" ? `已处理 ${formatRelativeTime(appState.asrProcessedAudioSeconds)} / ${formatRelativeTime(appState.asrAudioDurationSeconds)}` : "正在准备本地模型"}</span>
          <small>模型产生稳定文字后会立即追加；说话人和标点将在转写后全局校准。</small>
        </div>
      </div>
    `
    : "";
  const followEmptyBlock = appState.transcriptPacing === "follow" && rows.length && !visibleRows.length
    ? `<div class="empty-state transcript-empty">已识别 ${rows.length} 段。播放音频后，文字会跟随播放位置出现。</div>`
    : "";
  const issueBlock = hasTranscriptIssue
    ? `<div class="transcript-inline-alert">${escapeHtml(appState.asrLastError || appState.asrChunkLastError)}</div>`
    : "";

  $("transcriptList").innerHTML = `
    ${issueBlock}
    ${streamingEmptyBlock}
    ${followEmptyBlock}
    <div class="transcript-table" role="list" aria-label="对话转写列表">
      ${visibleRows.map((item, index) => `
        <div
          class="transcript-table-row ${item.segmentId === appState.activeTranscriptSegmentId ? "transcript-row-active" : ""} ${item.provisional ? "provisional" : ""}"
          data-segment-index="${item.index}"
          data-segment-id="${escapeHtml(item.segmentId)}"
          ${item.startTime != null ? `data-segment-start="${item.startTime}"` : ""}
          role="listitem"
          tabindex="0"
        >
          <span class="transcript-row-time">${escapeHtml(item.time)}</span>
          <span class="transcript-role-tag ${escapeHtml(item.speaker)}">【${escapeHtml(speakerDisplayLabel(item, speakerCount))}】</span>
          <span class="transcript-row-text">${escapeHtml(item.text || "（无文本）")}</span>
          <button type="button" class="transcript-row-link" data-open-detail="transcript:${item.index}" data-busy-allowed="true">查看原文</button>
        </div>
      `).join("")}
    </div>
  `;
}

function renderTranscriptDetailContent(target = "all") {
  const rows = transcriptRows();
  if (!rows.length) return `<div class="empty-state">暂无对话转写。</div>`;
  const selectedIndex = Number(target);
  const canEdit = Boolean(appState.currentAsrSessionId && appState.currentAsrResult?.segments?.length);
  const unreviewedCount = rows.filter((item) => item.needsReview || !item.reviewedByDoctor).length;
  const canGenerateFromTranscript = Boolean(appState.currentAsrResult && !appState.currentTaskId && !appState.currentRecordFields);
  const speakerGroups = transcriptSpeakerGroups(rows);
  const reviewHint = canEdit
    ? appState.roleReviewDirty
      ? "存在未保存校正，保存后会用于后续病历生成。"
      : "可在这里校正角色和原文，默认列表保持只读。"
    : "当前内容来自文本导入或无可保存 ASR 会话，仅展示完整原文。";
  const actionButtons = `
    <div class="transcript-review-actions">
      ${canEdit ? `<button type="button" class="primary-action" data-save-role-review ${appState.roleReviewSaving ? "disabled" : ""}>${appState.roleReviewSaving ? "保存中" : "保存校正"}</button>` : ""}
      ${canGenerateFromTranscript ? `<button type="button" class="secondary-action" data-generate-from-transcript>用当前转写生成病历</button>` : ""}
    </div>
  `;
  return `
    ${detailSection("转写状态", `
      <div class="detail-kv"><span>引擎</span><strong>${escapeHtml(appState.currentAsrResult?.engine || appState.selectedEngine || "ASR")}</strong></div>
      <div class="detail-kv"><span>分段</span><strong>${rows.length} 条</strong></div>
      <div class="detail-kv"><span>校正</span><strong>${escapeHtml(canEdit ? (unreviewedCount ? `${unreviewedCount} 段待确认` : "角色已确认") : "只读")}</strong></div>
      <p class="detail-note">${escapeHtml(reviewHint)}</p>
    `)}
    ${canEdit && speakerGroups.length ? detailSection("按说话人统一校正", `
      <p class="detail-note">说话人由 CAM++ 声纹聚类得到；临床角色仍需医生确认。一次修改会同步到该说话人的全部发言。</p>
      <div class="speaker-role-groups">
        ${speakerGroups.map((group) => `
          <label class="speaker-role-group">
            <span><strong>${escapeHtml(group.displayName)}</strong><small>${escapeHtml(group.speakerId)} · ${group.count} 段</small></span>
            <select data-speaker-role-select data-speaker-id="${escapeHtml(group.speakerId)}" aria-label="设置${escapeHtml(group.displayName)}角色">
              ${renderRoleOptions(group.role)}
            </select>
          </label>
        `).join("")}
      </div>
    `) : ""}
    ${detailSection("角色与文本校正", `
      <div class="transcript-review-list">
        ${rows.map((item) => `
          <div class="transcript-review-row ${Number.isFinite(selectedIndex) && selectedIndex === item.index ? "focus" : ""}" data-segment-index="${item.index}">
            <div class="transcript-review-meta">
              <span class="transcript-row-time">${escapeHtml(item.time)}</span>
              ${canEdit ? `
                <select data-detail-role-select aria-label="校正角色">
                  ${renderRoleOptions(item.label)}
                </select>
              ` : `<strong class="transcript-role-tag ${escapeHtml(item.speaker)}">【${escapeHtml(item.label)}】</strong>`}
              <span class="status-badge ${item.needsReview ? "candidate" : item.reviewedByDoctor ? "confirmed" : "neutral"}">
                ${item.needsReview ? "待确认" : item.reviewedByDoctor ? "已校正" : "未校正"}
              </span>
            </div>
            <textarea data-detail-segment-text ${canEdit ? "" : "readonly"}>${escapeHtml(item.text)}</textarea>
          </div>
        `).join("")}
      </div>
      ${actionButtons}
    `)}
  `;
}

function missingItems() {
  const fields = activeRecordFields();
  if (!fields) return [];
  return FIELD_DEFS.filter(([key]) => fieldStatus(fields[key], key).key === "missing").map(([, label]) => label);
}

function allEvidence() {
  const fields = activeRecordFields();
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
        ${listPreview(diagnoses, 2).visible.map((diagnosis, index) => `
          <li>
            <span>${index + 1}</span>
            <div>
              <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong>
              <em>${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</em>
            </div>
          </li>
        `).join("")}
      </ol>
      ${diagnoses.length > 2 ? `<div class="summary-note">另有 ${diagnoses.length - 2} 条候选诊断，点击详情查看。</div>` : ""}
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
  const treatmentText = treatment?.value || treatment?.hint || previewTreatmentText() || "暂无明确处理建议，需医生结合问诊、查体和检查结果补充。";
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
        <strong>${escapeHtml(treatmentText)}</strong>
      </div>
      <div class="assist-mini-grid">
        <div>
          <span>建议检查</span>
          <strong>${escapeHtml(suggestedChecks.slice(0, 3).join("、") || "暂无结构化建议检查")}</strong>
        </div>
        <div>
          <span>用药提示</span>
          <strong>${escapeHtml(medicationNotes.slice(0, 3).join("、") || "不自动处方，需医生确认")}</strong>
        </div>
      </div>
    `,
  });
}

function renderEvidenceCard(evidence, diagnoses) {
  const diagnosisReasons = diagnoses
    .map((diagnosis) => diagnosis.reason ? `${diagnosis.name || "候选诊断"}：${diagnosis.reason}` : "")
    .filter(Boolean);
  const linkedEvidence = (appState.recordPreview?.evidence_links || []).map((item) => ({
    text: `${item.label || "字段证据"}：${item.evidence || item.text || ""}`,
    segmentId: item.segment_id || "",
    startTime: item.start_time,
  }));
  const items = [
    ...linkedEvidence,
    ...diagnosisReasons.map((text) => ({ text })),
    ...evidence.map((text) => ({ text })),
  ].filter((item, index, values) => item.text && values.findIndex((candidate) => candidate.text === item.text) === index).slice(0, 6);

  return assistCard({
    title: "判断证据",
    badgeClass: items.length ? "info" : "neutral",
    badgeText: items.length ? "可追溯" : "暂无",
    detailTarget: "assist:evidence",
    body: items.length
      ? listPreview(items, 3).visible.map((item) => item.segmentId
        ? `<button type="button" class="assist-evidence-quote linked" data-evidence-segment-id="${escapeHtml(item.segmentId)}" ${item.startTime != null ? `data-evidence-start="${item.startTime}"` : ""}>${escapeHtml(item.text)}<span>播放证据</span></button>`
        : `<div class="assist-evidence-quote">${escapeHtml(item.text)}</div>`).join("")
        + (items.length > 3 ? `<div class="summary-note">另有 ${items.length - 3} 条证据，点击详情查看。</div>` : "")
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
      ${listPreview(rows, 4).visible.map((row) => `
        <div class="assist-check-row ${row.tone}">
          <span></span>
          <strong>${escapeHtml(row.text)}</strong>
        </div>
      `).join("")}
      ${rows.length > 4 ? `<div class="summary-note">另有 ${rows.length - 4} 条校验结果，点击详情查看。</div>` : ""}
    </div>`,
  });
}

function renderAssistDetailContent(section) {
  const fields = activeRecordFields();
  const diagnoses = fields?.candidate_diagnoses || [];
  const evidence = allEvidence();
  const missing = missingItems();
  const risk = riskSummary();
  const safety = activeSafetyCheck();
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
    const treatmentText = treatment?.value || treatment?.hint || previewTreatmentText() || activeDraftText() || "暂无明确处理建议，需医生补充。";
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

function renderDoctorAssistOverview({ fields, diagnoses, evidence }) {
  const previewNotice = isRecordPreviewActive()
    ? `<div class="preview-notice">${escapeHtml(previewNoticeText())}；不作为最终诊断或处方。</div>`
    : "";
  const previewError = appState.recordPreviewError
    ? `<div class="safety-strip warning">${escapeHtml(appState.recordPreviewError)}</div>`
    : "";
  return `
    <div class="doctor-assist-overview">
      ${previewNotice}
      ${previewError}
      ${renderCandidateDiagnosisCard(diagnoses)}
      ${renderTreatmentRecommendationCard(fields, diagnoses)}
      ${renderEvidenceCard(evidence, diagnoses)}
    </div>
  `;
}

function renderAssist() {
  const fields = activeRecordFields();
  const safety = activeSafetyCheck();
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
      badgeClass: activeDraftText() ? "info" : "neutral",
      badgeText: activeDraftText() ? (isRecordPreviewActive() ? "预览" : "已生成") : "待生成",
      open: false,
      body: `<div class="draft-block">${escapeHtml(activeDraftText() || "暂无病历草稿。")}</div>`,
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
    const title = DRAFT_FIELD_DEFS.find(([key]) => key === value)?.[1]
      || FIELD_DEFS.find(([key]) => key === value)?.[1]
      || "病历字段详情";
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
    openDetailDrawer("对话转写与校正", renderTranscriptDetailContent(value));
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
  appState.pendingGenerateAfterRoleReview = false;
  appState.speakerRoleCorrections = {};
}

function resetRecordPreview() {
  if (appState.recordPreviewTimer) {
    window.clearTimeout(appState.recordPreviewTimer);
    appState.recordPreviewTimer = null;
  }
  appState.recordPreviewAbortController?.abort();
  appState.recordPreviewAbortController = null;
  appState.recordPreviewRequestId += 1;
  appState.recordPreview = null;
  appState.recordPreviewStatus = "idle";
  appState.recordPreviewUpdatedAt = "";
  appState.recordPreviewError = "";
  appState.recordPreviewLastRunAt = 0;
  appState.recordPreviewLastSignature = "";
  appState.recordPreviewInFlight = false;
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
  resetRecordPreview();
  if (!keepAsr) {
    closeAsrStream();
    releaseAudioPlayerSource();
    updateSessionUrl("");
    appState.currentAsrResult = null;
    appState.currentAudioId = null;
    appState.currentAsrSessionId = null;
    appState.liveTranscriptSegments = [];
    appState.asrStreamProgress = 0;
    appState.asrStreamCurrentSegment = 0;
    appState.asrStreamTotalSegments = 0;
    appState.asrPhase = "idle";
    appState.asrProgressKind = "indeterminate";
    appState.asrProcessedAudioSeconds = 0;
    appState.asrAudioDurationSeconds = 0;
    appState.diarizationStatus = "idle";
    appState.asrFirstSegmentAt = "";
    appState.asrLastSegmentAt = "";
    appState.asrVisibleAudioSeconds = 0;
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
    appState.asrProgressEstimated = false;
    appState.asrElapsedSeconds = 0;
    appState.asrStreamCurrentSegment = 0;
    appState.asrStreamTotalSegments = 0;
    appState.asrPhase = "idle";
    appState.asrProgressKind = "indeterminate";
    appState.asrProcessedAudioSeconds = 0;
    appState.asrAudioDurationSeconds = 0;
    appState.diarizationStatus = "idle";
    appState.asrFirstSegmentAt = "";
    appState.asrLastSegmentAt = "";
    appState.asrVisibleAudioSeconds = 0;
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
    appState.asrPhase = "model_loading";
    appState.asrProgressKind = "indeterminate";
    appState.asrProgressEstimated = false;
    setBusy(true, "正在识别音频...");
    renderAll();
  });

  source.addEventListener("transcribing_progress", (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrPhase = data.phase || appState.asrPhase || "streaming";
    appState.asrProgressKind = data.progress_kind || appState.asrProgressKind || "indeterminate";
    if (data.progress != null) appState.asrStreamProgress = Number(data.progress);
    if (data.processed_audio_seconds != null) {
      appState.asrProcessedAudioSeconds = Number(data.processed_audio_seconds);
    }
    if (data.audio_duration_seconds != null) {
      appState.asrAudioDurationSeconds = Number(data.audio_duration_seconds);
    }
    appState.asrProgressEstimated = false;
    appState.asrElapsedSeconds = Number(data.elapsed_seconds || appState.asrElapsedSeconds || 0);
    setBusy(true, "正在识别音频...");
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
    appState.asrProgressEstimated = false;
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
    appState.asrProgressEstimated = false;
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
    appState.asrProgressEstimated = false;
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
    appState.asrProgressEstimated = false;
    renderAll();
  });

  const handleTranscriptSegment = (event) => {
    const data = JSON.parse(event.data);
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    appState.taskStatus = "TRANSCRIBING";
    appState.asrPhase = "streaming";
    appState.asrProgressKind = data.progress_kind || appState.asrProgressKind || "actual";
    if (data.progress != null) appState.asrStreamProgress = Number(data.progress);
    if (data.processed_audio_seconds != null) {
      appState.asrProcessedAudioSeconds = Number(data.processed_audio_seconds);
    }
    if (data.audio_duration_seconds != null) {
      appState.asrAudioDurationSeconds = Number(data.audio_duration_seconds);
    }
    appState.asrProgressEstimated = false;
    appState.asrStreamTotalSegments = Number(data.total || appState.asrStreamTotalSegments || 0);
    if (data.segment) {
      upsertLiveTranscriptSegment(data.segment);
      appState.asrStreamCurrentSegment = appState.liveTranscriptSegments.length;
      const now = new Date().toISOString();
      appState.asrFirstSegmentAt = appState.asrFirstSegmentAt || now;
      appState.asrLastSegmentAt = now;
      const segmentEnd = segmentEndsAt(data.segment);
      if (segmentEnd != null) {
        appState.asrVisibleAudioSeconds = Math.max(appState.asrVisibleAudioSeconds || 0, segmentEnd);
      }
      scheduleRecordPreview();
    }
    renderAll();
  };

  source.addEventListener("segment", handleTranscriptSegment);
  source.addEventListener("segment_update", handleTranscriptSegment);

  source.addEventListener("diarization_progress", (event) => {
    const data = JSON.parse(event.data);
    appState.taskStatus = "TRANSCRIBING";
    appState.asrPhase = data.phase || "speaker_calibration";
    appState.asrProgressKind = data.progress_kind || "indeterminate";
    appState.diarizationStatus = data.status || "reconciling";
    if (data.progress != null) appState.asrStreamProgress = Number(data.progress);
    if (data.status === "failed") {
      appState.asrRetryHint = data.message || "说话人校准未完成，可在转写详情中人工校正。";
    }
    renderAll();
  });

  source.addEventListener("reconciliation_completed", (event) => {
    const data = JSON.parse(event.data);
    const result = data.asr_result;
    if (!result) return;
    appState.currentAsrResult = result;
    appState.liveTranscriptSegments = finalTranscriptSegments(result.segments || [], []);
    appState.asrStreamCurrentSegment = appState.liveTranscriptSegments.length;
    appState.asrStreamTotalSegments = appState.liveTranscriptSegments.length;
    appState.asrPhase = "speaker_calibration_completed";
    appState.diarizationStatus = "completed";
    scheduleRecordPreview({ force: true });
    renderAll();
  });

  source.addEventListener("completed", (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    appState.currentAudioId = data.audio_id || appState.currentAudioId;
    appState.selectedEngine = data.engine || appState.selectedEngine;
    const mergedSegments = finalTranscriptSegments(data.asr_result?.segments || [], appState.liveTranscriptSegments);
    appState.currentAsrResult = data.asr_result
      ? {
          ...data.asr_result,
          segments: mergedSegments,
          text: textFromSegments(mergedSegments) || data.asr_result.text,
          conversation_text: conversationFromSegments(mergedSegments) || data.asr_result.conversation_text,
        }
      : data.asr_result;
    appState.liveTranscriptSegments = mergedSegments;
    appState.taskStatus = "TRANSCRIBED";
    appState.asrPhase = "completed";
    appState.asrProgressKind = "actual";
    appState.asrStreamProgress = 1;
    appState.asrProgressEstimated = false;
    appState.asrElapsedSeconds = 0;
    appState.asrVisibleAudioSeconds = Math.max(
      appState.asrVisibleAudioSeconds || 0,
      Number(data.duration || data.asr_result?.duration || 0),
    );
    appState.asrProcessedAudioSeconds = Number(data.duration || data.asr_result?.duration || appState.asrProcessedAudioSeconds || 0);
    appState.asrAudioDurationSeconds = Number(data.duration || data.asr_result?.duration || appState.asrAudioDurationSeconds || 0);
    appState.asrStreamTotalSegments = data.segments || data.asr_result?.segments?.length || appState.asrStreamTotalSegments || appState.liveTranscriptSegments.length;
    appState.asrStreamCurrentSegment = appState.asrStreamTotalSegments;
    appState.asrLastError = "";
    appState.asrChunkStatus = appState.asrChunkTotal ? "切片转写完成" : "";
    appState.asrChunkLastError = "";
    appState.asrRetryHint = "";
    appState.currentEvaluation = null;
    resetRoleReviewState();
    scheduleRecordPreview({ force: true });
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

async function createRecordTask(conversationText, { keepAsr = false } = {}) {
  resetTaskState({ keepAsr });
  appState.currentInputText = conversationText;
  if (!keepAsr) {
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
  }
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

function updateSpeakerRole(speakerId, role) {
  if (!speakerId) return;
  const segments = currentReviewSegments();
  let changed = false;
  segments.forEach((segment) => {
    const identity = segment.speaker_id || segment.speaker;
    if (identity !== speakerId) return;
    segment.role = role;
    segment.reviewed_by_doctor = role !== "待确认";
    segment.needs_review = role === "待确认";
    changed = true;
  });
  if (!changed) return;
  appState.speakerRoleCorrections[speakerId] = role;
  appState.roleReviewDirty = true;
  syncAsrTextFromSegments();
  renderAll();
}

function transcriptSpeakerGroups(rows = transcriptRows()) {
  const groups = new Map();
  rows.forEach((row) => {
    if (!row.speakerId) return;
    const current = groups.get(row.speakerId) || {
      speakerId: row.speakerId,
      count: 0,
      roles: [],
    };
    current.count += 1;
    current.roles.push(row.label);
    groups.set(row.speakerId, current);
  });
  return [...groups.values()].map((group, index) => {
    const roleCounts = group.roles.reduce((counts, role) => {
      counts[role] = (counts[role] || 0) + 1;
      return counts;
    }, {});
    const role = Object.entries(roleCounts).sort((left, right) => right[1] - left[1])[0]?.[0] || "待确认";
    return {
      ...group,
      role,
      displayName: `说话人 ${String.fromCharCode(65 + Math.min(index, 25))}`,
    };
  });
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

function roleReviewPendingCount() {
  return currentReviewSegments()
    .filter((segment) => segment.needs_review || !segment.role || segment.role === "待确认")
    .length;
}

function focusNextActionPanel() {
  const panel = $("nextActionPanel");
  if (!panel) return;
  panel.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  panel.querySelector("[data-workflow-action='generate-record'], [data-workflow-action='save-role-review']")?.focus?.();
}

async function saveRoleReview({ silent = false } = {}) {
  if (!appState.currentAsrSessionId || !appState.currentAsrResult?.segments?.length) {
    if (!silent) showToast("暂无可保存的角色校正结果");
    return appState.currentAsrResult;
  }

  syncAsrTextFromSegments();
  appState.roleReviewSaving = true;
  renderAll();
  let savedResult = appState.currentAsrResult;
  let pendingCount = 0;
  let shouldAutoGenerate = false;
  try {
    const segments = appState.currentAsrResult.segments.map((segment, index) => ({
      index,
      role: segment.role || "待确认",
      text: segment.text || "",
      reviewed_by_doctor: Boolean(segment.reviewed_by_doctor && segment.role && segment.role !== "待确认"),
    }));
    const speakerRoles = Object.entries(appState.speakerRoleCorrections).map(([speakerId, role]) => ({
      speaker_id: speakerId,
      role,
      reviewed_by_doctor: role !== "待确认",
    }));

    const response = await api(`/api/asr/sessions/${appState.currentAsrSessionId}/result`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        reviewer: "doctor",
        segments,
        speaker_roles: speakerRoles,
      }),
    });
    appState.currentAsrResult = response.asr_result;
    appState.liveTranscriptSegments = response.asr_result.segments || [];
    appState.currentAudioId = response.audio_id || appState.currentAudioId;
    appState.roleReviewDirty = false;
    appState.speakerRoleCorrections = {};
    savedResult = response.asr_result;
    pendingCount = roleReviewPendingCount();
    shouldAutoGenerate = Boolean(
      !silent
        && appState.pendingGenerateAfterRoleReview
        && !pendingCount
        && !appState.currentTaskId
        && !appState.currentRecordFields,
    );
  } finally {
    appState.roleReviewSaving = false;
    renderAll();
  }
  if (silent) return savedResult;
  if (pendingCount) {
    showToast(`角色校正已保存，仍有 ${pendingCount} 段待确认`);
    focusNextActionPanel();
    return savedResult;
  }
  if (shouldAutoGenerate) {
    appState.pendingGenerateAfterRoleReview = false;
    closeDrawer();
    showToast("角色校正已保存，正在生成病历");
    await regenerateRecord();
    return savedResult;
  }
  appState.pendingGenerateAfterRoleReview = false;
  showToast("角色校正已保存，可继续生成病历");
  focusNextActionPanel();
  renderAll();
  return savedResult;
}

async function uploadAndTranscribe(file, engine) {
  if (!file) throw new Error("请选择音频文件");
  resetRecordPreview();
  prepareAudioPlayer(file);
  appState.selectedEngine = engine;
  appState.uploadedFilename = "上传中";
  appState.taskStatus = "CREATED";
  appState.currentAsrResult = null;
  appState.liveTranscriptSegments = [];
  appState.asrStreamProgress = 0;
  appState.asrStreamCurrentSegment = 0;
  appState.asrStreamTotalSegments = 0;
  appState.asrPhase = "model_loading";
  appState.asrProgressKind = "indeterminate";
  appState.asrProcessedAudioSeconds = 0;
  appState.asrAudioDurationSeconds = 0;
  appState.diarizationStatus = "idle";
  appState.asrFirstSegmentAt = "";
  appState.asrLastSegmentAt = "";
  appState.asrVisibleAudioSeconds = 0;
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
  applyUploadedAudioMetadata(uploaded);
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
        appState.pendingGenerateAfterRoleReview = true;
        setBusy(false);
        const pendingCount = roleReviewPendingCount();
        showToast(pendingCount
          ? `转写完成，仍有 ${pendingCount} 段角色待确认`
          : "转写完成，请保存角色校正后自动生成病历");
        focusNextActionPanel();
        renderAll();
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
    const keepAsr = Boolean(appState.currentAudioId && appState.currentAsrResult?.engine !== "text-import");
    await createRecordTask(text, { keepAsr });
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
  const consultationAudio = $("consultationAudio");
  $("doctorModeButton").addEventListener("click", () => setViewMode("doctor"));
  $("debugModeButton").addEventListener("click", () => setViewMode("debug"));
  $("demoModeButton").addEventListener("click", () => setScreenshotMode(false));
  $("screenshotModeButton").addEventListener("click", () => setScreenshotMode(true));
  $("standardModeButton").addEventListener("click", () => setDisplayScale("standard"));
  $("careModeButton").addEventListener("click", () => setDisplayScale("care"));
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
  $("transcriptSettingsButton").addEventListener("click", () => openWorkbenchDetail("transcript:all"));
  $("audioPlayPauseButton").addEventListener("click", toggleAudioPlayback);
  $("audioMuteButton").addEventListener("click", () => {
    consultationAudio.muted = !consultationAudio.muted;
    appState.audioMuted = consultationAudio.muted;
    renderAudioPlayer();
  });
  $("audioSeekRange").addEventListener("pointerdown", () => {
    appState.audioSeekDragging = true;
  });
  $("audioSeekRange").addEventListener("input", (event) => {
    const duration = Number.isFinite(consultationAudio.duration)
      ? consultationAudio.duration
      : appState.audioDurationSeconds;
    seekConsultationAudio(duration * Number(event.target.value || 0) / 1000);
  });
  $("audioSeekRange").addEventListener("change", () => {
    appState.audioSeekDragging = false;
    renderAudioPlayer();
  });
  $("audioVolumeRange").addEventListener("input", (event) => {
    consultationAudio.volume = Number(event.target.value);
    consultationAudio.muted = false;
    appState.audioVolume = consultationAudio.volume;
    appState.audioMuted = false;
    renderAudioPlayer();
  });
  $("audioPlaybackRate").addEventListener("change", (event) => {
    consultationAudio.playbackRate = Number(event.target.value);
    appState.audioPlaybackRate = consultationAudio.playbackRate;
    renderAudioPlayer();
  });
  $("consultationAudioPlayer").addEventListener("click", (event) => {
    const paceButton = event.target.closest("[data-transcript-pace]");
    if (!paceButton) return;
    appState.transcriptPacing = paceButton.dataset.transcriptPace;
    renderTranscript();
  });
  consultationAudio.addEventListener("loadedmetadata", () => {
    appState.audioDurationSeconds = Number.isFinite(consultationAudio.duration)
      ? consultationAudio.duration
      : appState.audioDurationSeconds;
    renderAudioPlayer();
  });
  consultationAudio.addEventListener("timeupdate", handleAudioTimeUpdate);
  consultationAudio.addEventListener("play", () => {
    appState.audioPlaying = true;
    renderAudioPlayer();
  });
  consultationAudio.addEventListener("pause", () => {
    appState.audioPlaying = false;
    renderAudioPlayer();
  });
  consultationAudio.addEventListener("ended", () => {
    appState.audioPlaying = false;
    renderAudioPlayer();
  });
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
    const transcriptRow = event.target.closest(".transcript-table-row[data-segment-start]");
    if (transcriptRow) {
      seekConsultationAudio(Number(transcriptRow.dataset.segmentStart), { autoplay: true });
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
  $("transcriptList").addEventListener("keydown", (event) => {
    if (!['Enter', ' '].includes(event.key)) return;
    const transcriptRow = event.target.closest(".transcript-table-row[data-segment-start]");
    if (!transcriptRow || event.target.closest("button, select, textarea")) return;
    event.preventDefault();
    seekConsultationAudio(Number(transcriptRow.dataset.segmentStart), { autoplay: true });
  });
  $("detailDrawerContent").addEventListener("change", (event) => {
    const speakerRoleSelect = event.target.closest("[data-speaker-role-select]");
    if (speakerRoleSelect) {
      updateSpeakerRole(speakerRoleSelect.dataset.speakerId, speakerRoleSelect.value);
      $("detailDrawerContent").innerHTML = renderTranscriptDetailContent();
      return;
    }
    const roleSelect = event.target.closest("[data-detail-role-select]");
    if (!roleSelect) return;
    const row = roleSelect.closest("[data-segment-index]");
    updateReviewSegment(Number(row.dataset.segmentIndex), { role: roleSelect.value });
    renderTranscript();
  });
  $("detailDrawerContent").addEventListener("input", (event) => {
    const textInput = event.target.closest("[data-detail-segment-text]");
    if (!textInput) return;
    const row = textInput.closest("[data-segment-index]");
    updateReviewSegment(Number(row.dataset.segmentIndex), { text: textInput.value });
    renderTranscript();
  });
  $("detailDrawerContent").addEventListener("click", async (event) => {
    const generateButton = event.target.closest("[data-generate-from-transcript]");
    if (generateButton) {
      await regenerateRecord();
      return;
    }
    const saveButton = event.target.closest("[data-save-role-review]");
    if (!saveButton) return;
    try {
      await saveRoleReview();
      $("detailDrawerContent").innerHTML = renderTranscriptDetailContent();
    } catch (error) {
      reportActionError(error);
    }
  });
  $("assistPanels").addEventListener("click", (event) => {
    const evidenceButton = event.target.closest("[data-evidence-segment-id]");
    if (evidenceButton) {
      const row = transcriptRows().find((item) => item.segmentId === evidenceButton.dataset.evidenceSegmentId);
      const start = evidenceButton.dataset.evidenceStart !== undefined
        ? Number(evidenceButton.dataset.evidenceStart)
        : row?.startTime;
      if (start != null) seekConsultationAudio(start, { autoplay: true });
      return;
    }
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

async function init() {
  bindEvents();
  renderAll();
  refreshLlmStatus();
  await restoreAsrSessionFromUrl();
}

init();
