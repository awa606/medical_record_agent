# 课程报告缺失插图提示词与插入说明

本目录图片用于补充 `AI生成式电子病历辅助系统_人工智能课程项目报告.docx` 中明确标注的两个缺图位置。通用 AI 绘图工具容易把中文标签画错，本目录 PNG 已按报告内容直接生成，建议优先插入 PNG；下面提示词可用于后续重新制图或在 Canva、PPT、即梦、通义万相等工具中重做风格。

## 图 3 Plan-and-Execute + Human-in-the-loop 执行流程图

- 图片文件：`docs/course_report_images/fig03_agent_plan_execute_hitl.png`
- 插入位置：`2.2 核心流程（Agent 循环 / 图）`
- 建议图注：`图 3：Plan-and-Execute + Human-in-the-loop 执行流程图`

提示词：

```text
生成一张横向 16:9 白底扁平信息图，风格正式、清晰、适合高校人工智能课程项目报告。主题是“AI 生成式电子病历辅助系统的 Plan-and-Execute + Human-in-the-loop 执行流程”。

主流程从左到右排列 7 个圆角矩形节点，并用蓝色箭头连接：
1. 输入/上传：文本问诊、预录音频、ASR 测试可单独返回
2. 感知归一：文本规范化、ASRResult、conversation_text
3. Plan 计划：判断输入类型、选择任务路径、拆分执行步骤
4. Execute 执行：字段抽取、草稿生成、安全校验
5. 过程记录：task_step、audit_log、Agent Trace、Run Log
6. 医生审核：补充缺失项、确认候选诊断、审核病历草稿
7. 导出门禁：默认 export_allowed=false、医生确认后再导出

在下方增加一条任务状态流转：CREATED -> EXTRACTING_FIELDS -> GENERATING_DRAFT -> SAFETY_CHECKING -> WAITING_DOCTOR_REVIEW。
突出“医生审核”为黄色，“导出门禁”为红色，“执行”为绿色。加入一条从医生审核返回执行阶段的反馈箭头，说明缺失项、角色待校正或安全风险存在时需要人工复核。
要求中文清晰可读，布局不要拥挤，不要真实患者照片，不要医院 logo，不要水印，不要额外无关元素。
```

## 图 4 安全护栏与导出门禁图

- 图片文件：`docs/course_report_images/fig04_safety_guardrails_export_gate.png`
- 插入位置：`3.4 安全与护栏机制`
- 建议图注：`图 4：安全护栏与导出门禁图`

提示词：

```text
生成一张横向 16:9 白底扁平信息图，风格正式、清晰、适合高校人工智能课程项目报告。主题是“AI 生成式电子病历辅助系统的安全护栏与导出门禁”。

上方主流程从左到右排列 6 个圆角矩形节点，并用蓝色箭头连接：
1. AI 草稿：由字段抽取结果生成，不补写未提及事实
2. 安全校验：SafetyCheckResult，检查缺失与风险
3. 风险拦截：Prompt 注入、候选诊断误用、敏感信息泄露
4. 医生审核：确认字段、补充缺失项、确认候选诊断
5. 导出门禁：export_allowed=false，未审核禁止导出
6. 最终导出：医生确认后形成最终病历材料

下方展示 5 个护栏层次卡片：
数据边界：只用课程样例、不接真实 HIS/EMR、API Key 不进截图和日志
Prompt 约束：System Prompt 固定边界、防 Prompt 注入、AI 只能辅助医生
Schema 校验：JSON 解析、Pydantic 校验、无效输出触发 fallback
字段规则：未提及 = missing、候选诊断需确认、不自动写“正常”
审计追踪：task_step、audit_log、Run Log、Agent Trace

突出 export_allowed=false 和医生审核前禁止导出。红色用于风险和门禁，黄色用于医生审核，绿色用于校验通过或最终导出。要求中文清晰可读，布局不要拥挤，不要真实患者信息，不要医院 logo，不要水印，不要额外无关元素。
```
