# Page speed

Read this when the owner asks for speed, Lighthouse, PageSpeed or Core Web Vitals, or when a change adds weight to a page. The loop is measure, find the cause in the code, fix, and measure again. A score is a symptom: the fix is always in a file.

## Measure

- Measure the production build. A dev server ships unminified code and extra tooling, so its numbers mean nothing.
- Measure the phone first. Lighthouse scores mobile with a slow CPU and network, so a page that passes there usually passes on desktop.
- Run Lighthouse three times for each state and keep the median. The score moves between runs, and most of that movement does not come from Lighthouse ([performance scoring](https://developer.chrome.com/docs/lighthouse/performance/performance-scoring)).
- A local site is measured with Lighthouse on the machine. The PageSpeed Insights API sends the URL to Google, so ask the owner before sending an internal or private URL.
- `python scripts/speed_report.py summary RUN1.json RUN2.json RUN3.json` reads the JSON reports and prints the medians, the failing audits by estimated saving and the largest contentful paint element. `compare --before ... --after ...` puts two states side by side.
- Lighthouse is lab data. Real users at the 75th percentile decide Core Web Vitals when that data exists (see `quality-and-delivery.md`).

```bash
npx lighthouse http://localhost:4321/ --output=json --output-path=run1.json --form-factor=mobile
```

## Find the cause

Write a table: failing audit, the file that causes it, the fix and its risk. Fix in the order the score weighs the metrics. In Lighthouse 10 they are Total Blocking Time (TBT) 30 %, Largest Contentful Paint (LCP) 25 %, Cumulative Layout Shift (CLS) 25 %, First Contentful Paint (FCP) 10 % and Speed Index 10 %.

## Fix

Largest Contentful Paint has four parts: time to first byte, resource load delay, resource load duration and element render delay ([optimize LCP](https://web.dev/articles/optimize-lcp)). Find which part is long before you change anything.

- Never lazy-load the LCP image. Give it `fetchpriority="high"`, use an `<img>` instead of a CSS background so the browser finds it early, and preload it when it is not in the HTML.
- Serve AVIF or WebP at the size it is shown, with `srcset`, `sizes`, `width` and `height`.
- Fonts: `font-display`, the main font preloaded, a subset, few weights, a fallback with similar metrics.
- Cut render-blocking CSS and JavaScript: `defer` scripts, load CSS that is not critical without blocking, remove unused CSS.

Total Blocking Time comes from long tasks on the main thread.

- Ship less JavaScript: split it per route or per interaction, drop heavy dependencies, prefer static HTML or islands over hydrating a whole page.
- Load third-party scripts after the page, on interaction, or behind a facade (a video or a map that loads when clicked). Removing one is the owner's decision.
- Split any task over 50 ms.

Cumulative Layout Shift comes from content that moves after it appears.

- Every image, video and iframe has `width` and `height` or `aspect-ratio`.
- Reserve the space of banners, embeds and notices. Never insert content above what the reader already sees.
- Animate only `transform` and `opacity`.

## Rules

- One group of related changes per iteration, so each one can be reverted, and the project's tests after each.
- Never game the score: no other page for the Lighthouse user agent, no content hidden to move the LCP.
- Never remove analytics, chat or other features without the owner. Propose a later load first.
- A change outside the repository, such as a content delivery network (CDN), compression or server headers, goes in the report as a recommendation.
- Never add a dependency to make a page faster.

## Report

A table before and after for the phone and the desktop: the four category scores and FCP, LCP, TBT, CLS and Speed Index, each the median of its runs, with the device, the network and the Lighthouse version. Then the changes by file, and the audits that still fail with their cause and who can fix them. A difference smaller than the spread between runs is not an improvement.

This method follows the [pagespeed-optimizer](https://github.com/tuthuongvo/pagespeed-optimizer-skills) skill, written here from the Lighthouse and web.dev sources because that skill publishes no license.
