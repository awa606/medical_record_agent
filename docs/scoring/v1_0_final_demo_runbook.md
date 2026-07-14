# v1.0 最终演示 Runbook

## 0. 开场前检查

```powershell
python scripts\check_docker_port.py --start 2600 --end 2699 --format env
$env:MRA_HOST_PORT = "2644"
docker compose up -d --build
curl.exe http://127.0.0.1:$env:MRA_HOST_PORT/health
node --check static\doctor.js
```

预期结果：

- Docker 容器正在运行。
- `/health` 返回 `ok`。
- 浏览器可以打开 `http://127.0.0.1:<实际端口>/static/doctor.html`。

## 1. 推荐演示主线

1. 展示 GitHub Release：说明当前是 `v1.0` 课程工程交付版。
2. 打开医生端页面，说明三栏结构：病历草稿、对话转写、AI 辅助。
3. 点击“输入方式 -> 文本生成”，生成病历草稿。
4. 展示字段摘要、质量标签、候选诊断、治疗方案和诊断证据。
5. 打开详情抽屉，展示证据、质量原因和导出阻断原因。
6. 点击“确认导出”，先展示未确认字段时被阻断。
7. 点击“确认字段”，再展示导出成功路径。
8. 如时间允许，切换 Mock ASR 展示 SSE 转写和角色校正。
9. 如模型已预热，再展示 FunASR 真实音频；否则说明真实 ASR 已有评测和截图证据。

## 2. 现场话术

- “本系统是课程工程原型，不是临床自动诊断产品。”
- “系统输出的是病历草稿、候选诊断、治疗建议和风险提醒，导出前必须医生确认。”
- “本周重点是把工程闭环做完整：ASR、病历质量、导出、Docker、GitHub Release 和评审材料。”
- “医院真实 PC 和边缘端部署还没有实机条件，所以目前只做配置建议和后续计划。”
- “现场如果真实 ASR 首次加载较慢，会使用 Mock ASR 保底展示主流程。”

## 3. 卡住时处理

| 现象 | 处理 |
| --- | --- |
| 端口无法访问 | 重新运行端口预检，换用脚本推荐端口 |
| FunASR 首次加载慢 | 切回 Mock ASR，说明真实模型需要预热 |
| 页面缓存旧样式 | 强制刷新页面或重建 Docker |
| 导出按钮不可用 | 打开详情抽屉，展示阻断原因和医生确认边界 |
| 被问到边缘端部署 | 回答已形成配置建议，但需要医院设备和合规条件确认后再实机部署 |

## 4. 收尾文件

- `docs/scoring/v0_9_8_week_review_material.md`
- `docs/scoring/v0_9_8_week_review_talk_track.md`
- `docs/scoring/v0_9_8_claude_design_ppt_prompt.md`
- `docs/scoring/v1_0_final_freeze_checklist.md`
- `docs/doctor_workbench_acceptance_v1_0.md`
- `homework/Medical_Record_Agent_v0.9.8_week_review_package.docx`
