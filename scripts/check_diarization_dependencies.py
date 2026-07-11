from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.diarization.factory import create_diarization_engine


def collect_status() -> dict[str, object]:
    engines = {}
    for name in ("pyannote", "three_d_speaker"):
        engine = create_diarization_engine(name)
        available, reason = engine.availability()
        engines[name] = {
            "status": "available" if available else "skipped",
            "reason": reason,
        }
    engines["funasr_campp"] = {
        "status": "measured_in_docker",
        "reason": "FunASR VAD + punctuation + CAM++ is the current production baseline.",
    }
    return {
        "scope": "v0.8.7 diarization dependency check",
        "engines": engines,
        "ground_truth": {
            "status": "pending_annotation",
            "reason": "Human-reviewed RTTM files are required before DER/JER conclusions.",
        },
    }


def render_markdown(payload: dict[str, object]) -> str:
    lines = [
        "# v0.8.7 说话人分离依赖检查",
        "",
        "| 引擎 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for name, item in payload["engines"].items():
        lines.append(f"| `{name}` | `{item['status']}` | {item['reason']} |")
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- 当前交付基线仍为 FunASR VAD + CAM++。",
            "- pyannote 需要隔离环境和本地 `HF_TOKEN`；3D-Speaker 需要独立本地运行区。",
            "- 在人工 RTTM 完成前，不输出或宣称 DER/JER 成绩。",
            "- 缺依赖记为 `skipped`，不解释为模型效果差。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    args = parser.parse_args()
    payload = collect_status()
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
