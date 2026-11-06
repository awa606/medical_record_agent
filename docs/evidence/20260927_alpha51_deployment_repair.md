# 5.1：真实Provider与知识包部署候选

2026-09-27，工作树 `medical_record_agent_alpha51_visual`、分支 `codex/alpha51-demo-visual-e2e`。沿用已认可详情排版；没有修改医生页面、业务API、SQLite结构、Provider或安全阈值。

## 结论

隔离候选在 `http://127.0.0.1:8795/static/doctor.html` 完成部署核验。2626仍是旧环境，未切换；原容器、2600/2666及冻结包均保留。实际Edge125%/150%证据尚缺，5.1保持VERIFY，5.3未启动。

| 检查 | 实测 |
|---|---|
| 版本 | HTML、JS及工作区CSS的HTTP内容SHA与当前工作树一致；正式页面不注入样稿场景 |
| 真实Provider | FunASR upload四组件；Ollama 0.34.0、固定摘要Qwen3:4b；edge且fallback=false |
| 健康与就绪 | `/health=200`；冷启动期间`/ready=503`，实际推理完成后200 |
| 知识包 | 仅导入4来源/4文档/39片段，未替换业务库，未导入旧管理审计；0 embedding |
| 真实查询 | 现有医生页面“查依据”得到5条FTS5结果，来源详情4/4返回200，5条来源链接已渲染；本轮不声明BGE可用或所有外部站点均可达 |
| 权限 | 未登录401；管理员登录后另一独立客户端仍401；医生管理接口403 |
| 文本路径 | 本地Qwen抽取约9.98秒；首版主诉证据冲突，医生修正后保存Revision2、逐项批准、DOCX导出；未批准导出400 |
| 否定 | 导出仍含“没有花生过敏”和“没有药物过敏史”，不含蛇咬固定内容 |
| ASR | 重放既有授权匿名11.008秒WAV；真实funasr-paraformer-zh，5.84秒；单人角色阻断，生成409 |
| 持久化 | 重建应用后9张业务/知识表的行数和逻辑SHA完全一致，含两个Revision和批准记录 |
| 网络 | app/gateway/ollama对外连接探针均BLOCKED；未宣称Windows主机物理断网 |
| 回归 | 最终完整575 passed、8 subtests passed、1 warning；网关与导入8项定向通过，前端语法、无网依赖复用镜像构建通过 |

指标与文件SHA见[结构化证据](20260927_alpha51_deployment_repair.json)。原始WAV、DOCX、截图、运行数据库、凭据及日志仅在本地 `.artifacts/alpha51-deployment-repair-20260927-1345/`。

## 本轮发现和修复

1. **部署错位**：旧2626绑定alpha31历史目录，知识表为空，病历生成仍为demo/mock。新Compose要求显式绝对目录和真实Provider，Docker健康检查改用health，真实AI仍等待ready。
2. **网关会话串用**：原共享HTTPX客户端保存了管理员登录Cookie，导致独立匿名请求被误认证。改为每请求独立客户端，并保留独立Set-Cookie及流式连接清理；单元和真实HTTP复测均通过。历史r6归档保留，但含此缺陷，不能作为当前安全/发布通过证据。
3. **知识SHA口径**：病历规范原Markdown为CRLF，既有导入读成LF。补记已验收导入文本SHA，原文SHA不覆盖。导入工具逐表校验、拒绝冲突并事务回滚；第二次同包导入不改数据库字节。
4. **跨系统SQLite检查**：Windows直接打开活跃Linux容器的WAL后出现候选disk I/O error。保留DB/WAL/SHM，停止候选并在Linux侧checkpoint恢复；quick_check为ok，两版Revision和所有业务/知识指纹一致。后续运行态查询、备份和检查统一在容器内执行。旧2626再次检查SQLite仍正常。
5. **冷启动与测试限制**：首次Qwen预热120秒超时，后续热推理成功；完整回归仍有一条Windows子进程UTF-8解码警告，未隐藏或放宽断言。文本主诉冲突如实保留，未将生成成功等同语义全对。

## 剩余门禁

原生识别重试已停止。按后续批准计划，实际Edge125%/150%直接采用人工菜单百分比及页面截图核验；当前仍未收到证据，不计PASS，不以无头视口替代。当前提交重建与复验见[切换前检查](20260927_alpha51_cutover_preflight.md)。

本次是部署修复验证；音频是重放，不是新物理麦克风验收。最终SHA的文本/上传/新录音三路径、截图基线及离线恢复仍需齐备后才关闭5.1。软件预测2026-10-07保留为基线，返工影响记R11，未静默调整16项/99h、19技术/4资源依赖或日期。

执行与回退见[部署Runbook](../runbooks/alpha51_deployment_repair.md)。唯一下一工作是补齐实际Edge缩放并按门禁切换2626，再完成对应版本三路径和恢复验收。
