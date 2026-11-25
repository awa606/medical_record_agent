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
R41_COMMIT = "ebece5c7ffb863f334034095e464d871561933e1"
R42_COMMIT = "963439b389e07cf31791dbfac030f825ab951a35"
R43_COMMIT = "bfc6779c5bd3d9f546b1f7669e2c32eb6bde1f96"
R44_COMMIT = "40747b6381c0c03506dc6fb059a4f4a0c118c6a0"
R45_COMMIT = "a2f6c3120eb82d36eceeaa53b3fffc0ef5d1e20a"
R46_COMMIT = "ad645bc38d8bbb042e4318d1ca5196144ac446d3"
R44_CONTENT_PATHS = (
    "app/services/knowledge_store.py",
    "static/help/index.html",
    "docs/pilot/doctor-v1/manual.html",
)
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


def require_ancestor(ancestor: str, descendant: str, edition: str) -> None:
    result = subprocess.run(["git", "merge-base", "--is-ancestor", ancestor, descendant], cwd=REPO)
    if result.returncode != 0:
        raise ValueError(f"{edition} 的提交不在已核验的版本范围，或本地缺少所需提交历史")


def verify_release_changes(previous: str, commit: str, edition: str, assets: tuple[str, ...],
                           additional_paths: tuple[str, ...] = ()) -> list[str]:
    packaged = ["app", "assets", "config", "static", *approved_help_inputs(previous)]
    changed = git_bytes("diff", "--name-only", previous, commit, "--", *packaged).decode().splitlines()
    expected = {"static/doctor.html", *("static/" + name for name in assets), *additional_paths}
    if set(changed) != expected:
        raise ValueError(f"{edition} 的运行文件或内置帮助超出已核验范围：{changed}")
    expected_html = git_bytes("show", f"{previous}:static/doctor.html").decode()
    for name in assets:
        old_stamp = digest(git_bytes("show", f"{previous}:static/{name}"))[:16]
        new_stamp = digest(git_bytes("show", f"{commit}:static/{name}"))[:16]
        expected_html = replace_once(expected_html, f"./{name}?v={old_stamp}", f"./{name}?v={new_stamp}")
    if git_bytes("show", f"{commit}:static/doctor.html") != expected_html.encode():
        raise ValueError(f"{edition} 的医生入口只允许更新已核验资源的实际内容指纹")
    return sorted(changed)


def verify_r42_changes(commit: str) -> list[str]:
    require_ancestor(R41_COMMIT, commit, "r4.2")
    require_ancestor(commit, R42_COMMIT, "r4.2")
    return verify_release_changes(R41_COMMIT, commit, "r4.2", ("doctor.js", "doctor-workspace.css"))


def verify_r43_changes(commit: str) -> list[str]:
    require_ancestor(R42_COMMIT, commit, "r4.3")
    require_ancestor(commit, R43_COMMIT, "r4.3")
    return verify_release_changes(R42_COMMIT, commit, "r4.3", ("doctor.js",))


def verify_r44_changes(commit: str) -> list[str]:
    if commit != R44_COMMIT:
        raise ValueError("r4.4 需要已冻结的完整应用提交")
    require_ancestor(R43_COMMIT, commit, "r4.4")
    return verify_release_changes(R43_COMMIT, commit, "r4.4", ("doctor.js",), R44_CONTENT_PATHS)


def verify_r45_changes(commit: str) -> list[str]:
    if commit != R45_COMMIT:
        raise ValueError("r4.5 需要已冻结的完整应用提交")
    require_ancestor(R44_COMMIT, commit, "r4.5")
    return verify_release_changes(R44_COMMIT, commit, "r4.5", ("doctor.js",))


def verify_r46_changes(commit: str) -> list[str]:
    if commit != R46_COMMIT:
        raise ValueError("r4.6 需要已冻结的完整工作台应用提交")
    require_ancestor(R45_COMMIT, commit, "r4.6")
    packaged = ["app", "assets", "config", "static", *approved_help_inputs(R45_COMMIT)]
    changed = git_bytes("diff", "--name-only", R45_COMMIT, commit, "--", *packaged).decode().splitlines()
    assets = ("doctor-workspace.css", "doctor.js")
    if set(changed) != {"static/doctor.html", *("static/" + name for name in assets)}:
        raise ValueError(f"r4.6 的运行文件或内置帮助超出已核验范围：{changed}")
    entry = git_bytes("show", f"{commit}:static/doctor.html").decode()
    for name in assets:
        stamp = digest(git_bytes("show", f"{commit}:static/{name}"))[:16]
        if entry.count(f"./{name}?v=") != 1 or f'./{name}?v={stamp}"' not in entry:
            raise ValueError(f"r4.6 的医生入口未使用本次 {name} 实际内容指纹")
    return sorted(changed)


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

def build(base: Path, output: Path, commit: str, *, with_help: bool = False, r4_2: bool = False,
          r4_3: bool = False, r4_4: bool = False, r4_5: bool = False, r4_6: bool = False) -> Path:
    if not re.fullmatch("[0-9a-f]{40}", commit):
        raise ValueError("请使用完整的应用提交 SHA")
    if sum((with_help, r4_2, r4_3, r4_4, r4_5, r4_6)) > 1:
        raise ValueError("只能选择一个随身包版本")
    if (r4_2 or r4_3 or r4_4 or r4_5 or r4_6) and output.exists() and any(output.iterdir()):
        raise ValueError("请使用全新的输出目录，以保留已有发行物和指纹")
    if digest(base.read_bytes()) != BASE_SHA256:
        raise ValueError("基础 ZIP 与已验收的 r3 不符")
    edition = "r4.1" if with_help else "r4"
    if r4_2:
        edition = "r4.2"
        changes_since_previous = verify_r42_changes(commit)
    if r4_3:
        edition = "r4.3"
        changes_since_previous = verify_r43_changes(commit)
    if r4_4:
        edition = "r4.4"
        changes_since_previous = verify_r44_changes(commit)
    if r4_5:
        edition = "r4.5"
        changes_since_previous = verify_r45_changes(commit)
    if r4_6:
        edition = "r4.6"
        changes_since_previous = verify_r46_changes(commit)
    with_help = with_help or r4_2 or r4_3 or r4_4 or r4_5 or r4_6
    changed = set(git_bytes("diff", "--name-only", BASE_COMMIT, commit, "--", "app", "assets", "config", "static").decode().splitlines())
    expected = {"static/doctor.js", "static/doctor.html", "static/doctor-workspace.css"}
    if with_help:
        expected.update({"static/doctor.css", "static/help/index.html"})
    if r4_4 or r4_5 or r4_6:
        expected.add("app/services/knowledge_store.py")
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
    if r4_2:
        report["previous_application_commit"] = R41_COMMIT
        report["changed_since_r4_1"] = changes_since_previous
    if r4_3:
        report["previous_application_commit"] = R42_COMMIT
        report["changed_since_r4_2"] = changes_since_previous
    if r4_4 or r4_5 or r4_6:
        previous, change_key = {
            "r4.4": (R43_COMMIT, "changed_since_r4_3"),
            "r4.5": (R44_COMMIT, "changed_since_r4_4"),
            "r4.6": (R45_COMMIT, "changed_since_r4_5"),
        }[edition]
        report["previous_application_commit"] = previous
        report[change_key] = changes_since_previous
        report["changed_source_sha256"] = {
            name: digest(git_bytes("show", f"{commit}:{name}")) for name in changes_since_previous
        }
    (output / "发布指纹.json").write_bytes(json_bytes(report))
    (output / (path.name+".sha256")).write_bytes((sha+"  "+path.name+"\n").encode())
    return path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, required=True, help="已冻结的 r3 ZIP")
    parser.add_argument("--output", type=Path, required=True, help="新构建目录")
    parser.add_argument("--commit", required=True, help="完整的字段审核应用提交")
    edition = parser.add_mutually_exclusive_group()
    edition.add_argument("--with-help", action="store_true", help="构建含完整内置帮助的 r4.1")
    edition.add_argument("--r4-2", action="store_true", help="构建含完整内置帮助、可逐条查看出处的 r4.2")
    edition.add_argument("--r4-3", action="store_true", help="构建含字段操作完整可访问名称的 r4.3")
    edition.add_argument("--r4-4", action="store_true", help="构建标明参考资料性质与用途的 r4.4")
    edition.add_argument("--r4-5", action="store_true", help="构建显示中文字段冲突提示的 r4.5")
    edition.add_argument("--r4-6", action="store_true", help="构建以连续病历正文为主的普通医生工作台 r4.6")
    args = parser.parse_args()
    print(build(args.base, args.output, args.commit, with_help=args.with_help,
                r4_2=args.r4_2, r4_3=args.r4_3, r4_4=args.r4_4, r4_5=args.r4_5, r4_6=args.r4_6))
