"""Build the public help bundle from an explicit document allowlist."""
from pathlib import Path
import argparse
import json
import shutil

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ("manual.html", "manual.css", "manual-evidence.js", "guide.css",
             "feedback.html", "feedback.js", "help-nav.js", "maintenance.html",
             "dual-environment.html", "course-demo.html", "viewer-section.html",
             "images/usage-workbench-20260929.png",
             "images/showcase-source-review-20260929.png")


def build(output: Path, *, source: Path | None = None, pdf: Path | None = None):
    source = source or ROOT / "docs/pilot/doctor-v1"
    output.mkdir(parents=True, exist_ok=True)
    for name in ALLOWLIST:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if name.endswith(".png"):
            shutil.copyfile(source / name, target)
            continue
        text = (source / name).read_text(encoding="utf8")
        text = text.replace("../../../static/brand/medilisten-v1.png", "../brand/medilisten-v1.png")
        target.write_text(text, encoding="utf8")
    if pdf:
        shutil.copyfile(pdf, output / "doctor-manual.pdf")
    elif not (output / "doctor-manual.pdf").is_file():
        manual = output / "manual.html"
        manual.write_text(manual.read_text(encoding="utf8").replace(
            '<a href="doctor-manual.pdf">PDF手册</a>',
            '<span>PDF手册尚未随本环境打包，请使用本页手册。</span>'), encoding="utf8")
    return list(ALLOWLIST)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", type=Path, default=ROOT / "static/help")
    p.add_argument("--pdf", type=Path)
    args = p.parse_args()
    print(json.dumps(build(args.output, pdf=args.pdf)))
