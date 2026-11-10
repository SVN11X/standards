// Checks the pattern gallery of web-improve in a real browser: keyboard, touch, language, states and reduced motion.
// Run: node tests/web/gallery.test.mjs   (needs Playwright where Node can find it. verify.py skips it otherwise)
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const file = resolve(root, "skills/web-improve/gallery/index.html");
const measure = resolve(root, "skills/web-improve/scripts/measure_page.mjs");
let chromium;
try {
  ({ chromium } = createRequire(import.meta.url)("playwright"));
} catch {
  console.log("SKIP: Playwright is not installed");
  process.exit(77);
}

const browser = await chromium.launch();
let failed = 0;
async function check(name, options, body) {
  const context = await browser.newContext({ viewport: { width: 360, height: 800 }, ...options });
  const page = await context.newPage();
  await page.goto(pathToFileURL(file).href);
  try {
    await body(page);
    console.log(`pass  ${name}`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL  ${name}: ${error.message.split("\n")[0]}`);
  } finally {
    await context.close();
  }
}
const settle = (page) => page.evaluate(() => Promise.all(document.getAnimations().map((a) => a.finished.catch(() => null))));
const checked = (page) => page.$eval('#modes [aria-checked="true"]', (el) => el.dataset.mode);
async function indicatorMatches(page) {
  await settle(page);
  const [indicator, option] = await page.evaluate(() => {
    const box = (el) => { const b = el.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.width)]; };
    return [box(document.querySelector("#modes .indicator")), box(document.querySelector('#modes [aria-checked="true"]'))];
  });
  assert.deepEqual(indicator, option, "the indicator has the position and the width of the selected option");
  return option[1];
}

await check("segmented control: click, then a language change keeps the choice and resizes the indicator", {}, async (page) => {
  await page.click('[data-mode="practice"]');
  assert.equal(await checked(page), "practice");
  const english = await indicatorMatches(page);
  await page.click('[data-lang="es"]');
  assert.equal(await checked(page), "practice");
  assert.equal(await page.textContent('[data-mode="practice"]'), "Practicar");
  assert.equal(await page.getAttribute("html", "lang"), "es");
  const spanish = await indicatorMatches(page);
  assert.notEqual(english, spanish, "the widths differ between languages, so the indicator was measured again");
});

await check("segmented control: keyboard with one tab stop", {}, async (page) => {
  await page.focus('[data-mode="study"]');
  await page.keyboard.press("ArrowRight");
  assert.equal(await checked(page), "practice");
  assert.equal(await page.evaluate(() => document.activeElement.dataset.mode), "practice");
  await page.keyboard.press("End");
  assert.equal(await checked(page), "review");
  await page.keyboard.press("ArrowRight");
  assert.equal(await checked(page), "study");
  assert.equal(await page.$$eval('#modes [tabindex="0"]', (els) => els.length), 1);
  await indicatorMatches(page);
});

await check("segmented control: touch", { hasTouch: true, isMobile: true }, async (page) => {
  await page.tap('[data-mode="review"]');
  assert.equal(await checked(page), "review");
  await indicatorMatches(page);
});

await check("depth button: the area that reacts stays in place while pressed", {}, async (page) => {
  const area = () => page.$eval(".press-area", (el) => { const b = el.getBoundingClientRect(); return [b.left, b.top, b.width, b.height]; });
  const before = await area();
  await page.hover("#depth");
  await page.mouse.down();
  await settle(page);
  assert.deepEqual(await area(), before);
  await page.mouse.up();
  assert.match(await page.textContent("#depth-count"), /1$/);
});

await check("action button: the result appears only after the operation, and an error offers a retry", {}, async (page) => {
  await page.click("#save");
  assert.equal(await page.getAttribute("#save", "data-state"), "running");
  assert.equal(await page.isDisabled("#save"), true);
  assert.equal(await page.textContent("#save-status"), "");
  await page.waitForSelector('#save[data-state="success"]');
  assert.equal(await page.textContent("#save"), "Saved");
  await page.check("#fail");
  await page.click("#save");
  await page.waitForSelector('#save[data-state="error"]');
  assert.equal(await page.textContent("#save"), "Try again");
  assert.match(await page.textContent("#save-status"), /could not be saved/);
  assert.equal(await page.isDisabled("#save"), false);
  await page.click("#save");
  await page.waitForSelector('#save[data-state="success"]');
});

await check("expanding content opens with the keyboard", {}, async (page) => {
  await page.focus("#more summary");
  await page.keyboard.press("Enter");
  assert.equal(await page.$eval("#more", (el) => el.open), true);
});

await check("progress signal follows real steps and resets", {}, async (page) => {
  for (let i = 0; i < 3; i += 1) await page.click("#step");
  assert.equal(await page.textContent("#progress-text"), "All 3 steps done.");
  assert.equal(await page.isDisabled("#step"), true);
  await page.click("#reset");
  assert.match(await page.textContent("#progress-text"), /^0 of 3/);
});

const moveOverStage = async (page) => {
  await page.locator("#stage").scrollIntoViewIfNeeded();
  const box = await page.locator("#stage").boundingBox();
  for (const [dx, dy] of [[0.5, 0.5], [0.9, 0.2], [0.1, 0.8], [0.8, 0.9]]) {
    await page.mouse.move(box.x + box.width * dx, box.y + box.height * dy, { steps: 4 });
    await page.waitForTimeout(60);
  }
};
const orbAt = (page) => page.$eval("#orb", (el) => [Number(el.dataset.x), Number(el.dataset.y), el.style.transform]);

await check("reactive object: it follows the pointer when motion is allowed", {}, async (page) => {
  await moveOverStage(page);
  const [x, y] = await orbAt(page);
  assert.ok(Math.abs(x) + Math.abs(y) > 1, "the engine moves the object");
});

await check("reactive object: with reduced motion and no task it stays still while the pointer moves", { reducedMotion: "reduce" }, async (page) => {
  await moveOverStage(page);
  assert.deepEqual(await orbAt(page), [0, 0, "translate(0px, 0px)"]);
  await page.click("#listen");
  await moveOverStage(page);
  const [x, y] = await orbAt(page);
  assert.ok(Math.abs(x) + Math.abs(y) > 1, "it moves while the task the visitor started runs");
  await page.click("#listen");
  await page.waitForTimeout(100);
  await moveOverStage(page);
  assert.deepEqual((await orbAt(page)).slice(0, 2), [0, 0]);
});

await check("reduced motion reaches the style sheet too", { reducedMotion: "reduce" }, async (page) => {
  const seconds = await page.$eval("#modes .indicator", (el) => Math.max(...getComputedStyle(el).transitionDuration.split(",").map(parseFloat)));
  assert.ok(seconds < 0.001, `transition lasts ${seconds}s`);
  await page.click('[data-mode="review"]');
  await indicatorMatches(page);
});

await check("no horizontal scroll at 320 px in both languages", { viewport: { width: 320, height: 700 } }, async (page) => {
  const overflow = () => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  assert.ok((await overflow()) <= 0);
  await page.click('[data-lang="es"]');
  assert.ok((await overflow()) <= 0);
});

await browser.close();

for (const scheme of ["light", "dark"]) {
  try {
    const report = JSON.parse(execFileSync(process.execPath, [measure, file, "--scheme", scheme], { encoding: "utf8" }));
    assert.equal(report.findings, 0, JSON.stringify(report.viewports.flatMap((v) => v.findings)));
    console.log(`pass  measured at 360 and 1280 px in ${scheme}: contrast, touch targets, line length, overflow, fonts`);
  } catch (error) {
    failed += 1;
    console.log(`FAIL  measured in ${scheme}: ${error.message.split("\n")[0]}`);
  }
}
process.exit(failed ? 1 : 0);
