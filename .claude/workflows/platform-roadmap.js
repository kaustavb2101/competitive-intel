export const meta = {
  name: 'platform-roadmap',
  description: 'Forward-looking committee: given everything that just shipped, advise WHAT TO DO NEXT — the single highest-value move plus a ranked, adversarially-verified roadmap',
  whenToUse: 'After a big wave of work, to decide the next moves. Members each propose next steps in their domain against the CURRENT (post-shipment) platform; proposals are adversarially verified (not already done? grounded in real data/gaps?); the chair synthesizes one prioritized roadmap.',
  phases: [
    { title: 'Propose', detail: 'strategy ∥ risk-analytics ∥ acquisition ∥ data-frontier ∥ ux-coherence — each proposes next moves' },
    { title: 'Verify', detail: 'adversarial check: is each proposal actually undone, grounded, and high-value?' },
    { title: 'Synthesize', detail: 'one ranked WHAT-NEXT roadmap: the top move + backlog, each with objective, effort, why-now' },
  ],
}

// What SHIPPED recently — fed to every member so they advise on the FRONTIER, not solved problems.
const SHIPPED = `ALREADY SHIPPED (do NOT re-propose these — they are done and verified):
- Trust fixes: vendored Leaflet+deck.gl (CDN-independent map), canonical "Open next" (sequenced plan), provenance-label consistency, honest competitor coverage (comparable-brands %), zero-state risk cards, ex-gold vehicle-title collateral leg on Home, favicon, 3D-scene 404 cleanup.
- Four-destination IA: nav is Home / Risk / Expand / Map&Explore with a contextual sub-nav; every legacy hash route preserved. Overview reordered so crop-household stress (objective #1) leads and the 5 collateral/EV boards are grouped behind one expander. Home slimmed to one row per theme with deep links; boot fetch double-fetches de-duplicated.
- Measured data layers added this wave (data room now 76 layers / 33 measured): drought_watch flag + OAE napprang (measured second-rice exposure behind it; Suphanburi 906k rai #2), ThaiWater flood pulse (live river levels), truck_flow (logistics-SME registration churn), labour_context (informality 63.2%, agri -300k YoY, self-employed 50.4% = the borrower base is half the workforce), peer_npl benchmark, EV penetration/exposure, brand trends. Thai farm-gate (NABC) prices now drive macro_sensitivity; measured household DTI joined the district risk score.
- Design system: one canonical :root (dead legacy palette deleted). Determinism gate at 72 checks, all green; every builder --check byte-exact.
KNOWN-DEFERRED (name only if you can argue it's now top-priority): migrate 431 inline styles to utility classes; PMTiles for the 35MB R2 catchments; 6 unlabelled data layers still need meta stamps.
STILL-BLOCKED (do not propose re-pulling): all NSO hosts, data.go.th aggregator, competitor corporate sites, IMF/FRED. The one true owner-side unlock remains a REAL loan-tape export (contract ready at pipeline/loan_tape_schema.md) — it would flip 4 SYNTHETIC outputs to measured and calibrate every estimated risk score.`

const COMMON = `You are one member of the AutoX / เงินไชโย credit-intelligence platform committee, convened to advise WHAT TO DO NEXT. Repo: /home/user/competitive-intel (read CLAUDE.md first). Static site in platform/ (serve over http, never file://; Chromium at /opt/pw-browsers/chromium). Data layers live in platform/data/*.json, each with meta provenance. Audience: a non-technical Corp Strategy Director whose two standing objectives are (1) portfolio impact / PD risk, (2) acquisition / where to expand. Lead with the answer; every claim grounded in a real file/route/number you actually checked; honest measured-vs-estimated labels; NO fabrication. Your job is NOT to re-list what's already done — it is to name the highest-value UNDONE moves.\n\n${SHIPPED}`

const PROPOSALS = {
  type: 'object', required: ['member', 'proposals'],
  properties: {
    member: { type: 'string' },
    proposals: {
      type: 'array', maxItems: 8,
      items: {
        type: 'object', required: ['title', 'rationale', 'objective', 'effort', 'value'],
        properties: {
          title: { type: 'string', description: 'the concrete next move (a build, a layer, a UX change)' },
          rationale: { type: 'string', description: 'why now — the gap it closes, grounded in a real file/route/number' },
          objective: { type: 'string', enum: ['risk', 'acquisition', 'both', 'trust/ux'] },
          effort: { type: 'string', enum: ['S', 'M', 'L'] },
          value: { type: 'string', enum: ['high', 'medium', 'low'] },
          evidence: { type: 'string', description: 'the file/route/layer + number that shows this is real and undone' },
        },
      },
    },
  },
}

phase('Propose')
const MEMBERS = [
  { key: 'strategy', prompt: `${COMMON}
Role: Corp-strategy lead. Step back: with the platform now at 76 layers / 33 measured and the four-destination IA in place, what are the 3-5 moves that most advance the two standing objectives toward the 2027 IPO story? Think in terms of decisions the director actually makes — branch openings, collections tiering, segment product mix — and what the platform still cannot answer. Name the single highest-leverage next move and defend it. Consider whether the real loan-tape export should now be pushed hard (what exactly it unlocks), and whether any shipped layer is under-exploited.` },
  { key: 'risk-analytics', prompt: `${COMMON}
Role: Portfolio-risk analyst (objective #1). The platform now has: household DTI, crop/drought stress + drought-watch, napprang second-crop exposure, collateral outlook (ex-gold leg), peer NPL, truck-flow, labour context, EV penetration. What's the next risk capability that would change a decision? Candidates to evaluate (propose the best, reject the rest with a reason): a composite early-warning score combining the measured legs; vintage-over-vintage risk deltas now that more measured layers exist; a diesel-pickup LTV lever in the simulator keyed to province diesel share; wiring peer-NPL as the calibration anchor for the estimated composites. Ground each in the actual layer.` },
  { key: 'acquisition', prompt: `${COMMON}
Role: Acquisition analyst (objective #2). The platform has: sequenced Road-to-3,000 plan (canonical "open next"), opportunity-score lens, exit-whitespace, competitor coverage (comparable-brands), rival density, contested ground. What's the next acquisition capability? Evaluate: a true sub-scale-operator fragility index ahead of the Q1-2026 BoT registration deadline (currently inferred, not measured); catchment-level (not province) vehicle mix; a merchant/SME expansion lens; branch-level ROI/payback (needs the loan tape). Propose the best moves; say which need owner-side data vs are buildable now.` },
  { key: 'data-frontier', prompt: `${COMMON}
Role: Data-frontier scout. Read docs/CKAN_SOURCES.md (the live source map — never re-propose a documented dead-end). Given what's reachable from cloud/CI (OAE, DLT gdcatalog, DIW, NABC, ThaiWater, ILOSTAT, Overpass, HDX, World Bank, BIS) and what's already pulled, name the 3-5 highest value-per-effort NEW pulls or under-exploited on-disk datasets (e.g. the 14 DLT mirror datasets — which still have no consumer? OAE main-crop yield trend? new ILOSTAT ids? DIW EEC factory class?). For each: the concrete endpoint/file, which objective it serves, and the surface it would improve. Cloud-buildable only — flag owner-side separately.` },
  { key: 'ux-coherence', prompt: `${COMMON}
Role: UX / coherence reviewer. The four-destination IA + Home slimming + Overview reorder just shipped. Serve the platform and drive the new nav headlessly (Home / Risk / Expand / Map&Explore + sub-nav) in light AND dark, mobile 390px. What are the next UX moves now that the structure changed? Look for: sub-nav sections that still overflow or bury the answer; the Risk destination's internal order (does crop-stress lead there too?); any board that still renders the same fact twice across the new destinations; the deferred inline-style→utility-class migration (is it now blocking anything?); mobile depth. Propose concrete, grounded next moves — and confirm the new IA has no regressions worth fixing first.` },
]
const proposals = await parallel(MEMBERS.map(m => () =>
  agent(m.prompt, { label: `propose:${m.key}`, phase: 'Propose', schema: PROPOSALS })
))

phase('Verify')
const alive = proposals.filter(Boolean)
const all = alive.flatMap(r => (r.proposals || []).map(p => ({ ...p, member: r.member })))
const worth = all.filter(p => p.value !== 'low')
log(`${alive.length}/5 members reported · ${all.length} proposals · ${worth.length} to adversarially verify`)
const VERDICT = {
  type: 'object', required: ['undone', 'grounded', 'keep', 'note'],
  properties: {
    undone: { type: 'boolean', description: 'true only if this is genuinely NOT already shipped' },
    grounded: { type: 'boolean', description: 'true only if the cited evidence (file/route/number) checks out' },
    keep: { type: 'boolean', description: 'true if this belongs in the what-next roadmap' },
    note: { type: 'string' },
  },
}
const verified = await parallel(worth.slice(0, 20).map(p => () =>
  agent(
    `${COMMON}\nRole: adversarial verifier. Check this proposed NEXT move against the actual repo/data/pages. Confirm ONLY if it is genuinely undone (not in the SHIPPED list, not already in platform/data or app.js), its evidence checks out when you open the file/run the page, and it is real high-value work. Default every boolean to false when uncertain.\n\n${JSON.stringify(p, null, 1)}`,
    { label: `verify:${(p.title || '').slice(0, 30)}`, phase: 'Verify', schema: VERDICT }
  ).then(v => ({ ...p, verdict: v }))
))

phase('Synthesize')
const kept = verified.filter(Boolean).filter(p => p.verdict && p.verdict.undone && p.verdict.grounded && p.verdict.keep)
const report = await agent(
  `${COMMON}\nRole: committee chair. Write the WHAT'S-NEXT roadmap for Kaustav from these adversarially-verified proposals (each confirmed undone + grounded). Structure:\n(1) Bottom line — 3 sentences: the single highest-value next move and why.\n(2) Do next (the top 3-5, ranked) — each: the move, which objective (risk / acquisition / both / trust-ux), effort (S/M/L), and the one-line why-now.\n(3) Then (the next tier, ranked briefly).\n(4) Owner-side asks — what only Kaustav can unlock (loan tape etc.) and what each would flip.\n(5) One-paragraph sequencing recommendation.\nPlain language, lead with the answer, every number sourced. Keep it tight — this is a decision aid, not an essay.\n\nVERIFIED PROPOSALS:\n${JSON.stringify(kept, null, 1)}`,
  { label: 'chair:roadmap', phase: 'Synthesize' }
)
return { report, kept_count: kept.length, members_reported: alive.length }
