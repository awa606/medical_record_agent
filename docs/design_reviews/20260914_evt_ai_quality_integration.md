# EVT AI Quality Integration — Engineering Design Review

- Review date: 2026-09-14
- Repository baseline: `codex/issue-41-role-policy-calibration@986e1c79`
- Integration source: `codex/medilisten-live-v1@dd75643`
- Owner: 李国毅
- Gate: **NEEDS VALIDATION**

## Goal and deliverables

The goal is to turn the existing demonstration branches into a reproducible local product baseline with quantitative tests, source-traceable fever/respiratory knowledge retrieval, and measured local-model improvement. The deliverables are an isolated integration branch, a stable test entry point, a 13-item EVT test matrix with real results, a versioned knowledge store and retrieval API, model evaluation/training pipelines, and Git/Obsidian evidence.

The first checkpoint serves the course assessor and the later artifacts serve developers and reviewers. Jetson acceptance, clinical deployment and autonomous diagnosis are outside the current validated scope.

## Inputs, outputs and constraints

Inputs include three course audio recordings, 23 synthetic ASR cases, 60 structured fever/respiratory cases, versioned official clinical documents and the current Git branches. Outputs are structured records, evidence-linked knowledge results, machine-readable evaluation reports and reproducible experiment manifests.

Constraints are a single owner, an existing dirty worktree, an RTX 5070 Laptop GPU with 8 GB VRAM, no available Jetson hardware, unverified clinical labels and a 2026-09-15 course checkpoint. Raw medical audio, downloaded corpora, model weights and secrets must not be pushed to GitHub.

## Assumptions

- **ASSUMPTION A01:** The 2026-09-15 checkpoint may use a clearly identified development-machine environment. Jetson-only checks remain `HARDWARE BLOCKED`.
- **ASSUMPTION A02:** The local Toyhom dialogue corpus is used only for language and stress-test mining; its answers are not clinical truth.
- **ASSUMPTION A03:** Fever/respiratory is the first knowledge pack. Oral-health content is a later, independently sourced pack.
- **ASSUMPTION A04:** Model checkpoints stay local; Git stores configuration, metrics, hashes and reproduction commands.

## PBS and architecture

The product breakdown is: reproducible runtime, EVT verification pack, audio/ASR dataset pack, local ASR and semantic model pack, source registry and knowledge index, evidence-linked retrieval interface, and release evidence.

Data flows from browser audio to ASR, speaker/role quality, clinical fact extraction, structured draft generation, knowledge retrieval, doctor review, revision storage and controlled export. SQLite owns application records and canonical knowledge metadata/text. The dense index is derived and rebuildable. Git owns source/configuration/evidence metadata; Obsidian owns task, schedule, risk and gate facts.

## Module boundaries and interfaces

| Module | Responsibility / owned data | Interface |
|---|---|---|
| ASR runtime | Decode audio and report model/runtime metrics | audio bytes/path → transcript, segments, timing or typed failure |
| Role quality | Assign or block uncertain speaker roles | segments → role decisions, confidence and violations |
| Clinical facts | Extract source-grounded structured facts | transcript → fields with source spans and missing/negated state |
| Knowledge ingest | Register, hash, parse and version approved documents | local manifest/PDF → source, document and chunk rows |
| Knowledge retrieve | Lexical/dense retrieval and citation assembly | query/fields → ranked chunks with scores and citations |
| Record workflow | Draft, review, revision and export gates | task/record actions → persisted revision or explicit rejection |
| Evaluation | Re-run metrics against frozen data | versioned manifest → JSON/Markdown report and exit code |

Existing read interfaces remain compatible: `GET /api/knowledge/sources`, `GET /api/knowledge/sources/{source_id}`, `POST /api/knowledge/retrieve`, and `GET /api/tasks/{task_id}/evidence`. Retrieval results may add document/chunk/version/page/hash and component-score fields. Import is local CLI-only in this phase.

## WBS, dependencies and critical path

New work is implemented inside the existing Alpha tasks: runtime/tests in 1.2; real providers in 1.3; ASR data and baseline in 2.2; role gates in 2.3; structured semantics/retrieval in 3.2; knowledge persistence in 4.1; citation/revision linkage in 4.2; and EVT execution in 5.1–5.4. Alpha+ owns interruption/recovery and idempotent re-indexing. Beta owns frozen quality data, training experiments and full regression.

The implementation dependency is: isolated branch → stable test runner → checkpoint baseline → branch integration → knowledge lexical MVP → dense/hybrid retrieval → ASR/semantic training experiments → reliability/full EVT regression. Project Planner remains the only authoritative calendar critical-path calculation; this review does not introduce a second CPM algorithm.

## Risks and validation plan

Primary risks are branch conflicts, Windows test infrastructure, low-quality or unlicensed labels, unsupported medical claims, model overfitting, 8 GB memory pressure, missing Jetson hardware, schedule compression and single-owner throughput. Mitigations are an isolated worktree, atomic commits, frozen holdouts, official-source allowlists, citation gates, baseline-before-training, local-only artifacts and honest BLOCKED/FAIL results.

Minimal validation is:

1. Resolve the integration in an isolated worktree and make the formal unit suite collect and run without scanning evidence snapshots.
2. Produce a real 13-item checkpoint baseline; unavailable tests remain NOT TESTED/BLOCKED.
3. Ingest three official documents, retrieve about 30 source-located chunks for 20 fixed queries, and prove citations and idempotent re-import.
4. Benchmark existing ASR engines and the 60-case structured pipeline before changing weights.

## Milestones and acceptance

- Checkpoint 1: reproducible function/interface/deployment evidence with no fabricated results.
- Alpha: local end-to-end workflow, source-linked knowledge MVP and evidence-backed gates.
- Alpha+: recording, task and index recovery under interruption.
- Beta/EVT: frozen metrics, Blocker/Critical = 0, veto tests PASS and complete regression evidence.

## Fixed five questions

1. **Why this split?** Each quality claim has one owner, one input/output boundary and one reproducible metric.
2. **Alternatives?** A wholesale branch replacement, a second vector database and immediate full-model training were considered; they increase conflict, duplicate facts or hide missing baselines.
3. **Most likely failure?** Branch/data provenance errors can produce convincing but invalid evidence.
4. **Lowest-cost validation?** Use the development machine, existing audio/cases, three official documents and smoke-sized training before any Jetson or full training commitment.
5. **Proof of completion?** Frozen datasets, rerunnable commands, raw JSON metrics, source hashes/citations, Git SHAs and five consecutive offline E2E runs.

## Design Review Gate

**NEEDS VALIDATION.** Implementation may proceed only through the four minimal validations above. A failed validation keeps the affected task IN PROGRESS or BLOCKED and prevents promotion of its model or gate.
