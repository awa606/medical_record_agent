#!/usr/bin/env python3
"""Read-only preflight for the Alpha Jetson provider bring-up.

The script never installs packages, starts containers, or claims product acceptance.
On non-Jetson hardware it returns HARDWARE_BLOCKED with exit code 3.
"""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path


MIN_FREE_BYTES = 100 * 1024**3
EXPECTED_ARCHES = {"aarch64", "arm64"}
PLANNED_STAGES = [
    "identity_and_nvme",
    "jetpack_cuda",
    "docker_nvidia_runtime",
    "model_cache_manifest",
    "funasr_isolated_smoke",
    "asr_memory_release",
    "ollama_qwen_structured_smoke",
    "ollama_unload",
    "fastapi_health_and_readiness",
]


def run(command: list[str]) -> dict[str, object]:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=15, check=False)
        return {
            "command": command,
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"command": command, "returncode": None, "error": str(error)}


def is_jetson() -> tuple[bool, str]:
    arch = platform.machine().lower()
    tegra = Path("/etc/nv_tegra_release")
    return arch in EXPECTED_ARCHES and tegra.is_file(), arch


def dry_run() -> int:
    detected, arch = is_jetson()
    report = {
        "schema_version": "mra-alpha13-jetson-smoke-v1",
        "mode": "dry-run",
        "result": "READY_FOR_PREFLIGHT" if detected else "HARDWARE_BLOCKED",
        "hardware_detected": detected,
        "architecture": arch,
        "planned_stages": PLANNED_STAGES,
        "claims": {"jetson_pass": False, "provider_pass": False, "alpha_pass": False},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if detected else 3


def preflight(cache_root: Path) -> int:
    detected, arch = is_jetson()
    if not detected:
        print(json.dumps({
            "schema_version": "mra-alpha13-jetson-smoke-v1",
            "mode": "preflight",
            "result": "HARDWARE_BLOCKED",
            "hardware_detected": False,
            "architecture": arch,
            "reason": "Requires an aarch64 Jetson with /etc/nv_tegra_release",
            "claims": {"jetson_pass": False, "provider_pass": False, "alpha_pass": False},
        }, ensure_ascii=False, indent=2))
        return 3

    checks: dict[str, object] = {
        "architecture": {"ok": True, "value": arch},
        "tegra_release": {"ok": True, "value": Path("/etc/nv_tegra_release").read_text(encoding="utf-8").strip()},
        "jetpack_package": run(["dpkg-query", "--show", "nvidia-jetpack"]),
        "cuda": run(["nvcc", "--version"]) if shutil.which("nvcc") else {"returncode": None, "error": "nvcc not found"},
        "docker": run(["docker", "version", "--format", "{{json .Server}}"]),
        "compose": run(["docker", "compose", "version"]),
        "docker_runtimes": run(["docker", "info", "--format", "{{json .Runtimes}}"]),
    }
    cache_ok = cache_root.is_dir()
    free_bytes = shutil.disk_usage(cache_root).free if cache_ok else None
    checks["cache_root"] = {
        "ok": cache_ok and free_bytes is not None and free_bytes >= MIN_FREE_BYTES,
        "path": str(cache_root),
        "free_bytes": free_bytes,
        "minimum_free_bytes": MIN_FREE_BYTES,
    }
    command_checks = ["jetpack_package", "cuda", "docker", "compose", "docker_runtimes"]
    ok = all(checks[name].get("returncode") == 0 for name in command_checks) and checks["cache_root"]["ok"]
    report = {
        "schema_version": "mra-alpha13-jetson-smoke-v1",
        "mode": "preflight",
        "result": "PASS" if ok else "BLOCKED",
        "hardware_detected": True,
        "checks": checks,
        "next_stage": "docker_nvidia_runtime" if ok else None,
        "claims": {"jetson_pass": False, "provider_pass": False, "alpha_pass": False},
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--preflight", action="store_true")
    parser.add_argument("--cache-root", type=Path, default=Path("/srv/mra-alpha/model-cache"))
    args = parser.parse_args()
    return dry_run() if args.dry_run else preflight(args.cache_root)


if __name__ == "__main__":
    sys.exit(main())

