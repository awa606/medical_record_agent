# 医生工作区 V3.4：已认可的三栏版式

状态：**LAYOUT APPROVED / WIRED TO ISOLATED REAL SERVICE**。用户在 2026-09-24 明确回复“认可 V3.4，接入真实业务”。这是版式与操作顺序认可，不是 5.1 稳定版本验收。样稿仍使用匿名固定数据；`static/doctor.html` 已按同一骨架接入现有真实录音、转写、编辑、审核和导出接口。本版病历正文17px、转写16px，保留三个业务区域。

## 版式依据与改动

参考Bahmni临床工作区在同一屏查看上下文、记录本次就诊的组织方式，以及OpenMRS的patient-chart工作区边界。这些是成熟医疗软件的公开交互资料，**不是我国所有医院的统一UI标准，也不代表本项目已经接入HIS**。不复制其框架、代码、病人数据或治疗功能。

- 患者及本次就诊为第一行，五步流程为第二行，合为一个就诊信息区；与三栏保持16px间隔。
- 样稿说明保留在顶栏；异常和长内容场景收进默认折叠的“样稿验收工具”，医生不需要选择场景。
- 默认进入待采集，点击开始录音即可进入问诊；结束时停止、试听并提交，随后显示草稿、编辑与审核。全部仍为本地交互示意。
- 未录音时不展示虚假音频时长，原文证据入口禁用；未生成前不展示患者事实。
- 用深色顶边、浅蓝流程背景、明确的栏标题底色与边框分隔模块；不改变三栏比例。
- 保留转写、病历、核对参考三栏；病历17px、转写16px；栏间20–24px，栏内增加段落和分组间距；不靠缩小正文实现窄屏。
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

打开 `http://127.0.0.1:8767/`。全部数据仅为匿名固定示例；不录音、不访问API、不写数据库、不生成病历文件。默认直接试用“开始录音→停止→模拟提交→病历编辑”顺序；11种异常或长内容场景仅用于验收工具。

## 验证与边界

Playwright固定检查四种视口（1366×768、1440×900、1920×1080、1000×720），覆盖字号、栏位稳定、操作可达、长病历、编辑审核示意、原文只读、转义、角色恢复和无外部请求。结果以本轮[证据报告](../../evidence/20260923_alpha51_visual_preview_v33.json)为准。

V3.4 的用户认可记录在 `tests/visual/baselines/approval.json`，Windows 截图基线在 `tests/visual/baselines/win32/`。生产页面接入后的真实三路径结果见 [5.1 工程Smoke](../../evidence/20260924_alpha51_real_three_path_smoke.json)；完整回归、视觉缩放和断网恢复仍需分别判定，不能仅凭样稿与三路径Smoke宣称可恢复稳定版本。2626 保持原活动环境，隔离服务使用独立端口。

V1/V2源码及否决、待调整证据保留；V3原版保存在Git提交8bf700c，V3.1在同一目录增量调整，不把新版结果覆盖到旧版记录。

## 参考资料

访问日期：2026-09-23。只借鉴公开的工作区组织原则，不将布局选择伪装为临床验证。

- [Bahmni Consultation Pad](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/5441617957/Consultation%2BPad)：查看上下文与本次就诊录入同屏。
- [Bahmni Clinical Services](https://bahmni.atlassian.net/wiki/spaces/BAH/pages/32604195/Clinical%2BServices)：已有患者查询、临床记录查看和编辑。
- [OpenMRS Workspaces](https://o3-docs.openmrs.org/en-US/docs/workspaces/)：在患者上下文中组织工作区。
