"""Render the B and C synthetic outpatient scripts using local Windows speech voices."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
import wave


HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parents[1] / "data/clinical_e2e/synthetic_visit_timeline_v1/spoken_input.json"
VOICES = {
    "SYN-TM-B": ("Huihui", "Kangkang", "Yaoyao"),
    "SYN-TM-C": ("Yaoyao", "Huihui", "Kangkang"),
}
SAMPLE_RATE = 16_000
GAP_FRAMES = 4_800


def render(destination: Path) -> None:
    if destination.exists():
        raise FileExistsError(f"目标已存在，请选择新目录：{destination}")
    destination.parent.mkdir(exist_ok=True, parents=True)
    scripts = {case["id"]: case["发言"] for case in json.loads(SCRIPTS.read_bytes())["cases"]}
    with TemporaryDirectory(dir=destination.parent, prefix="mra-voice-") as temporary:
        work = Path(temporary)
        bundle = work / "bundle"
        bundle.mkdir()
        jobs = []
        for case, voices in VOICES.items():
            for number, (turn, voice) in enumerate(zip(scripts[case], voices, strict=True), start=1):
                jobs.append({
                    "case": case, "id": f"{case}-{number}", "voice": voice,
                    "speaker": turn["角色"], "words": turn["原话"],
                })
        spec = work / "voices.json"
        spec.write_text(json.dumps(jobs, ensure_ascii=False), encoding="utf-8")
        subprocess.run([
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(HERE / "synthesize_wav.ps1"), "-Spec", str(spec), "-Destination", str(work),
        ], check=True)
        recordings = {}
        for case in VOICES:
            pcm = bytearray()
            timeline = []
            for row in (item for item in jobs if item["case"] == case):
                with wave.open(str(work / (row["id"] + ".wav")), "rb") as part:
                    if part.getparams()[:3] != (1, 2, SAMPLE_RATE):
                        raise ValueError(f"非预期的语音格式：{row['id']}")
                    segment = part.readframes(part.getnframes())
                if not any(segment):
                    raise ValueError(f"音轨为空：{row['id']}")
                if timeline:
                    pcm.extend(bytes(GAP_FRAMES * 2))
                start = len(pcm) // 2
                pcm.extend(segment)
                timeline.append({
                    "speaker": row["speaker"], "voice": row["voice"], "words": row["words"],
                    "start_frame": start, "end_frame": len(pcm) // 2,
                    "pcm_sha256": hashlib.sha256(segment).hexdigest(),
                })
            path = bundle / (case + ".wav")
            with wave.open(str(path), "wb") as recording:
                recording.setparams((1, 2, SAMPLE_RATE, 0, "NONE", "not compressed"))
                recording.writeframes(pcm)
            recordings[case] = {
                "file": path.name, "sample_rate": SAMPLE_RATE, "gap_frames": GAP_FRAMES,
                "frames": len(pcm) // 2, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "turns": timeline,
            }
        (bundle / "timeline.json").write_text(
            json.dumps(recordings, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        bundle.rename(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="新建的输出目录")
    render(parser.parse_args().output.resolve())
