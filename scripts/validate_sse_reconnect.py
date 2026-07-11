from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.api.asr_sessions import _append_events, _asr_session_event_stream, create_asr_session
from app.schemas import ASRSessionEvent


async def _collect(session_id: str, last_event_id: int) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    async for chunk in _asr_session_event_stream(session_id, last_event_id=last_event_id, delay_ms=0):
        for block in chunk.strip().split("\n\n"):
            if not block.strip():
                continue
            parsed: dict[str, object] = {}
            for line in block.splitlines():
                if line.startswith("id: "):
                    parsed["id"] = int(line[4:])
                elif line.startswith("event: "):
                    parsed["event"] = line[7:]
                elif line.startswith("data: "):
                    parsed["data"] = json.loads(line[6:])
            if parsed:
                events.append(parsed)
    return events


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ASR SSE Last-Event-ID reconnect behavior.")
    parser.add_argument("--events", type=int, default=500)
    parser.add_argument("--resume-tail", type=int, default=50)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "data" / "asr_eval" / "reports" / "v0_8_11_sse_reconnect" / "sse_reconnect_report.json")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as tmp:
        os.environ["MEDICAL_RECORD_AGENT_UPLOAD_DIR"] = str(Path(tmp) / "uploads")
        session = create_asr_session(engine="mock")
        synthetic = [
            ASRSessionEvent(id=1, event="transcribing_progress", data={"sequence": index})
            for index in range(args.events)
        ]
        synthetic.append(ASRSessionEvent(id=1, event="completed", data={"status": "completed"}))
        _append_events(session.session_id, synthetic)

        started = time.perf_counter()
        first = asyncio.run(_collect(session.session_id, 0))
        full_elapsed = time.perf_counter() - started
        resume_after = int(first[-(args.resume_tail + 1)]["id"])
        resumed = asyncio.run(_collect(session.session_id, resume_after))

    first_ids = [int(item["id"]) for item in first]
    resumed_ids = [int(item["id"]) for item in resumed]
    report = {
        "status": "passed",
        "total_events": len(first),
        "expected_total_events": args.events + 1,
        "full_stream_elapsed_seconds": round(full_elapsed, 4),
        "resume_after_id": resume_after,
        "resumed_events": len(resumed),
        "expected_resumed_events": args.resume_tail,
        "first_ids_monotonic": first_ids == sorted(first_ids),
        "resumed_ids_monotonic": resumed_ids == sorted(resumed_ids),
        "resume_has_no_duplicate_boundary": resume_after not in resumed_ids,
    }
    failures = [
        key
        for key in ["first_ids_monotonic", "resumed_ids_monotonic", "resume_has_no_duplicate_boundary"]
        if not report[key]
    ]
    if len(first) != args.events + 1:
        failures.append("total_events")
    if len(resumed) != args.resume_tail:
        failures.append("resumed_events")
    if failures:
        report["status"] = "failed"
        report["failures"] = failures

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
