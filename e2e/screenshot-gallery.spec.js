const fs = require("node:fs");
const path = require("node:path");
const { test, expect } = require("@playwright/test");

const {
  assertNoClientErrors,
  attachClientErrorCollectors,
  loginAndWaitForMap,
  openMapPage,
  resolveBaseUrl,
  seedScreenshotDemo,
} = require("./helpers/app");

const SCREENSHOT_ROOT = path.join(process.cwd(), "artifacts", "screenshots");

function projectCredentials(projectName) {
  const slug = projectName.replace(/[^a-z0-9]+/gi, "_").toLowerCase();
  return {
    username: `screenshot_${slug}`,
    password: `screenshot_pass_${slug}_123`,
  };
}

function screenshotPath(testInfo, filename) {
  const filePath = path.join(SCREENSHOT_ROOT, testInfo.project.name, filename);
  fs.mkdirSync(path.dirname(filePath), { recursive: true });
  return filePath;
}

async function saveScreenshot(page, testInfo, filename, fullPage = false) {
  await page.screenshot({
    path: screenshotPath(testInfo, filename),
    fullPage,
  });
}

test.describe("Screenshot gallery", () => {
  test("capture map, updates, and impact views", async ({ page }, testInfo) => {
    test.slow();

    const credentials = projectCredentials(testInfo.project.name);
    const demo = seedScreenshotDemo(credentials);
    const baseUrl = await resolveBaseUrl();
    const clientErrors = attachClientErrorCollectors(page);

    await loginAndWaitForMap(page, baseUrl, demo.username, demo.password);
    await saveScreenshot(page, testInfo, "map-overview.png");

    await openMapPage(
      page,
      baseUrl,
      `/map/?focus_type=trash_site&focus_id=${demo.cleaned_site_id}`
    );
    await expect(page.locator("#detail-content h3")).toContainText("Screenshot Demo Cleaned Site");
    await saveScreenshot(page, testInfo, "map-trash-focus.png");

    await openMapPage(
      page,
      baseUrl,
      `/map/?focus_type=route_cleanup&focus_id=${demo.route_id}`
    );
    await expect(page.locator("#detail-content h3")).toContainText("Cleanup Route");
    await saveScreenshot(page, testInfo, "map-route-focus.png");

    await page.goto(`${baseUrl}/updates/`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "Recent Updates" })).toBeVisible();
    await saveScreenshot(page, testInfo, "updates.png", true);

    await page.goto(`${baseUrl}/impact/`, { waitUntil: "domcontentloaded" });
    await expect(page.getByRole("heading", { name: "My Impact" })).toBeVisible();
    await saveScreenshot(page, testInfo, "impact.png", true);

    assertNoClientErrors(clientErrors);
  });
});
