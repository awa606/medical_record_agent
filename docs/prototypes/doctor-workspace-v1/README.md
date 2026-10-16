# 医生工作区样稿 V1（未获认可）

**视觉审核：REJECTED。** 2026-09-23，用户反馈“不认可，需要重新调整布局”。本版仅保留为设计实验记录，不得晋升为生产页面或截图基线。

## 查看与试用

在仓库根目录运行：

```powershell
python -m http.server 8767 --bind 127.0.0.1 --directory docs/prototypes/doctor-workspace-v1
```

打开 [本地样稿](http://127.0.0.1:8767/)。右上角可切换11种场景；病历可编辑、取消、模拟保存和模拟审核，右侧可查看转写、原文证据、来源卡片及紧凑录音控件。

所有数据均为合成示例。没有API请求、真实录音、模型调用、业务数据库写入或正式文件导出。录音与检索只展示交互，不计入任何真实E2E通过数。内容安全策略禁止网络请求和表单提交。

## 当前边界

- 生产 `static/doctor.html`、两套生产CSS及 `doctor.js` 均未修改。
- 不加载生产旧样式；样稿区域样式独立，以便未来批准后保留同一结构接入业务。
- 已验证的64项几何/交互检查不代表视觉认可。用户已否决，必须重做样稿。
- 不将此版复制到2626，不创建稳定冻结包。
- 用户认可新版后，才审核固定运行环境的图片基线、接现有业务接口并开展5.1真实三路径验收。

## 测试

```powershell
cd tests/visual
npm ci --ignore-scripts
npx playwright install chromium
npm test
```

测试使用隔离8768端口；截图、JSON结果及失败追踪保存到 `.artifacts/alpha51-preview/`，不提交Git。四种尺寸为1366×768、1440×900、1920×1080和1000×720。

`npm run test:visual` 是独立图片比较门禁。没有已审批基线时返回 `VISUAL_BASELINE_NOT_APPROVED`；不得用 `--update-snapshots` 将失败图片自动晋升为已认可设计。CI当前仅执行几何与交互检查，不声称图片比较或审美验收通过。

后续须在固定Linux/Chromium/字体环境审核图片，并记录核验人、时间、代码SHA和每张图片SHA。Windows截图不能直接当作Linux参考图。参考：[Playwright视觉比较](https://playwright.dev/docs/test-snapshots)。
