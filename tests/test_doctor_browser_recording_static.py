from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_recording_panel_is_present() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")

    assert 'id="recordingPanel"' in html
    assert 'id="startBrowserRecordingButton"' in html
    assert 'id="pauseBrowserRecordingButton"' in html
    assert 'id="resumeBrowserRecordingButton"' in html
    assert 'id="stopBrowserRecordingButton"' in html
    assert 'id="cancelBrowserRecordingButton"' in html
    assert 'id="submitBrowserRecordingButton"' in html
    assert 'id="retryBrowserRecordingChunksButton"' in html
    assert 'id="browserRecordingPreview"' in html
    assert 'id="browserRecordingChunkStatus"' in html


def test_doctor_recording_uses_browser_pcm_wav_path() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "navigator.mediaDevices.getUserMedia" in script
    assert "createScriptProcessor" in script
    assert "function encodeWavFromFloat32" in script
    assert 'writeWavString(view, 0, "RIFF")' in script
    assert "window.__MRA_APP_STATE__ = appState" in script
    assert "browserRecordingChunks" not in script
    assert "new File([blob]" not in script
    assert "const MAX_BROWSER_RECORDING_SECONDS = 1800" in script
    assert "window.__MRA_BROWSER_RECORDING_CHUNK_SECONDS || 10" in script


def test_doctor_recording_uses_resumable_chunked_upload_path() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "async function sha256Blob" in script
    assert "indexedDB.open" in script
    assert 'const BROWSER_RECORDING_DB_VERSION = 2' in script
    assert "BROWSER_RECORDING_CLEANUP_STORE" in script
    assert "async function queueBrowserRecordingChunk" in script
    assert "async function pumpBrowserRecordingUploadQueue" in script
    assert "async function processPendingBrowserRecordingCleanups" in script
    assert "/chunks" in script
    assert "/chunks/status" in script
    assert "/finalize" in script
    assert "/complete" in script
    assert "/recording" in script
    assert "pauseBrowserRecording" in script
    assert "resumeBrowserRecording" in script
    assert "Promise.allSettled(appState.browserRecordingChunkUploads)" not in script
    assert "BROWSER_RECORDING_MAX_RETRY_ATTEMPTS" in script


def test_doctor_recording_marks_hash_conflict_without_retry_loop() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "function isBrowserRecordingChunkConflict" in script
    assert 'status: "conflict"' in script
    assert "分块冲突，请取消并重新录制" in script
    assert 'row.status !== "conflict"' in script


def test_playwright_is_not_a_production_dependency() -> None:
    production_requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    dev_requirements = (ROOT / "requirements-dev.txt").read_text(encoding="utf-8")

    assert "playwright" not in production_requirements.lower()
    assert "playwright" in dev_requirements.lower()


def test_doctor_recording_replaces_reserved_placeholder() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    placeholder = "浏览器麦克风录音暂未接入"

    assert placeholder not in script
    assert 'openDrawer("recordingPanel", "浏览器录音生成病历")' in script
    assert "completeBrowserRecordingUpload" in script
    assert "continueGeneratingFromTranscription(transcribed)" in script


def test_doctor_recording_requires_visible_encounter_selection() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert "pendingInputMethodAfterEncounterSelection" in script
    assert "请先选择已报到或问诊中的患者，再开始录音生成" in script
    assert "encounter-selection-notice" in script
    assert ".encounter-selection-notice" in stylesheet
    assert "开始问诊并录音" in script
    assert "选择并开始录音" in script
    assert 'data-after-restore-input="record"' in script
    input_button_handler = script[
        script.index('$("inputMethodButton").addEventListener("click"') :
        script.index('$("displaySettingsButton").addEventListener("click"')
    ]
    assert "if (!encounterReadyForInput())" in input_button_handler
    assert 'requireEncounterBeforeInput("record")' in input_button_handler
    assert "toggleInputMethodMenu()" in input_button_handler


def test_doctor_generation_menu_restores_demo_record_audio_and_text_entries() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert 'data-input-method="mock"' in html
    assert 'data-input-method="record"' in html
    assert 'data-input-method="audio"' in html
    assert 'data-input-method="text"' in html
    assert 'mock: "固定音频演示"' in script
    assert 'record: "录音生成"' in script
    assert 'audio: "音频生成"' in script
    assert 'text: "文本生成"' in script
    assert "menu.hidden = !appState.inputMenuOpen" in script
    assert 'button.textContent = appState.currentTaskId ? "继续审核" : "新建问诊"' in script
    assert "startFixedAudioLiveDemo().catch(reportActionError)" in script


def test_doctor_recording_submit_keeps_progress_visible_until_task_created() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    submit_body = script[
        script.index("async function submitBrowserRecording()") :
        script.index("function openReservedRecording()")
    ]
    before_upload = submit_body[: submit_body.index("const transcribed = await completeBrowserRecordingUpload()")]

    assert "closeDrawer()" not in before_upload
    assert "正在转写录音并生成病历草稿，请保持页面打开。" in submit_body
    assert "录音转写完成，正在生成结构化病历草稿..." in submit_body
    assert "病历草稿已生成，可在工作区继续修改、审核和导出。" in submit_body
    assert "const generated = await continueGeneratingFromTranscription(transcribed)" in submit_body
    assert 'showToast("病历草稿已生成，请继续修改和审核")' in submit_body


def test_doctor_recording_drawer_close_does_not_silently_cancel_active_recording() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "cancelBrowserRecording({ silent: true })" not in script
    assert "录音正在进行。请先点击“停止”完成试听，或点击“取消”放弃本次录音。" in script
    assert "录音进行中，请先停止或取消录音" in script
    assert "return false;" in script


def test_doctor_recording_panel_has_default_next_step_feedback() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "function browserRecordingDefaultMessage" in script
    assert "点击“开始录音”后允许麦克风权限；停止后可试听并上传生成病历。" in script
    assert "录音已停止，可先试听；确认后点击“上传并生成病历”。" in script
def test_doctor_recording_live_gate_uses_follow_chunks_and_transcript_events() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "function shouldUseLiveBrowserRecordingFollow" in script
    assert "const useLiveFollow = shouldUseLiveBrowserRecordingFollow();" in script
    assert 'appState.recognitionMode = "follow"' in script
    assert "if (useLiveFollow)" in script
    assert 'listenForAsrEvents(`/api/asr/sessions/${encodeURIComponent(liveSessionId)}/events`)' in script
    assert 'form.append("chunk_started_at_ms"' in script
    assert 'form.append("chunk_ended_at_ms"' in script
    assert 'source.addEventListener("transcript.partial", handleTranscriptSegment)' in script
    assert 'source.addEventListener("transcript.stable", handleTranscriptSegment)' in script


def test_doctor_live_clinical_reference_handles_versioned_sse_events() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "liveClinicalDraft" in script
    assert "function applyLiveClinicalDraft" in script
    assert "version <= Number(appState.liveClinicalVersion || 0)" in script
    assert 'source.addEventListener("record.live_patch"' in script
    assert 'source.addEventListener("clinical_processing.started"' in script
    assert 'source.addEventListener("clinical_processing.failed"' in script
    assert 'source.addEventListener("session.finalizing"' in script
    assert 'source.addEventListener("session.finalized"' in script


def test_doctor_live_clinical_reference_summary_is_bounded_and_detailed() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    stylesheet = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert "function renderLiveClinicalReferenceCard" in script
    assert "function renderLiveClinicalDetailContent" in script
    assert 'detailTarget: "assist:live-clinical"' in script
    assert 'if (section === "live-clinical")' in script
    assert ".slice(0, 3)" in script
    assert "data-evidence-segment-id" in script
    assert "实时草稿为临时内容" in script
    assert "data-live-clinical-action=\"mark-asked\"" in script
    assert "data-live-clinical-action=\"add-question\"" in script
    assert "data-live-clinical-action=\"adopt-candidate\"" in script
    assert "live-clinical-actions" in stylesheet


def test_fixed_audio_demo_uses_live_follow_and_idempotent_convergence() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "fixedDemoAudioUrl: \"/api/audio/demo/fever-01\"" in script
    assert "function startFixedAudioLiveDemo" in script
    assert "function finalizeFixedAudioLiveDemo" in script
    assert "function convergeFixedAudioLiveDemo" in script
    assert "FIXED_DEMO_CHUNK_SECONDS" in script
    assert "uploadFixedDemoAudioChunk" in script
    assert "固定音频跟随识别演示" in script
    assert "开始问诊演示" in script
    assert "结束问诊并生成正式病历" in script
    assert "/converge-record" in script
    assert 'key: "start-live-demo", label: "开始问诊演示"' in script
    assert 'key: "finalize-live-demo", label: "结束问诊并生成正式病历"' in script
    assert 'appState.fixedDemoStatus === "ready_to_finalize"' in script
    assert 'button.textContent = "结束问诊并生成正式病历"' in script
    assert 'button.disabled = Boolean((appState.busy && !fixedDemoReadyToFinalize) || fixedDemoProcessing)' in script
    assert 'button.dataset.busyAllowed = fixedDemoReadyToFinalize ? "true" : "false"' in script
    assert 'fixedDemoStatus === "ready_to_finalize" && appState.fixedDemoSessionId && !appState.currentTaskId' in script
    assert "[data-workflow-action='finalize-live-demo']" in script
    assert "setBusy(false);" in script
    assert "finalizeFixedAudioLiveDemo().catch(reportActionError)" in script
    assert "appState.viewMode === \"doctor\"" in script
    assert "startFixedAudioLiveDemo().catch(reportActionError)" in script
    assert "async function waitForAsrResultReady" in script
    assert "/api/asr/sessions/${encodeURIComponent(sessionId)}/result" in script
    assert "const resultTimeoutMs = Math.max(600000, Math.ceil(finalizedAudioSeconds * 2500))" in script
    assert "await waitForAsrResultReady(appState.currentAsrSessionId, completed.events_url, { timeoutMs: resultTimeoutMs })" in script
    assert 'fallback: "result_poll"' in script
    assert "async function waitForFormalRecordReady" in script
    assert "appState.currentRecordFields && taskRevisionId" in script
    assert "await waitForFormalRecordReady(created.task_id)" in script
