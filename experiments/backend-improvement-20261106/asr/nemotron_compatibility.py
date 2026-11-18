"""Isolated CPU compatibility Spike; never import production services or network."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import resource
import time
import wave


# Exact digest is checked against the independently recorded 2026-09-19 pair.
AUDIO_SHA = "e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4"
WEIGHT_SHA = "c074d86335b3b794f8fa5edc25594558f128bdb3914d27806a3a5a2e44963cb6"
RTTM_SHA = "3cb3a3cc9c9634b9b74e75a3abff039d944d11c92023ac9c4e8c6eebcc0c057b"


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--full-after-short", action="store_true")
    args = parser.parse_args()
    started = time.monotonic()
    result = {"scope": "isolated_compatibility_not_medical_role_validation", "cloud_calls": 0,
              "model_load_count": 0, "production_modified": False, "runs": []}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        if sha(args.base / "authorized_fever_60s.wav") != AUDIO_SHA:
            raise ValueError("unauthorized or changed input SHA")
        if sha(args.base / "model/model.safetensors") != WEIGHT_SHA:
            raise ValueError("weight SHA mismatch")
        import numpy as np
        import torch
        from transformers import AutoModelForAudioFrameClassification, AutoProcessor
        torch.set_num_threads(2)
        torch.set_num_interop_threads(1)
        with wave.open(str(args.base / "authorized_fever_60s.wav"), "rb") as wav:
            if wav.getnchannels() != 1 or wav.getframerate() != 16000 or wav.getsampwidth() != 2:
                raise ValueError("expected fixed 16 kHz mono PCM16 input")
            audio = np.frombuffer(wav.readframes(wav.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        load_started = time.monotonic()
        processor = AutoProcessor.from_pretrained(args.base / "model", local_files_only=True)
        model = AutoModelForAudioFrameClassification.from_pretrained(
            args.base / "model", local_files_only=True, dtype=torch.float32).eval()
        result["model_load_count"] = 1
        result["load_seconds"] = time.monotonic() - load_started
        processor.set_streaming_mode("low_latency")
        result["input_buffer_ms_excludes_compute"] = processor.streaming_latency_ms

        def run(seconds):
            source = audio[: int(seconds * 16000)]
            cache, logits, times = None, [], []
            chunks = []
            chunks.append(processor(source[:processor.num_samples_first_audio_chunk], sampling_rate=16000,
                                    is_streaming=True, is_first_audio_chunk=True))
            mel_idx = processor.num_mel_frames_per_step
            start_idx = processor.audio_chunk_start(mel_idx)
            while (end_idx := start_idx + processor.num_samples_per_audio_chunk) <= source.shape[0]:
                chunks.append(processor(source[start_idx:end_idx], sampling_rate=16000,
                                        is_streaming=True, is_first_audio_chunk=False))
                mel_idx += processor.num_mel_frames_per_step
                start_idx = processor.audio_chunk_start(mel_idx)
            chunks.append(processor(source[start_idx:], sampling_rate=16000, is_streaming=True,
                                    is_first_audio_chunk=False, is_last_audio_chunk=True))
            compute_start = time.monotonic()
            with torch.inference_mode():
                for inputs in chunks:
                    step = time.monotonic()
                    outputs = model(**inputs, speaker_cache=cache)
                    logits.append(outputs.logits)
                    cache = outputs.speaker_cache
                    times.append(time.monotonic() - step)
            elapsed = time.monotonic() - compute_start
            segments = processor.extract_speaker_dict(torch.cat(logits, dim=1))[0]
            return {"audio_seconds": seconds, "chunks": len(chunks), "seconds": elapsed,
                    "compute_only_rtf": elapsed / seconds, "chunk_compute_p95_seconds": float(np.percentile(times, 95)),
                    "capture_arrival_pacing_measured": False, "speaker_segments": segments,
                    "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024}

        result["runs"].append(run(10))
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        if args.full_after_short and time.monotonic() - started < 1200:
            result["runs"].append(run(60))
            rttm = args.base / "authorized_fever_60s.rttm"
            if sha(rttm) != RTTM_SHA:
                raise ValueError("matching archived RTTM changed")
            try:
                from pyannote.core import Annotation, Segment
                from pyannote.metrics.diarization import DiarizationErrorRate, JaccardErrorRate
                reference, hypothesis = Annotation(), Annotation()
                for index, line in enumerate(rttm.read_text(encoding="utf-8").splitlines()):
                    row = line.split()
                    reference[Segment(float(row[3]), float(row[3]) + float(row[4])), index] = row[7]
                for index, row in enumerate(result["runs"][-1]["speaker_segments"]):
                    hypothesis[Segment(row["Start"], row["End"]), index] = str(row["Speaker"])
                result["acoustic_metrics"] = {"der": DiarizationErrorRate(collar=0, skip_overlap=False)(reference, hypothesis),
                    "jer": JaccardErrorRate(collar=0, skip_overlap=False)(reference, hypothesis),
                    "collar_seconds": 0, "skip_overlap": False, "reference_rttm_sha256": RTTM_SHA,
                    "medical_role_accuracy": None, "patient_subject_accuracy": None}
            except ImportError as error:
                result["acoustic_metrics"] = {"der": None, "jer": None, "blocker": str(error)}
        result["status"] = "COMPATIBILITY_MEASURED_NOT_PRODUCT_PASS"
    except Exception as error:
        result["status"] = "FAILED_NO_RETRY"
        result["error_type"] = type(error).__name__
        result["error"] = str(error)[:500]
        raise
    finally:
        result["total_seconds"] = time.monotonic() - started
        result["peak_rss_mib"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
        args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({k: v for k, v in result.items() if k != "runs"}))


if __name__ == "__main__":
    main()
