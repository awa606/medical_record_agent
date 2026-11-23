"""Build an offline listening packet from six verified synthetic review pages."""
import argparse
import hashlib
import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo


CASE_IDS = tuple(f"zh_original_{i:03}" for i in range(1, 7))
INDEX = Path(__file__).with_name("index.html")


def attachments(manifest):
    cases = json.loads(manifest.read_text(encoding="utf-8-sig"))
    if set(cases) != set(CASE_IDS):
        raise ValueError("需要六个已验证的合成病例编号。")
    files = {}
    cards = []
    for number, case_id in enumerate(CASE_IDS, 1):
        case = cases[case_id]
        content = (manifest.parent / case["source"]).read_bytes()
        if hashlib.sha256(content).hexdigest() != case["sha256"]:
            raise ValueError(f"{case_id} 的文件指纹与逐例核验记录不一致。")
        if case_id.encode() not in content or b"data:audio/wav;base64," not in content:
            raise ValueError(f"{case_id} 缺少病例标识或内嵌的 WAV 音频。")
        seconds = case["seconds"]
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not 0 < seconds < 86400:
            raise ValueError(f"{case_id} 没有有效的录音时长。")
        name = f"病例{number:03}.html"
        files[name] = content
        minutes, remainder = divmod(round(seconds), 60)
        cards.append(f'<a href="{name}"><strong>病例 {number:03}</strong>'
                     f'<span>原音 {minutes} 分 {remainder:02} 秒</span></a>')
    template = INDEX.read_text(encoding="utf-8")
    if template.count("{{CASES}}") != 1:
        raise ValueError("听录目录模板中的病例入口异常。")
    files["从这里开始听录.html"] = template.replace("{{CASES}}", "".join(cards)).encode()
    return files


def build(manifest, destination):
    files = attachments(manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=destination.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        with ZipFile(temporary, "w") as archive:
            for name, content in sorted(files.items()):
                member = ZipInfo(name, date_time=(2026, 11, 24, 0, 0, 0))
                member.create_system = 0
                member.external_attr = 0o100644 << 16
                archive.writestr(member, content, compress_type=ZIP_DEFLATED, compresslevel=6)
        with ZipFile(temporary) as archive:
            if sorted(archive.namelist()) != sorted(files) or any(
                archive.read(name) != expected for name, expected in files.items()
            ):
                raise ValueError("复读 ZIP 与已核对的目录或病例页不符。")
        with temporary.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if os.name == "nt":
            temporary.rename(destination)
        else:
            os.link(temporary, destination)
        return digest
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description="把六份已核验的合成听录页封装成可离线使用的 ZIP。")
    cli.add_argument("manifest", type=Path, help="逐例提供已核验页面路径 source、sha256 与秒数 seconds")
    cli.add_argument("destination", type=Path, help="新 ZIP 路径")
    args = cli.parse_args()
    print(build(args.manifest, args.destination), args.destination.name)
