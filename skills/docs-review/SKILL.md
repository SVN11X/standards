---
name: docs-review
description: Review a document or a documentation repository, such as a thesis, report, paper, book, manual or documentation site, for purpose, structure, consistency, evidence, citations, figures and build, against the repository's own rules when it has them. Use this whenever the user asks to review, check, proofread, audit or critique a thesis, chapter, paper, report or docs, asks whether a document is ready to submit, or wants to find contradictions or redundancy between chapters, even if they only say "review this" or "revisa esto".
---

# docs-review

Review a document so its author can fix what matters most before submitting. Report problems with evidence and a concrete fix. Do not rewrite the document unless the author asks.

## Read first

- `AGENTS.md`, if the repository has one. For the docs profile it requires one chapter per file, a single bibliography, figures next to their sources, a one-command build and tags for submitted versions.
- `docs/goals.md`: audience, objectives and constraints of the document.
- The institution or publisher template and style guide, and the citation style.
- The whole document before judging any part, so findings about consistency are real.

## Passes

Run them in this order and keep the findings of each pass together.

1. Purpose. Does the document answer its question or meet its objectives? Do the objectives stated in the introduction match the results and the conclusions? Does every chapter serve them?
2. Structure and consistency. Chapter order, content repeated across chapters, terms used consistently with the glossary, numbering, and cross references that resolve.
3. Evidence and method. Every claim is supported by data or a citation. Methods can be reproduced: parameters, versions, conditions. Measured data, derived results and illustrative examples are labeled as such. Units, significant figures and statistics are reported correctly.
4. Citations. Every citation resolves to a bibliography entry and the style is applied consistently. Prefer primary sources. When you can check a reference exists, check it. Never invent or complete a reference from memory.
5. Figures and tables. Each one is referenced in the text before it appears, has a caption that explains it, is legible, has units, and keeps its source file next to the export.
6. Language. Written in the document's language, plain and precise, consistent in tense and person as the institution requires. Flag filler and AI-sounding prose. Use antislop-copywriting for this if it is installed.
7. Build. The document builds with its documented command without broken references or warnings, and submitted versions are tagged.

## Output

Findings only, ordered by severity:

- Blocker: an unsupported or wrong claim, a missing required section, a fabricated or unresolvable reference, a broken build.
- Should fix: inconsistency between chapters, missing method detail, figure or citation problems.
- Consider: clarity and style improvements.

Each finding gives the location (file and line, or section and page), what is wrong in one sentence, why it matters, and a concrete fix. For wording, show the original passage and a proposed version. Reply in the owner's language and quote the document in its own language.

## Deeper review

For a simulated journal peer review with several reviewer roles, use a dedicated academic review skill if one is installed, such as academic-paper-reviewer from the academic-research-skills project.
