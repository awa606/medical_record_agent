# 历史产物归档与精确恢复

本轮归档仅供历史恢复与排错，不是新的稳定产品发布。当前运行目录、业务数据、授权音频、登录状态、凭据和正在排障的原始证据继续保留本地。

## 保存方式

- 源码、报告和恢复工具由 Git 保存。
- 完成隐私及许可审查的历史二进制按 SHA256 去重，存入公开仓库的历史归档 Release，标记预发布且不设为 latest。
- 每个原文件压缩为 gzip，JSON 清单记录原文件、压缩文件和每个分片的字节数及 SHA256。本轮 1.5 GiB 分片上传出现 HTTP 408，改为至多 64 MiB 分片；只重分压缩流，不修改原文件或重新压缩。
- 恢复索引记录各历史包的相对路径与内容哈希；相同附件可恢复多份历史包中的同一文件。
- 这不是完整业务数据库备份。未公开上传的数据库、身份信息、原录音、配置凭据和敏感原件不在公开恢复范围内。

## 恢复一个文件

本轮使用 [第二次归档传输](https://github.com/awa606/medical_record_agent/releases/tag/archive-medilisten-20261021-02)。[首次传输](https://github.com/awa606/medical_record_agent/releases/tag/archive-medilisten-20261021-01)保留失败记录，不能用来恢复。先核对第二次传输的最终验证收据；附件尚未齐全或收据不是通过状态时，不删除任何本地原件。

从归档 Release 下载所需 `blob-<SHA256>.json` 及清单列出的全部 `blob-<SHA256>.gz.part-NNN`，放入同一个全新目录。安装了 GitHub CLI 的电脑可使用以下命令；必须指定本次标签，不使用“最新版本”，也不下载以 `failed-` 开头的未完成附件：

```powershell
gh release download archive-medilisten-20261021-02 --repo awa606/medical_record_agent --pattern 'blob-<SHA256>*' --dir 'D:\恢复\附件'
```

随后在当前源码根目录运行恢复工具：

```powershell
python scripts/release_archive_blob.py restore --manifest 'D:\恢复\附件\blob-<SHA256>.json' --assets 'D:\恢复\附件' --output 'D:\恢复\输出\ollama-image.tar'
```

将占位 SHA256 和目标文件名替换为索引中该文件的实际值。目标文件必须尚不存在。工具先验证每个分片，再验证拼接 gzip，最后解压并验证原始字节；全部通过才发布输出文件。缺片、换序、篡改、异常解压大小和覆盖已有文件均拒绝。

镜像 tar 恢复后可用 Docker 的 `image load --input` 加载。加载镜像不等于启动旧环境；启动前仍须恢复相应配置、独立数据和模型，并避开当前端口。归档不会包含现用密钥。

## 查找某个旧包中的模型文件

先下载 `archive-recovery-index.json`，按旧包名及文件的 `relative_path` 查找记录。`archive.kind` 决定恢复方式：

| 索引类型 | 恢复方法 |
|---|---|
| `gzip-parts` | 用上面的恢复命令取得原文件，并核对该记录的 SHA256。 |
| `tar-member-in-gzip-parts` | 先还原模型集合的 tar，再向全新目录提取 `archive.member` 指定的成员；核对该成员的字节数和 SHA256。 |
| `zip-member` | 下载并校验指定 ZIP，只提取 `archive.member` 指定的成员，再核对成员校验值。 |

FunASR 集合只包含已审查的模型和配置文件，Qwen 配套元数据单独保存为 ZIP。不能把恢复出的集合目录直接覆盖当前模型目录，也不能只校验外层压缩包而省略目标成员的核对。

清理后的旧包保留 `ARCHIVED_FILES_20261021.json`，只列出该包本轮实际移走的文件。最终 `archive-completion-receipt.json` 说明远端取回、文件清理和现用依赖复查的结果；初始恢复索引里的待核验状态是创建时记录，保留不改，由最终收据补充结果。

2026-10-22 收尾结果：171 项原始白名单附件、5 个原始载荷及指定模型成员均已完整取回核验；额外的[完成收据](https://github.com/awa606/medical_record_agent/releases/download/archive-medilisten-20261021-02/archive-completion-receipt.json)也已独立取回。C 盘精确清理 121 项历史副本，D 盘精确清理 340 项临时传输副本。实际空间、保留项和执行边界见[清理证据](../evidence/20261021_release_archive_cleanup.md)。不需要为了查看旧报告而恢复整套镜像或模型，只取回本次需要的文件。

## 清理边界

本地删除只处理本轮精确清单里的单个生成文件：完成公开内容审查、实际 SHA256 核对、完整远端下载及解压复核，且实际容器与启动配置均无引用后才执行。含排除项的父目录保留，不整删 `.artifacts`、模型缓存根或原主仓库。

旧 `r5`、`r6` 目录仍存在实际容器模型引用；名称旧并不意味着可删除。原主仓库包含关联工作树共享的 Git 目录，不能当作历史包清除。

## 后续迭代的保留方式

本地默认保留当前源码与报告、一套开发环境、实际使用的运行包，以及当前排障所需证据。仍被容器或启动器引用的旧模型作为例外单独登记；解除引用并验证替代路径以前继续保留。

旧包的镜像与模型按内容哈希复用归档，不为每个版本重复上传相同二进制。每个版本保留自己的文件映射、原验收结论及恢复入口。失败产物不能改标为稳定版本；包含私人录音、数据或凭据的部分继续本地保护，不能因为其他文件已经公开归档就一并删除。

一次归档的收尾应同时有远端完整取回记录、本地精确删除记录和当前运行依赖复查。仅有压缩包、Release页面或上传成功提示，均不等于已完成空间回收。

## 本轮工具验证

```powershell
python -m unittest discover -s tests -p test_release_archive_blob.py -v
```

检查精确分片恢复、原文件不变、损坏分片、越界名称、既有输出保护、错误源哈希和异常解压大小。上传及实际空间释放另以本轮收据为准，工具检查不代替远端验证。

## 官方资料

- [GitHub Release 与单附件限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [Docker image load](https://docs.docker.com/reference/cli/docker/image/load/)
