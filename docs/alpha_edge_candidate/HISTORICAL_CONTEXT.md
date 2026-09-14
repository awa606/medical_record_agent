# 历史事实与边缘端适用性

[返回目录](README.md)

历史证据采集于2026-09-11，本摘要整理于2026-09-14。以下为已有记录，未重新执行。

## 1.1原办公主机基线

原环境MRA-ALPHA-ENV-01针对16GB内存、512GB SSD、集显办公主机，主方案整机历史参考价2699元。原任务DONE只对应该基线建立，不代表购买或产品运行通过。Jetson候选MRA-ALPHA-EDGE-01没有继承此状态；其8GB共享内存和2070元套件参考价须按新边界另验。旧工作簿、图像和原始证据在本地homework/Alpha保留。

## 1.2历史开发机CPU实验

| 项目 | 历史结果 | 适用性 |
| --- | --- | --- |
| Docker / Compose | 29.6.1 / 5.1.4 | 开发机工具版本 |
| 容器 / health | running / healthy；GET /health返回ok | 证明存活，不代替模型或流程验收 |
| 医生页面 | HTTP 200，16849 bytes | 页面可访问 |
| FunASR | 146.264秒后ready | CPU环境预加载，不等于Jetson转写性能 |
| 五组件 | paraformer-zh-streaming、paraformer-zh、fsmn-vad、ct-punc、cam++ | 历史加载结果 |
| 模型缓存 | 180文件，6274641999 bytes | 非新采样 |
| 内存 | 4.174GiB，Docker可用15.34GiB | 单次样本，不是8GB Jetson峰值 |
| LLM | mock-deterministic-extractor | 真实LLM未通过 |
| 目标环境 | target_environment_realized=false | 目标实机未复验 |
| 任务状态 | 1.2 IN PROGRESS | 未更改正式状态 |

代码SHA为896c8f89dc4d3bc3d94381b85860f723a37be9ea，历史构建前有41个工作树状态条目；SHA不能独立重建全部未提交内容。镜像ID为sha256:60761a4b7ff6fcdb85e225b69a92bd5d9c839ce58762e852a6ef1eee3bba84cc。

## 原始来源指纹

下列文件没有复制到本目录；哈希用于和本地Alpha/sources原件对应。指纹不等于读取原件或重新验收。

| 本地sources相对文件 | SHA256 |
| --- | --- |
| 1.1_BOM基线验收记录.md | A3E608E47DDE89E468A3B2CF2C57A95F6DBBA831ED1FA125AE75275848CE3340 |
| 1.2_Docker阶段证据.md | 5EFAC7CB158177973EAC57DC3D6B8244D20058775E575A5411BB41BAA971E003 |
| docker/runtime_check_20260911.json | 0E0AFE3912353CCBBE687D725150E22545EB5236771473CDDDE5DCF8ADAECBC8 |
| docker/runtime_check_20260911.md | 261EBCD6C6AFE1D2865C5F2CF69792BFAB122BCFC15319810337A5F8B340D52C |
| docker/compose_config_20260911.yml | 2317C6DB468AAFFF7DEA0145F90FCCEE498021D298FF2628CEA0EAAF151F995F |
| docker/build_start_20260911.log | 51AAE72CA00761A5A4B8A90796A1FD0943C99600B0C6BCF59A2F532A1C0A37E5 |
| docker/readiness_poll_20260911.jsonl | A324881F7A42CD5275B3D1C64DC4566E94C8902693B079D1097194CD1BA7C0E7 |
