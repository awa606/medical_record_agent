# 医生工作区整体候选验收

本入口直接使用 `static/doctor.html`、现有API及同一份前端逻辑。数据为合成资料，Provider固定demo/mock，仅验证排版和交互，不作为真实转写、病历模型或发布验收证据。

## 启动

在仓库根目录、已安装开发依赖的Python环境执行：

```powershell
python scripts/alpha51_workspace_review.py --port 8791
```

打开 [隔离验收页面](http://127.0.0.1:8791/workspace-review)，使用该隔离环境的演示账号登录。不要输入真实患者资料。运行数据仅保存在被Git忽略的 `.artifacts/alpha51-clinical-review/`，服务只监听本机。Ctrl+C停止，不影响2626。

顶部“版式验收场景”覆盖草稿、待采集、模拟录音、长病历、审核、角色阻断及Revision冲突；切换会重置合成修改。录音状态场景不调用麦克风。正常“开始录音”仍是原真实采音入口，需要设备授权。

旧页面对照可复制精确SHA的静态文件至 `.artifacts`，用 `--baseline-static .artifacts/<baseline>/static --port 8792` 启动。不要覆盖当前静态目录。记录旧SHA和文件哈希，两个页面使用相同fixture。

## 核对顺序

1. 1440×900下先看三栏主次；病历是否够宽、顶部是否紧凑、名称与动作是否易找。
2. 待采集与模拟录音：左栏只出现当前所需控件，停止前无提交入口。
3. 长病历：正文区域内纵向滚动，按钮不被底部操作覆盖。
4. 编辑后打开参考详情，用Esc返回；未保存字段保持原值。
5. 角色阻断与Revision冲突：状态、恢复入口清楚，不允许绕过审核导出。
6. 窄屏按按钮打开转写/参考，键盘可进出；不要把缩小视口当真实浏览器缩放。

## 自动检查

```powershell
python -m pytest tests/test_alpha51_clinical_layout_playwright.py -q
$env:ALPHA51_BROWSER_CHANNEL = 'chrome'
python -m pytest tests/test_alpha51_clinical_layout_playwright.py -q
```

设置 `ALPHA51_CLINICAL_SCREENSHOTS` 为本地 `.artifacts` 目录可保存截图。测试不写入/更新截图基线；基线必须在用户认可后人工审查。

测试场景与生产页面分离：脚本的 `/workspace-review` 和 fixture 资源只存在于该开发启动器，不修改生产公共API。

## 收口边界

候选人工认可、实际Edge125%/150%、最终SHA真实三路径和离线恢复尚需分别验收。保留PR #113 Draft、5.1 VERIFY；2626和历史2600/2666不切换，不更新冻结包，不启动5.3。
