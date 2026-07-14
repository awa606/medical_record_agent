# Claude Design PPT 提示词：Medical Record Agent 周评审

请根据以下内容生成一套中文周评审 PPT，风格要求为：医疗科技、清爽、专业、低噪声、白底浅蓝辅助色。不要做夸张营销风，使用系统截图、流程图、指标表和里程碑时间线表达工程进度。

## 基本信息

- 项目名：Medical Record Agent / AI 生成式电子病历辅助系统
- 当前阶段：v0.9.7 Release Candidate，准备进入 v1.0 冻结
- 项目定位：课程工程原型，不声明临床可用，不做自动最终诊断
- 展示重点：工程闭环、可复现测试、医生审核边界、Docker/GitHub 可追踪

## 幻灯片结构

### Slide 1 封面

标题：AI 生成式电子病历辅助系统  
副标题：周评审汇报：从汇报版到可交付工程原型  
右下角：版本 v0.9.7 Release Candidate / 2026-07-14

### Slide 2 项目目标

用一句话说明：
将中文医患问诊音频或文本转化为可审核、可追溯、可导出的电子病历草稿。

三点边界：
- 辅助医生，不替代医生
- 候选诊断和治疗建议必须医生确认
- 不使用真实患者隐私数据

### Slide 3 本周完成概览

使用 2x3 卡片：
- ASR 与角色校正
- 病历字段抽取
- 病历质量规则
- 候选诊断和治疗建议
- Docker 本地部署
- GitHub Issue/Tag/Release

### Slide 4 系统流程

画流程图：
输入音频/文本 -> ASR 转写 -> 角色校正 -> 病历草稿 -> 质量评估 -> 候选诊断/治疗建议 -> 医生审核 -> 导出。

强调：所有正式结果必须经过医生确认。

### Slide 5 医生端界面

使用截图：
- docs/final_report/images/v0_9_6_frontend_polish/01_empty_1366x768.png
- docs/final_report/images/v0_9_6_frontend_polish/03_text_generated_1366x768.png

说明三栏：
- 左：病历草稿摘要
- 中：对话转写和进度
- 右：候选诊断、治疗方案、诊断证据、操作区

### Slide 6 病历质量与证据定位

展示字段质量：完整、缺失、低置信度、证据不足、需要医生复核。

强调：
- 不把占位文本当作完整字段
- 每个字段需要证据来源
- 缺失项会触发补问建议

### Slide 7 ASR 与角色识别现状

用“已完成 / 仍需优化”两列：

已完成：
- FunASR / SenseVoice / Qwen3 评测
- 长音频切片
- SSE 进度和断连恢复
- 说话人/角色质量门禁

仍需优化：
- 自动角色识别不是 100%
- 医院真实 PC 未实测
- 边缘端未真实部署

### Slide 8 Docker 与 GitHub 工程化

展示：
- Docker 本地启动
- 端口扫描脚本
- GitHub Issue
- Git tag / Release

命令示例：
python scripts/check_docker_port.py --start 2600 --end 2699 --format env
docker compose up -d --build

### Slide 9 评分表对应

用表格：
- 技术打通 8 分：主流程闭环
- 系统架构 6 分：FastAPI、ASR、Orchestrator、质量评估、Docker
- 接口定义 3 分：ASR/records/tasks/export
- 过程记录 3 分：daily log、debug log、Issue、Release

### Slide 10 明天演示路线

演示步骤：
1. 打开医生端
2. 文本生成病历
3. 查看字段质量和详情证据
4. 展示候选诊断和治疗方案
5. 展示导出阻断
6. 确认字段后导出
7. 展示 GitHub Release 和 Docker 端口预检

### Slide 11 风险和下一步

风险：
- 医院 PC 未实测
- 边缘端真实部署暂缓
- 自动角色识别仍需要更多真实样本验证

下一步：
- v0.9.8 周评审材料冻结
- v1.0 最终交付冻结
- v1.1 医院 PC / 边缘端扩展

### Slide 12 结束页

一句话：
当前系统已经从“汇报版”推进到“可运行、可评测、可追踪、可准备交付”的工程原型。

## 视觉建议

- 主色：医疗蓝 #2563eb
- 辅助色：浅蓝 #eff6ff、绿色 #16a34a、红色 #dc2626、黄色 #f59e0b
- 字体：思源黑体 / 微软雅黑
- 页面风格：清爽、卡片化、留白充足，不要堆满文字
- 每页最多 3-5 个重点，不要把文档整段搬进 PPT

## 必须保留的风险边界文案

本系统为课程工程原型，当前不声明临床可用；候选诊断、治疗建议和导出结果均必须经过医生确认。
