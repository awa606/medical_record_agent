# 发热/呼吸知识库 V1

本目录记录知识库的可复现配置与指标。原始 PDF、SQLite 索引、OCR 中间文件和模型权重保存在本机 `.artifacts/knowledge/`，不进入 Git。

## 数据边界

- 首批来源只包含国家卫生健康部门发布的流感、新型冠状病毒感染和儿童肺炎支原体肺炎资料。
- 每个正式片段必须保留来源、版本、章节、页码、URL 和内容 SHA256。
- 检索结果只作为医生人工核验依据，不能自动批准病历、诊断或治疗，也不能替代音频原文证据。
- 当前 20 条查询是开发用来源级标签。最终 T11 仍需至少 120 条复核查询，其中 40 条为冻结测试集，并改用片段级相关性标注。

## 重建命令

```powershell
python -m pip install -r requirements-knowledge.txt

python scripts/ingest_knowledge.py `
  --manifest config/knowledge/fever_respiratory_v1.json `
  --source-root .artifacts/knowledge/sources `
  --db .artifacts/knowledge/knowledge_v1.sqlite3 `
  --report .artifacts/knowledge/ingest_report.json

python scripts/evaluate_knowledge_retrieval.py `
  --db .artifacts/knowledge/knowledge_v1.sqlite3 `
  --dataset data/knowledge/eval/fever_respiratory_queries_v1.json `
  --output-json .artifacts/knowledge/retrieval_fts5.json `
  --output-markdown .artifacts/knowledge/retrieval_fts5.md
```

加入 `--build-embeddings` 后，导入脚本会使用 `BAAI/bge-small-zh-v1.5` 建立可重建的向量派生索引；API 在向量存在时返回 `hybrid_v1`，否则返回 `fts5_v1`。

## 当前工程门禁

30 个页码可定位片段和 20 条开发查询只满足最小闭环验证。开发集指标达到阈值不等于课程 T11 PASS，也不代表 Alpha Exit。
