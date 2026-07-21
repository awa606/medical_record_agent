const appState = {
  currentTaskId: null,
  currentAudioId: null,
  currentAsrSessionId: null,
  currentAsrResult: null,
  liveTranscriptSegments: [],
  provisionalTranscriptSegments: [],
  currentEvaluation: null,
  currentTask: null,
  currentEncounter: null,
  currentSteps: [],
  currentRecordFields: null,
  currentDraft: "",
  currentSafetyCheck: null,
  currentQualityReport: null,
  currentExportReadiness: null,
  currentExports: null,
  currentAgentTrace: null,
  currentLlmStatus: null,
  currentInputText: "",
  productView: "workbench",
  adminUsers: [],
  adminRuntimeStatus: null,
  adminStatus: "idle",
  adminError: "",
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
  asrConnectionStatus: "idle",
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
  speakerAssignments: [],
  speakerMappingRequired: false,
  lastSpeakerMergeSnapshot: null,
  doctorProfiles: [],
  selectedDoctorProfileId: "",
  doctorProfileEnrollmentBusy: false,
  browserRecordingStatus: "idle",
  browserRecordingStartedAt: 0,
  browserRecordingElapsedSeconds: 0,
  browserRecordingTimer: null,
  browserRecordingChunkTimer: null,
  browserRecordingStream: null,
  browserRecordingAudioContext: null,
  browserRecordingSource: null,
  browserRecordingProcessor: null,
  browserRecordingChunkBuffer: [],
  browserRecordingChunkIndex: 0,
  browserRecordingRecordedChunks: 0,
  browserRecordingUploadedChunks: 0,
  browserRecordingPendingChunks: 0,
  browserRecordingRetryStatus: "",
  browserRecordingUploadInFlight: false,
  browserRecordingRetryTimer: null,
  browserRecordingRecovering: false,
  browserRecordingMissingChunks: [],
  browserRecordingSessionId: "",
  browserRecordingPausedAt: 0,
  browserRecordingTotalPausedMs: 0,
  browserRecordingSampleRate: 0,
  browserRecordingRecordedSamples: 0,
  browserRecordingObjectUrl: "",
  browserRecordingFile: null,
  browserRecordingFinalized: null,
  browserRecordingMessage: "",
  browserRecordingChunkStatus: "",
  browserRecordingRequestId: 0,
  lastActionError: "",
  inputMenuOpen: false,
  settingsOpen: false,
  compactDoctorMode: true,
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
  asrPrewarmStatus: null,
  asrPrewarmCheckedAt: "",
  asrPrewarmTimer: null,
  authUser: null,
  authStatus: "unknown",
  authMessage: "",
  encounterWorklist: [],
  encounterWorklistStatus: "idle",
  encounterWorklistError: "",
};

window.__MRA_APP_STATE__ = appState;

const RECORD_PREVIEW_MIN_CHARS = 10;
const RECORD_PREVIEW_MIN_SEGMENTS = 1;
const RECORD_PREVIEW_MIN_INTERVAL_MS = 2000;
const RECORD_PREVIEW_DEBOUNCE_MS = 450;
const ROLE_DISPLAY_CONFIDENCE_THRESHOLD = 0.9;
const MAX_BROWSER_RECORDING_SECONDS = 1800;
const MIN_BROWSER_RECORDING_SECONDS = 0.5;
const BROWSER_RECORDING_CHUNK_SECONDS = Number(window.__MRA_BROWSER_RECORDING_CHUNK_SECONDS || 10);
const BROWSER_RECORDING_MAX_RETRY_ATTEMPTS = 8;
const BROWSER_RECORDING_RETRY_BASE_MS = 1000;
const BROWSER_RECORDING_RETRY_MAX_MS = 30000;
const BROWSER_RECORDING_DB_NAME = "medical-record-agent-recording-v2";
const BROWSER_RECORDING_DB_VERSION = 2;
const BROWSER_RECORDING_STORE = "chunks";
const BROWSER_RECORDING_CLEANUP_STORE = "recording_cleanups";

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
  { key: "INPUT", label: "1.开始问诊" },
  { key: "TRANSCRIBING", label: "2.智能转写" },
  { key: "GENERATE_RECORD", label: "3.生成病历" },
  { key: "DOCTOR_REVIEW", label: "4.医生审核" },
  { key: "EXPORT", label: "5.导出" },
];

const STATUS_TO_STEP = {
  CREATED: "INPUT",
  TRANSCRIBING: "TRANSCRIBING",
  TRANSCRIBED: "GENERATE_RECORD",
  EXTRACTING_FIELDS: "GENERATE_RECORD",
  GENERATING_DRAFT: "GENERATE_RECORD",
  SAFETY_CHECKING: "GENERATE_RECORD",
  WAITING_DOCTOR_REVIEW: "DOCTOR_REVIEW",
  doctor_review: "DOCTOR_REVIEW",
  FAILED: "GENERATE_RECORD",
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
  reviewed: "修改已保存",
  approved: "病历审核已完成",
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
  ["", "请选择角色"],
  ["医生", "医生"],
  ["患者", "患者"],
  ["陪同人员", "陪同人员"],
  ["其他", "其他"],
  ["待确认", "暂不确定"],
];
const FINAL_CLINICAL_ROLES = ["医生", "患者", "陪同人员", "其他"];
const PRODUCT_VIEWS = ["workbench", "encounter", "admin"];

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
    if (response.status === 401) {
      appState.authUser = null;
      appState.authStatus = "required";
      appState.authMessage = "登录已失效，请重新登录。";
      renderAuthPanel();
    }
    const detail = data.detail;
    if (typeof detail === "string") throw new Error(detail);
    const errorMessage = detail?.message
      || (Array.isArray(detail?.errors) ? detail.errors.join(" ") : "")
      || JSON.stringify(detail || data);
    const error = new Error(errorMessage);
    error.status = response.status;
    error.detail = detail || data;
    throw error;
  }
  return data;
}

async function refreshAuth() {
  try {
    const response = await fetch("/api/auth/me");
    if (!response.ok) {
      appState.authUser = null;
      appState.authStatus = "required";
      appState.authMessage = "";
      return null;
    }
    const user = await response.json();
    appState.authUser = user;
    appState.authStatus = "authenticated";
    appState.authMessage = "";
    return user;
  } catch (_error) {
    appState.authUser = null;
    appState.authStatus = "required";
    appState.authMessage = "无法连接登录服务。";
    return null;
  } finally {
    renderAuthPanel();
  }
}

function renderAuthPanel() {
  const panel = $("loginPanel");
  const label = $("authUserLabel");
  const logoutButton = $("logoutButton");
  const message = $("loginMessage");
  if (label) {
    label.textContent = appState.authUser
      ? `${appState.authUser.display_name || appState.authUser.username} · ${appState.authUser.role}`
      : "未登录";
  }
  if (logoutButton) logoutButton.hidden = !appState.authUser;
  if (panel) panel.hidden = appState.authStatus === "authenticated";
  if (message) message.textContent = appState.authMessage || "";
}

async function submitLogin(event) {
  event.preventDefault();
  const username = $("loginUsername")?.value?.trim();
  const password = $("loginPassword")?.value || "";
  if (!username || !password) {
    appState.authMessage = "请输入用户名和密码。";
    renderAuthPanel();
    return;
  }
  appState.authMessage = "正在登录...";
  renderAuthPanel();
  try {
    const response = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || "用户名或密码错误。");
    }
    appState.authUser = data.user;
    appState.authStatus = "authenticated";
    appState.authMessage = "";
    if (!productViewFromHash()) appState.productView = "workbench";
    renderAll();
    refreshEncounterWorklist().catch(reportActionError);
    refreshLlmStatus();
    showToast("登录成功");
  } catch (error) {
    appState.authUser = null;
    appState.authStatus = "required";
    appState.authMessage = error?.message || "登录失败。";
    renderAuthPanel();
  }
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST" });
  } finally {
    appState.authUser = null;
    appState.authStatus = "required";
    appState.authMessage = "已退出登录。";
    renderAll();
  }
}

async function refreshExportReadiness() {
  if (!appState.currentTaskId) return null;
  try {
    const readiness = await api(`/api/tasks/${appState.currentTaskId}/export-readiness`);
    appState.currentExportReadiness = readiness;
    if (readiness?.exports) {
      appState.currentExports = readiness.exports;
    }
    return readiness;
  } catch (error) {
    appState.currentExportReadiness = null;
    return null;
  }
}

function formatDateTime(value) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function productViewFromHash() {
  const raw = window.location.hash.replace(/^#\/?/, "").split(/[/?]/)[0];
  return PRODUCT_VIEWS.includes(raw) ? raw : "";
}

function setProductView(view, { updateHash = true } = {}) {
  const nextView = PRODUCT_VIEWS.includes(view) ? view : "workbench";
  appState.productView = nextView;
  if (updateHash && window.location.hash !== `#${nextView}`) {
    window.location.hash = nextView;
  }
  renderProductShell();
  if (nextView === "workbench" && appState.authUser) {
    refreshEncounterWorklist().catch(reportActionError);
  }
  if (nextView === "admin" && appState.authUser) {
    refreshAdminHome().catch(reportActionError);
  }
}

function renderProductShell() {
  const view = appState.authStatus === "authenticated" ? appState.productView : "workbench";
  document.querySelectorAll("[data-product-view]").forEach((element) => {
    element.hidden = element.dataset.productView !== view;
  });
  document.querySelectorAll("[data-product-view-target]").forEach((button) => {
    const active = button.dataset.productViewTarget === view;
    button.classList.toggle("active", active);
    button.setAttribute("aria-current", active ? "page" : "false");
  });
}

function encounterWorklistMarkup({ includeRevisions = true } = {}) {
  if (appState.encounterWorklistStatus === "loading") {
    return `<div class="empty-state">正在加载今日就诊...</div>`;
  }
  if (appState.encounterWorklistError) {
    return `<div class="safety-strip danger">${escapeHtml(appState.encounterWorklistError)}</div>`;
  }
  const items = appState.encounterWorklist || [];
  if (!items.length) {
    return `<div class="empty-state">暂无可恢复的就诊记录。</div>`;
  }
  const rows = items.map((item) => {
    const active = appState.currentEncounter?.id === item.id;
    const patient = item.patient_display_name || item.patient_deidentified_id || `Encounter ${item.id}`;
    const status = encounterStatusLabel(item.status || item.task_current_stage);
    return `
      <article class="encounter-worklist-item ${active ? "active" : ""}">
        <div>
          <strong>${escapeHtml(patient)}</strong>
          <span>${escapeHtml(item.patient_deidentified_id || "-")}</span>
          <small>更新 ${escapeHtml(formatDateTime(item.updated_at || item.created_at))} · 版本 ${escapeHtml(item.current_revision_id || "-")} · Task ${escapeHtml(item.task_id || "-")}</small>
        </div>
        <div class="encounter-worklist-actions">
          <span class="status-badge ${active ? "confirmed" : "neutral"}">${escapeHtml(status)}</span>
          <button type="button" data-restore-encounter="${escapeHtml(item.id)}">${active ? "已打开" : "继续编辑"}</button>
        </div>
      </article>
    `;
  }).join("");
  const revisions = appState.currentEncounter?.revisions || [];
  const revisionHistory = includeRevisions && revisions.length ? `
    <section class="encounter-revision-history">
      <h3>当前就诊版本</h3>
      ${revisions.map((revision) => `
        <div class="encounter-revision-row">
          <strong>v${escapeHtml(revision.revision_no || "-")}</strong>
          <span>${escapeHtml(revision.source || "-")} · ${escapeHtml(formatDateTime(revision.created_at))}</span>
        </div>
      `).join("")}
    </section>
  ` : "";
  return rows + revisionHistory;
}

function encounterStatusLabel(status) {
  const labels = {
    draft: "草稿",
    modified: "已修改",
    pending_review: "待审核",
    approved: "已批准",
    exported: "已导出",
  };
  return labels[status] || status || "未开始";
}

function renderEncounterWorklistPanel() {
  const list = $("encounterWorklist");
  const dashboardList = $("dashboardEncounterList");
  const drawerHtml = encounterWorklistMarkup({ includeRevisions: true });
  const dashboardHtml = encounterWorklistMarkup({ includeRevisions: false });
  if (list) list.innerHTML = drawerHtml;
  if (dashboardList) dashboardList.innerHTML = dashboardHtml;
  renderDashboardSummary();
}

async function refreshEncounterWorklist() {
  appState.encounterWorklistStatus = "loading";
  appState.encounterWorklistError = "";
  renderEncounterWorklistPanel();
  const query = $("encounterSearchInput")?.value?.trim() || "";
  const status = $("encounterStatusFilter")?.value || "";
  const mine = appState.authUser?.role === "admin" ? "false" : "true";
  const params = new URLSearchParams({ mine });
  if (query) params.set("q", query);
  if (status) params.set("status", status);
  try {
    const data = await api(`/api/encounters?${params.toString()}`);
    appState.encounterWorklist = data.encounters || [];
    appState.encounterWorklistStatus = "ready";
  } catch (error) {
    appState.encounterWorklist = [];
    appState.encounterWorklistStatus = "error";
    appState.encounterWorklistError = error?.message || "无法加载就诊列表";
  }
  renderEncounterWorklistPanel();
}

async function openEncounterWorklist() {
  openDrawer("encounterWorklistPanel", "今日就诊");
  await refreshEncounterWorklist();
}

function applyEncounterDetail(detail) {
  resetTaskState();
  appState.currentEncounter = detail;
  const task = detail?.task || null;
  const result = task?.result_json || {};
  appState.currentTask = task;
  appState.currentTaskId = task?.id || null;
  appState.taskStatus = task?.current_stage || task?.status || detail?.status || "draft";
  appState.currentRecordFields = result.fields || null;
  appState.currentDraft = result.draft || "";
  appState.currentSafetyCheck = result.safety_check || null;
  appState.currentQualityReport = result.quality_report || null;
  appState.currentExports = result.exports || null;
  appState.currentExportReadiness = null;
  appState.currentInputText = "";
}

async function restoreEncounter(encounterId) {
  if (!encounterId) return;
  setBusy(true, "正在恢复就诊草稿...");
  try {
    const detail = await api(`/api/encounters/${encodeURIComponent(encounterId)}`);
    applyEncounterDetail(detail);
    if (appState.currentTaskId) {
      await refreshTask(appState.currentTaskId, appState.currentTask);
      await refreshExportReadiness();
    }
    await refreshEncounterWorklist();
    closeDrawer();
    setProductView("encounter");
    showToast("已恢复就诊草稿");
  } catch (error) {
    reportActionError(error);
  } finally {
    setBusy(false);
    renderAll();
  }
}

function renderExportReadinessDetail(readiness = appState.currentExportReadiness) {
  const exports = appState.currentExports || readiness?.exports || null;
  const rows = [];
  if (readiness) {
    rows.push(readiness.ready ? "导出状态：可以导出。" : "导出状态：暂不可导出。");
    (readiness.errors || []).forEach((item) => rows.push(`阻断原因：${item}`));
    if (readiness.next_action) rows.push(`下一步：${readiness.next_action}`);
  } else {
    rows.push("导出状态：尚未获取导出就绪状态。");
  }

  const exportRows = exports
    ? Object.entries(exports).map(([key, value]) => `${key}：${value}`)
    : [];

  return detailSection("导出状态与文件", `
    <div class="detail-evidence-list">
      ${[...rows, ...exportRows].map((item) => `<div class="assist-evidence-quote">${escapeHtml(item)}</div>`).join("")}
    </div>
  `);
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

function renderDashboardSummary() {
  const doctor = appState.authUser
    ? `${appState.authUser.display_name || appState.authUser.username} · ${appState.authUser.role}`
    : "未登录";
  const encounter = appState.currentEncounter
    ? `${appState.currentEncounter.patient_display_name || appState.currentEncounter.patient_deidentified_id || `Encounter ${appState.currentEncounter.id}`}`
    : "未打开就诊";
  const task = STATUS_LABELS[appState.taskStatus] || appState.taskStatus || "等待输入";
  const recording = appState.browserRecordingStatus !== "idle"
    ? productRecordingStatusLabel()
    : (appState.asrConnectionStatus !== "idle" ? asrPhaseLabel() : "等待录音或文本输入");
  if ($("dashboardDoctorLabel")) $("dashboardDoctorLabel").textContent = doctor;
  if ($("dashboardEncounterLabel")) $("dashboardEncounterLabel").textContent = encounter;
  if ($("dashboardTaskStatusLabel")) $("dashboardTaskStatusLabel").textContent = task;
  if ($("dashboardRecordingLabel")) $("dashboardRecordingLabel").textContent = recording;
}

function productRecordingStatusLabel() {
  const labels = {
    idle: "等待录音",
    requesting: "请求麦克风",
    recording: "录音中",
    paused: "已暂停",
    finalizing: "合并音频中",
    recorded: "已录制，可试听",
    uploading: "转写启动中",
    error: "录音异常",
  };
  return labels[appState.browserRecordingStatus] || appState.browserRecordingStatus || "等待录音";
}

function renderAdminHome() {
  const usersPanel = $("adminUsersPanel");
  const runtimePanel = $("adminRuntimePanel");
  if (usersPanel) {
    if (appState.adminStatus === "loading") {
      usersPanel.innerHTML = `<div class="empty-state">正在加载用户...</div>`;
    } else if (appState.authUser?.role !== "admin") {
      usersPanel.innerHTML = `<div class="safety-strip warning"><strong>权限不足</strong><br>当前账号不是管理员，只能查看本人工作区。</div>`;
    } else if (appState.adminError) {
      usersPanel.innerHTML = `<div class="safety-strip danger">${escapeHtml(appState.adminError)}</div>`;
    } else if (!appState.adminUsers.length) {
      usersPanel.innerHTML = `<div class="empty-state">暂无用户数据。</div>`;
    } else {
      usersPanel.innerHTML = appState.adminUsers.map((user) => `
        <div class="admin-list-row">
          <strong>${escapeHtml(user.display_name || user.username)}</strong>
          <span>${escapeHtml(user.username)} · ${escapeHtml(user.role || "-")}</span>
        </div>
      `).join("");
    }
  }
  if (runtimePanel) {
    const runtime = appState.adminRuntimeStatus;
    if (appState.adminStatus === "loading" && !runtime) {
      runtimePanel.innerHTML = `<div class="empty-state">正在检查系统健康...</div>`;
    } else if (runtime) {
      const checks = runtime.checks && typeof runtime.checks === "object"
        ? Object.entries(runtime.checks).slice(0, 6)
        : [];
      runtimePanel.innerHTML = `
        <div class="admin-list-row">
          <strong>${escapeHtml(runtime.status || "unknown")}</strong>
          <span>ready=${escapeHtml(String(runtime.ready ?? "-"))}</span>
        </div>
        ${checks.map(([key, value]) => `
          <div class="admin-list-row">
            <strong>${escapeHtml(key)}</strong>
            <span>${escapeHtml(value?.status || JSON.stringify(value))}</span>
          </div>
        `).join("")}
      `;
    } else {
      runtimePanel.innerHTML = `<div class="empty-state">尚未检查运行状态。</div>`;
    }
  }
}

async function refreshAdminHome() {
  appState.adminStatus = "loading";
  appState.adminError = "";
  renderAdminHome();
  try {
    const [readyResult, usersResult] = await Promise.allSettled([
      api("/ready"),
      appState.authUser?.role === "admin" ? api("/api/auth/users") : Promise.resolve({ users: [] }),
    ]);
    if (readyResult.status === "fulfilled") {
      appState.adminRuntimeStatus = readyResult.value;
    } else {
      appState.adminRuntimeStatus = { status: "not_ready", ready: false, checks: { ready: { status: readyResult.reason?.message || "检查失败" } } };
    }
    if (usersResult.status === "fulfilled") {
      appState.adminUsers = usersResult.value.users || [];
    } else {
      appState.adminUsers = [];
      appState.adminError = usersResult.reason?.message || "无法加载用户列表。";
    }
    appState.adminStatus = "ready";
  } catch (error) {
    appState.adminStatus = "error";
    appState.adminError = error?.message || "管理后台状态加载失败。";
  }
  renderAdminHome();
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

function activeQualityReport() {
  return appState.currentQualityReport || appState.recordPreview?.quality_preview || null;
}

function activeExtractionInfo() {
  const preview = appState.recordPreview?.extraction_info;
  if (preview) return preview;
  const traceLlm = appState.currentAgentTrace?.llm;
  if (!traceLlm) return null;
  return {
    requested_provider: traceLlm.llm_provider || "mock",
    actual_provider: traceLlm.actual_provider || traceLlm.llm_provider || "mock",
    model: traceLlm.model || "mock-deterministic-extractor",
    fallback: Boolean(traceLlm.fallback),
    fallback_reason: traceLlm.fallback_reason || null,
    mode: traceLlm.mode || "demo",
    fallback_allowed: traceLlm.fallback_allowed ?? true,
    extraction_mode: "formal_record_generation",
  };
}

function fieldQualityLabel(key) {
  const quality = activeQualityReport();
  if (!quality) return "";
  const fieldQuality = (quality.field_quality || []).find((item) => item.key === key);
  if (fieldQuality) {
    const statusLabels = {
      complete: "质量可用",
      missing: "需补充",
      partial: "部分完成",
      conflicting: "证据冲突",
      low_confidence: "低置信度",
      evidence_missing: "证据不足",
      needs_doctor_review: "待医生确认",
    };
    return statusLabels[fieldQuality.status] || "需复核";
  }
  const low = quality.low_confidence_fields || [];
  if (low.some((item) => item.key === key)) return "低置信度";
  const evidenceMissing = quality.evidence_missing_fields || [];
  const labelMap = {
    chief_complaint: "主诉",
    present_illness: "现病史",
    previous_treatment: "既往处理",
    accompanying_symptoms: "伴随症状",
    past_history: "既往史",
    allergy_history: "过敏史",
    physical_exam: "查体",
  };
  if (evidenceMissing.includes(labelMap[key])) return "证据不足";
  if ((quality.missing_fields || []).includes(labelMap[key])) return "需补充";
  return "质量可用";
}

function fieldQualityBadgeClass(label) {
  if (label === "质量可用") return "confirmed";
  if (label === "需补充") return "missing";
  if (label === "部分完成") return "partial";
  if (label === "证据冲突") return "conflicting";
  if (label === "证据不足") return "warning";
  return "low";
}

function fieldQualityItem(key) {
  const quality = activeQualityReport();
  return (quality?.field_quality || []).find((item) => item.key === key) || null;
}

function fieldWeightClass(key) {
  if (["present_illness", "physical_exam", "treatment_plan"].includes(key)) return "weight-high";
  if (["past_history", "allergy_history"].includes(key)) return "weight-low";
  return "weight-medium";
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
    .filter((item) => item.status !== "missing" && item.value_preview)
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
  const extraction = activeExtractionInfo();
  const extractionText = extraction
    ? ` · 字段抽取：${extraction.actual_provider || "mock"} / ${extraction.model || "mock-deterministic-extractor"} / ${extraction.mode || "demo"}${extraction.fallback ? "（已降级）" : ""}`
    : "";
  return `实时预览，需医生确认 · ${stageLabel}${recognized}${extractionText}`;
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
  if (!button || !menu) return;
  button.textContent = "开始生成";
  const labels = {
    audio: "上传音频",
    text: "粘贴文本",
    record: "录音生成",
    mock: "Mock 演示",
  };
  menu.querySelectorAll("[data-input-method]").forEach((item) => {
    const method = item.dataset.inputMethod;
    if (labels[method]) item.textContent = labels[method];
  });
  button.classList.toggle("active", appState.inputMenuOpen);
  button.setAttribute("aria-expanded", appState.inputMenuOpen ? "true" : "false");
  menu.hidden = !appState.inputMenuOpen;
}

function renderDisplaySettingsMenu() {
  const button = $("displaySettingsButton");
  const menu = $("displaySettingsMenu");
  if (!button || !menu) return;
  button.classList.toggle("active", appState.settingsOpen);
  button.setAttribute("aria-expanded", appState.settingsOpen ? "true" : "false");
  menu.hidden = !appState.settingsOpen;
}

function closeDisplaySettingsMenu() {
  appState.settingsOpen = false;
  renderDisplaySettingsMenu();
}

function toggleDisplaySettingsMenu() {
  appState.settingsOpen = !appState.settingsOpen;
  if (appState.settingsOpen) appState.inputMenuOpen = false;
  renderInputMethodMenu();
  renderDisplaySettingsMenu();
}

function closeInputMethodMenu() {
  appState.inputMenuOpen = false;
  renderInputMethodMenu();
}

function toggleInputMethodMenu() {
  appState.inputMenuOpen = !appState.inputMenuOpen;
  if (appState.inputMenuOpen) appState.settingsOpen = false;
  renderInputMethodMenu();
  renderDisplaySettingsMenu();
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
    text = "请核对病历内容及鉴别诊断参考，完成医生审核后方可导出。";
  } else if (appState.currentDraft || appState.taskStatus === "GENERATING_DRAFT" || appState.taskStatus === "SAFETY_CHECKING") {
    text = "病历草稿已生成，请审核病历内容。";
  } else if (appState.taskStatus === "TRANSCRIBED" || appState.currentAsrResult) {
    text = roleReviewRequired() ? "说话人身份需要确认后才能生成病历。" : "对话已转写，说话人角色已自动识别。";
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
    return "GENERATE_RECORD";
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
      ? `仍有 ${pendingCount} 位说话人需要确认；已可靠识别的说话人不会重复要求确认。`
      : (roleQualityReasonText() || "身份确认已完成，请保存结果。");
    const resumeText = appState.pendingGenerateAfterRoleReview
      ? "保存后将自动继续生成病历。"
      : "保存后可继续生成病历。";
    return {
      tone: "warning",
      title: rolePending ? "请确认说话人身份" : "请保存身份确认",
      detail: `${pendingText}${resumeText}`,
      actions: [
        workflowAction({
          key: rolePending ? "open-role-review" : "save-role-review",
          label: appState.roleReviewSaving ? "保存中" : rolePending ? "确认说话人身份" : "保存身份确认",
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
      detail: "说话人角色已自动识别，可以用当前对话生成病历草稿。",
      actions: [
        workflowAction({ key: "generate-record", label: "生成病历", tone: "primary" }),
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
      title: "病历审核已完成，可以导出",
      detail: "导出前请确认鉴别诊断参考和安全校验提示已由医生审核。",
      actions: [
        workflowAction({ key: "export-record", label: "确认导出", tone: "primary" }),
      ],
    };
  }

  if (appState.currentRecordFields) {
    const missingText = risk.missing.length ? `缺失项：${risk.missing.join("、")}。` : "病历草稿已生成。";
    return {
      tone: risk.hasError ? "danger" : risk.hasRisk ? "warning" : "ready",
      title: "请审核病历内容",
      detail: `${missingText} 保存修改后完成病历审核，完成医生审核后方可导出。`,
      actions: [
        workflowAction({ key: "save-draft", label: "保存修改" }),
        workflowAction({ key: "confirm-fields", label: "完成病历审核", tone: "primary" }),
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
  closeDisplaySettingsMenu();
  $("drawerTitle").textContent = title;
  $("drawerBackdrop").classList.add("active");
  $("drawer").classList.add("active");
  $("drawer").setAttribute("aria-hidden", "false");
  document.querySelectorAll(".drawer-panel").forEach((panel) => panel.classList.remove("active"));
  $(panelId).classList.add("active");
}

function closeDrawer() {
  if (appState.browserRecordingStatus === "recording" || appState.browserRecordingStatus === "requesting") {
    cancelBrowserRecording({ silent: true });
  }
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
  $("patientName").textContent = appState.currentEncounter?.patient_display_name || "模拟患者";
  $("patientProfile").textContent = "女 / 32岁";
  $("sessionId").textContent = appState.currentTaskId
    ? `T-${appState.currentTaskId}`
    : appState.currentAsrSessionId
      ? `S-${appState.currentAsrSessionId.slice(0, 8)}`
      : appState.currentAudioId
        ? `A-${appState.currentAudioId}`
        : "未创建";
  $("recordingStatus").textContent = appState.currentEncounter?.id
    ? `就诊 ${appState.currentEncounter.id} · ${encounterStatusLabel(appState.currentEncounter.status)}`
    : appState.uploadedFilename
      || (appState.currentAudioId ? "音频已上传" : appState.currentInputText ? "输入方式：文本" : "未上传");
  $("topAsrEngineSelect").value = appState.selectedEngine;
  $("audioEngineSelect").value = appState.selectedEngine;
  const recordingEngineSelect = $("recordingEngineSelect");
  if (recordingEngineSelect) recordingEngineSelect.value = appState.selectedEngine;
  $("llmProvider").textContent = `${llm.provider} / ${llm.mode || "demo"}`;
  $("llmModel").textContent = llm.model;
  $("llmFallback").textContent = llm.fallbackLabel;
  $("reviewStatus").textContent = STATUS_LABELS[appState.taskStatus] || appState.taskStatus || "等待输入";
  renderAsrPrewarmStatus();
}

function renderBrowserRecordingPanel() {
  const statusLabel = $("browserRecordingStatusLabel");
  const timer = $("browserRecordingTimer");
  const startButton = $("startBrowserRecordingButton");
  const pauseButton = $("pauseBrowserRecordingButton");
  const resumeButton = $("resumeBrowserRecordingButton");
  const stopButton = $("stopBrowserRecordingButton");
  const cancelButton = $("cancelBrowserRecordingButton");
  const submitButton = $("submitBrowserRecordingButton");
  const retryButton = $("retryBrowserRecordingChunksButton");
  const preview = $("browserRecordingPreview");
  const chunkStatus = $("browserRecordingChunkStatus");
  const message = $("browserRecordingMessage");
  if (!statusLabel || !timer || !startButton || !pauseButton || !resumeButton || !stopButton || !cancelButton || !submitButton || !retryButton || !preview || !chunkStatus || !message) return;

  const statusLabels = {
    idle: "等待录音",
    requesting: "正在请求麦克风权限",
    recording: "正在录音",
    paused: "录音已暂停",
    finalizing: "正在准备试听",
    recorded: "录音已就绪",
    uploading: "正在生成病历",
    error: "录音异常",
  };
  const isRecording = appState.browserRecordingStatus === "recording";
  const isPaused = appState.browserRecordingStatus === "paused";
  const isRequesting = appState.browserRecordingStatus === "requesting";
  const isUploading = ["uploading", "finalizing"].includes(appState.browserRecordingStatus);
  const hasQueuedChunks = Boolean(appState.browserRecordingSessionId && (appState.browserRecordingChunkIndex > 0 || appState.browserRecordingRecordedChunks > 0));
  const hasFailedChunks = Boolean(appState.browserRecordingPendingChunks > 0 || appState.browserRecordingRetryStatus);
  statusLabel.textContent = statusLabels[appState.browserRecordingStatus] || statusLabels.idle;
  timer.textContent = formatRelativeTime(appState.browserRecordingElapsedSeconds);
  startButton.disabled = appState.busy || isRequesting || isRecording || isUploading;
  pauseButton.disabled = !isRecording || isUploading;
  resumeButton.disabled = !isPaused || isUploading;
  stopButton.disabled = !(isRecording || isPaused);
  cancelButton.disabled = isUploading || (appState.browserRecordingStatus === "idle" && !hasQueuedChunks && !appState.browserRecordingFinalized);
  submitButton.disabled = appState.busy || isUploading || !appState.browserRecordingFinalized || hasFailedChunks || appState.browserRecordingRecovering;
  retryButton.disabled = appState.browserRecordingUploadInFlight || !appState.browserRecordingSessionId || !hasFailedChunks;
  preview.style.display = appState.browserRecordingObjectUrl ? "block" : "none";
  chunkStatus.textContent = appState.browserRecordingChunkStatus || "";
  message.textContent = appState.browserRecordingMessage || "";
  message.classList.toggle("error", appState.browserRecordingStatus === "error");
}

function renderAsrPrewarmStatus() {
  const target = $("asrModelStatus");
  const settingsTarget = $("settingsAsrModelStatus");
  if (!target && !settingsTarget) return;
  const status = appState.asrPrewarmStatus?.status || "idle";
  let label = "按需加载";
  let tone = "neutral";
  if (appState.selectedEngine !== "funasr") {
    label = "切换后按需加载";
  } else if (status === "warming") {
    label = "模型准备中";
    tone = "warning";
  } else if (status === "ready") {
    label = "模型已就绪";
    tone = "ok";
  } else if (status === "failed") {
    label = "预热失败，可用 Mock";
    tone = "danger";
  } else if (status === "idle") {
    label = "启动后自动预热";
  }
  [target, settingsTarget].filter(Boolean).forEach((node) => {
    node.textContent = label;
    node.className = `model-status ${tone}`;
    node.title = appState.asrPrewarmStatus?.last_error || "";
  });
}

async function refreshAsrPrewarmStatus() {
  try {
    const status = await api("/api/asr/prewarm/status");
    appState.asrPrewarmStatus = status;
    appState.asrPrewarmCheckedAt = new Date().toISOString();
  } catch (error) {
    appState.asrPrewarmStatus = { status: "failed", last_error: error.message || String(error) };
  }
  renderPatientBar();
  return appState.asrPrewarmStatus;
}

function startAsrPrewarmPolling() {
  if (appState.asrPrewarmTimer) {
    clearInterval(appState.asrPrewarmTimer);
  }
  refreshAsrPrewarmStatus();
  appState.asrPrewarmTimer = setInterval(refreshAsrPrewarmStatus, 8000);
}

function llmDisplayState() {
  const extraction = activeExtractionInfo();
  const traceLlm = appState.currentAgentTrace?.llm;
  const status = appState.currentLlmStatus || {};
  const provider = extraction?.requested_provider || traceLlm?.llm_provider || status.provider || "mock";
  const model = extraction?.model || traceLlm?.model || status.model || "mock-deterministic-extractor";
  const mode = extraction?.mode || traceLlm?.mode || status.mode || "demo";
  const fallback = extraction?.fallback ?? traceLlm?.fallback ?? status.fallback ?? false;
  const checked = status.checked ?? Boolean(traceLlm);
  const configured = status.configured ?? true;
  let fallbackLabel = "否";
  if (!configured || fallback) {
    fallbackLabel = `是：${extraction?.actual_provider || status.fallback_provider || traceLlm?.actual_provider || "mock"}`;
  } else if (!checked && provider !== "mock") {
    fallbackLabel = "未测试";
  }
  return {
    provider,
    model,
    mode,
    fallback,
    fallbackLabel,
    fallback_reason: extraction?.fallback_reason || traceLlm?.fallback_reason || status.fallback_reason || null,
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
  if (field.status === "partial") return { key: "partial", label: "部分完成" };
  if (field.status === "conflicting") return { key: "conflicting", label: "证据冲突" };
  if (field.confirmed_by_doctor) return { key: "confirmed", label: "已确认" };
  if (typeof field.confidence === "number" && field.confidence < 0.7) return { key: "low", label: "低置信度" };
  return { key: "confirmed", label: "已确认" };
}

function fieldValue(fields, key) {
  if (key === "treatment_plan") {
    return previewTreatmentText()
      || (activeDraftText() ? "暂无明确处理建议，需医生结合问诊、查体和检查结果确认。" : "待医生补充处理建议");
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
    return evidence.length ? evidence.join("\n") : "暂无鉴别诊断参考证据，需医生结合原始转写复核。";
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
  if (diagnosis.confidence == null) return "规则匹配度待评估";
  return `规则匹配度 ${Math.round(Number(diagnosis.confidence) * 100)}%`;
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
  const ruleParts = appState.viewMode === "debug"
    ? [diagnosis.rule_id, diagnosisConfidence(diagnosis)]
    : [diagnosisConfidence(diagnosis)];
  const ruleText = ruleParts.filter(Boolean).join(" · ");
  const details = [
    renderDiagnosisDetailLine("规则匹配", ruleText),
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
            <div class="detail-kv"><span>规则匹配度</span><strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong></div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
          `)}
        `).join("")
      : `<div class="empty-state">暂无初步诊断。生成病历后会显示鉴别诊断参考摘要，需医生判断。</div>`;
  }
  const field = fields[key] || null;
  const status = fieldStatus(field, key);
  const confidence = key === "treatment_plan" ? null : field?.confidence;
  const qualityItem = fieldQualityItem(key);
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
    ${qualityItem ? detailSection("质量判断", `
      <div class="detail-kv"><span>质量状态</span><strong>${escapeHtml(fieldQualityLabel(key))}</strong></div>
      <div class="detail-kv"><span>证据数量</span><strong>${escapeHtml(String(qualityItem.evidence_count ?? 0))}</strong></div>
      <div class="detail-text">${escapeHtml(qualityItem.reason || qualityItem.suggested_action || "暂无进一步说明。")}</div>
    `) : ""}
    ${detailSection("证据片段", `<div class="detail-text">${escapeHtml(fieldEvidence(field, key))}</div>`)}
  `;
}

function renderDiagnosisDetailContent(index) {
  const diagnosis = activeRecordFields()?.candidate_diagnoses?.[index];
  if (!diagnosis) return `<div class="empty-state">暂无鉴别诊断参考详情。</div>`;
  const diagnosisQuality = activeQualityReport()?.candidate_diagnosis_status?.diagnosis_quality?.[index] || null;
  return `
    ${detailSection(diagnosis.name || "鉴别诊断参考", `
      <div class="detail-kv">
        <span>状态</span>
        <strong>${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong>
      </div>
      <div class="detail-kv">
        <span>规则匹配度</span>
        <strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong>
      </div>
      <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
    `)}
    ${diagnosisQuality ? detailSection("质量判断", `
      <div class="detail-kv"><span>质量状态</span><strong>${escapeHtml(diagnosisQuality.status === "complete" ? "质量可用" : "需完善")}</strong></div>
      <div class="detail-kv"><span>医生确认</span><strong>${escapeHtml(diagnosisQuality.doctor_confirmation_required ? "仍需确认" : "已满足边界")}</strong></div>
      <div class="detail-text">${escapeHtml(
        diagnosisQuality.missing?.length
          ? `缺项：${diagnosisQuality.missing.join("、")}。${diagnosisQuality.suggested_action || ""}`
          : (diagnosisQuality.suggested_action || "鉴别诊断参考结构完整，等待医生判断。")
      )}</div>
    `) : ""}
    ${detailSection("诊断证据", `<div class="detail-text">${escapeHtml((diagnosis.evidence || []).map((item) => item.text).filter(Boolean).join("\n") || "暂无鉴别诊断参考证据。")}</div>`)}
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
    ? detailSection("鉴别诊断参考", diagnoses.map((diagnosis, index) => `
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
    const qualityLabel = fieldQualityLabel(key);
    const confidence = appState.viewMode === "doctor"
      ? draftFieldConfidence(fields, key)
      : key === "treatment_plan" ? "需医生复核" : fields?.[key]?.confidence == null ? "需医生复核" : `置信度 ${Math.round(fields[key].confidence * 100)}%`;
    const compactStatusText = [status.label, qualityLabel].filter(Boolean).join(" · ");
    const meta = fields
      ? appState.viewMode === "doctor"
        ? `
        <div class="field-meta compact-field-meta">
          ${detailButton(`field:${key}`, "查看原文证据")}
        </div>
        `
        : `
        <div class="field-meta">
          <span class="confidence">${escapeHtml(confidence)}</span>
          <button type="button" data-evidence-toggle>证据</button>
          ${detailButton(`field:${key}`, "查看原文证据")}
        </div>
        <div class="field-evidence">${escapeHtml(evidence)}</div>
    `
      : "";
    return `
      <article class="field-card ${status.key} ${fieldWeightClass(key)} ${appState.viewMode === "doctor" ? "doctor-summary-card" : ""} ${value ? "has-value" : "is-empty"}" data-field="${key}">
        <div class="field-head">
          <span class="field-title">${escapeHtml(title)}</span>
          ${appState.viewMode === "doctor"
            ? `<span class="field-status-inline"><span class="status-dot-label ${status.key}" title="${escapeHtml(compactStatusText || "待生成")}"></span><span class="field-status-text">${escapeHtml(status.label)}</span></span>`
            : `<span class="status-badge ${status.key}">${escapeHtml(status.label)}</span>${qualityLabel ? `<span class="status-badge ${fieldQualityBadgeClass(qualityLabel)}">${escapeHtml(qualityLabel)}</span>` : ""}`}
        </div>
        <div class="field-value">${value ? escapeHtml(value) : `<span class="draft-placeholder" aria-hidden="true">&nbsp;</span>`}</div>
        ${meta}
      </article>
    `;
  }).join("");

  const diagnoses = appState.viewMode === "doctor" ? "" : (fields?.candidate_diagnoses || []).map((diagnosis, index) => `
    <article class="field-card candidate" data-field="diagnosis-${index}">
      <div class="field-head">
        <span class="field-title">鉴别诊断参考</span>
        <span class="status-badge candidate">${diagnosis.confirmed_by_doctor ? "已确认" : "候选待确认"}</span>
      </div>
      <div class="field-value">${escapeHtml(diagnosis.name || "未命名诊断")}</div>
      <div class="field-meta">
        <span class="confidence">${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</span>
        <button type="button" data-evidence-toggle>证据</button>
        ${detailButton(`diagnosis:${index}`, "详情")}
      </div>
      <div class="field-evidence">${escapeHtml((diagnosis.evidence || []).map((item) => item.text).join("\n") || "暂无鉴别诊断参考证据。")}</div>
    </article>
  `).join("");
  const hiddenFieldCount = Math.max(0, FIELD_DEFS.length - displayFieldDefs.length);
  const summaryFooter = fields && (hiddenFieldCount || appState.viewMode === "doctor")
    ? `<button type="button" class="inline-more-button" data-open-detail="fields:all">完整详情</button>`
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
  if (shouldShowSpeakerAlias(segment)) return "speaker";
  if (isTrustedClinicalRole(segment)) {
    if (segment.role === "医生") return "doctor";
    if (segment.role === "患者") return "patient";
    return "other";
  }
  if (segment.speaker_id || segment.speaker) return "speaker";
  if (segment.role === "医生") return "doctor";
  if (segment.role === "患者") return "patient";
  if (segment.role === "陪同人员") return "other";
  if (segment.role === "其他") return "other";
  const raw = `${segment.speaker || ""} ${line}`.toLowerCase();
  if (raw.includes("医生") || raw.includes("doctor")) return "doctor";
  if (raw.includes("患者") || raw.includes("patient")) return "patient";
  if (raw.includes("其他") || raw.includes("other")) return "other";
  const inferred = inferLowConfidenceRole(line);
  if (inferred === "医生") return "doctor";
  if (inferred === "患者") return "patient";
  return "unknown";
}

function isFinalClinicalRole(role) {
  return FINAL_CLINICAL_ROLES.includes(role);
}

function hasSpeakerIdentity(segment = {}) {
  return Boolean(segment.speaker_id || segment.speaker);
}

function isManualRoleSource(segment = {}) {
  return String(segment.role_source || "").startsWith("manual") || Boolean(segment.reviewed_by_doctor);
}

function isTrustedClinicalRole(segment = {}) {
  if (!isFinalClinicalRole(segment.role)) return false;
  if (isManualRoleSource(segment)) return true;
  if (segment.needs_review) return false;
  if (!hasSpeakerIdentity(segment)) return true;
  const confidence = Number(segment.role_confidence);
  if (!Number.isFinite(confidence)) return false;
  return confidence >= ROLE_DISPLAY_CONFIDENCE_THRESHOLD;
}

function shouldShowSpeakerAlias(segment = {}) {
  return hasSpeakerIdentity(segment) && !isTrustedClinicalRole(segment);
}

function speakerAliasLabelForId(speakerId) {
  const id = String(speakerId || "").trim();
  if (!id) return "说话人 A";
  const segments = currentReviewSegments();
  const ids = [];
  segments.forEach((segment) => {
    const identity = segment.speaker_id || segment.speaker;
    if (identity && !ids.includes(identity)) ids.push(identity);
  });
  if (!ids.includes(id)) ids.push(id);
  const index = Math.max(0, ids.indexOf(id));
  return `说话人 ${String.fromCharCode(65 + Math.min(index, 25))}`;
}

function roleLabelFromSegment(segment = {}, fallbackLine = "") {
  if (isTrustedClinicalRole(segment)) return segment.role;
  const speaker = classifySpeaker(fallbackLine, segment);
  if (speaker === "doctor") return "医生";
  if (speaker === "patient") return "患者";
  if (speaker === "other") return segment.role === "陪同人员" ? "陪同人员" : "其他";
  if (speaker === "speaker") return speakerAliasLabelForId(segment.speaker_id || segment.speaker);
  return "";
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
  // ASR speaker roles are assigned once per acoustic speaker on the backend.
  // Per-sentence text guesses caused role oscillation and are intentionally disabled.
  return segment;
}

function transcriptRoleNeedsReview(segment = {}, label = "") {
  if (isManualRoleSource(segment)) return false;
  if (segment.needs_review || label === "待确认") return true;
  return shouldShowSpeakerAlias(segment);
}

function speakerAssignmentNeedsReview(item = {}) {
  if (item.requires_confirmation || !item.role) return true;
  if (item.role === "待确认") return true;
  if (String(item.source || "").startsWith("manual")) return false;
  const confidence = Number(item.confidence);
  return Number.isFinite(confidence) && confidence < ROLE_DISPLAY_CONFIDENCE_THRESHOLD;
}

function isClinicalRole(role) {
  return FINAL_CLINICAL_ROLES.includes(role);
}

function stableAsrSegments(asr = appState.currentAsrResult) {
  const segments = asr?.segments?.length ? asr.segments : currentReviewSegments();
  return segments.filter((segment) => !segment.provisional);
}

function segmentSpeakerId(segment = {}) {
  return segment.speaker_id || segment.speaker || "";
}

function speakerRolesComplete(asr = appState.currentAsrResult) {
  const segments = stableAsrSegments(asr);
  const assignments = asr?.speaker_assignments || appState.speakerAssignments || [];
  const assignmentBySpeaker = new Map(assignments.map((item) => [item.speaker_id, item]));
  const speakerIds = new Set(segments.map(segmentSpeakerId).filter(Boolean));

  if (speakerIds.size) {
    for (const speakerId of speakerIds) {
      const assignmentRole = assignmentBySpeaker.get(speakerId)?.role;
      const segmentRoles = segments
        .filter((segment) => segmentSpeakerId(segment) === speakerId)
        .map((segment) => segment.role)
        .filter(Boolean);
      if (!isClinicalRole(assignmentRole) && !segmentRoles.some(isClinicalRole)) return false;
    }
    return true;
  }

  if (assignments.length) {
    return assignments.every((item) => isClinicalRole(item.role));
  }

  return segments.length ? segments.every((segment) => isClinicalRole(segment.role)) : false;
}

function roleQualityStatus(asr = appState.currentAsrResult) {
  return asr?.role_quality?.status || "";
}

function roleQualityPassed(asr = appState.currentAsrResult) {
  return roleQualityStatus(asr) === "passed" && speakerRolesComplete(asr);
}

function roleQualityNeedsIdentityReview(asr = appState.currentAsrResult) {
  return ["needs_review", "blocked"].includes(roleQualityStatus(asr));
}

function roleQualityReasonText(asr = appState.currentAsrResult) {
  const quality = asr?.role_quality;
  if (!quality) return "";
  const reasons = quality.reasons || [];
  if (reasons.length) return reasons.join("；");
  if (quality.status === "blocked") return "说话人角色质量门禁未通过。";
  if (quality.status === "needs_review") return "说话人身份需要医生确认。";
  return "说话人角色已自动识别。";
}

function pendingSpeakerAssignments() {
  const assignments = appState.currentAsrResult?.speaker_assignments || appState.speakerAssignments || [];
  const pending = assignments.filter((item) => speakerAssignmentNeedsReview(item));
  const pendingBySpeaker = new Map(pending.map((item) => [item.speaker_id, item]));
  const quality = appState.currentAsrResult?.role_quality || {};
  [
    ...(quality.unresolved_assignments || []),
    ...(quality.low_confidence_clinical_roles || []),
    ...(quality.unmapped_speakers || []),
  ].forEach((item) => {
    const speakerId = item?.speaker_id;
    if (!speakerId || pendingBySpeaker.has(speakerId)) return;
    const assignment = assignments.find((candidate) => candidate.speaker_id === speakerId) || {};
    pendingBySpeaker.set(speakerId, {
      ...assignment,
      ...item,
      speaker_id: speakerId,
      requires_confirmation: true,
    });
  });
  return [...pendingBySpeaker.values()];
}

function speakerClassFromRole(role) {
  if (role === "医生") return "doctor";
  if (role === "患者") return "patient";
  if (role === "陪同人员") return "other";
  if (role === "其他") return "other";
  if (String(role || "").startsWith("说话人 ")) return "speaker";
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
  const aliases = new Map();
  return segments
    .map((segment) => {
      const speakerId = segment.speaker_id || segment.speaker || "speaker_unassigned";
      if (!aliases.has(speakerId)) aliases.set(speakerId, `说话人 ${String.fromCharCode(65 + Math.min(aliases.size, 25))}`);
      return `[${segment.role || aliases.get(speakerId)}] ${segment.text || ""}`;
    })
    .join("\n");
}

function textFromSegments(segments = []) {
  return segments.map((segment) => segment.text || "").filter(Boolean).join("\n");
}

function currentReviewSegments() {
  const segments = appState.currentAsrResult?.segments?.length
    ? appState.currentAsrResult.segments
    : appState.liveTranscriptSegments;
  return segments.filter((segment) => !segment.provisional);
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

function upsertProvisionalTranscriptSegment(segment) {
  appState.provisionalTranscriptSegments = mergeTranscriptSegments(
    [segment],
    appState.provisionalTranscriptSegments,
  );
}

function latestProvisionalTranscriptText() {
  return appState.provisionalTranscriptSegments
    .slice(-3)
    .map((segment) => compactSegmentText(segment))
    .filter(Boolean)
    .join(" ");
}

function liveConversationTextForPreview() {
  const segments = currentReviewSegments();
  if (segments.length) {
    const aliases = new Map();
    return segments
      .map((segment) => {
        const displaySegment = segmentWithInferredRole(segment);
        const speakerId = displaySegment.speaker_id || displaySegment.speaker || "speaker_0";
        if (!aliases.has(speakerId)) aliases.set(speakerId, `说话人 ${String.fromCharCode(65 + Math.min(aliases.size, 25))}`);
        const role = displaySegment.role || aliases.get(speakerId);
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

function hasClinicalPreviewSignal(text) {
  return /(发烧|发热|体温|℃|°C|\d+\s*度|头痛|头疼|脑袋疼|咳嗽|布洛芬|退热|退烧|没有|否认)/i.test(String(text || ""));
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
  if (roleReviewRequired()) return;
  const segments = currentReviewSegments().filter((segment) => !segment.provisional).map(segmentWithInferredRole);
  const text = liveConversationTextForPreview();
  if (
    !force
    && segments.length < RECORD_PREVIEW_MIN_SEGMENTS
    && text.length < RECORD_PREVIEW_MIN_CHARS
    && !hasClinicalPreviewSignal(text)
  ) return;
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
    .replace(/\s*(\[(?:医生|患者|陪同人员|其他|doctor|patient|待校正|待确认)\])/gi, "\n$1")
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
      text: line.replace(/^\[(医生|患者|陪同人员|其他|doctor|patient|待校正|待确认)\]\s*/i, ""),
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
        needsReview: transcriptRoleNeedsReview(displaySegment, label),
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
        needsReview: transcriptRoleNeedsReview(displaySegment, label),
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

function renderSpeakerMergeOptions(sourceSpeakerId, groups = []) {
  const targets = groups.filter((group) => group.speakerId && group.speakerId !== sourceSpeakerId);
  return [
    `<option value="">合并到...</option>`,
    ...targets.map((group) => {
      const label = `${group.displayName}${group.role ? `（${group.role}）` : ""} · ${group.count} 段`;
      return `<option value="${escapeHtml(group.speakerId)}">${escapeHtml(label)}</option>`;
    }),
  ].join("");
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
    } else if (["created", "recording", "finalizing", "recorded"].includes(session.status)) {
      const localRows = await listBrowserRecordingQueueEntries(session.session_id).catch(() => []);
      if (session.status === "created" && !localRows.length) {
        renderAll();
        return;
      }
      appState.browserRecordingSessionId = session.session_id;
      const chunkStatus = await reconcileBrowserRecordingQueue(session.session_id);
      appState.browserRecordingStatus = chunkStatus?.status === "recorded" ? "recorded" : "paused";
      appState.browserRecordingChunkIndex = Number(chunkStatus?.next_chunk_index || 0);
      appState.browserRecordingRecordedChunks = Math.max(
        Number(chunkStatus?.chunk_count || 0),
        appState.browserRecordingRecordedChunks || 0,
      );
      if (chunkStatus?.status === "recorded" && chunkStatus.audio_id) {
        appState.browserRecordingFinalized = chunkStatus;
        appState.browserRecordingObjectUrl = chunkStatus.media_url || `/api/audio/${encodeURIComponent(chunkStatus.audio_id)}/media`;
        const preview = $("browserRecordingPreview");
        if (preview) {
          preview.src = appState.browserRecordingObjectUrl;
          preview.load();
        }
        appState.browserRecordingMessage = "录音会话已恢复，可试听并继续生成病历。";
      } else if (appState.browserRecordingMissingChunks?.length) {
        appState.browserRecordingMessage = `录音会话缺少第 ${appState.browserRecordingMissingChunks.join(", ")} 段，本地也没有可补传数据。`;
        appState.browserRecordingStatus = "error";
      } else {
        appState.browserRecordingMessage = "录音会话已恢复，可点击“恢复”继续录音，或停止后准备试听。";
      }
      updateBrowserRecordingChunkStatusText();
      appState.taskStatus = "CREATED";
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

function buildSpeakerAliasMap(rows) {
  const aliases = new Map();
  rows.forEach((row) => {
    if (row.speakerId && !aliases.has(row.speakerId)) {
      aliases.set(row.speakerId, String.fromCharCode(65 + Math.min(aliases.size, 25)));
    }
  });
  return aliases;
}

function speakerDisplayLabel(row, speakerCount, speakerAliases = null) {
  if (!row.speakerId) return row.label || "说话人 A";
  const match = String(row.speakerId).match(/(\d+)$/);
  const suffix = speakerAliases?.get(row.speakerId) || (match
    ? String.fromCharCode(65 + Math.min(Number(match[1]), 25))
    : String(row.speakerId).replace(/^speaker[-_]?|^spk/i, "").toUpperCase());
  const speakerName = `说话人 ${suffix || row.speakerId}`;
  if (String(row.label || "").startsWith("说话人 ")) return row.label;
  return row.label ? `${row.label} · ${suffix || row.speakerId}` : speakerName;
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
      ? `<button type="button" class="secondary-action" data-save-role-review ${appState.roleReviewSaving ? "disabled" : ""}>保存身份确认</button>`
      : canGenerateFromTranscript
        ? `<button type="button" class="primary-action" data-generate-from-transcript>用校正文本生成病历</button>`
        : ""
    : "";
  const detailAction = rows.length ? detailButton("transcript:all", "查看全部转写") : "";
  const reviewText = reviewable
    ? unreviewedCount
      ? "需确认说话人身份"
      : "说话人角色已自动识别"
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
    $("transcriptList").innerHTML = `<div class="empty-state transcript-empty">暂无对话转写。</div>`;
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
  const speakerAliases = buildSpeakerAliasMap(rows);
  const provisionalText = latestProvisionalTranscriptText();
  const streamingEmptyBlock = isStreaming && !rows.length
    ? `
      <div class="empty-state transcript-empty transcribing-empty" aria-live="polite">
        <div class="transcribing-empty-spinner" aria-hidden="true"></div>
        <div class="transcribing-empty-copy">
          <strong>${escapeHtml(asrPhaseLabel())}</strong>
          <span>${appState.asrProgressKind === "actual" ? `已处理 ${formatRelativeTime(appState.asrProcessedAudioSeconds)} / ${formatRelativeTime(appState.asrAudioDurationSeconds)}` : "正在准备本地模型"}</span>
           ${provisionalText
            ? `<p class="provisional-transcript-text">${escapeHtml(provisionalText)}</p><small>稳定句子会自动进入列表。</small>`
            : `<small>稳定句子会自动显示在这里。</small>`}
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
          <span class="transcript-role-tag ${escapeHtml(item.speaker)}">【${escapeHtml(speakerDisplayLabel(item, speakerCount, speakerAliases))}】</span>
          <span class="transcript-row-text">${escapeHtml(item.text || "（无文本）")}</span>
          <button type="button" class="transcript-row-link" data-open-detail="transcript:${item.index}" data-busy-allowed="true">详情</button>
        </div>
      `).join("")}
    </div>
  `;
}

function renderTranscriptDetailContent(target = "all") {
  const rows = transcriptRows();
  if (!rows.length) return `<div class="empty-state">暂无对话转写。</div>`;
  const selectedIndex = Number(target);
  const identityReviewMode = target === "role-review";
  const canEdit = Boolean(appState.currentAsrSessionId && appState.currentAsrResult?.segments?.length);
  const unreviewedCount = roleReviewPendingCount();
  const canGenerateFromTranscript = Boolean(appState.currentAsrResult && !appState.currentTaskId && !appState.currentRecordFields);
  const speakerGroups = transcriptSpeakerGroups(rows);
  const pendingSpeakerIds = new Set(pendingSpeakerAssignments().map((item) => item.speaker_id));
  const visibleSpeakerGroups = identityReviewMode
    ? speakerGroups.filter((group) => pendingSpeakerIds.has(group.speakerId) || !group.role)
    : speakerGroups;
  const speakerAliases = buildSpeakerAliasMap(rows);
  const reviewHint = canEdit
    ? appState.roleReviewDirty
      ? "存在未保存校正，保存后会用于后续病历生成。"
      : identityReviewMode
        ? "只需确认不确定的说话人；已可靠识别的说话人不会重复要求确认。"
        : "可在这里更正说话人身份和原文，默认列表保持只读。"
    : "当前内容只读。";
  const undoMergeButton = canEdit && appState.lastSpeakerMergeSnapshot
    ? `<button type="button" class="secondary-action" data-undo-speaker-merge>撤销本页合并</button>`
    : "";
  const actionButtons = `
    <div class="transcript-review-actions">
      ${undoMergeButton}
      ${canEdit ? `<button type="button" class="primary-action" data-save-role-review ${appState.roleReviewSaving ? "disabled" : ""}>${appState.roleReviewSaving ? "保存中" : identityReviewMode ? "保存身份确认" : "保存更正"}</button>` : ""}
      ${canGenerateFromTranscript ? `<button type="button" class="secondary-action" data-generate-from-transcript>用当前转写生成病历</button>` : ""}
    </div>
  `;
  return `
    ${detailSection("转写状态", `
      <div class="detail-kv"><span>引擎</span><strong>${escapeHtml(appState.currentAsrResult?.engine || appState.selectedEngine || "ASR")}</strong></div>
      <div class="detail-kv"><span>分段</span><strong>${rows.length} 条</strong></div>
      <div class="detail-kv"><span>说话人身份</span><strong>${escapeHtml(canEdit ? (unreviewedCount ? `${unreviewedCount} 位说话人需确认` : "说话人角色已自动识别") : "只读")}</strong></div>
      <p class="detail-note">${escapeHtml(reviewHint)}</p>
    `)}
    ${canEdit && visibleSpeakerGroups.length ? detailSection(identityReviewMode ? "需要确认的说话人" : "按说话人统一更正", `
      <p class="detail-note">${identityReviewMode ? "确认后会同步到该说话人的全部发言，并用于继续生成病历。" : "一次修改会同步到该说话人的全部发言。"}</p>
      <div class="speaker-role-groups">
        ${visibleSpeakerGroups.map((group) => `
          <div class="speaker-role-group">
            <span><strong>${escapeHtml(group.displayName)}</strong><small>${escapeHtml(group.speakerId)} · ${group.count} 段</small></span>
            <select data-speaker-role-select data-speaker-id="${escapeHtml(group.speakerId)}" aria-label="设置${escapeHtml(group.displayName)}角色">
              ${renderRoleOptions(group.role)}
            </select>
            <div class="speaker-merge-controls">
              <select data-speaker-merge-target data-source-speaker-id="${escapeHtml(group.speakerId)}" aria-label="选择${escapeHtml(group.displayName)}合并目标">
                ${renderSpeakerMergeOptions(group.speakerId, speakerGroups)}
              </select>
              <button type="button" class="secondary-action" data-speaker-merge-source="${escapeHtml(group.speakerId)}">合并</button>
            </div>
          </div>
        `).join("")}
      </div>
    `) : identityReviewMode ? detailSection("身份确认", `<div class="empty-state">当前没有需要人工确认的说话人。</div>`) : ""}
    ${detailSection(identityReviewMode ? "更正转写（可选）" : "身份与文本更正", `
      <div class="transcript-review-list">
        ${rows.map((item) => `
          <div class="transcript-review-row ${Number.isFinite(selectedIndex) && selectedIndex === item.index ? "focus" : ""}" data-segment-index="${item.index}">
            <div class="transcript-review-meta">
              <span class="transcript-row-time">${escapeHtml(item.time)}</span>
              <strong class="transcript-role-tag ${escapeHtml(item.speaker)}">【${escapeHtml(speakerDisplayLabel(item, speakerGroups.length, speakerAliases))}】</strong>
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
      if (span.text) evidence.push(`鉴别诊断参考 ${diagnosis.name}：${span.text}`);
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
      mode: llmStatus.mode || "demo",
      fallback_allowed: llmStatus.fallback_allowed ?? true,
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
        <div class="safety-strip ${llm.fallback ? "warning" : "success"}"><strong>LLM Provider</strong><br>${escapeHtml(llm.llm_provider || "mock")} / ${escapeHtml(llm.model || "mock-deterministic-extractor")} / ${escapeHtml(llm.mode || "demo")}</div>
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
          <strong>“保存修改到SQLite”会调用 <code>POST /api/tasks/{task_id}/review</code>。</strong>
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

function assistCard({ title, badgeClass = "neutral", badgeText = "", body = "", detailTarget = "", detailLabel = "详情" }) {
  return `
    <section class="doctor-assist-card">
      <div class="doctor-assist-card-head">
        <h3>${escapeHtml(title)}</h3>
        <div class="doctor-assist-card-actions">
          ${badgeText ? `<span class="status-badge ${badgeClass}">${escapeHtml(badgeText)}</span>` : ""}
          ${detailTarget ? detailButton(detailTarget, detailLabel) : ""}
        </div>
      </div>
      <div class="doctor-assist-card-body">${body}</div>
    </section>
  `;
}

function diagnosisEvidenceLine(diagnosis = {}) {
  return diagnosis.reason
    || (diagnosis.evidence || []).map((item) => item.text).filter(Boolean)[0]
    || "暂无匹配依据，需医生结合原始转写判断。";
}

function diagnosisRiskLine(diagnosis = {}) {
  return diagnosisList(diagnosis.risk_warnings)[0]
    || diagnosisList(diagnosis.suggested_checks)[0]
    || diagnosisList(diagnosis.follow_up_questions)[0]
    || "需结合查体、检查和病情变化继续判断。";
}

function renderCandidateDiagnosisCard(diagnoses) {
  if (!diagnoses.length) {
    return assistCard({
      title: "鉴别诊断参考",
      badgeClass: "confirmed",
      badgeText: "暂无",
      body: `<div class="empty-state">当前信息不足，完成关键补问后生成。</div>`,
    });
  }
  const preview = listPreview(diagnoses, 2);

  return assistCard({
    title: "鉴别诊断参考",
    badgeClass: "candidate",
    badgeText: "需医生判断",
    detailTarget: "assist:candidates",
    detailLabel: "查看完整依据",
    body: `
      <ol class="assist-number-list">
        ${preview.visible.map((diagnosis, index) => `
          <li>
            <span>${index + 1}</span>
            <div class="assist-diagnosis-summary">
              <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong>
              <em>${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</em>
              <p>依据：${escapeHtml(diagnosisEvidenceLine(diagnosis))}</p>
              <p>关注：${escapeHtml(diagnosisRiskLine(diagnosis))}</p>
            </div>
          </li>
        `).join("")}
      </ol>
      ${preview.hiddenCount ? `<div class="summary-note">另有 ${preview.hiddenCount} 条鉴别诊断参考，点击查看完整依据。</div>` : ""}
      <div class="summary-note">仅供鉴别诊断参考，需医生判断，不能作为已确诊结论。</div>
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
  const treatmentText = treatment?.value || treatment?.hint || previewTreatmentText() || "暂无处理建议。";
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
          <strong>${escapeHtml(suggestedChecks.slice(0, 3).join("、") || "待补充")}</strong>
        </div>
        <div>
          <span>用药提示</span>
          <strong>${escapeHtml(medicationNotes.slice(0, 3).join("、") || "需医生确认")}</strong>
        </div>
      </div>
    `,
  });
}

function renderEvidenceCard(evidence, diagnoses) {
  const diagnosisReasons = diagnoses
    .map((diagnosis) => diagnosis.reason ? `${diagnosis.name || "鉴别诊断参考"}：${diagnosis.reason}` : "")
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
      ? listPreview(items, 2).visible.map((item) => item.segmentId
        ? `<button type="button" class="assist-evidence-quote linked" data-evidence-segment-id="${escapeHtml(item.segmentId)}" ${item.startTime != null ? `data-evidence-start="${item.startTime}"` : ""}>${escapeHtml(item.text)}<span>播放证据</span></button>`
        : `<div class="assist-evidence-quote">${escapeHtml(item.text)}</div>`).join("")
        + (items.length > 2 ? `<div class="summary-note">另有 ${items.length - 2} 条证据，点击详情查看。</div>` : "")
      : `<div class="empty-state">暂无诊断证据。</div>`,
  });
}

function renderQualitySummaryCard() {
  const quality = activeQualityReport();
  if (!quality) {
    return assistCard({
      title: "病历质量摘要",
      badgeClass: "neutral",
      badgeText: "待生成",
      body: `<div class="empty-state">生成预览或正式病历后，将显示完整度、证据覆盖和下一步建议。</div>`,
    });
  }
  const percent = Math.round((quality.core_completeness || 0) * 100);
  const nextActions = quality.next_actions || [];
  const lowCount = (quality.low_confidence_fields || []).length;
  const evidenceMissingCount = (quality.evidence_missing_fields || []).length;
  const badgeClass = quality.ready_for_doctor_review ? "confirmed" : "missing";
  const badgeText = quality.ready_for_doctor_review ? "可审核" : "需复核";
  return assistCard({
    title: "病历质量摘要",
    badgeClass,
    badgeText,
    detailTarget: "assist:quality",
    body: `
      <div class="assist-mini-grid">
        <div><span>核心完整度</span><strong>${percent}%</strong></div>
        <div><span>证据覆盖</span><strong>${Math.round((quality.evidence_coverage || 0) * 100)}%</strong></div>
        <div><span>低置信度</span><strong>${lowCount} 项</strong></div>
        <div><span>证据不足</span><strong>${evidenceMissingCount} 项</strong></div>
      </div>
      <div class="assist-check-list">
        ${listPreview(nextActions, 3).visible.map((item) => `
          <div class="assist-check-row ${quality.ready_for_doctor_review ? "success" : "warning"}">
            <span></span>
            <strong>${escapeHtml(item)}</strong>
          </div>
        `).join("")}
      </div>
    `,
  });
}

function renderQualityStatusLine() {
  const quality = activeQualityReport();
  if (!quality) {
    return `
      <button type="button" class="assist-quality-line neutral" data-open-detail="assist:quality">
        <span>质量：待生成</span>
        <strong>详情</strong>
      </button>
    `;
  }
  const missingCount = (quality.missing_fields || []).length;
  const lowCount = (quality.low_confidence_fields || []).length;
  const evidenceMissingCount = (quality.evidence_missing_fields || []).length;
  const parts = [
    missingCount ? `需补充 ${missingCount} 项` : "",
    lowCount ? `低置信度 ${lowCount} 项` : "",
    evidenceMissingCount ? `证据不足 ${evidenceMissingCount} 项` : "",
  ].filter(Boolean);
  const text = parts.length ? parts.join(" · ") : "质量可进入医生审核";
  return `
    <button type="button" class="assist-quality-line ${quality.ready_for_doctor_review ? "confirmed" : "warning"}" data-open-detail="assist:quality">
      <span>质量：${escapeHtml(text)}</span>
      <strong>详情</strong>
    </button>
  `;
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

  if (section === "quality") {
    const quality = activeQualityReport();
    if (!quality) return `<div class="empty-state">暂无病历质量报告。</div>`;
    const treatment = quality.treatment_safety || {};
    const treatmentRows = [
      `治疗建议状态：${treatment.status === "complete" ? "完整" : treatment.status === "not_applicable" ? "暂无鉴别诊断参考，暂不适用" : "需完善"}`,
      `建议检查：${(treatment.suggested_checks || []).join("、") || "暂无"}`,
      `风险提醒：${(treatment.risk_warnings || []).join("、") || "暂无"}`,
      `建议补问：${(treatment.follow_up_questions || []).join("、") || "暂无"}`,
      `治疗建议缺项：${(treatment.quality_issues || []).join("、") || "无"}`,
    ];
    const fieldRows = (quality.field_quality || []).map((item) => {
      const statusLabels = {
        complete: "质量可用",
        missing: "需补充",
        low_confidence: "低置信度",
        evidence_missing: "证据不足",
        needs_doctor_review: "待医生确认",
      };
      const status = statusLabels[item.status] || item.status || "需复核";
      const evidenceCount = item.evidence_count == null ? 0 : item.evidence_count;
      return `${item.label}：${status}；证据 ${evidenceCount} 条；${item.suggested_action || item.reason || ""}`;
    });
    const rows = [
      `核心字段完整度：${Math.round((quality.core_completeness || 0) * 100)}%`,
      `证据覆盖率：${Math.round((quality.evidence_coverage || 0) * 100)}%`,
      `缺失字段：${(quality.missing_fields || []).join("、") || "无"}`,
      `低置信度字段：${(quality.low_confidence_fields || []).map((item) => item.label).join("、") || "无"}`,
      `证据不足字段：${(quality.evidence_missing_fields || []).join("、") || "无"}`,
      `是否可进入医生审核：${quality.ready_for_doctor_review ? "是" : "否"}`,
      ...treatmentRows,
      ...fieldRows,
      ...((quality.next_actions || []).map((item) => `下一步：${item}`)),
    ];
    return detailSection("病历质量摘要", `
      <div class="detail-evidence-list">
        ${rows.map((item) => `<div class="assist-evidence-quote">${escapeHtml(item)}</div>`).join("")}
      </div>
    `);
  }

  if (section === "candidates") {
    const diagnosisQuality = activeQualityReport()?.candidate_diagnosis_status?.diagnosis_quality || [];
    return diagnoses.length
      ? diagnoses.map((diagnosis, index) => `
          ${detailSection(`鉴别诊断参考 ${index + 1}：${diagnosis.name || "未命名诊断"}`, `
            <div class="detail-kv"><span>状态</span><strong>${escapeHtml(diagnosis.status || "候选/待医生确认")}</strong></div>
            <div class="detail-kv"><span>规则匹配度</span><strong>${escapeHtml(diagnosisConfidence(diagnosis))}</strong></div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
            ${diagnosisQuality[index] ? `<div class="detail-text">${escapeHtml(
              diagnosisQuality[index].missing?.length
                ? `缺项：${diagnosisQuality[index].missing.join("、")}。${diagnosisQuality[index].suggested_action || ""}`
                : (diagnosisQuality[index].suggested_action || "鉴别诊断参考结构完整，等待医生判断。")
            )}</div>` : ""}
          `)}
        `).join("")
      : `<div class="empty-state">暂无鉴别诊断参考。</div>`;
  }

  if (section === "treatment") {
    const treatment = fields?.treatment_plan;
    const treatmentText = treatment?.value || treatment?.hint || previewTreatmentText() || activeDraftText() || "暂无明确处理建议，需医生补充。";
    const suggestedChecks = uniqueDiagnosisItems(diagnoses, "suggested_checks");
    const medicationNotes = uniqueDiagnosisItems(diagnoses, "medication_notes");
    const riskWarnings = uniqueDiagnosisItems(diagnoses, "risk_warnings");
    const followUpQuestions = uniqueDiagnosisItems(diagnoses, "follow_up_questions");
    return `
      ${detailSection("处理建议", `<div class="detail-text">${escapeHtml(treatmentText)}</div>`)}
      ${detailSection("建议检查", `<div class="detail-text">${escapeHtml(suggestedChecks.join("\n") || "暂无结构化建议检查。")}</div>`)}
      ${detailSection("用药提示", `<div class="detail-text">${escapeHtml(medicationNotes.join("\n") || "不自动处方，需医生确认。")}</div>`)}
      ${detailSection("风险提醒", `<div class="detail-text">${escapeHtml(riskWarnings.join("\n") || "暂无结构化风险提醒。")}</div>`)}
      ${detailSection("建议补问", `<div class="detail-text">${escapeHtml(followUpQuestions.join("\n") || "暂无结构化补问建议。")}</div>`)}
    `;
  }

  if (section === "evidence") {
    const diagnosisReasons = diagnoses
      .map((diagnosis) => diagnosis.reason ? `${diagnosis.name || "鉴别诊断参考"}：${diagnosis.reason}` : "")
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
  const readiness = appState.currentExportReadiness;
  const exports = appState.currentExports || readiness?.exports || null;
  const exportRows = readiness
    ? [
        readiness.ready ? "导出状态：可以导出。" : "导出状态：暂不可导出。",
        ...(readiness.errors || []).map((item) => `导出阻断：${item}`),
        readiness.next_action ? `下一步：${readiness.next_action}` : "",
      ].filter(Boolean)
    : [];
  const exportedRows = exports
    ? Object.entries(exports).map(([key, value]) => `导出文件 ${key}：${value}`)
    : [];
  const detailRows = [...rows, ...exportRows, ...exportedRows];
  return detailSection("安全校验结果", `
    <div class="detail-evidence-list">
      ${detailRows.map((item) => `<div class="assist-evidence-quote">${escapeHtml(item)}</div>`).join("")}
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
    ${previewNotice}
    ${previewError}
    <div class="doctor-assist-overview">
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
      title: "鉴别诊断参考",
      badgeClass: diagnoses.length ? "candidate" : "confirmed",
      badgeText: diagnoses.length ? "需医生判断" : "暂无",
      open: diagnoses.length > 0,
      tone: diagnoses.length ? "risk-warning" : "normal-success",
      body: diagnoses.length ? diagnoses.map((diagnosis) => `
          <div class="diagnosis-card">
            <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong>
            <div class="diagnosis-status">${escapeHtml(diagnosis.status || "候选/待医生确认")} · ${escapeHtml(diagnosisConfidence(diagnosis))}</div>
            <div class="diagnosis-detail-list">${renderDiagnosisDetails(diagnosis)}</div>
          </div>
        `).join("") : `<div class="safety-strip success">暂无鉴别诊断参考。</div>`,
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
  const exportBlocked = !appState.currentTaskId || !isApprovedForExport();
  $("exportButton").disabled = appState.busy || !appState.currentTaskId;
  $("exportButton").classList.toggle("blocked-action", Boolean(appState.currentTaskId && !isApprovedForExport()));
  $("exportButton").setAttribute("aria-disabled", exportBlocked ? "true" : "false");
  $("exportButton").title = exportBlocked ? "点击查看暂不可导出的原因" : "确认导出病历";
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
    openDetailDrawer("鉴别诊断参考详情", renderDiagnosisDetailContent(Number(value)));
    return;
  }
  if (type === "transcript") {
    openDetailDrawer("对话转写与校正", renderTranscriptDetailContent(value));
    return;
  }
  if (type === "assist") {
    const titleMap = {
      candidates: "鉴别诊断参考完整依据",
      treatment: "治疗方案推荐详情",
      evidence: "判断证据详情",
      quality: "病历质量摘要",
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
  renderAuthPanel();
  renderProductShell();
  renderInputMethodMenu();
  renderDisplaySettingsMenu();
  renderPatientBar();
  renderEncounterWorklistPanel();
  renderBrowserRecordingPanel();
  renderRunContext();
  renderDashboardSummary();
  renderAdminHome();
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
  appState.speakerAssignments = [];
  appState.speakerMappingRequired = false;
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
  appState.currentEncounter = null;
  appState.currentSteps = [];
  appState.currentRecordFields = null;
  appState.currentDraft = "";
  appState.currentSafetyCheck = null;
  appState.currentQualityReport = null;
  appState.currentExportReadiness = null;
  appState.currentExports = null;
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
    appState.provisionalTranscriptSegments = [];
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
  appState.currentQualityReport = result.quality_report || appState.currentQualityReport;
  appState.currentExports = result.exports || appState.currentExports;
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
  const source = new EventSource(`${eventsUrl}${separator}delay_ms=100`);
  appState.asrEventSource = source;
  appState.asrConnectionStatus = "connecting";
  let terminalReceived = false;

  source.onopen = () => {
    appState.asrConnectionStatus = "connected";
    if (appState.asrLastError === "转写连接正在恢复，识别任务仍在后台运行。") {
      appState.asrLastError = "";
    }
    renderAll();
  };

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
    appState.provisionalTranscriptSegments = [];
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
      if (data.segment.provisional || data.partial) {
        upsertProvisionalTranscriptSegment(data.segment);
      } else {
        upsertLiveTranscriptSegment(data.segment);
      }
      appState.asrStreamCurrentSegment = appState.liveTranscriptSegments.length;
      const now = new Date().toISOString();
      appState.asrFirstSegmentAt = appState.asrFirstSegmentAt || now;
      appState.asrLastSegmentAt = now;
      const segmentEnd = segmentEndsAt(data.segment);
      if (segmentEnd != null) {
        appState.asrVisibleAudioSeconds = Math.max(appState.asrVisibleAudioSeconds || 0, segmentEnd);
      }
      if (!data.segment.provisional && !data.partial) scheduleRecordPreview();
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
    appState.speakerAssignments = result.speaker_assignments || appState.speakerAssignments;
    appState.speakerMappingRequired = appState.speakerAssignments.some((item) => item.requires_confirmation);
    appState.liveTranscriptSegments = finalTranscriptSegments(result.segments || [], []);
    appState.provisionalTranscriptSegments = [];
    appState.asrStreamCurrentSegment = appState.liveTranscriptSegments.length;
    appState.asrStreamTotalSegments = appState.liveTranscriptSegments.length;
    appState.asrPhase = "speaker_calibration_completed";
    appState.diarizationStatus = "completed";
    scheduleRecordPreview({ force: true });
    renderAll();
  });

  source.addEventListener("speaker_turn", (event) => {
    const data = JSON.parse(event.data);
    if (!data.segment || data.segment.provisional) return;
    upsertLiveTranscriptSegment(data.segment);
    appState.asrStreamCurrentSegment = appState.liveTranscriptSegments.length;
    renderTranscript();
  });

  const handleSpeakerMapping = (event, required) => {
    const data = JSON.parse(event.data);
    appState.speakerAssignments = data.assignments || [];
    appState.speakerMappingRequired = required
      || appState.speakerAssignments.some((item) => item.requires_confirmation);
    renderAll();
  };
  source.addEventListener("speaker_mapping_update", (event) => handleSpeakerMapping(event, false));
  source.addEventListener("speaker_mapping_required", (event) => handleSpeakerMapping(event, true));

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
    appState.speakerAssignments = appState.currentAsrResult?.speaker_assignments || appState.speakerAssignments;
    appState.speakerMappingRequired = appState.speakerAssignments.some((item) => item.requires_confirmation);
    appState.liveTranscriptSegments = mergedSegments;
    appState.provisionalTranscriptSegments = [];
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
    appState.asrConnectionStatus = "completed";
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
      // EventSource reconnects automatically and sends Last-Event-ID. A transient
      // network interruption must not turn a running ASR job into a failed job.
      appState.asrConnectionStatus = "reconnecting";
      appState.asrLastError = "转写连接正在恢复，识别任务仍在后台运行。";
      setBusy(true, "正在恢复转写连接...");
      renderAll();
    }
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
    segment.reviewed_by_doctor = Boolean(role);
    segment.needs_review = !role;
    changed = true;
  });
  if (!changed) return;
  appState.speakerRoleCorrections[speakerId] = role;
  appState.speakerAssignments = (appState.speakerAssignments || []).map((item) => (
    item.speaker_id === speakerId
      ? { ...item, role, confidence: 0.99, source: "manual_speaker_map", requires_confirmation: !role }
      : item
  ));
  appState.speakerMappingRequired = appState.speakerAssignments.some(
    (item) => item.requires_confirmation || !item.role,
  );
  appState.roleReviewDirty = true;
  syncAsrTextFromSegments();
  renderAll();
}

function cloneStateValue(value) {
  if (value == null) return value;
  return JSON.parse(JSON.stringify(value));
}

function speakerMergeSnapshot() {
  return {
    currentAsrResult: cloneStateValue(appState.currentAsrResult),
    liveTranscriptSegments: cloneStateValue(appState.liveTranscriptSegments),
    speakerAssignments: cloneStateValue(appState.speakerAssignments),
    speakerMappingRequired: appState.speakerMappingRequired,
    speakerRoleCorrections: cloneStateValue(appState.speakerRoleCorrections),
    roleReviewDirty: appState.roleReviewDirty,
  };
}

function applyAsrResultUpdate(asrResult = {}) {
  appState.currentAsrResult = asrResult;
  appState.currentAudioId = asrResult.audio_id || appState.currentAudioId;
  appState.liveTranscriptSegments = asrResult.segments || [];
  appState.speakerAssignments = asrResult.speaker_assignments || [];
  appState.speakerMappingRequired = roleQualityNeedsIdentityReview(asrResult)
    || appState.speakerAssignments.some((item) => speakerAssignmentNeedsReview(item));
  appState.speakerRoleCorrections = {};
  appState.roleReviewDirty = false;
  syncAsrTextFromSegments();
}

async function mergeSpeakerGroup(sourceSpeaker, targetSpeaker) {
  const source = String(sourceSpeaker || "").trim();
  const target = String(targetSpeaker || "").trim();
  if (!appState.currentAsrSessionId || !appState.currentAsrResult) {
    showToast("暂无可合并的转写会话");
    return null;
  }
  if (!source || !target) {
    showToast("请选择要合并到的说话人");
    return null;
  }
  if (source === target) {
    showToast("不能把说话人合并到自己");
    return null;
  }

  const snapshot = speakerMergeSnapshot();
  const response = await api(`/api/asr/sessions/${encodeURIComponent(appState.currentAsrSessionId)}/speakers/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_speaker: source,
      target_speaker: target,
      reviewer: "doctor",
      note: "manual diarization merge from doctor UI",
    }),
  });
  appState.lastSpeakerMergeSnapshot = snapshot;
  applyAsrResultUpdate(response.asr_result);
  resetRecordPreview();
  renderAll();
  const affected = response.affected_segment_ids?.length || 0;
  showToast(`已合并说话人，更新 ${affected} 段转写`);
  return response;
}

function undoLastSpeakerMerge() {
  const snapshot = appState.lastSpeakerMergeSnapshot;
  if (!snapshot) {
    showToast("暂无可撤销的本页合并");
    return;
  }
  appState.currentAsrResult = cloneStateValue(snapshot.currentAsrResult);
  appState.liveTranscriptSegments = cloneStateValue(snapshot.liveTranscriptSegments) || [];
  appState.speakerAssignments = cloneStateValue(snapshot.speakerAssignments) || [];
  appState.speakerMappingRequired = Boolean(snapshot.speakerMappingRequired);
  appState.speakerRoleCorrections = cloneStateValue(snapshot.speakerRoleCorrections) || {};
  appState.roleReviewDirty = Boolean(snapshot.roleReviewDirty);
  appState.lastSpeakerMergeSnapshot = null;
  renderAll();
  showToast("已撤销本页显示；刷新后以服务端合并结果为准");
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
    const role = Object.entries(roleCounts)
      .filter(([name]) => FINAL_CLINICAL_ROLES.includes(name))
      .sort((left, right) => right[1] - left[1])[0]?.[0] || "";
    return {
      ...group,
      role,
      displayName: `说话人 ${String.fromCharCode(65 + Math.min(index, 25))}`,
    };
  });
}

function roleReviewRequired() {
  const asr = appState.currentAsrResult;
  if (!asr) return false;
  if (roleQualityPassed(asr)) return false;
  if (roleQualityNeedsIdentityReview(asr)) return true;
  const segments = currentReviewSegments();
  const assignments = asr?.speaker_assignments || appState.speakerAssignments || [];
  if (assignments.length) {
    return assignments.some((item) => speakerAssignmentNeedsReview(item))
      || appState.speakerMappingRequired;
  }
  return Boolean(
    asr?.needs_review
      || asr?.role_strategy === "single_segment_needs_review"
      || segments.some((segment) => segment.needs_review || !segment.role || segment.role === "待确认"),
  );
}

function roleReviewPendingCount() {
  if (roleQualityPassed()) return 0;
  const assignments = appState.currentAsrResult?.speaker_assignments || appState.speakerAssignments || [];
  if (assignments.length) {
    return pendingSpeakerAssignments().length;
  }
  return currentReviewSegments()
    .filter((segment) => segment.needs_review || !segment.role || segment.role === "待确认")
    .length;
}

function focusNextActionPanel() {
  const panel = $("nextActionPanel");
  if (!panel) return;
  panel.scrollIntoView?.({ behavior: "smooth", block: "nearest" });
  panel.querySelector("[data-workflow-action='generate-record'], [data-workflow-action='open-role-review'], [data-workflow-action='save-role-review']")?.focus?.();
}

function speakerRolesForReviewSave() {
  const corrections = { ...appState.speakerRoleCorrections };
  if (roleReviewRequired()) {
    const pendingIds = new Set(pendingSpeakerAssignments().map((item) => item.speaker_id));
    transcriptSpeakerGroups().forEach((group) => {
      if (pendingIds.has(group.speakerId) && group.role && !corrections[group.speakerId]) {
        corrections[group.speakerId] = group.role;
      }
    });
  }
  return Object.entries(corrections).map(([speakerId, role]) => ({
    speaker_id: speakerId,
    role,
    reviewed_by_doctor: Boolean(role),
  }));
}

async function saveRoleReview({ silent = false } = {}) {
  if (!appState.currentAsrSessionId || !appState.currentAsrResult?.segments?.length) {
    if (!silent) showToast("暂无可保存的身份确认结果");
    return appState.currentAsrResult;
  }

  const pendingIds = new Set(pendingSpeakerAssignments().map((item) => item.speaker_id));
  const speakerGroupsForSave = pendingIds.size
    ? transcriptSpeakerGroups().filter((group) => pendingIds.has(group.speakerId))
    : transcriptSpeakerGroups();
  const unresolvedSpeakers = speakerGroupsForSave.filter((group) => !group.role);
  if (unresolvedSpeakers.length) {
    if (!silent) showToast(`请先完成 ${unresolvedSpeakers.length} 位说话人的身份确认`);
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
    const speakerRoles = speakerRolesForReviewSave();

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
    appState.speakerAssignments = response.asr_result.speaker_assignments || [];
    appState.speakerMappingRequired = appState.speakerAssignments.some(
      (item) => item.requires_confirmation || !item.role,
    );
    appState.liveTranscriptSegments = response.asr_result.segments || [];
    appState.currentAudioId = response.audio_id || appState.currentAudioId;
    appState.roleReviewDirty = false;
    appState.speakerRoleCorrections = {};
    savedResult = response.asr_result;
    pendingCount = roleReviewPendingCount();
    if (!pendingCount) scheduleRecordPreview({ force: true });
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
    showToast(`身份确认已保存，仍有 ${pendingCount} 位说话人需要确认`);
    focusNextActionPanel();
    return savedResult;
  }
  if (shouldAutoGenerate) {
    appState.pendingGenerateAfterRoleReview = false;
    closeDrawer();
    showToast("身份确认已保存，正在生成病历");
    await regenerateRecord();
    return savedResult;
  }
  appState.pendingGenerateAfterRoleReview = false;
  showToast("身份确认已保存，可继续生成病历");
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
    appState.provisionalTranscriptSegments = [];
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
  if (engine === "funasr") {
    const prewarm = await refreshAsrPrewarmStatus();
    if (prewarm?.status === "warming") {
      appState.asrLastError = "FunASR 模型仍在准备中，首次真实转写可能需要等待；Mock ASR 可作为现场保底。";
    } else if (prewarm?.status === "failed") {
      appState.asrLastError = "FunASR 自动预热失败，真实转写可能回退为按需加载；如现场演示受阻请切换 Mock ASR。";
    }
  }
  renderAll();

  setBusy(true, "正在创建 ASR 实时转写会话...");
  const sessionParams = new URLSearchParams({
    engine,
    diarization_engine: "auto",
  });
  if (appState.selectedDoctorProfileId) {
    sessionParams.set("doctor_profile_id", appState.selectedDoctorProfileId);
  }
  const session = await api(`/api/asr/sessions?${sessionParams.toString()}`, { method: "POST" });
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

async function continueGeneratingFromTranscription(transcribed) {
  if (roleReviewRequired()) {
    appState.pendingGenerateAfterRoleReview = true;
    setBusy(false);
    const pendingCount = roleReviewPendingCount();
    showToast(pendingCount
      ? `转写完成，仍有 ${pendingCount} 位说话人需要确认`
      : "转写完成，请确认说话人身份后自动生成病历");
    focusNextActionPanel();
    renderAll();
    return transcribed;
  }
  return startRecordGenerationFromAudio(transcribed.audio_id);
}

function applyRoleQualityGateError(error) {
  const roleQuality = error?.detail?.role_quality;
  if (!roleQuality) return false;
  if (appState.currentAsrResult) {
    appState.currentAsrResult = {
      ...appState.currentAsrResult,
      role_quality: roleQuality,
      needs_review: true,
    };
  }
  appState.speakerMappingRequired = true;
  appState.pendingGenerateAfterRoleReview = true;
  const reasonText = roleQualityReasonText(appState.currentAsrResult)
    || "说话人角色质量门禁未通过，请先确认说话人身份。";
  setBusy(false);
  setActionError(reasonText);
  renderAll();
  showToast("请先确认说话人身份");
  focusNextActionPanel();
  return true;
}

async function startRecordGenerationFromAudio(audioId) {
  setBusy(true, "正在从转写文本生成病历...");
  try {
    const created = await api(`/api/audio/${audioId}/generate-record`, { method: "POST" });
    appState.currentTaskId = created.task_id;
    appState.taskStatus = created.status;
    appState.currentTask = { id: created.task_id, status: created.status };
    renderAll();
    listenForEvents(created.task_id, created.events_url);
    return created;
  } catch (error) {
    if (applyRoleQualityGateError(error)) return null;
    throw error;
  }
}

async function runAudioWorkflowFromFile(file, engine, mode = appState.audioMode) {
  resetTaskState();
  appState.selectedEngine = engine;
  const transcribed = await uploadAndTranscribe(file, engine);
  if (mode === "generate") {
    return continueGeneratingFromTranscription(transcribed);
  }
  setBusy(false);
  renderAll();
  return transcribed;
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
    await runAudioWorkflowFromFile(file, engine, appState.audioMode);
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
      throw new Error("请先完成说话人身份确认");
    }
    const text = appState.currentAsrResult?.conversation_text || appState.currentInputText || $("conversationInput").value.trim();
    if (!text) throw new Error("暂无可重新生成的对话文本");
    const keepAsr = Boolean(appState.currentAudioId && appState.currentAsrResult?.engine !== "text-import");
    if (keepAsr) {
      await startRecordGenerationFromAudio(appState.currentAudioId);
      return;
    }
    await createRecordTask(text, { keepAsr });
  } catch (error) {
    setBusy(false);
    reportActionError(error);
  }
}

async function saveDraftReview() {
  try {
    if (!appState.currentTaskId || !appState.currentRecordFields) throw new Error("暂无可保存的病历字段");
    setBusy(true, "正在保存修改到 SQLite...");
    appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fields: appState.currentRecordFields }),
    });
    await refreshTask(appState.currentTaskId, appState.currentTask);
    setBusy(false);
    showToast("修改已保存到 SQLite");
  } catch (error) {
    setBusy(false);
    reportActionError(error);
  }
}

async function confirmFields() {
  try {
    if (!appState.currentTaskId) throw new Error("暂无可确认的任务");
    setBusy(true, "正在完成审核...");
    appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/approve`, { method: "POST" });
    appState.taskStatus = "approved";
    await refreshTask(appState.currentTaskId, appState.currentTask);
    setBusy(false);
    showToast("病历审核已完成");
  } catch (error) {
    setBusy(false);
    reportActionError(error);
  }
}

async function exportRecord() {
  try {
    if (!appState.currentTaskId) throw new Error("暂无可导出的任务");
    if (!isApprovedForExport()) {
      const readiness = await refreshExportReadiness();
      openDetailDrawer(
        "暂不可导出",
        readiness ? renderExportReadinessDetail(readiness) : renderAssistDetailContent("safety"),
      );
      return;
    }
    setBusy(true, "正在导出...");
    const result = await api(`/api/tasks/${appState.currentTaskId}/export`, { method: "POST" });
    appState.currentExports = result.exports || {};
    appState.currentExportReadiness = result.export_readiness || {
      task_id: appState.currentTaskId,
      ready: true,
      blocked: false,
      errors: [],
      next_action: "导出已完成。",
      exports: appState.currentExports,
    };
    appState.currentTask = {
      ...(appState.currentTask || {}),
      current_stage: "exported",
      result_json: {
        ...((appState.currentTask || {}).result_json || {}),
        exports: appState.currentExports,
      },
    };
    appState.taskStatus = "EXPORTED";
    renderAll();
    setBusy(false);
    openDetailDrawer("导出完成", renderExportReadinessDetail(appState.currentExportReadiness));
    showToast(`导出完成：${Object.values(result.exports || {}).join(" / ")}`);
  } catch (error) {
    if (error.detail?.errors) {
      appState.currentExportReadiness = error.detail;
      openDetailDrawer("暂不可导出", renderExportReadinessDetail(error.detail));
    }
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
  if (action === "open-role-review") {
    openRoleReview();
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
  if (method === "mock") {
    closeInputMethodMenu();
    appState.selectedEngine = "mock";
    const topSelect = $("topAsrEngineSelect");
    const audioSelect = $("audioEngineSelect");
    if (topSelect) topSelect.value = "mock";
    if (audioSelect) audioSelect.value = "mock";
    showToast("已切换为 Mock ASR 演示，可上传任意 MP3/WAV 跑通流程");
    openAudioGenerate();
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
  refreshDoctorProfiles();
}

function openAudioGenerate() {
  clearActionError();
  appState.audioMode = "generate";
  $("audioEngineSelect").value = appState.selectedEngine;
  $("audioPanelHint").textContent = "上传 MP3/WAV 预录音频，先完成 SSE 实时转写，再进入病历生成流程。";
  $("submitAudioButton").textContent = "实时转写并生成病历";
  openDrawer("audioPanel", "MP3/WAV 生成病历");
  refreshDoctorProfiles();
}

async function refreshDoctorProfiles() {
  const select = $("doctorProfileSelect");
  if (!select) return;
  try {
    const response = await api("/api/speaker-profiles");
    appState.doctorProfiles = response.profiles || [];
    select.innerHTML = `
      <option value="">不使用注册声纹</option>
      ${appState.doctorProfiles.map((profile) => `
        <option value="${escapeHtml(profile.profile_id)}">${escapeHtml(profile.name)} · ${Math.round(profile.effective_speech_seconds)}秒</option>
      `).join("")}
    `;
    const selectedExists = appState.doctorProfiles.some(
      (profile) => profile.profile_id === appState.selectedDoctorProfileId,
    );
    if (!selectedExists) appState.selectedDoctorProfileId = "";
    select.value = appState.selectedDoctorProfileId;
  } catch (error) {
    showToast(`医生声纹列表暂不可用：${error.message}`);
  }
}

async function enrollDoctorProfile() {
  const file = $("doctorProfileAudioInput")?.files?.[0];
  if (!file) {
    showToast("请选择 10-30 秒医生本人语音");
    return;
  }
  const name = $("doctorProfileNameInput")?.value?.trim() || "本机医生";
  const form = new FormData();
  form.append("file", file);
  appState.doctorProfileEnrollmentBusy = true;
  $("enrollDoctorProfileButton").disabled = true;
  $("enrollDoctorProfileButton").textContent = "正在提取声纹...";
  try {
    const profile = await api(`/api/speaker-profiles/doctor?name=${encodeURIComponent(name)}`, {
      method: "POST",
      body: form,
    });
    appState.selectedDoctorProfileId = profile.profile_id;
    await refreshDoctorProfiles();
    showToast("医生声纹已保存在本机，注册原始音频已删除");
  } catch (error) {
    reportActionError(error);
  } finally {
    appState.doctorProfileEnrollmentBusy = false;
    $("enrollDoctorProfileButton").disabled = false;
    $("enrollDoctorProfileButton").textContent = "注册 10-30 秒声纹";
  }
}

function secureBrowserRecordingContext() {
  const host = window.location.hostname;
  return window.isSecureContext || host === "localhost" || host === "127.0.0.1" || host === "::1";
}

function browserRecordingErrorMessage(error) {
  const name = error?.name || "";
  if (name === "NotAllowedError" || name === "SecurityError") {
    return "麦克风权限被拒绝，请在浏览器地址栏授权后重试。";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError") {
    return "未检测到麦克风输入设备，请连接麦克风后重试。";
  }
  if (name === "NotReadableError" || name === "TrackStartError") {
    return "麦克风正被其他程序占用，请关闭占用程序后重试。";
  }
  return error?.message || "浏览器录音失败，请检查麦克风权限和输入设备。";
}

function releaseBrowserRecordingPreview() {
  if (appState.browserRecordingObjectUrl?.startsWith("blob:")) {
    URL.revokeObjectURL(appState.browserRecordingObjectUrl);
  }
  appState.browserRecordingObjectUrl = "";
  appState.browserRecordingFile = null;
  const preview = $("browserRecordingPreview");
  if (preview) {
    preview.removeAttribute("src");
    preview.load();
  }
}

function cleanupBrowserRecordingCapture() {
  if (appState.browserRecordingTimer) {
    window.clearInterval(appState.browserRecordingTimer);
    appState.browserRecordingTimer = null;
  }
  if (appState.browserRecordingChunkTimer) {
    window.clearInterval(appState.browserRecordingChunkTimer);
    appState.browserRecordingChunkTimer = null;
  }
  if (appState.browserRecordingProcessor) {
    appState.browserRecordingProcessor.onaudioprocess = null;
    try {
      appState.browserRecordingProcessor.disconnect();
    } catch (_) {
      // The node may already be disconnected by the browser.
    }
  }
  if (appState.browserRecordingSource) {
    try {
      appState.browserRecordingSource.disconnect();
    } catch (_) {
      // The node may already be disconnected by the browser.
    }
  }
  if (appState.browserRecordingStream) {
    appState.browserRecordingStream.getTracks().forEach((track) => track.stop());
  }
  if (appState.browserRecordingAudioContext) {
    appState.browserRecordingAudioContext.close().catch(() => {});
  }
  appState.browserRecordingProcessor = null;
  appState.browserRecordingSource = null;
  appState.browserRecordingStream = null;
  appState.browserRecordingAudioContext = null;
}

function setBrowserRecordingError(message) {
  cleanupBrowserRecordingCapture();
  appState.browserRecordingStatus = "error";
  appState.browserRecordingMessage = message;
  appState.browserRecordingStartedAt = 0;
  renderAll();
  reportActionError(new Error(message));
}

function browserRecordingRequestActive(requestId) {
  return appState.browserRecordingRequestId === requestId && appState.browserRecordingStatus === "requesting";
}

function updateBrowserRecordingTimer() {
  if (appState.browserRecordingStatus !== "recording") return;
  const elapsed = (Date.now() - appState.browserRecordingStartedAt - appState.browserRecordingTotalPausedMs) / 1000;
  appState.browserRecordingElapsedSeconds = Math.min(elapsed, MAX_BROWSER_RECORDING_SECONDS);
  if (elapsed >= MAX_BROWSER_RECORDING_SECONDS) {
    stopBrowserRecording({ auto: true }).catch(reportActionError);
    return;
  }
  renderBrowserRecordingPanel();
}

function mergeBrowserRecordingChunks(chunks = []) {
  const sampleCount = chunks.reduce((total, chunk) => total + chunk.length, 0);
  const merged = new Float32Array(sampleCount);
  let offset = 0;
  chunks.forEach((chunk) => {
    merged.set(chunk, offset);
    offset += chunk.length;
  });
  return merged;
}

function writeWavString(view, offset, value) {
  for (let index = 0; index < value.length; index += 1) {
    view.setUint8(offset + index, value.charCodeAt(index));
  }
}

function encodeWavFromFloat32(chunks, sampleRate) {
  const samples = mergeBrowserRecordingChunks(chunks);
  const bytesPerSample = 2;
  const blockAlign = bytesPerSample;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);
  writeWavString(view, 0, "RIFF");
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  writeWavString(view, 8, "WAVE");
  writeWavString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * blockAlign, true);
  view.setUint16(32, blockAlign, true);
  view.setUint16(34, 16, true);
  writeWavString(view, 36, "data");
  view.setUint32(40, samples.length * bytesPerSample, true);
  let offset = 44;
  for (let index = 0; index < samples.length; index += 1) {
    const sample = Math.max(-1, Math.min(1, samples[index]));
    view.setInt16(offset, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
    offset += bytesPerSample;
  }
  return new Blob([view], { type: "audio/wav" });
}

async function sha256Blob(blob) {
  const buffer = await blob.arrayBuffer();
  const digest = await crypto.subtle.digest("SHA-256", buffer);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function recordingQueueKey(sessionId, chunkIndex) {
  return `${sessionId}:${String(chunkIndex).padStart(8, "0")}`;
}

function delay(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function openBrowserRecordingDb() {
  if (!window.indexedDB) {
    return Promise.reject(new Error("当前浏览器不支持录音恢复队列，请使用最新版 Chrome 或 Edge。"));
  }
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(BROWSER_RECORDING_DB_NAME, BROWSER_RECORDING_DB_VERSION);
    request.onerror = () => reject(request.error || new Error("无法打开录音恢复队列。"));
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(BROWSER_RECORDING_STORE)) {
        const store = db.createObjectStore(BROWSER_RECORDING_STORE, { keyPath: "key" });
        store.createIndex("session_id", "session_id", { unique: false });
        store.createIndex("status", "status", { unique: false });
      }
      if (!db.objectStoreNames.contains(BROWSER_RECORDING_CLEANUP_STORE)) {
        const cleanupStore = db.createObjectStore(BROWSER_RECORDING_CLEANUP_STORE, { keyPath: "session_id" });
        cleanupStore.createIndex("status", "status", { unique: false });
      }
    };
    request.onsuccess = () => resolve(request.result);
  });
}

async function withBrowserRecordingStore(mode, callback) {
  const db = await openBrowserRecordingDb();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(BROWSER_RECORDING_STORE, mode);
      const store = transaction.objectStore(BROWSER_RECORDING_STORE);
      let result;
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = () => reject(transaction.error || new Error("录音恢复队列操作失败。"));
      transaction.onabort = () => reject(transaction.error || new Error("录音恢复队列操作已取消。"));
      try {
        result = callback(store);
      } catch (error) {
        transaction.abort();
        reject(error);
      }
    });
  } finally {
    db.close();
  }
}

async function withBrowserRecordingCleanupStore(mode, callback) {
  const db = await openBrowserRecordingDb();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(BROWSER_RECORDING_CLEANUP_STORE, mode);
      const store = transaction.objectStore(BROWSER_RECORDING_CLEANUP_STORE);
      let result;
      transaction.oncomplete = () => resolve(result);
      transaction.onerror = () => reject(transaction.error || new Error("Recording cleanup queue operation failed."));
      transaction.onabort = () => reject(transaction.error || new Error("Recording cleanup queue operation aborted."));
      try {
        result = callback(store);
      } catch (error) {
        transaction.abort();
        reject(error);
      }
    });
  } finally {
    db.close();
  }
}

function requestToPromise(request) {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error || new Error("录音恢复队列请求失败。"));
  });
}

async function putBrowserRecordingQueueEntry(entry) {
  return withBrowserRecordingStore("readwrite", (store) => {
    store.put({
      ...entry,
      updated_at: new Date().toISOString(),
    });
  });
}

async function listBrowserRecordingQueueEntries(sessionId) {
  return withBrowserRecordingStore("readonly", async (store) => {
    const index = store.index("session_id");
    const rows = await requestToPromise(index.getAll(sessionId));
    return rows.sort((left, right) => Number(left.chunk_index) - Number(right.chunk_index));
  });
}

async function deleteBrowserRecordingQueueEntry(sessionId, chunkIndex) {
  return withBrowserRecordingStore("readwrite", (store) => {
    store.delete(recordingQueueKey(sessionId, chunkIndex));
  });
}

async function clearBrowserRecordingQueue(sessionId) {
  const rows = await listBrowserRecordingQueueEntries(sessionId);
  await withBrowserRecordingStore("readwrite", (store) => {
    rows.forEach((row) => store.delete(row.key));
  });
}

async function putBrowserRecordingCleanup(sessionId, reason = "cancel") {
  if (!sessionId) return;
  return withBrowserRecordingCleanupStore("readwrite", (store) => {
    store.put({
      session_id: sessionId,
      status: "pending",
      reason,
      retry_count: 0,
      last_error: "",
      next_retry_at: 0,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });
}

async function listBrowserRecordingCleanups() {
  return withBrowserRecordingCleanupStore("readonly", (store) => requestToPromise(store.getAll()));
}

async function deleteBrowserRecordingCleanup(sessionId) {
  return withBrowserRecordingCleanupStore("readwrite", (store) => {
    store.delete(sessionId);
  });
}

async function updateBrowserRecordingCleanup(sessionId, updates) {
  const rows = await listBrowserRecordingCleanups();
  const current = rows.find((row) => row.session_id === sessionId);
  if (!current) return;
  return withBrowserRecordingCleanupStore("readwrite", (store) => {
    store.put({
      ...current,
      ...updates,
      updated_at: new Date().toISOString(),
    });
  });
}

async function updateBrowserRecordingQueueEntry(sessionId, chunkIndex, updates) {
  const db = await openBrowserRecordingDb();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction(BROWSER_RECORDING_STORE, "readwrite");
      const store = transaction.objectStore(BROWSER_RECORDING_STORE);
      const key = recordingQueueKey(sessionId, chunkIndex);
      const request = store.get(key);
      request.onerror = () => reject(request.error || new Error("录音恢复队列读取失败。"));
      request.onsuccess = () => {
        const current = request.result;
        if (!current) return;
        store.put({
          ...current,
          ...updates,
          updated_at: new Date().toISOString(),
        });
      };
      transaction.oncomplete = () => resolve();
      transaction.onerror = () => reject(transaction.error || new Error("录音恢复队列更新失败。"));
      transaction.onabort = () => reject(transaction.error || new Error("录音恢复队列更新已取消。"));
    });
  } finally {
    db.close();
  }
}

async function refreshBrowserRecordingQueueCounts(sessionId = appState.browserRecordingSessionId) {
  if (!sessionId) return { pending: 0, failed: 0, uploaded: appState.browserRecordingUploadedChunks || 0 };
  const rows = await listBrowserRecordingQueueEntries(sessionId).catch(() => []);
  appState.browserRecordingPendingChunks = rows.length;
  const failed = rows.filter((row) => row.status === "failed").length;
  return {
    pending: rows.length,
    failed,
    uploaded: appState.browserRecordingUploadedChunks || 0,
  };
}

async function ensureBrowserRecordingSession(engine) {
  if (appState.browserRecordingSessionId) return appState.browserRecordingSessionId;
  const sessionParams = new URLSearchParams({ engine });
  if (appState.selectedDoctorProfileId) {
    sessionParams.set("doctor_profile_id", appState.selectedDoctorProfileId);
  }
  const session = await api(`/api/asr/sessions?${sessionParams.toString()}`, { method: "POST" });
  appState.currentAsrSessionId = session.session_id;
  appState.browserRecordingSessionId = session.session_id;
  appState.selectedEngine = session.engine || engine || appState.selectedEngine;
  updateSessionUrl(session.session_id);
  return session.session_id;
}

function updateBrowserRecordingChunkStatusText() {
  const parts = [
    `已录制 ${appState.browserRecordingRecordedChunks || 0} 块`,
    `已上传 ${appState.browserRecordingUploadedChunks || 0} 块`,
    `待上传 ${appState.browserRecordingPendingChunks || 0} 块`,
  ];
  if (appState.browserRecordingRetryStatus) parts.push(appState.browserRecordingRetryStatus);
  if (appState.browserRecordingMissingChunks?.length) {
    parts.push(`缺少第 ${appState.browserRecordingMissingChunks.join(", ")} 段，无法完成`);
  }
  appState.browserRecordingChunkStatus = parts.join(" · ");
}

async function queueBrowserRecordingChunk({ force = false } = {}) {
  if (!appState.browserRecordingSessionId) return null;
  const chunks = appState.browserRecordingChunkBuffer || [];
  const sampleCount = chunks.reduce((total, chunk) => total + chunk.length, 0);
  if (!force && sampleCount < (appState.browserRecordingSampleRate || 44100) * BROWSER_RECORDING_CHUNK_SECONDS) {
    return null;
  }
  if (sampleCount === 0) return null;
  const sampleRate = appState.browserRecordingSampleRate || 44100;
  const blob = encodeWavFromFloat32(chunks, sampleRate);
  const chunkIndex = appState.browserRecordingChunkIndex;
  const checksum = await sha256Blob(blob);
  await putBrowserRecordingQueueEntry({
    key: recordingQueueKey(appState.browserRecordingSessionId, chunkIndex),
    session_id: appState.browserRecordingSessionId,
    chunk_index: chunkIndex,
    sha256: checksum,
    duration_seconds: sampleCount / sampleRate,
    blob,
    status: "pending",
    retry_count: 0,
    next_retry_at: 0,
    last_error: "",
    created_at: new Date().toISOString(),
  });
  appState.browserRecordingChunkBuffer = [];
  appState.browserRecordingChunkIndex += 1;
  appState.browserRecordingRecordedChunks += 1;
  await refreshBrowserRecordingQueueCounts();
  updateBrowserRecordingChunkStatusText();
  renderBrowserRecordingPanel();
  pumpBrowserRecordingUploadQueue().catch(() => undefined);
  return { chunk_index: chunkIndex, sha256: checksum };
}

async function uploadQueuedBrowserRecordingChunk(entry) {
  const form = new FormData();
  form.append("chunk_index", String(entry.chunk_index));
  form.append("sha256", entry.sha256);
  form.append("duration_seconds", String(entry.duration_seconds || 0));
  form.append("file", entry.blob, `browser-recording-chunk-${String(entry.chunk_index).padStart(6, "0")}.wav`);
  return api(`/api/asr/sessions/${encodeURIComponent(entry.session_id)}/chunks`, {
    method: "POST",
    body: form,
  });
}

function scheduleBrowserRecordingQueueRetry(delayMs) {
  if (appState.browserRecordingRetryTimer) window.clearTimeout(appState.browserRecordingRetryTimer);
  appState.browserRecordingRetryTimer = window.setTimeout(() => {
    appState.browserRecordingRetryTimer = null;
    pumpBrowserRecordingUploadQueue().catch(() => undefined);
  }, Math.max(500, delayMs));
}

function isBrowserRecordingChunkConflict(error) {
  const message = String(error?.message || error?.detail?.message || "");
  return error?.status === 409 && /different hash|分块冲突|chunk_index/i.test(message);
}

async function pumpBrowserRecordingUploadQueue(sessionId = appState.browserRecordingSessionId) {
  if (!sessionId || appState.browserRecordingUploadInFlight) return;
  appState.browserRecordingUploadInFlight = true;
  try {
    while (true) {
      const rows = await listBrowserRecordingQueueEntries(sessionId);
      appState.browserRecordingPendingChunks = rows.length;
      const uploadable = rows
        .filter((row) => row.status !== "uploaded" && row.status !== "conflict")
        .sort((left, right) => Number(left.chunk_index) - Number(right.chunk_index));
      if (!uploadable.length) {
        appState.browserRecordingRetryStatus = rows.some((row) => row.status === "conflict")
          ? "分块冲突，请取消并重新录制"
          : "";
        break;
      }
      const next = uploadable[0];
      const now = Date.now();
      if (Number(next.next_retry_at || 0) > now) {
        const waitMs = Number(next.next_retry_at) - now;
        appState.browserRecordingRetryStatus = `等待 ${Math.ceil(waitMs / 1000)} 秒后重试第 ${next.chunk_index} 段`;
        scheduleBrowserRecordingQueueRetry(waitMs);
        break;
      }
      await updateBrowserRecordingQueueEntry(sessionId, next.chunk_index, {
        status: "uploading",
        last_error: "",
      });
      updateBrowserRecordingChunkStatusText();
      renderBrowserRecordingPanel();
      try {
        const result = await uploadQueuedBrowserRecordingChunk(next);
        await deleteBrowserRecordingQueueEntry(sessionId, next.chunk_index);
        appState.browserRecordingUploadedChunks = Math.max(
          appState.browserRecordingUploadedChunks || 0,
          Number(result.chunk_count || 0),
          Number(next.chunk_index) + 1,
        );
        appState.browserRecordingRetryStatus = "";
        await refreshBrowserRecordingQueueCounts(sessionId);
        updateBrowserRecordingChunkStatusText();
        renderBrowserRecordingPanel();
      } catch (error) {
        if (isBrowserRecordingChunkConflict(error)) {
          await updateBrowserRecordingQueueEntry(sessionId, next.chunk_index, {
            status: "conflict",
            retry_count: Number(next.retry_count || 0) + 1,
            next_retry_at: 0,
            last_error: error?.message || String(error),
          });
          appState.browserRecordingRetryStatus = `第 ${next.chunk_index} 段分块冲突，请取消并重新录制`;
          await refreshBrowserRecordingQueueCounts(sessionId);
          updateBrowserRecordingChunkStatusText();
          renderBrowserRecordingPanel();
          break;
        }
        const retryCount = Number(next.retry_count || 0) + 1;
        const retryable = retryCount < BROWSER_RECORDING_MAX_RETRY_ATTEMPTS;
        const delayMs = Math.min(
          BROWSER_RECORDING_RETRY_MAX_MS,
          BROWSER_RECORDING_RETRY_BASE_MS * (2 ** Math.max(0, retryCount - 1)),
        );
        await updateBrowserRecordingQueueEntry(sessionId, next.chunk_index, {
          status: retryable ? "pending" : "failed",
          retry_count: retryCount,
          next_retry_at: retryable ? Date.now() + delayMs : 0,
          last_error: error?.message || String(error),
        });
        appState.browserRecordingRetryStatus = retryable
          ? `第 ${next.chunk_index} 段上传失败，${Math.ceil(delayMs / 1000)} 秒后重试`
          : `第 ${next.chunk_index} 段上传失败，请点击重新上传`;
        await refreshBrowserRecordingQueueCounts(sessionId);
        updateBrowserRecordingChunkStatusText();
        renderBrowserRecordingPanel();
        if (retryable) scheduleBrowserRecordingQueueRetry(delayMs);
        break;
      }
    }
  } finally {
    appState.browserRecordingUploadInFlight = false;
  }
}

async function retryFailedBrowserRecordingChunks() {
  const sessionId = appState.browserRecordingSessionId;
  if (!sessionId) return;
  const rows = await listBrowserRecordingQueueEntries(sessionId);
  const retryableRows = rows.filter((row) => row.status !== "conflict");
  await Promise.all(retryableRows.map((row) => updateBrowserRecordingQueueEntry(sessionId, row.chunk_index, {
    status: "pending",
    retry_count: 0,
    next_retry_at: 0,
    last_error: "",
  })));
  appState.browserRecordingRetryStatus = "正在重新上传失败片段";
  await refreshBrowserRecordingQueueCounts(sessionId);
  updateBrowserRecordingChunkStatusText();
  renderBrowserRecordingPanel();
  await pumpBrowserRecordingUploadQueue(sessionId);
}

async function processPendingBrowserRecordingCleanups() {
  const rows = await listBrowserRecordingCleanups().catch(() => []);
  for (const row of rows) {
    const sessionId = row.session_id;
    if (!sessionId) continue;
    const now = Date.now();
    if (Number(row.next_retry_at || 0) > now) continue;
    try {
      await updateBrowserRecordingCleanup(sessionId, { status: "deleting", last_error: "" });
      await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/recording`, { method: "DELETE" });
      const cleanupStatus = await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/chunks/status?cleanup_check=${Date.now()}`);
      if (cleanupStatus?.status !== "cancelled") {
        throw new Error("Recording cleanup was not confirmed by the server.");
      }
      await clearBrowserRecordingQueue(sessionId).catch(() => undefined);
      await deleteBrowserRecordingCleanup(sessionId);
      if (appState.browserRecordingSessionId === sessionId) {
        appState.browserRecordingRetryStatus = "";
        appState.browserRecordingChunkStatus = "";
        appState.browserRecordingPendingChunks = 0;
      }
    } catch (error) {
      if (error?.status === 404) {
        await clearBrowserRecordingQueue(sessionId).catch(() => undefined);
        await deleteBrowserRecordingCleanup(sessionId);
        continue;
      }
      const retryCount = Number(row.retry_count || 0) + 1;
      const delayMs = Math.min(
        BROWSER_RECORDING_RETRY_MAX_MS,
        BROWSER_RECORDING_RETRY_BASE_MS * (2 ** Math.max(0, retryCount - 1)),
      );
      await updateBrowserRecordingCleanup(sessionId, {
        status: "pending",
        retry_count: retryCount,
        next_retry_at: Date.now() + delayMs,
        last_error: error?.message || String(error),
      });
      if (appState.browserRecordingSessionId === sessionId) {
        appState.browserRecordingRetryStatus = `取消清理失败，${Math.ceil(delayMs / 1000)} 秒后重试`;
        updateBrowserRecordingChunkStatusText();
        renderBrowserRecordingPanel();
      }
    }
  }
}

async function refreshBrowserRecordingServerStatus(sessionId = appState.browserRecordingSessionId) {
  if (!sessionId) return null;
  const status = await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/chunks/status`);
  appState.browserRecordingUploadedChunks = Number(status.next_chunk_index || status.chunk_count || 0);
  appState.browserRecordingMissingChunks = Array.isArray(status.missing_chunk_indices)
    ? status.missing_chunk_indices
    : [];
  if (status.status === "recorded" && status.audio_id) {
    appState.browserRecordingFinalized = status;
    appState.currentAudioId = status.audio_id;
    appState.audioMediaUrl = status.media_url || `/api/audio/${encodeURIComponent(status.audio_id)}/media`;
  }
  updateBrowserRecordingChunkStatusText();
  return status;
}

async function reconcileBrowserRecordingQueue(sessionId = appState.browserRecordingSessionId) {
  if (!sessionId) return null;
  appState.browserRecordingRecovering = true;
  try {
    const serverStatus = await refreshBrowserRecordingServerStatus(sessionId);
    const serverChunks = new Map((serverStatus?.chunks || []).map((chunk) => [Number(chunk.chunk_index), chunk]));
    const rows = await listBrowserRecordingQueueEntries(sessionId);
    for (const row of rows) {
      const serverChunk = serverChunks.get(Number(row.chunk_index));
      if (serverChunk?.sha256 === row.sha256) {
        await deleteBrowserRecordingQueueEntry(sessionId, row.chunk_index);
      } else if (!serverChunk) {
        await updateBrowserRecordingQueueEntry(sessionId, row.chunk_index, {
          status: "pending",
          next_retry_at: 0,
        });
      }
    }
    await refreshBrowserRecordingQueueCounts(sessionId);
    await pumpBrowserRecordingUploadQueue(sessionId);
    const latestStatus = await refreshBrowserRecordingServerStatus(sessionId);
    const localRows = await listBrowserRecordingQueueEntries(sessionId);
    const localIndexes = new Set(localRows.map((row) => Number(row.chunk_index)));
    appState.browserRecordingMissingChunks = (latestStatus?.missing_chunk_indices || [])
      .filter((index) => !localIndexes.has(Number(index)));
    appState.browserRecordingChunkIndex = Math.max(
      Number(latestStatus?.next_chunk_index || 0),
      ...localRows.map((row) => Number(row.chunk_index) + 1),
      appState.browserRecordingChunkIndex || 0,
    );
    updateBrowserRecordingChunkStatusText();
    return latestStatus;
  } finally {
    appState.browserRecordingRecovering = false;
    renderBrowserRecordingPanel();
  }
}

async function waitForBrowserRecordingUploads(sessionId = appState.browserRecordingSessionId) {
  const deadline = Date.now() + 60000;
  while (Date.now() < deadline) {
    await pumpBrowserRecordingUploadQueue(sessionId);
    await refreshBrowserRecordingQueueCounts(sessionId);
    const rows = await listBrowserRecordingQueueEntries(sessionId);
    if (!rows.length && !appState.browserRecordingUploadInFlight) {
      const status = await refreshBrowserRecordingServerStatus(sessionId);
      if (status?.missing_chunk_indices?.length) {
        throw new Error(`缺少第 ${status.missing_chunk_indices.join(", ")} 段，无法完成录音。`);
      }
      return status;
    }
    const hasConflict = rows.some((row) => row.status === "conflict");
    const permanentlyFailed = rows.some((row) => row.status === "failed");
    updateBrowserRecordingChunkStatusText();
    if (hasConflict) {
      throw new Error("分块冲突，请取消并重新录制。");
    }
    if (permanentlyFailed) {
      throw new Error(`还有 ${rows.length} 个音频块未上传，请点击重新上传失败片段。`);
    }
    await delay(500);
  }
  throw new Error("音频块上传等待超时，请检查网络后点击重新上传失败片段。");
}

async function finalizeBrowserRecording() {
  const sessionId = appState.browserRecordingSessionId;
  if (!sessionId) throw new Error("录音会话尚未创建，请重新开始录音。");
  await waitForBrowserRecordingUploads(sessionId);
  appState.browserRecordingStatus = "finalizing";
  appState.browserRecordingMessage = "正在校验音频块并准备试听...";
  renderBrowserRecordingPanel();
  const finalized = await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/finalize`, { method: "POST" });
  appState.browserRecordingFinalized = finalized;
  appState.currentAsrSessionId = finalized.session_id;
  appState.currentAudioId = finalized.audio_id;
  appState.uploadedFilename = finalized.filename || finalized.audio_id;
  appState.audioMediaUrl = finalized.media_url || `/api/audio/${encodeURIComponent(finalized.audio_id)}/media`;
  appState.audioDurationSeconds = Number(finalized.duration_seconds || 0);
  const preview = $("browserRecordingPreview");
  if (preview) {
    preview.src = appState.audioMediaUrl;
    preview.load();
  }
  appState.browserRecordingObjectUrl = appState.audioMediaUrl;
  appState.browserRecordingStatus = "recorded";
  appState.browserRecordingMessage = "录音已准备完成，可先试听，再点击上传并生成病历。";
  await refreshBrowserRecordingServerStatus(sessionId);
  renderAll();
  return finalized;
}

async function uploadBrowserRecordingChunk({ force = false } = {}) {
  return queueBrowserRecordingChunk({ force });
}

async function flushBrowserRecordingChunk({ force = false } = {}) {
  try {
    return await queueBrowserRecordingChunk({ force });
  } catch (error) {
    setBrowserRecordingError(`音频块保存失败：${error?.message || String(error)}`);
    throw error;
  }
}

function startBrowserRecordingIntervals() {
  if (appState.browserRecordingTimer) window.clearInterval(appState.browserRecordingTimer);
  if (appState.browserRecordingChunkTimer) window.clearInterval(appState.browserRecordingChunkTimer);
  appState.browserRecordingTimer = window.setInterval(updateBrowserRecordingTimer, 250);
  appState.browserRecordingChunkTimer = window.setInterval(() => {
    flushBrowserRecordingChunk().catch(() => undefined);
  }, Math.max(1000, BROWSER_RECORDING_CHUNK_SECONDS * 1000));
}

async function startBrowserRecordingCaptureForExistingSession(requestId) {
  if (!appState.browserRecordingSessionId) {
    throw new Error("录音会话尚未恢复，请重新开始录音。");
  }
  if (navigator.mediaDevices.enumerateDevices) {
    const devices = await navigator.mediaDevices.enumerateDevices();
    if (!devices.some((device) => device.kind === "audioinput")) {
      throw new DOMException("No audio input device", "NotFoundError");
    }
  }
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });
  if (appState.browserRecordingRequestId !== requestId) {
    stream.getTracks().forEach((track) => track.stop());
    return;
  }
  const AudioContextClass = window.AudioContext || window.webkitAudioContext;
  const audioContext = new AudioContextClass();
  await audioContext.resume();
  const source = audioContext.createMediaStreamSource(stream);
  const processor = audioContext.createScriptProcessor(4096, Math.max(1, source.channelCount || 1), 1);
  processor.onaudioprocess = (event) => {
    if (appState.browserRecordingStatus !== "recording") return;
    const input = event.inputBuffer;
    const frameCount = input.length;
    const channelCount = Math.max(1, input.numberOfChannels || 1);
    const mixed = new Float32Array(frameCount);
    for (let channel = 0; channel < channelCount; channel += 1) {
      const data = input.getChannelData(channel);
      for (let index = 0; index < frameCount; index += 1) {
        mixed[index] += data[index] / channelCount;
      }
    }
    appState.browserRecordingChunkBuffer.push(mixed);
    appState.browserRecordingRecordedSamples += mixed.length;
  };
  source.connect(processor);
  processor.connect(audioContext.destination);
  appState.browserRecordingStream = stream;
  appState.browserRecordingAudioContext = audioContext;
  appState.browserRecordingSource = source;
  appState.browserRecordingProcessor = processor;
  appState.browserRecordingSampleRate = audioContext.sampleRate;
}

async function completeBrowserRecordingUpload() {
  if (!appState.browserRecordingSessionId) {
    throw new Error("录音会话尚未创建，请重新开始录音。");
  }
  await waitForBrowserRecordingUploads(appState.browserRecordingSessionId);
  if (!appState.browserRecordingFinalized?.audio_id) {
    await finalizeBrowserRecording();
  }
  const completed = await api(`/api/asr/sessions/${encodeURIComponent(appState.browserRecordingSessionId)}/complete`, {
    method: "POST",
  });
  appState.currentAsrSessionId = completed.session_id;
  appState.currentAudioId = completed.audio_id;
  appState.uploadedFilename = completed.filename || completed.audio_id;
  applyUploadedAudioMetadata(completed);
  appState.taskStatus = "TRANSCRIBING";
  setBusy(true, `正在使用 ${ENGINE_LABELS[completed.engine] || completed.engine} 转写录音...`);
  return new Promise((resolve, reject) => {
    listenForAsrEvents(completed.events_url, { resolve, reject });
  });
}

async function startBrowserRecording() {
  clearActionError();
  releaseBrowserRecordingPreview();
  appState.browserRecordingChunkBuffer = [];
  appState.browserRecordingChunkIndex = 0;
  appState.browserRecordingRecordedChunks = 0;
  appState.browserRecordingUploadedChunks = 0;
  appState.browserRecordingPendingChunks = 0;
  appState.browserRecordingRetryStatus = "";
  appState.browserRecordingMissingChunks = [];
  appState.browserRecordingSessionId = "";
  appState.browserRecordingFinalized = null;
  appState.browserRecordingPausedAt = 0;
  appState.browserRecordingTotalPausedMs = 0;
  appState.browserRecordingElapsedSeconds = 0;
  appState.browserRecordingRecordedSamples = 0;
  appState.browserRecordingMessage = "";
  appState.browserRecordingChunkStatus = "";
  const requestId = appState.browserRecordingRequestId + 1;
  appState.browserRecordingRequestId = requestId;
  if (appState.browserRecordingRetryTimer) {
    window.clearTimeout(appState.browserRecordingRetryTimer);
    appState.browserRecordingRetryTimer = null;
  }

  if (!navigator.mediaDevices?.getUserMedia) {
    setBrowserRecordingError("当前浏览器不支持麦克风录音，请使用最新版 Chrome 或 Edge。");
    return;
  }
  if (!secureBrowserRecordingContext()) {
    setBrowserRecordingError("浏览器录音需要 HTTPS 或 localhost 环境，请切换安全地址后重试。");
    return;
  }

  appState.browserRecordingStatus = "requesting";
  appState.browserRecordingMessage = "正在请求麦克风权限...";
  renderAll();

  let stream = null;
  let audioContext = null;
  try {
    if (navigator.mediaDevices.enumerateDevices) {
      const devices = await navigator.mediaDevices.enumerateDevices();
      if (!browserRecordingRequestActive(requestId)) return;
      if (devices.length && !devices.some((device) => device.kind === "audioinput")) {
        throw new DOMException("No audio input device", "NotFoundError");
      }
    }
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    if (!browserRecordingRequestActive(requestId)) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    if (!stream.getAudioTracks().length) {
      throw new DOMException("No audio input track", "NotFoundError");
    }
    const engine = $("recordingEngineSelect").value;
    await ensureBrowserRecordingSession(engine);
    if (!browserRecordingRequestActive(requestId)) {
      stream.getTracks().forEach((track) => track.stop());
      return;
    }
    const AudioContextClass = window.AudioContext || window.webkitAudioContext;
    audioContext = new AudioContextClass();
    await audioContext.resume();
    if (!browserRecordingRequestActive(requestId)) {
      stream.getTracks().forEach((track) => track.stop());
      audioContext.close().catch(() => {});
      return;
    }
    const source = audioContext.createMediaStreamSource(stream);
    const processor = audioContext.createScriptProcessor(4096, Math.max(1, source.channelCount || 1), 1);
    processor.onaudioprocess = (event) => {
      if (appState.browserRecordingStatus !== "recording") return;
      const input = event.inputBuffer;
      const frameCount = input.length;
      const channelCount = Math.max(1, input.numberOfChannels || 1);
      const mixed = new Float32Array(frameCount);
      for (let channel = 0; channel < channelCount; channel += 1) {
        const data = input.getChannelData(channel);
        for (let index = 0; index < frameCount; index += 1) {
          mixed[index] += data[index] / channelCount;
        }
      }
      appState.browserRecordingChunkBuffer.push(mixed);
      appState.browserRecordingRecordedSamples += mixed.length;
    };
    source.connect(processor);
    processor.connect(audioContext.destination);

    appState.browserRecordingStream = stream;
    appState.browserRecordingAudioContext = audioContext;
    appState.browserRecordingSource = source;
    appState.browserRecordingProcessor = processor;
    appState.browserRecordingSampleRate = audioContext.sampleRate;
    appState.browserRecordingStartedAt = Date.now();
    appState.browserRecordingStatus = "recording";
    appState.browserRecordingMessage = "录音中，音频会自动分块上传；最长支持 30 分钟。";
    startBrowserRecordingIntervals();
    renderAll();
  } catch (error) {
    if (browserRecordingRequestActive(requestId)) {
      if (stream) stream.getTracks().forEach((track) => track.stop());
      if (audioContext) audioContext.close().catch(() => {});
      setBrowserRecordingError(browserRecordingErrorMessage(error));
    }
  }
}

async function pauseBrowserRecording() {
  if (appState.browserRecordingStatus !== "recording") return;
  appState.browserRecordingPausedAt = Date.now();
  appState.browserRecordingStatus = "paused";
  if (appState.browserRecordingTimer) window.clearInterval(appState.browserRecordingTimer);
  if (appState.browserRecordingChunkTimer) window.clearInterval(appState.browserRecordingChunkTimer);
  appState.browserRecordingTimer = null;
  appState.browserRecordingChunkTimer = null;
  appState.browserRecordingMessage = "录音已暂停；已录内容会继续保留，可恢复录音或结束上传。";
  renderAll();
  await flushBrowserRecordingChunk({ force: true });
  showToast("录音已暂停");
}

async function resumeBrowserRecording() {
  if (appState.browserRecordingStatus !== "paused") return;
  if (!navigator.mediaDevices?.getUserMedia) {
    setBrowserRecordingError("当前浏览器不支持麦克风录音，请使用最新版 Chrome 或 Edge。");
    return;
  }
  if (!secureBrowserRecordingContext()) {
    setBrowserRecordingError("浏览器录音需要 HTTPS 或 localhost 环境，请切换安全地址后重试。");
    return;
  }
  const requestId = appState.browserRecordingRequestId + 1;
  appState.browserRecordingRequestId = requestId;
  if (!appState.browserRecordingProcessor) {
    appState.browserRecordingStatus = "requesting";
    appState.browserRecordingMessage = "正在恢复麦克风录音...";
    renderAll();
    try {
      await startBrowserRecordingCaptureForExistingSession(requestId);
    } catch (error) {
      if (appState.browserRecordingRequestId === requestId) {
        setBrowserRecordingError(browserRecordingErrorMessage(error));
      }
      return;
    }
  }
  if (appState.browserRecordingPausedAt) {
    appState.browserRecordingTotalPausedMs += Date.now() - appState.browserRecordingPausedAt;
  }
  appState.browserRecordingPausedAt = 0;
  if (!appState.browserRecordingStartedAt) {
    appState.browserRecordingStartedAt = Date.now();
  }
  appState.browserRecordingStatus = "recording";
  appState.browserRecordingMessage = "录音已恢复，音频块会继续按顺序上传。";
  startBrowserRecordingIntervals();
  renderAll();
  showToast("录音已恢复");
}

async function stopBrowserRecording({ auto = false } = {}) {
  if (!["recording", "paused"].includes(appState.browserRecordingStatus)) return;
  const effectiveNow = appState.browserRecordingStatus === "paused"
    ? appState.browserRecordingPausedAt || Date.now()
    : Date.now();
  const elapsed = (effectiveNow - appState.browserRecordingStartedAt - appState.browserRecordingTotalPausedMs) / 1000;
  appState.browserRecordingElapsedSeconds = Math.min(elapsed, MAX_BROWSER_RECORDING_SECONDS);
  cleanupBrowserRecordingCapture();

  if ((appState.browserRecordingRecordedSamples || 0) === 0 || appState.browserRecordingElapsedSeconds < MIN_BROWSER_RECORDING_SECONDS) {
    releaseBrowserRecordingPreview();
    appState.browserRecordingStatus = "error";
    appState.browserRecordingMessage = "未录到有效声音，请重新录制。";
    renderAll();
    showToast("未录到有效声音，请重新录制");
    return;
  }

  try {
    await flushBrowserRecordingChunk({ force: true });
    await finalizeBrowserRecording();
  } catch (error) {
    appState.browserRecordingStatus = "error";
    appState.browserRecordingMessage = `录音已停止，但仍需补传音频块：${error?.message || String(error)}`;
    renderAll();
    return;
  }

  appState.browserRecordingMessage = auto
    ? "已达到最长 30 分钟录音限制，可先试听再上传生成病历。"
    : "录音已停止，可先试听再上传生成病历。";
  renderAll();
  showToast(auto ? "已达到最长 30 分钟录音限制" : "录音已停止");
}

async function cancelBrowserRecording({ silent = false } = {}) {
  const sessionId = appState.browserRecordingSessionId;
  appState.browserRecordingRequestId += 1;
  if (appState.browserRecordingSessionId && appState.currentAsrSessionId === appState.browserRecordingSessionId) {
    appState.currentAsrSessionId = null;
    updateSessionUrl("");
  }
  cleanupBrowserRecordingCapture();
  releaseBrowserRecordingPreview();
  appState.browserRecordingChunkBuffer = [];
  if (appState.browserRecordingRetryTimer) {
    window.clearTimeout(appState.browserRecordingRetryTimer);
    appState.browserRecordingRetryTimer = null;
  }
  let serverCleanupConfirmed = !sessionId;
  if (sessionId) {
    try {
      await api(`/api/asr/sessions/${encodeURIComponent(sessionId)}/recording`, { method: "DELETE" });
      await deleteBrowserRecordingCleanup(sessionId).catch(() => undefined);
      serverCleanupConfirmed = true;
    } catch (error) {
      await putBrowserRecordingCleanup(sessionId, "cancel").catch(() => undefined);
      appState.browserRecordingRetryStatus = "取消清理待网络恢复后重试";
      if (!silent && window.navigator.onLine) reportActionError(error);
    }
    if (serverCleanupConfirmed) {
      await clearBrowserRecordingQueue(sessionId).catch(() => undefined);
    }
  }
  appState.browserRecordingChunkIndex = 0;
  appState.browserRecordingRecordedChunks = 0;
  appState.browserRecordingUploadedChunks = 0;
  appState.browserRecordingPendingChunks = 0;
  appState.browserRecordingRetryStatus = "";
  appState.browserRecordingMissingChunks = [];
  appState.browserRecordingSessionId = "";
  appState.browserRecordingChunkStatus = "";
  appState.browserRecordingPausedAt = 0;
  appState.browserRecordingTotalPausedMs = 0;
  appState.browserRecordingStartedAt = 0;
  appState.browserRecordingElapsedSeconds = 0;
  appState.browserRecordingSampleRate = 0;
  appState.browserRecordingRecordedSamples = 0;
  appState.browserRecordingStatus = "idle";
  appState.browserRecordingMessage = silent
    ? ""
    : (serverCleanupConfirmed ? "录音已取消。" : "取消请求已保存，网络恢复后会自动清理服务端录音。");
  appState.browserRecordingFinalized = null;
  appState.browserRecordingFile = null;
  renderAll();
  if (!silent) showToast(serverCleanupConfirmed ? "录音已取消" : "取消请求已保存，网络恢复后会自动清理");
}

async function submitBrowserRecording() {
  try {
    if (!appState.browserRecordingFinalized?.audio_id) {
      throw new Error("请先完成录音并试听确认。");
    }
    appState.browserRecordingStatus = "uploading";
    appState.browserRecordingMessage = "正在启动转写并生成病历...";
    renderAll();
    closeDrawer();
    appState.audioMode = "generate";
    const transcribed = await completeBrowserRecordingUpload();
    await continueGeneratingFromTranscription(transcribed);
    appState.browserRecordingStatus = "recorded";
    appState.browserRecordingMessage = "录音已合并上传，正在等待生成流程。";
    renderBrowserRecordingPanel();
  } catch (error) {
    appState.browserRecordingStatus = appState.browserRecordingFile ? "recorded" : "error";
    appState.browserRecordingMessage = `上传失败：${error?.message || String(error)}`;
    setBusy(false);
    renderAll();
    reportActionError(error);
  }
}

function openReservedRecording() {
  closeInputMethodMenu();
  clearActionError();
  appState.audioMode = "generate";
  $("recordingEngineSelect").value = appState.selectedEngine;
  openDrawer("recordingPanel", "浏览器录音生成病历");
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

function openRoleReview() {
  openDetailDrawer("说话人身份确认", renderTranscriptDetailContent("role-review"));
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
  $("displaySettingsButton").addEventListener("click", (event) => {
    event.stopPropagation();
    toggleDisplaySettingsMenu();
  });
  $("openWorklistButton").addEventListener("click", () => {
    openEncounterWorklist();
  });
  $("inputMethodMenu").addEventListener("click", (event) => {
    const button = event.target.closest("[data-input-method]");
    if (!button) return;
    handleInputMethod(button.dataset.inputMethod);
  });
  document.addEventListener("click", (event) => {
    if (appState.inputMenuOpen && !event.target.closest(".input-method-menu")) {
      closeInputMethodMenu();
    }
    if (appState.settingsOpen && !event.target.closest(".display-settings-menu")) {
      closeDisplaySettingsMenu();
    }
  });
  document.querySelectorAll("[data-product-view-target]").forEach((button) => {
    button.addEventListener("click", () => setProductView(button.dataset.productViewTarget));
  });
  window.addEventListener("hashchange", () => {
    const view = productViewFromHash();
    if (view) setProductView(view, { updateHash: false });
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
  $("refreshWorklistButton").addEventListener("click", () => {
    refreshEncounterWorklist();
  });
  $("encounterSearchInput").addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    refreshEncounterWorklist();
  });
  $("encounterStatusFilter").addEventListener("change", () => {
    refreshEncounterWorklist();
  });
  $("encounterWorklist").addEventListener("click", async (event) => {
    const button = event.target.closest("[data-restore-encounter]");
    if (!button) return;
    await restoreEncounter(button.dataset.restoreEncounter);
  });
  $("dashboardEncounterList")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-restore-encounter]");
    if (!button) return;
    await restoreEncounter(button.dataset.restoreEncounter);
  });
  $("dashboardRefreshWorklistButton")?.addEventListener("click", () => {
    refreshEncounterWorklist().catch(reportActionError);
  });
  $("dashboardOpenWorklistButton")?.addEventListener("click", openEncounterWorklist);
  $("refreshAdminHomeButton")?.addEventListener("click", () => {
    refreshAdminHome().catch(reportActionError);
  });
  $("submitTextButton").addEventListener("click", submitTextImport);
  $("submitAudioButton").addEventListener("click", submitAudio);
  $("startBrowserRecordingButton").addEventListener("click", startBrowserRecording);
  $("pauseBrowserRecordingButton").addEventListener("click", () => {
    pauseBrowserRecording().catch(reportActionError);
  });
  $("resumeBrowserRecordingButton").addEventListener("click", () => {
    resumeBrowserRecording().catch(reportActionError);
  });
  $("stopBrowserRecordingButton").addEventListener("click", () => {
    stopBrowserRecording().catch(reportActionError);
  });
  $("cancelBrowserRecordingButton").addEventListener("click", () => cancelBrowserRecording());
  $("retryBrowserRecordingChunksButton").addEventListener("click", () => {
    retryFailedBrowserRecordingChunks().catch(reportActionError);
  });
  $("submitBrowserRecordingButton").addEventListener("click", submitBrowserRecording);
  window.addEventListener("online", () => {
    processPendingBrowserRecordingCleanups().catch(reportActionError);
    if (appState.browserRecordingSessionId) {
      appState.browserRecordingRetryStatus = "网络已恢复，正在补传音频块";
      pumpBrowserRecordingUploadQueue().catch(reportActionError);
    }
  });
  $("enrollDoctorProfileButton").addEventListener("click", enrollDoctorProfile);
  $("doctorProfileSelect").addEventListener("change", (event) => {
    appState.selectedDoctorProfileId = event.target.value;
  });
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
    $("recordingEngineSelect").value = appState.selectedEngine;
    renderPatientBar();
  });
  $("audioEngineSelect").addEventListener("change", () => {
    appState.selectedEngine = $("audioEngineSelect").value;
    $("topAsrEngineSelect").value = appState.selectedEngine;
    $("recordingEngineSelect").value = appState.selectedEngine;
    renderPatientBar();
  });
  $("recordingEngineSelect").addEventListener("change", () => {
    appState.selectedEngine = $("recordingEngineSelect").value;
    $("topAsrEngineSelect").value = appState.selectedEngine;
    $("audioEngineSelect").value = appState.selectedEngine;
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
      const target = $("drawerTitle").textContent === "说话人身份确认" ? "role-review" : "all";
      $("detailDrawerContent").innerHTML = renderTranscriptDetailContent(target);
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
    const mergeButton = event.target.closest("[data-speaker-merge-source]");
    if (mergeButton) {
      const group = mergeButton.closest(".speaker-role-group");
      const targetSelect = group?.querySelector("[data-speaker-merge-target]");
      try {
        await mergeSpeakerGroup(mergeButton.dataset.speakerMergeSource, targetSelect?.value);
        const target = $("drawerTitle").textContent === "说话人身份确认" ? "role-review" : "all";
        $("detailDrawerContent").innerHTML = renderTranscriptDetailContent(target);
      } catch (error) {
        reportActionError(error);
      }
      return;
    }
    const undoMergeButton = event.target.closest("[data-undo-speaker-merge]");
    if (undoMergeButton) {
      undoLastSpeakerMerge();
      const target = $("drawerTitle").textContent === "说话人身份确认" ? "role-review" : "all";
      $("detailDrawerContent").innerHTML = renderTranscriptDetailContent(target);
      return;
    }
    const saveButton = event.target.closest("[data-save-role-review]");
    if (!saveButton) return;
    try {
      await saveRoleReview();
      const target = $("drawerTitle").textContent === "说话人身份确认" ? "role-review" : "all";
      $("detailDrawerContent").innerHTML = renderTranscriptDetailContent(target);
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
  $("loginForm").addEventListener("submit", submitLogin);
  $("logoutButton").addEventListener("click", logout);
}

async function init() {
  appState.productView = productViewFromHash() || "workbench";
  bindEvents();
  await refreshAuth();
  await processPendingBrowserRecordingCleanups().catch(() => undefined);
  renderAll();
  if (appState.authUser) {
    refreshEncounterWorklist().catch(reportActionError);
  }
  startAsrPrewarmPolling();
  refreshLlmStatus();
  await restoreAsrSessionFromUrl();
}

init();
