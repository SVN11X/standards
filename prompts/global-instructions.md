# Global instructions

Paste the text below the line into the global instructions of each tool, so every agent knows the standard even outside a repository:

- Claude Code: `~/.claude/CLAUDE.md`
- Codex: `~/.codex/AGENTS.md`
- Gemini CLI: `~/.gemini/GEMINI.md`
- Chat apps (claude.ai, ChatGPT, Gemini): the personal or custom instructions in their settings.

On Windows, `~` is your user folder, for example `C:\Users\<you>`.

---

My repositories follow SVN11X/standards: https://github.com/SVN11X/standards

- Inside a repository, follow its AGENTS.md. It wins over these lines.
- To improve a repository as a whole, use the repo-improve skill. To create a repository or reorganize one, use the repo-setup skill. Without skills, ask me to paste prompts/intake.md from the standard.
- To review code or a pull request, use the code-review skill. Without skills, ask me to paste prompts/review.md.
- To improve a website or an interactive page, use the web-improve skill.
- To review a thesis, paper, report or documentation, use the docs-review skill.
- Reply to me in the language I write in. Write every repository artifact in English.
