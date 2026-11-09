# Regression tests for websites

Playwright Test is the evidence that stays in the repository. Playwright MCP and manual browsing help to explore a bug, but they do not replace a test anyone can run again.

## What to cover

- Every main route at 360, 768 and 1280 px, in light and dark theme.
- No horizontal overflow: `document.documentElement.scrollWidth <= window.innerWidth`.
- Keyboard: every control is reachable with Tab and has a visible focus.
- States: loading, empty, error and success for every view that loads data.
- Content counts: the number of questions, images or items the page shows equals the number in the data files, so a change never hides content silently.
- Saved state: preferences and progress survive a reload, and a corrupt saved value falls back to the default.
- Visual snapshots only for stable views, with a tolerance, kept per browser.

## Minimal setup

```js
// tests/web/smoke.spec.js
import { test, expect } from "@playwright/test";

for (const width of [360, 768, 1280]) {
  for (const scheme of ["light", "dark"]) {
    test(`home at ${width}px in ${scheme}`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: "reduce" });
      await page.setViewportSize({ width, height: 800 });
      await page.goto("/");
      await expect(page.locator("main")).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      expect(overflow).toBeLessThanOrEqual(0);
    });
  }
}
```

Pin `@playwright/test` to an exact version in `package.json`, add `"test": "playwright test"`, and serve the site with `webServer` in `playwright.config.js`. `verify.py` runs `npm test` when the script exists, and the adversarial suite runs `npx playwright test` at the deep level when a Playwright config exists.
