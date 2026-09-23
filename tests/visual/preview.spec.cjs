const { test, expect } = require("@playwright/test");

async function selectScenario(page, scenario) {
  await page.getByText("样稿验收工具", { exact: true }).click();
  await page.getByLabel("切换演示场景").selectOption(scenario);
}
test.beforeEach(async ({ page }) => {
  await page.goto("/");
  await selectScenario(page, "draft");
});
test.afterEach(async ({ page }, info) => {
  await page.screenshot({
    path: info.outputPath("review-candidate.png"),
    animations: "disabled",
  });
});

for (const scenario of [
  "draft",
  "empty",
  "recording",
  "processing",
  "editing",
  "review",
  "approved",
  "role",
  "conflict",
  "failed",
  "long",
]) {
  test(`layout ${scenario}`, async ({ page }) => {
    await selectScenario(page, scenario);
    const geometry = await page.evaluate(() => {
      const paper = document
        .querySelector("#paper-scroll")
        .getBoundingClientRect();
      const actions = document
        .querySelector(".ml-action-bar")
        .getBoundingClientRect();
      const panel = document.querySelector("#reference-panel");
      const action = document.querySelector("#primary-action");
      const button = action.getBoundingClientRect();
      const modal = panel.getAttribute("aria-modal") === "true";
      return {
        width: innerWidth,
        documentWidth: document.documentElement.scrollWidth,
        bodyWidth: document.body.scrollWidth,
        paperBottom: paper.bottom,
        actionTop: actions.top,
        actionBottom: actions.bottom,
        height: innerHeight,
        actionWidth: button.width,
        actionHit:
          modal ||
          action.contains(
            document.elementFromPoint(
              button.x + button.width / 2,
              button.y + button.height / 2,
            ),
          ),
      };
    });
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.width);
    expect(geometry.bodyWidth).toBeLessThanOrEqual(geometry.width);
    expect(geometry.paperBottom).toBeLessThanOrEqual(geometry.actionTop + 1);
    expect(geometry.actionBottom).toBeLessThanOrEqual(geometry.height);
    expect(geometry.actionWidth).toBeGreaterThanOrEqual(100);
    expect(geometry.actionHit).toBe(true);
    await expect(
      page.getByText("匿名固定数据 · 未执行录音或真实模型", { exact: false }),
    ).toBeVisible();
    if (scenario === "recording") {
      await expect(
        page.getByRole("button", { name: "模拟提交", exact: true }),
      ).toBeDisabled();
      const heights = await page
        .locator(".ml-rec-controls button")
        .evaluateAll((els) => els.map((e) => e.getBoundingClientRect().height));
      expect(Math.max(...heights)).toBeLessThanOrEqual(48);
    }
  });
}

test("editing save review invalidation and escaped content", async ({
  page,
}) => {
  await page.getByRole("button", { name: "编辑病历", exact: true }).click();
  const text = "医生补充示例 <img src=x onerror=alert(1)>，否认胸痛。";
  await page.getByRole("textbox", { name: "现病史", exact: true }).fill(text);
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.locator('[data-field="present_illness"] p')).toHaveText(
    text,
  );
  await expect(page.locator('[data-field="present_illness"] img')).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "审核病历", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "确认审核（示意）" }),
  ).toBeDisabled();
  await page.getByLabel("我已核对本页匿名示例内容").check();
  await page.getByRole("button", { name: "确认审核（示意）" }).click();
  await expect(page.locator("#phase-badge")).toHaveText("审核完成 · 示意");
  await page.getByRole("button", { name: "修改病历", exact: true }).click();
  await page
    .getByRole("textbox", { name: "主诉", exact: true })
    .fill("再次修改");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.locator("#phase-badge")).toHaveText("等待医生审核");
  await expect(
    page.getByRole("button", { name: "模拟导出", exact: true }),
  ).toHaveCount(0);
});

test("cancel restores values and conflict keeps local edits", async ({
  page,
}) => {
  const before = await page
    .locator('[data-field="chief_complaint"] p')
    .textContent();
  await page.getByRole("button", { name: "编辑病历", exact: true }).click();
  await page
    .getByRole("textbox", { name: "主诉", exact: true })
    .fill("未保存内容");
  await page.getByRole("button", { name: "取消修改", exact: true }).click();
  await expect(page.locator('[data-field="chief_complaint"] p')).toHaveText(
    before,
  );
  await selectScenario(page, "conflict");
  await expect(page.locator("#notice")).toContainText("本地修改已保留");
  await expect(
    page.getByRole("textbox", { name: "现病史", exact: true }),
  ).toContainText("本地新增内容示例");
});

test("read-only evidence panel and keyboard dismissal", async ({ page }) => {
  await page.getByRole("button", { name: "原文证据", exact: true }).click();
  await expect(page.locator("#panel-content")).toContainText("absent · 否认");
  await expect(page.locator("#panel-content textarea")).toHaveCount(0);
  if (page.viewportSize().width < 1200) {
    await expect(page.locator("#reference-panel")).toHaveAttribute(
      "aria-modal",
      "true",
    );
    await expect(page.locator(".ml-document-area")).toHaveAttribute(
      "inert",
      "",
    );
    await page
      .getByRole("button", { name: "返回临床提示", exact: true })
      .press("Tab");
    await expect(
      page.getByRole("button", { name: "返回临床提示", exact: true }),
    ).toBeFocused();
  }
  await page.keyboard.press("Escape");
  if (page.viewportSize().width < 1200)
    await expect(page.locator("#reference-panel")).toBeHidden();
  else await expect(page.locator("#panel-title")).toHaveText("核对与参考");
  await expect(
    page.getByRole("button", { name: "原文证据", exact: true }),
  ).toBeFocused();
});

test("recording stop then cancel is compact and leaves empty state", async ({
  page,
}) => {
  await selectScenario(page, "recording");
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "试听示意", exact: true }),
  ).toBeEnabled();
  await expect(
    page.getByRole("button", { name: "模拟提交", exact: true }),
  ).toBeEnabled();
  await page.locator("#record-cancel").click();
  await expect(page.locator("#phase-badge")).toHaveText("待采集");
  if (page.viewportSize().width < 1200)
    await expect(page.locator("#reference-panel")).toBeHidden();
  else await expect(page.locator("#panel-title")).toHaveText("核对与参考");
});

test("no API calls or external requests in sample workflow", async ({
  page,
}) => {
  const unexpected = [];
  page.on("request", (request) => {
    if (
      request.method() !== "GET" ||
      !request.url().startsWith("http://127.0.0.1:8768/")
    )
      unexpected.push(request.url());
  });
  await selectScenario(page, "role");
  await page.getByRole("button", { name: "确认说话人", exact: true }).click();
  await page.locator("#role-a").selectOption("doctor");
  await page.locator("#role-b").selectOption("patient");
  await page
    .getByRole("button", { name: "确认映射并继续", exact: true })
    .click();
  await expect(page.locator("#phase-badge")).toHaveText("草稿待处理");
  expect(unexpected).toEqual([]);
});

test("readable three columns keep geometry when evidence opens", async ({
  page,
}) => {
  const before = await page.locator(".ml-document-area").boundingBox();
  await expect(page.locator(".ml-transcript-column")).toBeVisible();
  const sizes = await page.evaluate(() => ({
    transcript: parseFloat(
      getComputedStyle(document.querySelector(".ml-speech p")).fontSize,
    ),
    record: parseFloat(
      getComputedStyle(document.querySelector(".ml-field p")).fontSize,
    ),
    action: parseFloat(
      getComputedStyle(document.querySelector("#primary-action")).fontSize,
    ),
    label: parseFloat(
      getComputedStyle(document.querySelector(".ml-field h3")).fontSize,
    ),
  }));
  expect(sizes.transcript).toBeGreaterThanOrEqual(16);
  expect(sizes.record).toBeGreaterThanOrEqual(17);
  expect(sizes.action).toBeGreaterThanOrEqual(14);
  expect(sizes.label).toBeGreaterThanOrEqual(16);
  if (page.viewportSize().width >= 1200) {
    await expect(page.locator("#reference-panel")).toBeVisible();
    const left = await page.locator(".ml-transcript-column").boundingBox();
    const right = await page.locator("#reference-panel").boundingBox();
    expect(left.x + left.width).toBeLessThanOrEqual(before.x);
    expect(before.x + before.width).toBeLessThanOrEqual(right.x);
  }
  await page.getByRole("button", { name: "原文证据", exact: true }).click();
  const after = await page.locator(".ml-document-area").boundingBox();
  expect(after).toEqual(before);
  const gutter = await page
    .locator(".ml-workspace")
    .evaluate((el) => parseFloat(getComputedStyle(el).columnGap));
  expect(gutter).toBeGreaterThanOrEqual(20);
  await expect(page.locator("#panel-content")).toContainText("absent");
});

test("doctor starts consultation without selecting test scenarios", async ({
  page,
}) => {
  await page.reload();
  await expect(page.getByLabel("切换演示场景")).toBeHidden();
  await expect(page.locator("#paper")).toBeHidden();
  await expect(
    page.getByRole("button", { name: "原文证据", exact: true }),
  ).toBeDisabled();
  await expect(page.locator(".ml-audio-preview")).toBeHidden();
  await page.getByRole("button", { name: "开始录音", exact: true }).click();
  await expect(page.locator("#record-label")).toContainText("正在录音");
  await expect(page.locator("#paper")).toBeHidden();
  await page.getByRole("button", { name: "停止", exact: true }).click();
  await expect(page.locator("#record-listen")).toBeEnabled();
  await page.getByRole("button", { name: "模拟提交", exact: true }).click();
  await expect(page.locator("#phase-badge")).toHaveText("草稿待处理");
  await expect(page.locator("#paper")).toBeVisible();
  await expect(page.getByLabel("切换演示场景")).toBeHidden();
});
