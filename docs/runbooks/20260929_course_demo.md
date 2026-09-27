# 9月29日课程展示：A／B／C交付检查点

9月28日新增[独立数据库／知识库浏览器](readonly_data_browser.md)：查看匿名患者→就诊→Revision→批准→导出、指南来源→版本→片段→embedding元数据。8796优先、8797备用；它是需本地登录的只读快照，不替代8795医生页面。模型Schema提示词候选有局部改善，但因第6例医生提问误入主诉被拒绝部署，详见[实验及工具证据](../evidence/20260928_alpha51_schema_and_browser.md)。

本次是DEV-01课程演示，不是完整Alpha出口或临床产品验收。正式计划仍为16项、99h；硬件1.1–1.4延期，不采购或测试Jetson。9月28日18:00后只处理阻断性缺陷、回归与冻结。

## 本轮设计补充

复用已通过的医生工作区、Knowledge V1、Provider及Revision设计。决策为ADAPT；公共API、SQLite结构、安全阈值和模型保持不变。设计边界可执行，部署／视觉／模型质量Gate仍以实测为准。

| 评审项 | 决策 |
|---|---|
| Goal／Deliverables | A为可访问的8795候选入口；B为可追踪知识与模型质量报告；C为三路径、恢复包和10分钟讲解 |
| Input／Output | 仅合成文本和已授权匿名录音；输出可重开的就诊、字段、引用、Revision及导出 |
| Constraints | 原WBS、零资料采购、无训练；正文17px／转写16px，展示设备150%保留三栏 |
| Largest uncertainty | 本地Qwen首次提取仍可能改写引用；必须保留失败并由医生修正，不能把后审结果计作原始模型成功 |
| PBS／Architecture | 原生医生页→既有API→SQLite；FunASR／Ollama本地运行；知识引用和患者事实分离 |
| Module ownership | CSS负责紧凑框架；JS负责显示现有状态；准备脚本仅使用既有接口，不审批病历或覆盖原库 |
| Interfaces | Encounter登记／恢复、records/generate、tasks/trace、knowledge/retrieve；原401／403／409及模型失败语义不变 |
| WBS／Dependencies | 本轮属于5.1收敛，5.1通过才进入5.3；不修改任务日期、依赖或阶段门槛 |
| Critical path | 继续使用Obsidian工程插件共享快照，不另建关键路径算法 |
| Risks | R04布局、R08部署／恢复、R11额外投入；模型冲突和外屏实测不足保持可见 |
| Minimal validation | 紧凑宽度布局回归＋实际Edge缩放；三个匿名场景；知识查询、真实Provider、持久性及权限复验 |
| Milestones／Acceptance | 课程展示检查点不新增正式里程碑；最终三路径、真实缩放及离线恢复齐全才关闭5.1 |

固定五问：按可见结果拆A/B/C，避免资料扩充拖住入口；替代方案是重建前端或数据库，现有能力已成立故不采用；最大失败点是模型改写与错误部署；最低成本检查是同一匿名病例和真实API；完成证明必须包含实际页面、内容、Provider、SHA和恢复证据。

ASSUMPTION A01：当前电脑为演示设备，外接显示设备未验证前不声称兼容通过。A02：8795继续作为本轮验证入口，切换2626不再是交付前提；旧环境保留回退，2626不是POC2666。

## A：8795可操作候选

### 已有容器退出后的恢复

先检查`docker ps -a --filter name=mra51repair8795`、退出日志和8795端口，核对三个容器仍指向已验证镜像与绝对挂载。不要因为页面打不开重建数据库或执行`down -v`。

```powershell
docker start mra51repair8795-ollama-1
docker start mra51repair8795-app-1
docker start mra51repair8795-gateway-1
```

打开8795并核验`/health`。ASR／LLM预热期间`/ready=503`需查看具体检查层；只有实际返回200才进行真实AI操作。随后检查知识检索、已保存Revision和匿名访问保护。恢复失败保留日志与挂载，不自动切到旧2626或Mock环境。

9月27日晚恢复记录及未通过的JSON引用实验见[恢复与引用对照](../evidence/20260927_alpha51_recovery_citation_ab.md)。原转写界面及运行模型保持不变；不能将此次进程恢复称为新版本离线恢复验收。

1. 更新8795前备份候选容器内数据库，使用SQLite Backup API，记录表级指纹及容器／挂载信息。不改旧2626；不要从Windows直接打开Docker正在使用的WAL数据库。
2. 检查当前代码、镜像revision及HTTP静态资源SHA一致；真实配置必须是FunASR＋Ollama/Qwen3:4b，无Mock或云端回退。
3. 使用下列准备工具创建三组显式合成病例。已有相同标识就诊会复用，不删除旧记录，不自动批准；前两组执行真实Qwen，第三组保留供现场输入。首次结果和当前结果分别保存在本地。

```powershell
python scripts/alpha51_prepare_demo_cases.py `
  --base-url http://127.0.0.1:8795 `
  --password-file <本地管理员密码文件> `
  --output-dir .artifacts/<本轮目录>/demo-cases
```

4. 实际Edge100%／125%／150%检查三栏、录音、编辑、参考详情及审核操作。900px以上采用紧凑导航保留三栏；更小的移动视口继续抽屉布局。模拟视口只证明布局回归，不等于实际缩放。
5. 检查知识来源与FTS5结果、保存与重载、独立匿名401和医生管理接口403。模型未就绪仍阻断真实AI操作。
6. 本轮继续使用8795，不切换旧2626。更新候选失败时保留新数据并恢复更新前的候选镜像；2600／2666保持停止。

## B：知识和理解

资料仅限已批准四类官方文档；完整章节与新版必须保留旧文档、旧chunk及历史引用，记录原文件SHA与提取文本SHA。2025流感资料获取失败时保留已知版本，不凭搜索摘要补全文。BGE限时一小时，真实混合检索与冻结查询不退化才启用。

模型评测保持1–30开发、31–40验证、41–60冻结划分。240条规则安全集与真实Qwen输出分开统计；记录首次字段覆盖、冲突、事实召回、耗时及人工修正。现有demo/mock报告不作为DeepSeek在线基线。

## C：十分钟演示与冻结

| 顺序 | 展示内容 | 相对POC的增量 |
|---|---|---|
| 1 | 搜索`SIM-DEMO-0929`，重开历史就诊 | 数据持久化和患者／就诊关联 |
| 2 | 实际录音或重放已标注的历史录音，显示实际模型 | 真实本地ASR及Qwen，无固定文本回退 |
| 3 | 角色未确认时阻断，再人工确认 | 角色门禁及审计 |
| 4 | 否定、家属和缺失字段核对 | 有证据的语义保护，失败如实显示 |
| 5 | 原文证据、查依据、版本／页码 | 可管理、可追踪知识库 |
| 6 | 修改→新Revision→审核→导出→重开 | 旧批准失效、版本冲突与受控导出 |
| 7 | 管理员查看知识文档、启停及测试搜索 | 管理权限与停用排除 |

最终SHA必须重跑文本、上传音频、物理麦克风三条真实路径。精确代码／镜像／配置／匿名库／模型清单和缓存归档后，在新目录新端口断网恢复。旧r6不替本版本验收。未完成前5.1保持VERIFY，5.3不启动。

## 9月27日可用候选与离线依赖

当前实际结果见[冲刺证据](../evidence/20260927_alpha51_demo_sprint.md)：8795是真实候选，2626仍旧环境；不要向评审展示2626并称其已是最新版本。搜索 `SIM-DEMO-0929-FEVER` 可打开已审核导出的合成就诊；`SIM-DEMO-0929-NEGATION` 保留首次抽取冲突供人工核对；`SIM-DEMO-0929-LIVE` 留作现场输入。

本轮更新前的候选代码为 `4c05a897c6bc191132b8f44bef822f18c8d807a0`，镜像为 `mra-alpha51:demo-b-bge-4c05a89`。最新核对候选及实际版本见[病历核对证据](../evidence/20260927_alpha51_record_review_quality.md)。本轮操作文件位于本地 `.artifacts/alpha51-demo-sprint-20260927/`，`candidate-b.env`含本地凭据，不提交或投影展示。原始录音、数据库、截图、PDF、模型和wheel同样仅保留本地。

原基础镜像缺少可选知识依赖；补入官方PyPI的 `sentence-transformers==5.7.0` wheel，SHA256为 `b78141da3d8137e70d965866e2ca43190b9266f3d4d8752e250ded75e7136730`。本地 `knowledge-wheel/requirements.lock` 精确内容：

```text
sentence-transformers==5.7.0 --hash=sha256:b78141da3d8137e70d965866e2ca43190b9266f3d4d8752e250ded75e7136730
```

已执行的离线扩展镜像配方如下。它复用已验证基础镜像中的Torch、Transformers等，不下载或升级其他包；`pip check`已通过。后续冻结仍需打包最终镜像，而不是只存本配方。

```dockerfile
FROM mra-alpha51:demo-b-4c05a89
USER root
COPY *.whl requirements.lock /tmp/mra-knowledge-wheel/
RUN python -m pip install --no-index --no-deps --require-hashes \
    --find-links=/tmp/mra-knowledge-wheel \
    -r /tmp/mra-knowledge-wheel/requirements.lock
USER appuser
```

新HF缓存位于本轮 `knowledge-hf/`，以只读方式挂载，未覆盖旧缓存。知识版本变更前备份是 `knowledge-staging/before-promote.sqlite3`；事务只增补知识表并断言业务表指纹不变。不能直接用该备份覆盖后来产生的新病历。查询停用资料仍不可见，2025流感版暂不提升为当前版。

服务启动检查先看 `/health`，再轮询 `/ready`；就绪缓存过期后的首次503会触发真实模型探测，应等待后续结果，禁止改为Mock消除503。只有实际 `ollama`、正确模型摘要、`fallback_allowed=false` 和FunASR ready齐全才开展真实生成。

9月28日18:00功能冻结是人工冲刺检查点，本次未创建后台定时任务。现阶段尚无与该镜像对应的三路径3/3和离线恢复包，不称稳定演示版。
