"""data_builder 模块统一路径配置。

本项目把可编辑 Excel 模板放在 data/templates/，把脚本生成的 JSON、
模拟对话和评估报告统一放在 data/output/。路径集中在这里，便于课堂展示
时说明数据流向，也避免每个脚本重复拼接路径。
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
TEMPLATE_DIR = DATA_DIR / "templates"
OUTPUT_DIR = DATA_DIR / "output"
KB_OUTPUT_DIR = OUTPUT_DIR / "kb"


def ensure_data_builder_dirs() -> None:
    """确保数据构建需要的目录存在。"""

    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    KB_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
