from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.services.asr import (  # noqa: E402
    ASREvaluator,
    apply_manifest_role_strategy,
    create_asr_engine,
    load_asr_manifest,
)


AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate ASR output with CER and keyword recall.")
    parser.add_argument("--engine", default="mock", choices=["mock", "funasr", "qwen3", "online"])
    parser.add_argument("--audio-dir", required=True, type=Path)
    parser.add_argument("--truth-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--keyword-file",
        default=PROJECT_ROOT / "config" / "hotwords_medical.txt",
        type=Path,
    )
    return parser.parse_args()


def load_keywords(path: Path) -> list[str]:
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def iter_audio_files(audio_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in audio_dir.iterdir()
        if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    )


def main() -> int:
    args = parse_args()
    engine = create_asr_engine(args.engine)
    evaluator = ASREvaluator()
    keywords = load_keywords(args.keyword_file)
    manifest = load_asr_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict[str, object]] = []
    for audio_path in iter_audio_files(args.audio_dir):
        truth_path = args.truth_dir / f"{audio_path.stem}.txt"
        if not truth_path.exists():
            print(f"skip {audio_path.name}: missing ground truth {truth_path}", file=sys.stderr)
            continue

        started_at = time.perf_counter()
        result = engine.transcribe(audio_path.stem, audio_path)
        result = apply_manifest_role_strategy(result, audio_path.stem, manifest)
        inference_time = time.perf_counter() - started_at
        sample = manifest.get(audio_path.stem) or {}
        expected_keywords = sample.get("expected_keywords") or keywords
        evaluation = evaluator.evaluate(
            audio_id=audio_path.stem,
            engine=result.engine,
            ground_truth_text=truth_path.read_text(encoding="utf-8"),
            recognized_text=result.text,
            expected_keywords=expected_keywords,
        )
        rows.append(
            {
                "filename": audio_path.name,
                "engine": result.engine,
                "duration": result.duration,
                "inference_time": round(inference_time, 3),
                "cer": round(evaluation.cer, 6),
                "keyword_recall": round(evaluation.keyword_recall, 6),
                "recognized_keywords": "|".join(evaluation.medical_keywords["recognized"]),
                "missing_keywords": "|".join(evaluation.medical_keywords["missing"]),
            }
        )

    with args.output.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=[
                "filename",
                "engine",
                "duration",
                "inference_time",
                "cer",
                "keyword_recall",
                "recognized_keywords",
                "missing_keywords",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"wrote {len(rows)} rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
