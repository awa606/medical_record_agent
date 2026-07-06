"""评估字段抽取结果。

运行方式一：使用标准答案演示完整评估流程
    python scripts/evaluate_extraction.py

运行方式二：指定模型/规则抽取结果
    python scripts/evaluate_extraction.py --pred data/output/predicted_extractions.json

预测文件格式示例：
{
  "cases": [
    {
      "case_id": "GEN_COLD_001",
      "predicted_symptom_ids": ["SYM_CHILLS", "SYM_NO_SWEAT"],
      "predicted_fields": {"主诉": "发热怕冷2天"}
    }
  ]
}
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_builder.evaluator import evaluate_extraction
from app.data_builder.paths import OUTPUT_DIR


def main() -> None:
    parser = argparse.ArgumentParser(description="评估模拟病历字段抽取结果")
    parser.add_argument("--gold", type=Path, default=OUTPUT_DIR / "generated_dialogues.json", help="标准答案 JSON")
    parser.add_argument("--pred", type=Path, default=None, help="预测结果 JSON，可选")
    parser.add_argument("--output", type=Path, default=OUTPUT_DIR / "evaluation_report.json", help="评估报告输出 JSON")
    args = parser.parse_args()

    report = evaluate_extraction(gold_path=args.gold, pred_path=args.pred, output_path=args.output)
    aggregate = report["aggregate"]
    print("评估完成：")
    print(f"- Precision: {aggregate['precision']}")
    print(f"- Recall: {aggregate['recall']}")
    print(f"- F1: {aggregate['f1']}")
    print(f"- 字段完整率: {aggregate['field_completeness']}")
    print(f"- 输出文件: {args.output}")
    print(f"- Markdown 报告: {args.output.with_suffix('.md')}")


if __name__ == "__main__":
    main()
