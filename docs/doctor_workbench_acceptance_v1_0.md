# 医生端工作台 v1.0 验收记录

验收日期：2026-07-14
验收入口：`http://127.0.0.1:<实际端口>/static/doctor.html`
运行方式：`docker compose up -d --build`
当前实测端口：`2644`
验收性质：课程工程交付版验收，不声明临床可用。

## 结论

医生端 v1.0 主流程可以用于课程展示：文本生成、病历草稿摘要、候选诊断、治疗方案、诊断证据、详情抽屉、字段确认、导出阻断和导出成功路径已形成闭环。真实 ASR 仍建议提前预热；现场保底路线为 Mock ASR。

## 验收项目

| 项目 | 结果 | 证据 |
| --- | --- | --- |
| Docker 端口预检 | 通过 | `python scripts/check_docker_port.py --start 2600 --end 2699 --format env` 输出 `MRA_HOST_PORT=2644` |
| 服务健康检查 | 通过 | `curl http://127.0.0.1:2644/health` 返回 `ok` |
| 医生端页面访问 | 通过 | `curl -I http://127.0.0.1:2644/static/doctor.html` 返回 200 |
| 文本生成病历 | 通过 | 可展示病历字段、质量状态、候选诊断和治疗建议 |
| 详情抽屉 | 通过 | 可展示字段质量、证据、导出阻断等详细信息 |
| 未确认导出阻断 | 通过 | 未确认字段时导出不可直接完成 |
| 确认后导出 | 通过 | 确认字段后可生成导出结果路径 |
| Mock ASR 保底 | 通过 | 可用于展示 SSE 和角色校正主流程 |
| FunASR 真实音频 | 可选通过 | 需提前预热，首次模型加载可能较慢 |

## 截图证据

- `docs/final_report/images/v0_9_6_frontend_polish/01_empty_1366x768.png`
- `docs/final_report/images/v0_9_6_frontend_polish/02_empty_1920x1080.png`
- `docs/final_report/images/v0_9_6_frontend_polish/03_text_generated_1366x768.png`
- `docs/final_report/images/v0_9_6_frontend_polish/04_quality_detail_drawer_1366x768.png`

## 已知边界

- 当前没有医院真实 PC 实机复测。
- 边缘端真实部署暂缓，不阻塞课程交付。
- 自动角色识别不是最终事实，仍需要医生校正。
- 候选诊断和治疗建议必须医生确认。

## 复测命令

```powershell
python scripts\check_docker_port.py --start 2600 --end 2699 --format env
$env:MRA_HOST_PORT = "2644"
docker compose up -d --build
curl.exe http://127.0.0.1:$env:MRA_HOST_PORT/health
curl.exe -I http://127.0.0.1:$env:MRA_HOST_PORT/static/doctor.html
pytest -q
node --check static\doctor.js
```
