"""Build a portable classroom runtime from the verified course materials and this checkout."""
import argparse
import hashlib
from html import escape
import json
import os
from pathlib import Path
import subprocess
import tempfile


HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def build(frozen, destination):
    if destination.exists():
        raise FileExistsError(f"构建目录必须为新目录：{destination}")
    manifest = json.loads((frozen / "frozen-sha256.json").read_text(encoding="utf-8"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        work = Path(temporary) / "build"
        work.mkdir()
        for name, checksum in manifest.items():
            src = (frozen / name).resolve()
            if not src.is_relative_to(frozen.resolve()):
                raise ValueError(f"无效清单路径：{name}")
            data = src.read_bytes()
            if digest(data) != checksum:
                raise ValueError(f"原始资产校验失败：{name}")
            if name.startswith("source/"):
                target = work / name.removeprefix("source/")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)

        for name in ("static/doctor.js", "static/doctor.html", "app/api/tasks.py"):
            # A checkout may use platform-native line endings. The built files use UTF-8/LF.
            (work / name).write_bytes((REPO / name).read_text(encoding="utf-8").encode())
        subprocess.run(["git", "apply", "--whitespace=nowarn", str(HERE / "classroom-ui.patch")],
                       cwd=work, env={**os.environ, "GIT_CEILING_DIRECTORIES": str(work.parent.resolve())},
                       check=True)
        html_path = work / "static/doctor.html"
        html = html_path.read_text(encoding="utf-8")
        marker = "{{COURSE_VERIFIED_TEXT}}"
        if html.count(marker) != 1:
            raise ValueError("课堂模板的原文入口数量异常")
        sample = json.loads((frozen / "fixtures/input.json").read_text(encoding="utf-8"))
        if digest(sample["text"].encode()) != sample["sha256"]:
            raise ValueError("课堂问诊原文校验失败")
        html_path.write_bytes(html.replace(marker, escape(sample["text"])).encode())
        deployment_path = work / "static/deployment.json"
        deployment = json.loads(deployment_path.read_text(encoding="utf-8"))
        deployment["label"] = "课堂审核版 v2"
        deployment_path.write_bytes(json.dumps(deployment, ensure_ascii=False).encode())
        for name, asset in (("投影.css", "projector.css"), ("course-entry.css", "course-entry.css")):
            (work / "static" / asset).write_bytes((HERE / name).read_text(encoding="utf-8").encode())
        files = {p.relative_to(work).as_posix(): digest(p.read_bytes())
                 for p in sorted(work.rglob("*")) if p.is_file()}
        (work / "runtime-sha256.json").write_bytes(json.dumps(files, sort_keys=True, indent=2).encode())
        work.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="从冻结的课堂材料构建可离线运行的新版工作台")
    parser.add_argument("frozen", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    build(args.frozen, args.destination)
