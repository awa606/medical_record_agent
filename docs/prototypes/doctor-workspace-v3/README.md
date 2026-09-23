# 医生工作区 V3：简洁三栏样稿

状态：**AWAITING USER REVIEW**。用户认为V2字体过大、冗余内容多，要求参考真实医院系统。本版正文16px、按钮14px、辅助信息13px；保留三个业务区域，未接生产接口。

## 版式依据与改动

参考Bahmni临床工作区在同一屏查看上下文、记录本次就诊的组织方式，以及OpenMRS的patient-chart工作区边界。这些是成熟医疗软件的公开交互资料，**不是我国所有医院的统一UI标准，也不代表本项目已经接入HIS**。不复制其框架、代码、病人数据或治疗功能。

- 患者和本次就诊压缩为一行；保留五步状态，减少顶部高度。
- 保留转写、病历、核对参考三栏；正文16px；不靠缩小正文实现窄屏。
- 去掉大头像、重复病历标题、英文装饰标题、侧栏口号和重复输入入口。
- 右栏仅展示过敏信息核对、待补充项、参考查询；非生成状态不提前展示患者事实。
- 原文和知识卡按需替换右栏；病历栏位置保持不变。
- 编辑、保存、审核、导出随场景切换主操作；首次草稿不重复放置“开始新录音”按钮。
- 未取消角色、冲突、未保存或失败提示。顶部保留明确的匿名样稿标记。

## 运行

仓库根目录：

```powershell
python -m http.server 8767 --bind 127.0.0.1 --directory docs/prototypes/doctor-workspace-v3
npm ci --prefix tests/visual --ignore-scripts
npm test --prefix tests/visual
```

打开 `http://127.0.0.1:8767/`。全部数据仅为匿名固定示例；不录音、不访问API、不写数据库、不生成病历文件。右上角切换11种场景。

## 验证与边界

Playwright固定检查四种视口（1366×768、1440×900、1920×1080、1000×720），覆盖字号、栏位稳定、操作可达、长病历、编辑审核示意、原文只读、转义、角色恢复和无外部请求。结果以本轮[证据报告](../../evidence/20260923_alpha51_visual_preview_v3.json)为准。

用户明确认可具体V3布局后才允许固定截图基线并接业务。尚未获批时图片回归拒绝；自动测试不能替代用户认可。真实三路径和离线恢复仍未执行；5.1保持BACKLOG，2626不变。

V1/V2源码及否决、待调整证据保留，不把新版结果覆盖到旧版记录。

## 参考资料

访问日期：2026-09-23。只借鉴公开的工作区组织原则，不将布局选择伪装为临床验证。

- [Bahmni Consultation Pad](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/5441617957/Consultation%2BPad)：查看上下文与本次就诊录入同屏。
- [Bahmni Clinical Services](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/32604195/Clinical%2BServices)：已有患者查询、临床记录查看和编辑。
- [OpenMRS Workspaces](https://o3-docs.openmrs.org/en-US/docs/workspaces/)：在患者上下文中组织工作区。
