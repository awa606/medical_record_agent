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
    assert "@media (min-width: 1680px)" in ui_css
    assert "@media (max-width: 1366px)" in ui_css
    assert "@media (prefers-reduced-motion: reduce)" in ui_css


def test_product_shell_sets_visible_route_context() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "document.body.dataset.productView = view" in js
    assert 'workbench: "工作台"' in js
    assert 'encounter: "就诊工作区"' in js
    assert 'admin: "管理后台"' in js


def test_product_shell_does_not_remove_recording_v2_core_path() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "browserRecordingChunks" not in js
    assert "async function queueBrowserRecordingChunk" in js
    assert "async function pumpBrowserRecordingUploadQueue" in js
    assert "async function finalizeBrowserRecording" in js
    assert "async function completeBrowserRecordingUpload" in js
    assert "async function cancelBrowserRecording" in js
