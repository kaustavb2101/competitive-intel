# Operating model — the three product-development loops

> Standing process for how this platform is built and improved. Every piece of work belongs to
> one of three nested feedback loops (fast inside slow). Adopted 2026-07-02 by owner directive.

## Loop 1 — Agentic coding loop (~minutes)
**Coding agent ⇄ product spec / evals.** An autonomous agent implements ONE committee item against
its written spec, and the EVALS decide — never vibes:

- **Spec** = the committee item's `what` + `acceptance` fields (concrete, files named, honest-labeling
  requirements stated). No agent starts without one.
- **Evals** = `bash tests/run.sh check` (determinism gate + data validators — checked by REAL exit
  code, never through a pipe) **plus** a headless-browser render of the touched surface (zero page
  errors, content assertions, screenshot). UI items must render-verify on desktop AND a 390px
  phone viewport before they count as done.
- Mechanics: isolated worktree per agent; commit to an `agent/<item>` branch (incremental commits
  every ~15 units on long batches — container restarts must never lose more than one increment);
  NEVER push. The operator session merges `--no-ff`, re-runs the evals on the merged head, and
  pushes only on green.

## Loop 2 — Developer feedback loop (~hours)
**Product spec/evals ⇄ developer vision.** Kaustav's directives steer what the specs ARE:

- A directive ("occupation leads near each branch, not expansion") convenes a **committee**:
  4-6 specialist lenses propose, a chair dedups/feasibility-checks/ranks into a waved execution
  plan. Ranked items carry spec + acceptance + conflicts → they feed Loop 1.
- Every wave that lands produces a **plain-language digest** back to Kaustav (what shipped, what
  it says about the business, what's next) — the course-correction point. Standing constraints
  live in CLAUDE.md; per-cycle state in `docs/IMPROVEMENT_BACKLOG.md` + `docs/PROGRESS_LOG.md`.
- Cadence: multiple committee→wave cycles per working session.

## Loop 3 — External feedback loop (~days)
**Developer vision ⇄ external feedback.** What reality says about the shipped product:

- **Intake channels:** (1) Kaustav using the live preview on his phone (bugs/reactions land in
  chat → logged); (2) the Vercel preview **Comment** button (toolbar threads); (3) the nightly
  **site-health CI** (opens/closes a GitHub issue on live breakage); (4) eventually: branch-manager
  pilot users once the lead boards go to the field.
- **Log:** every external signal gets a dated entry in `docs/FEEDBACK_LOG.md` (verbatim signal →
  interpretation → disposition). Feedback items outrank committee backlog items at the next
  committee — reality beats plans.
- Cadence: reviewed at least daily while in active development; the vision (CLAUDE.md "two
  standing objectives") is only edited from THIS loop.

## Rules that keep the loops honest
1. A slower loop's output is a faster loop's input — never skip inward (no coding without a spec;
   no spec without the current vision).
2. Evals gate every merge; a red eval stops the push, full stop.
3. Measured vs estimated labeling is part of every spec's acceptance, and the data-integrity
   validators enforce provenance on every new layer.
4. No fabricated data, no branch-expansion features, no GL lighting/shadow changes (unverifiable
   headless) — standing constraints from Loop 3's owner.
