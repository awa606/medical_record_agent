from pathlib import Path
import webbrowser

from scripts.package_help import build, ALLOWLIST, ROOT
from scripts import doctor_pilot


def test_help_only_packages_allowlisted_public_documents(tmp_path):
    source = ROOT / "docs/pilot/doctor-v1"
    names = build(tmp_path)
    assert set(names) == set(ALLOWLIST)
    assert not (tmp_path / "terminology.md").exists()
    manual = (tmp_path / "manual.html").read_text(encoding="utf8")
    assert "generation-failure" in manual
    assert "doctor-manual.pdf" not in manual  # No broken PDF link without a package.
    assert "../../../static/brand" not in manual
    for name in ALLOWLIST:
        assert (tmp_path / name).is_file()


def test_launcher_opens_help_for_its_own_environment(monkeypatch):
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(doctor_pilot, "fetch", lambda *args: (200, b"help"))
    result = doctor_pilot.open_help({"port": 8798})
    assert opened == ["http://127.0.0.1:8798/static/help/index.html"]
    assert result["phase"] == "HELP_OPENED"


def test_launcher_reports_offline_help_explicitly(tmp_path, monkeypatch):
    (tmp_path / "manual.html").write_text("offline")
    opened = []
    monkeypatch.setattr(webbrowser, "open", opened.append)
    monkeypatch.setattr(doctor_pilot, "fetch", lambda *args: (0, b""))
    result = doctor_pilot.open_help({"port": 8798, "handbook_dir": str(tmp_path)})
    assert result["phase"] == "HELP_OFFLINE"
    assert opened == [(tmp_path / "manual.html").as_uri()]
