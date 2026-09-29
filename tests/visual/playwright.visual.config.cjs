const { defineConfig } = require("@playwright/test");
const base = require("./playwright.config.cjs");
module.exports = defineConfig({
  ...base,
  testMatch: "visual.spec.cjs",
  outputDir: "../../.artifacts/alpha51-preview-v3/baseline-check",
  reporter: [
    ["list"],
    [
      "json",
      {
        outputFile:
          "../../.artifacts/alpha51-preview-v3/baseline-check-results.json",
      },
    ],
  ],
  updateSnapshots: "none",
  snapshotPathTemplate:
    "{testDir}/baselines/{platform}/{projectName}/{arg}{ext}",
  expect: {
    toHaveScreenshot: {
      animations: "disabled",
      caret: "hide",
      maxDiffPixels: 0,
    },
  },
});
