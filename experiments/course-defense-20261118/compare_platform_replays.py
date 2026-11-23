"""Recompute the predeclared classroom comparison from two completed deployments."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
from statistics import median

import pymupdf


def summarize(directory):
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    assert result["status"] == "PASS" and result["signed_revision"] == 3
    assert result["field_count"] == 24 and result["live_model_calls"] == 0
    assert result["unsigned_export_http"] == 400 and [s for _, s in result["actions_http"]] == [200] * 4
    pdf = directory / "合成病例_R3.pdf"
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == result["pdf_sha256"]
    with pymupdf.open(pdf) as document:
        assert len(document) == 1
        content = document[0].get_text()
    assert all(word in content for word in ("昨天吃过一次布洛芬", "没有胸痛", "已完成医生分项审核"))
    # Only these two label-bound clock values are allowed to vary between actual runs.
    pattern = r"((?:就诊时间|导出时间)\s*\n)\d{4}-\d\d-\d\d \d\d:\d\d\s+UTC\+08:00"
    normalized, n = re.subn(pattern, r"\1<本次实际时刻 UTC+08:00>", content)
    assert n == 2, "两项时间须展示明确时区"
    result["pdf_text_hash_without_times"] = hashlib.sha256(normalized.encode()).hexdigest()
    stats = {}
    for name in ("queue", "encounter", "task"):
        samples = sorted(result["samples_ms"][name])
        assert len(samples) == 30 and all(x >= 0 for x in samples)
        stats[name] = (median(samples), samples[math.ceil(.95 * len(samples)) - 1])
    return result, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("windows", type=Path)
    parser.add_argument("linux", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    win, ws = summarize(args.windows)
    linux, ls = summarize(args.linux)
    assert win["os"].startswith("Windows") and linux["os"].startswith("Linux")
    for key in ("runtime_sha256", "files_sha256", "review_actions_sha256", "first_field_hash",
                "final_field_hash", "pdf_text_hash_without_times"):
        assert win[key] == linux[key], key
    rows = []
    passed = True
    for name, label in (("queue", "就诊队列"), ("encounter", "就诊详情"), ("task", "病历任务详情")):
        wm, wp = ws[name]
        lm, lp = ls[name]
        diff = abs(wp - lp)
        ok = max(wp, lp) <= 2000 and diff <= 250
        passed &= ok
        rows.append(f"| {label} | {wm:.1f} / {wp:.1f} | {lm:.1f} / {lp:.1f} | {diff:.1f} | {'通过' if ok else '未通过'} |")
    conclusion = "通过" if passed else "未通过"
    args.out.write_text("\n".join([
        "# 课堂固定病例双平台复测", "",
        f"同版软件部署在 Windows 11 本机及 Debian 12 容器（Docker Desktop / WSL2），共用一台物理电脑。功能一致性通过，预登记的小负载性能预算{conclusion}。评委对学校条款作最终认定。", "",
        "两端各建一份空库，逐字节核对启动器、回放适配器、冻结问诊与首响应。独立比对 24 个首稿字段组成的完整树，及两处修改后的完整字段树。未签署导出均返回 400，两次保存、签署、导出均成功，下载的是已签署的 R3。两份 PDF 各一页，包含补回的布洛芬与修订后症状；两项时刻均标明 UTC+08:00，遮掉各自实际就诊与导出时刻后，两份全文相同。", "",
        "| 每项各 30 次 | Windows 中位 / P95（ms） | Linux 中位 / P95（ms） | P95 绝对差（ms） | 预算 |",
        "|---|---:|---:|---:|---|", *rows, "",
        f"首次启动就绪约 {win['startup_ms']/1000:.2f} 秒及 {linux['startup_ms']/1000:.2f} 秒。运行清单 SHA-256 为 `{win['runtime_sha256']}`。本轮使用一个固定合成病例、一个模拟医生身份，每端 90 次计时读取。Windows 端另有浏览器按钮复核，Linux 端通过本机 HTTP 走审核与导出。两端各回放一次，在线模型调用为零。", "",
        f"[Windows 原始样本]({args.windows.name}/result.json) · [Linux 原始样本]({args.linux.name}/result.json) · [Windows 签署 PDF]({args.windows.name}/合成病例_R3.pdf) · [Linux 签署 PDF]({args.linux.name}/合成病例_R3.pdf) · [实测口径](实测口径.md)", ""
    ]), encoding="utf-8")
    if not passed:
        raise SystemExit("两平台小负载性能对照未通过")


if __name__ == "__main__":
    main()
