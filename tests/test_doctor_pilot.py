import copy
import json
from pathlib import Path

import pytest
from scripts import doctor_pilot as pilot


@pytest.fixture
def registered(tmp_path, monkeypatch):
    runtime = tmp_path / "runtime"; runtime.mkdir()
    (runtime / "medical_record_agent.sqlite3").touch()
    manifest = tmp_path / "manifest"; manifest.write_text("model")
    digest = pilot.sha(manifest); monkeypatch.setattr(pilot, "MODEL_DIGEST", digest)
    config = {"schema_version": 1, "project": "pilot-test", "port": 8795,
              "runtime": str(runtime), "model_manifest": str(manifest), "model_digest": digest,
              "app_git_sha": "a" * 40, "release_status": "CANDIDATE_NOT_RELEASED",
              "resources": {name: pilot.hashlib.sha256(b"current").hexdigest() for name in pilot.RESOURCES}, "containers": {}}
    items = {}
    for name in pilot.SERVICES:
        mounts = [{"Destination": "/app/runtime", "Source": str(runtime)}] if name == "app" else []
        items[name] = {"Id": name + "-id", "Image": name + "-image", "Mounts": mounts,
            "State": {"Running": True, "Status": "running"},
            "Config": {"Labels": {"com.docker.compose.project": "pilot-test", "com.docker.compose.service": name},
            "Env": ["RECORD_PROVIDER_MODE=edge", "MEDICAL_RECORD_AGENT_ASR_ENGINE=funasr",
                    "MEDICAL_RECORD_AGENT_REQUIRE_FUNASR=1", "LLM_PROVIDER=ollama", "OLLAMA_MODEL=qwen3:4b",
                    "OLLAMA_BASE_URL=http://ollama:11434"]},
            "HostConfig": {"PortBindings": {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8795"}]} if name == "gateway" else {}}}
        config["containers"][name] = {"id": name + "-id", "image": name + "-image",
                                        "mounts": {m["Destination"]: m["Source"] for m in mounts}}
    monkeypatch.setattr(pilot, "inspect", lambda identifier: copy.deepcopy(next(i for i in items.values() if i["Id"] == identifier)))
    return config, items


@pytest.mark.parametrize("failure", ["image", "mount", "project", "public_port", "mock", "model", "missing_db"])
def test_fail_closed_before_operation(registered, failure):
    config, items = registered
    if failure == "image": items["app"]["Image"] = "other"
    if failure == "mount": items["app"]["Mounts"][0]["Source"] += "-other"
    if failure == "project": items["app"]["Config"]["Labels"]["com.docker.compose.project"] = "old-project"
    if failure == "public_port": items["gateway"]["HostConfig"]["PortBindings"]["8000/tcp"][0]["HostIp"] = "0.0.0.0"
    if failure == "mock": items["app"]["Config"]["Env"].append("LLM_PROVIDER=mock")
    if failure == "model": Path(config["model_manifest"]).write_text("changed")
    if failure == "missing_db": (Path(config["runtime"]) / "medical_record_agent.sqlite3").unlink()
    with pytest.raises(pilot.PilotError): pilot.validate(config)


def test_readiness_is_not_health_and_stale_web_rejected(registered, monkeypatch):
    config, items = registered
    monkeypatch.setattr(pilot, "fetch", lambda port, path: (503, b"warming") if path == "/ready" else (200, b"current"))
    result = pilot.web_status(config, items)
    assert result["web_available"] and not result["model_ready"]
    monkeypatch.setattr(pilot, "fetch", lambda *args: (200, b"old version"))
    with pytest.raises(pilot.PilotError, match="RESOURCE_MISMATCH"):
        pilot.web_status(config, items)


def test_repeated_start_only_changes_registered_policies(registered, tmp_path, monkeypatch):
    config, _ = registered; calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or "")
    monkeypatch.setattr(pilot, "fetch", lambda *args: (200, b"current"))
    for _ in range(2): assert pilot.start(config, tmp_path / "config.json")["model_ready"]
    assert calls == [("docker", "update", "--restart", "unless-stopped", "ollama-id", "app-id", "gateway-id")] * 2
    assert not (tmp_path / "config.operation-lock").exists()


def test_foreign_port_is_not_stopped(registered, tmp_path, monkeypatch):
    config, items = registered; calls = []
    items["gateway"]["State"] = {"Running": False, "Status": "exited"}
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args))
    class Occupied:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect_ex(self, *args): return 0
    monkeypatch.setattr(pilot.socket, "socket", Occupied)
    with pytest.raises(pilot.PilotError, match="PORT_OCCUPIED"):
        pilot.start(config, tmp_path / "config.json")
    assert calls == []


def test_stop_scoped_reverse_order_and_no_delete(registered, tmp_path, monkeypatch):
    config, _ = registered; calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or "")
    pilot.stop(config, tmp_path / "config.json")
    assert calls == [("docker", "stop", "--time", "30", s+"-id") for s in reversed(pilot.SERVICES)]
    assert (Path(config["runtime"]) / "medical_record_agent.sqlite3").exists()


def test_concurrent_actions_rejected_without_unlocking_owner(tmp_path):
    path = tmp_path / "config.json"
    with pilot.operation_lock(path):
        with pytest.raises(pilot.PilotError, match="OPERATION_RUNNING"):
            with pilot.operation_lock(path): pass
        assert path.with_suffix(".operation-lock").exists()


def test_timeout_keeps_data_and_does_not_claim_ready(registered, tmp_path, monkeypatch):
    config, _ = registered
    monkeypatch.setattr(pilot, "command", lambda *args: "")
    monkeypatch.setattr(pilot, "fetch", lambda port, path: (503, b"") if path == "/ready" else (200, b"current"))
    with pytest.raises(pilot.PilotError, match="READY_TIMEOUT"):
        pilot.start(config, tmp_path / "config.json", timeout=0)
    assert (Path(config["runtime"]) / "medical_record_agent.sqlite3").exists()


def test_feedback_download_retains_text_without_network(tmp_path):
    from playwright.sync_api import sync_playwright
    path = Path(__file__).resolve().parents[1] / "docs/pilot/doctor-v1/feedback.html"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(accept_downloads=True)
        outgoing = []
        page.on("request", lambda r: outgoing.append(r.url) if r.url.startswith(("http:", "https:")) else None)
        page.goto(path.as_uri())
        for name, value in {"tester": "D01", "version": "test-version", "expected": "保存成功", "actual": "<script>alert(1)</script>保存失败", "help": "没有修改病历"}.items():
            page.fill("#"+name, value)
        page.check("#safe")
        with page.expect_download() as download:
            page.click("button[type=submit]")
        dest = tmp_path / "feedback.json"; download.value.save_as(dest)
        result = json.loads(dest.read_text(encoding="utf8"))
        assert result["actual"].startswith("<script>") and result["scope"] == "synthetic_and_simulated_only"
        assert page.input_value("#actual") == result["actual"]
        assert not outgoing
        assert not any(k in result for k in ("patient", "password", "audio"))
        browser.close()


def test_open_uses_isolated_browser_profile(registered, tmp_path, monkeypatch):
    config, _ = registered
    edge = tmp_path / "Microsoft/Edge/Application/msedge.exe"
    edge.parent.mkdir(parents=True); edge.touch()
    monkeypatch.setenv("PROGRAMFILES(X86)", str(tmp_path))
    monkeypatch.setattr(pilot, "web_status", lambda *_: {"web_available": True})
    calls = []
    monkeypatch.setattr(pilot.subprocess, "Popen", lambda args: calls.append(args))
    pilot.open_workspace(config)
    args = calls[0]
    assert str(edge) == args[0]
    assert "--app=http://127.0.0.1:8795/static/doctor.html" in args
    assert "--user-data-dir=" + str(Path(config["runtime"]).parent / "doctor-browser-profile") in args


def test_brand_fingerprints_optional_for_old_registration_but_complete_for_new(registered, monkeypatch):
    config, items = registered
    pilot.validate(config)  # Existing registrations remain usable.
    for name in pilot.BRAND_RESOURCES:
        config["resources"][name] = pilot.hashlib.sha256(b"brand").hexdigest()
    pilot.validate(config)
    monkeypatch.setattr(pilot, "fetch", lambda port, path: (200, b"brand" if "/brand/" in path else b"current"))
    assert pilot.web_status(config, items)["web_available"]
    monkeypatch.setattr(pilot, "fetch", lambda *args: (200, b"current"))
    with pytest.raises(pilot.PilotError, match="RESOURCE_MISMATCH"):
        pilot.web_status(config, items)
    del config["resources"][pilot.BRAND_RESOURCES[0]]
    with pytest.raises(pilot.PilotError):
        pilot.validate(config)


def test_missing_ancillary_entry_does_not_claim_product_ready(registered, tmp_path, monkeypatch):
    config, items = registered
    config["handbook_dir"] = str(tmp_path / "missing-handbook")
    monkeypatch.setattr(pilot, "data_browser_status", lambda: {"available": False, "phase": "STOPPED"})
    result = pilot.entrypoint_status(config, {"phase": "MODEL_NOT_READY", "web_available": True, "model_ready": False})
    assert result["entrypoints"]["doctor"]["available"]
    assert result["entrypoints"]["knowledge"]["url"].endswith("#admin")
    assert not result["entrypoints"]["data_browser"]["available"]
    assert not result["entrypoints"]["manual"]["available"]
    assert not result["model_ready"]


@pytest.mark.parametrize("owned,http_code,expected", [(True, 403, True), (True, 200, False), (False, 403, False)])
def test_viewer_status_requires_own_process_auth_and_valid_snapshot(tmp_path, monkeypatch, owned, http_code, expected):
    from types import SimpleNamespace
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    folder = tmp_path / ".artifacts/data-browser"; folder.mkdir(parents=True)
    snapshot = folder / "snapshot"; snapshot.mkdir()
    (snapshot / "mra_snapshot.sqlite3").write_bytes(b"synthetic projection")
    (snapshot / "manifest.json").write_text(json.dumps({"synthetic_only": True,
        "database_sha256": pilot.sha(snapshot / "mra_snapshot.sqlite3"), "captured_at": "2026-09-29T00:00:00Z", "source_label": "historical version"}))
    (snapshot / "login.private.json").write_text(json.dumps({"run_id": "test-run", "url": "SECRET_TOKEN"}))
    (folder / "state.private.json").write_text(json.dumps({"port": 18896, "pid": 123,
        "snapshot_dir": str(snapshot), "run_id": "test-run"}))
    monkeypatch.setattr(pilot.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="data_browser.py test-run" if owned else "unrelated.exe"))
    monkeypatch.setattr(pilot, "fetch", lambda *a: (http_code, b""))
    result = pilot.data_browser_status()
    assert result["available"] is expected
    assert "SECRET_TOKEN" not in json.dumps(result)
    (snapshot / "mra_snapshot.sqlite3").write_bytes(b"tampered")
    assert pilot.data_browser_status()["phase"] == "INVALID_SNAPSHOT"


def test_reused_pid_is_ignored_without_touching_other_process():
    import re
    import shutil
    import subprocess
    shell = shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell 7 required for native launcher test")
    script = (Path(__file__).resolve().parents[1] / "scripts/Start-MRADataBrowser.ps1").read_text(encoding="utf-8-sig")
    function = re.search(r"function Get-OwnedProcess\(\$saved\) \{.*?\n\}", script, re.S).group(0)
    code = '''$ErrorActionPreference='Stop'
$scriptPath='data_browser.py'
function Get-CimInstance { return @{CommandLine='unrelated.exe'} }
function Stop-Process { throw 'must never stop unrelated process' }
''' + function + '''
$result=Get-OwnedProcess @{pid=123;run_id='viewer-run'}
if($null -ne $result){throw 'unowned process returned'}
'''
    done = subprocess.run([shell, "-NoProfile", "-Command", code], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_start_viewer_uses_file_output_for_detached_process_and_keeps_errors_private(tmp_path, monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(pilot, "ROOT", tmp_path)
    monkeypatch.setattr(pilot, "validate", lambda c: {})
    monkeypatch.setattr(pilot.shutil, "which", lambda name: "pwsh")
    monkeypatch.setattr(pilot, "data_browser_status", lambda: {"available": True, "url": "http://127.0.0.1:8796/"})
    def run(args, **kwargs):
        assert "capture_output" not in kwargs
        assert kwargs["stdout"].fileno() == kwargs["stderr"].fileno()
        kwargs["stdout"].write("PRIVATE_TOOL_OUTPUT")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(pilot.subprocess, "run", run)
    result = pilot.open_data_browser({})
    assert result["phase"] == "VIEWER_READY"
    assert "PRIVATE_TOOL_OUTPUT" not in json.dumps(result)
