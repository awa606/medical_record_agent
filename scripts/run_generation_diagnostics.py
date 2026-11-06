"""One-call diagnostics for explicitly synthetic cases; output stays local."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time

from app.agents import MedicalRecordOrchestrator
from app.services.llm.llm_record_generator import LLMRecordGenerator, FIELD_KEYS
from app.services.llm.ollama_provider import OllamaLLMProvider


def run(inputs: Path, output: Path):
    data = json.loads(inputs.read_text(encoding="utf8"))
    if data.get("synthetic_only") is not True or [c["id"] for c in data["cases"]] != ["B01", "I01", "P01"]:
        raise ValueError("Only the approved B01/I01/P01 synthetic diagnostic set is accepted")
    if os.getenv("LLM_MAX_RETRIES") != "0" or os.getenv("OLLAMA_MODEL") != "qwen3:4b":
        raise ValueError("Use fixed Qwen3:4b with LLM_MAX_RETRIES=0")
    output.mkdir(parents=True, exist_ok=True)
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(output / "diagnostics.sqlite3")
    rows = []
    for case in data["cases"]:
        provider = OllamaLLMProvider(base_url=os.environ["OLLAMA_BASE_URL"], model="qwen3:4b")
        generator = LLMRecordGenerator(provider=provider, mode="edge", allow_mock_fallback=False)
        generator.diagnostics_enabled = True
        start = time.perf_counter()
        result = MedicalRecordOrchestrator(generator).run_from_text(case["text"])
        fields = result.get("fields")
        item = {"id": case["id"], "status": result["status"], "error": result["error_message"],
                "elapsed_seconds": round(time.perf_counter()-start, 2),
                "attempts": generator.diagnostic_attempts, "trace": generator.get_trace(),
                "final_fields": fields.model_dump() if fields else None,
                "manual_corrections": 0, "code_sha": data["code_sha"]}
        (output / (case["id"] + ".private.json")).write_text(json.dumps(item, ensure_ascii=False, indent=2), encoding="utf8")
        rows.append({k: v for k, v in item.items() if k not in ("attempts", "final_fields")})
        print(json.dumps({"id": case["id"], "status": result["status"],
                          "attempt_count": generator.attempt_count, "seconds": item["elapsed_seconds"],
                          "field_status": {k: getattr(fields, k).status for k in FIELD_KEYS} if fields else {}}, ensure_ascii=False), flush=True)
    (output / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf8")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inputs", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    run(args.inputs, args.output)
