"""Replay archived model responses through the current checks, with no network.

Detailed output stays in a new ignored directory. Raw model checks and pipeline
changes are reported separately; this does not improve a model's first output.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from unittest.mock import patch

from app.schemas import MedicalRecordFields
from app.services.field_grounding import FIELD_KEYS, ground_fields
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.privacy import anonymize_text
from scripts.experiments.compare_local_models import quality_checks
from scripts.replay_citation_outputs import RecordedProvider


def read(path):
    return json.loads(path.read_text(encoding="utf8"))


def replay(directory: Path, output: Path) -> dict:
    report = read(directory / "report.json")
    inputs = {i["id"]: i for i in read(directory / "inputs.private.json")}
    rows = []
    for call in report["calls"]:
        path = directory / f"{call['input_id']}-{call['run']}.private.json"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == call["raw_sha256"], "archived response changed"
        item = read(path)
        case = inputs[call["input_id"]]
        source = anonymize_text(case["source"])
        assert hashlib.sha256(source.encode()).hexdigest() == item["input_sha256"]
        row = {"input_id": call["input_id"], "run": call["run"], "raw_sha256": call["raw_sha256"],
               "before_passed": bool(item["passed"]), "raw_passed": False, "after_passed": False}
        try:
            raw = json.loads(item["transport"][0]["response"]["message"]["content"])
            fields = MedicalRecordFields.model_validate(raw.get("fields", raw))
            raw_checks = quality_checks(call["input_id"], fields, source)
            assert raw_checks == item["first_output_checks"], "raw quality criteria changed"
            row["raw_passed"] = all(raw_checks.values())
            checked = ground_fields(fields.model_copy(deep=True), source, case["trusted"])
            provider = RecordedProvider(raw)
            provider.model = report["model"]
            generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
            generator.max_retries = 0
            generator.source_segments = case["trusted"]
            final = generator.extract_fields(source)
            assert provider.calls == 1
            conflicts = {k: getattr(checked, k).hint for k in FIELD_KEYS if getattr(checked, k).status == "conflicting"}
            pipeline_checks = quality_checks(call["input_id"], final, source)
            pipeline_conflicts = {k: getattr(final, k).hint for k in FIELD_KEYS if getattr(final, k).status == "conflicting"}
            row.update(raw_checks=raw_checks, before_conflicts=item.get("conflicts", {}),
                       after_conflicts=conflicts, pipeline_checks=pipeline_checks, pipeline_conflicts=pipeline_conflicts,
                       after_passed=row["raw_passed"] and not conflicts and all(pipeline_checks.values()) and not pipeline_conflicts)
            detail = {"source": source, "raw": raw, "checked": checked.model_dump(mode="json"), "pipeline": final.model_dump(mode="json"), "summary": row}
            (output / f"{directory.name}-{path.name}").write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf8")
        except Exception as exc:
            row["error"] = f"{type(exc).__name__}: {str(exc)[:300]}"
        rows.append(row)
    return {"model": report["model"], "total": len(rows), "raw_passed": sum(r["raw_passed"] for r in rows),
            "before_passed": sum(r["before_passed"] for r in rows), "after_passed": sum(r["after_passed"] for r in rows),
            "new_regressions": sum(r["before_passed"] and not r["after_passed"] for r in rows), "runs": rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "replay.private.sqlite3")
    with patch("socket.create_connection", side_effect=AssertionError("network forbidden during replay")), patch("socket.socket.connect", side_effect=AssertionError("network forbidden during replay")):
        reports = [replay(path, args.output) for path in args.input]
    summary = {"new_model_calls": 0, "manual_corrections": 0, "reports": reports}
    (args.output / "report.private.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps([{k: v for k, v in r.items() if k != "runs"} for r in reports], ensure_ascii=False))


if __name__ == "__main__":
    main()
