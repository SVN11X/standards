---
name: desktop-improve
description: Improve the UX of a Windows desktop app, tkinter, Win32, Go, WinForms, WPF or Electron, by doing the task the way a person does in the real executable, fixing the code, and doing the same task again. Covers windows, dialogs, notices that pop up, tray icons, quizzes, keyboard and focus, scaling, contrast, target size and usability tests with people. Use this whenever the user wants to improve, fix or polish a window, notice, tray, dialog, form, quiz or control of a desktop app, or says the app is confusing, interrupts, loses focus or does not fit, even if they never say "UX".
---

# desktop-improve

Improve what a person meets in the window, proven in the executable on Windows. A browser test proves nothing about a native window, and a passing unit test proves nothing about how the window feels.

`<standard>` is the copy of the standard the plugin ships in `skills/repo-setup/standard`, or a checkout of SVN11X/standards.

## Ground rules

- Talk to the owner in their language. Write code, comments and docs in English. Text people see stays in the app's language.
- Work on a test profile, never on the owner's data: point the app's data folder (for example `LOCALAPPDATA`) at a scratch folder, or use the app's own test profile.
- Keep the app's toolkit, theme and words. Fix the cause with the smallest change. No new UI framework for a UX fix.
- Never claim "verified on Windows" without a run on Windows. Say what ran and what did not.

## 1. Name the task

Write the task in the person's words, with what done looks like, before touching code: "while I type in another window, the review notice lets me finish the sentence; when I choose to start, the keyboard goes to the first question". A task the owner can recognize when it is done.

## 2. See what the window exposes

- tkinter exposes little to UI Automation. Measure it from inside: `python <standard>/scripts/desktop_ux.py tk <module>:<factory> --shots <scratch>` builds the interface on a Tk root, opens every tab at 1024x700 and 800x600 and saves screenshots. Add `--scale 1.5` for Windows scaling at 150 percent.
- Win32, Go, WinForms, WPF and Electron expose controls to UI Automation. Read them with the FlaUI MCP server (`windows_snapshot`) or with `python <standard>/scripts/desktop_ux.py uia --title "<title>"`.
- When `AxeWindowsCLI` is installed, scan the process too: `AxeWindowsCLI --processName <exe>`.

## 3. Reproduce the difficulty

Do the task as a person would, in the running executable: launch it, use the keyboard first and the mouse second, and take a screenshot at each step. With the FlaUI MCP server: `windows_launch`, `windows_snapshot`, `windows_send_keys`, `windows_type`, `windows_screenshot`. Without it, ask the owner to run the steps and describe or capture what happens. Write down the steps, so the same steps prove the fix.

Check these every time a window, notice or dialog is involved:

- A window the system opens, such as a reminder or a quiz that pops up, must not take the keyboard from the app the person is using. It shows on top without focus, or flashes its taskbar button, and the person activates it when ready ([Windows window management](https://learn.microsoft.com/windows/win32/uxguide/win-window-mgt)). Test it by typing in Notepad while it appears.
- A window the person opens takes the focus once, on its first field or action ([WCAG 2.2, 2.4.3](https://www.w3.org/TR/WCAG22/#focus-order)).
- Tab reaches every control in reading order, Esc closes or cancels, Enter does the default action ([WCAG 2.2, 2.1.1](https://www.w3.org/TR/WCAG22/#keyboard)).
- Closing in the middle of a task and coming back keeps what was done, or says plainly that it did not.
- At 150 percent scaling the main action stays visible without scrolling or a cut label.
- When it feels slow, measure before guessing: Windows Performance Recorder and Analyzer show where the time goes.

## 4. Fix and do the same task again

Change the code, then repeat the same steps and screenshots. Run `desktop_ux.py` again, the repository's tests, and the standard check. Keep the evidence: a test that drives the interface (a tkinter test that calls the window's own methods, a Go test, or a pywinauto script for a Win32 window) so the problem cannot come back unnoticed.

## 5. Report

Show the before and after screenshots side by side, the findings a program measured and the ones you judged from the screenshots against the [ten usability heuristics](https://www.nngroup.com/articles/ten-usability-heuristics/), and what is still open. Hand the review of a large change to the `desktop-tester` agent. When a change reshapes a main task, propose `python <standard>/scripts/desktop_ux.py protocol --app <name> --task "..."`: five people doing the task are the proof that it helps (`docs/013-desktop-ux.md` in SVN11X/standards).
