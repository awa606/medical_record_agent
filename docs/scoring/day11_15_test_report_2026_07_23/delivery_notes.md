# 交付说明

本目录为 AI 生成式电子病历辅助系统 Day11-Day15 自主测试与优化复盘交付包。

## 建议提交文件

- AI生成式电子病历辅助系统_Day11-15自主测试报告_20260723.docx
- Bug_List_Day11.csv
- System_Test_Record_Day12-14.csv
- Day11-15_Task_Record.csv

## 证据附件

- text_chinese_smoke_summary.json：有效中文文本生成病历 smoke 结果。
- valid_chinese_export_summary.json：审核与导出下载验证结果。
- audio_direct_smoke_summary.json：Mock 音频与 FunASR 音频验证结果。
- docker_status_log.md：Docker 服务状态与日志摘要。
- task_15_valid_chinese_export.md / .docx：有效中文病例导出样本。
- raw_test_log.md：自动化测试原始命令摘要。

## 展示建议

明天展示优先走文本生成闭环：登录、工作台、文本输入、生成结构化病历、候选诊断与证据、保存修改、完成审核、导出已审核病历。

真实 FunASR 音频在当前 Docker 环境中受 ModelScope DNS/模型缓存影响，会超时，不建议现场等待；可说明音频入口已接通，真实模型需预置模型缓存或修复网络后再做稳定演示。
