from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_doctor_worklist_drawer_is_present() -> None:
    html = (ROOT / "static" / "doctor.html").read_text(encoding="utf-8")

    assert 'id="openWorklistButton"' in html
    assert 'id="encounterWorklistPanel"' in html
    assert 'id="encounterSearchInput"' in html
    assert 'id="encounterStatusFilter"' in html
    assert 'id="refreshWorklistButton"' in html
    assert 'id="encounterWorklist"' in html


def test_doctor_worklist_uses_encounter_api_and_restore_path() -> None:
    script = (ROOT / "static" / "doctor.js").read_text(encoding="utf-8")

    assert "/api/encounters" in script
    assert "function renderEncounterWorklistPanel" in script
    assert "async function refreshEncounterWorklist" in script
    assert "async function restoreEncounter" in script
    assert "data-restore-encounter" in script
    assert "appState.currentEncounter" in script
    assert "encounterStatusFilter" in script
    assert "encounter-revision-history" in script


def test_doctor_worklist_styles_are_scoped_to_drawer() -> None:
    css = (ROOT / "static" / "doctor.css").read_text(encoding="utf-8")

    assert ".worklist-toolbar" in css
    assert ".encounter-worklist" in css
    assert ".encounter-worklist-item" in css
    assert ".encounter-worklist-actions" in css
    assert ".encounter-revision-history" in css
