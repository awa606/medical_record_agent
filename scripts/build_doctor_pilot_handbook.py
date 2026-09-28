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
    for name in ("manual.html", "guide.css", "feedback.html", "feedback.js", "maintenance.html"):
        shutil.copyfile(source / name, output / name)
    shots = []
    for item in manifest["screenshots"]:
        key = item["key"]
        if key not in {"login", "worklist", "workspace", "knowledge", "review"}:
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
    text = ParagraphStyle("text", fontName="MRA-CJK", fontSize=11, leading=19,
                          spaceAfter=12, textColor=colors.HexColor("#172d43"), wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=text, fontSize=18, leading=25, spaceAfter=20)
    small = ParagraphStyle("small", parent=text, fontSize=9, leading=14, textColor=colors.HexColor("#53697c"))
    width = A4[0] - 100
    story = []
    soup = BeautifulSoup((source / "manual.html").read_text(encoding="utf8"), "html.parser")
    def paragraph(value, style=text):
        story.append(Paragraph(escape(value), style))
    paragraph("MediListen 医生试用", small)
    paragraph("一页快速开始", heading)
    paragraph(version, small)
    paragraph(soup.select_one("main > aside").get_text(" ", strip=True))
    for number, li in enumerate(soup.select(".quick li"), 1):
        paragraph(f"{number}. {li.get_text(' ', strip=True)}")
    images = {s["key"]: s for s in shots}
    for section in soup.select("main > section:not(.quick)"):
        # Keep short, related instructions together instead of seven mostly
        # empty pages. Captures are bounded viewport crops, never full scrolls.
        if section.h2.get_text().startswith(("4.", "7.")):
            story.append(Spacer(1, 22))
        else:
            story.append(PageBreak())
        paragraph(section.h2.get_text(" ", strip=True), heading)
        for element in section.find_all(["p", "table", "div"], recursive=False):
            if element.name == "p":
                paragraph(element.get_text(" ", strip=True))
            elif element.name == "table":
                for row in element.find_all("tr")[1:]:
                    paragraph("：".join(c.get_text(" ", strip=True) for c in row.find_all("td")))
            elif element.get("data-shot") in images:
                image = images[element["data-shot"]]
                im = Image(str(output / image["path"]))
                scale = min(width / im.imageWidth, 355 / im.imageHeight)
                im.drawWidth = im.imageWidth * scale
                im.drawHeight = im.imageHeight * scale
                im.hAlign = "LEFT"
                story.extend([Spacer(1, 10), im, Spacer(1, 8)])
                paragraph(image["caption"], small)
    pdf = output / "doctor-manual.pdf"
    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("MRA-CJK", 8)
        canvas.setFillColor(colors.HexColor("#53697c"))
        canvas.drawString(50, 28, "合成病例 / 模拟问诊 · 不能作为临床使用放行证明")
        canvas.drawRightString(A4[0]-50, 28, str(doc.page))
        canvas.restoreState()
    SimpleDocTemplate(str(pdf), pagesize=A4, leftMargin=50, rightMargin=50,
                      topMargin=44, bottomMargin=48, title="MediListen 医生操作手册").build(
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
