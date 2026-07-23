from pathlib import Path
from html.parser import HTMLParser


ROOT = Path(__file__).resolve().parents[1]


class _IdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.ids: list[str] = []

    def handle_starttag(self, _tag: str, attrs: list[tuple[str, str | None]]) -> None:
        for key, value in attrs:
            if key == "id" and value:
                self.ids.append(value)


def test_doctor_product_shell_exposes_four_core_views() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")

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
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    parser = _IdCollector()
    parser.feed(html)

    duplicates = sorted({item for item in parser.ids if parser.ids.count(item) > 1})
    assert duplicates == []


def test_doctor_product_shell_reuses_existing_business_endpoints() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "const PRODUCT_VIEWS" in js
    assert "function setProductView" in js
    assert "function renderProductShell" in js
    assert "function encounterWorklistMarkup" in js
    assert "dashboardEncounterList" in js
    assert "/api/encounters" in js
    assert "/api/auth/users" in js
    assert 'api("/ready")' in js


def test_doctor_product_shell_styles_support_responsive_workbench() -> None:
    css = (ROOT / "static" / "doctor.css").read_text(encoding="utf-8")
    ui_css = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert ".product-nav" in css
    assert ".product-dashboard" in css
    assert ".dashboard-status-grid" in css
    assert ".admin-grid" in css
    assert "@media (max-width: 1366px)" in css
    assert ".product-main" in ui_css
    assert ".encounter-patient-banner" in ui_css
    assert '"transcript record"' in ui_css
    assert '"transcript assist"' in ui_css
    assert "repeat(4, minmax(0, 1fr))" in ui_css
    assert "repeat(5, minmax(96px, 1fr))" in ui_css
    assert "@media (min-width: 1680px)" in ui_css
    assert "@media (max-width: 1366px)" in ui_css
    assert "@media (prefers-reduced-motion: reduce)" in ui_css


def test_product_shell_sets_visible_route_context() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "document.body.dataset.productView = view" in js
    assert 'workbench: "工作台"' in js
    assert 'encounter: "就诊工作区"' in js
    assert 'admin: "管理后台"' in js


def test_demo_v2_workbench_uses_task_table_and_real_actions() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    for dom_id in [
        "dashboardPendingInputCount",
        "dashboardProcessingCount",
        "dashboardPendingReviewCount",
        "dashboardExceptionCount",
        "dashboardSearchInput",
        "dashboardStatusFilter",
    ]:
        assert f'id="{dom_id}"' in html

    assert "renderDashboardTaskTable" in js
    assert "encounter-task-table" in js
    assert 'data-dashboard-input-method="record"' in js
    assert "今日暂无就诊任务" in js


def test_demo_v2_hides_technical_noise_and_adds_recovery_panel() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert 'class="asr-engine-meta debug-only"' in html
    assert 'id="transcriptionFailurePanel"' in html
    assert "转写服务暂时不可用" in html
    assert 'id="retryTranscriptionButton"' in html
    assert 'id="fallbackTextInputButton"' in html
    assert 'id="openTechnicalDetailButton"' in html
    assert "friendlyTranscriptionError" in js
    assert "转写服务暂时不可用，本次任务已暂停" in js
    assert "renderTranscriptionTechnicalDetail" in js


def test_demo_v2_admin_and_references_are_business_facing() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "服务运行概览" in html
    assert "数据存储服务" in js
    assert "音频存储服务" in js
    assert "病历输出服务" in js
    assert "声纹资料服务" in js
    assert "AI生成服务" in js
    assert "演示管理员" in js
    assert "演示模式可用" in js
    assert "diagnosisReferences" in js
    assert "renderReferenceList" in js
    assert "来源已核验，临床映射待复核" in js
    assert "reference-item" in js


def test_demo_v2_display_states_are_consistent_for_showcase() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")
    ui_css = (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8")

    assert 'id="patientDataStatus"' in html
    assert "function doctorDisplayState" in js
    assert "病历草稿已生成，可编辑" in js
    assert "等待医生审核" in js
    assert "医生已确认未采集" in js
    assert "音频已安全保存" in js
    assert "dataset.displayState" in js
    assert "clearToast()" in js
    assert "window.setTimeout(() => toast.classList.remove(\"active\"), 3800)" in js
    assert ".encounter-action-bar.draft-generated" in ui_css
    assert ".encounter-action-bar.pending-review" in ui_css
    assert ".field-card.readonly-field" in ui_css


def test_demo_v2_removes_unverified_or_legacy_visible_copy() -> None:
    combined = "\n".join(
        [
            (ROOT / "static" / "doctor.html").read_text(encoding="utf-8"),
            (ROOT / "static" / "doctor.js").read_text(encoding="utf-8"),
            (ROOT / "static" / "doctor-ui-v2.css").read_text(encoding="utf-8"),
        ]
    )

    forbidden = [
        "MediSync",
        "MedAI",
        "Sarah Miller",
        "Station ID",
        "国家三级等保认证",
        "AI智能填充",
        "提交审核",
        "导出PDF",
        "确认导出",
        "Local Admin",
        "mock · demo",
        "fever_respiratory_v1",
        "规则匹配度",
        "[object Object]",
        "/app/runtime",
    ]
    for term in forbidden:
        assert term not in combined


def test_product_shell_does_not_remove_recording_v2_core_path() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "browserRecordingChunks" not in js
    assert "async function queueBrowserRecordingChunk" in js
    assert "async function pumpBrowserRecordingUploadQueue" in js
    assert "async function finalizeBrowserRecording" in js
    assert "async function completeBrowserRecordingUpload" in js
    assert "async function cancelBrowserRecording" in js
