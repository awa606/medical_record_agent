# Alpha 1.2 目标环境资源 Spike 检查点

本目录记录从PR #100合并后的 `main` 建立的资源筛选实验。它是开发机上的 **Resource Feasibility Estimate**，不是Jetson验收。

## 基线

- PR #100 merge commit：`db4f5f809377963c4a5a842fbc79eeaaf8932544`
- 分支：`codex/alpha12-jetson-runtime`
- 应用镜像：`sha256:b4d2969770a9aad2223e9ca5a3a1189f96e2b112da15bd8474fb8c7fd99c1f5e`
- Ollama镜像：`sha256:684d8674b4315fa18f4f0e973a118ec2652ed96f67563277839985175858e0ba`
- Ollama模型：`qwen3:4b@359d7dd4bcdab3d86b87d73ac27966f4dbb9f5efdfcc75d34a8764a09474fae7`
- 下限候选：`qwen3:1.7b@8f68893c685c`（Q4_K_M，约1.4GB）
- 运行环境：Windows开发机、Docker Desktop linux/amd64、CPU-only资源筛选
- 额外swap：禁用

## 已完成结果

| Phase | 条件 | 结果 | 判定 |
|---|---|---|---|
| A 当前常驻 | FastAPI/FunASR 4864 MiB + Ollama 1792 MiB | ASR预热时OOMKilled，Exit 137 | FAIL |
| B ASR隔离 | FastAPI/FunASR 6656 MiB | 预热84.9秒；3段音频成功3/3，最大RTF 0.1514；峰值6,629,724,160字节，无swap/OOM | PASS（开发机资源筛选） |
| C LLM优化Smoke | Ollama 5888 MiB + runner 640 MiB，4B/2048/512/keep_alive=0 | 峰值2.903 GiB，无swap/OOM；单例300秒超时，Schema 0/1；随后成功卸载 | FAIL/INCOMPLETE |
| C2 1.7B停止条件复测 | 与C相同资源和参数，`qwen3:1.7b` | 峰值1,921,376,256字节，无swap/OOM；单例300.110秒超时，Schema 0/1；0.912秒卸载 | FAIL；停止，不扩到10例 |

Phase A证实当前共驻留策略不适合6.5 GiB预算。Phase B在恢复Docker后完成，证明upload四组件和三段既有脱敏音频可在开发机的6.5 GiB限额内运行；约6.17 GiB的峰值意味着余量很小。Phase C/C2证实4B和1.7B权重都能装入CPU容器预算并在请求后卸载，但两者都没有在300秒停止条件内产生有效Schema；1.7B不能仅凭更低内存成为替代版本。

## 未完成项

- [x] Phase B HTTP ready与三段固定音频ASR。
- [x] Phase C 4B单例停止条件：300秒超时，Schema 0/1，不扩到10例。
- [x] Phase C2 1.7B单例停止条件：300秒超时，Schema 0/1，不扩到10例。
- [ ] 一次GPU诊断对照；仅作主存/显存分离说明。
- [ ] Jetson ARM64/CUDA、温度、功耗和持续稳定性实机验证。
- [ ] 完整BOM两份含税运费报价。

## 数据保护与清理

- 原始音频、转写正文、模型权重、数据库和密码未提交。
- LLM结果只保存输入/输出哈希和Schema判定。
- 全量本地日志位于被Git忽略的 `.artifacts/target-env-spike-20260914/` 和 `.artifacts/target-env-spike-20260915/`。
- 每轮结束均移除本轮 `mra-alpha12-spike-*` 容器与网络；未停止用户原有容器。
- Obsidian已通过Project Planner Engineering API把1.1重开为`verify`并清除当前核验标志；1.2保持`in_progress / hardware blocked`，1.3保持`backlog / research-only`。插件因Research与Design Gate未通过拒绝向受控`evidence`字段追加本轮记录，原Evidence数组保持不变。

## 恢复顺序

1. 确认Docker Desktop可用，检查没有同名Spike容器。
2. Phase B结果以三音频哈希、RTF和cgroup峰值重算。
3. 重读[`checkpoint.json`](checkpoint.json)及对应SHA，确认失败结果与开发机证据边界。
4. 取得完整BOM报价并在真实Jetson上分层验证；不得把开发机结果写成Jetson PASS。

## 当前门禁

- Research Gate：`NEEDS MORE EVIDENCE`
- Target Environment Gate：`MORE_EVIDENCE_REQUIRED`
- Jetson采购：未执行

Docker Desktop在恢复运行前遇到两组损坏的Windows Unix socket。诊断、可逆修复和数据盘保护记录见 [Docker Desktop运行端点恢复](Docker_Desktop_runtime_socket_recovery.md)。
