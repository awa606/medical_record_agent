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
    assert 'id="browserRecordingPreview"' in html
    assert 'id="browserRecordingChunkStatus"' in html


def test_doctor_recording_uses_browser_pcm_wav_path() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "navigator.mediaDevices.getUserMedia" in script
    assert "createScriptProcessor" in script
    assert "function encodeWavFromFloat32" in script
    assert 'writeWavString(view, 0, "RIFF")' in script
    assert 'new File([blob], `browser-recording-${timestamp}.wav`, { type: "audio/wav" })' in script
    assert "const MAX_BROWSER_RECORDING_SECONDS = 1800" in script
    assert "const BROWSER_RECORDING_CHUNK_SECONDS = 10" in script


def test_doctor_recording_uses_resumable_chunked_upload_path() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "async function sha256Blob" in script
    assert "async function uploadBrowserRecordingChunk" in script
    assert "/chunks" in script
    assert "/chunks/status" in script
    assert "/complete" in script
    assert "pauseBrowserRecording" in script
    assert "resumeBrowserRecording" in script
    assert "Promise.allSettled(appState.browserRecordingChunkUploads)" in script


def test_doctor_recording_replaces_reserved_placeholder() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    placeholder = "浏览器麦克风录音暂未接入"

    assert placeholder not in script
    assert 'openDrawer("recordingPanel", "浏览器录音生成病历")' in script
    assert "completeBrowserRecordingUpload" in script
    assert "continueGeneratingFromTranscription(transcribed)" in script
