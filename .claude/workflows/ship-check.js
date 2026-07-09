export const meta = {
  name: 'ship-check',
  description: 'Pre-commit verification fan-out: determinism gate + UI render check + provenance audit in parallel',
  whenToUse: 'Before committing a change that touches pipeline/ + platform/. args = {route: "#overview", expect: "text the change should render"}. Invoke as Workflow({name:"ship-check", args:{...}}).',
  phases: [{ title: 'Verify', detail: 'gate-runner ∥ ui-verifier ∥ provenance-auditor' }],
}

const route = (args && args.route) || '#overview'
const expect = (args && args.expect) || ''

phase('Verify')
const [gate, ui, prov] = await parallel([
  () => agent(
    'Run the determinism gate per your role. Repo root: /home/user/competitive-intel.',
    { label: 'gate', phase: 'Verify', agentType: 'gate-runner' }
  ),
  () => agent(
    `Verify the platform route ${route} renders${expect ? ` and contains (case-insensitive): "${expect}"` : ''}. Use an uncommon port (81xx). Report page errors.`,
    { label: 'ui', phase: 'Verify', agentType: 'ui-verifier' }
  ),
  () => agent(
    'Audit ONLY the platform/data files modified in the current working tree (git status) per your role. Skip untouched layers.',
    { label: 'provenance', phase: 'Verify', agentType: 'provenance-auditor' }
  ),
])
return {
  gate: gate || 'gate agent failed',
  ui: ui || 'ui agent failed',
  provenance: prov || 'provenance agent failed',
  verdict: 'SHIP only if the gate shows 0 failed, the UI check rendered the expected content with 0 page errors, and the audit found no unlabelled/fabrication-smell layers.',
}
