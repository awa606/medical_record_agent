from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.db import get_task, get_task_steps  # noqa: E402
from app.services.agent_trace import build_agent_trace  # noqa: E402


AUDIO_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
DEFAULT_UPLOAD_DIR = PROJECT_ROOT / "data" / "uploads"
DEFAULT_OUTPUT_DIR = PROJECT_ROOT / "docs" / "dev_logs" / "runs"
DEFAULT_ASR_EVAL_DIR = PROJECT_ROOT / "data" / "asr_eval"
try:
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except ZoneInfoNotFoundError:
    LOCAL_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a Markdown run log from task_id and audio_id.",
    )
    parser.add_argument("--task-id", required=True, type=int)
    parser.add_argument("--audio-id", required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument(
        "--upload-dir",
        type=Path,
        default=Path(os.environ.get("MEDICAL_RECORD_AGENT_UPLOAD_DIR", DEFAULT_UPLOAD_DIR)),
    )
    parser.add_argument("--db", type=Path, default=None)
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any] | list[Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def decode_json_value(value: Any) -> Any:
    if not isinstance(value, str) or not value:
        return value
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def decode_task(task: dict[str, Any] | None) -> dict[str, Any] | None:
    if task is None:
        return None
    decoded = dict(task)
    decoded["result_json"] = decode_json_value(decoded.get("result_json"))
    return decoded


def decode_steps(steps: list[dict[str, Any]]) -> list[dict[str, Any]]:
    decoded_steps: list[dict[str, Any]] = []
    for step in steps:
        decoded = dict(step)
        decoded["input_snapshot_json"] = decode_json_value(
            decoded.get("input_snapshot_json"),
        )
        decoded["output_snapshot_json"] = decode_json_value(
            decoded.get("output_snapshot_json"),
        )
        decoded_steps.append(decoded)
    return decoded_steps


def slugify_title(title: str) -> str:
    slug = re.sub(r"[^\w.-]+", "_", title.strip(), flags=re.UNICODE).strip("_")
    return slug or "run_log"


def truncate_text(value: Any, limit: int = 320) -> str:
    if value is None:
        return "未找到"
    text = str(value).replace("\r\n", "\n").replace("\r", "\n").strip()
    text = re.sub(r"\n{3,}", "\n\n", text)
    if len(text) <= limit:
        return text or "空"
    return f"{text[:limit].rstrip()}..."


def inline_text(value: Any, limit: int = 120) -> str:
    text = truncate_text(value, limit=limit).replace("\n", " / ")
    return text.replace("|", "\\|")


def list_text(items: Any) -> str:
    if not items:
        return "无"
    if isinstance(items, list):
        return "、".join(str(item) for item in items) or "无"
    return str(items)


def output_keys(value: Any) -> str:
    if isinstance(value, dict):
        keys = list(value.keys())
        return ", ".join(keys[:8]) if keys else "空对象"
    if isinstance(value, list):
        return f"list[{len(value)}]"
    if value is None:
        return "无"
    return type(value).__name__


def find_audio_file(upload_dir: Path, audio_id: str) -> Path | None:
    for suffix in AUDIO_SUFFIXES:
        path = upload_dir / f"{audio_id}{suffix}"
        if path.exists():
            return path
    matches = [
        path
        for path in upload_dir.glob(f"{audio_id}.*")
        if path.suffix.lower() in AUDIO_SUFFIXES
    ]
    return matches[0] if matches else None


def load_audio_record(upload_dir: Path, audio_id: str) -> dict[str, Any] | None:
    data = load_json(upload_dir / f"{audio_id}.record.json")
    return data if isinstance(data, dict) else None


def load_asr_result(upload_dir: Path, audio_id: str) -> dict[str, Any] | None:
    data = load_json(upload_dir / f"{audio_id}.transcript.json")
    return data if isinstance(data, dict) else None


def load_evaluation_json(path: Path, audio_id: str) -> dict[str, Any] | None:
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    if data.get("audio_id") == audio_id:
        return data
    if {"cer", "keyword_recall"}.issubset(data.keys()) and "audio_id" not in data:
        return data
    return None


def load_evaluation_csv(path: Path, audio_id: str, audio_filename: str | None) -> dict[str, Any] | None:
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for row in csv.DictReader(csv_file):
            filename = row.get("filename") or ""
            if row.get("audio_id") == audio_id or filename == audio_filename or Path(filename).stem == audio_id:
                return row
    return None


def find_evaluation(
    *,
    audio_id: str,
    title: str,
    upload_dir: Path,
    asr_eval_dir: Path = DEFAULT_ASR_EVAL_DIR,
    audio_filename: str | None = None,
) -> dict[str, Any] | None:
    json_candidates = [
        upload_dir / f"{audio_id}.evaluation.json",
        upload_dir / f"{audio_id}.eval.json",
        upload_dir / f"{audio_id}.evaluation_result.json",
        asr_eval_dir / f"{audio_id}.json",
        asr_eval_dir / f"{audio_id}.evaluation.json",
        asr_eval_dir / f"{slugify_title(title)}.json",
    ]
    for path in json_candidates:
        evaluation = load_evaluation_json(path, audio_id)
        if evaluation is not None:
            evaluation["_source"] = str(path)
            return evaluation

    if asr_eval_dir.exists():
        for path in sorted(asr_eval_dir.glob("*.csv")):
            evaluation = load_evaluation_csv(path, audio_id, audio_filename)
            if evaluation is not None:
                evaluation["_source"] = str(path)
                return evaluation
    return None


def medical_keywords_summary(asr_result: dict[str, Any] | None) -> dict[str, Any]:
    if not asr_result:
        return {"expected": [], "recognized": [], "missing": []}
    keywords = asr_result.get("medical_keywords")
    if not isinstance(keywords, dict):
        return {"expected": [], "recognized": [], "missing": []}
    return {
        "expected": keywords.get("expected") or [],
        "recognized": keywords.get("recognized") or [],
        "missing": keywords.get("missing") or [],
    }


def build_steps_table(steps: list[dict[str, Any]]) -> str:
    if not steps:
        return "未找到步骤日志。"

    lines = [
        "| 步骤 | 状态 | 尝试 | 耗时 ms | 输出摘要 | 错误 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for step in steps:
        lines.append(
            "| {step} | {status} | {attempt} | {duration} | {summary} | {error} |".format(
                step=inline_text(step.get("step_name"), 48),
                status=inline_text(step.get("status"), 32),
                attempt=step.get("attempt_no") or "",
                duration=step.get("duration_ms") if step.get("duration_ms") is not None else "",
                summary=inline_text(output_keys(step.get("output_snapshot_json")), 80),
                error=inline_text(step.get("error_message"), 80) if step.get("error_message") else "无",
            )
        )
    return "\n".join(lines)


def build_markdown(
    *,
    task_id: int,
    audio_id: str,
    title: str,
    run_time: datetime,
    task: dict[str, Any] | None,
    steps: list[dict[str, Any]],
    audio_record: dict[str, Any] | None,
    audio_file: Path | None,
    asr_result: dict[str, Any] | None,
    evaluation: dict[str, Any] | None,
) -> str:
    result = task.get("result_json") if task else None
    result = result if isinstance(result, dict) else {}
    safety_check = result.get("safety_check") if isinstance(result.get("safety_check"), dict) else {}
    keywords = medical_keywords_summary(asr_result)

    audio_path = audio_record.get("path") if audio_record else None
    audio_name = audio_record.get("filename") if audio_record else None
    if not audio_path and audio_file:
        audio_path = str(audio_file)
    if not audio_name and audio_file:
        audio_name = audio_file.name

    evaluation_source = evaluation.get("_source") if evaluation else "未找到"
    cer = evaluation.get("cer") if evaluation else "未找到"
    keyword_recall = evaluation.get("keyword_recall") if evaluation else "未找到"
    agent_trace = build_agent_trace(task=task, steps=steps, asr_result=asr_result)
    decision = agent_trace["decision"]
    llm_trace = agent_trace.get("llm") or {}
    safety_decision = (
        f"passed={decision.get('safety_passed')}, "
        f"blocked={decision.get('safety_blocked')}"
    )

    lines = [
        f"# 运行日志：{title}",
        "",
        "## 运行时间",
        "",
        f"- 日志生成时间：{run_time.isoformat()}",
        f"- task_id：{task_id}",
        f"- audio_id：{audio_id}",
        "",
        "## 输入音频",
        "",
        f"- 文件名：{audio_name or '未找到'}",
        f"- 文件路径：{audio_path or '未找到'}",
        f"- 上传状态：{audio_record.get('status') if audio_record else '未找到'}",
        f"- 文件大小：{audio_record.get('size_bytes') if audio_record else '未找到'}",
        "",
        "## ASR engine",
        "",
        f"- engine：{asr_result.get('engine') if asr_result else '未找到'}",
        f"- duration：{asr_result.get('duration') if asr_result else '未找到'}",
        f"- segments：{len(asr_result.get('segments') or []) if asr_result else '未找到'}",
        "",
        "## ASRResult 摘要",
        "",
        f"- text 摘要：{truncate_text(asr_result.get('text') if asr_result else None, 260)}",
        f"- conversation_text 摘要：{truncate_text(asr_result.get('conversation_text') if asr_result else None, 360)}",
        f"- recognized keywords：{list_text(keywords['recognized'])}",
        f"- missing keywords：{list_text(keywords['missing'])}",
        "",
        "## CER / keyword_recall",
        "",
        f"- CER：{cer}",
        f"- keyword_recall：{keyword_recall}",
        f"- evaluation 来源：{evaluation_source}",
        "",
        "## role_strategy / warnings",
        "",
        f"- role_strategy：{asr_result.get('role_strategy') if asr_result else '未找到'}",
        f"- warnings：{list_text(asr_result.get('warnings') if asr_result else [])}",
        "",
        "## Agent Trace / Decision Loop",
        "",
        f"- Agent mode: {agent_trace['agent_mode']}",
        f"- Input type: {agent_trace['input_type']}",
        f"- LLM provider: {llm_trace.get('llm_provider')}",
        f"- LLM model: {llm_trace.get('model')}",
        f"- LLM latency_ms: {llm_trace.get('latency_ms')}",
        f"- LLM fallback: {llm_trace.get('fallback')}",
        f"- LLM fallback_reason: {llm_trace.get('fallback_reason') or 'none'}",
        f"- Plan steps: {' -> '.join(agent_trace['plan'])}",
        f"- Executed steps: {', '.join(step['step'] + ':' + str(step['status']) for step in agent_trace['executed_steps']) or 'none'}",
        f"- Decision summary: next_state={decision.get('next_state')}, reason={decision.get('reason')}",
        f"- Safety decision: {safety_decision}",
        f"- Human-in-the-loop: {decision.get('human_in_the_loop_required')}",
        f"- Export allowed: {decision.get('export_allowed')}",
        "",
        "## 任务状态",
        "",
        f"- input_type：{task.get('input_type') if task else '未找到'}",
        f"- status：{task.get('status') if task else '未找到'}",
        f"- current_stage：{task.get('current_stage') if task else '未找到'}",
        f"- retry_count：{task.get('retry_count') if task else '未找到'}",
        f"- created_at：{task.get('created_at') if task else '未找到'}",
        f"- updated_at：{task.get('updated_at') if task else '未找到'}",
        f"- completed_at：{task.get('completed_at') if task else '未找到'}",
        f"- error_message：{task.get('error_message') if task and task.get('error_message') else '无'}",
        "",
        "## 步骤日志摘要",
        "",
        build_steps_table(steps),
        "",
        "## 病历草稿摘要",
        "",
        truncate_text(result.get("draft"), 700),
        "",
        "## 安全校验摘要",
        "",
        f"- passed：{safety_check.get('passed', '未找到')}",
        f"- blocked：{safety_check.get('blocked', '未找到')}",
        f"- errors：{list_text(safety_check.get('errors'))}",
        f"- warnings：{list_text(safety_check.get('warnings'))}",
        "",
    ]
    return "\n".join(lines)


def save_run_log(
    *,
    task_id: int,
    audio_id: str,
    title: str,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    upload_dir: Path | None = None,
    now: datetime | None = None,
) -> Path:
    run_time = now or datetime.now(LOCAL_TZ)
    resolved_upload_dir = upload_dir or Path(
        os.environ.get("MEDICAL_RECORD_AGENT_UPLOAD_DIR", DEFAULT_UPLOAD_DIR),
    )
    task = decode_task(get_task(task_id))
    steps = decode_steps(get_task_steps(task_id)) if task else []
    audio_record = load_audio_record(resolved_upload_dir, audio_id)
    audio_file = find_audio_file(resolved_upload_dir, audio_id)
    asr_result = load_asr_result(resolved_upload_dir, audio_id)
    audio_filename = audio_record.get("filename") if audio_record else None
    evaluation = find_evaluation(
        audio_id=audio_id,
        title=title,
        upload_dir=resolved_upload_dir,
        audio_filename=audio_filename,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{run_time.strftime('%Y-%m-%d')}_{slugify_title(title)}.md"
    output_path.write_text(
        build_markdown(
            task_id=task_id,
            audio_id=audio_id,
            title=title,
            run_time=run_time,
            task=task,
            steps=steps,
            audio_record=audio_record,
            audio_file=audio_file,
            asr_result=asr_result,
            evaluation=evaluation,
        ),
        encoding="utf-8",
    )
    return output_path


def main() -> int:
    args = parse_args()
    if args.db is not None:
        os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.db)

    output_path = save_run_log(
        task_id=args.task_id,
        audio_id=args.audio_id,
        title=args.title,
        output_dir=args.output_dir,
        upload_dir=args.upload_dir,
    )
    print(output_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
