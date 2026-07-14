# v1.0 最终冻结检查清单

冻结日期：2026-07-14
冻结范围：课程工程交付版，不声明临床可用。

## 当前版本定位

- 发布版本：`v1.0`
- 基线来源：`v0.9.8 Release Candidate`
- 交付形态：本机 Docker + 局域网演示 + GitHub Release + 周评审材料
- 边缘端：暂不真实部署，仅保留配置建议和后续实机复测计划

## 可提交材料

- `README.md`
- `docs/版本演进记录.md`
- `docs/能力证据追踪矩阵.md`
- `docs/docker_local_deploy.md`
- `docs/scoring/v0_9_8_week_review_material.md`
- `docs/scoring/v0_9_8_week_review_talk_track.md`
- `docs/scoring/v0_9_8_claude_design_ppt_prompt.md`
- `docs/scoring/v1_0_final_freeze_checklist.md`
- `docs/scoring/v1_0_final_demo_runbook.md`
- `docs/doctor_workbench_acceptance_v1_0.md`
- `docs/final_report/images/v0_9_6_frontend_polish/`
- GitHub Issues、tags、Releases

本地课程材料：

- `homework/Medical_Record_Agent_v0.9.8_week_review_package.docx`

说明：`homework/` 按 `.gitignore` 保留为本地课程材料，不默认上传 GitHub。

## 不可提交材料

- 真实患者病历、真实患者音频、身份信息。
- API Key、Token、`.env` 私密配置。
- 模型权重、模型缓存、`data/asr_model_cache/`。
- Docker 运行数据、`data/docker_runtime/`。
- 虚拟环境、`__pycache__`、临时调试文件。
- 未确认的大体积音频、视频录屏。

## 最终验证命令

```powershell
python scripts\check_docker_port.py --start 2600 --end 2699 --format env
$env:MRA_HOST_PORT = "2644"
docker compose up -d --build
curl.exe http://127.0.0.1:$env:MRA_HOST_PORT/health
curl.exe -I http://127.0.0.1:$env:MRA_HOST_PORT/static/doctor.html

$env:PYTHONPATH = (Get-Location).Path
pytest -q
node --check static\doctor.js
git diff --check
git status --short
```

## 已知边界

- 当前系统是课程工程原型，不声明临床诊断有效性。
- 候选诊断、治疗建议和导出结果必须医生确认。
- 自动角色识别不是 100% 准确，系统保留人工校正和质量门禁。
- 医院真实 PC 未实机复测，当前配置建议来自本机测试和公开资料推断。
- 边缘端真实部署放到 `v1.1` 或后续扩展。
- 本地仍存在未纳入 v1.0 的后端字段抽取实验改动，未进入本次 Release。

## 最终演示顺序

1. 展示 GitHub Release 和版本记录，说明当前是课程工程交付版。
2. 运行端口预检脚本，选择实际可用端口。
3. 打开医生端页面，展示三栏工作台。
4. 走文本生成主链路：字段、质量、候选诊断、治疗建议、证据。
5. 展示导出阻断和确认字段后的导出成功路径。
6. 展示 ASR 能力：Mock ASR 保底，FunASR 真实音频作为可选演示。
7. 展示周评审材料和后续边缘端/医院实机计划。
