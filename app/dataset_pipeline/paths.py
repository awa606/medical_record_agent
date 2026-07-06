"""外部数据集处理路径配置。"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
RAW_EXTERNAL_DIR = DATA_DIR / "raw_external"
PROCESSED_DIR = DATA_DIR / "processed"
ANNOTATION_DIR = DATA_DIR / "annotation"
OUTPUT_DIR = DATA_DIR / "output"


def ensure_pipeline_dirs() -> None:
    """确保流水线输入输出目录存在。"""

    RAW_EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    ANNOTATION_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
