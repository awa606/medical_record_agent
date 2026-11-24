"""Build the offline Windows synthetic field-review trial from the frozen r3 distribution."""

import argparse
import ast
from hashlib import sha256
import json
from pathlib import Path
import re
import subprocess
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

RECIPE = Path(__file__).resolve().parent
REPO = RECIPE.parents[2]
BASE_SHA256 = "6371cb8ee6a62609e9fc19656ad106e566302a3a45f74ba271a731f636a5da87"
BASE_COMMIT = "d231e1c5f0c120fa15b3cc228cbfec12c345ecfd"
REFERENCE = "data/knowledge/review/outpatient-information-page/six-clauses.json"
REFERENCE_SHA256 = "5d470b317685af7b30653ce65285d0392c3d6cf8b76f1e48b1dc46c73c30737d"
REFERENCE_FILE = "六条文书释义.json"
ROOT = "MediListen_同就诊来源修订试用/"
DEEP = ROOT + "医院/录音复核/医生操作/本机演练/"
FIXED = DEEP + "固定素材/"

def digest(data: bytes) -> str:
    return sha256(data).hexdigest()

def json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode()

def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError(f"基础包的预期内容不匹配：{old[:90]}")
    return text.replace(old, new)

def git_bytes(*args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=REPO)

def approved_help_inputs(commit: str) -> list[str]:
    script = "scripts/package_help.py"
    source = git_bytes("show", f"{commit}:{script}")
    assignments = (stmt for stmt in ast.parse(source).body if isinstance(stmt, ast.Assign))
    declaration = next(stmt for stmt in assignments
                       if any(isinstance(target, ast.Name) and target.id == "ALLOWLIST" for target in stmt.targets))
    names = ast.literal_eval(declaration.value)
    if not names or not all(isinstance(name, str) and ".." not in Path(name).parts and not Path(name).is_absolute() for name in names):
        raise ValueError("帮助白名单路径无效")
    return [script, *("docs/pilot/doctor-v1/" + name for name in names)]


def update_launcher(data: bytes, commit: str, with_help: bool) -> bytes:
    text = data.decode("utf8")
    if text.count(BASE_COMMIT[:12]) != 3:
        raise ValueError("基础包的目录、进程和会话版本与 r3 不一致")
    text = text.replace(BASE_COMMIT[:12], commit[:12])
    location = "def prepare(session, base, account):"
    reference_code = (RECIPE / "prepare_reference.py").read_text(encoding="utf-8-sig").strip()
    text = replace_once(text, location, reference_code + "\n\n\ndef prepare(session, base, account, root):")
    text = replace_once(text, '    users=api("GET","/api/auth/users")', '    prepare_reference(root, api)\n    users=api("GET","/api/auth/users")')
    text = replace_once(text, "ids=prepare(session,base,account)", "ids=prepare(session,base,account,root)")
    if with_help:
        before_app = "        from app.main import app"
        assemble = "        from scripts.package_help import build as build_public_help\n        build_public_help(source / 'static/help')\n"
        text = replace_once(text, before_app, assemble + before_app)
    compile(text, "体验.py", "exec")
    return text.encode()

def build(base: Path, output: Path, commit: str, *, with_help: bool = False) -> Path:
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("请使用完整的应用提交 SHA")
    if digest(base.read_bytes()) != BASE_SHA256:
        raise ValueError("基础 ZIP 与已验收的 r3 不符")
    changed = set(git_bytes("diff", "--name-only", BASE_COMMIT, commit, "--", "app", "assets", "config", "static").decode().splitlines())
    expected = {"static/doctor.js", "static/doctor.html", "static/doctor-workspace.css"}
    if with_help:
        expected.update({"static/doctor.css", "static/help/index.html"})
    if changed != expected:
        raise ValueError(f"本配方只适用于已验收的字段界面差异：{sorted(changed)}")
    reference = git_bytes("show", f"{commit}:{REFERENCE}")
    if digest(reference) != REFERENCE_SHA256:
        raise ValueError("随包文书条文与冻结的项目释义不符")
    with ZipFile(base) as bundle:
        originals = {name: bundle.read(name) for name in bundle.namelist()}
    files = dict(originals)
    manifest = json.loads(files[FIXED + "版本与输入.json"])
    if manifest["commit"] != BASE_COMMIT or manifest["sha256"] != digest(files[FIXED + "修订工作台.zip"]):
        raise ValueError("基础应用源码指纹不匹配")
    for name, expected in manifest["files"].items():
        if digest(files[FIXED + name]) != expected:
            raise ValueError(f"冻结素材指纹不匹配：{name}")
    help_inputs = approved_help_inputs(commit) if with_help else []
    source_zip = git_bytes("archive", "--format=zip", commit, "app", "assets", "config", "static", *help_inputs)
    manifest.update(commit=commit, sha256=digest(source_zip))
    manifest["files"][REFERENCE_FILE] = digest(reference)
    files[FIXED + REFERENCE_FILE] = reference
    files[FIXED + "版本与输入.json"] = json_bytes(manifest)
    files[FIXED + "修订工作台.zip"] = source_zip
    files[DEEP + "体验.py"] = update_launcher(files[DEEP + "体验.py"], commit, with_help)
    guide_name = ROOT + "先打开_同就诊来源修订.html"
    guide = files[guide_name].decode("utf8")
    guide = replace_once(guide, "同一就诊的录音订正与病历修订 · MediListen", "字段审核试用 · MediListen")
    guide = replace_once(guide, "订正说话人后，在同一次就诊修订病历", "字段审核与同一次就诊的录音订正")
    anchor = "<section><h2>先听清三段原话</h2>"
    guide = replace_once(guide, anchor, (RECIPE / "field_help.html").read_text(encoding="utf-8-sig").strip()+"\n"+anchor)
    files[guide_name] = guide.encode()
    output.mkdir(parents=True, exist_ok=True)
    edition = "r4.1" if with_help else "r4"
    path = output / f"MediListen_字段审核_Windows-x64_{commit[:7]}_{edition}.zip"
    with ZipFile(path, "x") as bundle:
        for name, contents in sorted(files.items()):
            info = ZipInfo(name, (2026, 11, 25, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            bundle.writestr(info, contents)
    with ZipFile(path) as bundle:
        if set(bundle.namelist()) != set(files) or any(bundle.read(n) != data for n, data in files.items()):
            raise ValueError("成品逐项回读失败")
    changed_members = sorted(name for name, data in files.items() if originals.get(name) != data)
    sha = digest(path.read_bytes())
    report = dict(file=path.name, sha256=sha, bytes=path.stat().st_size, files=len(files),
                  commit=commit, base=BASE_SHA256, source_sha=manifest["sha256"],
                  changed_application_files=sorted(changed), changed_archive_members=changed_members,
                  identical_archive_members=len(files)-len(changed_members),
                  frozen_model_reply_sha256=manifest["files"]["AUDIO_模型原答.json"],
                  reference_sha256=REFERENCE_SHA256)
    if with_help:
        report["public_help_inputs"] = help_inputs
    (output / "发布指纹.json").write_bytes(json_bytes(report))
    (output / (path.name+".sha256")).write_bytes((sha+"  "+path.name+"\n").encode())
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="已冻结的 r3 ZIP")
    parser.add_argument("--output", type=Path, required=True, help="新构建目录")
    parser.add_argument("--commit", required=True, help="完整的字段审核应用提交")
    parser.add_argument("--with-help", action="store_true", help="按应用提交中的公开白名单装配内置帮助")
    args = parser.parse_args()
    print(build(args.base, args.output, args.commit, with_help=args.with_help))
