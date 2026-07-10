export const meta = {
  name: 'platform-committee',
  description: 'Standing committee: UX/UI + coherence review of the whole platform, plus the twofold analytical objective — economic-impact areas and demographics→product-mix',
  whenToUse: 'A full platform assessment cycle. Members review in parallel, top findings are adversarially verified against the committed data, then one synthesis report ranks what to fix/build.',
  phases: [
    { title: 'Review', detail: 'ux-ui ∥ coherence ∥ economic-impact ∥ demographics→product-mix' },
    { title: 'Verify', detail: 'adversarial check of the top findings against committed layers' },
    { title: 'Synthesize', detail: 'one ranked report: fixes, builds, and the two area maps' },
  ],
}

const FINDINGS = {
  type: 'object', required: ['member', 'findings'],
  properties: {
    member: { type: 'string' },
    findings: {
      type: 'array', maxItems: 12,
      items: {
        type: 'object', required: ['title', 'detail', 'severity', 'evidence'],
        properties: {
          title: { type: 'string' },
          detail: { type: 'string', description: 'what is wrong / what the data shows, concretely' },
          severity: { type: 'string', enum: ['high', 'medium', 'low'] },
          evidence: { type: 'string', description: 'file/route/layer + the specific numbers or selectors backing this' },
          proposal: { type: 'string', description: 'the concrete fix or build this implies' },
        },
      },
    },
  },
}

const COMMON = `You are one member of the AutoX credit-intelligence platform committee. Repo: /home/user/competitive-intel (read CLAUDE.md first). The platform is a static site in platform/ (serve over http, never file://; Chromium at /opt/pw-browsers/chromium). Data layers live in platform/data/*.json, each with meta provenance. Audience: a non-technical Corp Strategy Director — lead with the answer, concrete numbers, honest measured/estimated labels. Return ONLY structured findings with real evidence (routes, selectors, file names, numbers you actually read). No fabrication: if you didn't verify it, don't claim it.`

phase('Review')
const MEMBERS = [
  { key: 'ux-ui', prompt: `${COMMON}
Role: UX/UI reviewer. Serve platform/ and drive EVERY nav route headlessly (#home, #overview, #map, #acq, #exposure, #trend, #sim, #provinces, #market, #branches — plus province.html?p=rayong and rayong-catchment.html). For each: page errors, broken/empty sections, skeletons that never resolve, unreadable text in light AND dark theme (?theme=), mobile viewport (390x844) overflow/clipping, dead links, load time outliers. The Overview has grown many boards this week (New-vehicle market, EV exposure/penetration, rain pulse) — check the page still reads as one prioritized story, not a pile. Report the worst concrete issues.` },
  { key: 'coherence', prompt: `${COMMON}
Role: Coherence reviewer. Does the platform tell ONE consistent story? Check: (1) the same fact shown in two places agrees (branch counts, vehicle totals, EV shares — note stock 0.95% vs new-registration ~10% MUST be framed distinctly wherever EV appears); (2) measured/estimated labels are consistent for the same layer across tabs; (3) the exec path Home → Overview → National → province drill hands off logically (no orphaned insights, no tab that contradicts the Home thesis); (4) terminology consistency (agri-PD vs agri stress vs agri pressure — one vocabulary?); (5) stale copy contradicting newer data (e.g. text still calling something a proxy after a measured layer landed). Read app.js render functions + the JSON layers to verify claims.` },
  { key: 'econ-impact', prompt: `${COMMON}
Role: Economic-impact analyst (objective A). Using ONLY committed layers (platform/data: crop_stress, macro_sensitivity, regional_outlook, brand_trends, ev_exposure, ev_penetration, thaiwater_rain, household_risk_by_province, province_stress_index, loan_tape_derived[SYNTHETIC — exclude], amphoe), identify WHICH AREAS (provinces, and districts where layers allow) carry the largest CURRENT impact from economic factors — crop-price cycles, EV transition vs auto-industry employment, household leverage, drought/flood, tourism/manufacturing softness. Deliver a ranked area list: area → dominant factor(s) → measured magnitude → what it means for a title lender. Also: name any impact the DATA supports but the PLATFORM doesn't yet surface (gap = proposal).` },
  { key: 'product-mix', prompt: `${COMMON}
Role: Demographics→product-mix analyst (objective B). Using committed layers (branch_workforce buckets/mix, branch_occupations, amphoe occupations, household income/debt by province, vehicle mix per province [moto/car/pickup shares], farmer households, ev_penetration, branch_agri, scurve_by_province), characterize the LOCAL DEMOGRAPHICS of area archetypes (e.g. Isan agri-moto, EEC factory-worker, urban merchant, southern rubber) and derive what PRODUCT MIX each offers: motorcycle-title vs car/pickup-title vs agri-season lending vs SME/merchant lending — with the measured shares that justify each. Deliver: per-region + notable-province product-mix table with evidence, plus whether the platform currently answers 'what should this branch SELL' (the recs say acquire/defend — do they say which product?). Gaps = proposals.` },
]
const reviews = await parallel(MEMBERS.map(m => () =>
  agent(m.prompt, { label: `review:${m.key}`, phase: 'Review', schema: FINDINGS })
))

phase('Verify')
const alive = reviews.filter(Boolean)
const top = alive.flatMap(r => (r.findings || []).filter(f => f.severity !== 'low').map(f => ({ ...f, member: r.member })))
log(`${alive.length}/4 members reported · ${top.length} med+high findings to verify`)
const VERDICT = {
  type: 'object', required: ['confirmed', 'note'],
  properties: { confirmed: { type: 'boolean' }, note: { type: 'string' } },
}
const verified = await parallel(top.slice(0, 14).map(f => () =>
  agent(
    `${COMMON}\nRole: adversarial verifier. Try to REFUTE this committee finding by checking the actual repo/data/pages:\n\n${JSON.stringify(f, null, 1)}\n\nConfirm ONLY if the evidence holds when you check it yourself (open the file, run the page, read the numbers). Default to confirmed=false when uncertain.`,
    { label: `verify:${(f.title || '').slice(0, 30)}`, phase: 'Verify', schema: VERDICT }
  ).then(v => ({ ...f, verdict: v }))
))

phase('Synthesize')
const confirmed = verified.filter(Boolean).filter(f => f.verdict && f.verdict.confirmed)
const lows = alive.flatMap(r => (r.findings || []).filter(f => f.severity === 'low').map(f => ({ ...f, member: r.member })))
const report = await agent(
  `${COMMON}\nRole: committee chair. Write the assessment report for Kaustav from these CONFIRMED findings (adversarially verified) plus the unverified low-severity list.\n\nCONFIRMED:\n${JSON.stringify(confirmed, null, 1)}\n\nLOW (unverified):\n${JSON.stringify(lows, null, 1)}\n\nStructure: (1) Bottom line — 3 sentences; (2) UX/coherence fixes ranked by impact (with the concrete fix each); (3) OBJECTIVE A — the economic-impact area map (ranked areas, factors, magnitudes); (4) OBJECTIVE B — the demographics→product-mix map (per region/archetype, with measured shares); (5) Build recommendations ranked (what new surface/layer each implies, smallest-first). Plain language, lead with answers, keep every number sourced.`,
  { label: 'chair:report', phase: 'Synthesize' }
)
return { report, confirmed_count: confirmed.length, members_reported: alive.length }
