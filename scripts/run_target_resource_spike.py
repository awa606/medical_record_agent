"""Measure ASR/LLM resource feasibility without changing the product runtime.

The script is intended to run inside short-lived, memory-limited containers.  It
stores hashes and metrics rather than transcript or generated medical content.
It does not claim Jetson compatibility: CPU measurements on an x86 development
machine are only a conservative shared-memory screening experiment.
"""
from __future__ import annotations

import argparse
import http.cookiejar
import hashlib
import json
import math
import mimetypes
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from urllib import error, request


ROOT = Path(__file__).resolve().parents[1]
CGROUP = Path("/sys/fs/cgroup")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def read_int(path: Path) -> int | None:
    try:
        value = path.read_text(encoding="utf-8").strip()
        return None if value == "max" else int(value)
    except (FileNotFoundError, PermissionError, ValueError):
        return None


def read_events() -> dict[str, int]:
    path = CGROUP / "memory.events"
    try:
        return {
            key: int(value)
            for key, value in (line.split(maxsplit=1) for line in path.read_text().splitlines())
        }
    except (FileNotFoundError, PermissionError, ValueError):
        return {}


def rss_bytes() -> int | None:
    try:
        for line in Path("/proc/self/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
    except (FileNotFoundError, PermissionError, ValueError):
        pass
    return None


class MemorySampler:
    def __init__(self, interval: float = 1.0) -> None:
        self.interval = interval
        self.samples: list[dict[str, int | float | None]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _sample(self) -> None:
        self.samples.append(
            {
                "elapsed_seconds": round(time.monotonic() - self.started, 3),
                "process_rss_bytes": rss_bytes(),
                "cgroup_memory_current_bytes": read_int(CGROUP / "memory.current"),
                "cgroup_swap_current_bytes": read_int(CGROUP / "memory.swap.current"),
            }
        )

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            self._sample()

    def __enter__(self) -> "MemorySampler":
        self.started = time.monotonic()
        self._sample()
        self._thread.start()
        return self

    def __exit__(self, *_args: object) -> None:
        self._stop.set()
        self._thread.join(timeout=max(2.0, self.interval * 2))
        self._sample()

    def summary(self) -> dict[str, object]:
        def peak(key: str) -> int | None:
            values = [int(item[key]) for item in self.samples if item.get(key) is not None]
            return max(values) if values else None

        return {
            "sample_interval_seconds": self.interval,
            "sample_count": len(self.samples),
            "peak_process_rss_bytes": peak("process_rss_bytes"),
            "peak_cgroup_memory_current_bytes": peak("cgroup_memory_current_bytes"),
            "peak_cgroup_swap_current_bytes": peak("cgroup_swap_current_bytes"),
            "cgroup_memory_peak_bytes": read_int(CGROUP / "memory.peak"),
            "cgroup_memory_max_bytes": read_int(CGROUP / "memory.max"),
            "cgroup_memory_events": read_events(),
            "samples": self.samples,
        }


def common_metadata(mode: str) -> dict[str, object]:
    try:
        git_sha = subprocess.check_output(
            ["git", "-c", f"safe.directory={ROOT}", "rev-parse", "HEAD"],
            cwd=ROOT,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        git_sha = "unavailable"
    return {
        "schema_version": "mra-alpha12-resource-spike-v1",
        "mode": mode,
        "started_at": utc_now(),
        "git_sha": git_sha,
        "host_scope": "development PC x86_64 CPU container; not Jetson evidence",
        "python": platform.python_version(),
        "platform": platform.platform(),
        "machine": platform.machine(),
        "container_memory_max_bytes": read_int(CGROUP / "memory.max"),
        "container_swap_max_bytes": read_int(CGROUP / "memory.swap.max"),
    }


def write_result(path: Path, result: dict[str, object]) -> None:
    if path.exists():
        raise SystemExit(f"Refusing to overwrite existing output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")


def asr_mode(args: argparse.Namespace) -> int:
    from app.services.asr.funasr_engine import FunASREngine

    result = common_metadata("asr")
    inputs = [Path(value).resolve() for value in args.audio]
    for path in inputs:
        if not path.is_file():
            raise SystemExit(f"Audio does not exist: {path}")
    result["inputs"] = [
        {"input_id": f"audio-{index:02d}", "sha256": sha256(path), "bytes": path.stat().st_size}
        for index, path in enumerate(inputs, start=1)
    ]
    rows: list[dict[str, object]] = []
    before_events = read_events()
    sampler = MemorySampler(args.sample_interval)
    try:
        with sampler:
            load_started = time.perf_counter()
            engine = FunASREngine(
                device=args.device,
                enable_punctuation=True,
                enable_vad=True,
                enable_speaker_diarization=args.speaker_diarization,
            )
            result["model_load_seconds"] = round(time.perf_counter() - load_started, 3)
            for index, path in enumerate(inputs, start=1):
                started = time.perf_counter()
                row: dict[str, object] = {"input_id": f"audio-{index:02d}"}
                try:
                    asr = engine.transcribe(f"target-spike-{index:02d}", path)
                    elapsed = time.perf_counter() - started
                    duration = asr.duration or 0.0
                    row.update(
                        {
                            "success": True,
                            "elapsed_seconds": round(elapsed, 3),
                            "audio_duration_seconds": round(duration, 3),
                            "rtf": round(elapsed / duration, 4) if duration > 0 else None,
                            "text_sha256": hashlib.sha256(asr.text.encode("utf-8")).hexdigest(),
                            "text_characters": len(asr.text),
                            "segment_count": len(asr.segments),
                            "recognized_keyword_count": len(asr.medical_keywords.get("recognized", [])),
                        }
                    )
                except Exception as exc:  # evidence must preserve runtime failures
                    row.update(
                        {
                            "success": False,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        }
                    )
                rows.append(row)
    except Exception as exc:
        result["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}
    result["cases"] = rows
    result["memory"] = sampler.summary()
    result["memory_events_before"] = before_events
    result["memory_events_after"] = read_events()
    result["summary"] = {
        "input_count": len(inputs),
        "success_count": sum(bool(row.get("success")) for row in rows),
        "max_rtf": max((float(row["rtf"]) for row in rows if row.get("rtf") is not None), default=None),
        "oom_kill_delta": read_events().get("oom_kill", 0) - before_events.get("oom_kill", 0),
    }
    result["completed_at"] = utc_now()
    write_result(args.output, result)
    return 0 if result["summary"]["success_count"] == len(inputs) else 2


def json_request(url: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    req = request.Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    try:
        with request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def get_json(url: str, timeout: float = 10.0) -> dict[str, object]:
    with request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def asr_api_mode(args: argparse.Namespace) -> int:
    """Use the real FastAPI upload/transcribe path without generating a record."""
    result = common_metadata("asr-api")
    inputs = [Path(value).resolve() for value in args.audio]
    password = os.getenv(args.password_env)
    if not password:
        raise SystemExit(f"Required password environment variable is empty: {args.password_env}")
    opener = request.build_opener(request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(
        method: str,
        path: str,
        data: dict[str, object] | None = None,
        *,
        body: bytes | None = None,
        content_type: str = "application/json",
        timeout: float = 600.0,
    ) -> tuple[int, dict[str, object] | str]:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8") if data is not None else body
        req = request.Request(
            args.base_url.rstrip("/") + path,
            method=method,
            data=payload,
            headers={"Content-Type": content_type},
        )
        try:
            with opener.open(req, timeout=timeout) as response:
                status, raw = response.status, response.read()
        except error.HTTPError as exc:
            status, raw = exc.code, exc.read()
        try:
            return status, json.loads(raw.decode("utf-8"))
        except ValueError:
            return status, raw.decode("utf-8", errors="replace")

    code, _ = call("POST", "/api/auth/login", {"username": args.username, "password": password})
    if code != 200:
        raise SystemExit(f"FastAPI login failed: HTTP {code}")
    ready_code, ready = call("GET", "/api/asr/prewarm/status")
    result["readiness"] = {"http": ready_code, "payload": ready}
    rows: list[dict[str, object]] = []
    for index, path in enumerate(inputs, start=1):
        if not path.is_file():
            raise SystemExit(f"Audio does not exist: {path}")
        raw = path.read_bytes()
        boundary = f"MRAResourceSpike{uuid.uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode() + raw + f"\r\n--{boundary}--\r\n".encode()
        row: dict[str, object] = {
            "input_id": f"audio-{index:02d}",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
        started = time.perf_counter()
        try:
            upload_code, uploaded = call(
                "POST",
                "/api/audio/upload",
                body=body,
                content_type=f"multipart/form-data; boundary={boundary}",
            )
            if upload_code != 200 or not isinstance(uploaded, dict):
                raise RuntimeError(f"upload HTTP {upload_code}: {str(uploaded)[:300]}")
            transcribe_code, transcribed = call(
                "POST", f'/api/audio/{uploaded["audio_id"]}/transcribe?engine=funasr'
            )
            if transcribe_code != 200 or not isinstance(transcribed, dict):
                raise RuntimeError(f"transcribe HTTP {transcribe_code}: {str(transcribed)[:300]}")
            asr_payload = transcribed.get("asr_result", {})
            text = str(asr_payload.get("text") or transcribed.get("text") or "")
            duration = float(asr_payload.get("duration") or 0.0)
            processing = float(transcribed.get("processing_duration_seconds") or 0.0)
            row.update(
                {
                    "success": bool(text.strip()),
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "processing_seconds": round(processing, 3),
                    "audio_duration_seconds": round(duration, 3),
                    "rtf": round(processing / duration, 4) if duration > 0 else None,
                    "engine": transcribed.get("model") or asr_payload.get("engine"),
                    "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                    "text_characters": len(text),
                    "segment_count": len(asr_payload.get("segments", [])),
                }
            )
        except Exception as exc:
            row.update(
                {
                    "success": False,
                    "elapsed_seconds": round(time.perf_counter() - started, 3),
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:500],
                }
            )
        rows.append(row)
    result["inputs"] = [
        {key: row[key] for key in ("input_id", "sha256", "bytes")} for row in rows
    ]
    result["cases"] = rows
    result["summary"] = {
        "input_count": len(rows),
        "success_count": sum(bool(row.get("success")) for row in rows),
        "max_rtf": max((float(row["rtf"]) for row in rows if row.get("rtf") is not None), default=None),
    }
    result["completed_at"] = utc_now()
    write_result(args.output, result)
    return 0 if result["summary"]["success_count"] == len(rows) else 2


def llm_mode(args: argparse.Namespace) -> int:
    from app.schemas import MedicalRecordFields
    from app.services.llm.ollama_provider import extraction_schema, numbered_source
    from app.prompts.medical_record_prompts import MEDICAL_RECORD_SYSTEM_PROMPT
    from app.services.privacy import anonymize_text

    result = common_metadata("llm")
    cases = sorted((ROOT / args.cases_dir).glob("*.json"))[: args.count]
    if len(cases) < args.count:
        raise SystemExit(f"Requested {args.count} cases but found {len(cases)}")
    result["configuration"] = {
        "model": args.model,
        "base_url": args.base_url,
        "num_ctx": args.num_ctx,
        "num_predict": args.num_predict,
        "keep_alive": args.keep_alive,
        "timeout_seconds": args.timeout,
        "temperature": 0,
        "think": False,
    }
    result["inputs"] = [
        {"case_id": path.stem, "sha256": sha256(path), "synthetic": True} for path in cases
    ]
    try:
        tags = get_json(f"{args.base_url.rstrip('/')}/api/tags")
        model_rows = tags.get("models", []) if isinstance(tags, dict) else []
        selected = next(
            (row for row in model_rows if row.get("name") == args.model or row.get("model") == args.model),
            None,
        )
        result["model_metadata"] = {
            key: selected.get(key) for key in ("name", "model", "size", "digest", "modified_at")
        } if selected else {"available": False}
    except Exception as exc:
        result["model_metadata_error"] = f"{type(exc).__name__}: {str(exc)[:300]}"

    rows: list[dict[str, object]] = []
    before_events = read_events()
    sampler = MemorySampler(args.sample_interval)
    try:
        with sampler:
            for path in cases:
                case = json.loads(path.read_text(encoding="utf-8"))
                if not case.get("privacy", {}).get("synthetic"):
                    raise RuntimeError(f"Non-synthetic case rejected: {path.name}")
                conversation = "\n".join(
                    f'{segment["role"]}：{segment["text"]}' for segment in case["segments"]
                )
                payload = {
                    "model": args.model,
                    "stream": False,
                    "think": False,
                    "format": extraction_schema(),
                    "messages": [
                        {"role": "system", "content": MEDICAL_RECORD_SYSTEM_PROMPT},
                        {"role": "user", "content": numbered_source(anonymize_text(conversation))},
                    ],
                    "options": {
                        "temperature": 0,
                        "num_ctx": args.num_ctx,
                        "num_predict": args.num_predict,
                    },
                    "keep_alive": args.keep_alive,
                }
                started = time.perf_counter()
                row: dict[str, object] = {"case_id": case["case_id"], "input_sha256": sha256(path)}
                try:
                    data = json_request(f"{args.base_url.rstrip('/')}/api/chat", payload, args.timeout)
                    content = data.get("message", {}).get("content") if isinstance(data.get("message"), dict) else None
                    parsed = json.loads(content) if isinstance(content, str) else None
                    fields_payload = parsed.get("fields", parsed) if isinstance(parsed, dict) else parsed
                    fields = MedicalRecordFields.model_validate(fields_payload)
                    row.update(
                        {
                            "success": True,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "output_sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                            "nonempty_field_count": sum(
                                not getattr(fields, key).missing and bool(getattr(fields, key).value)
                                for key in (
                                    "chief_complaint", "present_illness", "previous_treatment",
                                    "accompanying_symptoms", "past_history", "allergy_history", "physical_exam",
                                )
                            ),
                            "done_reason": data.get("done_reason"),
                            "load_duration_ns": data.get("load_duration"),
                            "prompt_eval_duration_ns": data.get("prompt_eval_duration"),
                            "eval_duration_ns": data.get("eval_duration"),
                        }
                    )
                except Exception as exc:
                    row.update(
                        {
                            "success": False,
                            "elapsed_seconds": round(time.perf_counter() - started, 3),
                            "error_type": type(exc).__name__,
                            "error": str(exc)[:500],
                        }
                    )
                rows.append(row)
    except Exception as exc:
        result["fatal_error"] = {"type": type(exc).__name__, "message": str(exc)[:500]}

    unload_started = time.monotonic()
    unload_requested = False
    unloaded = False
    unload_error = None
    try:
        json_request(
            f"{args.base_url.rstrip('/')}/api/generate",
            {"model": args.model, "keep_alive": 0},
            min(30.0, args.timeout),
        )
        unload_requested = True
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            running = get_json(f"{args.base_url.rstrip('/')}/api/ps").get("models", [])
            if not any(row.get("name") == args.model or row.get("model") == args.model for row in running):
                unloaded = True
                break
            time.sleep(1)
    except Exception as exc:
        unload_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    result["cases"] = rows
    result["memory"] = sampler.summary()
    result["memory_events_before"] = before_events
    result["memory_events_after"] = read_events()
    latencies = [float(row["elapsed_seconds"]) for row in rows]
    result["summary"] = {
        "case_count": len(cases),
        "schema_valid_count": sum(bool(row.get("success")) for row in rows),
        "failed_count": sum(not bool(row.get("success")) for row in rows),
        "p95_seconds": percentile(latencies, 0.95),
        "max_seconds": max(latencies, default=None),
        "mock_fallback_count": 0,
        "unload_requested": unload_requested,
        "unloaded_within_30_seconds": unloaded,
        "unload_seconds": round(time.monotonic() - unload_started, 3),
        "unload_error": unload_error,
        "oom_kill_delta": read_events().get("oom_kill", 0) - before_events.get("oom_kill", 0),
    }
    result["completed_at"] = utc_now()
    write_result(args.output, result)
    return 0 if result["summary"]["schema_valid_count"] == len(cases) and unloaded else 2


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)

    asr = sub.add_parser("asr", help="Run three local audio files through FunASR")
    asr.add_argument("--audio", action="append", required=True)
    asr.add_argument("--output", type=Path, required=True)
    asr.add_argument("--device", default="cpu")
    asr.add_argument("--speaker-diarization", action="store_true")
    asr.add_argument("--sample-interval", type=float, default=1.0)
    asr.set_defaults(func=asr_mode)

    asr_api = sub.add_parser("asr-api", help="Call the real FastAPI upload/transcribe path")
    asr_api.add_argument("--base-url", default="http://127.0.0.1:2780")
    asr_api.add_argument("--username", default="admin")
    asr_api.add_argument("--password-env", default="MRA_LOOP_ADMIN_PASSWORD")
    asr_api.add_argument("--audio", action="append", required=True)
    asr_api.add_argument("--output", type=Path, required=True)
    asr_api.set_defaults(func=asr_api_mode)

    llm = sub.add_parser("llm", help="Run synthetic transcripts through a structured Ollama call")
    llm.add_argument("--base-url", default="http://ollama:11434")
    llm.add_argument("--model", default="qwen3:4b")
    llm.add_argument("--cases-dir", default="data/clinical_e2e/field_disease_pack_v1/cases")
    llm.add_argument("--count", type=int, default=10)
    llm.add_argument("--num-ctx", type=int, default=2048)
    llm.add_argument("--num-predict", type=int, default=512)
    llm.add_argument("--keep-alive", default="0")
    llm.add_argument("--timeout", type=float, default=300.0)
    llm.add_argument("--output", type=Path, required=True)
    llm.add_argument("--sample-interval", type=float, default=1.0)
    llm.set_defaults(func=llm_mode)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
