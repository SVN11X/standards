# 013. Desktop UX

A desktop app needs its own UX checks. A browser test proves nothing about a native window, and the web tools of `docs/012-learning-visuals-writing.md` read pages. `scripts/desktop_ux.py` measures what a program can check in a window. It also prepares and reads a usability test with people, the only proof that the app helps them. The router of `docs/011-request-router.md` adds both to the `windows-app` and `learning-app` recipes, and names the `desktop-improve` skill and the `desktop-tester` agent for a window, notice, tray or dialog.

## The loop

The `desktop-improve` skill works the way the owner asked on 2026-11-16: do the task the way a person does in the real executable, fix the code, and do the same task again. It names the task in the person's words first, then looks at what the window exposes, because a tkinter window shows little to UI Automation and a Win32 or Go window shows its controls. It works on a test profile, never on the owner's data. Every time a window opens it checks the focus: a window the system opens, such as a review reminder, must not take the keyboard from the app the person is typing in ([Windows window management](https://learn.microsoft.com/windows/win32/uxguide/win-window-mgt)), and a window the person opens puts the focus on its first field.

## What a program measures

`desktop_ux.py tk MODULE:FACTORY` builds a tkinter interface in its own process. The factory gets the Tk root and builds on it, like the main window class of the app. The tool opens every tab of every notebook at every size (1024x700 and 800x600 by default) and can save one screenshot of each. `--scale 1.5` tries the text at Windows scaling of 150 percent.

`desktop_ux.py uia --title TEXT` reads the UI Automation tree of a running window through pywinauto, whatever the technology: Win32, WinForms, WPF, Go or Electron. `desktop_ux.py shot --title TEXT --out FILE.png` saves a running window. Both run on Windows only.

| Rule | tk | uia | Source |
| --- | --- | --- | --- |
| Text contrast of 4.5:1, or 3:1 for large text | yes | no | [WCAG 2.2, 1.4.3](https://www.w3.org/TR/WCAG22/#contrast-minimum) |
| Targets of 24 by 24 px, or a 24 px circle that touches no other target | yes | yes | [WCAG 2.2, 2.5.8](https://www.w3.org/TR/WCAG22/#target-size-minimum) |
| Targets that touch or keep 5 px apart | yes | yes | [Windows layout guidelines](https://learn.microsoft.com/windows/win32/uxguide/vis-layout) |
| Text of 9 points or more | yes | no | [Windows font guidelines](https://learn.microsoft.com/windows/win32/uxguide/vis-fonts) |
| Text cut by its widget, and content hidden because the window is too small | yes | partly | [Windows layout guidelines](https://learn.microsoft.com/windows/win32/uxguide/vis-layout) |
| Everything a click does, a key does too | yes | yes | [WCAG 2.2, 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard) |
| Every control has a name a screen reader says | no | yes | [WCAG 2.2, 4.1.2](https://www.w3.org/TR/WCAG22/#name-role-value) |
| Buttons with the same name | no | yes | [WCAG 2.2, 2.4.6](https://www.w3.org/TR/WCAG22/#headings-and-labels) |

The sizes depend on the theme, the fonts and the display. The report names the theme and the dpi it measured with, so a run on Linux is a first signal and a run on Windows is the evidence. No program hears what a screen reader says: do the main task once with Narrator. [Axe.Windows](https://github.com/microsoft/axe-windows) checks many more UI Automation rules, and its CLI `AxeWindowsCLI` is in the `desktop-ux` capability when it is installed.

## What a person judges

The `desktop-tester` agent runs the measures, opens every screenshot and judges it against the [ten usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/). It reports which findings a program measured and which it judged. It changes no file.

[FlaUI-MCP](https://github.com/shanselman/FlaUI-MCP) lets an agent launch a Windows app, read its UI Automation tree, click, type, send keys and capture a window, with no shell, file or registry tool. It is the first MCP server of the `desktop-ux` capability: `python scripts/orchestrate.py mcp config flaui --client claude` prints its block, with the path of the downloaded executable to fill in. It drives whatever has the keyboard focus, so run it with nothing else open. [Windows-MCP](https://github.com/CursorTouch/Windows-MCP) does the same and much more, with full access to the system and Python 3.14, so it is on hold.

The [Microsoft Learn MCP server](https://learn.microsoft.com/api/mcp) returns the Windows UX guidelines a rule rests on. It gave the font, layout, target and focus rules above. `mcp config microsoft-learn` prints its block, since the catalog now holds remote servers reached by URL. [Accessibility Insights for Windows](https://accessibilityinsights.io/docs/windows/overview/) shows a person the tab order and the UI Automation tree when Tab skips or traps a control.

## What only people show

`desktop_ux.py protocol --app NAME --task "TEXT" ...` writes a card in `docs/usability/`. Five people of the audience do the main tasks one at a time, think aloud and get no help, because five people find most usability problems of a design ([Nielsen and Landauer](https://www.nngroup.com/articles/why-you-only-need-to-test-with-5-users/)). The card records whether each task was done, its seconds, its errors and where the person hesitated. It ends with the ten statements of the System Usability Scale ([Brooke 2013](https://uxpajournal.org/sus-a-retrospective/)). The Spanish wording is this standard's translation, not a validated version.

`desktop_ux.py evidence` reads the cards. It gives the success rate and median time of each task, and the mean SUS score against 68, the average of hundreds of studies (Sauro 2011). A round counts once five people did it.

## First run

On 2026-11-16 on a clone of OpenTutor, in a Linux virtual display with the default ttk theme at 100 dpi. The tool opened its six tabs at two sizes in about two seconds and saved twelve screenshots. It found a minimum window height of 640 px where the content needs 663, so the last setting, "Ventana insistente", is hidden at that height without a scrollbar. It also found five domain checkboxes 21 px tall and too close together, and six pairs of controls 3.8 px apart. Its first version reported most ttk labels as cut by 6 px, because it guessed the padding of the theme. It now reads the size a widget asks for with all its text. Nothing was run on Windows yet.
