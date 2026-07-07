# 工程规则

本文是 Medical Record Agent 的工程约束入口。所有后续开发、调试、文档和版本归档必须遵守本规则。

## 变更控制

- 不做随机重构。
- 只修改用户明确要求、Issue 明确覆盖或验证证明已经损坏的内容。
- 未经需求要求，不修改核心算法逻辑、运行时 API、数据库结构或测试语义。

## 目录职责

- `docs/`：架构、版本、调试、评分和交接文档。
- `logs/`：每日工作日志和 Bug 调试报告。
- `versions/`：里程碑快照说明和验收证据索引。
- `.github/`：Issue 模板、PR 模板和协作流程。

## 可追踪性

- 每个功能必须对应 GitHub Issue。
- 每个 Bug 必须有 `/logs/debug/` 调试报告。
- 每个工作日必须有 `/logs/daily/YYYY-MM-DD.md`。
- 每个里程碑必须在 `versions/` 中有目录和说明。

## 标准版本线

- `v0.1`：basic ASR pipeline。
- `v0.2`：SSE 实时流式转写。
- `v0.2.1`：ASR session SSE file streaming。
- `v0.3`：role separation。
- `v0.4`：medical reasoning。
- `v1.0`：deployable system。

## 调试纪律

每条调试记录必须包含：

- cause
- reproduction steps
- fix
- verification

## 提交规范

- `feat:` new feature
- `fix:` bug fix
- `refactor:` structural change
- `docs:` documentation update
- `test:` testing

优先级顺序：系统稳定性、可追踪性、模块化，然后才是优化。
