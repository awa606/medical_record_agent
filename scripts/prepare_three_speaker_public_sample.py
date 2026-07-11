from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import tarfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.schemas.asr import DiarizationTurn
from app.services.asr.ffmpeg_utils import find_ffmpeg_executable


DATASETS = {
    "alimeeting": {
        "name": "AliMeeting Eval",
        "url": "https://speech-lab-share-data.oss-cn-shanghai.aliyuncs.com/AliMeeting/openlr/Eval_Ali.tar.gz",
        "license": "CC BY-SA 4.0",
        "source": "https://openslr.org/119/",
        "size": "3.42G",
    },
    "aishell5": {
        "name": "AISHELL-5 Dev",
        "url": "https://openslr.trmal.net/resources/159/Dev.tar.gz",
        "license": "CC BY-SA 4.0",
        "source": "https://openslr.org/159/",
        "size": "1.9G",
    },
}


@dataclass(frozen=True)
class Candidate:
    audio: Path
    annotation: Path
    turns: list[DiarizationTurn]


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare one public Chinese three-speaker diarization sample.")
    parser.add_argument("--dataset", choices=sorted(DATASETS), default="alimeeting")
    parser.add_argument("--work-dir", type=Path, default=PROJECT_ROOT / "data" / "asr_eval" / "public_diarization")
    parser.add_argument("--sample-id", default="three_speaker_alimeeting_01")
    parser.add_argument("--download", action="store_true", help="Download the dataset archive if missing.")
    parser.add_argument("--archive", type=Path, help="Use an existing local tar.gz archive.")
    parser.add_argument("--source-root", type=Path, help="Use an already extracted dataset root.")
    parser.add_argument("--duration-seconds", type=float, default=300.0)
    parser.add_argument("--min-speakers", type=int, default=3)
    parser.add_argument("--materialize", action="store_true", help="Cut audio with ffmpeg and write a relative RTTM.")
    parser.add_argument("--manifest-output", type=Path)
    parser.add_argument("--rttm-output", type=Path)
    args = parser.parse_args()

    work_dir = args.work_dir
    cache_dir = work_dir / "cache"
    extract_dir = work_dir / "extracted"
    audio_dir = work_dir / "audio"
    manifest_path = args.manifest_output or work_dir / "three_speaker_manifest.json"
    rttm_path = args.rttm_output or PROJECT_ROOT / "data" / "asr_eval" / "diarization_ground_truth" / f"{args.sample_id}.rttm"
    for path in [cache_dir, extract_dir, audio_dir, manifest_path.parent, rttm_path.parent]:
        path.mkdir(parents=True, exist_ok=True)

    dataset = DATASETS[args.dataset]
    archive = args.archive or cache_dir / Path(dataset["url"]).name
    status = "pending"
    reason = ""
    if args.download and not archive.exists():
        try:
            _download(dataset["url"], archive)
        except Exception as exc:
            status = "download_failed"
            reason = str(exc)

    source_root = args.source_root
    if source_root is None and archive.exists():
        try:
            source_root = _extract_archive(archive, extract_dir / args.dataset)
        except Exception as exc:
            status = "extract_failed"
            reason = str(exc)

    candidate: Candidate | None = None
    window: tuple[float, float] | None = None
    if source_root and source_root.exists():
        candidate = _find_candidate(source_root, min_speakers=args.min_speakers)
        if candidate:
            window = _select_window(candidate.turns, args.duration_seconds, args.min_speakers)
            status = "selected" if window else "no_three_speaker_window"
            reason = "" if window else "No window contains the requested number of speakers."
        elif status == "pending":
            status = "no_candidate"
            reason = "No audio/annotation pair with enough speakers was found."

    output_audio = audio_dir / f"{args.sample_id}{candidate.audio.suffix if candidate else '.wav'}"
    if args.materialize and candidate and window:
        _cut_audio(candidate.audio, output_audio, start=window[0], duration=window[1] - window[0])
        _write_rttm(rttm_path, _relative_turns(candidate.turns, start=window[0], end=window[1]), args.sample_id)
        status = "materialized"
    elif candidate and window:
        _write_rttm(rttm_path, _relative_turns(candidate.turns, start=window[0], end=window[1]), args.sample_id)

    manifest = {
        "sample_id": args.sample_id,
        "status": status,
        "reason": reason,
        "dataset": dataset,
        "source_root": _display_path(source_root) if source_root else None,
        "audio_source": _display_path(candidate.audio) if candidate else None,
        "annotation_source": _display_path(candidate.annotation) if candidate else None,
        "audio_output": _display_path(output_audio) if args.materialize and candidate and window else None,
        "rttm_output": _display_path(rttm_path) if candidate and window else None,
        "window_seconds": list(window) if window else None,
        "speaker_count": len({turn.speaker_id for turn in candidate.turns}) if candidate else 0,
        "note": "Raw audio and archives are local-only and must not be committed.",
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False))
    return 0 if status in {"selected", "materialized"} else 2


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def _download(url: str, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.replace(output)


def _extract_archive(archive: Path, destination: Path) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    marker = destination / ".extracted"
    if not marker.exists():
        with tarfile.open(archive, "r:*") as tar:
            _safe_extract(tar, destination)
        marker.write_text("ok", encoding="utf-8")
    return destination


def _safe_extract(tar: tarfile.TarFile, destination: Path) -> None:
    destination_root = destination.resolve()
    for member in tar.getmembers():
        target = (destination / member.name).resolve()
        if not str(target).startswith(str(destination_root)):
            raise RuntimeError(f"Unsafe archive path: {member.name}")
    tar.extractall(destination)


def _find_candidate(root: Path, *, min_speakers: int) -> Candidate | None:
    annotations = [*root.rglob("*.rttm"), *root.rglob("*.TextGrid"), *root.rglob("*.textgrid")]
    audio_files = [*root.rglob("*.wav"), *root.rglob("*.flac")]
    audio_by_stem: dict[str, Path] = {}
    for audio in audio_files:
        audio_by_stem.setdefault(audio.stem, audio)
    for annotation in annotations:
        audio = audio_by_stem.get(annotation.stem)
        if audio is None:
            audio = _best_audio_match(annotation, audio_by_stem)
        if audio is None:
            continue
        turns = parse_annotation(annotation)
        if len({turn.speaker_id for turn in turns}) >= min_speakers:
            return Candidate(audio=audio, annotation=annotation, turns=turns)
    return None


def _best_audio_match(annotation: Path, audio_by_stem: dict[str, Path]) -> Path | None:
    for stem, audio in audio_by_stem.items():
        if annotation.stem in stem or stem in annotation.stem:
            return audio
    return None


def parse_annotation(path: Path) -> list[DiarizationTurn]:
    if path.suffix.lower() == ".rttm":
        return _parse_rttm(path)
    return _parse_textgrid(path)


def _parse_rttm(path: Path) -> list[DiarizationTurn]:
    turns: list[DiarizationTurn] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = line.split()
        if len(parts) >= 8 and parts[0] == "SPEAKER":
            start = float(parts[3])
            duration = float(parts[4])
            turns.append(DiarizationTurn(start_time=start, end_time=start + duration, speaker_id=parts[7]))
    return turns


def _parse_textgrid(path: Path) -> list[DiarizationTurn]:
    text = path.read_text(encoding="utf-8", errors="ignore")
    item_blocks = re.split(r"\n\s*item \[\d+\]:", text)
    turns: list[DiarizationTurn] = []
    for block in item_blocks:
        name_match = re.search(r'name\s*=\s*"([^"]+)"', block)
        if not name_match:
            continue
        speaker = _normalize_speaker(name_match.group(1))
        intervals = re.findall(
            r"xmin\s*=\s*([0-9.]+)\s+xmax\s*=\s*([0-9.]+)\s+text\s*=\s*\"([^\"]*)\"",
            block,
            flags=re.S,
        )
        for start, end, label in intervals:
            label = label.strip()
            if not label or label in {"<sil>", "<SIL>", "<noise>", "<NOISE>"}:
                continue
            turns.append(
                DiarizationTurn(
                    start_time=float(start),
                    end_time=float(end),
                    speaker_id=speaker,
                )
            )
    return sorted(turns, key=lambda turn: (turn.start_time, turn.end_time, turn.speaker_id))


def _normalize_speaker(value: str) -> str:
    normalized = re.sub(r"\s+", "_", value.strip())
    return normalized or "speaker"


def _select_window(turns: list[DiarizationTurn], duration: float, min_speakers: int) -> tuple[float, float] | None:
    if not turns:
        return None
    starts = sorted({round(turn.start_time, 3) for turn in turns})
    for start in starts:
        end = start + duration
        speakers = {
            turn.speaker_id
            for turn in turns
            if max(0.0, min(turn.end_time, end) - max(turn.start_time, start)) > 0.2
        }
        if len(speakers) >= min_speakers:
            return (start, end)
    return None


def _relative_turns(turns: list[DiarizationTurn], *, start: float, end: float) -> list[DiarizationTurn]:
    output: list[DiarizationTurn] = []
    for turn in turns:
        overlap_start = max(turn.start_time, start)
        overlap_end = min(turn.end_time, end)
        if overlap_end - overlap_start <= 0.05:
            continue
        output.append(
            DiarizationTurn(
                start_time=round(overlap_start - start, 3),
                end_time=round(overlap_end - start, 3),
                speaker_id=turn.speaker_id,
            )
        )
    return output


def _write_rttm(path: Path, turns: list[DiarizationTurn], sample_id: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for turn in turns:
        duration = max(0.0, turn.end_time - turn.start_time)
        lines.append(f"SPEAKER {sample_id} 1 {turn.start_time:.3f} {duration:.3f} <NA> <NA> {turn.speaker_id} <NA> <NA>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cut_audio(source: Path, output: Path, *, start: float, duration: float) -> None:
    ffmpeg = find_ffmpeg_executable()
    if not ffmpeg:
        raise RuntimeError("ffmpeg is required to materialize the audio segment.")
    output.parent.mkdir(parents=True, exist_ok=True)
    import subprocess

    subprocess.run(
        [
            str(ffmpeg),
            "-y",
            "-ss",
            f"{start:.3f}",
            "-i",
            str(source),
            "-t",
            f"{duration:.3f}",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(output),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    raise SystemExit(main())
