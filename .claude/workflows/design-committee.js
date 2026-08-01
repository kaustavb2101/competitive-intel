export const meta = {
  name: 'design-committee',
  description: 'UX/IA committee: audit nav staleness, inventory province-card data, map 5-pillar integration',
  phases: [
    { title: 'Audit', detail: '3 parallel auditors: nav/staleness, card data inventory, pillar mapping' },
    { title: 'Verify', detail: 'cross-check auditor claims against the repo' },
  ],
}

const REPO = 'c:/Users/Kaustav Bagchi/competitive-intel/competitive-intel'

const NAV_SCHEMA = {
  type: 'object',
  properties: {
    tabs: { type: 'array', items: { type: 'object', properties: {
      name: { type: 'string' }, route: { type: 'string' },
      renders: { type: 'string' }, data_files: { type: 'array', items: { type: 'string' } },
      vintage: { type: 'string' }, status: { type: 'string', enum: ['ok','stale','broken','duplicate','orphan'] },
      issue: { type: 'string' }, recommendation: { type: 'string' },
    }, required: ['name','route','renders','status','recommendation'] } },
    nav_flow_problems: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['tabs','nav_flow_problems','summary'],
}

const CARD_SCHEMA = {
  type: 'object',
  properties: {
    fields: { type: 'array', items: { type: 'object', properties: {
      metric: { type: 'string' }, file: { type: 'string' }, key_path: { type: 'string' },
      measured: { type: 'boolean' }, coverage: { type: 'string' }, note: { type: 'string' },
    }, required: ['metric','file','measured','coverage'] } },
    proposed_five: { type: 'array', items: { type: 'object', properties: {
      metric: { type: 'string' }, why: { type: 'string' }, drill_target: { type: 'string' },
    }, required: ['metric','why','drill_target'] } },
    verdict_inputs: { type: 'array', items: { type: 'string' } },
    summary: { type: 'string' },
  },
  required: ['fields','proposed_five','verdict_inputs','summary'],
}

const PILLAR_SCHEMA = {
  type: 'object',
  properties: {
    pillars: { type: 'array', items: { type: 'object', properties: {
      pillar: { type: 'string' }, current_front: { type: 'string' },
      granular_layers: { type: 'array', items: { type: 'string' } },
      card_slot: { type: 'string' }, drill_path: { type: 'string' },
    }, required: ['pillar','current_front','card_slot','drill_path'] } },
    summary: { type: 'string' },
  },
  required: ['pillars','summary'],
}

phase('Audit')
const [nav, card, pillar] = await parallel([
  () => agent(
    `Audit the NAVIGATION + TAB STALENESS of the AutoX competitive-intel app at ${REPO}/platform/.\n` +
    `The owner (CSO) says some tabs feel stale (e.g. "Status") and the nav flow is cluttered — the More menu holds: Data book, Map view, Risk trend, Provinces, Market, Branches, Simulator, Status. Primary nav: Home, Macro, Acquisition, Assistance, Risk, Competition.\n` +
    `For EVERY tab/route (primary nav hash routes in index.html/app.js AND every More-menu item AND standalone pages data.html, status page, rayong-catchment.html, province.html, branch-explorer.html):\n` +
    `1. What it renders (one line). 2. Which data files it reads (grep the render fn for fetch/loadJSON paths). 3. Data vintage where discoverable (platform/data/provenance.json vintages, meta.updated). 4. Verdict: ok / stale (old data or superseded purpose) / broken / duplicate (same content reachable elsewhere) / orphan (unreachable or leftover). 5. One-line recommendation (keep / merge-into-X / retire / refresh).\n` +
    `Pay special attention to: the Status page (what is it, is status_data.json stale?), Map view (demoted map — is it still worth a menu slot?), duplicate paths to the same content (e.g. Branches vs Data book branches, Provinces vs Market), and whether the More menu could be collapsed.\n` +
    `Also list nav_flow_problems: concrete IA problems (e.g. "two entry points to province content with different data").\n` +
    `Be factual — read the actual code (index.html nav markup, app.js router, data.html). Cite real file paths. Do not modify anything.`,
    { label: 'audit:nav-staleness', phase: 'Audit', schema: NAV_SCHEMA }
  ),
  () => agent(
    `Inventory the MEASURED per-province data available in the AutoX competitive-intel repo at ${REPO} to ground a "Province Impact Card" — a TMLI-style concise card: 1 verdict line + exactly 5 headline numbers, every number drilling into an existing granular view.\n` +
    `Enumerate every per-province field usable on such a card. Check at minimum these files in platform/data/: tape_real.json (.geo.provinces — loan tape NPL-live/90+/book by province), crop_stress.json, household_risk_by_province.json, occupation_income.json, province_risk.json, province_pressure.json, province_stress_index.json, rival_pressure.json / rival_density.json / rival_threat.json, competitor_coverage.json, macro_sensitivity.json, drought_district.json (district-level, aggregatable), amphoe.json, province_lfs.json, region_debt.json, search_demand.json, peer_province.json, and source-data/household_debt_by_province.json, vehicles_by_province.json.\n` +
    `For each: metric name, file, key path, measured vs estimated (read the meta.source/label in the file), coverage (all 77 provinces? fewer?), and a short note.\n` +
    `Then PROPOSE the best 5 headline numbers for the card (with why + which existing view each should drill into: data.html?p=<slug>, province.html?p=<slug>, rayong-catchment.html?city=<slug>, or an app.js hash route), and list the verdict_inputs (which fields should drive the one-line verdict).\n` +
    `Ground every claim in the actual files — open them and check keys + provenance labels. Do not modify anything.`,
    { label: 'audit:card-data', phase: 'Audit', schema: CARD_SCHEMA }
  ),
  () => agent(
    `Map how "Province Impact Cards" (a TMLI-style concise summary layer) slot into the existing 5-PILLAR IA of the AutoX competitive-intel app at ${REPO}/platform/ WITHOUT removing any granular capability.\n` +
    `The 5 pillars (nav: Home, Macro, Acquisition, Assistance, Risk, Competition — see index.html nav + app.js router). For each pillar: 1. current front door (which view/render fn, one line). 2. its granular layers (the data-heavy views/tables it drills into today — name the render functions/routes). 3. card_slot: where a Province Impact Card row/grid would sit in THIS pillar (be specific: which container, above/below what). 4. drill_path: the click path from card number -> existing granular view (cite real routes like data.html?p=, #trend, #acq sections).\n` +
    `Constraint from the owner: cards must be ADDITIVE — nothing granular gets removed; cards are the summary row, granular is the drill. Read app.js render functions to ground claims. Do not modify anything.`,
    { label: 'audit:pillar-map', phase: 'Audit', schema: PILLAR_SCHEMA }
  ),
])

phase('Verify')
// Cross-check the two claims the mockup depends on hardest: stale-tab verdicts + the proposed 5 numbers.
const checks = []
if (nav) {
  const flagged = nav.tabs.filter(t => t.status !== 'ok').map(t => `${t.name} [${t.status}]: ${t.issue || ''} -> ${t.recommendation}`).join('\n')
  checks.push(() => agent(
    `Verify these tab-staleness verdicts against the repo at ${REPO}/platform/ (read the actual files; refute anything wrong):\n${flagged}\n` +
    `Return corrected: for each item say CONFIRMED or REFUTED with one-line evidence (file/vintage).`,
    { label: 'verify:nav-verdicts', phase: 'Verify' }
  ))
}
if (card) {
  const five = card.proposed_five.map(f => `${f.metric} (drill: ${f.drill_target})`).join('; ')
  checks.push(() => agent(
    `Verify that each of these 5 proposed province-card metrics is actually computable for (nearly) all 77 provinces from committed files in ${REPO}/platform/data/, and that each drill target route exists in the code: ${five}.\n` +
    `Open the files, count province coverage, check the routes exist in app.js/data.html. Return per metric: CONFIRMED (coverage N/77, route exists) or REFUTED (why).`,
    { label: 'verify:card-five', phase: 'Verify' }
  ))
}
const verifications = (await parallel(checks)).filter(Boolean)

return { nav, card, pillar, verifications }