# Quality checks and delivery

## Fit the work to the environment

| Access | Procedure |
|--------|-----------|
| Repository with git | Record base commit and branch, protect other people's changes, work on a branch or an isolated copy. |
| ZIP or attached files | Identify the structure and edit the available files. Recover a real base if a patch is required. |
| URL only | Try to get the files with the tools you have. Ask for the repository or files if you cannot read them. |
| Test browser | Run actions and observe states, errors and rendering. |
| No browser | Finish code, path, model and asset checks. Say that the visual check in a browser is still pending. |

A skill gives instructions. It does not grant git, a browser, write access to GitHub or publishing. Use tools only if the session has them.

## Checks

- JavaScript syntax and load errors, repeated IDs, references to missing elements, linked files.
- Relative links and paths under the repository base path, including SVG, fonts, video and modules.
- Every control: initial state, minimum and maximum, visible update, combinations, selection and reset.
- Model properties that can reveal errors: conservation, limits, composition and inverse of transformations, occluded cells, units, timing.
- Figures without clipped or overlapping labels, readable fallback content.
- Mobile and desktop, keyboard, touch, reduced motion, dark mode if the site has it.
- The repository's own checks. If indexed content changes, regenerate the index and check the sections outside the scope.

## Checklist before delivering

- [ ] Visual direction consistent with `DESIGN.md` and the brand
- [ ] Short, clear headings without repetition
- [ ] Calls to action work
- [ ] Motion is discreet and respects reduced motion
- [ ] Keyboard navigation and visible focus
- [ ] Semantics, labels, alt text, contrast, touch target sizes
- [ ] Responsive images with explicit sizes and careful lazy loading
- [ ] No credentials, secrets or sensitive data added
- [ ] No duplicated dependencies, dead code or new warnings
- [ ] Paths and links correct under the GitHub Pages base path
- [ ] The build ran, or is explicitly marked as not run
- [ ] SEO basics: titles, descriptions, canonical, robots, sitemap, Open Graph where they apply
- [ ] Forms and behaviors tested, failures handled

## Metrics

- Core Web Vitals at the 75th percentile of real users when data exists: LCP up to 2.5 s, INP up to 200 ms, CLS up to 0.1.
- Lab measurements use a stated device and network so before and after can be compared. Lighthouse is not real-user data.
- Aim for 95 or more in Lighthouse categories when realistic. Never report a score that was not measured, and never claim WCAG AA from Lighthouse alone.
- When adding 3D or heavy animation, compare JavaScript size, CPU, LCP and interaction cost to justify it.
- Every "faster" or "better" claim needs a comparison. Without data, call it an improvement hypothesis.

## Patch for git am

1. Identify the base commit that contains the files before the changes.
2. Commit every authorized file, including SVG and binaries, on top of that base. Keep other people's work and use an assistant identity as author when appropriate.
3. Keep the delivery to those commits. Use a branch or an isolated copy when the history has unrelated work.
4. Export with `git format-patch --full-index --binary --stdout BASE..FINAL`. A linear series can go in one `.patch` file.
5. Apply it with `git am` on a clean copy of BASE and compare the resulting tree with FINAL, including binaries and permissions.
6. Package every versioned file of FINAL in the full ZIP, keeping the structure. The ZIP is a snapshot without git history.

`scripts/deliver_git.py` automates steps 4 to 6. It needs Python 3 and git, a clean working tree, a reachable base, linear commits and no submodules. It works locally, never changes the original repository, installs nothing and never writes to the remote.

```bash
python scripts/deliver_git.py --help
python scripts/deliver_git.py --repo /path/to/project --base BASE_COMMIT --output /path/to/delivery --name project
```

Without the base, deliver the verifiable work and explain what is missing to build the patch. Never fabricate a base or promise that a patch applies to any version.

## Final message

At most twelve lines unless the owner asks for more:

- Result: what changed and why.
- Changes: main files and blocks.
- Verification: commands and scenarios that really ran, with results, or "not verified".
- Pending: relevant risks and the next step.
- Delivery: links to the ZIP and the verified patch, the base commit, and the command `git am <file>.patch`.
