# 三种接诊布局：参考来源与设计转化

日期：2026-11-06。先打开 [布局示意入口](comparison.html)，选择 A / B / C，再进入相应交互工作台。三种布局共用合成病例和接诊流程，不改动生产接口。

本轮资料研究执行者：`/root/design_sources`；公开页面交互与截图执行者：主线程。资料正文、实际操作、原型验证和医生使用验收分别记录，不互相替代。

## 设计目标和既有资产

用户已明确：医生日常接诊、简洁方便直观；流程保持，前端可以重新组织。连续病历为主，原文可以固定并排，诊疗参考按需展开。

已有 `../frontend-design-20261106/` 原型覆盖合成采集、角色确认、草稿、审核、签署、导出、完成接诊与异常模拟。本轮复用其交互状态作为实验基础，主要比较空间安排。其历史验证不自动等于本轮新布局通过。

流程保持为：**选择患者 → 采集问诊 → 核对病历 → 签署当前版本 → 导出 → 完成接诊。**

## 真实产品与可操作示例

| 来源 | 本轮读取或操作深度 | 借鉴的具体位置与行为 | MediListen 转化 | 未证明的部分 |
| --- | --- | --- | --- | --- |
| [Heidi：New Scribe layout reorganized around your note](https://support.heidihealth.com/en/articles/18184493-new-scribe-layout-reorganized-around-your-note) | 官方操作说明正文已打开阅读 | 左会话列表、中央病历、右控制面板；控制面板可收起；常用录音控制保持位置；可打开分屏 | A 以文档为主区，B 允许病历与原文并排。低频控制退出正文主阅读区 | 没有登录 Heidi 操作；页面声明 UK / EU 不可用，Managed teams 计划 2026-12-09 开放，不能说所有账号已可用 |
| [Nabla：Reviewing and editing generated notes](https://help.nabla.com/en/articles/4857090) | 官方操作说明正文已打开阅读 | 在当前章节直接修改文字或口述编辑 | 每字段保留必要动作，修改靠近正文；用清楚的保存状态承接编辑 | 没有实际操作 Nabla；不代表本项目语音编辑能力 |
| [Nabla：Adding encounter quotes](https://help.nabla.com/en/articles/808130) | 官方操作说明正文已打开阅读 | 在转写中选择原话后，明确执行加入病历 | 查看原文与采用原文分开；加入内容应是显式动作 | 不直接复用其界面或模型；没有实际执行加入原话 |
| [Nabla：Regenerating note](https://help.nabla.com/en/articles/5157570) | 官方操作说明正文已打开阅读 | 重生成可以撤销，支持突出显示变化 | 新句不静默覆盖医生手改；显示待合并差异；旧版本可追溯 | 没有验证其撤销的数据保存机制；原型恢复策略不等于生产持久化方案 |
| [Abridge：Linked Evidence](https://www.abridge.com/blog/a-year-of-abridge-in-summary) | 官方功能介绍正文已打开阅读 | 从生成的摘要定位转写，并可回放对应音频 | 病历字段“原文”定位对应句，保留章节与患者；原文证据和诊疗文献依据分开命名 | 未登录产品，未实际播放音频；不据此声明模型正确或提高临床效果 |
| [shadcn/ui：Mail 示例](https://v3.shadcn.com/examples/mail) | 主线程实际打开、点击、筛选、读取并查看截图 | 选择 Alice Smith 后右侧详情改变；选择 Unread 后列表切换为未读条目，而右侧 Alice 详情保持 | 借鉴稳定阅读区域、局部更新和清楚的列表状态；不照搬邮件三栏和邮件业务流程 | 页面明确为 v3 旧版示例，仅作成熟结构参考，不选择新依赖或声称使用最新版组件 |

shadcn/ui 实操证据在本机项目证据目录：

- `C:/Users/AWA007/Desktop/Data/开题报告/.artifacts/frontend-layout-comparison-20261106/reference-shadcn-mail.jpg`
- `C:/Users/AWA007/Desktop/Data/开题报告/.artifacts/frontend-layout-comparison-20261106/reference-shadcn-mail-unread.jpg`

这里的“借鉴”指信息组织和可观察的行为模式。没有复制商业产品源码，没有声称几个来源的不同优点已经自动组合为最佳方案。

## 将网格、动效和加载落实成页面

| 知识来源 | 已核对内容 | 本轮采用的设计选择 | 验证方法 |
| --- | --- | --- | --- |
| [Carbon 2x Grid 概览](https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/overview)与[布局指南](https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/guidelines) | 8px 基础单元、稳定区域、关键对齐线；长文档与高密度工作台按内容目的选择结构 | 间距采用 8 / 16 / 24 / 32；患者、章节和正文沿一致对齐线。病历保持可读行宽，辅助区按需占位 | 在同一合成病例下比较 1440×900、1366×768、800×600；检查正文宽高、截断、遮挡和全页溢出 |
| [Carbon Motion](https://www.carbondesignsystem.com/building-blocks/foundations/motion/overview) | 任务操作采用克制的 productive motion，动画应说明状态与空间关系 | 短反馈、平缓减速，避免弹跳；新增内容不导致正在阅读的整段内容跳动；支持减少动态偏好 | 检查面板开关、字段更新与焦点；动画时间仅为原型初始值，不声称经医生验证 |
| [Carbon Loading](https://www.carbondesignsystem.com/building-blocks/core/patterns/loading) | 初次内容加载可用骨架；局部处理应就地反馈；长处理需要更清楚的状态 | 保留已经出现的病历与原文；显示正在处理的动作和可继续操作的内容；无真实进度时不画假百分比 | 模拟采集、生成、保存、断连和失败，判断用户能否辨认“处理中 / 已保存 / 连接恢复中 / 真实失败” |

本项目的 60:40 比例、正文最大宽度和面板宽度是待比较的原型参数，**不是 Carbon 规定**。规范符合、无障碍检查、视觉美感和医生使用效率应分别判断。

## 三种布局的参考映射与取舍

| 方案 | 主要参考 | 适用任务 | 代价及检查点 |
| --- | --- | --- | --- |
| A 文书优先 | Heidi 病历中心结构、Carbon 文档模式 | 通读与编辑，随后签署 | 高频原文核对需要打开并固定面板；要检验是否增加操作 |
| B 持续对照 | Heidi 分屏、Abridge 证据定位 | 采集时观察草稿，频繁核对原话 | 原文持续占用宽度；在较窄视口需要面板化 |
| C 问题引导 | 稳定文档主区与就地异常处理的实验组合 | 集中处理缺失和差异 | 待办导航会争夺注意力；不能遮住连续病历，也不能使正常字段必须逐项过关 |

C 是本项目的实验组合，不宣称是某个商业产品的完整成熟方案。三方案的按钮数、内容量、病例和任务顺序需要保持可比。

## 用户提供的视频：本轮读取边界

用户提供的 B 站和抖音链接保留为研究输入。本轮资料代理尝试直接读取下列五条页面，网页工具均返回无法访问；没有取得视频正文、字幕或评论，因此没有标记“已完整观看”。

| 视频链接 | 本轮状态 |
| --- | --- |
| [《Refactoring UI》20 条设计规则](https://www.bilibili.com/video/BV1FXHs68Eh1/) | 页面工具不可访问；正文、视频、评论未读 |
| [没有 AI 味的设计 / impeccable](https://www.bilibili.com/video/BV1B2at64Eyf/) | 页面工具不可访问；正文、视频、评论未读 |
| [五星设计：网格系统](https://v.douyin.com/W0SLBmwoWMA/) | 页面工具不可访问；正文、视频、评论未读 |
| [设计师 PPM：运动曲线](https://v.douyin.com/EBDzTl-gAJI/) | 页面工具不可访问；正文、视频、评论未读 |
| [BeiYu 北煜：加载状态](https://v.douyin.com/i-MTcctoaS4/) | 页面工具不可访问；正文、视频、评论未读 |

上述名称来自用户提供的标题，不是本轮对视频内容的独立核实。其余用户链接本轮资料代理未读取。主线程若补充浏览器实看，应单独写明具体页面、时间段、字幕或评论范围；不能用这份官方资料综述代替视频观看。

## 验证与生产边界

本目录仅交付隔离设计实验。用户视觉确认、同条件任务效率对照和目标医生独立试用仍是关键未知。生产 Research Gate 保持 `NEEDS MORE EVIDENCE`；不因参考资料充分、状态测试或原型截图成功而进入生产设计放行。

真实音频、麦克风、实时病历质量、诊疗参考准确性、生产 API、实际持久化和生产 PDF 未由本目录验证。合成原型只证明其明确执行过的交互。

## 参考资料

- [Heidi 新 Scribe 布局](https://support.heidihealth.com/en/articles/18184493-new-scribe-layout-reorganized-around-your-note)
- [Heidi 2025 年 7 月更新：实时转写分屏](https://www.heidihealth.com/changelog/july-2025-updates)
- [Nabla：章节内编辑](https://help.nabla.com/en/articles/4857090)
- [Nabla：加入原话](https://help.nabla.com/en/articles/808130)
- [Nabla：重生成、撤销和差异显示](https://help.nabla.com/en/articles/5157570)
- [Abridge：Linked Evidence 功能说明](https://www.abridge.com/blog/a-year-of-abridge-in-summary)
- [shadcn/ui v3 Mail 公开交互示例](https://v3.shadcn.com/examples/mail)
- [Carbon 2x Grid 概览](https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/overview)
- [Carbon 2x Grid 布局指南](https://www.carbondesignsystem.com/building-blocks/foundations/2x-grid/guidelines)
- [Carbon Motion](https://www.carbondesignsystem.com/building-blocks/foundations/motion/overview)
- [Carbon Loading](https://www.carbondesignsystem.com/building-blocks/core/patterns/loading)
