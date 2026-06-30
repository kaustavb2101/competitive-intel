# IMPROVEMENT BACKLOG — the standing continuous-improvement loop

> This file is the queue for the **standing improvement loop** (a scheduled trigger that fires a
> fresh session every 6 hours). Each cycle: read this file → pick the single highest-value
> **UNBLOCKED, sandbox-safe** item → build it small + graceful → `bash tests/run.sh check` must pass
> → commit/push to `claude/new-session-wto26j` → log to `PROGRESS_LOG.md` → check the item off here and
> add 1–3 new ideas (self-enriching). One substantive improvement per cycle.

## Rules for each cycle (read before picking)
- **Sandbox-only.** No item that needs a desktop/Thai-IP data pull (those live in `TONIGHT_CHECKLIST.md`).
  Anything that consumes pulled data must **degrade gracefully** when the data is absent.
- **Gate-gated.** If you can't get `tests/run.sh check` to 0 failed, revert and pick a smaller item.
- **Honest provenance.** Always label measured vs estimated (see CLAUDE.md).
- **Never** commit secrets or synthetic/generated geographic data; **only** push `claude/new-session-wto26j`.
- **Scope discipline.** Large/architectural/ambiguous ideas → write them here as a recommendation
  instead of building them. Prefer high-impact / low-effort.
- Serve the two standing objectives: **(1) portfolio risk**, **(2) where to expand**.

## Queue — UX / polish (highest priority; goal: beat DataProteins)
- [ ] **Compact the National-map lens selector** — replace the full-screen grid of ~12 description
      cards with a slim row of icon+label chips (or a dropdown); move each description into an "ⓘ"
      tooltip. The map should be visible immediately. *(impact: high, effort: M)*
- [ ] **Lead-with-the-answer hero per tab** — each tab (esp. Command center, Exposure, Acquisition)
      opens with ONE hero metric/answer, details on demand below. *(high, M)*
- [ ] **Tighten the type scale + spacing** in `styles.css` — 2–3 sizes not 6; more whitespace, fewer
      borders; stronger number hierarchy. *(high, M)*
- [ ] **Reduce prose** — convert explanatory sentences to captions; let numbers + colour carry meaning. *(med, S)*
- [ ] Fold in the **UX committee** recommendations (workflow `uxui-committee`) once available — add each
      as its own checklist item with impact/effort. *(meta)*

## Queue — enrichment / capabilities (serve the two objectives)
- [ ] **Occupation × risk cross-read** — once `branch_occupations.json` is present, flag branches whose
      borrower base is concentrated in a stressed sector (e.g. factory-heavy + industrial slowdown). Graceful absent. *(high, M)*
- [ ] **Competitor coverage QA panel** — surface found-vs-expected per brand so the lower-bound caveat
      is explicit and quantified (Srisawad ~11%, MTC ~14%, Tidlor ~37%, Heng ~35%). *(med, S)*
- [ ] **Expand `validate_data.py`** coverage as new data layers land. *(med, S)*
- [ ] **Visual-regression baselines** for the new lenses/pages (`tests/run.sh baseline`). *(low, S)*
- [ ] **Simulator: occupation-sensitivity lever** — model borrower-base exposure to a sector shock. *(med, M)*

## Blocked (need a desktop / Thai-IP pull — do NOT attempt in the loop)
- Occupation/competitor **deltas over time** — needs ≥2 vintage snapshots with the new layers.
- **NSO 2022 Business & Industrial Census** ingest — data is data.go.th (blocked from sandbox).
- Real **farm-gate** prices, isochrones (ORS/GISTDA), DLT/DIW gov refresh.

## Done (most recent first)
- (loop will append here)
