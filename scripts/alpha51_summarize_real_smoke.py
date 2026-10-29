"""Summarize a private Alpha 5.1 run without copying recordings or transcripts.

The ignored run directory contains the source artifacts. The optional JSON output
contains only anonymous IDs, hashes, provider identity and gate results.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import wave
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
NEGATIVE_PEANUT = "没有花生过敏"
NEGATIVE_DRUG = "没有药物过敏史"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def document_text(path: Path) -> str:
    with ZipFile(path) as archive:
        root = ElementTree.fromstring(archive.read("word/document.xml"))
    return " ".join(node.text or "" for node in root.findall(".//w:t", WORD_NS))


def summarize_case(run_dir: Path, connection: sqlite3.Connection, name: str, encounter_id: int) -> dict:
    row = connection.execute(
        "SELECT id, current_stage, result_json FROM agent_task WHERE encounter_id=? ORDER BY id DESC LIMIT 1",
        (encounter_id,),
    ).fetchone()
    if row is None:
        raise ValueError(f"{name}: no task for encounter {encounter_id}")
    task_id, current_stage, raw_result = row
    result = json.loads(raw_result)
    review_dir = run_dir / {"text": "text-review", "upload": "audio-dual-review", "microphone": "mic-review"}[name]
    review = json.loads((review_dir / "review-result.json").read_text(encoding="utf-8"))
    docx = review_dir / f"task_{task_id}_medical_record.docx"
    exported = document_text(docx)
    trace = result.get("llm_trace") or {}
    extraction = (trace.get("operations") or {}).get("field_extraction") or {}
    asr = result.get("asr_source") or {}
    fields = result.get("fields") or {}
    summary = {
        "encounter_id": encounter_id,
        "task_id": task_id,
        "stage": current_stage,
        "revision_id": review.get("revision_after"),
        "review_status": review.get("status"),
        "docx_sha256": sha256(docx),
        "docx_size_bytes": docx.stat().st_size,
        "field_statuses": {key: value.get("status") for key, value in fields.items()
                           if isinstance(value, dict) and "status" in value},
        "llm_provider": extraction.get("actual_provider"),
        "llm_model": extraction.get("model"),
        "llm_model_digest": trace.get("model_digest"),
        "mock_or_cloud_fallback": bool(extraction.get("fallback") or trace.get("fallback")),
        "export_contains_fever": "发热" in exported,
        "export_contains_snakebite": "蛇咬" in exported,
        "export_contains_negative_peanut": NEGATIVE_PEANUT in exported,
        "export_contains_negative_drug_allergy": NEGATIVE_DRUG in exported,
    }
    if name != "text":
        audio_id = asr.get("audio_id")
        if not audio_id:
            raise ValueError(f"{name}: missing source audio ID")
        audio = run_dir / "runtime" / "uploads" / f"{audio_id}.wav"
        with wave.open(str(audio), "rb") as source:
            duration = source.getnframes() / source.getframerate()
        summary.update({
            "audio_id": audio_id,
            "audio_sha256": sha256(audio),
            "audio_duration_seconds": round(duration, 3),
            "asr_backend": asr.get("backend"),
            "asr_engine": asr.get("engine"),
            "role_gate": (asr.get("role_quality") or {}).get("status"),
            "manual_role_mapping": any(
                decision.get("provider") == "manual"
                for decision in (asr.get("role_quality") or {}).get("decisions", [])
            ),
        })
    checks = [
        current_stage == "exported",
        review.get("status") == "passed",
        extraction.get("actual_provider") == "ollama",
        not summary["mock_or_cloud_fallback"],
        summary["export_contains_fever"],
        not summary["export_contains_snakebite"],
        all(status != "conflicting" for status in summary["field_statuses"].values()),
    ]
    if name != "text":
        checks.extend([summary["asr_backend"] == "funasr", summary["role_gate"] == "passed"])
    if name == "text":
        checks.extend([summary["export_contains_negative_peanut"], summary["export_contains_negative_drug_allergy"]])
    if name == "microphone":
        checks.append(summary["export_contains_negative_drug_allergy"])
    summary["smoke_pass"] = all(checks)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--text-encounter", type=int, required=True)
    parser.add_argument("--upload-encounter", type=int, required=True)
    parser.add_argument("--microphone-encounter", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    connection = sqlite3.connect(args.run_dir / "runtime" / "mra.sqlite3")
    cases = {
        name: summarize_case(args.run_dir, connection, name, encounter_id)
        for name, encounter_id in (
            ("text", args.text_encounter),
            ("upload", args.upload_encounter),
            ("microphone", args.microphone_encounter),
        )
    }
    report = {
        "schema_version": "alpha51-real-three-path-v1",
        "evidence_scope": "DEV-01 synthetic cases; microphone audio was recorded by the user in Edge",
        "paths_passed": sum(case["smoke_pass"] for case in cases.values()),
        "paths_total": len(cases),
        "cases": cases,
        "limitations": [
            "This is an engineering smoke, not clinical accuracy validation.",
            "One-person microphone role was confirmed manually for a synthetic patient actor.",
            "The text case needed doctor correction of an unsupported chief-complaint citation.",
        ],
    }
    output = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    else:
        print(output)
    if report["paths_passed"] != report["paths_total"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
