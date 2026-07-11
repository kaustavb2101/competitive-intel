export const meta = {
  name: 'branch-enrichment',
  description: 'Sub-committee: enrich the maps/3D scenes with MEASURED data for ALL 2,015 branches, not just the 3 curated provinces — audit the exact per-branch gap, find the national sources that close it, and produce a concrete executable build plan',
  whenToUse: 'The recurring "make every branch as rich as Rayong" task. Members audit what the rich scene shows vs what every other branch shows, which measured national sources can fill each gap, and how the fallback wiring must change; then one ranked BUILD plan (pull / build / wire), each item tagged with how many branches it enriches.',
  phases: [
    { title: 'Audit', detail: 'scene-inventory ∥ buildings-coverage ∥ national-sources ∥ branch-view-wiring' },
    { title: 'Verify', detail: 'adversarial check: is each enrichment measured, all-branch, and genuinely undone?' },
    { title: 'Plan', detail: 'one ranked executable build plan: pull → build → wire, with per-item branch coverage' },
  ],
}

const CONTEXT = `THE PROBLEM (owner has requested this repeatedly and it keeps not happening):
The 3D building/map scenes are RICH for the 3 curated provinces (Rayong, Bangkok, Chiang Mai) and
NEAR-EMPTY everywhere else. The Rayong scene shows: extruded Overture building footprints; population
≤10km (WorldPop, measured); a full collateral/finance/commerce POI breakdown (vehicle shops, gold
dealers, banks, fresh markets, factories, etc.); the "who works nearby" workforce split (66% informal)
+ occupation mix; and measured rivals by brand. For the other 74 provinces the per-province catchment
file isn't committed (git ls-files shows only rayong/bangkok/chiang-mai *_catchment.json; the rest are
~35MB each on an R2 bucket or fall back to a live Overpass pull that is flaky/blocked), so the branch
scene often renders EMPTY (the owner's Samut Sakhon screenshot: floating POI cubes on a bare disc).
Goal: EVERY one of the 2,015 branches gets the rich treatment, from MEASURED data, not flaky live pulls.

WHAT LIKELY ALREADY EXISTS NATIONALLY (verify before proposing): branch_population.json (WorldPop
≤10km, index-aligned to branches.json), branch_workforce.json (ESTIMATED workforce mix), branch_occupations.json /
amphoe_occupations.json (Overture establishments, measured lower bound), branches.json k10 (measured OSM
POI counts per branch), competitors_national.json / competitors_census.json (measured rivals), the DIW
factory census, source-data/perimeter_counts.json (MEASURED Overture building COUNT within 10km of each
branch, from the 77-province catchment pulls). The 3D BUILDING FOOTPRINTS themselves are the hard gap —
pull_overture_buildings.py pulls per-province from the desktop; only 3 are committed.

DO NOT re-propose documented dead-ends (read docs/CKAN_SOURCES.md). DO ground every claim in a real file
you open + a real number (how many branches/provinces it covers).`

const COMMON = `You are one member of the AutoX / เงินไชโย branch-enrichment sub-committee. Repo: /home/user/competitive-intel (read CLAUDE.md first). Static site in platform/; the 3D scenes are rayong-catchment.html (city building scene, ?city=<slug>), province.html (district deep-dive), branch-explorer.html (per-branch scene). Data in platform/data/*.json + source-data/. Audience: a non-technical Corp Strategy Director. NO fabrication — measured only, and say how many of the 2,015 branches / 77 provinces each thing actually covers.\n\n${CONTEXT}`

const FINDINGS = {
  type: 'object', required: ['member', 'findings'],
  properties: {
    member: { type: 'string' },
    findings: {
      type: 'array', maxItems: 10,
      items: {
        type: 'object', required: ['title', 'detail', 'coverage', 'evidence'],
        properties: {
          title: { type: 'string', description: 'the enrichment gap OR the source that closes it' },
          detail: { type: 'string', description: 'what is missing across branches / what measured source fills it' },
          coverage: { type: 'string', description: 'how many of the 2,015 branches / 77 provinces this covers or would cover' },
          buildable: { type: 'string', enum: ['cloud-now', 'on-disk-now', 'owner-desktop', 'blocked'], description: 'can it be pulled/built from cloud/CI now, is it already on disk unused, does it need the owner desktop, or blocked' },
          effort: { type: 'string', enum: ['S', 'M', 'L'] },
          evidence: { type: 'string', description: 'the real file(s) + numbers you actually checked' },
          proposal: { type: 'string', description: 'the concrete pull/build/wire step' },
        },
      },
    },
  },
}

phase('Audit')
const MEMBERS = [
  { key: 'scene-inventory', prompt: `${COMMON}
Role: Scene-data inventory. Serve platform/ and read rayong-catchment.html + branch-explorer.html + app.js. Enumerate EXACTLY every data layer the rich Rayong scene renders (buildings, population, each POI category, workforce, occupation, rivals, factories, rings). For EACH: is its data source NATIONAL (covers all 2,015 branches — e.g. branch_population.json, branches.json k10, competitors_national.json) or RAYONG-ONLY (curated, e.g. the dense per-city POI set)? Produce the gap list: which of the rich scene's layers DON'T render for a non-curated province, and why (open the fallback code). This is the definitive "what's missing per branch" map.` },
  { key: 'buildings-coverage', prompt: `${COMMON}
Role: 3D building-footprint coverage. The extruded building footprints are the hardest gap. Establish the ground truth: how many of the 77 provinces have a committed *_catchment.json (git ls-files platform/data)? What does source-data/perimeter_counts.json actually contain (per-branch Overture building COUNT ≤10km — how many branches)? How does rayong-catchment.html / branch-explorer.html try to load footprints for a non-curated province (R2 bucket URL? live Overpass? the perimeter fallback)? Propose the realistic path to give EVERY branch real extruded footprints — including whether a lighter national building layer (counts→procedural, or an MVT/PMTiles tile source, or committing thinned per-province sets) is the answer. Ground every number.` },
  { key: 'national-sources', prompt: `${COMMON}
Role: National measured-source scout. Read docs/CKAN_SOURCES.md (never re-propose a dead-end). For each enrichment gap the other members surface, name the MEASURED national source that fills it for all branches — preferring what's ALREADY on disk but unused (like perimeter_counts.json was), then cloud-reachable pulls (Overture, OSM/Overpass mirror, DIW, OAE, DLT, HDX WorldPop). For each: which file, how many branches it covers, cloud-buildable now vs owner-desktop. Focus on breadth — the point is uniform coverage of all 2,015 branches, not more depth on the 3 rich ones.` },
  { key: 'branch-view-wiring', prompt: `${COMMON}
Role: Wiring / fallback reviewer. The per-branch scene (branch-explorer.html) goes EMPTY for sparse locations (owner's Samut Sakhon shot: floating cubes, no buildings). Trace the exact load chain (catchment perimeter → R2 → live Overpass) and the empty-state. Two deliverables: (1) the code change that makes the national measured layers (population, POI counts, workforce, rivals) render in EVERY branch scene from committed data instead of depending on a live pull; (2) a clean graceful state when footprints genuinely can't load (ground the markers, show rings + branch + an honest note) instead of crude floating cubes. Ground in the actual functions/line numbers.` },
]
const audits = await parallel(MEMBERS.map(m => () =>
  agent(m.prompt, { label: `audit:${m.key}`, phase: 'Audit', schema: FINDINGS })
))

phase('Verify')
const alive = audits.filter(Boolean)
const all = alive.flatMap(r => (r.findings || []).map(f => ({ ...f, member: r.member })))
log(`${alive.length}/4 members reported · ${all.length} enrichment findings to verify`)
const VERDICT = {
  type: 'object', required: ['measured', 'all_branch', 'undone', 'keep', 'note'],
  properties: {
    measured: { type: 'boolean', description: 'true only if the source is genuinely measured (not modelled/fabricated)' },
    all_branch: { type: 'boolean', description: 'true if it materially improves coverage toward all 2,015 branches (not just the 3 curated)' },
    undone: { type: 'boolean', description: 'true only if not already shipped/on the scene' },
    keep: { type: 'boolean' },
    note: { type: 'string' },
  },
}
const verified = await parallel(all.slice(0, 24).map(f => () =>
  agent(
    `${COMMON}\nRole: adversarial verifier. Check this branch-enrichment finding against the actual repo/data. Confirm ONLY if it is genuinely MEASURED, materially improves coverage across the 2,015 branches (not just the 3 curated provinces), is not already shipped, and its cited file/number checks out when you open it. Default every boolean to false when uncertain.\n\n${JSON.stringify(f, null, 1)}`,
    { label: `verify:${(f.title || '').slice(0, 30)}`, phase: 'Verify', schema: VERDICT }
  ).then(v => ({ ...f, verdict: v }))
))

phase('Plan')
const kept = verified.filter(Boolean).filter(f => f.verdict && f.verdict.measured && f.verdict.all_branch && f.verdict.undone && f.verdict.keep)
const report = await agent(
  `${COMMON}\nRole: sub-committee chair. Write the BRANCH-ENRICHMENT BUILD PLAN for Kaustav from these verified findings — the concrete, ordered work that makes EVERY branch's map/scene as rich as Rayong's, from measured data. Structure:\n(1) Bottom line — 3 sentences: why it keeps not happening and the one move that unblocks the most branches.\n(2) The build plan — an ORDERED list (do first → last), each item: the pull/build/wire step, how many of the 2,015 branches it enriches, effort (S/M/L), and cloud-now vs owner-desktop.\n(3) The buildings question — the honest path to real 3D footprints for all 77 provinces (or the best measured substitute), stated plainly.\n(4) Owner-desktop asks — what only Kaustav's machine can pull, and exactly the command to run.\nLead with the answer; every number sourced; this is an execution plan, not an essay.\n\nVERIFIED FINDINGS:\n${JSON.stringify(kept, null, 1)}`,
  { label: 'chair:build-plan', phase: 'Plan' }
)
return { report, kept_count: kept.length, members_reported: alive.length }
