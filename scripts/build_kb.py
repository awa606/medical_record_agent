"""将 data/templates/ 下的 Excel 模板转换为 JSON 知识库。

运行：
    python scripts/build_kb.py

输出：
    data/output/kb/*.json
    data/output/common_cold_kb.json
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_builder.kb_builder import build_knowledge_base
from app.data_builder.paths import OUTPUT_DIR


def main() -> None:
    kb = build_knowledge_base()
    table_names = ", ".join(kb["tables"].keys())
    print(f"知识库构建完成，包含表：{table_names}")
    print(f"输出目录：{OUTPUT_DIR}")


if __name__ == "__main__":
    main()
