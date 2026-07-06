# 期末报告正式版整理

## 修改日期 / 时间

2026-06-20，时区：Asia/Shanghai

## 修改目标

进入期末报告正式版整理阶段，不继续开发新功能，不修改后端业务逻辑、ASR/LLM 实现或医生端 UI，只基于当前项目代码、评分材料、开发日志和运行日志生成正式报告提交材料。

## 修改前问题

- 已有 `docs/scoring/final_report_draft.md` 是初稿，缺少封面、摘要、关键词、目录、截图占位、附录和提交说明。
- 已有 `docs/scoring/progress_dashboard.md` 和运行日志，但还没有统一的 `docs/final_report/` 目录承载正式提交材料。
- 报告提交前需要明确哪些截图要插入、哪些材料不能提交，以及如何导出 Word。

## 输入

- `docs/scoring/final_report_draft.md`
- `docs/scoring/progress_dashboard.md`
- `docs/dev_logs/2026-06-20_scoring_final_report_materials.md`
- `docs/dev_logs/runs/2026-06-20_fever_01_final_demo.md`
- 当前医生端、调试台、Agent Trace、Task Steps 和运行日志机制
- 用户关于正式报告整理阶段的要求

## 输出

- 新建 `docs/final_report/` 目录。
- 新增正式版报告 Markdown。
- 新增截图清单。
- 新增报告提交检查清单。
- 新增 final_report 目录 README。
- 新增可选 Word 导出脚本。

## 修改文件

- `docs/final_report/AI生成式电子病历辅助系统_期末报告_正式版.md`
- `docs/final_report/截图清单.md`
- `docs/final_report/报告提交检查清单.md`
- `docs/final_report/README.md`
- `scripts/export_final_report_docx.py`
- `docs/dev_logs/2026-06-20_final_report_formalization.md`

## 关键设计决策

- 正式报告继续明确课程 POC 边界，不把系统描述成真实临床产品。
- 报告正文保留 12 章结构，并新增封面、摘要、关键词、目录、截图占位、提交说明和附录。
- 附录直接映射评分细则、运行日志、核心代码、截图和开发日志，方便答辩查证。
- Word 导出脚本作为可选工具：如果 `python-docx` 不存在，只提示安装命令，不影响 Markdown 报告提交。
- 不修改 `app/` 业务逻辑，不修改 ASR/LLM 实现，不优化前端 UI，不处理其他课程目录。

## 验证步骤

1. 运行：

```powershell
git diff --check -- docs/final_report docs/dev_logs/2026-06-20_final_report_formalization.md
```

2. 如果新增 Word 导出脚本，运行：

```powershell
python scripts/export_final_report_docx.py
```

3. 检查 `docs/final_report/AI生成式电子病历辅助系统_期末报告_正式版.docx` 是否生成。

## 验证结果

- `git diff --check -- docs/final_report docs/dev_logs/2026-06-20_final_report_formalization.md` 通过。
- `python -m py_compile scripts\export_final_report_docx.py` 通过。
- `python scripts\export_final_report_docx.py` 执行成功。
- 已生成 Word 文件：`docs/final_report/AI生成式电子病历辅助系统_期末报告_正式版.docx`。

## 未解决问题

- 报告封面中的小组成员、指导老师、学院 / 专业仍需人工填写。
- 正式报告截图尚未实际插入，需要按 `截图清单.md` 采集并补充。
- Word 导出脚本只提供基础格式，最终页眉页脚、自动目录、图片编号和分页仍建议人工检查。

## 下一步计划

- 按截图清单采集并插入 10 张关键截图。
- 人工补齐封面信息。
- 导出 Word 后检查格式，必要时在 Word 中调整目录、页码、图片和表格。
- 用户确认后再按具体文件路径执行 git add / commit / push，不使用 `git add .`。
