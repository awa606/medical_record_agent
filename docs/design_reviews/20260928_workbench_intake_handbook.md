# 工作台接诊与产品手册增量评审

- WBS：5.1，现有视觉／可用性返工；不新增任务、不变更99h和日期。
- 输入：用户批准的接诊流程计划；`20260928_doctor_pilot_delivery.md`；本轮隔离接口和可见按钮验证。
- Research：ADAPT 现有登记、报到、开始和恢复接口，无新依赖选型。OpenEMR 的流程分层与按任务组织用户指南作为文档参考。
- Design Gate：PASS（接口与操作边界）；不代表5.1、模型质量或独立医生试用放行。

## 评审覆盖

| 项 | 本轮边界 |
|---|---|
| Goal / Deliverables | 工作台完成登记报到；开始接诊后选择输入；稳定模拟姓名；图文HTML/PDF手册及版本一致性证据 |
| I/O | 输入为授权医生操作和三个明确合成ID；输出为现有Encounter/Revision、界面状态与本地手册 |
| Constraints | 保留三栏、HTTP API、数据库、模型及安全阈值；其他历史记录继续脱敏 |
| Largest unknown | 两阶段登记报到部分失败，以及内部函数测试掩盖真实点击断点 |
| PBS | 前端流程修复、真实API浏览器回归、图文手册、隔离部署和PM证据 |
| Architecture | doctor.js内部状态适配→现有API→SQLite；展示名字是合成ID白名单映射，不读身份表 |
| Modules / Owned data | 前端持有待重试登记ID、编辑和录音状态；服务端持有就诊与版本；手册构建器仅读匿名截图清单 |
| Interfaces | POST encounters返回registered；POST check-in返回checked_in；POST start后进入工作区；GET恢复历史。失败保留已有记录，重试不重新创建 |
| WBS / Dependencies | 5.1 VERIFY；只修接诊和手册；5.3仍依赖最终三路径及恢复，不提前启动 |
| Critical path | 沿用同轮Project Planner快照；不另写算法。硬件延期，当前返工计入R11 |
| Risks | 隐私：只映射三个合成ID；数据：部分成功重试；交互：未保存／未提交录音保护；范围：不扩模型；排期：实际返工另记 |
| Minimal validation | 隔离真实API：可见按钮登记→报到→开始→文本生成→修改→审核→导出→重开；注入一次check-in503验证只有一条登记 |
| Acceptance / Milestone | 点击路径、权限、失败恢复、全量回归、运行资源SHA及手册逐页检查。模型质量与真实麦克风不由mock回归证明 |

## 固定五问

1. 为什么这样拆：接诊行政动作属于工作台，工作区只承担当前就诊的采集与病历处理。
2. 替代：保留抽屉仍会反复跳转；新建客户端或API没有解决必要性，选择复用。
3. 最可能失败：登记已成功而报到失败；切换覆盖未保存编辑；手册截图与运行版错位。
4. 最低成本验证：一个真实隔离数据库配可见按钮；一次503故障；截图按资源SHA绑定候选。
5. 如何证明完成：可见操作证据、失败重试不重复、权限回归、手册PDF书签及页面检查；不以代码存在代替验收。

ASSUMPTION A01：当前试用只含合成病例，不提供真实患者登记能力。A02：模型质量仍有历史缺口，本轮不声明消除。

## 参考

- [OpenEMR通用就诊流程](https://www.open-emr.org/wiki/index.php/A_Generic_Medical_Encounter_Workflow_in_OpenEMR_6.1)
- [OpenEMR用户指南](https://www.open-emr.org/wiki/index.php/OpenEMR_7.0.4_Users_Guide)
