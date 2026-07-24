from __future__ import annotations

import os
from pathlib import Path
from typing import Any


RETRYABLE_CATEGORIES = {
    "dns_failure",
    "model_config_mismatch",
    "model_missing",
    "model_timeout",
    "audio_damaged",
    "dependency_missing",
    "model_load_failed",
}


def classify_funasr_error(error: BaseException | str) -> dict[str, Any]:
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    lowered = message.lower()
    category = "model_load_failed"

    if any(token in lowered for token in ("not registered", "registered model keys")):
        category = "model_config_mismatch"
    elif any(
        token in lowered
        for token in ("nameresolutionerror", "failed to resolve", "temporary failure in name resolution", "dns")
    ):
        category = "dns_failure"
    elif any(token in lowered for token in ("modelscope.cn", "huggingface.co", "hf_hub", "download")):
        category = "dns_failure"
    elif any(token in lowered for token in ("timeout", "timed out", "read timed out")):
        category = "model_timeout"
    elif any(token in lowered for token in ("no such file", "not found", "missing", "does not exist")):
        category = "model_missing"
    elif any(token in lowered for token in ("import failed", "no module named", "install requirements-asr")):
        category = "dependency_missing"
    elif any(token in lowered for token in ("ffmpeg audio decode failed", "invalid data", "could not find codec", "damaged")):
        category = "audio_damaged"

    return {
        "category": category,
        "retryable": category in RETRYABLE_CATEGORIES,
        "message": message[:500],
        "user_message": _user_message(category),
    }


def _user_message(category: str) -> str:
    return {
        "dns_failure": "FunASR 模型服务或模型缓存不可用，请检查网络 DNS，或预先挂载本地模型缓存后重试。",
        "model_config_mismatch": "FunASR 模型配置与当前依赖版本不匹配，请检查模型名称和本地模型缓存后重试。",
        "model_missing": "FunASR 本地模型缺失，请先下载模型并挂载模型缓存后重试。",
        "model_timeout": "FunASR 转写超时，本次任务已暂停，可重新转写或改用文本输入。",
        "audio_damaged": "音频文件无法解码，请重新录音或上传有效音频。",
        "dependency_missing": "FunASR 运行依赖缺失，请安装 ASR 依赖后重试。",
        "model_load_failed": "FunASR 转写服务暂时不可用，本次任务已暂停，可重新转写或改用文本输入。",
    }.get(category, "FunASR 转写服务暂时不可用，本次任务已暂停，可重新转写或改用文本输入。")


def _cache_min_file_count() -> int:
    try:
        value = int(os.environ.get("MEDICAL_RECORD_AGENT_FUNASR_CACHE_MIN_FILES", "5"))
    except ValueError:
        return 5
    return max(value, 1)


def funasr_cache_status() -> dict[str, Any]:
    paths = {
        "modelscope": Path(os.environ.get("MODELSCOPE_CACHE", Path.home() / ".cache" / "modelscope")),
        "hf": Path(os.environ.get("HF_HOME", Path.home() / ".cache" / "huggingface")),
        "torch": Path(os.environ.get("TORCH_HOME", Path.home() / ".cache" / "torch")),
    }
    entries: dict[str, Any] = {}
    total_files = 0
    for name, path in paths.items():
        exists = path.exists()
        file_count = 0
        if exists:
            try:
                file_count = sum(1 for item in path.rglob("*") if item.is_file())
            except OSError:
                file_count = -1
        if file_count > 0:
            total_files += file_count
        entries[name] = {
            "path": str(path),
            "exists": exists,
            "file_count": file_count,
        }
    min_file_count = _cache_min_file_count()
    return {
        "ok": True,
        "has_cached_files": total_files > 0,
        "has_required_cache": total_files >= min_file_count,
        "min_file_count": min_file_count,
        "total_file_count": total_files,
        "caches": entries,
    }


def funasr_failure_payload(error: BaseException | str) -> dict[str, Any]:
    classified = classify_funasr_error(error)
    return {
        "message": classified["user_message"],
        "error_category": classified["category"],
        "retryable": classified["retryable"],
        "technical_detail": classified["message"],
        "fallback_action": "text_input",
    }
