"""Verify public artifacts only; never imports the app or accesses a database."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
read = lambda name: json.loads((ROOT / name).read_text(encoding="utf-8"))
manifest = read("publication_manifest.json")
for item in manifest["files"]:
    path = ROOT / item["path"]
    assert path.parent.resolve() == ROOT.resolve()
    assert path.stat().st_size == item["bytes"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item["sha256"]
queries = read("queries24.preregistered.json")["queries"]
assert len(queries) == 24 and len({row["query_id"] for row in queries}) == 24
assert sum(bool(row["relevant_locators"]) for row in queries) == 15
sources = read("source_sha_manifest.json")
assert len(sources["chunks"]) == 79 and sum(row["active"] for row in sources["chunks"]) == 78
assert not sources["contents_included"] and not sources["vectors_included"]
assert all("content" not in row and "vector_json" not in row for row in sources["chunks"])
assert read("invalid-empty-index-fixture.json")["validity"] == "INVALID_HARNESS"
result = read("fts-results.json")["summary"]
assert result["fts_current"]["chunk_hit_count"] == result["fts_population_filter"]["chunk_hit_count"] == 8
assert result["fts_current"]["population_ineligible_results"] == 30
assert result["fts_population_filter"]["population_ineligible_results"] == 0
assert result["fts_current"]["no_answer_false_return_count"] == result["fts_population_filter"]["no_answer_false_return_count"] == 9
assert not read("bge-equivalence.json")["matched"]
assert sum(row["matched"] for row in read("bge-equivalence.json")["checks"]) == 2
print("公开清单校验通过：24 条冻结问题、79 个片段元数据、FTS 有效/失效记录和 BGE 停止证据一致；无检索或模型重跑。")
