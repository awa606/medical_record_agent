# 调试记录规范

本文规定 Medical Record Agent 的调试记录方式，确保问题可复现、可追踪、可验收。

## 基本规则

- 所有 Bug 必须先创建 GitHub Issue，并使用 `.github/ISSUE_TEMPLATE/bug.md`。
- 所有 Bug 修复必须在 `/logs/debug/` 新增或更新调试报告。
- 每个工作日必须在 `/logs/daily/YYYY-MM-DD.md` 记录当天变更、验证和风险。
- 每个功能必须对应一个 Issue；没有 Issue 的功能不得直接合并。
- 每个调试报告必须包含 cause、reproduction steps、fix、verification。
- 调试记录不得包含真实患者数据、真实 API Key、医院系统凭据或模型权重。

## 调试报告命名

```text
logs/debug/YYYY-MM-DD_issue-<id>_<short-title>.md
```

示例：

```text
logs/debug/2026-07-06_issue-12_audio-upload-503.md
```

## 推荐内容

调试报告使用 `logs/template.md`，至少包含：

- Problem
- Steps to reproduce
- Expected vs actual
- Root cause
- Fix
- Verification

## 验证要求

提交前至少执行：

```powershell
git diff --check
$env:PYTHONPATH = (Get-Location).Path
pytest -q
```

如果某项验证无法运行，必须在日志中说明原因、影响和后续处理方式。
