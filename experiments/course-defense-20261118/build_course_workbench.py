"""Build the classroom variant without changing the reference prototype checkout."""
import argparse
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from PIL import Image


def main():
    parser = argparse.ArgumentParser(description="在独立目录构建课程版接诊演练")
    parser.add_argument("output", type=Path, help="新 HTML 文件的路径")
    target = parser.parse_args().output
    here = Path(__file__).resolve().parent
    repo = here.parents[1]
    relative = Path("experiments/frontend-reference-workbench-20261106")
    with tempfile.TemporaryDirectory(prefix="medilisten-course-build-") as scratch:
        work = Path(scratch)
        source = work / relative
        source.mkdir(parents=True)
        for name in ("app.mjs", "model.mjs", "style.css", "capture.mjs", "index.html", "build-standalone.py"):
            shutil.copy2(repo / relative / name, source / name)
        subprocess.run(["git", "apply", str(here / "reference-workbench.patch")], cwd=work, check=True)
        assets = source / "assets"
        assets.mkdir()
        with Image.open(repo / relative / "assets/medilisten.png") as original:
            original.resize((64, 64), Image.Resampling.LANCZOS).save(assets / "medilisten.png", optimize=True)
        subprocess.run([sys.executable, "-B", "-X", "utf8", str(source / "build-standalone.py")], check=True)
        # Keep the delivered Windows HTML line endings reproducible on other build hosts.
        data = (source / "直接打开工作台.html").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        with target.open("xb") as output:
            output.write(data)
        print(target, hashlib.sha256(data).hexdigest())


if __name__ == "__main__":
    main()
