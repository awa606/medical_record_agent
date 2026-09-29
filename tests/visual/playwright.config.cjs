const { defineConfig } = require("@playwright/test");

module.exports = defineConfig({
  testDir: __dirname,
  testMatch: "preview.spec.cjs",
  outputDir: "../../.artifacts/alpha51-preview-v3/playwright",
  fullyParallel: true,
  workers: 2,
  retries: 0,
  reporter: [
    ["list"],
    [
      "json",
      { outputFile: "../../.artifacts/alpha51-preview-v3/results.json" },
    ],
  ],
  use: {
    baseURL: "http://127.0.0.1:8768",
    locale: "zh-CN",
    timezoneId: "Asia/Shanghai",
    colorScheme: "light",
    reducedMotion: "reduce",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [
    { name: "desktop-1366", use: { viewport: { width: 1366, height: 768 } } },
    { name: "desktop-1440", use: { viewport: { width: 1440, height: 900 } } },
    { name: "desktop-1920", use: { viewport: { width: 1920, height: 1080 } } },
    { name: "narrow-1000", use: { viewport: { width: 1000, height: 720 } } },
  ],
  webServer: {
    command:
      "python -m http.server 8768 --bind 127.0.0.1 --directory ../../docs/prototypes/doctor-workspace-v3",
    cwd: __dirname,
    url: "http://127.0.0.1:8768",
    reuseExistingServer: false,
    timeout: 15000,
  },
});
