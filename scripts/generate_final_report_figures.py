from __future__ import annotations

from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "final_report" / "images"

BLUE = "#2563eb"
BLUE_SOFT = "#eff6ff"
BLUE_LINE = "#93c5fd"
GRAY = "#4b5563"
GRAY_SOFT = "#f3f4f6"
GRAY_LINE = "#d1d5db"
GREEN_SOFT = "#ecfdf5"
GREEN_LINE = "#86efac"
YELLOW_SOFT = "#fffbeb"
YELLOW_LINE = "#fcd34d"
RED_SOFT = "#fef2f2"
RED_LINE = "#fecaca"
TEXT = "#111827"
MUTED = "#6b7280"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()
    draw_architecture(fonts).save(OUTPUT_DIR / "fig03_architecture.png")
    draw_agent_flow(fonts).save(OUTPUT_DIR / "fig04_agent_flow.png")
    draw_decision_prompt_flow(fonts).save(OUTPUT_DIR / "fig05_decision_prompt_flow.png")
    draw_test_evidence_flow(fonts).save(OUTPUT_DIR / "fig10_test_evidence_flow.png")
    print(OUTPUT_DIR)
    return 0


def load_fonts() -> dict[str, ImageFont.FreeTypeFont]:
    font_candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    font_path = next((path for path in font_candidates if path.exists()), None)
    if font_path is None:
        return {
            "title": ImageFont.load_default(),
            "body": ImageFont.load_default(),
            "small": ImageFont.load_default(),
        }
    return {
        "title": ImageFont.truetype(str(font_path), 34),
        "body": ImageFont.truetype(str(font_path), 23),
        "small": ImageFont.truetype(str(font_path), 18),
    }


def canvas(title: str, fonts: dict[str, ImageFont.FreeTypeFont]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1600, 920), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 42), title, fill=TEXT, font=fonts["title"])
    draw.line((70, 92, 1530, 92), fill=BLUE_LINE, width=3)
    return image, draw


def box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str,
    fonts: dict[str, ImageFont.FreeTypeFont],
    *,
    fill: str = BLUE_SOFT,
    outline: str = BLUE_LINE,
) -> None:
    draw.rounded_rectangle(xy, radius=22, fill=fill, outline=outline, width=3)
    x1, y1, x2, _ = xy
    draw.text((x1 + 24, y1 + 20), title, fill=TEXT, font=fonts["body"])
    for i, line in enumerate(wrap_text(body, 17)):
        draw.text((x1 + 24, y1 + 62 + i * 28), line, fill=GRAY, font=fonts["small"])


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int]) -> None:
    draw.line((start, end), fill=BLUE, width=4)
    ex, ey = end
    sx, sy = start
    if ex >= sx:
        points = [(ex, ey), (ex - 16, ey - 10), (ex - 16, ey + 10)]
    else:
        points = [(ex, ey), (ex + 16, ey - 10), (ex + 16, ey + 10)]
    draw.polygon(points, fill=BLUE)


def wrap_text(text: str, width: int) -> Iterable[str]:
    lines: list[str] = []
    for raw_line in text.split("\n"):
        current = ""
        for char in raw_line:
            current += char
            if len(current) >= width:
                lines.append(current)
                current = ""
        if current:
            lines.append(current)
    return lines


def draw_architecture(fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image, draw = canvas("图 3 系统总体架构图", fonts)
    boxes = [
        ((80, 160, 330, 330), "输入层", "文本问诊\n预录音频", BLUE_SOFT, BLUE_LINE),
        ((410, 160, 660, 330), "感知层", "文本解析\nASRResult", GRAY_SOFT, GRAY_LINE),
        ((740, 160, 990, 330), "编排层", "Orchestrator\nPlan-and-Execute", BLUE_SOFT, BLUE_LINE),
        ((1070, 160, 1320, 330), "执行层", "字段抽取\n草稿生成\n安全校验", GREEN_SOFT, GREEN_LINE),
        ((740, 500, 990, 670), "医生审核", "Human-in-the-loop\n候选诊断确认\n导出前审核", YELLOW_SOFT, YELLOW_LINE),
        ((1070, 500, 1320, 670), "证据层", "Task Steps\naudit_log\nAgent Trace\nRun Log", GRAY_SOFT, GRAY_LINE),
    ]
    for xy, title, body, fill, outline in boxes:
        box(draw, xy, title, body, fonts, fill=fill, outline=outline)
    arrow(draw, (330, 245), (410, 245))
    arrow(draw, (660, 245), (740, 245))
    arrow(draw, (990, 245), (1070, 245))
    arrow(draw, (1195, 330), (865, 500))
    arrow(draw, (990, 585), (1070, 585))
    draw.text((80, 760), "说明：本项目是课程 POC，不接真实 HIS/EMR；AI 只生成草稿，最终由医生审核。", fill=MUTED, font=fonts["small"])
    return image


def draw_agent_flow(fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image, draw = canvas("图 4 Plan-and-Execute + Human-in-the-loop 执行流程图", fonts)
    steps = [
        ("输入/上传", "文本或音频"),
        ("感知", "ASR 转写\n或文本规范化"),
        ("计划", "选择任务路径\n拆分执行步骤"),
        ("执行", "字段抽取\n草稿生成\n安全校验"),
        ("医生审核", "确认字段\n补充缺失项"),
        ("导出决策", "export_allowed=false\n直到医生确认"),
    ]
    x = 70
    y = 240
    width = 210
    for i, (title, body) in enumerate(steps):
        fill = YELLOW_SOFT if title == "医生审核" else BLUE_SOFT
        outline = YELLOW_LINE if title == "医生审核" else BLUE_LINE
        box(draw, (x, y, x + width, y + 180), title, body, fonts, fill=fill, outline=outline)
        if i < len(steps) - 1:
            arrow(draw, (x + width, y + 90), (x + width + 55, y + 90))
        x += width + 65
    draw.text((120, 570), "每一步写入 task_step / audit_log；调试模式展示 Agent Trace；任务最终进入 WAITING_DOCTOR_REVIEW。", fill=GRAY, font=fonts["body"])
    return image


def draw_decision_prompt_flow(fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image, draw = canvas("图 5 决策系统与 Prompt 链流程图", fonts)
    top = [
        ((90, 170, 360, 330), "输入分流", "文本生成病历\n音频仅转写\n音频生成病历"),
        ((460, 170, 730, 330), "ASR 决策", "FunASR / Mock\nQwen3 / Online\nrole_strategy"),
        ((830, 170, 1100, 330), "LLM Provider", "mock / online / ollama\n失败时 fallback"),
        ((1200, 170, 1470, 330), "Schema 校验", "JSON 解析\nPydantic 校验\n字段完整性"),
    ]
    for xy, title, body in top:
        box(draw, xy, title, body, fonts)
    for start_x, end_x in [(360, 460), (730, 830), (1100, 1200)]:
        arrow(draw, (start_x, 250), (end_x, 250))

    prompt_boxes = [
        ((190, 520, 450, 690), "System Prompt", "医生审核边界\n防 Prompt 注入"),
        ((520, 520, 780, 690), "字段抽取", "MedicalField\nCandidateDiagnosis"),
        ((850, 520, 1110, 690), "草稿生成", "只根据已有字段\n不编造事实"),
        ((1180, 520, 1440, 690), "安全校验", "候选诊断\n导出门禁"),
    ]
    for xy, title, body in prompt_boxes:
        box(draw, xy, title, body, fonts, fill=GREEN_SOFT, outline=GREEN_LINE)
    for start_x, end_x in [(450, 520), (780, 850), (1110, 1180)]:
        arrow(draw, (start_x, 605), (end_x, 605))
    draw.text((120, 770), "说明：模型输出必须转成 JSON 并通过 Schema 校验；失败时降级，不影响 Orchestrator 主流程。", fill=MUTED, font=fonts["small"])
    return image


def draw_test_evidence_flow(fonts: dict[str, ImageFont.FreeTypeFont]) -> Image.Image:
    image, draw = canvas("图 10 测试验证与证据链路图", fonts)
    boxes = [
        ((90, 170, 390, 340), "演示输入", "文本导入\n音频上传\nfever_01_final_demo 日志"),
        ((480, 170, 780, 340), "运行过程", "ASRResult\nTask Steps\nSafetyCheck"),
        ((870, 170, 1170, 340), "可解释证据", "Agent Trace\nRun Log\ndebug JSON"),
        ((1260, 170, 1510, 340), "汇报材料", "截图清单\n评分看板\n正式报告"),
    ]
    for xy, title, body in boxes:
        box(draw, xy, title, body, fonts, fill=BLUE_SOFT, outline=BLUE_LINE)
    for start_x, end_x in [(390, 480), (780, 870), (1170, 1260)]:
        arrow(draw, (start_x, 255), (end_x, 255))

    box(draw, (180, 540, 680, 710), "已有证据", "文本链路、运行日志、Agent Trace、debug JSON、node --check、git diff --check", fonts, fill=GREEN_SOFT, outline=GREEN_LINE)
    box(draw, (900, 540, 1400, 710), "建议补充测试内容", "pytest 总通过数、多病种、ASR 对比、fallback、响应时间、Prompt 注入", fonts, fill=YELLOW_SOFT, outline=YELLOW_LINE)
    arrow(draw, (680, 625), (900, 625))
    return image


if __name__ == "__main__":
    raise SystemExit(main())
