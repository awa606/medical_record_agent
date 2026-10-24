# CI收口与本地提取判因（2026-10-24）

## CI失败与局部修正

当前分支`cd888108d07efd8f58820d0586ff493c1dab1b6d`的[CI 40096589009](https://github.com/awa606/medical_record_agent/actions/runs/40096589009)为FAIL：1361项通过、1项失败、3项跳过、8个子测试通过。

唯一失败是`tests/test_doctor_workflow_simplification_static.py::test_recognition_mode_replaces_visible_asr_engine_selector`仍要求旧说明“即时显示已返回转写；切换不会重新识别。”。运行资源已采用“切换已返回转写，不重新识别。”，本机单例复现同一断言失败。

本批仅将此断言适配现有可见文案；保留识别模式、上传说明、内部参数及工作流检查，不改生产资源或识别行为。所属测试文件10项于本轮通过（0.31秒），`git diff --check`通过。此前31项和实际E-8/E-23显示验收复用；没有重复部署8798。新CI尚待本次提交触发和核验。

## 当前运行与研究边界

8798前端仍为`cd56f59d6c7bf6ff02a6e78c1367cd01768c98d9`，后端仍为`4b041cf469cebc547ac79835891a985f4db30ae1`，本地FunASR与在线DeepSeek承担展示流程。测试/文档提交不是新运行版本。

本地研究将独立记录原始选择、映射和校验。强制`previous_treatment.minItems=1`仅用于诊断约束兼容性，不作为模型理解成绩或生产补全规则。既有三次七空数组失败保留，本轮不重复字段释义或标签候选。

正式16项、99h、日期及硬件延期不变；5.1保持VERIFY，5.3不启动。模型质量和最终版本发布门禁分别判断。
