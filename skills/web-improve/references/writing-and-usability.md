# Writing and usability

Whether a page helps its reader is a fact about people, not about the page. This file has the checks a program can run, the heuristics a reviewer applies, and the test with real readers that settles it.

## 1. What a program measures

`python <standard>/scripts/text_check.py check <files or folder>` reads Markdown, HTML and the prose inside JSON content, and reports:

| Measure | Rule | Source |
| --- | --- | --- |
| Readability score | Spanish: Szigriszt-Pazos with the INFLESZ scale, 55 or more for a general audience. English: Flesch reading ease, 50 or more | Barrio-Cantalejo and colleagues (2008), Flesch (1948) |
| Long sentences | Not more than one sentence in five over 25 words | GOV.UK content design |
| Long paragraphs | Not over 120 words | ISO 24495-1 |
| Headings | A text over 400 words has headings to scan by | ISO 24495-1 |
| Acronyms | Expanded at first use | WCAG 2.2, Abbreviations |
| Link text | Says where it leads, never only "aquí" or "click here" | WCAG 2.2, Link Purpose |
| Passive voice | Under one sentence in four. A pattern match, so read the examples | ISO 24495-1 |

These are proxies. A precise technical text can score low and help its expert reader. A short, easy text can still leave out the one thing the reader needed. Use `--audience expert` for material written for specialists, and always read the examples before changing a sentence.

## 2. What a reviewer checks

Nielsen's ten usability heuristics, applied to the task the page is for:

1. The page shows what is happening: loading, saved, progress.
2. It speaks the reader's words, not the system's.
3. The reader can undo and leave.
4. It is consistent with itself and with the platform.
5. It prevents errors before it explains them.
6. Options are visible, so the reader recognizes rather than remembers.
7. Shortcuts exist for frequent readers without hiding the path for new ones.
8. Nothing on screen competes with the main task without a reason.
9. An error says what went wrong and how to fix it, in plain words.
10. Help is where the reader needs it.

Write each finding with the heuristic, the place and what the reader would do there.

## 3. What readers show

The only evidence that a page helps is readers of its audience using it. Five readers find most problems a round can find, and a round after each change finds the rest (Nielsen 2000).

1. `python <standard>/scripts/text_check.py protocol <page> --task "<what the reader came to do>"` writes a card in `docs/evidence/comprehension/`.
2. Write two to five questions whose answer is on the page, with the answer that counts as right.
3. With each reader, one at a time: show the page for five seconds and ask what it is for. Then give the task, say nothing, and note where they hesitate. Then ask the questions without the page.
4. Write what happened, never a name. Change the page, then run a new round.
5. `python <standard>/scripts/text_check.py evidence` reports each page as not run, too few readers or tested, with the completion and right answer rates.

A page counts as tested when five readers finished the last round. Report the rates as they are, with the number of readers.

## Sources

- ISO 24495-1:2023, Plain language, governing principles and guidelines: https://www.iso.org/standard/78907.html
- GOV.UK, Writing for GOV.UK: https://www.gov.uk/guidance/content-design/writing-for-gov-uk
- Flesch (1948), A new readability yardstick: https://doi.org/10.1037/h0057532
- Barrio-Cantalejo and colleagues (2008), Validación de la escala INFLESZ, Anales del Sistema Sanitario de Navarra 31(2):135-152
- WCAG 2.2, Understanding Link Purpose (In Context): https://www.w3.org/WAI/WCAG22/Understanding/link-purpose-in-context.html
- WCAG 2.2, Understanding Abbreviations: https://www.w3.org/WAI/WCAG22/Understanding/abbreviations.html
- Nielsen, 10 usability heuristics for user interface design: https://www.nngroup.com/articles/ten-usability-heuristics/
- Nielsen (2000), Why you only need to test with 5 users: https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/
