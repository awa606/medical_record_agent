"""Install a project-local portable ffmpeg build for Whisper smoke tests."""

from __future__ import annotations

import argparse
import json
import shutil
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
DEFAULT_TOOLS_DIR = PROJECT_ROOT / "tools" / "ffmpeg"
DEFAULT_REPORT_JSON = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "ffmpeg_portable_setup.json"
DEFAULT_REPORT_MD = PROJECT_ROOT / "data" / "asr_eval" / "reports" / "ffmpeg_portable_setup.md"


def setup_ffmpeg_portable(
    *,
    url: str = DEFAULT_URL,
    tools_dir: Path = DEFAULT_TOOLS_DIR,
    force: bool = False,
) -> dict[str, Any]:
    bin_dir = tools_dir / "bin"
    ffmpeg_exe = bin_dir / "ffmpeg.exe"
    if ffmpeg_exe.exists() and not force:
        return _report("present", url, tools_dir, "existing portable ffmpeg detected")

    tools_dir.mkdir(parents=True, exist_ok=True)
    archive_path = tools_dir / "ffmpeg-release-essentials.zip"
    _download(url, archive_path)
    extracted = _extract_binaries(archive_path, bin_dir)
    return _report("installed", url, tools_dir, f"extracted: {', '.join(extracted)}")


def write_setup_report(report: dict[str, Any], json_output: Path, markdown_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# 便携 ffmpeg 安装记录",
            "",
            "> 本记录用于 v0.5.3 Whisper 复测。`tools/ffmpeg/` 被 `.gitignore` 忽略，不提交二进制文件。",
            "",
            "| 项目 | 值 |",
            "| --- | --- |",
            f"| 状态 | {report['status']} |",
            f"| 下载源 | {report['source_url']} |",
            f"| 本地目录 | `{report['tools_dir']}` |",
            f"| ffmpeg.exe | `{report['ffmpeg_exe']}` |",
            f"| 说明 | {report['message']} |",
            "",
        ]
    )


def _download(url: str, destination: Path) -> None:
    with urllib.request.urlopen(url, timeout=120) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)


def _extract_binaries(archive_path: Path, bin_dir: Path) -> list[str]:
    bin_dir.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []
    wanted = {"ffmpeg.exe", "ffprobe.exe", "ffplay.exe"}
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            name = Path(member.filename).name
            if name not in wanted:
                continue
            with archive.open(member) as source, (bin_dir / name).open("wb") as target:
                shutil.copyfileobj(source, target)
            extracted.append(name)
    if "ffmpeg.exe" not in extracted:
        raise RuntimeError("ffmpeg.exe was not found in downloaded archive")
    return extracted


def _report(status: str, url: str, tools_dir: Path, message: str) -> dict[str, Any]:
    ffmpeg_exe = tools_dir / "bin" / "ffmpeg.exe"
    return {
        "schema_version": "v0.5.3",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "status": status,
        "source_url": url,
        "tools_dir": _relative(tools_dir),
        "ffmpeg_exe": _relative(ffmpeg_exe),
        "message": message,
    }


def _relative(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(PROJECT_ROOT))
    except ValueError:
        return path.name


def main() -> int:
    parser = argparse.ArgumentParser(description="Install project-local portable ffmpeg.")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--tools-dir", type=Path, default=DEFAULT_TOOLS_DIR)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-output", type=Path, default=DEFAULT_REPORT_JSON)
    parser.add_argument("--markdown-output", type=Path, default=DEFAULT_REPORT_MD)
    args = parser.parse_args()

    report = setup_ffmpeg_portable(url=args.url, tools_dir=args.tools_dir, force=args.force)
    write_setup_report(report, args.json_output, args.markdown_output)
    print("便携 ffmpeg 准备完成：")
    print(f"- status: {report['status']}")
    print(f"- ffmpeg: {report['ffmpeg_exe']}")
    print(f"- report: {args.markdown_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
