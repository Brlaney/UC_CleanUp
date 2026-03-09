const { defineConfig, devices } = require("@playwright/test");

module.exports = defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  reporter: "list",
  use: {
    headless: true,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "desktop-chrome",
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "desktop-wide",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1720, height: 980 },
      },
    },
    {
      name: "iphone-14",
      use: {
        browserName: "chromium",
        ...devices["iPhone 14"],
      },
    },
    {
      name: "pixel-7",
      use: {
        browserName: "chromium",
        ...devices["Pixel 7"],
      },
    },
  ],
});
