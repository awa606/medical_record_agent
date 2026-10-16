# 5.1 展示与使用测试环境：增量研究及设计评审

## Research Decision Record

- 基线：`codex/alpha51-demo-visual-e2e` / `e60214f`；展示运行镜像仍为 `8afc6bd`。
- 决策：**PASS / ADAPT** 现有 Compose、SQLite、认证和桌面启动器。未更换模型、框架或数据结构。
- 比较：共享数据库无法满足隔离；完全复制模型浪费磁盘；选择独立项目、可写目录和 Cookie，仅共享只读模型文件。
- 本轮最小实验：两个无外网容器独立注册一个匿名患者、不同 Cookie、停止/重启后原记录保留；8795 容器与镜像未改动。结果 PASS，未执行 AI 推理。
- 本地证据：`.artifacts/alpha51-dual-environment-20260929/isolation-spike.json`。两份运行目录互不相同，Cookie 分别为 `mra_probe_1` / `mra_probe_2`。
- 官方设计依据：[Compose 项目隔离](https://docs.docker.com/compose/how-tos/project-name/)、[Cookie 作用域](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies)。本轮以实测判断可行性。
- 限制：端口不隔离 Cookie；演示与测试不能同时驻留真实模型；此实验不证明模型质量。
- 展示镜像使用 `Dockerfile.alpha51-showcase`，仅覆盖静态文件和 Cookie 配置，保留 `8afc6bd` 后端；测试镜像使用当前完整提交。两者分别记录交付 SHA 和后端 SHA，不能把展示页更新等同于部署后续字段规则修复。

## DESIGN REVIEW

| 项目 | 本次增量 |
|---|---|
| Goal | 8795 保留演示；8798/8799 可自行创建匿名患者、使用音频；历史原文和审核清晰可见 |
| Deliverables / PBS | 共享恢复修复、审核摘要、测试登记、双环境配置及启动器、独立快照、操作手册及验证记录 |
| Input / Output | 既有任务原文/ASR → 原文栏；现有 Revision/approval → 审核摘要；用户音频 → 既有 ASR 与病历流程 |
| Constraints | 不新增公共 API、表字段、视频或诊疗功能；不改变三栏、模型、安全阈值及正式 16 项/99h |
| Assumptions | A01 测试输入为合成或授权去标识内容；A02 两套真实模型轮流运行；A03 测试库不复制展示账号/历史 |
| Largest Uncertainty | 登录、数据与运行环境混淆；基础隔离已通过实测，切换及真实推理仍须实施后验收 |
| Architecture | 浏览器 → 各自网关/应用/SQLite/文件；只读模型缓存 → 各自 Ollama；仅一组服务活动 |
| Module Boundaries | doctor.js 恢复与呈现；静态 deployment.json 只含模式/版本；auth.py Cookie 配置；启动器拥有容器与快照归属 |
| Interfaces | 复用 task/encounter/audio/review API；读取失败提示且不编造原文；过期响应丢弃；非法配置/活动任务拒绝切换 |
| WBS | 5.1 内：恢复与审核 → 测试登记 → 部署切换 → 浏览器/安全/回退验证；负责人 Codex；证据对应本轮目录 |
| Dependencies | 隔离 Spike PASS → 增量设计 → 实现 → 候选验证 → 备份升级展示；5.3 仍依赖完整 5.1 |
| Critical Path | 使用同轮 Planner 快照，不另算 CPM；本变更不改正式依赖/日期；模型质量仍是放行阻断 |
| Risks | R04 过期内容串显示：版本令牌；数据风险：一致性备份；安全：独立 Cookie/账号；性能：单环境；R11 额外投入单列 |
| Minimal Validation | 独立 Cookie/库及重启已通过；后续两端浏览器、真实原文重开、非法切换、知识与快照归属测试 |
| Milestones / Acceptance | 功能测试候选可用不等于医生稳定版；三路径、模型质量、恢复及全部 Gate 未齐时 5.1 保持 VERIFY |

### 五问

1. 为什么这样拆：把可独立验证的恢复缺陷与部署隔离分开，避免把模型失败误判为界面问题。
2. 替代方案：共享库、复制整个演示目录或重建客户端均增加串数据或不必要范围。
3. 最可能失败：活动浏览器有未保存内容，后台仅靠任务表无法判断；切换要求先保存并退出，运行任务检查失败即拒绝。
4. 最低成本验证：原始失败测试、两容器 SQLite/Cookie Spike、真实按钮操作和停止重启验证。
5. 完成证据：版本资源 SHA、两个独立数据位置、可重复登记与审核、原文不串病例、实际认证和回退记录；模型不足继续公开。

**DESIGN REVIEW GATE：PASS**。实施范围已获用户授权，隔离可行性已实测；此结论不代表发布验收通过。
