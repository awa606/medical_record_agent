from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key == "id" and value:
                self.ids.append(value)


def read_static(name: str) -> str:
    return (ROOT / "static" / name).read_text(encoding="utf-8")


def function_body(script: str, name: str) -> str:
    marker = f"function {name}"
    start = script.index(marker)
    next_function = script.find("\nfunction ", start + len(marker))
    if next_function == -1:
        next_function = len(script)
    return script[start:next_function]


def test_doctor_product_shell_exposes_four_core_views() -> None:
    html = read_static("doctor.html")

    assert 'data-product-view-target="workbench"' in html
    assert 'data-product-view-target="encounter"' in html
    assert 'data-product-view-target="admin"' in html
    assert 'id="workbenchHome"' in html
    assert 'data-product-view="workbench"' in html
    assert 'data-product-view="encounter"' in html
    assert 'id="adminHome"' in html
    assert 'id="dashboardEncounterList"' in html
    assert 'id="encounterView"' in html
    assert 'class="product-main"' in html
    assert 'class="login-shell"' in html
    assert 'doctor-ui-v2.css' in html


def test_doctor_product_shell_has_unique_dom_ids() -> None:
    html = read_static("doctor.html")
    parser = _IdCollector()
    parser.feed(html)

    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    assert duplicates == []


def test_doctor_product_shell_reuses_existing_business_endpoints() -> None:
    js = read_static("doctor.js")

    assert "const PRODUCT_VIEWS" in js
    assert "function setProductView" in js
    assert "function renderProductShell" in js
    assert "function encounterWorklistMarkup" in js
    assert "dashboardEncounterList" in js
    assert "/api/encounters" in js
    assert "/api/auth/users" in js
    assert 'api("/ready")' in js


def test_doctor_product_shell_styles_support_responsive_workbench() -> None:
    css = read_static("doctor.css")
    ui_css = read_static("doctor-ui-v2.css")

    assert ".product-nav" in css
    assert ".product-dashboard" in css
    assert ".dashboard-status-grid" in css
    assert ".admin-grid" in css
    assert "@media (max-width: 1366px)" in css
    assert ".product-main" in ui_css
    assert ".encounter-patient-banner" in ui_css
    assert '"transcript record"' in ui_css
    assert '"transcript assist"' in ui_css
    assert "@media (min-width: 1680px)" in ui_css
    assert "@media (max-width: 1366px)" in ui_css
    assert "@media (prefers-reduced-motion: reduce)" in ui_css


def test_product_shell_sets_visible_route_context() -> None:
    js = read_static("doctor.js")

    assert "document.body.dataset.productView = view" in js
    assert 'workbench: "工作台"' in js
    assert 'encounter: "就诊工作区"' in js
    assert 'admin: "管理后台"' in js


def test_product_shell_keeps_main_recording_path_without_pr69_protocol() -> None:
    js = read_static("doctor.js")

    assert "browserRecordingChunks" in js
    assert "function mergeBrowserRecordingChunks" in js
    assert "async function completeBrowserRecordingUpload" in js
    assert "function cancelBrowserRecording" in js
    assert "async function queueBrowserRecordingChunk" not in js
    assert "async function pumpBrowserRecordingUploadQueue" not in js
    assert "async function finalizeBrowserRecording" not in js


def test_demo_v2_state_consistency_markup_and_helpers() -> None:
    html = read_static("doctor.html")
    js = read_static("doctor.js")
    ui_css = read_static("doctor-ui-v2.css")

    assert 'id="transcriptionFailurePanel"' in html
    assert 'id="retryTranscriptionButton"' in html
    assert 'id="patientDataStatus"' in html
    assert "function doctorDisplayState" in js
    assert "function doctorFacingTranscriptionIssue" in js
    assert "function renderTranscriptionFailurePanel" in js
    assert "document.body.dataset.displayState" in js
    assert "病历草稿已生成，可编辑" in js
    assert "等待医生审核" in js
    assert "转写服务暂时不可用" in js
    assert "请先重新转写或改用文本输入" in js
    assert "音频已安全保存" in js
    assert "医生已确认未采集" in js
    assert "doctorFacingTranscriptionIssue() ||" in js
    assert "setTimeout" in js and "3800" in js
    assert "clearToast()" in js
    assert "body.doctor-mode .debug-only" in ui_css
    assert ".failure-recovery-panel" in ui_css
    assert ".field-card.readonly-field" in ui_css
    assert ".encounter-action-bar.pending-review" in ui_css
    assert ".encounter-action-bar.flow-failed" in ui_css


def test_retry_transcription_uses_real_asr_endpoint_not_generate_record() -> None:
    js = read_static("doctor.js")
    retry_body = function_body(js, "retryTranscriptionFromFailure")
    generate_body = function_body(js, "startRecordGenerationFromAudio")

    assert "/transcribe?${params.toString()}" in retry_body
    assert "/generate-record" not in retry_body
    assert "/generate-record" in generate_body


def test_export_uses_authenticated_download_endpoint_not_server_paths() -> None:
    js = read_static("doctor.js")
    detail_body = function_body(js, "renderExportReadinessDetail")
    export_body = function_body(js, "exportRecord")

    assert "function downloadTaskExport" in js
    assert "/exports/${encodeURIComponent(format)}" in js
    assert "data-export-download-format" in js
    assert "exportSummaryRows" in detail_body
    assert "renderExportDownloadActions" in detail_body
    assert "Object.entries(exports)" not in detail_body
    assert "Object.values(result.exports" not in export_body
    assert 'downloadTaskExport("docx")' in export_body


def test_admin_and_reference_copy_hide_debug_values() -> None:
    js = read_static("doctor.js")

    assert "function runtimeServiceLabel" in js
    assert "演示管理员" in js
    assert "演示模式可用" in js
    assert "音频存储服务" in js
    assert "病历输出服务" in js
    assert "声纹资料服务" in js
    assert "function referenceStatusLabel" in js
    assert "来源已核验，临床映射待复核" in js
    assert "证据匹配度（非疾病概率）" in js


def test_novice_workbench_uses_task_stats_and_recoverable_empty_actions() -> None:
    html = read_static("doctor.html")
    js = read_static("doctor.js")
    ui_css = read_static("doctor-ui-v2.css")

    assert "dashboard-stat-card" in html
    assert "function encounterInputMethodLabel" in js
    assert "function encounterPhaseLabel" in js
    assert "pendingInput" in js
    assert "exceptions" in js
    assert "dashboard-empty-state" in js
    assert 'data-input-method="audio"' in js
    assert 'data-input-method="text"' in js
    assert ".encounter-worklist-meta" in ui_css
    assert ".empty-state-actions" in ui_css


def test_novice_layout_keeps_sidebar_full_height_and_action_bar_clear() -> None:
    js = read_static("doctor.js")
    ui_css = read_static("doctor-ui-v2.css")
    next_action_body = function_body(js, "nextActionState")
    footer_body = function_body(js, "renderFooter")

    assert "min-height: calc(100dvh - 68px)" in ui_css
    assert "height: calc(100dvh - 68px)" in ui_css
    assert "grid-template-rows: auto auto minmax(260px, 1fr)" in ui_css
    assert "padding-bottom: 148px" in ui_css
    assert "min-height: max(520px, calc(100dvh - 330px))" in ui_css
    assert "exportButton.dataset.disabledReason" in footer_body
    assert "actions: []" in next_action_body


def test_product_shell_normal_mode_blocks_forbidden_demo_copy() -> None:
    html = read_static("doctor.html")
    js = read_static("doctor.js")
    ui_css = read_static("doctor-ui-v2.css")
    combined = "\n".join([html, js, ui_css])

    forbidden = [
        "MediSync",
        "MedAI",
        "Sarah Miller",
        "Station ID",
        "国家三级等保认证",
        "[object Object]",
        "/app/runtime",
        "Local Admin · admin",
        "mock · demo",
    ]
    for item in forbidden:
        assert item not in combined
