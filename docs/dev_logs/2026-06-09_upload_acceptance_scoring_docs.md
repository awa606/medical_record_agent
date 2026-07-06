# 2026-06-09 仓库上传验收与评分文档补齐

## 修改日期 / 时间

2026-06-09，时区：Asia/Shanghai

## 修改目标

按用户要求进行仓库上传验收，确认评分相关文件是否存在且已纳入 Git；补齐缺失的演示讲稿、代码讲解路线和演示验收清单。

## 修改前问题

- `docs/scoring/demo_script.md` 缺失。
- `docs/scoring/code_walkthrough.md` 缺失。
- `docs/scoring/demo_checklist.md` 缺失。
- 其他评分文档、Prompt 示例和脚本已纳入 Git。

## 输入

- 用户要求运行 `git status --short` 和 `git status --ignored --short`。
- 用户指定必须确认的评分文档和脚本清单。
- 当前 Git 状态与已推送提交 `cc595a1`。

## 输出

- 新增现场演示讲稿。
- 新增代码讲解路线。
- 新增演示验收清单。
- 新增本次上传验收开发日志。

## 修改文件

- `docs/scoring/demo_script.md`
- `docs/scoring/code_walkthrough.md`
- `docs/scoring/demo_checklist.md`
- `docs/dev_logs/2026-06-09_upload_acceptance_scoring_docs.md`

## 关键设计决策

- 不新增业务功能，不改后端和前端。
- 只补课程评分所需文档，服务现场演示、代码展示和验收自检。
- 不强行上传 `data/`、`video/`、`.venv/`、数据库、模型权重和缓存。

## 验证步骤

1. 运行 `git status --short`。
2. 运行 `git status --ignored --short`。
3. 使用 `git ls-files --error-unmatch` 检查用户指定文件是否纳入 Git。
4. 暂存新增评分文档和本日志。
5. 检查暂存文件不包含数据、音频、模型或缓存。
6. 提交并推送到 GitHub。

## 验证结果

- 已运行 `git status --short`，确认 `medical_record_agent` 目标文件无未提交改动；存在的未提交项来自其他课程目录或仓库根部。
- 已运行 `git status --ignored --short`，确认 `.venv/`、`data/uploads/`、`data/medical_record_agent.sqlite3`、`data/outputs/`、`video/`、模型文件和缓存处于忽略列表。
- 已使用 `git ls-files --error-unmatch` 检查用户指定文件；补齐前 3 个 `docs/scoring/demo_*.md` / `code_walkthrough.md` 文件缺失，补齐后纳入本次提交。
- 已运行 `git diff --cached --check`，通过。
- 暂存文件仅包含评分文档和本次验收日志，不包含数据、音频、模型或缓存。

## 未解决问题

- 仓库根部和其他课程目录存在未提交改动，本次不处理。

## 下一步计划

- 汇报前按 `docs/scoring/demo_checklist.md` 完成现场演示自检。
