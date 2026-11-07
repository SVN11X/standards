# Technology and hosting

## Pick the least complex option that meets the goal

| Situation | Default | When to choose something else |
|-----------|---------|-------------------------------|
| The site works with HTML, CSS and JavaScript | Improve it with modern CSS and modular JavaScript | Change framework only when complexity justifies it |
| New informational site that needs SEO | Static site generator (for example Astro) with TypeScript | Prerendered React or Next only for concrete needs |
| A few dynamic components | Islands or plain JavaScript | A full single-page app only for real app navigation |
| Static interactive app | React or similar with Vite, static build | Plan SEO for routes that are not prerendered |
| Complex scroll animation | GSAP with ScrollTrigger, loaded on demand | CSS scroll-driven animations when target browsers support them |
| Microinteractions | CSS, Motion for advanced coordination | Never two animation libraries for the same job |
| Useful interactive 3D | Three.js or React Three Fiber, loaded lazily with a 2D fallback | Nothing for decorative spinning icons |
| Character or diagram animation | SVG and CSS, or Rive | Justify the runtime and asset cost |
| Heavy local computation | Web Worker, WebAssembly after profiling | WebGPU only with proven support and a fallback |
| Icons and illustrations | Optimized SVG from one consistent set | Not a full icon pack for three icons |
| Images | AVIF or WebP with fallbacks, srcset and sizes | Balance compression against relevant detail |

## How to choose

1. List what is already installed. Do not add a second library for the same job.
2. Name the experience you want to improve and how you will measure it.
3. Compare the native option with the specialized dependency.
4. Estimate the cost: initial JavaScript, assets, maintenance, accessibility, compatibility.
5. Build a small trial, measure it, and remove it if it does not help.
6. Check the current stable versions at implementation time. Versions named in documents go stale.

## GitHub Pages limits

- Pages serves static files only. No Node, PHP or Python server and no private APIs hosted on Pages.
- Frameworks are fine when CI builds them into a static `dist` folder.
- A form that must send data securely needs an external backend provider or another host. Never embed private keys.
- A project site lives under `/repository-name/`. Set the build's base path accordingly. A `<owner>.github.io` site usually uses `/`. For a custom domain, confirm the final URL and keep the existing configuration, redirects and canonical tags.
- Single-page apps need a plan for direct links, 404 handling and SEO before deploying.
- GitHub Pages is not meant for SaaS, e-commerce transactions or sensitive data. If the site needs that, recommend another host.
- Keep the existing GitHub Actions workflow unless changing it helps. Use minimal permissions, a committed lockfile and a build check.

## Avoid over-engineering

- No several frameworks at once.
- No Tailwind migration when the existing CSS is solid and the migration means rebuilding styles for nothing.
- No Three.js for a rotating icon.
- No carousels, parallax and permanent animation in every section.
- Remove duplicated dependencies, conflicting global CSS and near-identical components.

## Official references

- What is GitHub Pages: https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages
- GitHub Pages limits: https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits
- Custom domains: https://docs.github.com/en/pages/configuring-a-custom-domain-for-your-github-pages-site
- Deploying Astro to GitHub Pages: https://docs.astro.build/en/guides/deploy/github/
