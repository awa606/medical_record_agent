"""把 Excel 模板转换为 JSON 知识库。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.data_builder.excel_io import load_data_rows, write_template_workbook
from app.data_builder.paths import KB_OUTPUT_DIR, OUTPUT_DIR, TEMPLATE_DIR, ensure_data_builder_dirs
from app.data_builder.template_data import (
    JSON_FIELDS_BY_TEMPLATE,
    LIST_FIELDS_BY_TEMPLATE,
    NUMBER_FIELDS_BY_TEMPLATE,
    TEMPLATE_SPECS,
)


def create_excel_templates() -> list[Path]:
    """生成全部 Excel 模板。"""

    ensure_data_builder_dirs()
    return [write_template_workbook(spec) for spec in TEMPLATE_SPECS.values()]


def _split_pipe_list(value: Any) -> list[str]:
    """把 Excel 中用竖线分隔的多值字段转换为列表。"""

    if value in (None, ""):
        return []
    return [item.strip() for item in str(value).split("|") if item.strip()]


def _normalize_number(value: Any) -> int | float | None:
    """把 Excel 读取到的数字字段标准化为 int/float。"""

    if value in (None, ""):
        return None
    number = float(value)
    if number.is_integer():
        return int(number)
    return number


def normalize_row(template_name: str, row: dict[str, Any]) -> dict[str, Any]:
    """按模板字段类型清洗一行数据。"""

    list_fields = LIST_FIELDS_BY_TEMPLATE.get(template_name, set())
    json_fields = JSON_FIELDS_BY_TEMPLATE.get(template_name, set())
    number_fields = NUMBER_FIELDS_BY_TEMPLATE.get(template_name, set())

    normalized: dict[str, Any] = {}
    for key, value in row.items():
        if key in list_fields:
            normalized[key] = _split_pipe_list(value)
        elif key in json_fields:
            if value in (None, ""):
                normalized[key] = {}
            else:
                normalized[key] = json.loads(str(value))
        elif key in number_fields:
            normalized[key] = _normalize_number(value)
        else:
            normalized[key] = value
    return normalized


def build_knowledge_base(template_dir: Path = TEMPLATE_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, Any]:
    """读取 data/templates/ 下的 Excel，并输出 JSON 知识库。

    输出文件：
    - data/output/kb/disease.json 等单表 JSON；
    - data/output/common_cold_kb.json 汇总知识库。
    """

    ensure_data_builder_dirs()
    kb_output_dir = output_dir / "kb"
    kb_output_dir.mkdir(parents=True, exist_ok=True)

    knowledge_base: dict[str, Any] = {
        "meta": {
            "name": "感冒中医证候-症状-问诊路径知识库",
            "data_scope": "课程模拟数据，不含真实患者隐私信息",
            "generated_at": datetime.now(timezone.utc).isoformat(),
        },
        "tables": {},
    }

    for template_name, spec in TEMPLATE_SPECS.items():
        workbook_path = template_dir / spec.filename
        if not workbook_path.exists():
            # 如果模板缺失，先自动生成，保证脚本从干净工程也可以运行。
            write_template_workbook(spec, template_dir)

        rows = [normalize_row(template_name, row) for row in load_data_rows(workbook_path)]
        knowledge_base["tables"][template_name] = rows

        table_json_path = kb_output_dir / f"{template_name}.json"
        table_json_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    combined_path = output_dir / "common_cold_kb.json"
    combined_path.write_text(json.dumps(knowledge_base, ensure_ascii=False, indent=2), encoding="utf-8")
    return knowledge_base


def load_or_build_knowledge_base() -> dict[str, Any]:
    """优先读取已生成的汇总 JSON；不存在时自动构建。"""

    combined_path = OUTPUT_DIR / "common_cold_kb.json"
    if combined_path.exists():
        return json.loads(combined_path.read_text(encoding="utf-8"))
    return build_knowledge_base()
