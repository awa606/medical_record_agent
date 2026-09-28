"""Local, pinned deployment controller. Never builds, deletes or migrates data."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import shutil
import subprocess
import sys
import time
from urllib import error, request

SERVICES = ("ollama", "app", "gateway")
RESOURCES = ("doctor.html", "doctor.js", "doctor.css", "doctor-ui-v2.css", "doctor-workspace.css")
BRAND_RESOURCES = ("brand/medilisten-v1.png", "brand/medilisten-v1.ico")
MODEL_DIGEST = "359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7"
ROOT = Path(__file__).resolve().parents[1]


class PilotError(RuntimeError):
    pass


def command(*args: str) -> str:
    try:
        p = subprocess.run(list(args), capture_output=True, text=True, encoding="utf8",
                           errors="replace", timeout=40,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PilotError("DOCKER_UNAVAILABLE: 请打开Docker Desktop后重试；未改动其他服务。") from exc
    if p.returncode:
        # Docker output can contain environment values. Do not expose it in the UI.
        raise PilotError("DOCKER_COMMAND_FAILED: 请由维护人员检查Docker及登记的容器。")
    return p.stdout.strip()


def inspect(name: str) -> dict:
    return json.loads(command("docker", "inspect", name))[0]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fetch(port: int, path: str) -> tuple[int, bytes]:
    opener = request.build_opener(request.ProxyHandler({}))
    try:
        with opener.open(f"http://127.0.0.1:{port}{path}", timeout=10) as r:
            return r.status, r.read()
    except error.HTTPError as exc:
        return exc.code, exc.read()
    except (OSError, error.URLError, TimeoutError):
        return 0, b""


def env(item: dict) -> dict:
    return dict(x.split("=", 1) for x in item["Config"].get("Env", []) if "=" in x)


def mount(item: dict, destination: str) -> str:
    matches = [m["Source"] for m in item["Mounts"] if m["Destination"] == destination]
    if len(matches) != 1:
        raise PilotError("MOUNT_MISMATCH: 运行目录或模型缓存不明确；已停止操作。")
    return str(Path(matches[0]).resolve())


def check_real(items: dict, project: str, port: int) -> None:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{2,60}", project) or not 1024 <= port <= 65535:
        raise PilotError("INVALID_CONFIG: 项目或端口无效。")
    if port in (2600, 2626, 2666):
        raise PilotError("LEGACY_PORT: 本工具不管理历史环境。")
    for service, item in items.items():
        labels = item["Config"].get("Labels") or {}
        if labels.get("com.docker.compose.project") != project or labels.get("com.docker.compose.service") != service:
            raise PilotError("PROJECT_MISMATCH: 容器不属于登记项目。")
    e = env(items["app"])
    expected = {"RECORD_PROVIDER_MODE": "edge", "MEDICAL_RECORD_AGENT_ASR_ENGINE": "funasr",
                "MEDICAL_RECORD_AGENT_REQUIRE_FUNASR": "1", "LLM_PROVIDER": "ollama",
                "OLLAMA_MODEL": "qwen3:4b", "OLLAMA_BASE_URL": "http://ollama:11434"}
    if any(e.get(k) != v for k, v in expected.items()):
        raise PilotError("PROVIDER_MISMATCH: 必须使用固定本地FunASR和Qwen，拒绝Mock或云端。")
    bindings = items["gateway"]["HostConfig"].get("PortBindings") or {}
    if bindings != {"8000/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(port)}]}:
        raise PilotError("PORT_MISMATCH: 网关必须只绑定登记的本机端口。")
    for service in ("app", "ollama"):
        if items[service]["HostConfig"].get("PortBindings"):
            raise PilotError("EXPOSED_MODEL: 模型和应用不得单独暴露端口。")


def configure(project: str, port: int, path: Path) -> dict:
    if path.exists():
        raise PilotError("CONFIG_EXISTS: 保留旧配置；升级请生成新文件并重新验收。")
    items = {s: inspect(f"{project}-{s}-1") for s in SERVICES}
    check_real(items, project, port)
    code, _ = fetch(port, "/health")
    if code != 200:
        raise PilotError("HEALTH_REQUIRED: 登记版本前必须恢复现有服务。")
    app = items["app"]
    labels = json.loads(command("docker", "image", "inspect", app["Image"]))[0]["Config"].get("Labels") or {}
    revision = labels.get("org.opencontainers.image.revision", "")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise PilotError("VERSION_UNKNOWN: 镜像必须有完整Git版本标签。")
    model_dir = Path(mount(items["ollama"], "/root/.ollama/models"))
    manifest = model_dir / "manifests/registry.ollama.ai/library/qwen3/4b"
    if not manifest.is_file() or sha(manifest) != MODEL_DIGEST:
        raise PilotError("MODEL_DIGEST_MISMATCH: 固定模型摘要不符。")
    resources = {}
    for resource in (*RESOURCES, *BRAND_RESOURCES):
        status, content = fetch(port, "/static/" + resource)
        if status != 200:
            raise PilotError("RESOURCE_MISSING: 医生页面资源不完整。")
        resources[resource] = hashlib.sha256(content).hexdigest()
    config = {"schema_version": 1, "release_status": "CANDIDATE_NOT_RELEASED",
              "project": project, "port": port, "app_git_sha": revision,
              "model_digest": MODEL_DIGEST, "model_manifest": str(manifest),
              "runtime": mount(app, "/app/runtime"), "resources": resources,
              "containers": {s: {"id": i["Id"], "image": i["Image"],
                                  "mounts": {m["Destination"]: str(Path(m["Source"]).resolve()) for m in i["Mounts"]}}
                             for s, i in items.items()}}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf8")
    return config


def validate(config: dict) -> dict:
    if config.get("schema_version") != 1 or set(config.get("containers", {})) != set(SERVICES):
        raise PilotError("INVALID_CONFIG: 配置版本或服务不完整。")
    # Previous registrations stay valid; a new registration pins both brand assets.
    if set(config.get("resources", {})) not in (set(RESOURCES), set(RESOURCES) | set(BRAND_RESOURCES)):
        raise PilotError("INVALID_CONFIG: 网页资源指纹不完整，需要维护人员重新登记。")
    items = {s: inspect(config["containers"][s]["id"]) for s in SERVICES}
    check_real(items, config["project"], config["port"])
    for service, item in items.items():
        pinned = config["containers"][service]
        actual_mounts = {m["Destination"]: str(Path(m["Source"]).resolve()) for m in item["Mounts"]}
        if item["Id"] != pinned["id"] or item["Image"] != pinned["image"] or actual_mounts != pinned["mounts"]:
            raise PilotError("VERSION_MISMATCH: 容器、镜像或挂载已变化，需要维护人员重新登记。")
    if not (Path(config["runtime"]) / "medical_record_agent.sqlite3").is_file():
        raise PilotError("DATA_MISSING: 运行库不存在；不会自动初始化或覆盖。")
    manifest = Path(config["model_manifest"])
    if not manifest.is_file() or sha(manifest) != config["model_digest"] or config["model_digest"] != MODEL_DIGEST:
        raise PilotError("MODEL_DIGEST_MISMATCH: 模型缓存发生变化。")
    return items


def web_status(config: dict, items: dict) -> dict:
    states = {s: i["State"]["Status"] for s, i in items.items()}
    result = {"phase": "STOPPED", "states": states, "web_available": False,
              "model_ready": False, "app_git_sha": config["app_git_sha"],
              "release_status": config["release_status"], "port": config["port"]}
    if not all(i["State"]["Running"] for i in items.values()):
        return result
    status, _ = fetch(config["port"], "/health")
    if status != 200:
        result["phase"] = "WEB_STARTING"
        return result
    for name, expected in config["resources"].items():
        code, content = fetch(config["port"], "/static/" + name)
        if code != 200 or hashlib.sha256(content).hexdigest() != expected:
            raise PilotError("RESOURCE_MISMATCH: 网页资源与登记版本不同，拒绝打开。")
    result["web_available"] = True
    status, _ = fetch(config["port"], "/ready")
    result.update(phase="READY" if status == 200 else "MODEL_NOT_READY", model_ready=status == 200)
    return result


def data_browser_status() -> dict:
    """Inspect the separately authenticated snapshot; never expose its token."""
    state_path = ROOT / ".artifacts/data-browser/state.private.json"
    if not state_path.is_file():
        return {"available": False, "phase": "STOPPED"}
    try:
        state = json.loads(state_path.read_text(encoding="utf-8-sig"))
        port = int(state["port"])
        if not 1024 <= port <= 65535:
            raise ValueError("invalid port")
        directory = Path(state["snapshot_dir"])
        manifest = json.loads((directory / "manifest.json").read_text(encoding="utf8"))
        if (manifest.get("synthetic_only") is not True
                or sha(directory / "mra_snapshot.sqlite3") != manifest["database_sha256"]):
            raise ValueError("invalid snapshot")
        login = json.loads((directory / "login.private.json").read_text(encoding="utf8"))
        if login.get("run_id") != state["run_id"]:
            raise ValueError("snapshot process mismatch")
        # The private run ID binds the process to this tool, not just any HTTP 403.
        process_code = f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {int(state['pid'])}').CommandLine"
        process = subprocess.run(["powershell.exe", "-NoProfile", "-Command", process_code],
                                 capture_output=True, text=True, encoding="utf8", errors="replace",
                                 timeout=8, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        owned = state["run_id"] in process.stdout and "data_browser.py" in process.stdout
        code, _ = fetch(port, "/") if owned else (0, b"")
        return {"available": code == 403, "phase": "AUTH_REQUIRED" if code == 403 else "STOPPED",
                "url": f"http://127.0.0.1:{port}/", "snapshot_at": manifest["captured_at"],
                "source_label": manifest["source_label"], "readonly_snapshot": True}
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired):
        return {"available": False, "phase": "INVALID_SNAPSHOT"}


def entrypoint_status(config: dict, result: dict) -> dict:
    documents = Path(config.get("handbook_dir") or ROOT / "docs/pilot/doctor-v1")
    base = f"http://127.0.0.1:{config['port']}/static/doctor.html"
    return {**result, "entrypoints": {
        "doctor": {"available": result["web_available"], "url": base},
        "knowledge": {"available": result["web_available"], "url": base + "#admin",
                      "requires": "admin login; doctor uses field evidence search"},
        "data_browser": data_browser_status(),
        "manual": {"available": (documents / "manual.html").is_file(), "path": str(documents / "manual.html")},
    }}


def open_data_browser(config: dict) -> dict:
    # Verify this launcher still belongs to the pinned deployment before opening
    # any ancillary entry. Start is idempotent and retains the saved backup date.
    validate(config)
    shell = shutil.which("pwsh")
    if not shell:
        raise PilotError("VIEWER_SHELL_MISSING: 数据浏览器需要现有PowerShell 7；医生服务未改动。")
    # A newly detached Windows process/browser may inherit a captured pipe and
    # keep communicate() waiting after PowerShell exits. Use a local log file.
    log = ROOT / ".artifacts/data-browser/launcher.private.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf8") as output:
        process = subprocess.run([shell, "-NoProfile", "-File", str(ROOT / "scripts/Start-MRADataBrowser.ps1"),
                                  "-Action", "Start", "-OpenBrowser"],
                                 stdout=output, stderr=output, timeout=60,
                                 creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if process.returncode:
        raise PilotError("VIEWER_START_FAILED: 数据浏览器未启动；检查备份、端口或独立工具环境，医生服务保持原样。")
    result = data_browser_status()
    if not result["available"]:
        raise PilotError("VIEWER_NOT_READY: 本地快照尚未通过认证入口检查。")
    return {"phase": "VIEWER_READY", "entrypoints": {"data_browser": result}}


@contextmanager
def operation_lock(path: Path):
    lock = path.with_suffix(".operation-lock")
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise PilotError("OPERATION_RUNNING: 另一项启动/停止正在执行。若进程异常退出，请维护人员核对锁文件。") from exc
    try:
        os.write(descriptor, str(os.getpid()).encode())
        yield
    finally:
        os.close(descriptor)
        lock.unlink()


def start(config: dict, config_path: Path, timeout: int = 600) -> dict:
    with operation_lock(config_path):
        items = validate(config)
        if not items["gateway"]["State"]["Running"]:
            with socket.socket() as probe:
                if probe.connect_ex(("127.0.0.1", config["port"])) == 0:
                    raise PilotError("PORT_OCCUPIED: 端口已有其他程序；不会停止它或切到旧版本。")
        command("docker", "update", "--restart", "unless-stopped", *(items[s]["Id"] for s in SERVICES))
        for service in SERVICES:
            if not items[service]["State"]["Running"]:
                command("docker", "start", items[service]["Id"])
        deadline = time.monotonic() + timeout
        previous = None
        while True:
            state = web_status(config, validate(config))
            if state["phase"] != previous:
                print(json.dumps(state, ensure_ascii=False), flush=True)
                previous = state["phase"]
            if state["model_ready"]:
                return state
            if time.monotonic() >= deadline:
                raise PilotError("READY_TIMEOUT: 页面可打开时可查历史记录，真实生成仍被阻断；请维护人员检查ASR/LLM。")
            time.sleep(3)


def stop(config: dict, config_path: Path) -> dict:
    with operation_lock(config_path):
        items = validate(config)
        for service in reversed(SERVICES):
            if items[service]["State"]["Running"]:
                command("docker", "stop", "--time", "30", items[service]["Id"])
        return {"phase": "STOPPED", "message": "已停止本版本，数据库和模型保留。"}


def open_workspace(config: dict, *, view: str = "workbench") -> dict:
    result = web_status(config, validate(config))
    if not result["web_available"]:
        raise PilotError("WEB_NOT_READY: 请先启动本版本。")
    edge = next((Path(os.environ.get(k, "")) / "Microsoft/Edge/Application/msedge.exe"
                 for k in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA")
                 if (Path(os.environ.get(k, "")) / "Microsoft/Edge/Application/msedge.exe").is_file()), None)
    if edge is None:
        raise PilotError("EDGE_MISSING: 请维护人员安装Microsoft Edge。")
    # Separate cookies from the maintainer's ordinary Edge/admin session.
    profile = Path(config["runtime"]).parent / "doctor-browser-profile"
    suffix = "#admin" if view == "admin" else ""
    subprocess.Popen([str(edge), f"--user-data-dir={profile}", "--no-first-run",
                      f"--app=http://127.0.0.1:{config['port']}/static/doctor.html{suffix}"])
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=("configure", "status", "start", "stop", "open", "open-knowledge", "open-data"))
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--project", default="mra51repair8795")
    p.add_argument("--port", type=int, default=8795)
    p.add_argument("--timeout", type=int, default=600)
    a = p.parse_args()
    try:
        if a.action == "configure":
            config = configure(a.project, a.port, a.config)
            result = {"phase": "CONFIGURED", "app_git_sha": config["app_git_sha"], "config": str(a.config)}
        else:
            config = json.loads(a.config.read_text(encoding="utf-8-sig"))
            result = {"status": lambda: entrypoint_status(config, web_status(config, validate(config))),
                      "start": lambda: entrypoint_status(config, start(config, a.config, a.timeout)),
                      "stop": lambda: stop(config, a.config),
                      "open": lambda: open_workspace(config),
                      "open-knowledge": lambda: open_workspace(config, view="admin"),
                      "open-data": lambda: open_data_browser(config)}[a.action]()
        print(json.dumps(result, ensure_ascii=False), flush=True)
    except (PilotError, OSError, ValueError, KeyError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({"phase": "ERROR", "message": str(exc)}, ensure_ascii=False), flush=True)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
