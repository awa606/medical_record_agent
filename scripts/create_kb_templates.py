"""生成感冒中医证候知识库 Excel 模板。

运行：
    python scripts/create_kb_templates.py
"""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.data_builder.kb_builder import create_excel_templates


def main() -> None:
    paths = create_excel_templates()
    print("已生成 Excel 模板：")
    for path in paths:
        print(f"- {path}")


if __name__ == "__main__":
    main()
