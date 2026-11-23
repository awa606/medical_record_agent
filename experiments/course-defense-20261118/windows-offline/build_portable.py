"""Rebuild the verified 2026-11-24 classroom ZIP from its two delivery folders."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile, ZipInfo

TEMPLATES = Path(__file__).resolve().parent / "portable"
LAYERS = {
    "运行源": ("runtime-sha256.json", "5cc24fe0ff55c645447afbffe9adf3dbdf218f14b01482885e0fc7adce5128ee"),
    "冻结资产": ("frozen-sha256.json", "f8b550226bdbfb33b4c4ba0e097cabb99ee349e7ec9cfd0f861e1bc61e3b5b70"),
}
PYTHON_ARCHIVE = "python-3.14.10-amd64.zip"
PYTHON_SHA = "cc28026a650970cc1570bb127312f1f9634eb67abfe157ae6ca1acbbc627d091"
WHEELS_INDEX = "Windows314轮包核验.json"
INDEX_SHA = "7b888ce0e432e39acc1a7dc4cc935f4073075e066f80b7f8ecbeb96bfb52116e"
INVENTORY_SHA = "56541e6f8693a38429cda6214e66eb8f83550d24d1f3c356a6a96eef0ab9d076"
ZIP_SHA = "cf726261e443369d43157573df31a4aa2194e40d83c21de2bee49942096e2ef5"


def digest(content):
    return hashlib.sha256(content).hexdigest()


def verified(content, expected, name):
    if digest(content) != expected:
        raise ValueError(f"文件摘要与封定版本不同：{name}")
    return content


def read_inside(folder, relative):
    path = (folder / relative).resolve(strict=True)
    if not path.is_relative_to(folder):
        raise ValueError(f"输入路径越过交付目录：{relative}")
    return path.read_bytes()


def text_bytes(content, *, windows=False):
    lf = content.replace(b"\r\n", b"\n")
    return lf.replace(b"\n", b"\r\n") if windows else lf


def collect(software):
    entries = {}
    for layer, (name, expected) in LAYERS.items():
        prefix = f"现场回放/{layer}/"
        raw = verified(read_inside(software, prefix + name), expected, name)
        entries[prefix + name] = (raw, layer + "校验清单")
        for relative, expected_file in json.loads(raw).items():
            key = prefix + relative
            entries[key] = (verified(read_inside(software, key), expected_file, key), layer)

    for name in ("课堂启动.py", "course_service.py"):
        key = "现场回放/" + name
        entries[key] = (read_inside(software, key), "课堂程序")

    for name in ("windows_bootstrap.ps1", "windows_runtime.py", "双击启动专用课堂.cmd", WHEELS_INDEX,
                 "requirements-win314.lock"):
        key = "专用环境/" + name
        entries[key] = (text_bytes(read_inside(software, key), windows=not name.endswith(".py")), "3.14 准备与启动")

    host = verified(read_inside(software, "专用环境/" + PYTHON_ARCHIVE), PYTHON_SHA, PYTHON_ARCHIVE)
    entries["专用环境/" + PYTHON_ARCHIVE] = (host, "Python 官方完整 ZIP")
    with ZipFile(io.BytesIO(host)) as src:
        entries["许可/CPython-LICENSE.txt"] = (src.read("LICENSE.txt"), "官方 ZIP 内完整许可的阅读副本")

    index = verified(entries["专用环境/" + WHEELS_INDEX][0], INDEX_SHA, WHEELS_INDEX)
    for wheel in json.loads(index)["rows"]:
        key = "专用环境/wheels-win314-x64/" + wheel["filename"]
        entries[key] = (verified(read_inside(software, key), wheel["sha256"], key), "PyPI 官方完整 wheel")

    for name, kind in (("许可/第三方成分.html", "随包说明"), ("使用说明.html", "随包说明"), ("双击启动课堂.cmd", "便携入口")):
        entries[name] = (text_bytes(read_inside(TEMPLATES, name), windows=name.endswith(".cmd")), kind)

    # The released inventory pins every name, size, content digest and category,
    # including launchers and guides that are separate from the core manifests.
    inventory = {
        "format": 1, "scope": "Windows x64 教学合成病例", "self": "分发清单.json",
        "files": [{"path": name, "kind": kind, "size": len(blob), "sha256": digest(blob)}
                  for name, (blob, kind) in sorted(entries.items())],
    }
    raw_inventory = (json.dumps(inventory, ensure_ascii=False, indent=2) + "\n").encode("utf8")
    entries["分发清单.json"] = (verified(raw_inventory, INVENTORY_SHA, "分发清单"), "自身清单")
    return entries


def build(software, destination):
    entries = collect(software.resolve(strict=True))
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as temp:
        staging = Path(temp.name)
    try:
        with ZipFile(staging, "w") as archive:
            for name, (blob, _) in sorted(entries.items()):
                member = ZipInfo(name, date_time=(2026, 11, 24, 0, 0, 0))
                member.create_system = 0  # Match the Windows release on other build hosts.
                member.external_attr = 0o100644 << 16
                method = ZIP_STORED if name.endswith((".whl", ".zip", ".png", ".ico")) else ZIP_DEFLATED
                archive.writestr(member, blob, compress_type=method, compresslevel=6 if method == ZIP_DEFLATED else None)
        with staging.open("rb") as stream:
            if hashlib.file_digest(stream, "sha256").hexdigest() != ZIP_SHA:
                raise ValueError("生成的 ZIP 与已验证的分发文件摘要不同")
        # Both publication paths fail if a different build has already published.
        if os.name == "nt":
            staging.rename(destination)
        else:
            os.link(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    return ZIP_SHA


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("software", type=Path, help="含专用环境和现场回放两个目录的软件目录")
    parser.add_argument("destination", type=Path, help="新的输出 ZIP 文件路径")
    args = parser.parse_args()
    print(build(args.software, args.destination), args.destination)
