# Why `vercel.json` looks the way it does

## READ THIS FIRST: there are TWO vercel.json files and only ONE of them is live

    vercel.json            <- THE LIVE CONFIG. Vercel reads this.
    platform/vercel.json   <- read by NOTHING in the deployed project.

The `competitive-intel` Vercel project's Root Directory is the **repo root** — which is why the
root file carries `"outputDirectory": "platform"`. Vercel therefore reads the root
`vercel.json`, and `platform/vercel.json` is inert as far as production is concerned.

**This was not noticed for four days, and it cost production.** Every deploy guard described
below — `git.deploymentEnabled` and `ignoreCommand`, both added on 2026-08-12 specifically to
stop preview deployments burning the free-tier quota — was written into `platform/vercel.json`,
where Vercel never read it. The guards looked present in code review, in git history and in the
file that documented them. They were doing nothing.

The proof is in the deployment list: with `"**": false` supposedly in force, branch pushes for
`feat/rival-full-coverage`, `fix/vercel-json-schema` and `feat/rival-facebook-daily` all created
deployments anyway. And on 2026-08-16 production stopped updating entirely — three master
merges (#457, #459, #460, #461) produced **no production deployment at all**, leaving the live
site on an older commit. Production never retries itself.

Moved to the root file on 2026-08-16. If you edit deploy behaviour, edit **`vercel.json` at the
repo root**. Treat `platform/vercel.json` as legacy: it is what a `vercel` CLI invocation run
from inside `platform/` would read, which is a different project entirely (running
`npx vercel --prod` from that directory creates/targets a *separate* Vercel project called
`platform` — do not deploy from there; deploy from the repo root).

## Why this file exists at all

`vercel.json` cannot hold comments. The two settings below look like belt-and-braces
duplication and are not — each stops a different failure, and the second was added only after
the first proved insufficient in production.

These notes used to live inside `vercel.json` as `//git` and `//ignoreCommand` keys. That
worked with the Git integration, which ignores unknown keys, but the Vercel **CLI** validates
against its published schema and refuses to deploy: *"Invalid vercel.json — should NOT have
additional property `//git`"*. Moved here rather than deleted; the content is the point.

## `git.deploymentEnabled` — the quota lever

```json
"git": { "deploymentEnabled": { "**": false, "master": true } }
```

**Skipping a build is not the same as not deploying, and that distinction cost us the live site
on 2026-08-15.** `ignoreCommand` had skipped every non-master *build* since 2026-08-12, but
Vercel still **creates** a deployment first and only then runs the ignore step — so each skipped
preview still consumed one of the free tier's 100 deployments/day.

That day the auto-resolve loop (every master merge pushes a fresh merge commit onto every open
PR, and each push is a deployment) burned all 100. `vercel[bot]` answered
`api-deployments-free-per-day` on PRs #432 and #433, and **production froze for three consecutive
master pushes.** Production never retries itself, so the dashboard silently served an hour-old
build.

`git.deploymentEnabled` is the lever that stops the deployment being *created* at all, so it
never counts against the quota.

An earlier version of this note claimed Vercel offers no wildcard here. It does — Vercel matches
these keys with minimatch, and where a branch matches several rules a deployment happens if
**any** matching rule is true. Hence `**: false` with `master: true`: everything is off, and
master is explicitly switched back on.

## `ignoreCommand` — the belt behind the braces

```json
"ignoreCommand": "if [ \"$VERCEL_GIT_COMMIT_REF\" = \"master\" ]; then exit 1; else exit 0; fi"
```

Build **only** master; skip every other branch. Keep this even though `deploymentEnabled` above
already blocks most of it — `ignoreCommand` still guards anything that slips through, such as a
branch whose own `vercel.json` predates the rule.

**Note the inverted exit codes.** They are Vercel's, and they are easy to get backwards:
**exit 1 CONTINUES the build, exit 0 SKIPS it.**

Nothing is lost by skipping preview builds: the generated branches only ever change JSON under
`platform/data/`, and this repo verifies a PR with the QA workflow's headless render, visual and
overflow audit — not by eye on a preview URL.

To preview a branch, temporarily add it to the `ignoreCommand` test **and** give it a `true` rule
under `deploymentEnabled`. Both, or it will not deploy.

`github.enabled: false` was considered and rejected: it is deprecated, and it disables the whole
project including production.
