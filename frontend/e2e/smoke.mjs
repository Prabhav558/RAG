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
const PASSWORD = "Smoke-Password-1!";
const registered = new Set();

// Phase 2: every page needs a login. The first account ever registered on a fresh database becomes admin
// automatically, so `data/tools/ingest.py --reset`'s seed data (loaded
// through the service layer, with no HTTP users) means this suite's first registration is that admin.
async function actAs(username, displayName) {
  if (await page.locator("text=Log out").count()) await page.click("text=Log out");
  await page.waitForSelector(".login-card");
  const isNew = !registered.has(username);
  await page.click(isNew ? ".tabs >> text=Register" : ".tabs >> text=Log in");
  await page.fill(".login-card input[autocomplete='username']", username);
  if (isNew) await page.fill(".login-card input[autocomplete='name']", displayName);
  await page.fill(`.login-card input[autocomplete='${isNew ? "new-password" : "current-password"}']`, PASSWORD);
  await page.click(".login-card form button[type=submit]");
  await page.waitForSelector(".acting-as");
  registered.add(username);
}

await step("register the first user (auto-admin) and log in", async () => {
  await page.goto(BASE + "/");
  await actAs("smoke-admin", "Smoke Admin");
});

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

await step("quality gate end to end: create work, self-appraise, submit, judge, decide", async () => {
  await page.goto(BASE + "/work");
  await actAs("smoke-alice", "Alice");
  await page.click("text=+ New subject");
  await page.fill("label:has-text('Name') >> input", `Smoke project ${unique}`);
  await page.selectOption("label:has-text('Type') >> select", "project");
  await page.click("button:has-text('Create')");
  await page.getByText(`Smoke project ${unique}`).first().waitFor();
  await page.click("text=+ New subject");
  await page.fill("label:has-text('Name') >> input", `Smoke task ${unique}`);
  await page.selectOption("label:has-text('Under') >> select", { label: `Smoke project ${unique}` });
  await page.click("button:has-text('Create')");
  await page.click(`a:has-text('Smoke task ${unique}')`);
  await page.selectOption("label:has-text('Published scorecard') >> select", { label: "Client Email Quality (v1)" });
  await page.click("button:has-text('Start')");
  await page.waitForSelector("text=What happens next");
  await page.click("button:has-text('Self-appraise')");
  await page.waitForSelector("text=Complete evaluation");
  for (const btn of await page.locator(".leaf .score-btn", { hasText: /^8$/ }).all()) { await btn.click(); await page.waitForTimeout(150); }
  await page.click("text=Complete evaluation");
  await page.waitForSelector("text=✓ Meets target");
  await page.click("text=← Back to the submission");
  await page.click("button:has-text('Submit for judging')");
  await page.waitForSelector(".stepper .s.now:has-text('In review')");
  await actAs("smoke-bob", "Bob");
  await page.click("button:has-text('Judge as Bob')");
  await page.waitForSelector("text=Complete evaluation");
  for (const btn of await page.locator(".leaf .score-btn", { hasText: /^9$/ }).all()) { await btn.click(); await page.waitForTimeout(150); }
  await page.click("text=Complete evaluation");
  await page.waitForSelector("text=✓ Meets target");
  await page.click("text=← Back to the submission");
  await page.click("button:has-text('Decide')");
  await page.waitForSelector("text=✓ Passed the gate");
  await snap("submission-decided");
  await page.goto(BASE + "/work");
  const row = page.locator("tr", { hasText: `Smoke project ${unique}` });
  await row.locator(".chip.pass", { hasText: "Green" }).waitFor();
});

await step("ODTQRC task definition can be edited", async () => {
  // Note: this deliberately stops short of clicking "Check clarity" — that endpoint calls a real LLM and needs
  // GROQ_API_KEY, which CI does not set (the same reason this suite never calls the LLM judge either); a
  // 503 from that call would still log a browser console error and trip the "no browser errors" check below.
  await page.goto(BASE + "/work");
  await page.click(`a:has-text('Smoke task ${unique}')`);
  await page.click("button:has-text('Edit details')");
  await page.fill("label:has-text('Objective') >> textarea", "Ship a reviewed report by Friday");
  await page.fill("label:has-text('Deliverable') >> textarea", "report.pdf in the shared drive");
  await page.fill("label:has-text('Quality') >> textarea", "Passes the 5-point review checklist");
  await page.fill("label:has-text('Risk') >> textarea", "Reviewer may be on leave");
  await page.click("button:has-text('Save')");
  await page.waitForSelector("text=Ship a reviewed report by Friday");
});

await step("admin can manage users and roles", async () => {
  await page.goto(BASE + "/users");
  await page.waitForSelector("text=Users & roles");
  const row = page.locator("tr", { hasText: "Alice" });
  await row.waitFor();
  await row.locator("td input[type=checkbox]").first().click();
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
