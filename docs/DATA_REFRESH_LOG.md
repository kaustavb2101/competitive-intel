# DATA REFRESH LOG — dated entries from the data-enrichment & integrity cycle

> Appended by the recurring DATA-ENRICHMENT & INTEGRITY routine (one entry per cycle: what was
> refreshed/enriched/audited, with provenance + source). See `docs/IMPROVEMENT_BACKLOG.md` for the
> Rules this cycle follows (no-fabrication is absolute).

## 2026-07-02 — AUDIT: `gpp_by_province.json` mislabelled MEASURED, actually a 76/77-row estimate

**Task type:** AUDIT (provenance sweep). No new data value was invented or shipped; a false
"measured" claim already sitting in the repo was corrected.

**What was found.** `source-data/tmli/provincial-gpp.js` (vendored from `kaustavb2101/watcher` in
commit `b203eb6`) titles itself `PROVINCIAL GPP KNOWLEDGE BASE — NESDC OFFICIAL DATA` and its own
`GPP_META` block cites exactly **one** CKAN-verified resource
(`ffabdf4f-b326-4d2d-8ede-a4514bf20339`, Mukdahan only). Inspecting all 82 rows:
- Only **Mukdahan** carries `source: 'CKAN-NESDC-2566'` and `confidence: 0.95` — genuinely tied to a
  named CKAN resource.
- The other **76 provinces** carry a generic `source: 'NESDC-2566'` tag, GPP figures that are all
  round multiples of 1,000–5,000 (million THB) — a strong fabrication smell for a real economic
  statistic — and confidence scores (0.75–0.97) that look hand-assigned per region rather than
  measured. `GPP_META.downloaded_at` is `new Date().toISOString()` (evaluates at *load* time), which
  is inconsistent with a genuine timestamped API pull.
- `pipeline/ingest_tmli.py` (`build_gpp()`) had copied this straight through into
  `source-data/gpp_by_province.json` with `"provenance": "MEASURED. ... NESDC 2566 B.E. (2023 CE)
  estimate."` — an incorrect blanket claim. `docs/NEXT_STEPS.md` and `docs/DATA_PROVENANCE.md` both
  repeated the MEASURED label.
- **Contrast:** the other three TMLI-vendored files (`nso-ses-debt-2566.json`,
  `nso-ses-income-2566.json`, `nso-lfs-provincial-summary.json`) have non-round, per-province-distinct
  values and (for the LFS file) an explicit `catalogapi.nso.go.th` table id + `downloaded_at`
  timestamp — consistent with real pulls. Those remain labelled MEASURED; only the GPP layer is
  affected.

**Blast radius:** contained. `gpp_by_province.json` is **not yet wired into any `platform/data`
layer** — no view or score in the live app currently uses it — so this was caught before a fabricated
number reached a user-facing screen.

**Fix applied (no fabrication — corrected the label, did not invent a number):**
- `pipeline/ingest_tmli.py` `build_gpp()`: regex now also captures the per-row `source` tag; emits it
  in each province record; rewrote `meta.provenance` to state plainly that only 1/77 rows is
  CKAN-verified and the rest are an ESTIMATED knowledge base, with an explicit "do not surface as
  MEASURED" instruction; added `meta.n_ckan_verified`.
- Regenerated `source-data/gpp_by_province.json` (`python3 ingest_tmli.py`) — **only meta + the new
  per-row `source` field changed; every `gpp_million_thb`/share/hub_type value is byte-identical to
  before** (verified via diff before committing). `ingest_tmli.py --check` reproduces byte-exact.
- Corrected the MEASURED claims in `docs/NEXT_STEPS.md` (§0a) and `docs/DATA_PROVENANCE.md` (§2
  table) to match.
- `bash tests/run.sh check` — 28 passed, 0 failed (`validate_data.py`: 125/125). (Sandbox note: this
  run required `pip install numpy==2.4.6` per `.github/workflows/qa.yml`'s pin — not present by
  default in this container; installed to mirror CI exactly.)

**Follow-up (logged, not attempted — needs a real per-province pull):** a genuine fix requires
pulling NESDC Provincial Accounts per-province from `data.go.th` (same CKAN dataset family as the
verified Mukdahan resource, `package_search?q=GPP`, 44 datasets) from a Thai IP — blocked from this
sandbox. Added to `docs/TONIGHT_CHECKLIST.md`. Until then, `gpp_by_province.json` should **not** be
wired into any `platform/data` layer or app view labelled MEASURED.

**Source:** `source-data/tmli/provincial-gpp.js` (self-disclosed provenance in its own header/`GPP_META`) — no external pull performed this cycle.

---
