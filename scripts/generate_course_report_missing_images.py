from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "docs" / "course_report_images"

TEXT = "#111827"
MUTED = "#4b5563"
BLUE = "#2563eb"
BLUE_SOFT = "#eff6ff"
BLUE_LINE = "#93c5fd"
GREEN_SOFT = "#ecfdf5"
GREEN_LINE = "#86efac"
YELLOW_SOFT = "#fffbeb"
YELLOW_LINE = "#fcd34d"
RED_SOFT = "#fef2f2"
RED_LINE = "#fca5a5"
GRAY_SOFT = "#f9fafb"
GRAY_LINE = "#d1d5db"


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    fonts = load_fonts()

    outputs = [
        (
            OUTPUT_DIR / "fig03_agent_plan_execute_hitl.png",
            draw_agent_plan_execute_hitl(fonts),
        ),
        (
            OUTPUT_DIR / "fig04_safety_guardrails_export_gate.png",
            draw_safety_guardrails_export_gate(fonts),
        ),
    ]
    for path, image in outputs:
        image.save(path, dpi=(160, 160))
        print(path)
    return 0


def load_fonts() -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    candidates = [
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
    ]
    font_path = next((path for path in candidates if path.exists()), None)
    if font_path is None:
        return {
            "title": ImageFont.load_default(),
            "subtitle": ImageFont.load_default(),
            "box_title": ImageFont.load_default(),
            "body": ImageFont.load_default(),
            "small": ImageFont.load_default(),
            "badge": ImageFont.load_default(),
        }
    return {
        "title": ImageFont.truetype(str(font_path), 42),
        "subtitle": ImageFont.truetype(str(font_path), 23),
        "box_title": ImageFont.truetype(str(font_path), 28),
        "body": ImageFont.truetype(str(font_path), 22),
        "small": ImageFont.truetype(str(font_path), 19),
        "badge": ImageFont.truetype(str(font_path), 17),
    }


def new_canvas(title: str, subtitle: str, fonts: dict[str, ImageFont.ImageFont]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", (1800, 1050), "white")
    draw = ImageDraw.Draw(image)
    draw.text((70, 44), title, fill=TEXT, font=fonts["title"])
    draw.text((72, 103), subtitle, fill=MUTED, font=fonts["subtitle"])
    draw.line((70, 145, 1730, 145), fill=BLUE_LINE, width=3)
    return image, draw


def draw_agent_plan_execute_hitl(fonts: dict[str, ImageFont.ImageFont]) -> Image.Image:
    image, draw = new_canvas(
        "图 3 Plan-and-Execute + Human-in-the-loop 执行流程图",
        "文本或音频先统一为 conversation_text，再由 Orchestrator 按步骤执行，并在医生审核前阻止最终导出。",
        fonts,
    )

    nodes = [
        ("输入/上传", "文本问诊\n预录音频\nASR 测试\n可单独返回", BLUE_SOFT, BLUE_LINE),
        ("感知归一", "文本规范化\nASRResult\nconversation_text", BLUE_SOFT, BLUE_LINE),
        ("Plan 计划", "判断输入类型\n选择任务路径\n拆分执行步骤", BLUE_SOFT, BLUE_LINE),
        ("Execute 执行", "字段抽取\n草稿生成\n安全校验", GREEN_SOFT, GREEN_LINE),
        ("过程记录", "task_step\naudit_log\nAgent Trace\nRun Log", GRAY_SOFT, GRAY_LINE),
        ("医生审核", "补充缺失项\n确认候选诊断\n审核病历草稿", YELLOW_SOFT, YELLOW_LINE),
        ("导出门禁", "默认禁止导出\nexport_allowed\n= false\n医生确认后再导出", RED_SOFT, RED_LINE),
    ]
    x, y, w, h, gap = 58, 235, 220, 224, 25
    centers: list[tuple[int, int]] = []
    for index, (title, body, fill, outline) in enumerate(nodes):
        left = x + index * (w + gap)
        right = left + w
        rounded_box(
            draw,
            (left, y, right, y + h),
            title,
            body,
            fonts,
            fill=fill,
            outline=outline,
            body_width=w - 40,
        )
        centers.append(((left + right) // 2, y + h // 2))
        if index > 0:
            prev_right = left - gap
            arrow(draw, (prev_right + 8, y + h // 2), (left - 10, y + h // 2), BLUE)

    loop_y = 525
    arrow(draw, (centers[5][0], y + h + 22), (centers[5][0], loop_y), YELLOW_LINE, width=5)
    draw.line((centers[5][0], loop_y, centers[3][0], loop_y), fill=YELLOW_LINE, width=5)
    arrow(draw, (centers[3][0], loop_y), (centers[3][0], y + h + 18), YELLOW_LINE, width=5)
    draw.text(
        (centers[3][0] - 190, loop_y + 24),
        "缺失项、角色待校正或安全风险存在时，返回补充信息和人工复核。",
        fill=MUTED,
        font=fonts["small"],
    )

    draw_section_label(draw, (78, 590), "任务状态流转", fonts)
    statuses = [
        "CREATED",
        "EXTRACTING_FIELDS",
        "GENERATING_DRAFT",
        "SAFETY_CHECKING",
        "WAITING_DOCTOR_REVIEW",
    ]
    sx, sy, sw, sh, sgap = 108, 648, 290, 66, 27
    for index, status in enumerate(statuses):
        left = sx + index * (sw + sgap)
        badge(draw, (left, sy, left + sw, sy + sh), status, fonts, fill="white", outline=BLUE_LINE)
        if index > 0:
            prev_right = left - sgap
            arrow(draw, (prev_right + 7, sy + sh // 2), (left - 9, sy + sh // 2), BLUE)

    draw.text(
        (90, 930),
        "插入位置建议：2.2 核心流程（Agent 循环 / 图）。",
        fill=TEXT,
        font=fonts["body"],
    )
    return image


def draw_safety_guardrails_export_gate(fonts: dict[str, ImageFont.ImageFont]) -> Image.Image:
    image, draw = new_canvas(
        "图 4 安全护栏与导出门禁图",
        "AI 输出只作为病历草稿、候选诊断和安全提醒；最终确认与导出必须经过医生审核。",
        fonts,
    )

    flow = [
        ("AI 草稿", "由字段抽取结果生成\n不补写未提及事实", BLUE_SOFT, BLUE_LINE),
        ("安全校验", "SafetyCheckResult\n检查缺失与风险", GREEN_SOFT, GREEN_LINE),
        ("风险拦截", "Prompt 注入\n候选诊断误用\n敏感信息泄露", RED_SOFT, RED_LINE),
        ("医生审核", "确认字段\n补充缺失项\n确认候选诊断", YELLOW_SOFT, YELLOW_LINE),
        ("导出门禁", "export_allowed\n= false\n未审核禁止导出", RED_SOFT, RED_LINE),
        ("最终导出", "医生确认后\n形成最终病历材料", GREEN_SOFT, GREEN_LINE),
    ]
    x, y, w, h, gap = 76, 220, 230, 182, 42
    for index, (title, body, fill, outline) in enumerate(flow):
        left = x + index * (w + gap)
        rounded_box(
            draw,
            (left, y, left + w, y + h),
            title,
            body,
            fonts,
            fill=fill,
            outline=outline,
            body_width=w - 36,
        )
        if index > 0:
            prev_right = left - gap
            arrow(draw, (prev_right + 7, y + h // 2), (left - 10, y + h // 2), BLUE)

    draw_section_label(draw, (78, 492), "护栏层次", fonts)
    layers = [
        ("数据边界", "只用课程样例\n不接真实 HIS/EMR\nAPI Key 不进截图和日志", BLUE_SOFT, BLUE_LINE),
        ("Prompt 约束", "System Prompt 固定边界\n防 Prompt 注入\nAI 只能辅助医生", GRAY_SOFT, GRAY_LINE),
        ("Schema 校验", "JSON 解析\nPydantic 校验\n无效输出触发 fallback", GREEN_SOFT, GREEN_LINE),
        ("字段规则", "未提及 = missing\n候选诊断需确认\n不自动写“正常”", YELLOW_SOFT, YELLOW_LINE),
        ("审计追踪", "task_step\naudit_log\nRun Log\nAgent Trace", GRAY_SOFT, GRAY_LINE),
    ]
    lx, ly, lw, lh, lgap = 76, 560, 318, 242, 25
    for index, (title, body, fill, outline) in enumerate(layers):
        left = lx + index * (lw + lgap)
        rounded_box(
            draw,
            (left, ly, left + lw, ly + lh),
            title,
            body,
            fonts,
            fill=fill,
            outline=outline,
            body_width=lw - 46,
        )

    draw.text(
        (90, 905),
        "关键说明：医生审核前系统保持 export_allowed=false，WAITING_DOCTOR_REVIEW 是正常终态，不代表流程失败。",
        fill=TEXT,
        font=fonts["body"],
    )
    draw.text(
        (90, 948),
        "插入位置建议：3.4 安全与护栏机制。",
        fill=MUTED,
        font=fonts["small"],
    )
    return image


def rounded_box(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    title: str,
    body: str,
    fonts: dict[str, ImageFont.ImageFont],
    *,
    fill: str,
    outline: str,
    body_width: int,
) -> None:
    x1, y1, x2, _ = xy
    draw.rounded_rectangle(xy, radius=24, fill=fill, outline=outline, width=3)
    draw.text((x1 + 20, y1 + 22), title, fill=TEXT, font=fonts["box_title"])
    draw_wrapped_text(
        draw,
        (x1 + 20, y1 + 74),
        body,
        fonts["small"],
        MUTED,
        body_width,
        line_gap=8,
    )


def draw_section_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str, fonts: dict[str, ImageFont.ImageFont]) -> None:
    x, y = xy
    draw.rounded_rectangle((x, y, x + 150, y + 38), radius=19, fill=BLUE, outline=BLUE, width=1)
    draw.text((x + 20, y + 7), text, fill="white", font=fonts["small"])


def badge(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    text: str,
    fonts: dict[str, ImageFont.ImageFont],
    *,
    fill: str,
    outline: str,
) -> None:
    draw.rounded_rectangle(xy, radius=18, fill=fill, outline=outline, width=2)
    bbox = draw.textbbox((0, 0), text, font=fonts["badge"])
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    x1, y1, x2, y2 = xy
    draw.text(((x1 + x2 - tw) // 2, (y1 + y2 - th) // 2 - 2), text, fill=TEXT, font=fonts["badge"])


def draw_wrapped_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    *,
    line_gap: int = 6,
) -> int:
    x, y = xy
    line_height = draw.textbbox((0, 0), "国", font=font)[3] + line_gap
    for line in wrap_text(draw, text, font, max_width):
        draw.text((x, y), line, fill=fill, font=font)
        y += line_height
    return y


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        current = ""
        for char in raw_line:
            trial = current + char
            if draw.textlength(trial, font=font) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = char
        if current:
            lines.append(current)
    return lines


def arrow(
    draw: ImageDraw.ImageDraw,
    start: tuple[int, int],
    end: tuple[int, int],
    color: str,
    *,
    width: int = 5,
) -> None:
    draw.line((start, end), fill=color, width=width)
    sx, sy = start
    ex, ey = end
    angle = math.atan2(ey - sy, ex - sx)
    size = 16
    points = [
        (ex, ey),
        (ex - size * math.cos(angle - math.pi / 6), ey - size * math.sin(angle - math.pi / 6)),
        (ex - size * math.cos(angle + math.pi / 6), ey - size * math.sin(angle + math.pi / 6)),
    ]
    draw.polygon(points, fill=color)


if __name__ == "__main__":
    raise SystemExit(main())
