"""Prepare explicit synthetic course cases via existing localhost APIs.

Uses real Ollama only; never approves, exports, edits model output or clears data.
Private first results are retained so later human edits cannot replace evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import time
from urllib.parse import urlparse

import httpx

CASES = (
    ("SIM-DEMO-0929-FEVER", "合成演示·发热咳嗽", "[医生] 今天哪里不舒服？\n[患者] 发热伴咳嗽、咽痛两天，最高体温38.2℃。\n[医生] 有没有胸痛？有没有用过药？\n[患者] 没有胸痛，还没有用药。"),
    ("SIM-DEMO-0929-NEGATION", "合成演示·否定与家属", "[医生] 今天哪里不舒服？\n[患者] 今天发热，体温38.2℃，伴有咳嗽。\n[医生] 你有花生或药物过敏史吗？家里有人过敏吗？\n[患者] 我没有花生过敏，也没有药物过敏史。我父亲有花生过敏。"),
    ("SIM-DEMO-0929-LIVE", "合成演示·现场问诊", None),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password-file", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if urlparse(args.base_url).hostname not in {"localhost", "127.0.0.1"}:
        parser.error("synthetic preparation is restricted to localhost")
    root = Path(__file__).resolve().parents[1]
    if not args.output_dir.resolve().is_relative_to(root / ".artifacts"):
        parser.error("private output must stay under ignored .artifacts")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    with httpx.Client(base_url=args.base_url, timeout=30, trust_env=False) as client:
        def call(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            response.raise_for_status()
            return response.json()

        call("POST", "/api/auth/login", json={"username": args.username, "password": args.password_file.read_text(encoding="utf8").strip()})
        configured = call("GET", "/api/llm/status")
        if configured.get("provider") != "ollama" or configured.get("model") != "qwen3:4b" or configured.get("mode") != "edge":
            raise RuntimeError("expected real edge Ollama/qwen3:4b; refusing demo/cloud preparation")
        summaries = []
        for marker, name, transcript in CASES:
            matches = call("GET", "/api/encounters", params={"q": marker})["encounters"]
            matches = [e for e in matches if e.get("patient_deidentified_id") == marker]
            if len(matches) > 1:
                raise RuntimeError(f"duplicate synthetic marker: {marker}")
            encounter = matches[0] if matches else call("POST", "/api/encounters", json={"patient_deidentified_id": marker, "patient_display_name": name})
            encounter_id = encounter["id"]
            row = {"case": marker, "encounter_id": encounter_id, "synthetic": True}
            if transcript is None:
                row["state"] = "reserved_for_live_input"
            else:
                task_id = encounter.get("task_id")
                if not task_id:
                    if encounter["check_in_status"] == "registered":
                        call("POST", f"/api/encounters/{encounter_id}/check-in")
                    call("POST", f"/api/encounters/{encounter_id}/start")
                    task_id = call("POST", "/api/records/generate", json={"conversation_text": transcript, "encounter_id": encounter_id})["task_id"]
                start = time.monotonic()
                while True:
                    task = call("GET", f"/api/tasks/{task_id}")
                    if task["status"] in {"WAITING_DOCTOR_REVIEW", "FAILED", "COMPLETED"}:
                        break
                    if time.monotonic() - start > 300:
                        raise TimeoutError(f"task {task_id} remains incomplete; retained for inspection")
                    time.sleep(2)
                trace = call("GET", f"/api/tasks/{task_id}/trace")
                evidence = args.output_dir / f"{marker}-first-result.json"
                if not evidence.exists():
                    evidence.write_text(json.dumps({"transcript": transcript, "task": task, "trace": trace}, ensure_ascii=False, indent=2), encoding="utf8")
                (args.output_dir / f"{marker}-current-result.json").write_text(
                    json.dumps({"task": task, "trace": trace}, ensure_ascii=False, indent=2), encoding="utf8")
                manual_fields = [key for key, field in task.get("result_json", {}).get("fields", {}).items()
                                 if isinstance(field, dict) and str(field.get("doctor_review_note") or "").startswith("manual_doctor_edit_v1:")]
                row.update(task_id=task_id, state=task["status"], result_sha256=hashlib.sha256(evidence.read_bytes()).hexdigest(),
                           human_modified_fields=manual_fields, human_edits=len(manual_fields))
                llm = trace.get("llm", {})
                row["llm"] = llm
                if task["status"] == "FAILED" or llm.get("actual_provider", llm.get("llm_provider")) != "ollama" or llm.get("fallback"):
                    raise RuntimeError(f"real model gate failed for task {task_id}; evidence retained")
            summaries.append(row)
            print(json.dumps(row, ensure_ascii=False), flush=True)
            (args.output_dir / "cases.json").write_text(json.dumps(summaries, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    main()
