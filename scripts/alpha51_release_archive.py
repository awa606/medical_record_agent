"""Create and restore the isolated, anonymous Alpha 5.1 offline candidate.

The package stays outside Git. A release is not stable until ``restore`` has
verified its hashes, started it from a different directory, and passed a real
provider readiness probe. No patient audio or source runtime database is copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen


ROOT = Path(__file__).resolve().parents[1]
APP_IMAGE = "mra-alpha-demo-m4-rc1:candidate"
OLLAMA_IMAGE = "ollama/ollama:0.34.0"
OLLAMA_MODEL = "qwen3:4b"
MANIFEST_REL = Path("manifests/registry.ollama.ai/library/qwen3/4b")


def run(*command: str, cwd: Path | None = None) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=True)
    return result.stdout.strip()


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def image_id(name: str) -> str:
    return run("docker", "image", "inspect", name, "--format", "{{.Id}}")


def tracked_files(package: Path) -> list[Path]:
    return sorted(
        (item for item in package.rglob("*") if item.is_file()
         and item.name not in {"manifest.json", "sha256sums.txt"}),
        key=lambda item: item.relative_to(package).as_posix(),
    )


def write_hashes(package: Path) -> dict[str, str]:
    entries = {item.relative_to(package).as_posix(): digest(item) for item in tracked_files(package)}
    (package / "sha256sums.txt").write_text(
        "".join(f"{value}  {name}\n" for name, value in entries.items()), encoding="utf-8"
    )
    return entries


def verify_hashes(package: Path) -> dict[str, str]:
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    expected = manifest["files"]
    actual = {item.relative_to(package).as_posix(): digest(item) for item in tracked_files(package)}
    if actual != expected:
        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        changed = sorted(name for name in set(actual) & set(expected) if actual[name] != expected[name])
        raise RuntimeError(f"archive hash mismatch: missing={missing}, extra={extra}, changed={changed}")
    return manifest


def create(args: argparse.Namespace) -> None:
    package = args.package.resolve()
    if package.exists():
        raise RuntimeError(f"refusing to overwrite archive: {package}")
    if args.modelscope.resolve() == package or package.is_relative_to(args.modelscope.resolve()):
        raise RuntimeError("archive must be outside the model cache")
    sha = run("git", "rev-parse", "HEAD", cwd=ROOT)
    if run("git", "status", "--porcelain", cwd=ROOT):
        raise RuntimeError("commit the release source before packaging")
    source_manifest = args.ollama_models / MANIFEST_REL
    model = json.loads(source_manifest.read_text(encoding="utf-8"))
    layers = [model["config"], *model["layers"]]
    expected_blobs = [(layer["digest"], int(layer["size"])) for layer in layers]
    for model_digest, size in expected_blobs:
        blob = args.ollama_models / "blobs" / model_digest.replace(":", "-")
        if blob.stat().st_size != size:
            raise RuntimeError(f"Ollama blob size mismatch: {model_digest}")
        if digest(blob) != model_digest.partition(":")[2]:
            raise RuntimeError(f"Ollama blob digest mismatch: {model_digest}")
    if not (args.modelscope / "models").is_dir():
        raise RuntimeError("FunASR ModelScope cache has no models directory")
    package.mkdir(parents=True)
    (package / "models" / "ollama" / MANIFEST_REL.parent).mkdir(parents=True)
    shutil.copy2(source_manifest, package / "models" / "ollama" / MANIFEST_REL)
    blob_dir = package / "models" / "ollama" / "blobs"
    blob_dir.mkdir(parents=True)
    for model_digest, _size in expected_blobs:
        filename = model_digest.replace(":", "-")
        shutil.copy2(args.ollama_models / "blobs" / filename, blob_dir / filename)
    shutil.copytree(args.modelscope, package / "models" / "modelscope")
    (package / "models" / "hf").mkdir()
    (package / "data").mkdir()
    (package / "data" / "anonymous_seed.json").write_text(json.dumps({
        "patient_display_name": "模拟患者", "patient_deidentified_id": "SIM-ALPHA51",
        "source": "synthetic fixture; no real patient information",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    evidence = package / "evidence"
    evidence.mkdir()
    for name in (
        "20260924_alpha51_real_three_path_smoke.json",
        "20260924_alpha51_visual_verification.md",
        "20260924_alpha51_poc_to_alpha_case_card.md",
    ):
        shutil.copy2(ROOT / "docs" / "evidence" / name, evidence / name)
    shutil.copytree(ROOT / "docs" / "evidence" / "images" / "alpha51_v34_review",
                    evidence / "images" / "alpha51_v34_review")
    asr_licenses = []
    for card in sorted((package / "models" / "modelscope" / "models").glob("*/snapshots/*/README.md")):
        license_line = next((line.strip() for line in card.read_text(encoding="utf-8").splitlines()
                             if line.lower().startswith("license:")), "license: UNKNOWN")
        asr_licenses.append({"card": card.relative_to(package).as_posix(),
                             "card_sha256": digest(card), "declared_license": license_line.partition(":")[2].strip()})
    (evidence / "model_license_inventory.json").write_text(json.dumps({
        "qwen3_4b": {"license": "Apache-2.0",
                      "source": "https://huggingface.co/Qwen/Qwen3-4B-Thinking-2507/blob/main/LICENSE",
                      "ollama_manifest_sha256": digest(source_manifest)},
        "funasr_cached_models": asr_licenses,
        "scope": "local engineering archive; license metadata is not a clinical-use approval",
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    expected = json.loads((evidence / "20260924_alpha51_real_three_path_smoke.json").read_text(
        encoding="utf-8"))["cases"]["text"]["docx_sha256"]
    if digest(args.sample_export) != expected:
        raise RuntimeError("synthetic export does not match the verified text-case SHA")
    shutil.copy2(args.sample_export, evidence / "synthetic_text_case_export.docx")
    (package / "runtime-template" / "uploads").mkdir(parents=True)
    (package / "runtime-template" / "outputs").mkdir()
    (package / "runtime-template" / "speaker_profiles").mkdir()
    seed_db = package / "runtime-template" / "medical_record_agent.sqlite3"
    previous_db = os.environ.get("MEDICAL_RECORD_AGENT_DB")
    previous_bootstrap = os.environ.get("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP")
    try:
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(seed_db)
        os.environ["MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP"] = "0"
        sys.path.insert(0, str(ROOT))
        from app.db.sqlite import create_encounter, init_db
        init_db()
        create_encounter(doctor_user_id=None, deidentified_id="SIM-ALPHA51", display_name="模拟患者")
        with sqlite3.connect(seed_db) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.execute("PRAGMA journal_mode=DELETE")
            counts = {name: conn.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
                      for name in ("patient", "encounter", "auth_user", "agent_task")}
            if counts != {"patient": 1, "encounter": 1, "auth_user": 0, "agent_task": 0}:
                raise RuntimeError(f"unsafe seed database contents: {counts}")
    finally:
        if previous_db is None:
            os.environ.pop("MEDICAL_RECORD_AGENT_DB", None)
        else:
            os.environ["MEDICAL_RECORD_AGENT_DB"] = previous_db
        if previous_bootstrap is None:
            os.environ.pop("MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP", None)
        else:
            os.environ["MEDICAL_RECORD_AGENT_AUTH_BOOTSTRAP"] = previous_bootstrap
    (package / "runtime-template" / "README.md").write_text(
        "Synthetic patient and encounter only. No auth users, tasks, or audio are bundled.\n",
        encoding="utf-8",
    )
    (package / "tools").mkdir()
    shutil.copy2(Path(__file__), package / "tools" / "release.py")
    shutil.copy2(ROOT / "scripts" / "alpha51_gateway.py", package / "tools" / "gateway.py")
    (package / "compose.offline.yml").write_text(COMPOSE, encoding="utf-8")
    (package / "env.template").write_text(
        "MRA_PORT=8781\nMRA_BOOTSTRAP_PASSWORD=GENERATED_ON_RESTORE\n",
        encoding="utf-8",
    )
    (package / "README.md").write_text(RUNBOOK, encoding="utf-8")
    run("git", "bundle", "create", str(package / "source.bundle"), "--all", cwd=ROOT)
    for image, name in ((APP_IMAGE, "app-image.tar"), (OLLAMA_IMAGE, "ollama-image.tar")):
        subprocess.run(("docker", "save", "-o", str(package / name), image), check=True)
    files = write_hashes(package)
    payload = {
        "schema_version": "alpha51-offline-candidate-v1",
        "release_id": "alpha-demo-m4-rc1",
        "status": "CANDIDATE_UNVERIFIED",
        "git_sha": sha,
        "images": {APP_IMAGE: image_id(APP_IMAGE), OLLAMA_IMAGE: image_id(OLLAMA_IMAGE)},
        "model": {"tag": OLLAMA_MODEL, "manifest_sha256": digest(source_manifest),
                  "license": "Apache-2.0", "license_inventory": "evidence/model_license_inventory.json",
                  "blobs": dict(expected_blobs)},
        "data_policy": "synthetic only; source runtime/audio/password excluded",
        "files": files,
    }
    (package / "manifest.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"package": str(package), "files": len(files), "git_sha": sha}))


def check_port(port: int) -> None:
    if not 1024 <= port <= 65535:
        raise RuntimeError("port must be 1024..65535")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))


def response_code(url: str) -> int:
    try:
        with urlopen(url, timeout=8) as response:
            return response.status
    except (URLError, OSError) as exc:
        return getattr(exc, "code", 0) or 0


def restore(args: argparse.Namespace) -> None:
    source = args.package.resolve()
    target = args.target.resolve()
    if target.exists() or target == source or target.is_relative_to(source):
        raise RuntimeError("restore target must be a new directory separate from the package")
    check_port(args.port)
    manifest = verify_hashes(source)
    shutil.copytree(source, target)
    verify_hashes(target)
    runtime = target / "runtime"
    shutil.copytree(target / "runtime-template", runtime)
    password = secrets.token_urlsafe(32)
    (target / ".env").write_text(
        f"MRA_PORT={args.port}\nMRA_BOOTSTRAP_PASSWORD={password}\n", encoding="utf-8"
    )
    (target / "admin-password.txt").write_text(password, encoding="utf-8")
    for image_name in ("app-image.tar", "ollama-image.tar"):
        run("docker", "load", "-i", str(target / image_name))
    project = f"mra51restore{args.port}"
    command = ("docker", "compose", "-p", project, "-f", "compose.offline.yml")
    run(*command, "up", "-d", cwd=target)
    checks: dict[str, object] = {"restored_from_sha": manifest["git_sha"], "port": args.port,
                                "offline_network": "internal", "model": OLLAMA_MODEL}
    base = f"http://127.0.0.1:{args.port}"
    deadline = time.monotonic() + args.timeout
    while time.monotonic() < deadline:
        checks["health"] = response_code(base + "/health")
        checks["ready"] = response_code(base + "/ready")
        checks["doctor_page"] = response_code(base + "/static/doctor.html")
        if all(checks[key] == 200 for key in ("health", "ready", "doctor_page")):
            break
        time.sleep(5)
    network_probe = (
        "import socket\n"
        "try:\n socket.create_connection(('1.1.1.1',443),timeout=3); print('OPEN')\n"
        "except OSError:\n print('BLOCKED')\n"
    )
    checks["external_connection"] = run(*command, "exec", "-T", "app", "python", "-c", network_probe, cwd=target)
    checks["pass"] = (
        all(checks.get(key) == 200 for key in ("health", "ready", "doctor_page"))
        and checks["external_connection"] == "BLOCKED"
    )
    (target / "restore-result.json").write_text(json.dumps(checks, indent=2), encoding="utf-8")
    print(json.dumps(checks))
    if not checks["pass"]:
        raise RuntimeError("offline restore failed; inspect docker compose logs in target directory")


def stop(args: argparse.Namespace) -> None:
    target = args.target.resolve()
    project = f"mra51restore{args.port}"
    print(run("docker", "compose", "-p", project, "-f", "compose.offline.yml", "down", cwd=target))


COMPOSE = """services:
  ollama:
    image: ollama/ollama:0.34.0
    environment:
      OLLAMA_HOST: 0.0.0.0:11434
      OLLAMA_NO_CLOUD: "1"
    gpus: all
    volumes:
      - ./models/ollama:/root/.ollama/models
    networks: [offline]
  app:
    image: mra-alpha-demo-m4-rc1:candidate
    depends_on: [ollama]
    environment:
      PYTHONPATH: /app
      MEDICAL_RECORD_AGENT_DB: /app/runtime/medical_record_agent.sqlite3
      MEDICAL_RECORD_AGENT_UPLOAD_DIR: /app/runtime/uploads
      MEDICAL_RECORD_AGENT_OUTPUT_DIR: /app/runtime/outputs
      MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR: /app/runtime/speaker_profiles
      MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD: ${MRA_BOOTSTRAP_PASSWORD}
      RECORD_PROVIDER_MODE: edge
      MEDICAL_RECORD_AGENT_ASR_ENGINE: funasr
      MEDICAL_RECORD_AGENT_REQUIRE_FUNASR: "1"
      FUNASR_DEVICE: cpu
      ASR_PREWARM_ENABLED: "1"
      ASR_PREWARM_PROFILE: upload
      SPEAKER_ROLE_PROVIDER: rules
      LLM_PROVIDER: ollama
      OLLAMA_BASE_URL: http://ollama:11434
      OLLAMA_MODEL: qwen3:4b
      LLM_TIMEOUT_SECONDS: "180"
      LLM_MAX_RETRIES: "0"
      MRA_ANONYMIZE: "1"
      HF_HUB_OFFLINE: "1"
      TRANSFORMERS_OFFLINE: "1"
      MODELSCOPE_CACHE: /app/model_cache/modelscope
      HF_HOME: /app/model_cache/hf
    volumes:
      - ./runtime:/app/runtime
      - ./models/modelscope:/app/model_cache/modelscope
      - ./models/hf:/app/model_cache/hf
    networks: [offline]
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://127.0.0.1:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s
  gateway:
    image: mra-alpha-demo-m4-rc1:candidate
    depends_on: [app]
    command: ["python", "/gateway.py"]
    ports:
      - "127.0.0.1:${MRA_PORT}:8000"
    volumes:
      - ./tools/gateway.py:/gateway.py:ro
    networks: [offline, frontend]
networks:
  offline:
    internal: true
  frontend: {}
"""

RUNBOOK = """# Alpha demo m4 rc1 · 离线恢复候选

该包只含合成数据和固定模型。`manifest.json` 状态为 CANDIDATE_UNVERIFIED；
恢复成功后以 `restore-result.json` 和真实生成 Smoke 判定可恢复，不能把候选直接称作稳定版。

在已安装 Python 3、Docker Engine、Docker Compose 与可用 NVIDIA 容器 GPU 的
DEV-01 开发机执行。该归档未在 Jetson ARM/CUDA 上验证：

```powershell
python tools/release.py restore --package <归档目录> --target <新空目录> --port 8781
python tools/release.py stop --target <新空目录> --port 8781
```

恢复器先核对每个文件 SHA256，再复制到新目录、加载镜像。App 与 Ollama 只接入
Docker internal 网络；无运行数据卷的 TCP 网关把 App 发布到主机 loopback 端口。
浏览器仅访问 `http://127.0.0.1:8781/static/doctor.html`。
`admin-password.txt` 和 `.env` 在恢复时随机生成，位于恢复目录，不属于原归档。
`/health` 仅表示 Web 进程存活，`/ready` 表示本地 ASR/LLM 等真实依赖就绪。
`evidence/` 包含匿名测试摘要、认可版截图、模型许可清单及一份经 SHA 对照的
合成病例导出样例。需要通过另外的合成病例生成 Smoke，才可标为可恢复候选。
真实音频和患者资料不得放入归档。
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    create_parser = sub.add_parser("create")
    create_parser.add_argument("--package", type=Path, required=True)
    create_parser.add_argument("--modelscope", type=Path, required=True)
    create_parser.add_argument("--ollama-models", type=Path, required=True)
    create_parser.add_argument("--sample-export", type=Path, required=True)
    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--package", type=Path, required=True)
    restore_parser.add_argument("--target", type=Path, required=True)
    restore_parser.add_argument("--port", type=int, required=True)
    restore_parser.add_argument("--timeout", type=int, default=600)
    stop_parser = sub.add_parser("stop")
    stop_parser.add_argument("--target", type=Path, required=True)
    stop_parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    try:
        {"create": create, "restore": restore, "stop": stop}[args.action](args)
    except (RuntimeError, OSError, subprocess.CalledProcessError) as exc:
        print(json.dumps({"status": "failed", "error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
