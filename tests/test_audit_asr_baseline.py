from __future__ import annotations

import csv
import wave
from pathlib import Path

from scripts.audit_asr_baseline import audit_audio, summarize_benchmark


def _write_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(16000)
        handle.writeframes(b"\x00\x00" * 16000)


def test_audio_audit_detects_duplicate_and_ground_truth(tmp_path: Path) -> None:
    audio_root = tmp_path / "audio"
    truth_root = tmp_path / "truth"
    audio_root.mkdir()
    truth_root.mkdir()
    first = audio_root / "sample.wav"
    duplicate = audio_root / "copy.wav"
    _write_wav(first)
    duplicate.write_bytes(first.read_bytes())
    (truth_root / "sample.txt").write_text("人工转写", encoding="utf-8")

    rows, duplicates = audit_audio(audio_root, truth_root)

    assert len(rows) == 2
    assert rows[1]["format_matches_suffix"] is True
    assert next(row for row in rows if row["filename"] == "sample.wav")["ground_truth_present"] is True
    assert duplicates == [["copy.wav", "sample.wav"]]


def test_benchmark_gate_requires_all_quality_thresholds(tmp_path: Path) -> None:
    report = tmp_path / "engine_report.csv"
    with report.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["filename", "engine", "status", "cer", "keyword_recall", "realtime_factor", "rss_peak_mb"],
        )
        writer.writeheader()
        writer.writerow(
            {
                "filename": "sample.wav",
                "engine": "test-engine",
                "status": "measured",
                "cer": "0.10",
                "keyword_recall": "0.80",
                "realtime_factor": "0.5",
                "rss_peak_mb": "100",
            }
        )

    result = summarize_benchmark("test", report, {"sample"})

    assert result["gate_checks"]["cer_le_0_15"] is True
    assert result["gate_checks"]["keyword_recall_ge_0_90"] is False
    assert result["t09_gate"] == "FAIL"
