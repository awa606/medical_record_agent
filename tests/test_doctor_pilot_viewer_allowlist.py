"""A test-looking identifier is not proof of permission to expose a record."""
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import doctor_pilot as pilot


@pytest.fixture
def viewer_setup(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    source = runtime / "medical_record_agent.sqlite3"
    with sqlite3.connect(source) as db:
        db.execute("CREATE TABLE patient (id INTEGER PRIMARY KEY, deidentified_id TEXT)")
        db.executemany("INSERT INTO patient VALUES (?,?)", [
            (1, "SIM-TEST-REVIEWED"), (19, "SIM-TEST-UNCONFIRMED19"),
            (20, "SIM-TEST-UNCONFIRMED20"),
        ])
    policy_path = tmp_path / "reviewed-allowlist.json"
    policy = {"confirmed_synthetic": True, "reviewed_by": "explicit test approval",
              "synthetic_patient_ids": ["SIM-TEST-REVIEWED"]}
    policy_path.write_text(json.dumps(policy, indent=2), encoding="utf8")
    config = {"runtime": str(runtime), "viewer_directory": str(tmp_path / "viewer"),
              "viewer_allowlist": str(policy_path), "environment": "test",
              "environment_label": "使用测试版", "app_git_sha": "a" * 40}
    calls = []
    monkeypatch.setattr(pilot, "validate", lambda _: {"app": {"Id": "app-id", "State": {"Running": True}}})
    monkeypatch.setattr(pilot.shutil, "which", lambda _: "pwsh")
    monkeypatch.setattr(pilot, "data_browser_status", lambda _: {"available": True})

    def command(*args):
        calls.append(("backup", args))
        with sqlite3.connect(source) as src, sqlite3.connect(runtime / "viewer-source.sqlite3") as dst:
            src.backup(dst)

    def run(args, **kwargs):
        calls.append(("launch", args))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(pilot, "command", command)
    monkeypatch.setattr(pilot.subprocess, "run", run)
    return config, policy_path, source, calls


def test_existing_reviewed_allowlist_is_not_expanded_from_test_patient_ids(viewer_setup):
    config, policy, source, calls = viewer_setup
    original = policy.read_bytes()
    source_original = source.read_bytes()
    assert pilot.open_data_browser(config)["phase"] == "VIEWER_READY"
    assert policy.read_bytes() == original
    assert source.read_bytes() == source_original
    launch = next(args for kind, args in calls if kind == "launch")
    assert launch[launch.index("-AllowlistPath") + 1] == str(policy)
    assert json.loads(policy.read_text())["synthetic_patient_ids"] == ["SIM-TEST-REVIEWED"]


@pytest.mark.parametrize("invalid", ["missing", "no_config_path", "unreviewed", "empty", "duplicates", "invalid_json"])
def test_missing_or_unreviewed_allowlist_refuses_before_backup_and_start(viewer_setup, invalid):
    config, policy, source, calls = viewer_setup
    if invalid == "missing":
        policy.unlink()
    elif invalid == "no_config_path":
        config.pop("viewer_allowlist")
    elif invalid == "invalid_json":
        policy.write_text("not-json", encoding="utf8")
    else:
        value = json.loads(policy.read_text())
        if invalid == "unreviewed": value["reviewed_by"] = ""
        if invalid == "empty": value["synthetic_patient_ids"] = []
        if invalid == "duplicates": value["synthetic_patient_ids"] *= 2
        policy.write_text(json.dumps(value), encoding="utf8")
    original = policy.read_bytes() if policy.exists() else None
    source_original = source.read_bytes()
    with pytest.raises(pilot.PilotError, match="VIEWER_ALLOWLIST_REQUIRED"):
        pilot.open_data_browser(config)
    assert calls == []
    assert source.read_bytes() == source_original
    assert (policy.read_bytes() if policy.exists() else None) == original
