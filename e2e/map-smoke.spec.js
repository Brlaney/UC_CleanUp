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
  test("login and load map with features request", async ({ page }, testInfo) => {
    const credentials = projectCredentials(testInfo.project.name);
    const demo = seedScreenshotDemo(credentials);
    const baseUrl = await resolveBaseUrl();
    const clientErrors = attachClientErrorCollectors(page);

    await loginAndWaitForMap(page, baseUrl, demo.username, demo.password);
    await expect(page.locator("#map")).toBeVisible();
    await expect(page.locator("#map.leaflet-container")).toBeVisible();
    await expect(page.locator("#overlay-six-county-toggle")).toBeVisible();
    await page.locator("#overlay-six-county-toggle").check();
    await expect(page.locator("#overlay-six-county-toggle")).toBeChecked();
    await expect(page.locator("#overlay-putnam-toggle")).not.toBeChecked();
    assertNoClientErrors(clientErrors);
  });
});
