const { execSync } = require("node:child_process");
const http = require("node:http");
const { expect } = require("@playwright/test");

const DEFAULT_E2E_USERNAME = process.env.E2E_USERNAME || "screenshot_demo";
const DEFAULT_E2E_PASSWORD = process.env.E2E_PASSWORD || "screenshot_demo_pass_123";

function ping(url) {
  return new Promise((resolve) => {
    const req = http.get(`${url}/accounts/login/`, { timeout: 3_000 }, (res) => {
      resolve(res.statusCode && res.statusCode < 500);
      res.resume();
    });
    req.on("error", () => resolve(false));
    req.on("timeout", () => {
      req.destroy();
      resolve(false);
    });
  });
}

async function resolveBaseUrl() {
  const candidates = [
    process.env.E2E_BASE_URL,
    "http://127.0.0.1:8000",
    "http://127.0.0.1:8001",
  ].filter(Boolean);

  for (const candidate of candidates) {
    // eslint-disable-next-line no-await-in-loop
    const ok = await ping(candidate);
    if (ok) {
      return candidate;
    }
  }

  throw new Error(
    `Could not reach app on any candidate URL: ${candidates.join(", ")}. Start docker compose first.`
  );
}

function runDockerManageCommand(command, failureMessage) {
  try {
    return execSync(`docker compose exec -T web python manage.py ${command}`, {
      stdio: "pipe",
      encoding: "utf-8",
    }).trim();
  } catch (_error) {
    throw new Error(failureMessage);
  }
}

function seedScreenshotDemo(options = {}) {
  const username = options.username || DEFAULT_E2E_USERNAME;
  const password = options.password || DEFAULT_E2E_PASSWORD;
  const output = runDockerManageCommand(
    `seed_screenshot_demo --username ${username} --password ${password} --reset --json`,
    "Failed to seed screenshot demo data. Ensure the docker compose stack is running."
  );

  try {
    return JSON.parse(output);
  } catch (_error) {
    throw new Error(`Unexpected screenshot seed output: ${output}`);
  }
}

function isIgnoredConsoleError(message) {
  return (
    message.includes("Failed to load resource: the server responded with a status of 404") &&
    message.toLowerCase().includes("favicon")
  );
}

function attachClientErrorCollectors(page) {
  const consoleErrors = [];
  const pageErrors = [];

  page.on("console", (msg) => {
    if (msg.type() === "error" && !isIgnoredConsoleError(msg.text())) {
      consoleErrors.push(msg.text());
    }
  });
  page.on("pageerror", (error) => {
    pageErrors.push(error.message);
  });

  return { consoleErrors, pageErrors };
}

function assertNoClientErrors(errorState) {
  expect(errorState.pageErrors).toEqual([]);
  expect(errorState.consoleErrors).toEqual([]);
}

async function waitForMapViewport(page) {
  await expect(page.locator("#map")).toBeVisible();
  await expect(page.locator("#map.leaflet-container")).toBeVisible();
  await page.waitForFunction(
    () => document.querySelectorAll("#map .leaflet-tile-loaded").length > 0,
    null,
    { timeout: 15_000 }
  );
  await page.waitForTimeout(600);
}

async function loginAndWaitForMap(page, baseUrl, username, password) {
  const featuresResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/api/features/") && resp.request().method() === "GET",
    { timeout: 20_000 }
  );

  await page.goto(`${baseUrl}/accounts/login/`, { waitUntil: "domcontentloaded" });
  await expect(page.locator("form.auth-form")).toBeVisible();
  await page.fill('input[name="username"]', username);
  await page.fill('input[name="password"]', password);

  await Promise.all([
    page.waitForURL(/\/$/),
    page.click('button[type="submit"]'),
  ]);

  await waitForMapViewport(page);
  const featuresResponse = await featuresResponsePromise;
  expect(featuresResponse.status()).toBe(200);
}

async function openMapPage(page, baseUrl, path = "/") {
  const featuresResponsePromise = page.waitForResponse(
    (resp) => resp.url().includes("/api/features/") && resp.request().method() === "GET",
    { timeout: 20_000 }
  );

  await page.goto(`${baseUrl}${path}`, { waitUntil: "domcontentloaded" });
  await waitForMapViewport(page);
  const featuresResponse = await featuresResponsePromise;
  expect(featuresResponse.status()).toBe(200);
}

module.exports = {
  assertNoClientErrors,
  attachClientErrorCollectors,
  loginAndWaitForMap,
  openMapPage,
  resolveBaseUrl,
  seedScreenshotDemo,
};
