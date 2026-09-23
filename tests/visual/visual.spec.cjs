const { test, expect } = require("@playwright/test");
const fs = require("node:fs");
const path = require("node:path");

// 未认可样稿时必须失败，不生成或自动接受基线。后续证据文件需记录审核人及图像SHA。
test.beforeAll(() => {
  const filename = path.join(__dirname, "baselines", "approval.json");
  if (!fs.existsSync(filename))
    throw new Error(
      "VISUAL_BASELINE_NOT_APPROVED: 先完成用户视觉确认并审核固定环境截图",
    );
  const approval = JSON.parse(fs.readFileSync(filename, "utf8"));
  if (
    approval.status !== "approved" ||
    !approval.reviewed_by ||
    !approval.reviewed_at
  )
    throw new Error("VISUAL_BASELINE_NOT_APPROVED");
});
for (const state of [
  "empty",
  "recording",
  "draft",
  "editing",
  "review",
  "approved",
  "role",
  "conflict",
  "failed",
  "long",
]) {
  test(`approved layout ${state}`, async ({ page }) => {
    await page.goto("/");
    await page.getByLabel("切换演示场景").selectOption(state);
    await expect(page).toHaveScreenshot(`${state}.png`);
  });
}
