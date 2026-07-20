from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_page_exposes_login_panel_and_user_status():
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")

    assert 'id="loginPanel"' in html
    assert 'id="loginForm"' in html
    assert 'id="authUserLabel"' in html
    assert 'id="logoutButton"' in html


def test_doctor_js_uses_auth_endpoints_and_handles_401():
    js = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "/api/auth/me" in js
    assert "/api/auth/login" in js
    assert "/api/auth/logout" in js
    assert "response.status === 401" in js
    assert "renderAuthPanel" in js
