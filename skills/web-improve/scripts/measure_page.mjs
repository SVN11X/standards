#!/usr/bin/env node
// Layer 1 of the design judgment: open a page in a real browser and measure it. No AI and no network beyond the page.
// Usage: node measure_page.mjs <url-or-html-file> [--strict] [--widths 360,1280] [--scheme light|dark]
// Prints JSON. Every finding has the check, the element, the measured value and the limit. --strict exits 1 on any finding.
// Needs Playwright where Node can find it: the project's own node_modules, or a global install.
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const args = process.argv.slice(2);
const valueOf = (flag) => (args.includes(flag) ? args[args.indexOf(flag) + 1] : null);
const taken = ["--widths", "--scheme"].filter((flag) => args.includes(flag)).map((flag) => args.indexOf(flag) + 1);
const target = args.find((arg, index) => !arg.startsWith("--") && !taken.includes(index));
if (!target) {
  console.error("Usage: node measure_page.mjs <url-or-html-file> [--strict] [--widths 360,1280] [--scheme light|dark]");
  process.exit(2);
}
const widths = (valueOf("--widths") || "360,1280").split(",").map(Number);
const scheme = valueOf("--scheme") === "dark" ? "dark" : "light";
const url = existsSync(target) ? pathToFileURL(resolve(target)).href : target;

let chromium;
try {
  ({ chromium } = createRequire(resolve(process.cwd(), "package.json"))("playwright"));
} catch {
  try {
    ({ chromium } = createRequire(import.meta.url)("playwright"));
  } catch {
    console.error("Playwright is not installed here. Add it to the project (npm install -D playwright) and run again.");
    process.exit(3);
  }
}

// Runs inside the page.
function measure() {
  const findings = [];
  const name = (el) => {
    const id = el.id ? `#${el.id}` : "";
    const cls = typeof el.className === "string" && el.className ? `.${el.className.trim().split(/\s+/)[0]}` : "";
    const text = (el.textContent || "").trim().replace(/\s+/g, " ").slice(0, 30);
    return `${el.tagName.toLowerCase()}${id}${cls}${text ? ` "${text}"` : ""}`;
  };
  const add = (check, el, value, limit) => findings.push({ check, layer: "measured", element: el ? name(el) : "page", value, limit });
  const visible = (el) => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return box.width > 0 && box.height > 0 && style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0;
  };

  const overflow = document.documentElement.scrollWidth - window.innerWidth;
  if (overflow > 0) add("horizontal-scroll", null, `${overflow}px wider than the screen`, "0px");

  for (const el of document.querySelectorAll('a[href], button, input, select, textarea, summary, [role="button"], [role="radio"], [role="tab"], [role="link"]')) {
    if (!visible(el) || el.disabled || el.type === "hidden") continue;
    if (el.tagName === "A" && el.closest("p, li")) continue;
    const hit = el.closest("label") || el;
    const box = hit.getBoundingClientRect();
    if (box.width < 24 || box.height < 24) add("touch-target", el, `${Math.round(box.width)}x${Math.round(box.height)}px`, "24x24px");
  }

  const parse = (color) => {
    const match = /^rgba?\(([^)]+)\)$/.exec(color);
    if (!match) return null;
    const parts = match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
    return { r: parts[0], g: parts[1], b: parts[2], a: parts.length > 3 ? parts[3] : 1 };
  };
  const luminance = ({ r, g, b }) => {
    const channel = (v) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
  };
  const families = new Set();
  let unmeasured = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const seen = new Set();
  while (walker.nextNode()) {
    const el = walker.currentNode.parentElement;
    if (!el || seen.has(el) || !walker.currentNode.textContent.trim() || !visible(el) || ["SCRIPT", "STYLE"].includes(el.tagName)) continue;
    seen.add(el);
    const style = getComputedStyle(el);
    families.add(style.fontFamily.split(",")[0].trim().replace(/["']/g, ""));
    const text = parse(style.color);
    const box = el.getBoundingClientRect();
    const x = Math.min(window.innerWidth - 1, Math.max(0, box.left + box.width / 2));
    const y = box.top + box.height / 2;
    if (!text || y < 0 || y > window.innerHeight) { unmeasured += !text; continue; }
    let background = null;
    let image = false;
    for (const under of document.elementsFromPoint(x, y)) {
      const below = getComputedStyle(under);
      if (below.backgroundImage !== "none") { image = true; break; }
      const color = parse(below.backgroundColor);
      if (color === null && below.backgroundColor !== "rgba(0, 0, 0, 0)") { image = true; break; }
      if (color && color.a === 1) { background = color; break; }
      if (color && color.a > 0) { image = true; break; }
    }
    if (image) { unmeasured += 1; continue; }
    background = background || { r: 255, g: 255, b: 255 };
    const [light, dark] = [luminance(text), luminance(background)].sort((a, b) => b - a);
    const ratio = (light + 0.05) / (dark + 0.05);
    const size = parseFloat(style.fontSize);
    const large = size >= 24 || (size >= 18.66 && Number(style.fontWeight) >= 700);
    const limit = large ? 3 : 4.5;
    if (ratio < limit) add("contrast", el, `${ratio.toFixed(2)}:1`, `${limit}:1`);
  }
  if (families.size > 2) add("font-families", null, [...families].join(", "), "2 families");

  for (const el of document.querySelectorAll("p, li")) {
    if (!visible(el)) continue;
    const style = getComputedStyle(el);
    const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.2;
    const lines = Math.max(1, Math.round(el.getBoundingClientRect().height / lineHeight));
    const perLine = Math.round(el.textContent.trim().length / lines);
    if (lines > 1 && perLine > 80) add("line-length", el, `${perLine} characters per line`, "80");
  }
  for (const el of document.querySelectorAll("body *")) {
    const style = getComputedStyle(el);
    if (!el.children.length && el.textContent.trim() && visible(el) && ["hidden", "clip"].includes(style.overflowX) && el.scrollWidth > el.clientWidth + 1) {
      add("clipped-text", el, `${el.scrollWidth - el.clientWidth}px cut off`, "0px");
    }
  }
  return { findings, unmeasured_contrast: unmeasured, font_families: [...families] };
}

const browser = await chromium.launch();
const report = { url, scheme, viewports: [] };
try {
  for (const width of widths) {
    const page = await browser.newPage({ viewport: { width, height: 800 }, colorScheme: scheme });
    await page.goto(url, { waitUntil: "load" });
    // Measure the settled page: wait for fonts and for the entry transitions, two seconds at most.
    await page.evaluate(() => Promise.race([
      Promise.all([document.fonts ? document.fonts.ready : null, ...document.getAnimations().map((a) => a.finished.catch(() => null))]),
      new Promise((done) => setTimeout(done, 2000)),
    ]));
    report.viewports.push({ width, ...(await page.evaluate(measure)) });
    await page.close();
  }
} finally {
  await browser.close();
}
report.findings = report.viewports.reduce((sum, viewport) => sum + viewport.findings.length, 0);
console.log(JSON.stringify(report, null, 2));
process.exit(args.includes("--strict") && report.findings ? 1 : 0);
