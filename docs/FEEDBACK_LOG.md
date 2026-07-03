# External feedback log (Loop 3 intake)

> Every external signal about the shipped product lands here, dated: the verbatim signal, the
> interpretation, and the disposition (fix shipped / queued to committee / declined + why).
> Reviewed daily during active development. Reality beats plans: entries here outrank backlog
> items at the next committee. See docs/OPERATING_MODEL.md.

## 2026-07-02
- **Signal (owner, phone):** "It still looks the same… this box doesn't move or minimize" — the 3D
  legend blocked the phone view. **Interpretation:** fixed overlays unusable on small screens.
  **Disposition:** FIXED same-day (collapsible legend, default-collapsed on mobile); later
  generalized (bottom-sheet popups, swipe-scrolling nav).
- **Signal (owner, phone):** "i cant move the menu bar." **Interpretation:** nav wrap clipped rows
  2+ under the fixed bar on phones. **Disposition:** FIXED same-day (swipe-scrolling nav +
  re-parented More menu); regression-checked at 390px.
- **Signal (owner, desktop):** Chiang Mai pull produced a 500MB file. **Interpretation:** pre-cap
  batch skipped provinces with existing files. **Disposition:** FIXED (in-sandbox re-pull, 39.6MB,
  committed); root cause noted for the batch runner.
- **Signal (owner):** "this isn't to look at expanding branches, but occupation leads near each
  branch + macro factors per customer cluster." **Interpretation:** program scope correction —
  Loop 3 editing the vision. **Disposition:** committee recharted; expansion features frozen;
  leads+macro top-10 shipped.
