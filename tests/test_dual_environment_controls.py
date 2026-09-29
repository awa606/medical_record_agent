import copy
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import doctor_pilot as pilot
from tests.test_doctor_pilot import registered


def test_pair_rejects_shared_database_or_cookie(tmp_path):
    config = {"project": "demo", "runtime": str(tmp_path / "demo"), "cookie_name": "demo",
              "peer_config": str(tmp_path / "peer.json")}
    peer = {"project": "test", "runtime": str(tmp_path / "test"), "cookie_name": "test"}
    for field in ("runtime", "cookie_name", "project"):
        changed = {**peer, field: config[field]}
        Path(config["peer_config"]).write_text(json.dumps(changed))
        with pytest.raises(pilot.PilotError, match="ISOLATION_MISMATCH"):
            pilot.peer_configuration(config)


def test_active_or_unknown_work_never_stops_environment(registered, monkeypatch):
    config, items = registered
    calls = []
    monkeypatch.setattr(pilot, "command", lambda *args: calls.append(args) or '{"tasks":1,"sessions":0}')
    with pytest.raises(pilot.PilotError, match="SAVE_CONFIRMATION_REQUIRED"):
        pilot.assert_idle(config, items, False)
    assert not calls
    with pytest.raises(pilot.PilotError, match="ACTIVE_WORK"):
        pilot.assert_idle(config, items, True)
    assert all(call[:2] == ("docker", "exec") for call in calls)
    items["app"]["State"]["Running"] = False
    with pytest.raises(pilot.PilotError, match="IDLE_UNKNOWN"):
        pilot.assert_idle(config, items, True)


def test_start_refuses_running_peer(registered, tmp_path, monkeypatch):
    config, items = registered
    config["peer_config"] = "peer.json"
    config["switch_lock"] = str(tmp_path / "pair.json")
    monkeypatch.setattr(pilot, "peer_configuration", lambda _: ({"project": "peer"}, tmp_path / "peer.json"))
    monkeypatch.setattr(pilot, "validate", lambda _: items)
    commands = []
    monkeypatch.setattr(pilot, "command", lambda *args: commands.append(args))
    with pytest.raises(pilot.PilotError, match="PEER_RUNNING"):
        pilot.start(config, tmp_path / "target.json")
    assert not commands


def test_environment_cookie_pinning_cannot_silently_change(registered):
    config, items = registered
    config["cookie_name"] = "expected"
    items["app"]["Config"]["Env"].append("MEDICAL_RECORD_AGENT_SESSION_COOKIE_NAME=other")
    with pytest.raises(pilot.PilotError, match="COOKIE_MISMATCH"):
        pilot.validate(config)


@pytest.mark.parametrize('status,busy', [('stream_ready',False), ('reviewed',False),
    ('formal_record_created',False), ('recording',True), ('transcribing',True), ('unknown',True)])
def test_idle_probe_distinguishes_reviewable_audio_from_running_capture(registered, tmp_path, monkeypatch, status, busy):
    config, items = registered
    db = tmp_path / 'medical_record_agent.sqlite3'
    with sqlite3.connect(db) as conn:
        conn.execute('CREATE TABLE agent_task(status TEXT)')
        conn.execute("INSERT INTO agent_task VALUES ('WAITING_DOCTOR_REVIEW')")
    uploads = tmp_path / 'uploads'
    uploads.mkdir()
    (uploads / 'session.json').write_text(json.dumps({'status':status}))
    def local_probe(*args):
        assert args[:2] == ('docker','exec')
        script = args[-1].replace('/app/runtime', tmp_path.as_posix())
        return subprocess.check_output([sys.executable,'-c',script], text=True)
    monkeypatch.setattr(pilot, 'command', local_probe)
    if busy:
        with pytest.raises(pilot.PilotError, match='ACTIVE_WORK'):
            pilot.assert_idle(config, items, True)
    else:
        pilot.assert_idle(config, items, True)
