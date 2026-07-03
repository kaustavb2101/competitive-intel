# First 30 minutes with Claude Code — for this project

Plain steps. You're on your own laptop now (that's the point — your Thai connection unblocks the
government data the cloud sandbox couldn't reach).

## 0. Prerequisites (one-time)
- Install **Node.js** (LTS) from nodejs.org if you don't have it. Check: `node --version`.
- Install **Python 3** (you likely have it). Check: `python3 --version`.
- Install Claude Code: `npm install -g @anthropic-ai/claude-code` then run `claude` once to sign in.
  (If the command name differs, follow the on-screen install hint.)

## 1. Put the project somewhere and open it
- Unzip this handoff. You'll get the `autox-credit-intel/` folder.
- In a terminal: `cd path/to/autox-credit-intel`
- Start Claude Code in that folder: `claude`
- It automatically reads `CLAUDE.md` — so it already knows the whole project. You can literally say:
  > "Read CLAUDE.md and docs/PROGRESS_LOG.md, then tell me the current state and what you'd do first."

## 2. See the app locally (proves it works)
```
cd platform
python3 -m http.server 8000
```
Open http://localhost:8000 in your browser. Click through Overview / National / Rayong 3D / Catchment.
(Stop the server with Ctrl-C.)

## 3. Deploy it live
```
cd platform
npx vercel --prod
```
- Choose your team "Kaustav Bagchi's projects".
- Accept the defaults (it's a static site, no build).
- It prints a live URL. That's your platform.

## 4. The high-value local job: pull the blocked data
This is what the cloud couldn't do. From your Thai connection:
```
cd ../pipeline
# rotate the old token first in Vercel, then:
export DATA_GO_TH_TOKEN=your_new_token
python3 autox_dgt_ingest.py
```
If it now downloads DLT vehicle and DIW factory data, hand the files to Claude Code and say:
> "Merge these into source-data/branches_final.json and re-derive platform/data, then redeploy."

## How to work with Claude Code (tips)
- It can run commands, edit files, and see the output — let it. You don't have to read the code.
- Talk in plain goals: "the catchment number should be a real 15-minute walk, not a circle —
  use a routing API and update the page." It'll figure out the steps (see docs/NEXT_STEPS.md #3).
- When something errors, paste the error or just say "it broke" — it can read the terminal itself.
- If you feel lost, ask it to "explain what you're about to do in one paragraph, simply" before it runs.

## If you get stuck
- The four docs in `docs/` answer most "why is it like this" questions.
- `docs/NEXT_STEPS.md` has a concrete first action for each task.
- Keep using the regular Claude chat (phone) for thinking/strategy; use Claude Code (laptop) for
  running the pipeline and deploying.

## Safety note
- The `DATA_GO_TH_TOKEN` was shared in chat earlier — **rotate it** in Vercel and mark it Sensitive.
- Don't deploy `source-data/` publicly; only `platform/` is the website.
