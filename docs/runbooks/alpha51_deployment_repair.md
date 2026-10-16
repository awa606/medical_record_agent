# 5.1 部署候选：绝对路径、真实模型与知识包

该流程修复旧工作树挂载和演示Provider配置。先在8795验证，视觉和候选验收通过后才切换2626；不修改2666、2600或既有冻结包。它不是稳定发布声明。

## 数据库与知识库如何衔接

继续使用同一运行目录下的SQLite，分开业务表和知识表，不引入第二套病例库。业务关联是 `patient → encounter → agent_task → record_revision → approval/export`；知识关联是 `knowledge_source → knowledge_document → knowledge_chunk → knowledge_embedding`。

医生点击字段“查依据”时，现有接口携带task ID检查访问权限，将匿名化查询用于当前启用版本的知识检索。返回来源、版本、章节、页码、chunk和内容SHA；查询结果只读，不改写患者字段。病历中的原文证据仍来自本次转写，不能由指南文本替代。

本轮验证两个独立条件：导入知识不改变业务记录；修改并保存病历后，Revision与已有引用仍可重读。主动查询的临时结果不冒充已经保存的Revision引用；若未来需要把某条主动查询结果持久关联到Revision，须独立设计与验收，不在本次部署修复中新增关系。

## 备份与隔离

1. 本地保存 `docker inspect medical-record-agent`、镜像ID、Compose配置及挂载清单。inspect可能包含凭据，不提交Git。
2. 活跃SQLite的备份、检查和指纹计算均在**容器内**通过SQLite Backup API执行。不要在Windows上同时打开Linux容器正在使用的WAL数据库。离线文件复制必须先停对应应用，DB/WAL/SHM作为一组保留。
3. 将业务数据库备份及uploads/outputs复制到新的候选运行目录。旧目录只用于回退；所有候选操作写新目录。不要以知识库文件替换业务数据库。
4. 运行 `import_verified_knowledge.py` 前停止候选应用，目标库须已由当前应用初始化。工具仅插入知识四表和FTS索引；相同数据重复执行不改数据库，已有内容冲突则整次回滚，不导入用户、就诊或历史管理审计。

```powershell
python scripts/import_verified_knowledge.py `
  --source 'C:/absolute/approved/knowledge_v1.sqlite3' `
  --source-sha256 b729c1ed3693b9e0fad084269e234f88dfe21b9ca6f0c103e2fc610a6a675abc `
  --target 'C:/absolute/candidate/runtime/medical_record_agent.sqlite3' `
  --backup 'C:/absolute/candidate/before-knowledge.sqlite3'
```

参数路径替换为本机真实绝对路径。源包须关闭且无未checkpoint的WAL。四份文档对应 `config/knowledge/knowledge_v1.json`；病历规范同时记录原始CRLF文件SHA和已验收LF导入文本SHA，不能混用。

## 构建当前代码

正常部署可用仓库Dockerfile。已有本地依赖镜像时，可使用候选Dockerfile：它在复制新源码前比较五份requirements；不一致即失败，不下载或静默升级依赖。

```powershell
$taskBase = 'mra-alpha-demo-m4-rc1:candidate'
docker image inspect $taskBase --format '{{.Id}}'
$taskSha = git rev-parse HEAD
docker build --network=none --pull=false `
  -f Dockerfile.alpha51-candidate `
  --build-arg "MRA_BASE_IMAGE=$taskBase" --build-arg "CODE_SHA=$taskSha" `
  -t "mra-alpha51:deployment-$taskSha" .
```

基底ID、本次镜像ID、Git SHA和最终静态文件SHA写入本地部署记录。旧基底只复用依赖，不代表其旧网关或旧页面仍通过验收。旧r6含共享Cookie客户端的缺陷，禁止直接作为当前发布验收依据；本次网关按请求隔离会话。

## 明确绑定目录和Provider

在被Git忽略的本地 `candidate.env` 填入下列实际值；所有目录必须提前存在。Ollama模型清单摘要必须为已验证的 `359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`。

```dotenv
MRA_APP_IMAGE=mra-alpha51:deployment-实际GitSHA
MRA_RUNTIME=C:/absolute/candidate/runtime
MRA_MODELSCOPE_CACHE=C:/absolute/models/modelscope
MRA_HF_CACHE=C:/absolute/models/hf
MRA_OLLAMA_MODELS=C:/absolute/models/ollama
MRA_BOOTSTRAP_PASSWORD=本地生成的强密码
MRA_PORT=8795
```

已有库的用户凭据不会因bootstrap变量改变；不得误以为填写环境变量已重置现有密码。候选只发布到127.0.0.1，不把演示账号开放到局域网。

```powershell
docker compose --env-file .artifacts/本次目录/candidate.env `
  -p mra51repair8795 -f compose.alpha51-candidate.yml up -d --pull never
```

Compose固定edge、真实FunASR四组件upload、Ollama及Qwen3:4b、零LLM重试、离线模型缓存；模型服务无主机端口。网关沿用经过外连阻断验证的隔离方式，启动后移除默认路由并降权。模型缓存只读。

## 验证与切换条件

| 检查 | 合格证据 |
|---|---|
| 页面 | HTTP静态文件SHA与当前工作树一致，无验收工具注入 |
| 健康 | `/health=200`；模型预热期间页面可用，`/ready=503`如实保留 |
| 真实就绪 | `/ready=200`并核对funasr、ollama、模型摘要及fallback=false |
| 权限 | 登录前后独立匿名客户端均401，不同浏览器不继承会话；医生管理接口403 |
| 知识 | 4启用文档、39片段，FTS5真实返回文档/章节/页码/chunk/SHA及来源详情 |
| BGE | 本次包无embedding；只声明FTS5，不声明混合检索可用 |
| 持久化 | 应用重建后患者、就诊、任务、Revision、批准、知识表逻辑指纹不变 |
| 安全 | 冲突和未审核导出被阻止；角色未确认的音频生成409 |
| 模型 | 真实匿名文本生成、人工修改审核导出；既有授权WAV真实转写单独留证 |

本轮重放录音不算新麦克风采音，也不算最终SHA三路径3/3。UI缩放须真实Edge菜单125%/150%和页面证据，模拟视口不替代。工具识别网址失败时停止该自动化，交由人工核验。

全部切换条件满足后，保留旧容器并停止它，只修改候选网关端口到2626再重建网关；记录原端口和值。回退时停止新网关，启动旧容器。不得删除旧容器/镜像/卷或用新测试数据覆盖旧运行目录。未满足时保持8795候选和2626旧环境，5.1继续VERIFY。

人工验收等待期间旧2626仍可能产生业务数据。真正切换前必须再次执行容器内一致性备份，并比较业务表指纹及uploads/outputs；如果与候选迁移起点不同，使用新备份重建候选，仅补入已核验知识表并重新验证。不要把之前备份时间误当作切换水位。回退前同样保全新环境产生的数据，不覆盖原目录、不静默丢弃新记录。
