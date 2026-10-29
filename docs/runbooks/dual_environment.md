# 展示版与使用测试版运行说明

本机交付清单位于 `.artifacts/alpha51-dual-environment-20260929/deployment-manifest.json`。文件含绝对数据目录、镜像、资源SHA和后端SHA；不是凭据文件。账号仅在本地私有文件，不写入Git。

## 日常使用

1. 双击桌面“MediListen 使用测试版”或“MediListen 展示版”。
2. 先保存/取消修改、结束录音及生成，退出并关闭旧页面，再点“切换到本版”。
3. 模型就绪后打开工作台。测试版的“本机测试账号”打开本地凭据说明；管理员和医生账号不同。
4. 数据浏览器使用本版启动器打开/刷新；实际端口按绑定探测分配，不记忆旧地址。快照有环境和时间，不是实时库。

两个配置分别为该证据目录的 `test/launcher.json`、`showcase/launcher.json`。两者互相登记peer_config，Cookie、runtime、Compose项目均不同，仅只读模型文件复用。未保存内容需要用户确认；后台任务检查不取代该确认。禁用自动重启，避免Docker重启时同时加载两套模型。

## 维护检查

```powershell
python scripts/doctor_pilot.py status --config .artifacts/alpha51-dual-environment-20260929/test/launcher.json
python scripts/doctor_pilot.py status --config .artifacts/alpha51-dual-environment-20260929/showcase/launcher.json
```

健康仅证明服务存活；ready包含真实模型探测，冷启动需要等待。失败按状态处理，不改为Mock。资源或镜像不符时停止修补配置，先核对部署清单。

展示版只叠加已通过的静态修复及Cookie可配置项，后端保留8afc6bd；使用测试版为2ba52dd完整后端。启动器和文档后续提交不改变已运行的应用SHA。

## 回退

旧容器 `mra51repair8795-{app,gateway,ollama}-1` 保留停止；新展示项目 `mra51showcase8795` 使用同一原展示数据目录。维护前确认所有页面已保存退出、两套无生成或录音任务。

1. 使用新展示启动器停止服务；同时确认测试版停止，8795没有其他进程占用。
2. 核对旧容器镜像为清单中保存的 `sha256:24a5be7f284fbd095b5863b7fa312ac224fa43889ea5af119dc9e59168177358`、挂载为原运行目录。
3. 按Ollama→应用→网关启动旧三容器。检查health、页面和业务记录；模型未就绪继续阻断生成。
4. 返回新版本前停止旧三容器，再使用新配置启动。不得让两个应用同时写同一展示库。

本轮实际回退核验页面与health成功，未重复旧模型推理；一致性备份 `dual-env-before-20260929.sqlite3` 留在原展示runtime，SHA见交付证据。升级未改表结构，因此正常回退不覆盖数据库。若后续新增了业务记录，不得用旧备份覆盖；先做新的SQLite Backup并排查。

原2626、2600、2666与本次双环境独立，不由这两个启动器管理。完整离线恢复候选仍按5.1发布门禁另行验收。
