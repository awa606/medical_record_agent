const appState = {
  currentTaskId: null,
  currentAudioId: null,
  currentAsrResult: null,
  currentEvaluation: null,
  currentTask: null,
  currentSteps: [],
  currentRecordFields: null,
  currentDraft: "",
  currentSafetyCheck: null,
  currentAgentTrace: null,
  currentLlmStatus: null,
};

const uiState = {
  audioMode: "transcribe",
  selectedEngine: "funasr",
  selectedEvidenceField: "chief_complaint",
  highlightedEvidenceText: "",
};

const WORKFLOW_STEPS = [
  { key: "CREATED", label: "1.输入/上传" },
  { key: "TRANSCRIBED", label: "2.对话转写" },
  { key: "GENERATING_DRAFT", label: "3.病历草稿" },
  { key: "WAITING_DOCTOR_REVIEW", label: "4.医生审核" },
  { key: "EXPORTED", label: "5.确认导出" },
];

const STATUS_TO_STEP = {
  CREATED: "CREATED",
  EXTRACTING_FIELDS: "GENERATING_DRAFT",
  GENERATING_DRAFT: "GENERATING_DRAFT",
  SAFETY_CHECKING: "GENERATING_DRAFT",
  WAITING_DOCTOR_REVIEW: "WAITING_DOCTOR_REVIEW",
  FAILED: "WAITING_DOCTOR_REVIEW",
  reviewed: "WAITING_DOCTOR_REVIEW",
  approved: "WAITING_DOCTOR_REVIEW",
  exported: "EXPORTED",
};

const ENGINE_LABELS = {
  mock: "Mock ASR",
  funasr: "FunASR",
  sensevoice: "SenseVoice Small",
  whisper: "Whisper Base",
  qwen3: "Qwen3-ASR 0.6B",
  online: "Online ASR",
  "sensevoice-small": "SenseVoice Small",
  "whisper-base": "Whisper Base",
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

const $ = (id) => document.getElementById(id);

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function renderJson(element, value) {
  if (!element) return;
  element.textContent = value ? JSON.stringify(value, null, 2) : "-";
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
    alert("运行日志命令已复制");
  } catch (_error) {
    alert(command);
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail || data));
  }
  return data;
}

function updateTopbar() {
  const llm = llmDisplayState();
  $("sessionId").textContent = appState.currentTaskId
    ? `T-${appState.currentTaskId}`
    : appState.currentAudioId
      ? `A-${appState.currentAudioId}`
      : "未创建";
  $("currentEngineLabel").textContent = ENGINE_LABELS[uiState.selectedEngine] || uiState.selectedEngine;
  $("llmProviderLabel").textContent = llm.provider;
  $("llmModelLabel").textContent = llm.model;
  $("llmFallbackLabel").textContent = llm.fallbackLabel;
  if ($("debugTaskIdLabel")) $("debugTaskIdLabel").textContent = appState.currentTaskId || "-";
  if ($("debugAudioIdLabel")) $("debugAudioIdLabel").textContent = appState.currentAudioId || "-";
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
  return { provider, model, fallbackLabel };
}

function renderWorkflowStatus(status = "CREATED") {
  const activeKey = STATUS_TO_STEP[status] || status || "CREATED";
  const failed = status === "FAILED";
  $("workflowSteps").innerHTML = WORKFLOW_STEPS.map((step) => {
    const className = `step ${failed && step.key === activeKey ? "failed" : step.key === activeKey ? "active" : ""}`;
    return `<li class="${className}">${step.label}</li>`;
  }).join("");
}

function fieldStatus(field, key) {
  if (key === "treatment_plan") {
    return field?.value ? { key: "confirmed", label: "已确认" } : { key: "missing", label: "待补充" };
  }
  if (key === "physical_exam" && (!field || field.missing || !field.value || field.value.includes("待医生"))) {
    return { key: "missing", label: "待补充" };
  }
  if (field?.confirmed_by_doctor) return { key: "confirmed", label: "已确认" };
  if (field?.missing) return { key: "missing", label: "待补充" };
  if (typeof field?.confidence === "number" && field.confidence < 0.7) return { key: "low", label: "低置信度" };
  return { key: "confirmed", label: "已确认" };
}

function fieldValue(fields, key) {
  const field = fields?.[key];
  if (key === "treatment_plan") return field?.value || "待医生补充处理建议";
  if (key === "physical_exam" && (!field || field.missing || !field.value)) return field?.hint || "待医生查体补充";
  return field?.value || field?.hint || "";
}

function evidenceHtml(field, fieldKey) {
  const spans = field?.source_spans || [];
  if (!spans.length) return `<div class="muted">暂无证据片段，需结合原始转写复核。</div>`;
  return spans.map((span, index) => `
    <button type="button" class="ghost-button" onclick="selectEvidence('${fieldKey}', ${index})">
      ${escapeHtml(span.text || "证据片段")}
    </button>
  `).join("");
}

function renderRecordFields() {
  const fields = appState.currentRecordFields;
  if (!fields) {
    $("recordFields").innerHTML = `<div class="empty-copy">暂无病历字段，请输入文本或上传音频。</div>`;
    $("fieldSummary").textContent = "空状态";
    $("fieldSummary").className = "status-badge neutral";
    return;
  }

  let missingCount = 0;
  const cards = FIELD_DEFS.map(([key, title]) => {
    const field = fields[key] || {};
    const status = fieldStatus(field, key);
    const value = fieldValue(fields, key);
    if (status.key === "missing") missingCount += 1;
    return `
      <article class="field-card ${status.key}" data-field="${key}">
        <div class="field-title-row">
          <span class="field-title">${title}</span>
          <span class="status-badge ${status.key}">${status.label}</span>
        </div>
        <div class="field-value" data-field-value="${key}">${escapeHtml(value || "暂无内容")}</div>
        <div class="field-actions">
          <button type="button" onclick="editField('${key}')">编辑</button>
          <button type="button" onclick="toggleEvidence('${key}')">证据</button>
        </div>
        <div id="evidence-${key}" class="evidence-area">${evidenceHtml(field, key)}</div>
      </article>
    `;
  }).join("");

  const candidateDiagnoses = fields.candidate_diagnoses || [];
  const diagnoses = (candidateDiagnoses.length ? candidateDiagnoses : [{ name: "暂无候选诊断", status: "候选待确认" }]).map((diagnosis, index) => `
    <article class="field-card low">
      <div class="field-title-row">
        <span class="field-title">候选诊断</span>
        <span class="status-badge low">候选待确认</span>
      </div>
      <div class="field-value">${escapeHtml(diagnosis.name || "未命名诊断")}</div>
      <div class="field-actions">
        <button type="button" onclick="selectDiagnosisEvidence(${index})" ${candidateDiagnoses.length ? "" : "disabled"}>证据</button>
      </div>
    </article>
  `).join("");

  $("recordFields").innerHTML = cards + diagnoses;
  $("fieldSummary").textContent = missingCount ? `${missingCount}项待补充` : "待医生确认";
  $("fieldSummary").className = `status-badge ${missingCount ? "missing" : "confirmed"}`;
}

function toggleEvidence(key) {
  const node = $(`evidence-${key}`);
  if (node) node.classList.toggle("open");
}

function selectEvidence(fieldKey, index) {
  const span = appState.currentRecordFields?.[fieldKey]?.source_spans?.[index];
  uiState.selectedEvidenceField = fieldKey;
  uiState.highlightedEvidenceText = span?.text || "";
  renderTranscript();
  renderEvidencePanel();
}

function selectDiagnosisEvidence(index) {
  const diagnosis = appState.currentRecordFields?.candidate_diagnoses?.[index];
  uiState.selectedEvidenceField = `diagnosis:${index}`;
  uiState.highlightedEvidenceText = diagnosis?.evidence?.[0]?.text || "";
  renderTranscript();
  renderEvidencePanel();
}

function editField(key) {
  if (!appState.currentRecordFields) return;
  if (!appState.currentRecordFields[key]) {
    appState.currentRecordFields[key] = { value: "", missing: true, confidence: 0.6, source_spans: [] };
  }
  const card = document.querySelector(`[data-field="${key}"]`);
  const value = fieldValue(appState.currentRecordFields, key);
  card.querySelector(`[data-field-value="${key}"]`).innerHTML = `
    <textarea data-edit-text="${key}">${escapeHtml(value)}</textarea>
    <div class="field-actions">
      <button type="button" onclick="saveFieldEdit('${key}')">保存</button>
      <button type="button" onclick="renderRecordFields()">取消</button>
    </div>
  `;
}

function saveFieldEdit(key) {
  const input = document.querySelector(`[data-edit-text="${key}"]`);
  const nextValue = input.value.trim();
  const field = appState.currentRecordFields[key] || {};
  field.value = nextValue || null;
  field.missing = !nextValue;
  field.confirmed_by_doctor = Boolean(nextValue);
  appState.currentRecordFields[key] = field;
  renderRecordFields();
  renderRightColumn();
}

function classifySpeaker(line, segment) {
  const raw = `${segment?.role || ""} ${segment?.speaker || ""} ${line}`.toLowerCase();
  if (raw.includes("医生") || raw.includes("doctor")) return "doctor";
  if (raw.includes("患者") || raw.includes("patient")) return "patient";
  if (raw.includes("[医生]")) return "doctor";
  return "patient";
}

function transcriptLines() {
  const asr = appState.currentAsrResult;
  if (!asr) return [];
  if (Array.isArray(asr.segments) && asr.segments.length > 1) {
    return asr.segments.map((segment, index) => ({
      text: segment.text || "",
      speaker: classifySpeaker(segment.text || "", segment),
      time: segment.start_time != null ? `${Number(segment.start_time).toFixed(1)}s` : `00:${String(index * 8).padStart(2, "0")}`,
    }));
  }
  const normalizedText = String(asr.conversation_text || asr.text || "")
    .replace(/\s*(\[(?:医生|患者|doctor|patient|待校正)\])/gi, "\n$1")
    .trim();
  return normalizedText
    .split(/\n+/)
    .map((line, index) => line.trim())
    .filter(Boolean)
    .map((line, index) => ({
      text: line.replace(/^\[(医生|患者|doctor|patient|待校正)\]\s*/i, ""),
      speaker: classifySpeaker(line, null),
      time: `00:${String(index * 8).padStart(2, "0")}`,
    }));
}

function renderTranscript() {
  const asr = appState.currentAsrResult;
  if (!asr) {
    $("transcriptView").innerHTML = `<div class="empty-copy">暂无对话转写。</div>`;
    $("transcriptSummary").textContent = "暂无对话转写";
    return;
  }

  const warning = asr.role_strategy === "single_segment_needs_review"
    ? `<div class="safety-strip warning">当前 ASR 返回单段长文本，医生/患者角色需人工校正。</div>`
    : "";
  const rows = transcriptLines().map((item) => {
    const highlighted = uiState.highlightedEvidenceText && item.text.includes(uiState.highlightedEvidenceText);
    return `
      <div class="chat-row">
        <div class="chat-time">${escapeHtml(item.time)}</div>
        <div class="chat-card ${highlighted ? "evidence-highlight" : ""}">
          <span class="speaker-tag ${item.speaker}">${item.speaker === "doctor" ? "医生" : "患者"}</span>
          ${escapeHtml(item.text)}
        </div>
      </div>
    `;
  }).join("");

  $("transcriptView").innerHTML = warning + (rows || `<div class="empty-copy">暂无对话转写。</div>`);
  $("transcriptSummary").textContent = `${asr.engine || "ASR"} · ${asr.segments?.length || 0}段`;
}

function missingItems() {
  const fields = appState.currentRecordFields;
  if (!fields) return [];
  return FIELD_DEFS.filter(([key]) => fieldStatus(fields?.[key], key).key === "missing").map(([, label]) => label);
}

function renderMissingPanel() {
  const missing = missingItems();
  $("missingPanel").innerHTML = `
    <h3>缺失项提醒</h3>
    ${missing.length ? `<div class="safety-strip danger">${escapeHtml(missing.join("、"))}</div>` : `<div class="safety-strip success">暂无缺失项。</div>`}
  `;
}

function renderCandidatePanel() {
  const diagnoses = appState.currentRecordFields?.candidate_diagnoses || [];
  $("candidatePanel").innerHTML = `
    <h3>候选诊断</h3>
    ${diagnoses.length ? diagnoses.map((diagnosis, index) => `
      <div class="safety-strip warning">
        <strong>${escapeHtml(diagnosis.name || "未命名诊断")}</strong><br />
        <span class="muted">${escapeHtml(diagnosis.status || "候选待确认")}</span>
      </div>
    `).join("") : `<div class="empty-copy">暂无候选诊断。</div>`}
  `;
}

function renderEvidencePanel() {
  const fields = appState.currentRecordFields;
  const selected = uiState.selectedEvidenceField || "chief_complaint";
  let title = "字段证据";
  let spans = [];
  if (selected.startsWith("diagnosis:")) {
    const diagnosis = fields?.candidate_diagnoses?.[Number(selected.split(":")[1])];
    title = `字段证据：${diagnosis?.name || "候选诊断"}`;
    spans = diagnosis?.evidence || [];
  } else {
    const label = FIELD_DEFS.find(([key]) => key === selected)?.[1] || selected;
    title = `字段证据：${label}`;
    spans = fields?.[selected]?.source_spans || [];
  }
  $("evidencePanel").innerHTML = `
    <h3>${escapeHtml(title)}</h3>
    ${spans.length ? spans.map((span) => `
      <div class="safety-strip">
        ${escapeHtml(span.text || "")}
      </div>
    `).join("") : `<div class="empty-copy">暂无字段证据。</div>`}
  `;
}

function renderSafetyPanel() {
  const safety = appState.currentSafetyCheck;
  const asr = appState.currentAsrResult;
  const warnings = [...(asr?.warnings || []), ...(safety?.warnings || [])];
  if (asr?.role_strategy === "single_segment_needs_review") warnings.unshift("医生/患者角色需人工校正");
  const errors = safety?.errors || [];
  const evalMissing = appState.currentEvaluation?.medical_keywords?.missing || [];
  const blocks = [];
  warnings.forEach((item) => blocks.push(`<div class="safety-strip warning">${escapeHtml(item)}</div>`));
  errors.forEach((item) => blocks.push(`<div class="safety-strip danger">${escapeHtml(item)}</div>`));
  blocks.push(safety
    ? `<div class="safety-strip ${safety.passed && !safety.blocked ? "success" : "danger"}">安全校验结果：${safety.passed ? "通过" : "未通过"}${safety.blocked ? " / 阻止导出" : ""}</div>`
    : `<div class="empty-copy">暂无AI校验结果。</div>`);
  if (appState.currentEvaluation) {
    blocks.push(`<div class="safety-strip">ASR评测摘要：CER ${Number(appState.currentEvaluation.cer ?? 0).toFixed(4)}，keyword_recall ${Number(appState.currentEvaluation.keyword_recall ?? 0).toFixed(2)}，missing ${escapeHtml(evalMissing.join("、") || "无")}</div>`);
  }
  $("safetyPanel").innerHTML = `<h3>安全校验结果</h3>${blocks.join("")}`;
  renderJson($("debugSafetyJson"), safety);
}

function buildLocalAgentTrace() {
  const asr = appState.currentAsrResult;
  const task = appState.currentTask || {};
  const llmStatus = appState.currentLlmStatus || {};
  const llmFallback = llmStatus.configured === false || llmStatus.checked
    ? Boolean(llmStatus.fallback)
    : false;
  const inputType = asr && asr.audio_id ? "audio" : "text";
  const plan = inputType === "audio"
    ? ["ASR_TRANSCRIBE", "FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK", "DOCTOR_REVIEW"]
    : ["TEXT_INPUT_NORMALIZE", "FIELD_EXTRACTION", "DRAFT_GENERATION", "SAFETY_CHECK", "DOCTOR_REVIEW"];
  return {
    agent_mode: "Plan-and-Execute + Human-in-the-loop",
    input_type: inputType,
    perception: inputType === "audio"
      ? {
          source: "audio_asr",
          asr_engine: asr?.engine || uiState.selectedEngine,
          audio_id: asr?.audio_id || appState.currentAudioId,
          role_strategy: asr?.role_strategy || null,
          warnings: asr?.warnings || [],
          segments_count: asr?.segments?.length || 0,
        }
      : {
          source: "text_input",
          text_length: (asr?.conversation_text || asr?.text || "").length,
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
      next_state: task.status || "CREATED",
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
    updateTopbar();
    renderDebugJson();
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
    updateTopbar();
    return appState.currentLlmStatus;
  }
}

async function testLlmConnection() {
  const status = await refreshLlmStatus({ test: true });
  const message = status.reachable
    ? `LLM自检通过：${status.provider} / ${status.model}`
    : `LLM自检未通过，运行时将使用 ${status.fallback_provider || "mock"} 兜底`;
  alert(message);
  renderAll();
}

function renderRightColumn() {
  renderMissingPanel();
  renderCandidatePanel();
  renderEvidencePanel();
  renderSafetyPanel();
}

function renderDebugJson() {
  const llm = currentAgentTrace().llm || {};
  const debugRunLog = $("debugRunLogCommand");
  if (debugRunLog) debugRunLog.textContent = runLogCommand();
  renderJson($("debugAsrJson"), appState.currentAsrResult);
  renderJson($("debugAgentTraceJson"), currentAgentTrace());
  renderJson($("debugLlmTraceJson"), {
    llm_provider: llm.llm_provider,
    model: llm.model,
    latency_ms: llm.latency_ms,
    fallback: llm.fallback,
    fallback_reason: llm.fallback_reason,
  });
  renderJson($("debugTaskJson"), appState.currentTask);
  renderJson($("debugStepsJson"), appState.currentSteps);
  renderJson($("debugSafetyJson"), appState.currentSafetyCheck);
}

function renderAll() {
  updateTopbar();
  renderRecordFields();
  renderTranscript();
  renderRightColumn();
  renderDebugJson();
}

function openDrawer(sectionId, title) {
  $("drawerTitle").textContent = title;
  $("drawerBackdrop").classList.add("active");
  $("drawer").classList.add("active");
  $("drawer").setAttribute("aria-hidden", "false");
  document.querySelectorAll(".drawer-section").forEach((section) => section.classList.remove("active"));
  $(sectionId).classList.add("active");
}

function closeDrawer() {
  $("drawerBackdrop").classList.remove("active");
  $("drawer").classList.remove("active");
  $("drawer").setAttribute("aria-hidden", "true");
}

function openTextInput() {
  openDrawer("textDrawer", "文本导入");
}

function uploadAudioTranscribe() {
  uiState.audioMode = "transcribe";
  $("audioModeHint").textContent = "上传预录音频，仅测试 ASR 转写。";
  $("audioSubmitButton").onclick = submitAudioTranscribe;
  openDrawer("audioDrawer", "上传转写");
}

function uploadAudioGenerateRecord() {
  uiState.audioMode = "generate";
  $("audioModeHint").textContent = "上传预录音频，转写后生成病历。";
  $("audioSubmitButton").onclick = submitAudioGenerateRecord;
  openDrawer("audioDrawer", "上传生成病历");
}

function openEvaluationDrawer() {
  const expected = appState.currentAsrResult?.medical_keywords?.expected || [];
  if (expected.length) $("keywordsInput").value = expected.join("\n");
  openDrawer("evaluationDrawer", "ASR评测");
}

function openDebugDrawer() {
  renderDebugJson();
  openDrawer("debugDrawer", "调试详情");
}

async function submitTextRecord() {
  const text = $("conversationInput").value.trim();
  if (!text) return alert("请输入问诊文本");
  closeDrawer();
  appState.currentAudioId = null;
  appState.currentAsrResult = {
    audio_id: null,
    engine: "text-import",
    text,
    conversation_text: text,
    segments: [],
    duration: null,
    medical_keywords: null,
    warnings: [],
  };
  await createRecordTask(text);
}

async function uploadAndTranscribe(file, engine) {
  if (!file) throw new Error("请选择音频文件");
  uiState.selectedEngine = engine;
  $("uploadStatus").textContent = "上传中";
  updateTopbar();
  const form = new FormData();
  form.append("file", file);
  const uploaded = await api("/api/audio/upload", { method: "POST", body: form });
  appState.currentAudioId = uploaded.audio_id;
  $("uploadStatus").textContent = uploaded.filename || uploaded.audio_id;
  const transcribed = await api(`/api/audio/${uploaded.audio_id}/transcribe?engine=${engine}`, { method: "POST" });
  appState.currentAsrResult = transcribed.asr_result;
  appState.currentAudioId = transcribed.audio_id;
  renderWorkflowStatus("TRANSCRIBED");
  renderAll();
  return transcribed;
}

async function submitAudioTranscribe() {
  try {
    closeDrawer();
    await uploadAndTranscribe($("audioFileInput").files[0], $("audioEngineSelect").value);
  } catch (error) {
    alert(error.message);
  }
}

async function submitAudioGenerateRecord() {
  try {
    closeDrawer();
    const transcribed = await uploadAndTranscribe($("audioFileInput").files[0], $("audioEngineSelect").value);
    const created = await api(`/api/audio/${transcribed.audio_id}/generate-record`, { method: "POST" });
    appState.currentTaskId = created.task_id;
    appState.currentTask = { id: created.task_id, status: created.status };
    renderWorkflowStatus(created.status);
    renderAll();
    listenForEvents(created.task_id, created.events_url);
  } catch (error) {
    alert(error.message);
  }
}

async function createRecordTask(conversationText) {
  appState.currentEvaluation = null;
  appState.currentTask = null;
  appState.currentSteps = [];
  appState.currentRecordFields = null;
  appState.currentDraft = "";
  appState.currentSafetyCheck = null;
  appState.currentAgentTrace = null;
  renderWorkflowStatus("CREATED");
  renderAll();
  const created = await api("/api/records/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ conversation_text: conversationText }),
  });
  appState.currentTaskId = created.task_id;
  appState.currentTask = { id: created.task_id, status: created.status };
  renderWorkflowStatus(created.status);
  renderAll();
  listenForEvents(created.task_id, created.events_url);
}

function listenForEvents(taskId, eventsUrl) {
  const events = new EventSource(eventsUrl);
  let terminalReceived = false;
  ["CREATED", "EXTRACTING_FIELDS", "GENERATING_DRAFT", "SAFETY_CHECKING", "DEGRADED"].forEach((status) => {
    events.addEventListener(status, (event) => {
      const data = JSON.parse(event.data);
      appState.currentTaskId = data.task_id;
      appState.currentTask = { ...(appState.currentTask || {}), id: data.task_id, status: data.status, current_stage: data.current_stage };
      renderWorkflowStatus(data.status);
      renderAll();
    });
  });
  events.addEventListener("WAITING_DOCTOR_REVIEW", async (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    renderWorkflowStatus("WAITING_DOCTOR_REVIEW");
    await refreshTask(data.task_id, data.task);
    events.close();
  });
  events.addEventListener("FAILED", async (event) => {
    const data = JSON.parse(event.data);
    terminalReceived = true;
    renderWorkflowStatus("FAILED");
    await refreshTask(data.task_id, data.task);
    events.close();
  });
  events.onerror = () => {
    if (!terminalReceived) appState.currentTask = { ...(appState.currentTask || {}), status: "事件连接异常" };
    events.close();
    renderAll();
  };
}

async function refreshTask(taskId, taskFromEvent = null) {
  const task = taskFromEvent || await api(`/api/tasks/${taskId}`);
  const steps = await api(`/api/tasks/${taskId}/steps`);
  appState.currentTask = task;
  appState.currentSteps = steps;
  appState.currentTaskId = task.id || task.task_id || taskId;
  const result = task.result_json || {};
  appState.currentRecordFields = result.fields || appState.currentRecordFields;
  appState.currentDraft = result.draft || appState.currentDraft;
  appState.currentSafetyCheck = result.safety_check || appState.currentSafetyCheck;
  await refreshAgentTrace(appState.currentTaskId);
  renderAll();
}

async function runEvaluation() {
  try {
    if (!appState.currentAudioId) throw new Error("暂无可评测的转写");
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
    const missing = appState.currentEvaluation.medical_keywords?.missing || [];
    $("evaluationSummary").innerHTML = `
      <div class="safety-strip ${missing.length ? "warning" : "success"}">
        CER ${Number(appState.currentEvaluation.cer ?? 0).toFixed(4)} · keyword_recall ${Number(appState.currentEvaluation.keyword_recall ?? 0).toFixed(2)} · missing ${escapeHtml(missing.join("、") || "无")}
      </div>
    `;
    renderRightColumn();
  } catch (error) {
    $("evaluationSummary").innerHTML = `<div class="safety-strip danger">${escapeHtml(error.message)}</div>`;
  }
}

async function regenerateRecord() {
  const text = appState.currentAsrResult?.conversation_text || $("conversationInput").value.trim();
  if (!text) return alert("暂无可重新生成的对话文本");
  await createRecordTask(text);
}

async function saveDraftReview() {
  if (!appState.currentTaskId || !appState.currentRecordFields) return alert("暂无可保存的病历字段");
  appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ fields: appState.currentRecordFields }),
  });
  await refreshTask(appState.currentTaskId, appState.currentTask);
}

async function confirmFields() {
  if (!appState.currentTaskId) return alert("暂无可确认的任务");
  appState.currentTask = await api(`/api/tasks/${appState.currentTaskId}/approve`, { method: "POST" });
  await refreshTask(appState.currentTaskId, appState.currentTask);
}

async function exportRecord() {
  if (!appState.currentTaskId) return alert("暂无可导出的任务");
  await api(`/api/tasks/${appState.currentTaskId}/export`, { method: "POST" });
  renderWorkflowStatus("EXPORTED");
}

function init() {
  renderWorkflowStatus("CREATED");
  renderAll();
  refreshLlmStatus();
  $("audioEngineSelect").addEventListener("change", () => {
    uiState.selectedEngine = $("audioEngineSelect").value;
    updateTopbar();
  });
}

Object.assign(window, {
  openTextInput,
  uploadAudioTranscribe,
  uploadAudioGenerateRecord,
  openEvaluationDrawer,
  openDebugDrawer,
  testLlmConnection,
  copyRunLogCommand,
  closeDrawer,
  submitTextRecord,
  submitAudioTranscribe,
  submitAudioGenerateRecord,
  runEvaluation,
  regenerateRecord,
  saveDraftReview,
  confirmFields,
  exportRecord,
  editField,
  saveFieldEdit,
  toggleEvidence,
  selectEvidence,
  selectDiagnosisEvidence,
});

init();
