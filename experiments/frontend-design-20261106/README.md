# MediListen 接诊交互原型 · 2026-11-06

面向医生日常接诊的可操作设计样机：白底连续病历、原文并排、按需诊疗参考，以及逐句更新的模拟问诊。仅使用两位固定合成患者，不接业务 API、数据库、麦克风或模型。

## 打开原型

双击本目录的 `启动交互原型.cmd`，浏览器会打开 [本地交互预览](http://127.0.0.1:23711/)。需要已安装的 Python 3；没有第三方运行依赖。

也可以从仓库根目录运行：

```powershell
python experiments/frontend-design-20261106/serve.py --open
```

端口占用时指定另一个本机端口：

```powershell
python experiments/frontend-design-20261106/serve.py --port 23712 --open
```

服务只绑定 `127.0.0.1`，仅提供本原型目录；`.mjs` 使用 JavaScript MIME。关闭启动窗口或按 `Ctrl+C` 停止服务。帮助和版本：

```powershell
python experiments/frontend-design-20261106/serve.py --help
python experiments/frontend-design-20261106/serve.py --version
```

## 建议试用顺序

1. 从今日接诊选择合成患者甲，开始模拟录音。
2. 核对说话人，观察原文逐句出现、临时病历与辅助提示同步变化；可以暂停或手动播放下一句。
3. 在采集中编辑临时病历，继续播放，检查新内容是否明确进入待合并，而不是覆盖手改。
4. 播放完六句对话后结束采集，进入病历核对。
5. 点字段“原文”，检查定位；修改病历、保存新版本，并查看历史只读对照。
6. 分别处理缺失、冲突、候选与提醒，再签署当前保存版本。
7. 生成演示文本、发起下载、完成本次接诊并返回列表。
8. 换合成患者乙，检查输入与病历隔离；刷新或离开前观察保稿提示，回来明确选择恢复。
9. 用“演示场景”检查空列表、断连恢复、生成失败、保存冲突和下载失败。

## 演示边界

- “模拟录音”是固定合成对话的逐句播放，不录制声音，不产生真实音频，也不能用于评价 ASR、医疗模型质量或响应速度。
- 说话人未确认时显示原文，但不更新患者事实。断连暂停更新，恢复后继续同一合成状态；这不是生产断网恢复证明。
- 临时病历与正式保存版本分开。采集中手动修改需要明确保留和合并；正式修改会使旧签署失效。
- 文本与音频入口仍使用固定病例结果；自由输入仅验证表单、归属和恢复，不参与推理。
- 诊疗参考只演示信息组织与处理动作，不代表指南或医疗建议，不自动写成患者确诊。
- 导出为带合成标识的 `.txt`，不是生产 PDF。页面区分文件生成、下载发起和接诊完成；浏览器是否落盘仍要查看实际下载。
- 只在当前标签页的 `sessionStorage` 保存隔离演示状态，不使用 `localStorage`。浏览器恢复已关闭标签页时也可能恢复会话；明确清除可使用重置演示。请只输入合成测试文字。
- 旧原型保留在相邻 `frontend-design-20261105`，生产文件未因本样机变更。

## 代码与验证

```text
app.mjs              页面、交互和两个状态模型的衔接
style.css            布局、字体、颜色、窄屏和短窗口样式
model.mjs            既有就诊、版本、签署和恢复模型
capture.mjs          合成采集时间线与手改保护
model.test.mjs       原有状态回归
capture.test.mjs     新增采集模型行为验证
serve.py             本机静态服务器
design-qa.md         本轮渲染、实际按钮与限制
REVIEW.md            独立框架与功能审查
VISUAL_REVIEW.md     独立界面截图与基线比较
RESEARCH.md          隔离实验范围及未关闭问题
```

从仓库根目录执行：

```powershell
node --test experiments/frontend-design-20261106/model.test.mjs experiments/frontend-design-20261106/capture.test.mjs
node --check experiments/frontend-design-20261106/app.mjs
```

测试结果以本目录 `design-qa.md` 与 `REVIEW.md` 为准。状态测试不等于实际浏览器、系统缩放或医生独立验收。生产 Research Gate 保持 `NEEDS MORE EVIDENCE`，生产工程设计未放行。

## 设计来源

本轮视觉基线为本机 `.artifacts/frontend-design-baseline-20261106` 中三张已讨论的界面图与 `design-spec.json`。实现统一使用系统无衬线字体、青绿色主动作、连续病历和右侧辅助面板，并收敛概念图中重复的警告和过重标题。品牌图沿用仓库已有 MediListen 资源。

外部交互模式的前期研究见 [旧原型研究记录](../frontend-design-20261105/RESEARCH.md)。本轮没有重新宣称看完所有视频或评论，也没有使用外部产品代码替换项目框架。
