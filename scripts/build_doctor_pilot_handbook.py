"""Package the doctor HTML guide and a PDF from reviewed, local screenshots.

Development-only authoring tool. No access to application databases or accounts.
The screenshot manifest must describe synthetic content captured from the stated
application version; this builder does not certify clinical or release readiness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from xml.sax.saxutils import escape


def build(source: Path, manifest_path: Path, output: Path, font: Path) -> Path:
    from bs4 import BeautifulSoup
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, PageBreak

    manifest = json.loads(manifest_path.read_text(encoding="utf8"))
    if not re.fullmatch(r"[0-9a-f]{40}", manifest.get("app_git_sha", "")):
        raise ValueError("A full application Git SHA is required")
    if manifest.get("synthetic_only") is not True:
        raise ValueError("Only reviewed synthetic screenshots may be packaged")
    output.mkdir(parents=True, exist_ok=True)
    for name in ("manual.html", "guide.css", "manual.css", "feedback.html", "feedback.js", "maintenance.html"):
        shutil.copyfile(source / name, output / name)
    shots = []
    for item in manifest["screenshots"]:
        key = item["key"]
        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,39}", key):
            raise ValueError("Unexpected screenshot section")
        picture = (manifest_path.parent / item["path"]).resolve()
        if not picture.is_relative_to(manifest_path.parent.resolve()) or picture.suffix != ".png":
            raise ValueError("Screenshot must be a PNG within the evidence directory")
        sha = hashlib.sha256(picture.read_bytes()).hexdigest()
        if sha != item["sha256"]:
            raise ValueError("Screenshot changed after review")
        (output / "images").mkdir(exist_ok=True)
        target = output / "images" / (key + ".png")
        shutil.copyfile(picture, target)
        shots.append({"key": key, "path": target.relative_to(output).as_posix(),
                      "caption": item["caption"], "sha256": sha})
    version = f"内部候选操作手册 · 应用 {manifest['app_git_sha'][:12]} · {manifest['captured_at']} · 尚未放行独立试用"
    evidence = {"version": version, "app_git_sha": manifest["app_git_sha"], "screenshots": shots}
    (output / "manual-evidence.js").write_text("window.MRA_MANUAL_EVIDENCE=" + json.dumps(evidence, ensure_ascii=False) + ";\n", encoding="utf8")
    pdfmetrics.registerFont(TTFont("MRA-CJK", str(font), subfontIndex=0))
    text = ParagraphStyle("text", fontName="MRA-CJK", fontSize=10.5, leading=17,
                          spaceAfter=9, textColor=colors.HexColor("#172d43"), wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=text, fontSize=18, leading=26, spaceAfter=14)
    small = ParagraphStyle("small", parent=text, fontSize=8.5, leading=13, textColor=colors.HexColor("#53697c"))
    width = A4[0] - 88
    story = []
    soup = BeautifulSoup((source / "manual.html").read_text(encoding="utf8"), "html.parser")
    sections = soup.select("main > section")
    images = {s["key"]: s for s in shots}
    required = {e["data-shot"] for e in soup.select("[data-shot]")}
    if not required.issubset(images):
        raise ValueError("Missing current-version screenshots: " + str(sorted(required - images.keys())))

    class GuideDoc(SimpleDocTemplate):
        def afterFlowable(self, flowable):
            if hasattr(flowable, "bookmark"):
                self.canv.bookmarkPage(flowable.bookmark)
                self.canv.addOutlineEntry(flowable.getPlainText(), flowable.bookmark, 0, False)

    def paragraph(value, style=text, bookmark=None):
        item = Paragraph(escape(value), style)
        if bookmark:
            item.bookmark = bookmark
        story.append(item)

    paragraph("MediListen / 医生试用", small)
    story.append(Spacer(1, 85))
    paragraph("医生工作台操作手册", ParagraphStyle("cover", parent=heading, fontSize=28, leading=40))
    paragraph("工作台接诊 · 病历核对 · 审核导出", heading)
    paragraph(version, small)
    story.append(Spacer(1, 40))
    paragraph(soup.select_one("main > aside").get_text(" ", strip=True))
    paragraph(soup.select_one(".revision-note").get_text(" ", strip=True))
    paragraph("每项任务按使用条件、编号步骤、实际界面、成功结果与失败恢复组织。维护说明与医生正文分开。")
    paragraph("界面截图为当前候选与合成病例。未通过最终三路径、模型质量及恢复验收前，不将本手册视为临床或稳定发布证明。", small)
    story.append(PageBreak())
    paragraph("操作目录", heading, "contents")
    for n, section in enumerate(sections):
        label = section.h2.get_text(" ", strip=True)
        # Stable chapter links; page numbers remain in the PDF footer.
        story.append(Paragraph(f'<link href="#chapter-{n}" color="#07598a">{escape(label)}</link>', text))
    paragraph("界面区域：工作台负责登记／报到；工作区负责撰写和审核。左栏转写、中栏病历、右栏参考；五步进度无需逐步点击。", small)
    for n, section in enumerate(sections):
        story.append(PageBreak())
        paragraph(section.h2.get_text(" ", strip=True), heading, f"chapter-{n}")
        for element in section.find_all(["p", "ol", "div"], recursive=False):
            if element.name == "p":
                paragraph(element.get_text(" ", strip=True), small if "precondition" in element.get("class", []) else text)
            elif element.name == "ol":
                for number, li in enumerate(element.find_all("li", recursive=False), 1):
                    paragraph(f"{number}. {li.get_text(' ', strip=True)}")
            elif element.get("data-shot") in images:
                shot = images[element["data-shot"]]
                im = Image(str(output / shot["path"]))
                scale = min(width / im.imageWidth, 350 / im.imageHeight)
                im.drawWidth, im.drawHeight = im.imageWidth * scale, im.imageHeight * scale
                im.hAlign = "LEFT"
                story.extend([Spacer(1, 5), im, Spacer(1, 5)])
                paragraph(shot["caption"], small)
    pdf = output / "doctor-manual.pdf"
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("MRA-CJK", 8)
        canvas.setFillColor(colors.HexColor("#53697c"))
        canvas.drawString(44, 26, "MediListen v1.1 · 合成病例 / 候选操作手册")
        canvas.drawRightString(A4[0]-44, 26, str(doc.page))
        canvas.restoreState()
    GuideDoc(str(pdf), pagesize=A4, leftMargin=44, rightMargin=44,
             topMargin=40, bottomMargin=46, title="MediListen 医生操作手册 v1.1").build(
                 story, onFirstPage=footer, onLaterPages=footer)
    package = dict(manifest, screenshots=shots, release_status="CANDIDATE_NOT_RELEASED")
    package["files"] = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                        for p in output.rglob("*") if p.is_file() and p.name != "manifest.json"}
    (output / "manifest.json").write_text(json.dumps(package, ensure_ascii=False, indent=2), encoding="utf8")
    return pdf


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--font", type=Path, default=Path("C:/Windows/Fonts/msyh.ttc"))
    args = parser.parse_args()
    print(build(Path(__file__).resolve().parents[1] / "docs/pilot/doctor-v1", args.manifest, args.output, args.font))
