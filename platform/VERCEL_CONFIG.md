# Why `platform/vercel.json` looks the way it does

This file exists because `vercel.json` cannot hold comments. The two settings below look like
belt-and-braces duplication and are not — each one stops a different failure, and the second
was added only after the first proved insufficient in production.

**These notes used to live inside `vercel.json` as `//git` and `//ignoreCommand` keys.** That
worked with the Git integration, which ignores unknown keys, but the Vercel **CLI** validates
the file against its published schema and refuses to deploy: *"Invalid vercel.json — should NOT
have additional property `//git`"*. So `npx vercel --prod` had been broken by the comments while
Git-integration deploys kept working, and nobody noticed until a CLI deploy was attempted on
2026-08-16. Moved here rather than deleted; the content is the point.

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
