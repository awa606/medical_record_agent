from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.asr.prewarm import get_prewarm_status, start_funasr_prewarm


def main() -> int:
    parser = argparse.ArgumentParser(description="Prewarm FunASR models outside the request path.")
    parser.add_argument("--wait", action="store_true", help="Wait until prewarm reaches ready or failed.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    status = start_funasr_prewarm(force=True)
    started = time.perf_counter()
    if args.wait:
        while status["status"] == "warming" and time.perf_counter() - started < args.timeout_seconds:
            time.sleep(args.poll_seconds)
            status = get_prewarm_status()
        if status["status"] == "warming":
            status = {**status, "status": "timeout", "last_error": "prewarm timeout"}
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(status, ensure_ascii=False))
    return 0 if status["status"] in {"ready", "warming"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
