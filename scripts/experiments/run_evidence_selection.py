"""Bounded local-Ollama spike; raw source/output remain in ignored artifacts."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from urllib.request import Request, urlopen

from app.services.field_grounding import FIELD_KEYS, ground_fields
from app.services.llm.llm_record_generator import LLMRecordGenerator
from scripts.experiments.evidence_selection import catalog, map_selection, selection_prompt, selection_schema
from scripts.replay_citation_outputs import RecordedProvider, citation_errors, metrics

ROOT = Path(__file__).resolve().parents[2]
DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf8")


def inputs():
    text = "患者今天发热三十八点二度，伴有咳嗽和咽痛，没有胸痛，也没有药物过敏史。"
    yield "realtek13", "[患者] " + text, [{"segment_id": "paired-realtek-13s", "text": text,
        "role": "患者", "speaker_id": "single", "start_time": 0, "end_time": 13.397333}], None
    case = read(ROOT / "data/clinical_e2e/field_disease_pack_v1/cases/ce2e_v1_011_three_party_child_fever.json")
    yield "case11", "\n".join(f'{s["role"]}：{s["text"]}' for s in case["segments"]), [], case
    for key, text in {"question": "医生：有没有胸痛？", "family": "患者：我父亲有花生过敏。",
                      "negative_allergy": "患者：我没有花生过敏。",
                      "treatment": "患者：吃了布洛芬以后体温降下来了。",
                      "missing": "患者：今天有点不舒服。"}.items():
        yield key, text, [], None


def pass_checks(key, fields, errors):
    active = {k for k in FIELD_KEYS if getattr(fields, k).value and not getattr(fields, k).missing}
    conflicts = {k for k in active if getattr(fields, k).status == "conflicting"}
    checks = {"no_citation_error": not errors, "no_conflict": not conflicts}
    if key == "realtek13":
        checks["four_expected_fields"] = active == {"chief_complaint", "present_illness", "accompanying_symptoms", "allergy_history"}
    elif key == "case11":
        checks["headache_kept_in_chief"] = "头痛" in fields.chief_complaint.value
        checks["no_wrong_history_or_treatment"] = not (active & {"previous_treatment", "past_history", "allergy_history", "physical_exam"})
    elif key in {"question", "family"}:
        checks["no_patient_fact"] = not active
    elif key == "negative_allergy":
        checks["allergy_only"] = active == {"allergy_history"}
        checks["negation_retained"] = "没有花生过敏" in fields.allergy_history.value
    elif key == "treatment":
        checks["treatment_kept"] = "previous_treatment" in active
        checks["no_allergy_or_exam"] = not (active & {"allergy_history", "physical_exam", "past_history"})
    else:
        checks["no_unmentioned_history"] = not (active - {"chief_complaint", "present_illness"})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--url", default="http://ollama:11434")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "private.sqlite3")
    os.environ["LLM_MAX_RETRIES"] = "0"
    model = next(m for m in json.load(urlopen(args.url + "/api/tags", timeout=15))["models"] if m["name"] == "qwen3:4b")
    assert model["digest"] == DIGEST
    prepared = list(inputs())
    options = {"temperature": 0, "num_ctx": 8192, "num_predict": 2048}
    source_hashes = {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted((ROOT / "scripts/experiments").glob("*.py"))}
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "base_sha": args.base_sha,
              "candidate_source_sha256": source_hashes, "model_digest": DIGEST, "options": options,
              "think": False, "retries": 0, "manual_corrections": 0, "calls": [],
              "scope": "Archived real ASR transcript plus synthetic development negatives; no new ASR or microphone recording"}
    write(args.output / "inputs.private.json", [{"id": k, "source": s, "trusted": t, "case": c} for k,s,t,c in prepared])
    # Persist criteria before inference; do not adjust these from model output.
    write(args.output / "protocol.json", {"cases": [p[0] for p in prepared], "runs_each": 3,
          "quality_checks_source_sha256": source_hashes["scripts/experiments/run_evidence_selection.py"],
          "stop": "Complete these 21 calls; any failed check prevents development/held-out expansion and deployment."})
    for key, source, trusted, case in prepared:
        safe, rows = catalog(source, trusted)
        for run in range(1, 4):
            start = time.monotonic()
            record = {"input_id": key, "run": run, "catalog": [asdict(r) for r in rows],
                      "source_sha256": hashlib.sha256(safe.encode()).hexdigest()}
            try:
                payload = {"model": "qwen3:4b", "messages": [{"role": "user", "content": selection_prompt(rows)}],
                           "format": selection_schema(rows), "stream": False, "think": False,
                           "options": options, "keep_alive": "30m"}
                request = Request(args.url + "/api/chat", data=json.dumps(payload, ensure_ascii=False).encode(),
                                  headers={"Content-Type": "application/json"})
                raw = json.load(urlopen(request, timeout=120))
                record["raw_ollama"] = raw
                selection = json.loads(raw["message"]["content"])
                record["selection"] = selection
                mapped = map_selection(selection, rows)
                record["mapped"] = mapped.model_dump(mode="json")
                errors = citation_errors(mapped, safe)
                checked = ground_fields(mapped.model_copy(deep=True), safe, trusted)
                record["first_selection_checked"] = checked.model_dump(mode="json")
                record["citation_errors"] = errors
                record["metrics"] = metrics(checked, case)
                record["checks"] = pass_checks(key, checked, errors)
                provider = RecordedProvider(record["mapped"])
                generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
                generator.max_retries = 0; generator.source_segments = trusted
                final = generator.extract_fields(source)
                assert provider.calls == 1
                record["pipeline"] = final.model_dump(mode="json")
                record["repairs"] = generator.field_repairs
                record["passed"] = all(record["checks"].values())
            except Exception as exc:
                record.update(passed=False, error=f"{type(exc).__name__}: {str(exc)[:300]}")
            record["seconds"] = round(time.monotonic() - start, 3)
            path = args.output / f"{key}-{run}.private.json"
            write(path, record)
            summary = {k: record[k] for k in ("input_id", "run", "passed", "seconds")}
            summary.update(checks=record.get("checks"), metrics=record.get("metrics"), error=record.get("error"),
                           raw_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            report["calls"].append(summary)
            write(args.output / "report.json", report)
            print(json.dumps(summary, ensure_ascii=False), flush=True)
    report.update(completed_at=datetime.now(timezone.utc).isoformat(),
                  passed=sum(row["passed"] for row in report["calls"]), total=len(report["calls"]))
    report["gate"] = "SMALL_SPIKE_PASS" if report["passed"] == report["total"] else "REJECTED"
    write(args.output / "report.json", report)
    print(report["gate"], flush=True)


if __name__ == "__main__":
    main()
