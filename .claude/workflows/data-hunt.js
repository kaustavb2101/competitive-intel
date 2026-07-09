export const meta = {
  name: 'data-hunt',
  description: 'Fan out probes over the Thai data-source registry, mine what answers, merge verdicts',
  whenToUse: 'One hunt wave: parallel reachability probes + dataset mining of every source worth checking, merged into next-wave targets. Invoke as Workflow({name:"data-hunt"}); optional args = extra source hints.',
  phases: [
    { title: 'Probe', detail: 'one agent per source family — reachability + dataset enumeration' },
    { title: 'Synthesize', detail: 'merge verdicts, dedupe against CKAN_SOURCES.md, rank next pulls' },
  ],
}

// The source families worth re-checking each wave. INTERMITTENT hosts are the point of the fan-out:
// probing them all in parallel catches whichever window happens to be open right now.
const FAMILIES = [
  { key: 'dlt',   prompt: 'DLT gdcatalog.dlt.go.th (INTERMITTENT — retry 3x): package_list, then package_show on any dataset not yet in source-data/dlt/. New months of stat_1_1_01 monthly brand files? stat_1_008/009 monthly transactions?' },
  { key: 'diw',   prompt: 'DIW diw-dataset.diw.go.th: package_list; anything new beyond factype3/factype2/fac-10scurve already verdicted? Check fac-eec-class3 and factype101-105-106 shapes (rows, columns, province granularity).' },
  { key: 'oae',   prompt: 'OAE catalog.oae.go.th: any NEW datasets since the last enumeration (57 known)? Check ai-drought-warning for a machine-readable resource behind the HTML dashboard.' },
  { key: 'nabc',  prompt: 'NABC agriapi.nabc.go.th: enumerate endpoints beyond daily-prices/farmer-family/land-use — production/by-province needed params last time (HTTP 400): find the correct parameters.' },
  { key: 'thaiwater', prompt: 'ThaiWater api-v3.thaiwater.net: probe endpoints beyond public/rain_24h — waterlevel, storage, flood-forecast; anything public and per-province?' },
  { key: 'fresh', prompt: 'NEW hosts only (never re-probe documented dead-ends in docs/CKAN_SOURCES.md): think of 3-5 Thai department/open-data hosts NOT yet in the map, probe them, record verdicts.' },
]

const PROBE_SCHEMA = {
  type: 'object', required: ['family', 'reachable', 'findings', 'skips', 'next_pulls'],
  properties: {
    family: { type: 'string' },
    reachable: { type: 'boolean' },
    findings: { type: 'array', items: { type: 'string' }, description: 'new datasets/endpoints found, with granularity + freshness' },
    skips: { type: 'array', items: { type: 'string' }, description: 'honest skip verdicts with reasons' },
    next_pulls: { type: 'array', items: { type: 'string' }, description: 'concrete pull commands/targets worth executing' },
  },
}

phase('Probe')
const results = await parallel(FAMILIES.map(f => () =>
  agent(
    `You are one probe of a data-hunt wave for the AutoX credit-intel repo (read docs/CKAN_SOURCES.md FIRST — it is the live source map; never re-probe its documented dead-ends).\n\nYour family: ${f.prompt}\n\nProbe from this sandbox with python3/curl (retries, UA header). Return structured findings only — do NOT write files or commit.`,
    { label: `probe:${f.key}`, phase: 'Probe', schema: PROBE_SCHEMA }
  )
))

phase('Synthesize')
const alive = results.filter(Boolean)
log(`${alive.length}/${FAMILIES.length} probes returned`)
const synthesis = await agent(
  `Merge these data-hunt probe results into a wave report for docs/CKAN_SOURCES.md:\n\n` +
  JSON.stringify(alive, null, 1) +
  `\n\nProduce: (1) verdicts per family (reachable? anything new?), (2) a ranked list of the concrete pulls worth executing next (dedupe against what CKAN_SOURCES.md says is already pulled/skipped), (3) the exact markdown block to append to the wave log. Honesty rules: skips are findings; nothing gets labelled MEASURED without a citable dataset id.`,
  { label: 'synthesize', phase: 'Synthesize' }
)
return { probes: alive, synthesis }
