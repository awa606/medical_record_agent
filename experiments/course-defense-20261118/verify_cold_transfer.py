"""Use a newly created synthetic Windows classroom store and a private Linux restore."""
import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PureWindowsPath
import shutil
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory

import requests


RUNTIME_SHA = "5cc24fe0ff55c645447afbffe9adf3dbdf218f14b01482885e0fc7adce5128ee"
IMAGE = "sha256:7dc6ee49c65677b468dfcd27c922328eee904a208073b044045d95c0dbf1018f"
TABLES = ["patient", "encounter", "agent_task", "record_revision", "approval", "export_event"]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def doctor(base, state):
    credentials = json.loads((state / "本机账户.json").read_text(encoding="utf8"))
    api = requests.Session()
    api.trust_env = False
    result = api.post(base + "/api/auth/login", timeout=15,
                      json={k: credentials[k] for k in ["username", "password"]})
    result.raise_for_status()
    user = get(api, base, "/api/auth/me").json()
    assert user["role"] == "doctor" and user["username"] == credentials["username"]
    assert get(api, base, "/course/identity").json()["runtime_sha256"] == RUNTIME_SHA
    return api


def get(api, base, path, **kwargs):
    r = api.get(base + path, timeout=15, **kwargs)
    r.raise_for_status()
    return r


def receipt_count(state):
    uri = (state / "candidate.sqlite3").resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as db:
        return db.execute("select count(*) from export_event where task_id=1").fetchone()[0]


def observe(api, base, state, output_pdf):
    case = get(api, base, "/api/encounters").json()["encounters"]
    assert len(case) == 1 and case[0]["patient_deidentified_id"] == "SIM-COURSE-FEVER-01"
    task = get(api, base, "/api/tasks/1").json()
    ready = get(api, base, "/api/tasks/1/export-readiness").json()
    rec = task["result_json"]["export_event"]
    assert ready["revision_id"] == ready["revision_number"] == rec["revision_id"] == 3
    assert ready["approval_id"] == rec["approval_id"] == task["result_json"]["approval"]["id"] == 1
    assert task["result_json"]["approval"]["revision_id"] == 3 and ready["ready"]
    signed_sha = ready["exports"]["pdf_sha256"]
    win_path = PureWindowsPath(ready["exports"]["pdf_path"])
    assert win_path.is_absolute() and win_path.drive.endswith(":")
    stored_pdf = state / "outputs" / win_path.name
    assert signed_sha == digest(stored_pdf.read_bytes())
    before = receipt_count(state)
    response = get(api, base, "/api/tasks/1/exports/pdf", params={"sha256": signed_sha})
    assert response.content.startswith(b"%PDF-") and digest(response.content) == signed_sha
    after = receipt_count(state)
    assert before == after == 1
    with output_pdf.open("xb") as file:
        file.write(response.content)
    return {"task": task["id"], "encounter": task["encounter_id"], "revision": ready["revision_number"],
            "content_hash": ready["content_hash"], "approval": ready["approval_id"], "receipt": rec["id"],
            "receipts_before_get": before, "receipts_after_get": after, "stored_path_is_windows_absolute": True,
            "doctor_role_verified": True, "stored_pdf_sha256": signed_sha,
            "download_pdf_sha256": digest(response.content), "download_http": response.status_code}


def sign_once(api, base, actions):
    steps = [json.loads(line) for line in actions.read_text(encoding="utf8").splitlines()]
    expected = ["/api/tasks/1/" + suffix for suffix in (
        "review", "review", "approve", "export?expected_revision_id=3&expected_approval_id=1")]
    assert [step["route"] for step in steps] == expected and all(step["method"] == "POST" for step in steps)
    for step in steps:
        body = step["json"]
        current = get(api, base, "/api/tasks/1/export-readiness").json()
        if step["route"].endswith("/review"):
            assert body["expected_revision_id"] == current["revision_id"]
            body["expected_content_hash"] = current["content_hash"]
        elif step["route"].endswith("/approve"):
            assert body["revision_id"] == current["revision_id"]
            body["content_hash"] = current["content_hash"]
        result = api.post(base + step["route"], json=body, timeout=30)
        result.raise_for_status()


def linux_leg():
    from edge_sqlite_backup import restore_sqlite, sqlite_report
    from verify_platform_replay import deployed
    source, output, bundle = Path("/backup"), Path("/result"), Path("/bundle")
    with TemporaryDirectory(prefix="private-restore-") as tmp:
        dest = Path(tmp) / "restored"
        dest.mkdir(mode=0o700)
        # Work on a private local copy; SQLite can create WAL files on open.
        db_copy = Path(tmp) / "cold-copy.sqlite3"
        shutil.copyfile(source / "candidate.sqlite3", db_copy)
        restore_sqlite(db_copy, dest / "candidate.sqlite3", require_tables=TABLES)
        shutil.copytree(source / "outputs", dest / "outputs")
        shutil.copyfile(source / "本机账户.json", dest / "本机账户.json")
        (dest / "本机账户.json").chmod(0o600)
        sql = sqlite_report(dest / "candidate.sqlite3")
        assert sql["integrity_check"] == "ok"
        with deployed(bundle, dest) as (base, _), doctor(base, dest) as api:
            observed = observe(api, base, dest, output / "Linux恢复下载_R3.pdf")
        assert not (dest / "replay-events.jsonl").exists(), "恢复期间出现新模型回放事件"
        observed.update(restored_before_start_counts=sql["tables"], sqlite_integrity=sql["integrity_check"],
                        fresh_private_data_root=True, replay_events_after_restore=0, restore_post_export_calls=0,
                        cold_database_sha256=digest((source / "candidate.sqlite3").read_bytes()))
        (output / "linux-summary.json").write_text(json.dumps(observed, ensure_ascii=False, indent=2), encoding="utf8")


def windows_leg(repo, delivery, evidence):
    from edge_sqlite_backup import backup_sqlite, sqlite_report
    from verify_platform_replay import deployed
    recipe = repo / "experiments/course-defense-20261118"
    bundle = delivery / "软件/现场回放"
    actions = delivery / "双平台/模拟核对动作.jsonl"
    assert os.name == "nt" and digest((bundle / "运行源/runtime-sha256.json").read_bytes()) == RUNTIME_SHA
    self_path = Path(__file__).resolve()
    with TemporaryDirectory(prefix="MediListen-cold-source-") as tmp:
        work = Path(tmp)
        state, cold, exchange = work / "windows", work / "backup", work / "results"
        cold.mkdir()
        exchange.mkdir()
        with deployed(bundle, state) as (base, _), doctor(base, state) as api:
            assert receipt_count(state) == 0
            sign_once(api, base, actions)
            win = observe(api, base, state, exchange / "Windows签署下载_R3.pdf")
        checkpoint = sqlite_report(state / "candidate.sqlite3")
        assert checkpoint["integrity_check"] == "ok"
        backup_sqlite(state / "candidate.sqlite3", cold / "candidate.sqlite3")
        shutil.copytree(state / "outputs", cold / "outputs")
        shutil.copyfile(state / "本机账户.json", cold / "本机账户.json")
        archive_digest = digest((cold / "candidate.sqlite3").read_bytes())
        assert len(list((cold / "outputs").glob("*.pdf"))) == 1
        command = ["docker", "run", "--rm", "--network", "none", "--entrypoint", "python",
                   "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONPATH=/tools"]
        for host, path, writable in [(self_path, "/tools/recovery.py", False),
                (recipe / "verify_platform_replay.py", "/tools/verify_platform_replay.py", False),
                (repo / "scripts/edge_sqlite_backup.py", "/tools/edge_sqlite_backup.py", False),
                (bundle, "/bundle", False), (cold, "/backup", False), (exchange, "/result", True)]:
            command.extend(["--mount", f"type=bind,source={host},destination={path}" + ("" if writable else ",readonly")])
        command.extend([IMAGE, "-B", "-X", "utf8", "/tools/recovery.py", "--linux"])
        subprocess.run(command, check=True, timeout=120)
        linux = json.loads((exchange / "linux-summary.json").read_bytes())
        assert all(linux[key] == value for key, value in win.items())
        assert archive_digest == linux["cold_database_sha256"] and checkpoint["tables"] == linux["restored_before_start_counts"]
        assert (exchange / "Windows签署下载_R3.pdf").read_bytes() == (exchange / "Linux恢复下载_R3.pdf").read_bytes()
        for pdf in exchange.glob("*.pdf"):
            shutil.copyfile(pdf, evidence / pdf.name)
        report = {"result": "PASS", "verified_utc": datetime.now(timezone.utc).isoformat(), "synthetic_cases": 1,
                  "runtime_sha256": RUNTIME_SHA, "linux_image": IMAGE, "docker_network": "none",
                  "source_closed_before_backup": True, "same_table_counts_before_linux_start": True,
                  "original_and_recovered_pdf_identical": True, "windows": win, "linux": linux}
        (evidence / "跨平台恢复结果.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
        print(json.dumps({k: report[k] for k in ["result", "runtime_sha256", "original_and_recovered_pdf_identical"]}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--out", type=Path, help="新的证据目录；默认在脚本旁创建带时间戳的复验目录")
    parser.add_argument("--delivery", type=Path, help="包含软件和双平台目录的本次交付根目录")
    parser.add_argument("--linux", action="store_true")
    args = parser.parse_args()
    if args.linux:
        linux_leg()
    else:
        if args.repo is None or args.delivery is None:
            parser.error("Windows 复验需要 --repo 和 --delivery")
        repo = args.repo.resolve(strict=True)
        delivery = args.delivery.resolve(strict=True)
        sys.path[:0] = [str(repo / "scripts"), str(repo / "experiments/course-defense-20261118")]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = args.out or (Path(__file__).resolve().parent / "复验" / stamp)
        target.mkdir(parents=True, exist_ok=False)
        windows_leg(repo, delivery, target.resolve())
