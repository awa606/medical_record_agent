"""Replay a verified real FunASR result through the role gate and local LLM.

The WAV, transcript, database and complete task response stay in --output-dir.
Only the redacted summary is suitable for review or Git. This does not rerun ASR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import shutil
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path


FROZEN_CASES = {
    "fever_60s": {
        "audio_sha256": "e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4",
        "asr_sha256": "d7425b09008d846fc892c8bac9210d4122c4b71af8c25b83f65bc69a2fb9c271",
        "speaker_roles": {"spk0": "患者", "spk1": "医生"},
    },
    "fever_full": {
        "audio_sha256": "93291c6894de5bcb7945af4f456e1ab3402fb8a78f60b5c00bfbc7185c8c414d",
        "asr_sha256": "c3c369967b16d23f2020dc80d9e531a5d6221e42222a81b2581a95c3354db886",
        "speaker_roles": {"spk1": "医生", "spk2": "患者"},
    },
}
FIELD_NAMES = (
    "chief_complaint",
    "present_illness",
    "previous_treatment",
    "accompanying_symptoms",
    "past_history",
    "allergy_history",
    "physical_exam",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=FROZEN_CASES, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--asr-result", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11500")
    parser.add_argument("--excerpt-end", type=int, default=None, help="Optional seconds from start of frozen full audio")
    args = parser.parse_args()
    audio_sha = sha256(args.audio)
    asr_sha = sha256(args.asr_result)
    frozen = FROZEN_CASES[args.case]
    if (audio_sha, asr_sha) != (frozen["audio_sha256"], frozen["asr_sha256"]):
        parser.error("Input SHA256 does not match the frozen real-audio evidence")
    if args.excerpt_end is not None and (args.case != "fever_full" or not 30 <= args.excerpt_end <= 300):
        parser.error("An excerpt is only supported for the frozen full fever recording (30-300 s)")
    if args.output_dir.exists():
        parser.error("Output directory already exists; refusing to overwrite evidence")
    output = args.output_dir.resolve()
    output.mkdir(parents=True)
    private = output / "private"
    runtime = private / "runtime"
    uploads = runtime / "uploads"
    exports = runtime / "outputs"
    profiles = runtime / "speaker-profiles"
    for folder in (uploads, exports, profiles):
        folder.mkdir(parents=True, exist_ok=True)
    if args.excerpt_end is None:
        shutil.copy2(args.audio, private / "source.wav")
        shutil.copy2(args.asr_result, private / "real_funasr_result.json")
    else:
        with wave.open(str(args.audio), "rb") as source:
            with wave.open(str(private / "source.wav"), "wb") as target:
                target.setparams(source.getparams())
                target.writeframes(source.readframes(args.excerpt_end * source.getframerate()))
        original = json.loads(args.asr_result.read_text(encoding="utf-8"))
        segments = [
            item for item in original["segments"]
            if item.get("start_time") is not None and item.get("end_time") is not None
            and 0 <= item["start_time"] < item["end_time"] <= args.excerpt_end
        ]
        original.update(
            {
                "audio_id": f"fever_01_0_{args.excerpt_end}",
                "text": "".join(item["text"] for item in segments),
                "conversation_text": "\n".join(f"[{item.get('speaker') or item.get('speaker_id')}] {item['text']}" for item in segments),
                "segments": segments,
                "diarization_turns": [
                    item for item in original.get("diarization_turns", [])
                    if item.get("start_time") is not None and item.get("end_time") is not None
                    and 0 <= item["start_time"] < item["end_time"] <= args.excerpt_end
                ],
                "duration": float(args.excerpt_end),
                "medical_keywords": {},
            }
        )
        (private / "real_funasr_result.json").write_text(
            json.dumps(original, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    password = secrets.token_urlsafe(32)
    os.environ.update(
        {
            "MEDICAL_RECORD_AGENT_DB": str(runtime / "mra.sqlite3"),
            "MEDICAL_RECORD_AGENT_UPLOAD_DIR": str(uploads),
            "MEDICAL_RECORD_AGENT_OUTPUT_DIR": str(exports),
            "MEDICAL_RECORD_AGENT_SPEAKER_PROFILE_DIR": str(profiles),
            "MEDICAL_RECORD_AGENT_BOOTSTRAP_ADMIN_PASSWORD": password,
            "RECORD_PROVIDER_MODE": "edge",
            "MEDICAL_RECORD_AGENT_ASR_ENGINE": "funasr",
            "ASR_ENGINE": "funasr",
            "LLM_PROVIDER": "ollama",
            "OLLAMA_BASE_URL": args.ollama_url,
            "OLLAMA_MODEL": "qwen3:4b",
            "LLM_TIMEOUT_SECONDS": "180",
            "LLM_MAX_RETRIES": "0",
            "ASR_PREWARM_ENABLED": "0",
            "MRA_ANONYMIZE": "1",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
        }
    )
    repo = Path(__file__).resolve().parents[1]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from fastapi.testclient import TestClient

    from app.api.asr_sessions import _read_events, _read_session, _write_session, _write_session_result
    from app.api.audio import _write_transcript
    from app.main import app
    from app.schemas import ASRResult
    from app.services.asr.auto_roles import ensure_automatic_speaker_roles

    summary: dict[str, object] = {
        "schema_version": "alpha32-real-dual-replay-v1",
        "case": args.case,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "git_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
        "input": {
            "audio_sha256": audio_sha,
            "funasr_result_sha256": asr_sha,
            "asr_rerun": False,
            "excerpt_end_seconds": args.excerpt_end,
            "replayed_audio_sha256": sha256(private / "source.wav"),
            "replayed_result_sha256": sha256(private / "real_funasr_result.json"),
        },
        "configuration": {"mode": "edge", "asr": "funasr-replayed-real-result", "llm": "ollama/qwen3:4b", "mock_or_cloud_fallback_allowed": False},
    }
    start = time.perf_counter()
    try:
        with TestClient(app) as client:
            login = client.post("/api/auth/login", json={"username": "admin", "password": password})
            login.raise_for_status()
            with (private / "source.wav").open("rb") as stream:
                upload = client.post(
                    "/api/audio/upload?recognition_mode=follow",
                    files={"file": ("source.wav", stream, "audio/wav")},
                )
            upload.raise_for_status()
            audio_id = upload.json()["audio_id"]
            session = client.post(
                "/api/asr/sessions?engine=funasr&diarization_engine=funasr_campp&recognition_mode=follow"
            )
            session.raise_for_status()
            session_id = session.json()["session_id"]
            stored = _read_session(session_id)
            _write_session(
                stored.model_copy(update={"audio_id": audio_id, "filename": "source.wav", "status": "completed", "recognition_mode": "follow"})
            )
            result = ASRResult.model_validate_json((private / "real_funasr_result.json").read_text(encoding="utf-8"))
            result = ensure_automatic_speaker_roles(
                result.model_copy(update={"audio_id": audio_id, "backend": "funasr", "model": "funasr-paraformer-zh", "recognition_mode": "follow"})
            )
            _write_session_result(session_id, result)
            _write_transcript(result)
            before = client.post(f"/api/audio/{audio_id}/generate-record")
            summary["pre_review"] = {
                "generate_http": before.status_code,
                "role_quality": result.role_quality.status if result.role_quality else None,
                "speaker_count": len({s.speaker_id for s in result.segments if s.speaker_id}),
            }
            if before.status_code != 409:
                raise AssertionError("Unconfirmed speaker roles did not block generation")
            patch = client.patch(
                f"/api/asr/sessions/{session_id}/result",
                json={
                    "speaker_roles": [
                        {"speaker_id": speaker, "role": role, "reviewed_by_doctor": True}
                        for speaker, role in frozen["speaker_roles"].items()
                    ],
                    "reviewer": "alpha32_anonymous_verifier",
                    "note": "Isolated WBS 3.2 real-ASR replay",
                },
            )
            patch.raise_for_status()
            reviewed = ASRResult.model_validate(patch.json()["asr_result"])
            events = _read_events(session_id)
            summary["post_review"] = {
                "patch_http": patch.status_code,
                "role_quality": reviewed.role_quality.status if reviewed.role_quality else None,
                "pending_count": len(reviewed.role_quality.pending_confirmation) if reviewed.role_quality else None,
                "role_reviewed_events": sum(e.event == "role_reviewed" for e in events),
            }
            if summary["post_review"]["role_quality"] != "passed":
                raise AssertionError("Role quality did not pass after manual speaker mapping")
            generated = client.post(f"/api/audio/{audio_id}/generate-record")
            summary["generation_http"] = generated.status_code
            generated.raise_for_status()
            task_id = generated.json()["task_id"]
            task_response = client.get(f"/api/tasks/{task_id}")
            task_response.raise_for_status()
            task = task_response.json()
            trace_response = client.get(f"/api/tasks/{task_id}/trace?audio_id={audio_id}")
            trace_response.raise_for_status()
            (private / "task.json").write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
            (private / "trace.json").write_text(json.dumps(trace_response.json(), ensure_ascii=False, indent=2), encoding="utf-8")
            payload = task.get("result_json") or {}
            fields = payload.get("fields") or {}
            field_status = {
                name: {
                    "status": field.get("status"),
                    "missing": field.get("missing"),
                    "nonempty": bool(field.get("value")),
                    "span_count": len(field.get("source_spans") or []),
                }
                for name in FIELD_NAMES
                if isinstance(field := fields.get(name), dict)
            }
            llm_trace = payload.get("llm_trace") or {}
            summary["result"] = {
                "task_status": task.get("status"),
                "draft_present": bool(payload.get("draft")),
                "safety_blocked": (payload.get("safety_check") or {}).get("blocked"),
                "candidate_count": len(fields.get("candidate_diagnoses") or []),
                "field_status": field_status,
                "llm_provider": llm_trace.get("actual_provider") or llm_trace.get("provider"),
                "llm_model": llm_trace.get("actual_model") or llm_trace.get("model"),
                "llm_fallback": llm_trace.get("fallback"),
                "private_task_sha256": sha256(private / "task.json"),
                "private_trace_sha256": sha256(private / "trace.json"),
            }
            if task.get("status") == "FAILED":
                summary["failure"] = {"type": "TaskFailed", "stage": "field_extraction"}
            elif task.get("status") != "WAITING_DOCTOR_REVIEW" or not payload.get("draft"):
                summary["failure"] = {"type": "IncompleteDraft", "stage": "draft_generation"}
            elif (payload.get("safety_check") or {}).get("blocked"):
                summary["semantic_gate"] = "PARTIAL_FIELD_CONFLICT"
            elif not any(item.get("nonempty") for item in field_status.values()):
                summary["semantic_gate"] = "PARTIAL_EMPTY_FIELDS"
            else:
                summary["semantic_gate"] = "DRAFT_CREATED_NEEDS_ACCEPTANCE_REVIEW"
    except Exception as exc:
        summary["failure"] = {"type": type(exc).__name__, "stage": "role_or_generation"}
        (private / "failure.txt").write_text(repr(exc), encoding="utf-8")
    summary["elapsed_seconds"] = round(time.perf_counter() - start, 3)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if "failure" in summary else 0


if __name__ == "__main__":
    sys.exit(main())
