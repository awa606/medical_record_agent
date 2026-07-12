from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.diarization.factory import create_diarization_engine


def collect_status(
    *,
    scope: str = "diarization dependency check",
    ground_truth_status: str = "available",
    ground_truth_reason: str = "Human-reviewed RTTM files are available for current selected samples.",
) -> dict[str, object]:
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
        "scope": scope,
        "engines": engines,
        "ground_truth": {
            "status": ground_truth_status,
            "reason": ground_truth_reason,
        },
    }


def render_markdown(payload: dict[str, object]) -> str:
    engines = payload["engines"]
    ground_truth = payload["ground_truth"]
    lines = [
        "# Diarization 依赖检查",
        "",
        f"- 范围：{payload['scope']}",
        f"- 标注状态：`{ground_truth['status']}` - {ground_truth['reason']}",
        "",
        "| 引擎 | 状态 | 说明 |",
        "| --- | --- | --- |",
    ]
    for name, item in engines.items():
        lines.append(f"| `{name}` | `{item['status']}` | {item['reason']} |")
    lines.extend(
        [
            "",
            "## 结论",
            "",
            "- 当前交付基线仍为 FunASR VAD + CAM++。",
            "- pyannote 需要隔离环境和本地 `HF_TOKEN`；3D-Speaker 需要独立本地运行区。",
            "- 缺依赖记为 `skipped`，不解释为模型效果差。",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--markdown-output", type=Path, required=True)
    parser.add_argument("--scope", default="diarization dependency check")
    parser.add_argument("--ground-truth-status", default="available")
    parser.add_argument(
        "--ground-truth-reason",
        default="Human-reviewed RTTM files are available for current selected samples.",
    )
    args = parser.parse_args()
    payload = collect_status(
        scope=args.scope,
        ground_truth_status=args.ground_truth_status,
        ground_truth_reason=args.ground_truth_reason,
    )
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    args.markdown_output.write_text(render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
