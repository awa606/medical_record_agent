"""Collect a lightweight local hardware and model-dependency profile.

This script is intentionally read-only and does not download models or call
remote services. It is used as the v0.5 local benchmark baseline.
"""

from __future__ import annotations

import argparse
import ctypes
import importlib.util
import json
import os
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "hardware_profile.json"


def collect_hardware_profile() -> dict[str, Any]:
    torch_info = _torch_info()
    return {
        "schema_version": "v0.5.0",
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "purpose": "local_model_edge_benchmark_baseline",
        "privacy_note": "No local identity, API key, model weight path, or patient data is collected.",
        "system": {
            "os": platform.system(),
            "os_release": platform.release(),
            "os_version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_logical_cores": os.cpu_count(),
            "memory_total_gb": _total_memory_gb(),
        },
        "python": {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable_name": Path(sys.executable).name,
        },
        "gpu": {
            "torch_cuda_available": torch_info["cuda_available"],
            "cuda_device_count": torch_info["cuda_device_count"],
            "cuda_devices": torch_info["cuda_devices"],
            "nvidia_smi_available": shutil.which("nvidia-smi") is not None,
        },
        "dependencies": {
            "torch": torch_info,
            "funasr": _module_info("funasr"),
            "qwen_asr": _module_info("qwen_asr"),
            "whisper": _module_info("whisper"),
            "ffmpeg": {
                "available": shutil.which("ffmpeg") is not None,
                "version": None,
                "path_detected": shutil.which("ffmpeg") is not None,
            },
            "ollama_cli": {
                "available": shutil.which("ollama") is not None,
                "path_detected": shutil.which("ollama") is not None,
            },
            "ollama_env": {
                "OLLAMA_BASE_URL_configured": bool(os.environ.get("OLLAMA_BASE_URL")),
                "OLLAMA_MODEL_configured": bool(os.environ.get("OLLAMA_MODEL")),
            },
        },
        "benchmark_status": {
            "current_machine_role": "developer_baseline",
            "hospital_pc_profile": "pending_collection",
            "edge_device_profile": "pending_collection",
        },
    }


def write_hardware_profile(output_path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    profile = collect_hardware_profile()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
    return profile


def _module_info(module_name: str) -> dict[str, Any]:
    spec = importlib.util.find_spec(module_name)
    info: dict[str, Any] = {"available": spec is not None, "version": None}
    if spec is None:
        return info
    try:
        module = __import__(module_name)
        info["version"] = getattr(module, "__version__", None)
    except Exception as exc:  # noqa: BLE001 - dependency import failures are benchmark data.
        info["available"] = False
        info["error"] = _sanitize_local_paths(str(exc))[:200]
    return info


def _torch_info() -> dict[str, Any]:
    info = _module_info("torch")
    info.update(
        {
            "cuda_available": False,
            "cuda_device_count": 0,
            "cuda_devices": [],
        }
    )
    if not info["available"]:
        return info
    try:
        import torch

        cuda_available = bool(torch.cuda.is_available())
        device_count = int(torch.cuda.device_count()) if cuda_available else 0
        devices = [
            torch.cuda.get_device_name(index)
            for index in range(device_count)
        ]
        info.update(
            {
                "version": getattr(torch, "__version__", info.get("version")),
                "cuda_available": cuda_available,
                "cuda_device_count": device_count,
                "cuda_devices": devices,
            }
        )
    except Exception as exc:  # noqa: BLE001 - dependency import failures are benchmark data.
        info["error"] = _sanitize_local_paths(str(exc))[:200]
    return info


def _sanitize_local_paths(value: str) -> str:
    root = str(PROJECT_ROOT)
    return value.replace(root, "<PROJECT_ROOT>").replace(root.replace("\\", "/"), "<PROJECT_ROOT>")


def _total_memory_gb() -> float | None:
    if platform.system() == "Windows":
        return _windows_total_memory_gb()
    if hasattr(os, "sysconf"):
        try:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return round((pages * page_size) / (1024 ** 3), 2)
        except (OSError, ValueError):
            return None
    return None


def _windows_total_memory_gb() -> float | None:
    class MemoryStatus(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    try:
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(MemoryStatus)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
        return round(status.ullTotalPhys / (1024 ** 3), 2)
    except Exception:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Collect local hardware profile for v0.5 benchmark.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    profile = write_hardware_profile(args.output)
    print("硬件配置采集完成：")
    print(f"- OS: {profile['system']['os']} {profile['system']['os_release']}")
    print(f"- CPU logical cores: {profile['system']['cpu_logical_cores']}")
    print(f"- Memory GB: {profile['system']['memory_total_gb']}")
    print(f"- torch cuda available: {profile['gpu']['torch_cuda_available']}")
    print(f"- FunASR available: {profile['dependencies']['funasr']['available']}")
    print(f"- Qwen-ASR available: {profile['dependencies']['qwen_asr']['available']}")
    print(f"- Whisper available: {profile['dependencies']['whisper']['available']}")
    print(f"- ffmpeg available: {profile['dependencies']['ffmpeg']['available']}")
    print(f"- Output: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
