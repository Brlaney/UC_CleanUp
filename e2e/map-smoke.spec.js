const { execSync } = require("node:child_process");
const http = require("node:http");
const { test, expect } = require("@playwright/test");

const E2E_USERNAME = "e2e_smoke_user";
const E2E_PASSWORD = "e2e_smoke_pass_123";

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

function ensureSmokeUser() {
  const command =
    "docker compose exec -T web python manage.py shell -c \"from django.contrib.auth import get_user_model; User=get_user_model(); u,_=User.objects.get_or_create(username='" +
    E2E_USERNAME +
    "'); u.set_password('" +
    E2E_PASSWORD +
    "'); u.is_active=True; u.save(); print('ok')\"";
  try {
    execSync(command, { stdio: "pipe" });
  } catch (error) {
    throw new Error(
      "Failed to create E2E smoke user via docker compose. Ensure the docker compose stack is running."
    );
  }
}

function isIgnoredConsoleError(message) {
  return (
    message.includes("Failed to load resource: the server responded with a status of 404") &&
    message.toLowerCase().includes("favicon")
  );
}

test.describe("Map smoke", () => {
  test("login and load map with features request", async ({ page }) => {
    ensureSmokeUser();
    const baseUrl = await resolveBaseUrl();

    const consoleErrors = [];
    const pageErrors = [];

    page.on("console", (msg) => {
      if (msg.type() === "error" && !isIgnoredConsoleError(msg.text())) {
        consoleErrors.push(msg.text());
      }
    });
    page.on("pageerror", (err) => {
      pageErrors.push(err.message);
    });

    const featuresResponsePromise = page.waitForResponse(
      (resp) => resp.url().includes("/api/features/") && resp.request().method() === "GET",
      { timeout: 20_000 }
    );

    await page.goto(`${baseUrl}/accounts/login/`, { waitUntil: "domcontentloaded" });
    await expect(page.locator("form.auth-form")).toBeVisible();
    await page.fill('input[name="username"]', E2E_USERNAME);
    await page.fill('input[name="password"]', E2E_PASSWORD);

    await Promise.all([
      page.waitForURL(/\/map\/?$/),
      page.click('button[type="submit"]'),
    ]);

    await expect(page.locator("#map")).toBeVisible();
    await expect(page.locator("#map.leaflet-container")).toBeVisible();

    const featuresResponse = await featuresResponsePromise;
    expect(featuresResponse.status()).toBe(200);
    expect(pageErrors).toEqual([]);
    expect(consoleErrors).toEqual([]);
  });
});
