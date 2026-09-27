// UI smoke suite (Cycle 2 · §8.1): create → publish → evaluate → complete → import legacy → analytics.
// Needs a running app with the reference library loaded:
//   python data/tools/ingest.py --reset && uvicorn app.main:app --port 8000   (from backend/)
//   BASE_URL=http://localhost:8000 CHROME=/path/to/chrome node e2e/smoke.mjs
import { chromium } from "playwright-core";
import path from "node:path";
import { fileURLToPath } from "node:url";

const BASE = process.env.BASE_URL ?? "http://localhost:8000";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const SHOTS = process.env.SHOTS; // optional directory for screenshots
const browser = await chromium.launch({ executablePath: process.env.CHROME || undefined });
const page = await browser.newPage({ viewport: { width: 1400, height: 950 } });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));
const results = [];
const snap = (n) => SHOTS && page.screenshot({ path: `${SHOTS}/${n}.png`, fullPage: true });

async function step(name, fn) {
  try { await fn(); results.push(["PASS", name]); }
  catch (e) { results.push(["FAIL", name, e.message.split("\n")[0]]); await snap(`fail-${name.replace(/\W+/g, "-")}`); }
}

const unique = `Smoke ${Date.now() % 100000}`;

await step("library lists the reference scorecards", async () => {
  await page.goto(BASE + "/");
  await page.getByText("Assessment Quality").first().waitFor({ timeout: 5000 });
  if ((await page.locator(".grid.cards > .card").count()) < 6) throw new Error("fewer than 6 scorecards");
});

await step("create, fill and publish a scorecard", async () => {
  await page.click("text=+ New scorecard");
  await page.fill("input[placeholder='e.g. Sales Proposal Quality']", unique);
  await page.click("text=Create draft");
  await page.waitForSelector("text=Purpose — why does this scorecard exist?");
  await page.fill("textarea >> nth=0", "Smoke-test purpose");
  await page.fill("textarea >> nth=2", "Smoke-test objective");
  await page.click("text=2. Parameters & rating matrix");
  await page.click("text=+ Level-1 KPI");
  await page.click("text=One row per band");
  const areas = page.locator("textarea[placeholder='What does this score look like?']");
  for (let i = 0; i < (await areas.count()); i++) await areas.nth(i).fill(`Level ${i}`);
  await page.click("text=Save draft");
  await page.waitForSelector("text=Draft saved");
  await page.click("button:has-text('Publish')");
  await page.waitForSelector("text=is published and frozen", { timeout: 5000 });
});

await step("evaluate and complete with the pilot scorecard", async () => {
  await page.goto(BASE + "/");
  await page.locator(".card", { hasText: "Assessment Quality" }).locator("a:has-text('Evaluate')").click();
  await page.fill("input[placeholder='What is being evaluated?']", "Smoke quiz");
  await page.click("text=Start evaluation");
  await page.waitForSelector("text=Complete evaluation");
  const leaves = page.locator(".leaf");
  for (let i = 0; i < (await leaves.count()); i++) {
    await leaves.nth(i).locator(".score-btn", { hasText: /^9$/ }).first().click();
    await page.waitForTimeout(150);
  }
  await page.click("text=Complete evaluation");
  await page.waitForSelector("text=✓ Meets target", { timeout: 5000 });
});

await step("import a messy legacy workbook", async () => {
  await page.goto(BASE + "/import");
  await page.setInputFiles("input[type=file]", path.join(ROOT, "data/legacy/training-session-quality.xlsx"));
  await page.click("button:has-text('Preview')");
  await page.waitForSelector("text=Row-by-row outcome");
  await page.getByText("[M04] Conflicting scores").first().waitFor();
  await page.click("button:has-text('Commit import')");
  await page.waitForSelector("text=Open scorecard", { timeout: 10000 });
  await snap("import");
});

await step("analytics renders", async () => {
  await page.goto(BASE + "/analytics");
  await page.waitForSelector("text=Honest RAG distribution");
  await snap("analytics");
});

await step("no browser errors", async () => {
  if (errors.length) throw new Error(errors.join(" | "));
});

await browser.close();
for (const r of results) console.log(r.join("  "));
process.exit(results.some((r) => r[0] === "FAIL") ? 1 : 0);
