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
