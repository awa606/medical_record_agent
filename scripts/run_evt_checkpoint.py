from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REQUIRED_STRUCTURED_FIELDS = {
    "chief_complaint",
    "present_illness",
    "previous_treatment",
    "accompanying_symptoms",
    "past_history",
    "allergy_history",
    "physical_exam",
}

CHECK_GROUPS = {
    "workflow_gate": [
        "tests/test_encounter_workflow.py",
        "tests/test_tasks_api.py",
        "tests/test_review_revision_transaction.py",
        "tests/test_local_patient_encounter_doctor_isolation.py",
    ],
    "role_gate": [
        "tests/test_speaker_role_provider_policy.py",
        "tests/test_speaker_role_quality_policy.py",
        "tests/test_audio_api.py",
    ],
    "recovery": [
        "tests/test_task_persistence_after_restart.py",
        "tests/test_runtime_hardening.py",
        "tests/test_funasr_reliability.py",
    ],
    "knowledge_demo": [
        "tests/test_demo_knowledge_api.py",
        "tests/test_fever_respiratory_pack.py",
    ],
}


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_value(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout.strip()


def _run_check_group(name: str, paths: list[str]) -> dict[str, Any]:
    started = time.perf_counter()
    command = [sys.executable, "-m", "pytest", "-q", *paths]
    completed = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return {
        "name": name,
        "status": "PASS" if completed.returncode == 0 else "FAIL",
        "exit_code": completed.returncode,
        "duration_seconds": round(time.perf_counter() - started, 3),
        "command": command,
        "stdout_tail": completed.stdout[-2000:],
        "stderr_tail": completed.stderr[-2000:],
    }


def _final_check_metrics(clinical: dict[str, Any]) -> dict[str, Any]:
    cases = [case for case in clinical.get("cases", []) if case.get("split") == "final_check"]
    complete = 0
    missing: dict[str, list[str]] = {}
    for case in cases:
        fields = set((case.get("actual", {}).get("field_status") or {}).keys())
        absent = sorted(REQUIRED_STRUCTURED_FIELDS - fields)
        if absent:
            missing[str(case.get("case_id"))] = absent
        else:
            complete += 1
    metrics = clinical.get("metrics", {})
    return {
        "sample_count": len(cases),
        "required_field_schema_complete": complete,
        "required_field_schema_rate": round(complete / len(cases), 4) if cases else None,
        "missing_fields": missing,
        "unsupported_content_count": metrics.get("unsupported_content_count"),
        "forbidden_candidate_count": metrics.get("forbidden_candidate_count"),
        "confirmed_diagnosis_phrase_count": metrics.get("confirmed_diagnosis_phrase_count"),
        "provider_mode": clinical.get("provider_mode"),
        "audio_pipeline_evaluated": clinical.get("audio_pipeline_evaluated"),
    }


def build_matrix(
    clinical: dict[str, Any],
    dependencies: dict[str, Any],
    checks: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    final = _final_check_metrics(clinical)
    modules = dependencies.get("modules", {})
    real_asr_ready = any(bool(modules.get(name, {}).get("available")) for name in ("funasr", "sensevoice", "qwen_asr", "whisper"))
    asr_module_summary = {
        name: {
            "available": bool(modules.get(name, {}).get("available")),
            "version": modules.get(name, {}).get("version"),
        }
        for name in ("torch", "torchaudio", "funasr", "sensevoice", "qwen_asr", "whisper", "soundfile", "ffmpeg")
    }
    workflow_ok = checks["workflow_gate"]["status"] == "PASS"
    role_ok = checks["role_gate"]["status"] == "PASS"
    recovery_ok = checks["recovery"]["status"] == "PASS"
    knowledge_demo_ok = checks["knowledge_demo"]["status"] == "PASS"

    def item(test_id: str, category: str, name: str, standard: str, status: str, measured: dict[str, Any], gap: str, veto: bool = False) -> dict[str, Any]:
        return {
            "id": test_id,
            "category": category,
            "name": name,
            "standard": standard,
            "veto": veto,
            "status": status,
            "measured": measured,
            "remaining_gap": gap,
        }

    no_unsupported = all((final.get(key) or 0) == 0 for key in ("unsupported_content_count", "forbidden_candidate_count", "confirmed_diagnosis_phrase_count"))
    return [
        item("T01", "功能", "病历生成完整性", "20例必需结构字段存在率100%", "PARTIAL" if final["required_field_schema_rate"] == 1 else "FAIL", final, "结构Schema已验证；仍需真实ASR与真实本地LLM生成20例。"),
        item("T02", "AI质量", "AI幻觉检测", "虚构事实0、输入矛盾0", "PARTIAL" if no_unsupported else "FAIL", {k: final[k] for k in ("unsupported_content_count", "forbidden_candidate_count", "confirmed_diagnosis_phrase_count", "provider_mode")}, "当前是确定性Mock文本基线，不能替代真实本地模型验收。", True),
        item("T03", "功能", "医学术语规范", "20个固定样本错误数0", "NOT TESTED", {}, "尚未冻结20个术语样本和人工真值。"),
        item("T04", "功能", "编辑与人工确认", "10种场景全部可编辑，未确认提交/归档成功数0", "PARTIAL" if workflow_ok else "FAIL", {"workflow_gate": checks["workflow_gate"]["status"]}, "自动化接口/事务门禁已通过；仍需10种浏览器场景逐项留证。"),
        item("T05", "安全", "脱敏与合规", "姓名、ID、联系方式脱敏率100%，非授权外发0", "NOT TESTED", {}, "尚未建立带人工真值的脱敏样本和外发检查。", True),
        item("T06", "安全", "操作留痕", "生成、修改、审核、导出10种操作可追溯率100%", "PARTIAL" if workflow_ok else "FAIL", {"workflow_gate": checks["workflow_gate"]["status"]}, "审计链路测试通过；尚未形成10种操作的课程证据清单。"),
        item("T07", "性能", "生成时延", "最终转写完成到结构化病历就绪P95≤15秒", "BLOCKED", {"real_asr_runtime_available": real_asr_ready}, "真实ASR/LLM运行时未冻结，无法测P95。"),
        item("T08", "一致性", "双环境一致性", "20例结构化字段一致率100%", "HARDWARE BLOCKED", {"development_device": dependencies.get("cuda", {}), "jetson_available": False}, "Jetson未到货，当前只有开发机证据。"),
        item("T09", "AI质量", "ASR质量", "CER≤15%，医学关键词召回≥90%，RTF≤1", "BLOCKED", {"real_asr_runtime_available": real_asr_ready, "modules": asr_module_summary}, "真实ASR依赖未就绪，课程音频尚未完成冻结人工标注。"),
        item("T10", "AI质量", "角色判断", "准确率≥95%，高置信度跨角色写入0，低置信度必须阻断", "PARTIAL" if role_ok else "FAIL", {"role_gate": checks["role_gate"]["status"]}, "策略与低置信度门禁测试通过；仍需真实音频人工标注集计算准确率。"),
        item("T11", "AI质量", "知识检索", "Recall@5≥90%，引用完整率100%，无来源引用0", "NOT TESTED", {"demo_knowledge_checks": checks["knowledge_demo"]["status"] if knowledge_demo_ok else "FAIL"}, "当前仅有演示知识源；官方文档索引和40条冻结查询尚未完成。"),
        item("T12", "功能", "离线E2E", "断网后连续5次全流程PASS，Mock回退0", "BLOCKED", {"real_asr_runtime_available": real_asr_ready}, "真实ASR和真实本地LLM未就绪。"),
        item("T13", "可靠性", "异常恢复", "10个刷新、重启、失败重试场景恢复10/10，数据丢失和重复病历0", "PARTIAL" if recovery_ok else "FAIL", {"recovery": checks["recovery"]["status"]}, "自动化恢复测试通过；仍需按课程10场景进行真实运行和留证。"),
    ]


def _render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# EVT考核点一：13项测试真实基线",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- Git：`{report['git']['branch']}@{report['git']['sha']}`",
        f"- Python：`{report['environment']['python']}`",
        f"- 数据：`{report['inputs']['clinical_report']['path']}`（SHA256 `{report['inputs']['clinical_report']['sha256']}`）",
        "- 边界：这是开发机检查点证据；`PARTIAL` 不等于 EVT PASS，`HARDWARE BLOCKED` 不等于失败。",
        "",
        "| ID | 测试项 | 一票否决 | 当前结果 | 实测事实 | 尚未证明 |",
        "|---|---|---:|---|---|---|",
    ]
    for item in report["tests"]:
        measured = json.dumps(item["measured"], ensure_ascii=False, separators=(",", ":"))
        lines.append(
            f"| {item['id']} | {item['name']} | {'是' if item['veto'] else '否'} | **{item['status']}** | `{measured}` | {item['remaining_gap']} |"
        )
    lines += [
        "",
        "## 工程检查",
        "",
        "| 检查组 | 结果 | 耗时(s) | 命令 |",
        "|---|---|---:|---|",
    ]
    for check in report["engineering_checks"].values():
        lines.append(f"| {check['name']} | {check['status']} | {check['duration_seconds']} | `{' '.join(check['command'])}` |")
    lines += [
        "",
        "## 当前考核判断",
        "",
        f"- PASS：{report['summary']['PASS']}；PARTIAL：{report['summary']['PARTIAL']}；NOT TESTED：{report['summary']['NOT TESTED']}；BLOCKED：{report['summary']['BLOCKED']}；HARDWARE BLOCKED：{report['summary']['HARDWARE BLOCKED']}；FAIL：{report['summary']['FAIL']}。",
        "- 一票否决项尚无最终PASS，因此本次检查点不能宣称产品通过。",
        "- 下一验证：先导入三份官方发热/呼吸文档并建立FTS5查询基线，再处理真实音频与本地模型运行时。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the reproducible EVT checkpoint baseline.")
    parser.add_argument("--clinical-report", type=Path, required=True)
    parser.add_argument("--dependency-report", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()

    clinical = _load_json(args.clinical_report)
    dependencies = _load_json(args.dependency_report)
    checks = {name: _run_check_group(name, paths) for name, paths in CHECK_GROUPS.items()}
    tests = build_matrix(clinical, dependencies, checks)
    summary = {status: sum(item["status"] == status for item in tests) for status in ("PASS", "PARTIAL", "NOT TESTED", "BLOCKED", "HARDWARE BLOCKED", "FAIL")}
    report = {
        "schema_version": "evt_checkpoint_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "git": {"branch": _git_value("branch", "--show-current"), "sha": _git_value("rev-parse", "HEAD")},
        "environment": {"python": sys.version.split()[0], "platform": platform.platform()},
        "inputs": {
            "clinical_report": {"path": str(args.clinical_report), "sha256": _sha256(args.clinical_report)},
            "dependency_report": {"path": str(args.dependency_report), "sha256": _sha256(args.dependency_report)},
        },
        "engineering_checks": checks,
        "tests": tests,
        "summary": summary,
        "gate": "NEEDS VALIDATION",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(_render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": "ok", "summary": summary, "gate": report["gate"]}, ensure_ascii=False))
    return 0 if all(check["status"] == "PASS" for check in checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
