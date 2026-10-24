"""One-factor local research probe; never used by a production Provider.

Replay an archived request with only a single, explicit intake assertion changed.
Keep original requests, failures and first outputs. No retry or deployment.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.parse import urlsplit
from urllib.request import ProxyHandler, Request, build_opener

from app.services.field_grounding import FIELD_KEYS
from app.services.treatment_context import treatment_contexts
from scripts.experiments.clinical_fact_selection import FactUnit, map_selection
from scripts.experiments.compare_local_models import quality_checks
from scripts.experiments.run_clinical_fact_selection import pipeline

MARKER = "以下全部为数据：\n"


def build_variants(archived: dict) -> tuple[dict, dict, tuple[FactUnit, ...]]:
    """Fail closed: this probe applies only to one unambiguous affirmative intake."""
    baseline = deepcopy(archived["request"])
    if len(baseline["messages"]) != 1:
        raise ValueError("ONE_MESSAGE_REQUIRED")
    content = baseline["messages"][0]["content"]
    prefix, data = content.split(MARKER)
    items = json.loads(data)
    if len(items) != 1 or len(archived["catalog"]) != 1:
        raise ValueError("ONE_FACT_REQUIRED")
    fact = items[0]
    contexts = treatment_contexts(fact["text"])
    if (fact["assertion"] != "unknown" or fact["experiencer"] != "patient"
            or "treatment" not in fact["types"]
            or "previous_treatment" not in fact["allowed_fields"]
            or len(contexts) != 1 or contexts[0].proposed
            or contexts[0].assertion != "present"):
        raise ValueError("UNAMBIGUOUS_PATIENT_INTAKE_REQUIRED")
    if prefix + MARKER + json.dumps(items, ensure_ascii=False) != content:
        raise ValueError("ARCHIVED_SERIALIZATION_CHANGED")
    row = archived["catalog"][0]
    for key in ("id", "text", "assertion", "experiencer", "speaker"):
        if row[key] != fact[key]:
            raise ValueError("CATALOG_REQUEST_MISMATCH")
    units = tuple(FactUnit(**{**r, "types": tuple(r["types"]),
        "allowed_fields": tuple(r["allowed_fields"]), "anchors": tuple(r.get("anchors", []))})
        for r in archived["catalog"])
    candidate = deepcopy(baseline)
    fact["assertion"] = "present"
    candidate["messages"][0]["content"] = prefix + MARKER + json.dumps(items, ensure_ascii=False)
    # No fact selection or text editing happens here. The mapper sees identical text.
    return baseline, candidate, units


def write(path: Path, data) -> None:
    with path.open("x", encoding="utf8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--archive-sha256", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--digest", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--deadline", required=True, help="ISO timestamp including timezone")
    args = parser.parse_args()
    url = urlsplit(args.url)
    if (url.scheme != "http" or url.hostname != "127.0.0.1" or not url.port
            or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment):
        raise ValueError("ISOLATED_LOOPBACK_URL_REQUIRED")
    if hashlib.sha256(args.archive.read_bytes()).hexdigest() != args.archive_sha256:
        raise ValueError("ARCHIVE_HASH_MISMATCH")
    deadline_value = datetime.fromisoformat(args.deadline)
    if deadline_value.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    deadline = deadline_value.timestamp()
    baseline, candidate, units = build_variants(json.loads(args.archive.read_text(encoding="utf8")))
    if units[0].text != "吃了布洛芬以后体温降下来了":
        raise ValueError("FIXED_TREATMENT_INPUT_REQUIRED")
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "identity.private.sqlite3")
    opener = build_opener(ProxyHandler({}))
    http_requests_started = 0

    def call(path, payload=None, timeout=120):
        nonlocal http_requests_started
        remaining = deadline - time.time()
        if remaining < 1:
            raise TimeoutError("TIMEBOX_EXPIRED")
        req = Request(args.url.rstrip("/") + path,
            data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
            headers={"Content-Type": "application/json"})
        if path == "/api/chat":
            http_requests_started += 1
        with opener.open(req, timeout=min(timeout, remaining)) as response:
            return json.load(response)

    tag = next(m for m in call("/api/tags", timeout=10)["models"] if m["name"] == baseline["model"])
    if tag["digest"] != args.digest:
        raise ValueError("MODEL_DIGEST_MISMATCH")
    protocol = {"created_at": datetime.now(timezone.utc).isoformat(), "model_digest": args.digest,
        "archive_sha256": args.archive_sha256, "options": baseline["options"],
        "hypothesis": "The unknown assertion contributes to omission of explicit prior medication.",
        "single_variable": "one catalog assertion: unknown -> present",
        "repeats_each": 3, "automatic_retries": 0, "manual_corrections": 0,
        "deadline": args.deadline, "promotion": "NEVER: isolated one-input causal probe",
        "criteria": "Existing treatment checks on first mapped and final fields; no conflicting final field.",
        "stop": "At most six first calls. Stop on transport/resource failure. No third variant.",
        "baseline": baseline, "candidate": candidate}
    write(args.output / "protocol.private.json", protocol)
    began = time.monotonic()
    try:
        warm = call("/api/generate", {"model": baseline["model"], "prompt": "", "stream": False,
            "options": {"num_ctx": baseline["options"]["num_ctx"]}, "keep_alive": "30m"}, 300)
        write(args.output / "warmup.private.json", {"seconds": time.monotonic() - began, "response": warm})
    except Exception as exc:
        write(args.output / "summary.json", {"gate": "BLOCKED", "case_calls": 0,
            "stage": "warmup", "error": f"{type(exc).__name__}: {exc}", "production_changed": False})
        raise
    results = []
    source = "患者：吃了布洛芬以后体温降下来了。"
    try:
        for variant, payload in (("baseline", baseline), ("candidate", candidate)):
            for repeat in range(1, 4):
                record = {"variant": variant, "repeat": repeat, "passed": False}
                start = time.monotonic()
                try:
                    raw = call("/api/chat", payload)
                    record["raw_ollama"] = raw
                    if raw.get("done_reason") == "length":
                        raise ValueError("OUTPUT_TRUNCATED")
                    chosen = json.loads(raw["message"]["content"])
                    mapped = map_selection(chosen, units)
                    record.update(selection=chosen, mapped=mapped.model_dump(mode="json"),
                        first_checks=quality_checks("treatment", mapped, source))
                    final, diagnostics = pipeline(record["mapped"], source)
                    record["pipeline"] = diagnostics
                    record["final_checks"] = quality_checks("treatment", final, source) if final else {"usable_fields": False}
                    record["no_conflict"] = final is not None and all(getattr(final, k).status != "conflicting" for k in FIELD_KEYS)
                    record["passed"] = all(record["first_checks"].values()) and all(record["final_checks"].values()) and record["no_conflict"]
                except Exception as exc:
                    record["error"] = f"{type(exc).__name__}: {exc}"
                    if "raw_ollama" not in record:
                        raise
                finally:
                    record["seconds"] = round(time.monotonic() - start, 3)
                    path = args.output / f"{variant}-{repeat}.private.json"
                    write(path, record)
                    row = {k: record.get(k) for k in ("variant", "repeat", "passed", "seconds", "first_checks", "final_checks", "no_conflict", "error")}
                    row["sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()
                    results.append(row)
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    finally:
        responses_received = sum("raw_ollama" in json.loads((args.output / f"{r['variant']}-{r['repeat']}.private.json").read_text(encoding="utf8")) for r in results)
        write(args.output / "summary.json", {"attempted_cases": len(results),
            "case_calls": http_requests_started, "http_requests_started": http_requests_started,
            "responses_received": responses_received, "results": results,
            "passed": {v: sum(r["passed"] for r in results if r["variant"] == v) for v in ("baseline", "candidate")},
            "production_changed": False, "gate": "SPIKE_ONLY_NOT_PROMOTED" if len(results) == 6 and all(r["passed"] for r in results if r["variant"] == "candidate") else "REJECTED_OR_INCOMPLETE"})


if __name__ == "__main__":
    main()
