"""Offline replay of the 79 archived citation experiments; never calls a model.

Inputs and detailed output contain source text and must remain in local artifacts.
The saved old pipeline, first-output checks, and current pipeline are scored apart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
from collections import defaultdict
from unittest.mock import patch

from app.schemas import MedicalRecordFields
from app.services.field_grounding import FIELD_KEYS, compact, ground_fields
from app.services.clinical_facts import split_clinical_segments
from app.services.llm.base import LLMProviderResponse
from app.services.llm.llm_record_generator import LLMRecordGenerator
from app.services.privacy import anonymize_text
from scripts.run_local_closed_loop_eval import evaluate

ROOT = Path(__file__).resolve().parents[1]
DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def archived_runs(root):
    for directory in ("runs", "content-results", "negative-results"):
        for path in sorted((root / directory).glob("*.private.json")):
            item = read(path)
            source = item["input"]
            trusted = [] if directory == "negative-results" else [{
                "segment_id": "paired-realtek-13s", "text": source.removeprefix("[患者] "),
                "role": "患者", "speaker_id": "single", "start_time": 0, "end_time": 13.397333,
            }]
            raw = item["raw"][0] if directory == "negative-results" else item["raw_calls"][0]["content"]
            yield path, source, trusted, raw, item["fields"], None, directory, []
    for variant in ("dev-baseline", "dev-enum"):
        directory = root / "dev-results" / variant
        for case_path in sorted((ROOT / "data/clinical_e2e/field_disease_pack_v1/cases").glob("*.json"))[:30]:
            case = read(case_path)
            assert case["privacy"]["synthetic"]
            source = "\n".join(f'{s["role"]}：{s["text"]}' for s in case["segments"])
            input_sha = hashlib.sha256(source.encode()).hexdigest()
            path = directory / f"raw-{input_sha}.json"
            item = read(path)
            assert item["input_sha256"] == input_sha and item["model_digest"] == DIGEST
            old_path = directory / (case["case_id"] + ".json")
            yield path, source, [], item["content"], read(old_path)["fields"], case, variant, [case_path, old_path]


class RecordedProvider:
    name = "recorded-output-replay"
    model = "qwen3:4b"
    model_digest = DIGEST

    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def generate_fields_json(self, conversation_text, *, timeout_seconds):
        self.calls += 1
        return LLMProviderResponse(provider=self.name, model=self.model,
                                   content=json.dumps(self.raw, ensure_ascii=False), latency_ms=0)


def metrics(fields, case):
    active = [getattr(fields, key) for key in FIELD_KEYS if getattr(fields, key).value and not getattr(fields, key).missing]
    result = {"nonempty_fields": len(active), "conflicting_fields": sum(f.status == "conflicting" for f in active),
              "grounded_fields": sum(f.status != "conflicting" for f in active)}
    if case is not None:
        scored = evaluate(fields, case)
        result.update({k: scored[k] for k in ("expected_facts", "recovered_facts")})
    return result


def citation_errors(fields, source):
    sentences = split_clinical_segments(source)
    result = {}
    for key in FIELD_KEYS:
        errors = []
        for span in getattr(fields, key).source_spans:
            quote = compact(span.text)
            if not quote or quote not in compact(source):
                errors.append("quote_not_in_source")
            if span.index is not None and (
                span.index < 0 or span.index >= len(sentences)
                or not quote or quote not in compact(sentences[span.index])
            ):
                errors.append("index_text_mismatch")
        if errors:
            result[key] = sorted(set(errors))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Refusing to overwrite prior replay evidence")
    # Historical inputs must match the original experiment manifest first.
    manifest = read(args.archive / "private-evidence-sha256.json")
    declared = manifest.get("files", manifest) if isinstance(manifest, dict) else manifest
    if not isinstance(declared, dict):
        raise ValueError("Unsupported evidence manifest")
    verified = 0
    for name, expected in declared.items():
        path = args.archive / name
        expected = expected.get("sha256") if isinstance(expected, dict) else expected
        if not isinstance(expected, str) or len(expected) != 64:
            raise ValueError(f"Invalid manifest entry: {name}")
        if sha(path) != expected:
            raise ValueError(f"Historical evidence changed: {name}")
        verified += 1
    args.output.mkdir(parents=True)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.output / "private.sqlite3")
    os.environ["LLM_MAX_RETRIES"] = "0"
    rows, sources = [], {}
    totals = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
    # Enforce replay at the transport boundary, not only by a command-line flag.
    with patch.object(socket.socket, "connect", side_effect=AssertionError("Network forbidden during replay")):
        for path, source, trusted, raw, old, case, group, additional in archived_runs(args.archive):
            sources[str(path.resolve())] = sha(path)
            for extra in additional:
                sources[str(extra.resolve())] = sha(extra)
            provider = RecordedProvider(raw)
            generator = LLMRecordGenerator(provider=provider, allow_mock_fallback=False)
            generator.max_retries = 0
            generator.source_segments = trusted
            safe_source = anonymize_text(source)
            parsed = generator._fields_from_response(json.dumps(raw, ensure_ascii=False))
            raw_errors = citation_errors(parsed, safe_source)
            first_checked = ground_fields(parsed.model_copy(deep=True), safe_source, trusted)
            previous = MedicalRecordFields.model_validate(old)
            current = generator.extract_fields(source)
            assert provider.calls == 1
            versions = {"first_output_checked": first_checked, "saved_old_pipeline": previous, "fixed_pipeline": current}
            scores = {name: metrics(fields, case) for name, fields in versions.items()}
            for name, values in scores.items():
                for metric, count in values.items():
                    totals[group][name][metric] += count
            changes, hidden = {}, []
            for key in FIELD_KEYS:
                before, after = getattr(previous, key), getattr(current, key)
                if before.model_dump() != after.model_dump():
                    changes[key] = {"before": before.model_dump(), "after": after.model_dump()}
                if getattr(first_checked, key).status == "conflicting" and before.value and before.status != "conflicting":
                    hidden.append(key)
            row = {"input_id": case["case_id"] if case else path.stem, "group": group,
                   "raw_sha256": sha(path), "metrics": scores, "raw_citation_errors": raw_errors,
                   "previously_masked_conflicts": hidden, "changed_fields": changes,
                   "repairs": generator.field_repairs,
                   "fields": {name: fields.model_dump(mode="json") for name, fields in versions.items()}}
            rows.append(row)
    assert len(rows) == 79, f"Expected 79 original responses, got {len(rows)}"
    report = {"mode": "OFFLINE_REPLAY", "new_model_calls": 0, "manual_corrections": 0,
              "historical_files_verified": verified, "recorded_responses": len(rows),
              "model_digest": DIGEST, "summary": dict(totals),
              "previously_masked_conflicts": sum(len(r["previously_masked_conflicts"]) for r in rows),
              "changed_runs": sum(bool(r["changed_fields"]) for r in rows),
              "metric_limit": "Automatic fact parser proxy, not clinical accuracy; old normalized output is not first-output quality.",
              "rows": rows, "source_sha256": sources}
    (args.output / "replay.private.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in report if key not in {"rows", "source_sha256"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
