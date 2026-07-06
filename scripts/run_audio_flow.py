from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIO = Path(r"C:\Users\AWA007\Desktop\开题报告\病历\AI生成式电子病历.mp4-文本\AI生成式电子病历.mp4-音频.mp3")
DEFAULT_BILIBILI_DIR = Path(r"C:\Users\AWA007\Videos\bilibili")
DEFAULT_TRANSCRIPT = PROJECT_ROOT.parent / "medical-record-agent" / "docs" / "蛇咬伤问诊转写.txt"

AUDIO_OUTPUT_DIR = PROJECT_ROOT / "data" / "uploads" / "audio"
NORMALIZED_MEDIA_DIR = PROJECT_ROOT / "data" / "uploads" / "normalized_media"
TRANSCRIPT_OUTPUT_DIR = PROJECT_ROOT / "data" / "transcripts"
REPORT_OUTPUT_DIR = PROJECT_ROOT / "data" / "outputs"


def ensure_project_imports() -> None:
    project_root = str(PROJECT_ROOT)
    if project_root not in sys.path:
        sys.path.insert(0, project_root)


def get_ffmpeg_executable() -> str:
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg

    try:
        import imageio_ffmpeg
    except ImportError as exc:
        raise RuntimeError(
            "未找到 ffmpeg，也未安装 imageio-ffmpeg，无法转换音频。"
        ) from exc

    return imageio_ffmpeg.get_ffmpeg_exe()


def safe_name(name: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in name).strip("_")


def read_video_title(video_dir: Path) -> str:
    info_path = video_dir / "videoInfo.json"
    if not info_path.exists():
        return video_dir.name

    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return video_dir.name

    return info.get("title") or info.get("groupTitle") or video_dir.name


def convert_to_mp3(ffmpeg: str, input_path: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    normalized_input = normalize_mp4_prefix(input_path)
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(normalized_input),
        "-vn",
        "-acodec",
        "libmp3lame",
        "-b:a",
        "128k",
        str(output_path),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8", errors="replace")

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError(f"转换失败，输出文件为空：{output_path}")


def normalize_mp4_prefix(input_path: Path) -> Path:
    header = input_path.read_bytes()[:128]
    ftyp_at = header.find(b"ftyp")
    if ftyp_at in (-1, 4):
        return input_path

    box_start = ftyp_at - 4
    if box_start < 0:
        return input_path

    NORMALIZED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    normalized_path = NORMALIZED_MEDIA_DIR / input_path.name
    with input_path.open("rb") as source, normalized_path.open("wb") as target:
        source.seek(box_start)
        shutil.copyfileobj(source, target)
    return normalized_path


def convert_bilibili_folder(ffmpeg: str, bilibili_dir: Path) -> list[dict[str, str]]:
    converted: list[dict[str, str]] = []
    if not bilibili_dir.exists():
        return converted

    for video_dir in sorted(path for path in bilibili_dir.iterdir() if path.is_dir()):
        candidates = sorted(video_dir.glob("*.m4s"), key=lambda path: path.stat().st_size)
        if not candidates:
            continue

        title = read_video_title(video_dir)
        output_path = AUDIO_OUTPUT_DIR / f"{safe_name(video_dir.name)}_{safe_name(title)}.mp3"
        last_error: str | None = None

        for candidate in candidates:
            try:
                convert_to_mp3(ffmpeg, candidate, output_path)
                converted.append(
                    {
                        "title": title,
                        "source": str(candidate),
                        "output": str(output_path),
                    }
                )
                break
            except subprocess.CalledProcessError as exc:
                last_error = exc.stderr or str(exc)

        if last_error and not output_path.exists():
            converted.append(
                {
                    "title": title,
                    "source": str(video_dir),
                    "output": "",
                    "error": last_error,
                }
            )

    return converted


def copy_existing_audio(audio_path: Path) -> Path:
    if not audio_path.exists():
        raise FileNotFoundError(f"找不到音频文件：{audio_path}")

    AUDIO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = AUDIO_OUTPUT_DIR / audio_path.name
    shutil.copy2(audio_path, target)
    return target


def copy_transcript(transcript_path: Path) -> tuple[Path, str]:
    if not transcript_path.exists():
        raise FileNotFoundError(f"找不到转写文本：{transcript_path}")

    TRANSCRIPT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target = TRANSCRIPT_OUTPUT_DIR / transcript_path.name
    shutil.copy2(transcript_path, target)
    return target, target.read_text(encoding="utf-8")


def attach_source_metadata(task_id: int, metadata: dict[str, Any]) -> None:
    ensure_project_imports()
    from app.db import get_task, json_dumps, update_task

    task = get_task(task_id)
    if not task or not task.get("result_json"):
        return

    result = json.loads(task["result_json"])
    result["source_files"] = metadata
    update_task(task_id, result_json=json_dumps(result))


def run_agent_flow(transcript_text: str) -> dict[str, Any]:
    ensure_project_imports()
    from app.agents import MedicalRecordOrchestrator
    from app.api.tasks import approve_task, export_task, read_task

    result = MedicalRecordOrchestrator().run_from_text(transcript_text)
    task_id = result["task_id"]
    approve_task(task_id)
    export_info = export_task(task_id)
    task = read_task(task_id)

    return {
        "task_id": task_id,
        "task": task,
        "exports": export_info["exports"],
    }


def write_report(report: dict[str, Any], task_id: int) -> Path:
    REPORT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = REPORT_OUTPUT_DIR / f"audio_flow_report_task_{task_id}.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return report_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert local audio/video files and run the medical record Agent flow.")
    parser.add_argument("--audio", type=Path, default=DEFAULT_AUDIO)
    parser.add_argument("--bilibili-dir", type=Path, default=DEFAULT_BILIBILI_DIR)
    parser.add_argument("--transcript", type=Path, default=DEFAULT_TRANSCRIPT)
    args = parser.parse_args()

    ffmpeg = get_ffmpeg_executable()
    existing_audio = copy_existing_audio(args.audio)
    converted = convert_bilibili_folder(ffmpeg, args.bilibili_dir)
    transcript_file, transcript_text = copy_transcript(args.transcript)

    flow = run_agent_flow(transcript_text)
    source_metadata = {
        "existing_audio": str(existing_audio),
        "converted_audio": converted,
        "transcript_file": str(transcript_file),
        "note": "当前项目尚未接入 ASR，本次使用已有转写文本驱动 Agent 全流程。",
    }
    attach_source_metadata(flow["task_id"], source_metadata)

    report = {
        "task_id": flow["task_id"],
        "source_files": source_metadata,
        "exports": flow["exports"],
        "task_status": flow["task"]["status"],
        "task_query_url": f"/api/tasks/{flow['task_id']}",
    }
    report_path = write_report(report, flow["task_id"])

    print(json.dumps({**report, "report_path": str(report_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
