/* Marketing screenshot capture.
 *
 * Captures social-ready screenshots of the populated app (seeded via
 * `manage.py seed_demo`) into marketing/screenshots/. Standalone — does not
 * depend on the e2e/ Playwright config or helpers.
 *
 * Usage (from repo root, app running + seeded):
 *   1. docker compose up -d db web
 *   2. docker compose exec web python manage.py seed_demo --reset   # if needed
 *   3. NODE_PATH=node_modules BASE_URL=http://localhost:8001 node marketing/capture.js
 *
 * Env:
 *   BASE_URL  default http://localhost:8001  (host port for the web container)
 *   OUT       default marketing/screenshots
 */
const fs = require("node:fs");
const path = require("node:path");
const { chromium, devices } = require("@playwright/test");

const BASE_URL = (process.env.BASE_URL || "http://localhost:8001").replace(/\/$/, "");
const OUT = process.env.OUT || path.join(__dirname, "screenshots");

// Skip the first-run onboarding overlay so shots are clean.
const SKIP_ONBOARDING = () => { try { localStorage.setItem("uc_onboarded_v1", "1"); } catch (e) {} };

// Pages to capture full-page on desktop. `wait` is an optional selector to
// wait for (lazy-loaded content); `settle` is extra ms for animations/tiles.
const DESKTOP_PAGES = [
  { name: "map-overview",  url: "/",            wait: "#map.leaflet-container", settle: 2800, full: false },
  { name: "cleanups",      url: "/cleanups/",   wait: ".cleanup-card",          settle: 500,  full: true },
  { name: "districts",     url: "/districts/",  wait: ".district-card",         settle: 500,  full: true },
  { name: "challenges",    url: "/challenges/", wait: ".challenge-card",        settle: 500,  full: true },
  { name: "leaderboard",   url: "/leaderboard/",wait: "main",                   settle: 800,  full: true },
  { name: "events",        url: "/events/",     wait: "main",                   settle: 800,  full: true },
];

const MOBILE_PAGES = [
  { name: "map",      url: "/",          wait: "#map.leaflet-container", settle: 2800, full: false },
  { name: "cleanups", url: "/cleanups/", wait: ".cleanup-card",          settle: 500,  full: true },
];

function ensureDir(p) { fs.mkdirSync(p, { recursive: true }); }

async function capture(context, dir, pages, label) {
  const results = [];
  for (const p of pages) {
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(e.message));
    try {
      await page.goto(BASE_URL + p.url, { waitUntil: "networkidle", timeout: 30000 });
      if (p.wait) await page.waitForSelector(p.wait, { timeout: 15000 });
      // The leaderboard defaults to "This Month" (sparse at month start); the
      // "All Time" view is the better marketing shot.
      if (p.name === "leaderboard") {
        const allTime = page.getByRole("button", { name: /all time/i });
        if (await allTime.count()) { await allTime.first().click(); await page.waitForTimeout(600); }
      }
      if (p.settle) await page.waitForTimeout(p.settle);
      const file = path.join(dir, `${p.name}.png`);
      await page.screenshot({ path: file, fullPage: !!p.full });
      results.push(`  [ok]   ${label}/${p.name}.png${errors.length ? ` (JS errors: ${errors.length})` : ""}`);
    } catch (e) {
      results.push(`  [FAIL] ${label}/${p.name}: ${e.message.split("\n")[0]}`);
    } finally {
      await page.close();
    }
  }
  return results;
}

(async () => {
  ensureDir(path.join(OUT, "desktop"));
  ensureDir(path.join(OUT, "mobile"));
  const browser = await chromium.launch();
  const log = [];

  // Desktop
  const desktop = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  await desktop.addInitScript(SKIP_ONBOARDING);
  log.push(...await capture(desktop, path.join(OUT, "desktop"), DESKTOP_PAGES, "desktop"));
  await desktop.close();

  // Mobile (Pixel 7 profile)
  const mobile = await browser.newContext({ ...devices["Pixel 7"] });
  await mobile.addInitScript(SKIP_ONBOARDING);
  log.push(...await capture(mobile, path.join(OUT, "mobile"), MOBILE_PAGES, "mobile"));
  await mobile.close();

  await browser.close();
  console.log("Captured to " + OUT + ":\n" + log.join("\n"));
  const failed = log.filter((l) => l.includes("[FAIL]")).length;
  process.exit(failed ? 1 : 0);
})();
