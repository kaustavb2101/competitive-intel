# Working on this project in VS Code (Windows)

A plain-language setup guide. You already have the project folder on your PC
(`C:\Users\<you>\competitive-intel`) and you keep the same Claude account, so this is quick.

## One-time setup (~10 min)

1. **Install VS Code** — https://code.visualstudio.com → download for Windows → run the installer (defaults are fine).
2. **Install Git for Windows** — https://git-scm.com/downloads/win → run it, accept defaults. Lets VS Code talk to GitHub and run commands.
3. **Add the Claude Code extension** — open VS Code → `Ctrl+Shift+X` → search **Claude Code** → Install the one by **Anthropic** → restart VS Code.
4. **Sign in** — click the **✦ Spark icon** (top-right) → **Sign in** → use the **same Claude account** you use on the web. One account works everywhere (web, VS Code, terminal).

No Node.js needed. WSL not needed — native Windows is fine.

## Open the project

`File → Open Folder` → `C:\Users\<you>\competitive-intel` → **Select Folder**.

## Continue a web conversation in VS Code

In the Claude panel: **history/clock icon → Remote tab** → pick a claude.ai/code session to resume it locally. Sessions don't auto-sync, but you can pull any of them in this way. Your `CLAUDE.md`, settings, and MCP servers are shared across web + VS Code.

## Getting the latest code

The newest work lives on the branch **`claude/new-session-wto26j`** (open as PR #2), not yet on `master`.
- **Simplest:** merge PR #2 on GitHub, then in VS Code's terminal (`` Ctrl+` ``) run `git pull` — your folder updates to the latest.
- Until you merge, your local folder is the older `master` version.

## Run the site locally (optional)

In VS Code's terminal:
```
cd platform
python -m http.server 8000
```
Open http://localhost:8000 in your browser. (Use `http`, not opening the file directly, or the data won't load.)

## Deploy to Vercel (optional)

```
cd platform
npx vercel --prod
```
Prints the live URL.

## Common Windows gotchas

| Problem | Fix |
|---|---|
| Bash commands don't work | Install Git for Windows (step 2). Without it Claude falls back to PowerShell, which also works. |
| `claude` not found in the terminal | The extension doesn't add the `claude` terminal command. If you want it, run in PowerShell: `irm https://claude.ai/install.ps1 \| iex`, then restart VS Code. (Optional — the ✦ panel already does everything.) |
| Have to log in every time | You shouldn't — credentials persist in `%USERPROFILE%\.claude\.credentials.json`. If an `ANTHROPIC_API_KEY` env var is set, unset it so your normal login is used. |

Deeper docs: https://code.claude.com/docs/en/vs-code
