from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from app.services.knowledge_store import retrieve_knowledge


REQUIRED_CITATION_FIELDS = {
    "document_id",
    "chunk_id",
    "publisher",
    "version",
    "section",
    "page",
    "source_url",
    "content_sha256",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, check=True, capture_output=True, text=True, encoding="utf-8"
    ).stdout.strip()


def evaluate(dataset: dict[str, Any], *, limit: int = 5) -> dict[str, Any]:
    cases: list[dict[str, Any]] = []
    relevant_hit = 0
    citation_total = 0
    citation_complete = 0
    source_less = 0
    modes: set[str] = set()
    for item in dataset["queries"]:
        retrieval = retrieve_knowledge(item["query"], limit=limit)
        modes.add(retrieval["retrieval_mode"])
        results = retrieval["results"]
        retrieved_source_ids = [result["source_id"] for result in results]
        hit = bool(set(item["relevant_source_ids"]) & set(retrieved_source_ids))
        relevant_hit += int(hit)
        for result in results:
            citation_total += 1
            complete = all(result.get(field) not in (None, "") for field in REQUIRED_CITATION_FIELDS)
            citation_complete += int(complete)
            source_less += int(not result.get("source_url"))
        cases.append(
            {
                **item,
                "hit_at_5": hit,
                "retrieved": [
                    {
                        "rank": rank,
                        "source_id": result["source_id"],
                        "document_id": result["document_id"],
                        "chunk_id": result["chunk_id"],
                        "page": result["page"],
                        "section": result["section"],
                        "content_sha256": result["content_sha256"],
                        "lexical_score": result["lexical_score"],
                        "dense_score": result["dense_score"],
                        "score": result["score"],
                    }
                    for rank, result in enumerate(results, start=1)
                ],
            }
        )
    query_count = len(cases)
    return {
        "query_count": query_count,
        "recall_at_5": round(relevant_hit / query_count, 4) if query_count else None,
        "relevant_hit_count": relevant_hit,
        "citation_result_count": citation_total,
        "citation_complete_count": citation_complete,
        "citation_completeness": round(citation_complete / citation_total, 4) if citation_total else None,
        "source_less_citation_count": source_less,
        "retrieval_modes": sorted(modes),
        "cases": cases,
    }


def _markdown(report: dict[str, Any]) -> str:
    metric = report["metrics"]
    lines = [
        "# 发热/呼吸知识库检索基线",
        "",
        f"- 生成时间：{report['generated_at']}",
        f"- Git SHA：`{report['git_sha']}`",
        f"- 数据集：`{report['dataset_id']}`（{metric['query_count']}条开发查询）",
        f"- 模式：`{', '.join(metric['retrieval_modes'])}`",
        f"- Recall@5：**{metric['recall_at_5']:.1%}**（{metric['relevant_hit_count']}/{metric['query_count']}）",
        f"- 引用完整率：**{metric['citation_completeness']:.1%}**（{metric['citation_complete_count']}/{metric['citation_result_count']}）",
        f"- 无来源引用：**{metric['source_less_citation_count']}**",
        "- 边界：这是20条开发MVP的来源级标签；尚未达到最终120条、40条冻结测试集要求。",
        "",
        "| 查询 | 相关来源 | Top-5命中 | 前三结果（来源/页码） |",
        "|---|---|---:|---|",
    ]
    for case in metric["cases"]:
        top = "；".join(f"{row['source_id']}/p.{row['page']}" for row in case["retrieved"][:3])
        lines.append(f"| {case['query_id']} {case['query']} | {', '.join(case['relevant_source_ids'])} | {'PASS' if case['hit_at_5'] else 'FAIL'} | {top} |")
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate the local knowledge retrieval baseline.")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-markdown", type=Path, required=True)
    args = parser.parse_args()
    os.environ["MEDICAL_RECORD_AGENT_DB"] = str(args.db.resolve())
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    metrics = evaluate(dataset)
    report = {
        "schema_version": "knowledge_retrieval_report_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "dataset_id": dataset["dataset_id"],
        "dataset_sha256": _sha256(args.dataset),
        "metrics": metrics,
        "gate": "PASS" if metrics["recall_at_5"] >= 0.9 and metrics["citation_completeness"] == 1 and metrics["source_less_citation_count"] == 0 else "NEEDS VALIDATION",
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.output_markdown.write_text(_markdown(report), encoding="utf-8")
    print(json.dumps({"status": "ok", "recall_at_5": metrics["recall_at_5"], "citation_completeness": metrics["citation_completeness"], "source_less_citation_count": metrics["source_less_citation_count"], "gate": report["gate"]}, ensure_ascii=False))
    return 0 if report["gate"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
