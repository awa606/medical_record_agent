"""Run a bounded local LoRA smoke for transcript-to-structured-facts.

The adapter, generated text and model cache stay under .artifacts. The report
contains aggregate metrics and case-level pass facts only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from scripts.semantic_scoring import score_output
except ModuleNotFoundError:  # direct script execution
    from semantic_scoring import score_output


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "Qwen/Qwen2.5-0.5B-Instruct"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=PROJECT_ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _prompt(tokenizer, example: dict[str, Any]) -> str:
    return tokenizer.apply_chat_template(
        [
            {"role": "system", "content": example["system"]},
            {"role": "user", "content": example["input"]},
        ],
        tokenize=False,
        add_generation_prompt=True,
    )


def _training_item(tokenizer, example: dict[str, Any], max_length: int) -> dict[str, torch.Tensor]:
    prompt = _prompt(tokenizer, example)
    target = json.dumps(example["target"], ensure_ascii=False, separators=(",", ":"))
    prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
    full_ids = tokenizer(prompt + target + tokenizer.eos_token, add_special_tokens=False)["input_ids"][:max_length]
    labels = [-100] * min(len(prompt_ids), len(full_ids)) + full_ids[min(len(prompt_ids), len(full_ids)) :]
    return {
        "input_ids": torch.tensor([full_ids], dtype=torch.long),
        "attention_mask": torch.ones((1, len(full_ids)), dtype=torch.long),
        "labels": torch.tensor([labels], dtype=torch.long),
    }


def _validation_loss(model, tokenizer, rows: list[dict[str, Any]], device: torch.device, max_length: int) -> float:
    losses: list[float] = []
    model.eval()
    with torch.inference_mode():
        for row in rows:
            item = {key: value.to(device) for key, value in _training_item(tokenizer, row, max_length).items()}
            losses.append(float(model(**item).loss.detach().cpu()))
    return round(mean(losses), 6)


def _evaluate(model, tokenizer, rows: list[dict[str, Any]], device: torch.device, max_new_tokens: int) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    model.eval()
    tokenizer.padding_side = "left"
    for row in rows:
        prompt = _prompt(tokenizer, row)
        encoded = tokenizer(prompt, return_tensors="pt", add_special_tokens=False).to(device)
        with torch.inference_mode():
            output = model.generate(
                **encoded,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=tokenizer.pad_token_id,
                eos_token_id=tokenizer.eos_token_id,
            )
        generated = tokenizer.decode(output[0, encoded["input_ids"].shape[1] :], skip_special_tokens=True)
        case_results.append(score_output(row["case_id"], row["target"], generated))
    return {
        "case_count": len(case_results),
        "valid_json_rate": round(mean(float(row["valid_json"]) for row in case_results), 6),
        "schema_complete_rate": round(mean(float(row["schema_complete"]) for row in case_results), 6),
        "fact_recall": round(mean(row["fact_recall"] for row in case_results), 6),
        "field_status_accuracy": round(mean(row["field_status_accuracy"] for row in case_results), 6),
        "unsupported_fact_count": sum(row["unsupported_fact_count"] for row in case_results),
        "cases": case_results,
    }


def _render(report: dict[str, Any]) -> str:
    base = report["frozen_test"]["base"]
    trained = report["frozen_test"]["lora"]
    lines = [
        "# 本地语义结构化 LoRA Smoke",
        "",
        f"- 执行时间：{report['generated_at']}",
        f"- Git SHA：`{report['git_sha']}`",
        f"- 基础模型：`{report['model_id']}`",
        f"- 数据划分：{report['dataset']['train']} / {report['dataset']['validation']} / {report['dataset']['frozen_test']}",
        f"- 优化步数：{report['training']['optimizer_steps']}",
        f"- 初始/最终验证损失：{report['training']['validation_loss_before']} / {report['training']['validation_loss_after']}",
        f"- 候选门禁：**{report['promotion_gate']}**",
        "",
        "| 冻结集指标 | 基础模型 | LoRA |",
        "|---|---:|---:|",
        f"| JSON有效率 | {base['valid_json_rate']:.1%} | {trained['valid_json_rate']:.1%} |",
        f"| Schema完整率 | {base['schema_complete_rate']:.1%} | {trained['schema_complete_rate']:.1%} |",
        f"| 事实召回 | {base['fact_recall']:.1%} | {trained['fact_recall']:.1%} |",
        f"| 字段状态准确率 | {base['field_status_accuracy']:.1%} | {trained['field_status_accuracy']:.1%} |",
        f"| 无依据事实数 | {base['unsupported_fact_count']} | {trained['unsupported_fact_count']} |",
        "",
        "## 边界",
        "",
        "- 只训练转写文本到明确事实和字段状态，不训练诊断或治疗建议。",
        "- 适配器、生成文本和模型权重仅保存在 `.artifacts`，不进入 Git。",
        "- 只有冻结集结构指标提高、无依据事实为0且安全门禁不退化，才能成为候选；本次 smoke 不会自动接入生产。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a bounded local semantic LoRA smoke.")
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report-json", type=Path, required=True)
    parser.add_argument("--report-markdown", type=Path, required=True)
    parser.add_argument("--model-id", default=DEFAULT_MODEL)
    parser.add_argument("--allow-model-download", action="store_true")
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--max-length", type=int, default=640)
    parser.add_argument("--max-new-tokens", type=int, default=160)
    parser.add_argument("--seed", type=int, default=20260914)
    args = parser.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    if not torch.cuda.is_available():
        raise RuntimeError("LoRA smoke requires CUDA for the selected local model")
    device = torch.device("cuda")
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, local_files_only=not args.allow_model_download)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        dtype=torch.float16,
        local_files_only=not args.allow_model_download,
    ).to(device)
    model.config.use_cache = True

    train_rows = _load_jsonl(args.dataset_dir / "train.jsonl")
    validation_rows = _load_jsonl(args.dataset_dir / "validation.jsonl")
    frozen_rows = _load_jsonl(args.dataset_dir / "frozen_test.jsonl")
    if (len(train_rows), len(validation_rows), len(frozen_rows)) != (30, 10, 20):
        raise ValueError("semantic dataset must use the fixed 30/10/20 split")

    started = time.perf_counter()
    baseline_metrics = _evaluate(model, tokenizer, frozen_rows, device, args.max_new_tokens)
    validation_before = _validation_loss(model, tokenizer, validation_rows, device, args.max_length)
    lora = LoraConfig(
        r=8,
        lora_alpha=16,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora)
    model.config.use_cache = False
    trainable = sum(parameter.numel() for parameter in model.parameters() if parameter.requires_grad)
    total = sum(parameter.numel() for parameter in model.parameters())
    optimizer = torch.optim.AdamW((parameter for parameter in model.parameters() if parameter.requires_grad), lr=2e-4)
    losses: list[float] = []
    order = list(range(len(train_rows)))
    optimizer.zero_grad(set_to_none=True)
    model.train()
    for step in range(args.max_steps):
        if step % len(order) == 0:
            random.shuffle(order)
        row = train_rows[order[step % len(order)]]
        item = {key: value.to(device) for key, value in _training_item(tokenizer, row, args.max_length).items()}
        loss = model(**item).loss
        if not torch.isfinite(loss):
            raise RuntimeError(f"non-finite training loss at step {step + 1}")
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        optimizer.zero_grad(set_to_none=True)
        losses.append(float(loss.detach().cpu()))
    validation_after = _validation_loss(model, tokenizer, validation_rows, device, args.max_length)
    model.config.use_cache = True
    lora_metrics = _evaluate(model, tokenizer, frozen_rows, device, args.max_new_tokens)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    adapter_dir = args.output_dir / "adapter"
    model.save_pretrained(adapter_dir, safe_serialization=True)
    tokenizer.save_pretrained(adapter_dir)
    adapter_artifacts = {
        path.name: {"size_bytes": path.stat().st_size, "sha256": _sha256(path)}
        for path in sorted(adapter_dir.iterdir())
        if path.is_file()
    }

    improved = (
        lora_metrics["schema_complete_rate"] > baseline_metrics["schema_complete_rate"]
        and lora_metrics["fact_recall"] >= baseline_metrics["fact_recall"]
        and lora_metrics["field_status_accuracy"] >= baseline_metrics["field_status_accuracy"]
        and lora_metrics["unsupported_fact_count"] == 0
    )
    report = {
        "schema_version": "semantic_lora_smoke_report_v1",
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "git_sha": _git_sha(),
        "model_id": args.model_id,
        "model_revision": getattr(model.config, "_commit_hash", None),
        "dataset_manifest_sha256": _sha256(args.dataset_manifest),
        "dataset": {"train": len(train_rows), "validation": len(validation_rows), "frozen_test": len(frozen_rows)},
        "training": {
            "optimizer_steps": args.max_steps,
            "learning_rate": 2e-4,
            "lora_r": 8,
            "lora_alpha": 16,
            "trainable_parameters": trainable,
            "total_parameters_with_adapter": total,
            "train_loss_first": round(losses[0], 6),
            "train_loss_last": round(losses[-1], 6),
            "validation_loss_before": validation_before,
            "validation_loss_after": validation_after,
            "elapsed_seconds": round(time.perf_counter() - started, 3),
            "gpu": torch.cuda.get_device_name(0),
            "peak_cuda_memory_mb": round(torch.cuda.max_memory_allocated() / 1024 / 1024, 2),
        },
        "frozen_test": {"base": baseline_metrics, "lora": lora_metrics},
        "adapter_artifacts": adapter_artifacts,
        "promotion_gate": "PASS" if improved else "NEEDS_VALIDATION",
        "production_model_changed": False,
    }
    args.report_json.parent.mkdir(parents=True, exist_ok=True)
    args.report_markdown.parent.mkdir(parents=True, exist_ok=True)
    args.report_json.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.report_markdown.write_text(_render(report), encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "validation_loss_before": validation_before,
                "validation_loss_after": validation_after,
                "base_schema": baseline_metrics["schema_complete_rate"],
                "lora_schema": lora_metrics["schema_complete_rate"],
                "promotion_gate": report["promotion_gate"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
