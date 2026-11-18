"""Offline adapters for a shadow streaming experiment; never calls a model.

Raw logs belong in .artifacts. This module has no production/API integration.
Both audio and observation time must use one capture-relative monotonic clock.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
from pathlib import Path
import sys


UNKNOWN_SPEAKERS = {None, "", "streaming", "asr", "unknown"}
ROLES = {"医生", "患者", "家属", "其他"}
TRUTH_KINDS = {"human_reviewed_rttm", "official_dataset_rttm"}


def _number(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}: finite numeric value required")
    return float(value)


class EventLedger:
    """Keep observed history; a later role assignment cannot rewrite latency."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.latest = {}
        self.history = []
        self.duplicates = 0
        self.stale = 0
        self._last_observed_ms = -1.0

    def add(self, event: dict) -> str:
        if event.get("session_id") != self.session_id:
            raise ValueError("cross-session event rejected")
        if event.get("clock") != "capture_relative_monotonic_ms":
            raise ValueError("capture-relative common clock required; do not subtract server epoch")
        observed = _number(event.get("observed_ms"), "observed_ms")
        if observed < self._last_observed_ms or observed < 0:
            raise ValueError("observation clock moved backwards")
        segment = event.get("segment", {})
        segment_id, revision = segment.get("segment_id"), segment.get("revision")
        if not isinstance(segment_id, str) or not segment_id:
            raise ValueError("segment_id required")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise ValueError("positive integer revision required")
        start = _number(segment.get("start_time"), "start_time")
        end = _number(segment.get("end_time"), "end_time")
        if start < 0 or end <= start or observed < end * 1000:
            raise ValueError("invalid interval or future audio")
        if not isinstance(segment.get("text"), str) or not isinstance(segment.get("provisional"), bool):
            raise ValueError("text/provisional required")
        if not (segment.get("speaker_id") is None or isinstance(segment.get("speaker_id"), str)):
            raise ValueError("speaker_id must be a string or null")
        if not (segment.get("role") is None or isinstance(segment.get("role"), str)) or segment.get("role") not in ROLES | {None}:
            raise ValueError("unknown clinical role; preserve unknown as null")
        if not (segment.get("role_action") is None or isinstance(segment.get("role_action"), str)):
            raise ValueError("role_action must be a string or null")
        # Compare complete snapshots; changing evidence at one revision is invalid.
        previous = self.latest.get(segment_id)
        if previous and revision < previous["revision"]:
            self.stale += 1
            self._last_observed_ms = observed
            return "stale_ignored"
        if previous and revision == previous["revision"]:
            if previous != segment:
                raise ValueError("same revision contains different data")
            self.duplicates += 1
            self._last_observed_ms = observed
            return "duplicate_ignored"
        self.latest[segment_id] = copy.deepcopy(segment)
        self.history.append(copy.deepcopy(event))
        self._last_observed_ms = observed
        return "accepted"

    def summary(self) -> dict:
        first_text = next((e["observed_ms"] / 1000 for e in self.history if e["segment"]["text"].strip()), None)
        first_stable = {}
        first_role = {}
        for event in self.history:
            seg = event["segment"]
            if seg["provisional"] or not seg["text"].strip():
                continue
            first_stable.setdefault(seg["segment_id"], event)
            if (seg.get("speaker_id") not in UNKNOWN_SPEAKERS and seg.get("role") in ROLES
                    and seg.get("role_action") in {"auto_accept", "manual_confirmed"}):
                first_role.setdefault(seg["segment_id"], event)
        delays = sorted(e["observed_ms"] / 1000 - e["segment"]["end_time"] for e in first_stable.values())
        return {
            "scope": "event_contract_only_not_model_accuracy",
            "accepted_event_count": len(self.history),
            "segment_count": len(self.latest),
            "duplicate_event_count": self.duplicates,
            "stale_event_count": self.stale,
            "first_text_seconds": first_text,
            "first_stable_delay_p95_seconds": delays[math.ceil(.95 * len(delays)) - 1] if delays else None,
            "stable_segment_count": len(first_stable),
            "current_stable_segments_without_accepted_role": sum(
                not (seg.get("speaker_id") not in UNKNOWN_SPEAKERS and seg.get("role") in ROLES
                     and seg.get("role_action") in {"auto_accept", "manual_confirmed"})
                for seg in self.latest.values() if not seg["provisional"] and seg["text"].strip()),
            "first_observed_accepted_role_seconds": min((e["observed_ms"] / 1000 for e in first_role.values()), default=None),
            "speaker_accuracy": None, "role_accuracy": None, "patient_subject_accuracy": None,
            "input_log_mutated_by_adapter": False,
        }


def sortformer_turns(lines: list[str]) -> list[dict]:
    """Adapt official start/end/speaker output; do not invent doctor/patient."""
    result = []
    for line in lines:
        parts = line.split()
        if len(parts) != 3:
            raise ValueError("expected 'start end speaker_id'")
        start, end = _number(float(parts[0]), "start"), _number(float(parts[1]), "end")
        if start < 0 or end <= start:
            raise ValueError("invalid speaker interval")
        result.append({"start_time": start, "end_time": end, "speaker_id": parts[2]})
    return result


def score_saved_turns(reference_rttm: Path, hypothesis: list[dict], provenance: dict) -> dict:
    """Reuse existing evaluator with strict provenance; no inference or audio I/O."""
    if provenance.get("truth_kind") not in TRUTH_KINDS:
        raise ValueError("real acoustic boundary truth required; TTS equal-time labels rejected")
    expected = provenance.get("reference_rttm_sha256")
    raw_reference = reference_rttm.read_bytes()
    actual = hashlib.sha256(raw_reference).hexdigest()
    if not expected or actual != expected:
        raise ValueError("RTTM hash mismatch")
    source_rows = [line.split() for line in raw_reference.decode('utf-8').splitlines() if line.strip() and not line.lstrip().startswith('#')]
    if any(len(row) < 8 or row[0] != 'SPEAKER' or row[2] != '1' for row in source_rows):
        raise ValueError("single-channel speaker RTTM required")
    if len({row[1] for row in source_rows}) != 1:
        raise ValueError("one audio file per RTTM required")
    audio_hash = provenance.get("audio_sha256")
    if not isinstance(audio_hash, str) or len(audio_hash) != 64 or any(c not in '0123456789abcdef' for c in audio_hash):
        raise ValueError("exact evaluated audio hash required")
    if provenance.get("hypothesis_audio_sha256") != audio_hash:
        raise ValueError("reference and hypothesis audio mismatch")
    duration = _number(provenance.get("audio_duration_seconds"), "audio_duration_seconds")
    if duration <= 0:
        raise ValueError("positive audio duration required")
    root = Path(__file__).resolve().parents[3]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from scripts.evaluate_diarization import evaluate_turns, parse_rttm
    from app.schemas.asr import DiarizationTurn
    reference = parse_rttm(reference_rttm)
    predicted = [DiarizationTurn.model_validate(turn) for turn in hypothesis]
    if not reference:
        raise ValueError("empty RTTM cannot measure a speech sample")
    for turn in reference + predicted:
        if not (0 <= turn.start_time < turn.end_time <= duration + .001):
            raise ValueError("turn outside exact audio; do not apply full RTTM to a crop")
    result = evaluate_turns(reference, predicted).__dict__
    return {"scope": "saved_output_scoring_no_model_call", **result,
            "der_jer_status": "available" if result['der'] is not None else "unavailable_pyannote_metrics_not_installed",
            "asr_cer": None, "medical_role_accuracy": None, "patient_subject_accuracy": None,
            "rtf": None, "resource_peak": None,
            "boundary_tolerance_seconds": .5, "model_calls": 0}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--events", required=True, type=Path, help="Private JSONL; never uploads")
    parser.add_argument("--session", required=True)
    args = parser.parse_args(argv)
    ledger = EventLedger(args.session)
    for line in args.events.read_text(encoding="utf-8").splitlines():
        if line.strip():
            ledger.add(json.loads(line))
    print(json.dumps(ledger.summary(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
