// Checks the Autopilot view of Standards AI Control in a real browser against a real server and seeded state.
// Run: node tests/web/control.test.mjs   (needs Python, git and Playwright where Node can find it. verify.py skips it otherwise)
import assert from "node:assert/strict";
import { execFileSync, spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { createServer } from "node:net";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  console.log("SKIP: Playwright is not installed");
  process.exit(77);
}
const python = process.env.PYTHON || (process.platform === "win32" ? "python" : "python3");

const work = mkdtempSync(join(tmpdir(), "standards-control-"));
const home = join(work, "home");
const repo = join(work, "repo");
const id = "auto-" + "a".repeat(14);
const test = "python -m unittest discover -s tests";
mkdirSync(join(home, "plans"), { recursive: true });
mkdirSync(join(home, "executions"), { recursive: true });
mkdirSync(repo);
const git = (...args) => execFileSync("git", ["-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", ...args]);
git("init", "-q");
for (const name of ["a.py", "b.py", "c.py"]) writeFileSync(join(repo, name), "x = 1\n");
git("add", "-A");
git("commit", "-q", "-m", "init");
// An untracked file: a plan or a run started from the page stops at once with BLOCKED, before any model is asked.
writeFileSync(join(repo, "untracked.txt"), "x\n");
const unit = (n, file, deps, risk) => ({
  id: `u${n}`, title: `Edit ${file}`, task_type: "edit-small", goal: `Change ${file}`, allowed: [file], new_files: [],
  depends_on: deps, risk, acceptance: { test, criteria: ["Tests pass"] },
});
writeFileSync(join(home, "plans", `${id}.json`), JSON.stringify({
  plan_id: id, repo, base: "b".repeat(40), goal: "Add three small changes <script>alert(1)</script>",
  defaults: { risk: "green", test }, final_regression: [test],
  planner: { backend: "claude", model: "haiku", tier: "light", reasons: ["complexity light (score 0)"], repair_calls: 0, fixes: [] },
  units: [unit(1, "a.py", [], "green"), unit(2, "b.py", ["u1"], "red"), unit(3, "c.py", [], "green")],
}));
writeFileSync(join(home, "executions", `${id}.json`), JSON.stringify({
  plan_id: id,
  units: {
    u1: { status: "running", at: new Date(Date.now() - 42000).toISOString(), model: "opencode/free-a", executor: "opencode", channel: "remote_free" },
    u3: { status: "passed", at: new Date().toISOString(), model: "ollama/local-b", executor: "opencode", channel: "local", seconds: 12.5,
          review: { verdict: "pass" }, note: "review pass" },
  },
  metrics: { total_s: 31.2, parallel_limit: 3, peak_parallel: 2, waited_s: 0.4, integration_s: 0.2, collisions: 0, retries: 1 },
  publication: { pr: "https://github.com/example/repo/pull/7", ci: { state: "pending" }, auto_merge_requested: false },
}));
writeFileSync(join(home, "executions", `${id}.events.jsonl`),
  JSON.stringify({ at: "2026-01-01T00:00:00+00:00", event: "plan-started", unit: null }) + "\n");

const port = await new Promise((done) => {
  const probe = createServer();
  probe.listen(0, "127.0.0.1", () => { const { port } = probe.address(); probe.close(() => done(port)); });
});
const server = spawn(python, [join(root, "scripts", "control.py"), "serve", "--port", String(port), "--repo", repo],
  { env: { ...process.env, STANDARDS_HOME: home, PYTHONUTF8: "1" }, stdio: ["ignore", "pipe", "ignore"] });
// Whatever happens below, the server stops and the temp folder goes.
process.on("exit", () => { server.kill(); rmSync(work, { recursive: true, force: true }); });
process.on("uncaughtException", (error) => { console.log(`FAIL  ${error.message.split("\n")[0]}`); process.exit(1); });
await new Promise((done, fail) => {
  server.stdout.on("data", (chunk) => String(chunk).includes("Standards AI Control") && done());
  server.on("exit", (code) => fail(new Error(`the control server stopped with code ${code}`)));
  setTimeout(() => fail(new Error("the control server did not start in 30 s")), 30000);
});

const url = `http://127.0.0.1:${port}/`;
const control = () => JSON.parse(readFileSync(join(home, "executions", `${id}.control.json`), "utf8"));
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
const page = await context.newPage();
const errors = [];
page.on("console", (message) => message.type() === "error" && errors.push(message.text()));
page.on("pageerror", (error) => errors.push(error.message));
page.on("dialog", (dialog) => dialog.accept());
let failed = 0;
async function check(name, body) {
  try {
    await body();
    console.log(`pass  ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL  ${name}: ${error.message.split("\n")[0]}`);
  }
}
const planCard = (view) => view.locator(".card", { has: view.locator("h3", { hasText: id }) });
const card = planCard(page);
const row = (unit) => card.locator("tr", { has: page.locator("b", { hasText: new RegExp(`^${unit}$`) }) });

await page.goto(url + "#Autopilot");
await card.waitFor();

await check("a plan shows each unit with its state, model, provider and what it waits on", async () => {
  assert.match(await card.locator("h3").textContent(), /1 of 3 passed/);
  assert.match(await row("u1").textContent(), /running.*opencode\/free-a.*opencode.*remote_free/s);
  assert.match(await row("u1").textContent(), /4\d(\.\d)? s/, "the running unit shows the time since it started");
  assert.match(await row("u2").textContent(), /pending.*Not available.*waits on u1/s);
  assert.match(await row("u3").textContent(), /passed.*ollama\/local-b.*local.*12\.5 s.*pass/s);
  assert.match(await card.textContent(), /Planner haiku \(light, claude\)/);
  assert.match(await card.textContent(), /peak 2 of 3 at once.*conflicts 0.*retries 1/s);
});

await check("the active agents card lists only the unit that is running", async () => {
  const agents = page.locator(".card", { hasText: "Active agents" });
  assert.match(await agents.textContent(), /u1 Edit a\.py.*opencode\/free-a/s);
  assert.doesNotMatch(await agents.textContent(), /u3/);
});

await check("the pull request, its checks and what needs the owner are shown", async () => {
  assert.equal(await card.locator("a").getAttribute("href"), "https://github.com/example/repo/pull/7");
  assert.match(await card.textContent(), /checks pending.*auto-merge not requested/s);
  assert.match(await card.textContent(), /Needs the owner: u2 is red/);
});

await check("text from a plan is shown as text, never run as markup", async () => {
  assert.match(await card.textContent(), /<script>alert\(1\)<\/script>/);
  assert.equal(await page.locator("#view script").count(), 0);
});

await check("events are folded until the owner opens them", async () => {
  const events = card.locator("details");
  assert.equal(await events.evaluate((el) => el.open), false);
  await events.locator("summary").click();
  assert.match(await events.locator("pre").textContent(), /plan-started/);
  await events.locator("summary").click();
});

await check("pause and allow write the control file and the page follows", async () => {
  await card.getByRole("button", { name: "Pause new assignments" }).click();
  await card.getByRole("button", { name: "Allow new assignments" }).waitFor();
  assert.equal(control().paused, true);
  assert.match(await card.locator("h3").textContent(), /paused/);
  await card.getByRole("button", { name: "Allow new assignments" }).click();
  await card.getByRole("button", { name: "Pause new assignments" }).waitFor();
  assert.equal(control().paused, false);
});

await check("cancel names one unit of the plan and a finished unit has no cancel button", async () => {
  assert.equal(await row("u3").getByRole("button").count(), 0);
  await row("u2").getByRole("button", { name: "Cancel" }).click();
  await page.waitForFunction(() => true);
  await assert.doesNotReject(async () => {
    for (let n = 0; n < 50 && !(existsSync(join(home, "executions", `${id}.control.json`)) && (control().cancel || []).length); n += 1) {
      await page.waitForTimeout(100);
    }
  });
  assert.deepEqual(control().cancel, ["u2"]);
});

await check("a plan made in the page runs as a job whose exit code decides its state", async () => {
  await page.fill("#ap-text", "Add a comment to a.py");
  await page.selectOption("#ap-planner", "local");
  await page.click("#ap-plan");
  const jobs = page.locator(".card", { hasText: "plan ·" }).last();
  await jobs.locator("summary", { hasText: /plan · failed/ }).waitFor({ timeout: 30000 });
  await jobs.locator("summary").first().click();
  assert.match(await jobs.locator("pre").first().textContent(), /BLOCKED: Repository has changes/);
  assert.equal(await page.inputValue("#ap-text"), "Add a comment to a.py", "the draft survives the polls");
  await page.waitForTimeout(3000);
  assert.equal(await jobs.locator("details").first().evaluate((el) => el.open), true, "an opened log stays open across a poll");
});

await check("starting a paused plan runs the standards script in the repository of the plan", async () => {
  // The log opened above is still open: the page must go on following the state.
  await card.getByRole("button", { name: "Pause new assignments" }).click();
  await card.getByRole("button", { name: "Resume pending work" }).click();
  const jobs = page.locator(".card", { hasText: "run ·" }).last();
  await jobs.locator("summary", { hasText: /run · failed/ }).waitFor({ timeout: 30000 });
  await jobs.locator("summary", { hasText: /run · failed/ }).click();
  assert.match(await jobs.locator("details", { hasText: /run · failed/ }).locator("pre").textContent(), /BLOCKED: /);
  assert.equal(await card.getByRole("button", { name: /auto-merge/i }).count(), 0, "auto-merge is not offered in the page");
});

await check("every view renders without a script error", async () => {
  for (const view of ["Dashboard", "Autopilot", "Agents and models", "Tasks", "Operations", "Performance", "History", "Settings", "Logs"]) {
    await page.goto(url + "#" + encodeURIComponent(view));
    await page.waitForFunction(() => document.querySelector("#view").textContent.trim() !== "Loading");
    assert.notEqual((await page.textContent("#view")).trim(), "", view);
  }
  assert.deepEqual(errors, []);
});

await check("a request without the page token is refused", async () => {
  const status = await page.evaluate(async (plan) => (await fetch("/api/autopilot/pause", {
    method: "POST", headers: { "Content-Type": "application/json", "X-Standards-Token": "wrong" }, body: JSON.stringify({ plan_id: plan }),
  })).status, id);
  assert.equal(status, 403);
});

await check("the plan card fits a 360 px screen without sideways scroll of the page", async () => {
  await page.setViewportSize({ width: 360, height: 800 });
  await page.goto(url + "#Autopilot");
  await card.waitFor();
  const [scroll, width] = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
  assert.ok(scroll <= width + 1, `the page is ${scroll} px wide in a ${width} px window`);
});

if (process.env.CONTROL_SCREENSHOT) {
  const shot = await browser.newContext({ viewport: { width: 1280, height: 900 }, deviceScaleFactor: 2 });
  const view = await shot.newPage();
  await view.goto(url + "#Autopilot");
  await planCard(view).waitFor();
  await view.screenshot({ path: process.env.CONTROL_SCREENSHOT, fullPage: true });
  await shot.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
