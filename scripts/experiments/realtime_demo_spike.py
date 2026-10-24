"""Offline, real-paced 10s/2s ASR comparison; never a microphone acceptance test.

Run only after the coordinator has reserved a single-model resource window.
The default is a resource/input preflight: --execute is required to load ASR.
No production HTTP, SQLite, cloud inference or automatic retry is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
import wave


AUDIO_SHA256 = "e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4"
MODEL_SHA256 = "4fdfb48ed4471777c9a511e96a2acae17f77cac9d709cc756634622769192a64"
BUDGET = {"process_peak_rss_mib_max": 5120, "linux_available_mib_min": 2048,
          "wall_seconds_max": 420, "backlog_seconds_max": 15}
TARGETS = {"first_returned_text_seconds_max": 4,
           "stable_chunk_latency_p95_seconds_max": 5, "processing_rtf_max_exclusive": 1,
           "missing_duplicate_out_of_order_chunks_max": 0}


def resource_violation(memory: dict, *, before_new_model: bool = False) -> str | None:
    # Before loading another model, require the entire registered allocation
    # plus the minimum free-memory reserve. Existing processes are never killed.
    reserve = BUDGET["linux_available_mib_min"]
    if before_new_model:
        reserve += max(0, BUDGET["process_peak_rss_mib_max"] - memory["process_peak_rss_mib"])
    if memory["linux_available_mib"] < reserve:
        return "SPIKE_AVAILABLE_MEMORY_LOW"
    if memory["process_peak_rss_mib"] > BUDGET["process_peak_rss_mib_max"]:
        return "SPIKE_PROCESS_PEAK_EXCEEDED"
    return None


def memory_state() -> dict:
    import resource
    available = next(int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
                     if line.startswith("MemAvailable:"))
    return {"linux_available_mib": round(available / 1024, 2),
            "process_peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 2)}


def check_memory(*, before_new_model: bool = False) -> dict:
    state = memory_state()
    reason = resource_violation(state, before_new_model=before_new_model)
    if reason:
        raise RuntimeError(reason + ": " + json.dumps(state))
    return state


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def arm_summary(chunks: list[dict], first_text: float | None, duration: float) -> dict:
    delays = sorted(row["chunk_end_latency_seconds"] for row in chunks)
    p95 = delays[max(0, math.ceil(len(delays) * 0.95) - 1)] if delays else None
    sequences = [row["sequence"] for row in chunks]
    ordered = sequences == list(range(len(chunks)))
    rtf = sum(row["processing_seconds"] for row in chunks) / duration if duration else None
    return {"first_returned_text_seconds": first_text, "chunk_end_latency_p95_seconds": p95,
            "processing_rtf": rtf, "input_sequence_integrity": ordered,
            "engineering_targets_met": bool(first_text is not None and first_text <= 4
                                            and p95 is not None and p95 <= 5
                                            and rtf is not None and rtf < 1 and ordered),
            "browser_sse_delivery": "NOT_TESTED", "physical_microphone": "NOT_TESTED",
            "cer": "NOT_TESTED", "role_accuracy": "NOT_TESTED"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="New directory; existing runs are never overwritten")
    parser.add_argument("--repo-root", default=Path("/app"), type=Path)
    parser.add_argument("--execute", action="store_true", help="Load ASR after preflight; default only inspects resources")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {"protocol_version": "realtime-demo-20261019-r1", "resource_budget": BUDGET,
              "research_targets_not_formal_role_gate": TARGETS, "arms": [], "status": "PREFLIGHT",
              "network_attempts": [], "production_modified": False, "automatic_retries": 0,
              "role_policy": "Unresolved streaming roles stay unresolved; no hindsight label backfill."}

    def save():
        (args.output / "result.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    def emit(kind, value):
        print(json.dumps({"kind": kind, **value}, ensure_ascii=False), flush=True)

    try:
        if not sys.platform.startswith("linux"):
            raise RuntimeError("SPIKE_REQUIRES_LINUX_RESOURCE_ACCOUNTING")
        for key in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "MODELSCOPE_OFFLINE"):
            os.environ[key] = "1"
        os.environ["RECORD_PROVIDER_MODE"] = "edge"
        os.environ["MRA_ANONYMIZE"] = "0"  # Fixed authorized synthetic WAV; no identity-map I/O.

        def offline_guard(event, _args):
            if event in {"socket.connect", "socket.getaddrinfo", "socket.sendto"}:
                report["network_attempts"].append(event)
                raise RuntimeError("SPIKE_NETWORK_FORBIDDEN: " + event)
            if event == "sqlite3.connect":
                raise RuntimeError("SPIKE_DATABASE_FORBIDDEN")
        sys.addaudithook(offline_guard)
        report["input_sha256"] = sha256(args.audio)
        report["model_weight_sha256"] = sha256(args.model_dir / "model.pt")
        if report["input_sha256"] != AUDIO_SHA256 or report["model_weight_sha256"] != MODEL_SHA256:
            raise RuntimeError("SPIKE_INPUT_OR_MODEL_HASH_MISMATCH")
        with wave.open(str(args.audio), "rb") as audio:
            params = audio.getparams()
            if (params.nchannels, params.framerate, params.sampwidth) != (1, 16000, 2):
                raise RuntimeError("SPIKE_AUDIO_FORMAT_MISMATCH")
            pcm = audio.readframes(params.nframes)
        duration = params.nframes / params.framerate
        report["audio_seconds"] = duration
        report["memory_before_new_model"] = check_memory(before_new_model=True)
        if not args.execute:
            report["status"] = "PREFLIGHT_PASSED_MODEL_NOT_LOADED"
            return 0

        import signal
        def timed_out(*_args):
            raise TimeoutError("SPIKE_WALL_LIMIT_420S")
        signal.signal(signal.SIGALRM, timed_out)
        signal.alarm(BUDGET["wall_seconds_max"])
        sys.path.insert(0, str(args.repo_root))
        from app.services.asr.funasr_streaming_engine import FunASRStreamingEngine
        import numpy as np
        report["memory_after_import"] = check_memory()
        loading = time.perf_counter()
        engine = FunASRStreamingEngine(model_id=str(args.model_dir), device="cpu")
        report["load_seconds"] = time.perf_counter() - loading
        report["stream_config"] = vars(engine.config)
        report["memory_after_load"] = check_memory()
        warmup = time.perf_counter()
        engine.model.generate(input=np.zeros(engine.config.chunk_samples, dtype=np.float32), cache={}, is_final=True,
                              chunk_size=list(engine.config.chunk_size), encoder_chunk_look_back=engine.config.encoder_chunk_look_back,
                              decoder_chunk_look_back=engine.config.decoder_chunk_look_back)
        report["warmup_seconds"] = time.perf_counter() - warmup
        check_memory()
        save()
        for interval in (10, 2):
            arm = {"chunk_seconds": interval, "chunks": [], "stable_texts": []}
            report["arms"].append(arm)
            session = engine.create_live_chunk_session(f"spike-20261019-{interval}s")
            paths = []
            for sequence, start in enumerate(range(0, params.nframes, interval * params.framerate)):
                end = min(start + interval * params.framerate, params.nframes)
                path = args.output / f"chunk-{interval}-{sequence}.wav"
                with wave.open(str(path), "wb") as chunk:
                    chunk.setnchannels(1)
                    chunk.setsampwidth(2)
                    chunk.setframerate(params.framerate)
                    chunk.writeframes(pcm[start * 2:end * 2])
                paths.append((sequence, start / params.framerate, end / params.framerate, path))
            arm_start = time.perf_counter()
            first_text = None
            for sequence, start, end, path in paths:
                available_at = arm_start + end
                time.sleep(max(0, available_at - time.perf_counter()))
                resource_state = check_memory()
                call_started = time.perf_counter()
                events = session.transcribe_chunk(path, sequence=sequence,
                    chunk_started_at_ms=round(start * 1000), chunk_ended_at_ms=round(end * 1000))
                returned = time.perf_counter()
                if any(segment.text for _, segment, _ in events) and first_text is None:
                    first_text = returned - arm_start
                if any(segment.role is not None for _, segment, _ in events):
                    raise RuntimeError("SPIKE_UNEXPECTED_STREAMING_ROLE")
                stable = [segment.text for kind, segment, _ in events if kind == "transcript.stable"]
                row = {"sequence": sequence, "audio_start_seconds": start, "audio_end_seconds": end,
                       "queue_wait_seconds": max(0, call_started - available_at),
                       "processing_seconds": returned - call_started,
                       "chunk_end_latency_seconds": returned - available_at,
                       "stable_text": "".join(stable), "events": len(events), "memory_before_chunk": resource_state}
                arm["chunks"].append(row)
                arm["stable_texts"].extend(stable)
                emit("chunk", {"arm_seconds": interval, **row})
                save()
                check_memory()
                if row["chunk_end_latency_seconds"] > BUDGET["backlog_seconds_max"]:
                    raise RuntimeError("SPIKE_BACKLOG_EXCEEDED")
            arm.update(arm_summary(arm["chunks"], first_text, duration))
            arm["combined_stable_text"] = "".join(arm["stable_texts"])
            arm["memory_after_arm"] = check_memory()
            save()
        report["status"] = "COMPLETED_ENGINEERING_SPIKE_NOT_PRODUCT_ACCEPTANCE"
        signal.alarm(0)
        return 0
    except BaseException as exc:
        report["status"] = "STOPPED"
        report["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        emit("failure", report["failure"])
        return 2
    finally:
        save()
        emit("finished", {"status": report["status"], "output": str(args.output)})


if __name__ == "__main__":
    raise SystemExit(main())
