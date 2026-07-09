# AGENT_PATTERNS.md — how every recurring process runs (adopted 2026-07-09)

Three orchestration patterns, applied to all of this repo's processes. Same workers, different boss:
**who controls the flow is the whole story.**

| # | Pattern | Who controls | This repo's implementation |
|---|---|---|---|
| 1 | **Sub-agent** — spin up a worker on the fly, get the answer back | Claude, ad-hoc | the `Agent`/Explore tool in any session |
| 2 | **Agent team** — fixed, named specialists | The roster (`.claude/agents/*.md`) | `data-hunter` · `gate-runner` · `ui-verifier` · `provenance-auditor` (+ the Python committee: scout/census/geocoder/validator) |
| 3 | **Dynamic workflow** — a script fans out, merges, loops | The script (`.claude/workflows/*.js`) | `data-hunt` (probe sweep) · `ship-check` (pre-commit verify fan-out) |

## Process → pattern map

| Process | Pattern | Invocation |
|---|---|---|
| Recon / codebase mapping before a change | 1 sub-agent | spawn an Explore agent; keep the main chat clean |
| One-off source probe ("is X reachable?") | 1 sub-agent | quick Bash/agent probe, record verdict in CKAN_SOURCES.md |
| **Data-hunt wave** (many sources at once) | **3 workflow** | `Workflow({name:"data-hunt"})` — parallel probes catch whichever INTERMITTENT window (DLT!) is open right now |
| **Pre-ship verification** (gate + UI + provenance) | **3 workflow** | `Workflow({name:"ship-check", args:{route:"#overview", expect:"…"}})` — three independent checks you can trust, in parallel |
| Gate run alone | 2 team | `Agent(subagent_type:"gate-runner")` |
| UI render check alone | 2 team | `Agent(subagent_type:"ui-verifier")` |
| New-layer honesty audit | 2 team | `Agent(subagent_type:"provenance-auditor")` |
| Source mining after a probe hits | 2 team | `Agent(subagent_type:"data-hunter")` |
| Competitor / geocode / gov-census refresh | 2 team (Python) | `committee/run_cycle.py` + the CI workflows (committee-geocode.yml, data-gov-census.yml) |
| Scheduled feed refreshes (NABC, fuel, macro, rain) | 3 workflow (CI) | `.github/workflows/data-*.yml` — the script holds the loop, draft-PR pattern |

## Rules that keep the patterns honest
- Workflows/agents VERIFY before they ship: the gate must show 0 failed; skips are findings; nothing
  labelled MEASURED without a citable dataset id (see each agent's .md for its specific method).
- Sub-agents are for answers, not side-effects; only the team/workflow patterns write files, and only
  the main session (or a CI draft-PR) commits.
- The committee's Python members remain the network-data generators; the `.claude/agents` roster are
  the session-side specialists. Don't duplicate one in the other.
