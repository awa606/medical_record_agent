# 历史产物归档与精确恢复

本轮归档仅供历史恢复与排错，不是新的稳定产品发布。当前运行目录、业务数据、授权音频、登录状态、凭据和正在排障的原始证据继续保留本地。

## 保存方式

- 源码、报告和恢复工具由 Git 保存。
- 完成隐私及许可审查的历史二进制按 SHA256 去重，存入公开仓库的历史归档 Release，标记预发布且不设为 latest。
- 每个原文件压缩为 gzip，再分成至多 1.5 GiB 的附件。JSON 清单记录原文件、压缩文件和每个分片的字节数及 SHA256。
- 恢复索引记录各历史包的相对路径与内容哈希；相同附件可恢复多份历史包中的同一文件。
- 这不是完整业务数据库备份。未公开上传的数据库、身份信息、原录音、配置凭据和敏感原件不在公开恢复范围内。

## 恢复一个文件

从归档 Release 下载所需 `blob-<SHA256>.json` 及清单列出的全部 `blob-<SHA256>.gz.part-NNN`，放入同一个全新目录。然后运行：

```powershell
python scripts/release_archive_blob.py restore --manifest 'D:\恢复\附件\blob-<SHA256>.json' --assets 'D:\恢复\附件' --output 'D:\恢复\输出\ollama-image.tar'
```

将占位 SHA256 和目标文件名替换为索引中该文件的实际值。目标文件必须尚不存在。工具先验证每个分片，再验证拼接 gzip，最后解压并验证原始字节；全部通过才发布输出文件。缺片、换序、篡改、异常解压大小和覆盖已有文件均拒绝。

镜像 tar 恢复后可用 Docker 的 `image load --input` 加载。加载镜像不等于启动旧环境；启动前仍须恢复相应配置、独立数据和模型，并避开当前端口。归档不会包含现用密钥。

## 清理边界

本地删除只处理本轮精确清单里的单个生成文件：完成公开内容审查、实际 SHA256 核对、完整远端下载及解压复核，且实际容器与启动配置均无引用后才执行。含排除项的父目录保留，不整删 `.artifacts`、模型缓存根或原主仓库。

旧 `r5`、`r6` 目录仍存在实际容器模型引用；名称旧并不意味着可删除。原主仓库包含关联工作树共享的 Git 目录，不能当作历史包清除。

## 本轮工具验证

```powershell
python -m unittest discover -s tests -p test_release_archive_blob.py -v
```

检查精确分片恢复、原文件不变、损坏分片、越界名称、既有输出保护、错误源哈希和异常解压大小。上传及实际空间释放另以本轮收据为准，工具检查不代替远端验证。

## 官方资料

- [GitHub Release 与单附件限制](https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases)
- [Docker image load](https://docs.docker.com/reference/cli/docker/image/load/)
