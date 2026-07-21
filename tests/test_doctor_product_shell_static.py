from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    assert ".product-nav" in css
    assert ".product-dashboard" in css
    assert ".dashboard-status-grid" in css
    assert ".admin-grid" in css
    assert "@media (max-width: 1366px)" in css


def test_product_shell_does_not_remove_recording_v2_core_path() -> None:
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "browserRecordingChunks" not in js
    assert "async function queueBrowserRecordingChunk" in js
    assert "async function pumpBrowserRecordingUploadQueue" in js
    assert "async function finalizeBrowserRecording" in js
    assert "async function completeBrowserRecordingUpload" in js
    assert "async function cancelBrowserRecording" in js
