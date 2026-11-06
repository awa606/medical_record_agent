# 接诊工作台：已选设计规则

2026-11-06，用户明确批准“浅灰底＋独立白色面板”及本轮完整实施计划。此目录是隔离设计原型；旧三布局位于相邻 `frontend-layout-comparison-20261106`，保持原样。

## 区域与层级

- 患者横条呈现患者、就诊、版本和保存状态。
- 左侧为连续病历文书，右上为问诊原文，右下为问诊辅助。
- 原文只放说话人与原话，辅助放待追问、诊疗参考和依据，不把辅助塞进原文流。
- 一级面板有固定标题和自己的一个内容滚动区。病历章节保持连续，不逐段套卡片。
- 底部操作区保持采集状态与一个当前主要动作。

## 视觉规格

| 角色 | 规格 |
| --- | --- |
| 页面底色 | `#EEF2F5` |
| 面板 | 白色，`1px #CAD3DC`，8px 圆角 |
| 标题栏 | `#F7F9FB` |
| 网格 | 外边距24px，面板间隔16px，工作区最大1600px |
| 右栏 | 宽320–416px，原文/辅助约60:40 |
| 病历行宽 | 正文上限约760px |
| 字号 | 病历22px，面板16px，章节17px，正文16px，元信息13px |
| 距离 | 标题与内容8px，章节24px |
| 动效 | 按钮约120ms，更新字段约180ms，减少动态偏好生效；面板不做opacity入场 |
| 状态 | 蓝灰表示原文选中；琥珀表示待核对冲突；红色表示失败，均配文字 |

小于900 CSS px时保留单列病历，原文/问诊辅助进入命名面板。返回恢复焦点与阅读位置。实际缩放与CSS视口分别验收。

## 从知识到检查

- [Refactoring UI](https://refactoringui.com/)：用背景、间距和必要边界表达分组；公开页已读，不宣称读取付费全书。
- [Carbon Color](https://www.carbondesignsystem.com/building-blocks/foundations/color/overview)：表面与状态颜色按角色使用，不能仅替换品牌色。
- [Impeccable Layout](https://impeccable.style/docs/layout/)：检查归属、顺序、密度、宽窄屏，而非仅检查是否套用网格。
- [Impeccable Typeset](https://impeccable.style/docs/typeset/)：检查标题、正文、元信息的角色、行长与缩放，保持既有中文系统字体。

本轮审美知识查询采用 `aesthetics:compare-frontend-01`，仅借用“固定内容与设备，分别评价可读性和个人偏好”的方法。发布库输入 registry SHA256 为 `4213d5386cbddb61d99187b20414517b45ed5ed130b44304e669761bdc5853ce`，aesthetics SHA256 为 `431865d400fbadf7e5d5adf36da9fde5feef73bdc59db83c4c390f2ed221c076`。不把知识条目或规范符合当作用户认可。

## 行为保护

既有病历、原文和医生手改在整理、失败时保留。6/6显示本例已播完；待判断候选不变成确诊。不新增生产API，不修改数据库、签署规则、model.mjs或capture.mjs。导出页面的反馈与实际下载文件验收分开记录。

先在同患者、同内容、同状态、同CSS视口和同实际缩放下对照，再验证长内容和主流程。生产Research维持NEEDS MORE EVIDENCE，生产Design尚未进入。
