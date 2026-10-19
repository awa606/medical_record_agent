import copy
import json
from pathlib import Path

import pytest

from scripts import doctor_pilot as pilot
from tests.test_doctor_pilot import registered


@pytest.fixture
def online_registered(registered, tmp_path):
    config, items = registered
    config.update(provider_profile="online_deepseek", online_api_base="https://api.deepseek.com",
                  online_model="deepseek-flash", release_status="ONLINE_REVIEW_CANDIDATE")
    config.pop("model_manifest")
    config.pop("model_digest")
    config["containers"].pop("ollama")
    items.pop("ollama")
    items["app"]["Config"]["Env"] = [
        "RECORD_PROVIDER_MODE=live", "MEDICAL_RECORD_AGENT_ASR_ENGINE=funasr",
        "MEDICAL_RECORD_AGENT_REQUIRE_FUNASR=1", "LLM_PROVIDER=online",
        "ONLINE_LLM_PROFILE=deepseek_demo",
        "ONLINE_LLM_MODEL=deepseek-flash", "ONLINE_LLM_API_BASE=https://api.deepseek.com",
        "ONLINE_LLM_API_KEY=test-key-not-a-credential", "LLM_MAX_RETRIES=0", "MRA_ANONYMIZE=1",
        "ONLINE_LLM_BUDGET_LEDGER=/app/online-private/cost-ledger.json",
        "ONLINE_LLM_DIAGNOSTICS_DIR=/app/online-private/business-diagnostics",
    ]
    private = tmp_path / "online-private"
    private.mkdir()
    items["app"]["Mounts"].append({"Destination": "/app/online-private", "Source": str(private), "Type": "bind", "RW": True})
    config["containers"]["app"]["mounts"]["/app/online-private"] = str(private)
    return config, items


def test_online_start_and_stop_manage_two_services_without_ollama(online_registered, tmp_path, monkeypatch):
    config, items = online_registered
    calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or "")
    monkeypatch.setattr(pilot, "fetch", lambda *args: (200, b"current"))
    assert set(pilot.validate(config)) == {"app", "gateway"}
    result = pilot.start(config, tmp_path / "online.json")
    assert result["provider_profile"] == "online_deepseek"
    assert result["requires_internet"] is True
    assert "云端" in result["provider_label"]
    pilot.stop(config, tmp_path / "online.json")
    assert calls == [
        ("docker", "update", "--restart", "unless-stopped", "app-id", "gateway-id"),
        ("docker", "stop", "--time", "30", "gateway-id"),
        ("docker", "stop", "--time", "30", "app-id"),
    ]


@pytest.mark.parametrize("override", [
    "RECORD_PROVIDER_MODE=demo", "LLM_PROVIDER=mock", "ONLINE_LLM_MODEL=other",
    "ONLINE_LLM_API_BASE=https://example.test", "ONLINE_LLM_API_KEY=",
    "LLM_MAX_RETRIES=1", "MRA_ANONYMIZE=0", "MEDICAL_RECORD_AGENT_ASR_ENGINE=mock",
    "ONLINE_LLM_PROFILE=", "ONLINE_LLM_PROFILE=generic",
])
def test_online_rejects_unapproved_provider_configuration(online_registered, override):
    config, items = online_registered
    items["app"]["Config"]["Env"].append(override)
    with pytest.raises(pilot.PilotError, match="PROVIDER_MISMATCH"):
        pilot.validate(config)


def test_online_endpoint_is_pinned_even_between_official_forms(online_registered):
    config, items = online_registered
    items["app"]["Config"]["Env"].append("ONLINE_LLM_API_BASE=https://api.deepseek.com/v1")
    with pytest.raises(pilot.PilotError, match="PROVIDER_MISMATCH"):
        pilot.validate(config)


def test_unknown_profile_and_extra_ollama_are_rejected(online_registered):
    config, items = online_registered
    with pytest.raises(pilot.PilotError, match="INVALID_CONFIG"):
        pilot.validate({**config, "provider_profile": "arbitrary"})
    bad = copy.deepcopy(config)
    bad["containers"]["ollama"] = {"id": "should-not-be-inspected"}
    with pytest.raises(pilot.PilotError, match="INVALID_CONFIG"):
        pilot.validate(bad)


@pytest.mark.parametrize("base", ["https://api.deepseek.com", "https://api.deepseek.com/v1"])
def test_online_registration_pins_endpoint_but_never_key(online_registered, tmp_path, monkeypatch, base):
    config, items = online_registered
    items["app"]["Config"]["Env"].append("ONLINE_LLM_API_BASE=" + base)
    monkeypatch.setattr(pilot, "inspect", lambda name: items[next(s for s in items if f"-{s}-" in name)])
    monkeypatch.setattr(pilot, "command", lambda *args: json.dumps([{"Config": {"Labels": {
        "org.opencontainers.image.revision": "a" * 40,
    }}}]))
    monkeypatch.setattr(pilot, "fetch", lambda port, path: (404, b"") if path.endswith("deployment.json") else (200, b"current"))
    path = tmp_path / "online.json"
    actual = pilot.configure(config["project"], config["port"], path, provider_profile="online_deepseek")
    text = path.read_text(encoding="utf8")
    assert actual["online_api_base"] == base
    assert actual["online_model"] == "deepseek-flash"
    assert actual["release_status"] == "ONLINE_REVIEW_CANDIDATE"
    assert "model_manifest" not in actual and "model_digest" not in actual
    assert "test-key-not-a-credential" not in text and "api_key" not in text.lower()
    assert set(actual["containers"]) == {"app", "gateway"}


def test_online_start_disarms_local_peer_without_starting_it(online_registered, tmp_path, monkeypatch):
    config, items = online_registered
    config.update(peer_config="local.json", switch_lock=str(tmp_path / "pair.json"))
    peer_config = {"project": "local"}
    peer_items = {s: {"Id": "peer-" + s, "State": {"Running": False}} for s in pilot.SERVICES}
    monkeypatch.setattr(pilot, "peer_configuration", lambda _: (peer_config, tmp_path / "local.json"))
    monkeypatch.setattr(pilot, "validate", lambda c: peer_items if c is peer_config else items)
    monkeypatch.setattr(pilot, "web_status", lambda *args: {"model_ready": True, "phase": "READY"})
    calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or "")
    pilot.start(config, tmp_path / "online.json")
    assert calls == [
        ("docker", "update", "--restart", "no", "peer-ollama", "peer-app", "peer-gateway"),
        ("docker", "update", "--restart", "no", "app-id", "gateway-id"),
    ]


def test_local_profile_still_rejects_cloud_even_with_official_model(registered):
    config, items = registered
    items["app"]["Config"]["Env"].append("LLM_PROVIDER=online")
    with pytest.raises(pilot.PilotError, match="PROVIDER_MISMATCH"):
        pilot.validate(config)


def test_online_cold_start_never_starts_an_ollama_container(online_registered, tmp_path, monkeypatch):
    config, items = online_registered
    for item in items.values():
        item["State"]["Running"] = False
    class FreePort:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def connect_ex(self, *args): return 1
    monkeypatch.setattr(pilot.socket, "socket", FreePort)
    monkeypatch.setattr(pilot, "web_status", lambda *args: {"model_ready": True, "phase": "READY"})
    calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or "")
    pilot.start(config, tmp_path / "online.json")
    assert [call for call in calls if call[:2] == ("docker", "start")] == [
        ("docker", "start", "app-id"), ("docker", "start", "gateway-id"),
    ]
    assert not any("ollama" in str(call) for call in calls)


def test_failed_online_switch_stops_two_services_and_restores_local_peer(online_registered, tmp_path, monkeypatch):
    config, items = online_registered
    config.update(peer_config="local.json", switch_lock=str(tmp_path / "pair.json"))
    peer = {"project": "local"}
    peer_path = tmp_path / "local.json"
    monkeypatch.setattr(pilot, "peer_configuration", lambda _: (peer, peer_path))
    monkeypatch.setattr(pilot, "validate", lambda _: items)
    checked = []
    monkeypatch.setattr(pilot, "assert_idle", lambda c, i, saved: checked.append((c, saved)))
    stopped = []
    monkeypatch.setattr(pilot, "stop", lambda c, p, **kw: stopped.append(c))
    starts = []
    def start(c, *args, **kwargs):
        starts.append(c)
        if c is config:
            raise pilot.PilotError("READY_TIMEOUT")
        return {"phase": "READY"}
    monkeypatch.setattr(pilot, "start", start)
    commands = []
    monkeypatch.setattr(pilot, "command", lambda *args: commands.append(args) or "")
    with pytest.raises(pilot.PilotError, match="SWITCH_FAILED_RESTORED"):
        pilot.switch_environment(config, tmp_path / "online.json", 1, True)
    assert checked == [(peer, True)]
    assert stopped == [peer] and starts == [config, peer]
    assert commands == [("docker", "stop", "--time", "30", "gateway-id"),
                        ("docker", "stop", "--time", "30", "app-id")]


def test_online_status_still_rejects_stale_page_and_failed_readiness(online_registered, monkeypatch):
    config, items = online_registered
    monkeypatch.setattr(pilot, "fetch", lambda port, path: (503, b"") if path == "/ready" else (200, b"current"))
    status = pilot.web_status(config, items)
    assert status["phase"] == "MODEL_NOT_READY" and not status["model_ready"]
    monkeypatch.setattr(pilot, "fetch", lambda *args: (200, b"old-page"))
    with pytest.raises(pilot.PilotError, match="RESOURCE_MISMATCH"):
        pilot.web_status(config, items)


def _attach_key_file(config, items, tmp_path):
    path = tmp_path / "private.env"
    path.write_text("sentinel fixture; launcher must not read content", encoding="utf8")
    items["app"]["Config"]["Env"] = [item for item in items["app"]["Config"]["Env"]
                                          if not item.startswith("ONLINE_LLM_API_KEY=")]
    items["app"]["Config"]["Env"].append("ONLINE_LLM_API_KEY_FILE=/run/secrets/deepseek.env")
    items["app"]["Mounts"].append({"Destination": "/run/secrets/deepseek.env", "Source": str(path), "Type": "bind", "RW": False})
    config["containers"]["app"]["mounts"]["/run/secrets/deepseek.env"] = str(path)
    config["credential_file"] = "/run/secrets/deepseek.env"
    return path


def test_readonly_key_file_is_checked_without_reading_or_hashing(online_registered, tmp_path, monkeypatch):
    config, items = online_registered
    path = _attach_key_file(config, items, tmp_path)
    def forbidden(*args, **kwargs):
        raise AssertionError("launcher must not read credentials")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    monkeypatch.setattr(Path, "read_text", forbidden)
    assert set(pilot.validate(config)) == {"app", "gateway"}
    assert path.is_file()


@pytest.mark.parametrize("failure", ["writable", "directory", "missing", "wrong_target", "relative"])
def test_unsafe_credential_file_mount_is_rejected(online_registered, tmp_path, failure):
    config, items = online_registered
    path = _attach_key_file(config, items, tmp_path)
    key_mount = items["app"]["Mounts"][-1]
    if failure == "writable": key_mount["RW"] = True
    elif failure == "directory": key_mount["Source"] = str(tmp_path)
    elif failure == "missing": path.unlink()
    elif failure == "wrong_target": key_mount["Destination"] = "/run/secrets/other.env"
    elif failure == "relative": items["app"]["Config"]["Env"].append("ONLINE_LLM_API_KEY_FILE=relative.env")
    with pytest.raises(pilot.PilotError, match="CREDENTIAL_MOUNT_MISMATCH"):
        pilot.validate(config)


@pytest.mark.parametrize("failure", ["readonly", "missing_mount", "wrong_ledger", "ledger_directory", "diagnostics_file"])
def test_online_private_storage_contract_is_enforced(online_registered, failure):
    config, items = online_registered
    mount = items["app"]["Mounts"][-1]
    private = Path(mount["Source"])
    if failure == "readonly": mount["RW"] = False
    elif failure == "missing_mount": items["app"]["Mounts"].pop()
    elif failure == "wrong_ledger": items["app"]["Config"]["Env"].append("ONLINE_LLM_BUDGET_LEDGER=/tmp/new-ledger.json")
    elif failure == "ledger_directory": (private / "cost-ledger.json").mkdir()
    elif failure == "diagnostics_file": (private / "business-diagnostics").touch()
    with pytest.raises(pilot.PilotError, match="ONLINE_STORAGE_MISMATCH"):
        pilot.validate(config)
