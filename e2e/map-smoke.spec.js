const { test, expect } = require("@playwright/test");

const {
  assertNoClientErrors,
  attachClientErrorCollectors,
  loginAndWaitForMap,
  resolveBaseUrl,
  seedScreenshotDemo,
} = require("./helpers/app");

function projectCredentials(projectName) {
  const slug = projectName.replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  return {
    username: `e2e_${slug}`,
    password: `e2e_pass_${slug}_123`,
  };
}

test.describe("Map smoke", () => {
  test("public map loads with district boundary", async ({ page }) => {
    const baseUrl = await resolveBaseUrl();
    const clientErrors = attachClientErrorCollectors(page);

    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    await expect(page.locator("#map")).toBeVisible();
    await expect(page.locator("#map.leaflet-container")).toBeVisible();

    // Mode switcher should be present
    await expect(page.locator("#btn-mode-report")).toBeVisible();
    await expect(page.locator("#btn-mode-cleanup")).toBeVisible();

    assertNoClientErrors(clientErrors);
  });

  test("login and access report mode", async ({ page }, testInfo) => {
    const credentials = projectCredentials(testInfo.project.name);
    const demo = seedScreenshotDemo(credentials);
    const baseUrl = await resolveBaseUrl();
    const clientErrors = attachClientErrorCollectors(page);

    await loginAndWaitForMap(page, baseUrl, demo.username, demo.password);
    await expect(page.locator("#map")).toBeVisible();
    await expect(page.locator("#map.leaflet-container")).toBeVisible();

    // Click report mode and verify panel appears
    await page.click("#btn-mode-report");
    await expect(page.locator("#report-panel")).toBeVisible();

    assertNoClientErrors(clientErrors);
  });
});
