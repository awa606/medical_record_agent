"""Read package metadata and selected ASR files; no model imports/downloads."""
from __future__ import annotations

import argparse
import collections
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import sys
import wave

ROOT = Path(__file__).resolve().parents[3]
PACKAGES = ("funasr", "torch", "torchaudio", "diart", "pyannote.audio", "pyannote.metrics", "nemo_toolkit", "transformers", "sherpa-onnx")
AUTHORIZED_SHORT_HASH = "e0d16a3192b99ee99c74fc730facd22338cd4da2a3bb28da980d6d99375f74a4"
AUTHORIZED_SHORT_RTTM_HASH = "3cb3a3cc9c9634b9b74e75a3abff039d944d11c92023ac9c4e8c6eebcc0c057b"


def fingerprint(path: Path) -> dict:
    record = {"name": path.name, "exists": path.is_file()}
    if not path.is_file():
        return record
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    record.update(bytes=path.stat().st_size, sha256=hasher.hexdigest())
    if path.suffix.lower() == ".wav":
        with wave.open(str(path), "rb") as audio:
            record.update(seconds=audio.getnframes() / audio.getframerate(), sample_rate=audio.getframerate(), channels=audio.getnchannels())
    return record


def inspect(root: Path, audio: Path | None = None, reference_rttm: Path | None = None) -> dict:
    packages = {}
    for package in PACKAGES:
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = None
    data_root = root / "data/asr_eval"
    reference_rows = []
    for sample in ("fever_01", "chest_pain_01", "three_speaker_alimeeting_01"):
        reference = data_root / "diarization_ground_truth" / f"{sample}.rttm"
        item = fingerprint(reference)
        if reference.is_file():
            rows = [line.split() for line in reference.read_text(encoding="utf-8").splitlines() if line.startswith("SPEAKER ")]
            item.update(turns=len(rows), last_end_seconds=max((float(row[3]) + float(row[4]) for row in rows), default=0.))
        sample_audio = data_root / ("public_diarization/audio" if sample.startswith("three_") else "audio") / f"{sample}.wav"
        item["corresponding_audio_in_current_tree"] = fingerprint(sample_audio)
        reference_rows.append(item)
    synthetic_manifest = data_root / "executable_clinical_v1/manifest.json"
    synthetic = {"available": synthetic_manifest.is_file()}
    if synthetic_manifest.is_file():
        manifest = json.loads(synthetic_manifest.read_text(encoding="utf-8"))
        samples = manifest.get("samples", [])
        synthetic.update(
            sample_count=len(samples), splits=dict(collections.Counter(row["split"] for row in samples)),
            calibration_audio_hashes_match=all(
                fingerprint(synthetic_manifest.parent / row["audio_ref"]).get("sha256") == row["sha256"]
                for row in samples if row["split"] == "calibration"),
            acoustic_truth_eligible=False,
            reason="Generator uses one TTS Speak call and equally timed script labels; not multi-voice acoustic truth.",
            test_split_contents_opened=False,
        )
    supplied = fingerprint(audio) if audio else None
    if supplied:
        supplied["matches_existing_authorized_short_sample"] = supplied.get("sha256") == AUTHORIZED_SHORT_HASH
        paired = fingerprint(reference_rttm) if reference_rttm else None
        supplied["matching_human_rttm"] = paired
        supplied["verified_frozen_crop_pair"] = bool(
            supplied.get("sha256") == AUTHORIZED_SHORT_HASH and paired
            and paired.get("sha256") == AUTHORIZED_SHORT_RTTM_HASH)
    return {
        "scope": "metadata_and_hash_preflight_no_inference", "python": sys.version.split()[0],
        "platform": platform.platform(), "packages": packages,
        "references": reference_rows, "synthetic_fixture_inventory": synthetic, "supplied_audio": supplied,
        "research_gate": "NEEDS MORE EVIDENCE", "selected_candidate": None,
        "new_model_calls": 0, "model_weights_loaded": False, "production_modified": False,
        "blockers": [
            "Fresh isolated candidate runtime and weight licenses/cache not validated.",
            "Acoustic scoring requires the frozen WAV/RTTM pair; supplying an unmatched full-file RTTM is refused.",
            "Browser/SSE common-clock measurement and 5-10 minute reference session still not verified.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=ROOT)
    parser.add_argument("--audio", type=Path, help="Explicit local authorized audio; not uploaded or copied")
    parser.add_argument("--reference-rttm", type=Path, help="Optional exact 2026-09-19 crop RTTM; never infer offsets")
    args = parser.parse_args(argv)
    print(json.dumps(inspect(args.repo_root, args.audio, args.reference_rttm), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
