"""从锁定的官方 Windows wheels 准备课堂运行环境，并调用原课堂启动器。"""
import argparse
import hashlib
import json
import os
import platform
import re
import socket
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urlparse
from urllib.request import urlopen
from contextlib import contextmanager

HERE = Path(__file__).resolve().parent
BUNDLE = HERE.parent / "现场回放"
BUNDLE_SHA = "5cc24fe0ff55c645447afbffe9adf3dbdf218f14b01482885e0fc7adce5128ee"


def canonical(name):
    return re.sub(r"[-_.]+", "-", name).lower()


@contextmanager
def exclusive_setup(path):
    import msvcrt
    with path.open("a+b") as stream:
        if not stream.tell():
            stream.write(b"1")
            stream.flush()
        stream.seek(0)
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)


def check_installed(python, rows):
    inspect = (
        "from importlib.metadata import distributions; import json, platform, sys;"
        "print(json.dumps([sys.prefix!=sys.base_prefix,platform.python_version(),"
        "[[d.metadata['Name'],d.version] for d in distributions()]]))"
    )
    isolated, version, installed = json.loads(subprocess.check_output(
        [python, "-I", "-B", "-c", inspect], text=True))
    expected = sorted((canonical(row["name"]), row["version"]) for row in rows)
    actual = sorted((canonical(name), value) for name, value in installed)
    if not isolated or version != platform.python_version() or actual != expected:
        raise RuntimeError("解释器或安装清单与本锁不一致。请指定一个新目录重新准备。")
    subprocess.run([python, "-I", "-m", "pip", "--disable-pip-version-check", "check"], check=True)


def prepare(python, rows, lock, wheel_dir):
    env_dir = python.parent.parent
    marker = env_dir / ".medilisten-preparing.json"
    request = {"target": str(env_dir), "base": str(Path(sys.executable).resolve()),
               "lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest()}
    resuming = marker.is_file() and json.loads(marker.read_text(encoding="utf-8")) == request
    if env_dir.exists() and not resuming:
        if not (env_dir / "pyvenv.cfg").is_file() or not python.is_file():
            raise RuntimeError("目标已存在且不是可识别的虚拟环境。请选择新的环境目录。")
        check_installed(python, rows)
        return
    lines = [f"{r['name']}=={r['version']} --hash=sha256:{r['sha256']}" for r in rows]
    if lock.read_text(encoding="utf-8").splitlines() != lines:
        raise RuntimeError("轮包清单与版本锁不一致。")
    with TemporaryDirectory(prefix="medilisten-wheels-") as temp:
        for row in rows:
            parsed = urlparse(row["url"])
            filename = row["filename"]
            if (parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org"
                    or Path(filename).name != filename or not filename.endswith(".whl")):
                raise RuntimeError("轮包来源或文件名不符合锁定的官方发布形式。")
            if wheel_dir:
                data = (wheel_dir / filename).read_bytes()
            else:
                with urlopen(row["url"], timeout=90) as stream:
                    if urlparse(stream.geturl()).hostname != parsed.hostname:
                        raise RuntimeError("轮包下载被重定向到不同主机。")
                    data = stream.read()
            if len(data) != row["bytes"] or hashlib.sha256(data).hexdigest() != row["sha256"]:
                raise RuntimeError(f"轮包校验失败：{filename}")
            (Path(temp) / filename).write_bytes(data)
        if not resuming:
            env_dir.mkdir(parents=True, exist_ok=False)
            with marker.open("x", encoding="utf-8") as out:
                json.dump(request, out, ensure_ascii=False)
        with exclusive_setup(env_dir / ".medilisten-setup.lock"):
            if not marker.is_file():
                check_installed(python, rows)
                return
            subprocess.run([sys.executable, "-I", "-m", "venv", env_dir], check=True)
            env = {k: v for k, v in os.environ.items() if not k.upper().startswith("PIP_")}
            env["PIP_CONFIG_FILE"] = os.devnull
            subprocess.run([python, "-I", "-m", "pip", "--disable-pip-version-check", "--no-cache-dir",
                            "install", "--no-index", "--only-binary", ":all:", "--require-hashes",
                            "--find-links", temp, "-r", lock], check=True, env=env)
            check_installed(python, rows)
            marker.replace(env_dir / ".medilisten-prepared.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start"))
    parser.add_argument("--env-path", type=Path, help="专用虚拟环境路径")
    parser.add_argument("--wheel-dir", type=Path, help="用同一版本锁校验并从本地轮包目录安装")
    parser.add_argument("--data-root", type=Path, help="独立的课堂数据目录")
    parser.add_argument("--port", type=int, default=26428)
    parser.add_argument("--no-browser", action="store_true", help="供自动检查，不打开浏览器")
    args = parser.parse_args()
    if (sys.platform != "win32" or platform.machine().lower() != "amd64"
            or platform.python_implementation() != "CPython"):
        raise RuntimeError("此版本锁适用于 Windows x64 CPython。")
    abi = "".join(map(str, sys.version_info[:2]))
    index = HERE / f"Windows{abi}轮包核验.json"
    if not index.is_file():
        raise RuntimeError("本目录没有这个 Python 版本的 Windows 轮包锁。")
    manifest = json.loads(index.read_text(encoding="utf-8"))
    if not manifest["platform"].endswith(" " + platform.python_version()):
        raise RuntimeError("宿主补丁版本与已测记录不同，请使用对应的已测宿主。")
    if hashlib.sha256((BUNDLE / "运行源/runtime-sha256.json").read_bytes()).hexdigest() != BUNDLE_SHA:
        raise RuntimeError("相邻课堂包的运行清单与本次实测不一致。")
    local = Path(os.environ["LOCALAPPDATA"]) / "MediListen课堂专用"
    env_home = local
    if HERE.parts[-4:] == ("output", "20261124_企业与结课验收", "软件", "专用环境"):
        release = HERE.parents[3] / ".artifacts/20261124-release"
        marker = release / ".medilisten-workspace-root.txt"
        if marker.is_file() and marker.read_text(encoding="utf-8").strip().casefold() == str(HERE.parents[3]).casefold():
            env_home = release
    default_env = env_home / f"Windows-CPython{abi}-专用"
    python = (args.env_path or default_env).resolve() / "Scripts/python.exe"
    rows = manifest["rows"]
    if args.action == "prepare":
        prepare(python, rows, HERE / f"requirements-win{abi}.lock", args.wheel_dir)
        print("专用环境已核对", python)
        return
    if not python.is_file():
        raise RuntimeError("请先按同目录说明运行 prepare 准备专用环境。")
    check_installed(python, rows)
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", args.port)) == 0:
            raise RuntimeError("选定端口正在使用。请在原窗口结束或指定其他课堂端口。")
    data = args.data_root or local / f"课堂数据-{abi}"
    command = [python, "-B", "-X", "utf8", BUNDLE / "课堂启动.py",
               "--data-root", data, "--port", str(args.port)]
    if args.no_browser:
        command.append("--no-browser")
    subprocess.run(command, check=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as e:
        sys.exit(f"专用环境操作未完成。{e}")
