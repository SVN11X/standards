# 012. Learning, visual assets and writing

Three checks for what a page is for. Does it teach? Do its images and clips reach every reader, with their credit? Does its text help the reader do the task? Each check has a program for what can be measured. It also has a method for what only people can show. The router of `docs/011-request-router.md` sends a request to them.

## Learning

`scripts/learning_check.py` reads the question banks of a repository, whatever their field names, and reports two kinds of findings.

- Integrity errors set the exit code. They are an item with no key, a key that names no option, a repeated id, or two equal options.
- Learning findings name their rule and the study behind it. They cover missing explanations and wrong options without their own reason. They cover a key in one position far more often than chance (chi-square at p < 0.01), and a key that is clearly the longest option. They also cover "all of the above", negative questions without emphasis and repeated questions. Last come items without a topic or a source, and topics with fewer than five items.

It reads the code of the repository first. Some pages shuffle the options before showing them. There, a skewed key position in the data is only a note, because the learner never sees it.

`skills/web-improve/references/learning-science.md` turns the research into checks for a study site. It covers retrieval practice, spacing, interleaving and feedback that explains. It also covers worked examples, words next to diagrams and asking how sure the learner is. A site helps learning when learners recall more later. So the card says what to measure before claiming it.

### Run on the owner's question banks

On 2026-11-16, on shallow clones of three public repositories of the owner. Each run took under 0.13 s.

| Repository | Items | Errors | Main findings |
| --- | --- | --- | --- |
| test_dk_data_analyst | 731 | 1 item with two equal options | Key is B in 34% of the 418 five-option items where 20% is expected, and the page does not shuffle them. Key is the clearly longest option in 37%. No wrong option is explained. 9 "all of the above", 5 negative questions, 6 questions twice, 94 of 122 topics with fewer than five items |
| GCP_Data_Engineer_Fieldnotes, authored | 137 | none | Key is the clearly longest option in 39% of 120 four-option items where 25% is chance. 5 short explanations |
| GCP_Data_Engineer_Fieldnotes, imported | 349 | 2 items with two equal options | 306 items explain nothing and no wrong option is explained, which matches their status of unreviewed third party questions |
| nexocert | 216 | none | 35 short explanations. The key position is skewed in the data, but `src/components/Question.tsx` shuffles the options, so it is a note |

The first run reported three false findings, and each is now a test. Code options that differ only by a quote or an asterisk counted as equal. A scenario that "does not" do something counted as a negative question. A skewed key position was reported where the page shuffles the options.

## Visual assets

`scripts/media.py` has three commands.

- `search` asks Openverse and Wikimedia Commons. Both return the license and the author of every file. It keeps only licenses that allow commercial use and changes: CC0, public domain, CC BY and CC BY-SA. The owner can pass `--allow nc` or `--allow nd` for more. The search words leave the machine. So the router never offers it in `local-only` mode or for a `work` or `restricted` folder.
- `attach` saves one result in the repository and writes its credit to `assets/CREDITS.json`. It refuses an image with no alt text, unless `--decorative` says it adds nothing. It also refuses a license the owner did not allow, a licensed image with no author and a path outside the repository. It prints the `img` markup with width and height.
- `audit` reads HTML, Markdown and component files. It lists images without alt text, with a vague alt such as "imagen", or without width and height. It lists heavy files and SVG with scripts. It lists video without captions or poster, and video that plays sound on its own. It also lists media that no credit covers. A credit counts from `assets/CREDITS.json`, from a credits page that names the file or its folder, or from a REUSE annotation.

The router has five visual capabilities:

| Capability | Providers |
| --- | --- |
| Diagrams | Mermaid CLI, Pele, D2, Graphviz, draw.io, Excalidraw, anatomy, Archify, SVG by hand |
| New images | SVG by hand, charts with Matplotlib, Manim stills, Imagegen Skills, Perchance by hand |
| Existing images | the search of `media.py` |
| Attaching | `media.py`, sharp, Pillow |
| Short clips | HyperFrames, Manim, Motion Canvas, Remotion, OpenCut, explainroo in a project that has one |
| Narrated videos | explainroo, with a voice made on this machine |
| Media checks | ffprobe, Tesseract, the audit of `media.py` |

Every provider has a radar entry or a source. The ones not tested here are in `assess`.

The audit ran on the same three repositories. GCP_Data_Engineer_Fieldnotes has 36 media files, all credited by `docs/credits.md`, and nothing to fix. nexocert has two JSX images without size and no credits file. test_dk_data_analyst has no media. A first run read an `<img>` inside a code span of a Markdown document as an image. It also ignored the credits page and its folder mentions. Both are tests now.

## Writing and usability

`scripts/text_check.py check` reads Markdown, HTML and the prose inside JSON content. It detects the language and gives a readability score with its band. Spanish uses Szigriszt-Pazos with the INFLESZ scale, English uses Flesch. It also reports words per sentence, sentences over 25 and 40 words and paragraphs over 120 words. It flags long texts without headings, acronyms with no expansion at first use, link text such as "aquí" and passive voice. Every finding names its source. `--audience expert` lowers the score floor for material written for specialists.

The syllable counter follows Spanish diphthongs and hiatus. It counts "ayuda", "días", "una", "lee" and "elegida" right. A tool built on hyphenation, such as textstat 0.7.13 through pyphen, counts each one syllable short. Hyphenation never splits off one letter.

These measures are proxies. `text_check.py protocol PAGE --task "..."` writes a comprehension test card in `docs/evidence/comprehension/`. The card has a five second test, the task and questions whose answer is on the page. Five readers of the audience do it. Then `text_check.py evidence` reports each page as not run, too few readers or tested. It gives the completion and right answer rates. A page counts as tested only after five readers. `skills/web-improve/references/writing-and-usability.md` has the method and Nielsen's ten heuristics for the reviewer.

## Router

Three new recipes cover this file. `learning-site` takes a question bank or a request about learning. `content-clarity` takes a request about the text. `visual-asset` takes a diagram, an image or a clip. Six more cover the families of the owner's guide: `powershell-script`, `api-service`, `infra`, `hardware`, `mobile-app` and `ci-maintenance`. Words in a request add a capability to any recipe, such as a diagram or a speed check for a web change. The catalog has 36 capabilities and 121 providers.

The fingerprint now sees question banks, images, video, captions and diagram sources. It sees the video and image libraries of a project. It sees the project kinds of the guide, from OpenAPI and Android to Godot, dbt, Kubernetes and Quarto. The decision also says what to install before the tests. It reads that from the lockfiles and the requirement files.

### Pilots with the real verification commands

| Repository | Command the router chose | Result |
| --- | --- | --- |
| GCP_Data_Engineer_Fieldnotes | `npm test` (build, then `node --test`) | 200 of 200 tests passed in 2.4 s |
| foco_local_desktop | `go test ./...` | passed, and `go vet` for Windows passed |
| extractor_exambase | `python -m unittest discover -s tests` | 97 of 98 without the install step. With the three requirement files the router now names, 110 of 110 |
| nexocert | `npm ci`, then `npm test` | not run: installing a third party repository's packages runs its install scripts, and the session refused it |

## OpenCode MCP format

OpenCode 2 reads its native `mcp.servers` shape and the OpenCode 1 shape, with servers directly under `mcp` and `enabled`. OpenCode 1 reads only its own shape, and the OpenCode migration guide says not to point OpenCode 1 at a file converted to the native shape. So `orchestrate.py mcp config NAME --client opencode` keeps the shape both read, and `--opencode-format v2` prints `mcp.servers` for an install that runs only OpenCode 2. This was checked in the OpenCode source of 2026-11-15 (`services/site/src/docs/content/mcp-servers.mdx` and `migrate-v1.mdx`).

## Not done

- No live image search. `api.openverse.org` and `commons.wikimedia.org` were outside the network allowed in the session that wrote this. The field names come from their source code. For Openverse that is `api/api/serializers/media_serializers.py`, and for Commons the CommonsMetadata extension. The tests use recorded answers.
- No comprehension test with people. The protocol and the evidence report are ready. Readers of the audience have to do it.
- HyperFrames, D2, Remotion, Motion Canvas and the other new visual tools are registered with their verified license and source, and not run here.
- The nexocert pilot, refused as said above.

## Checks

```powershell
python -m unittest tests.test_learning_check tests.test_text_check tests.test_media tests.test_mcp_config
```

```powershell
python scripts\learning_check.py <folder of the question bank>
```

```powershell
python scripts\text_check.py check README.md docs
```

```powershell
python scripts\media.py audit .
```
