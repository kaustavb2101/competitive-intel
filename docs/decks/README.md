# docs/decks — presentation builds

## MCOM · 5 August 2026 — the Macro tab

```bash
python docs/decks/build_mcom_macro_pptx.py              # -> mcom-2026-08-05-macro.pptx
python docs/decks/build_mcom_macro_pptx.py --preview    # + preview/slideNN.png thumbnails
```

Deterministic, network-free, and every figure is read out of `platform/data/` at build time — no
transcribed numbers — so a rebuild after a data refresh picks the new vintage up. Layers read:
`macro_book`, `imf_weo`, `commodity_history`, `crop_mix`, `farm_book`, `crop_farmer_income`,
`income_impact`, `province_stress_index`, `amphoe_crops`, `used_vehicle_value`, `vehicle_models`,
`collateral_book`.

Scope is the **Macro tab only, and the tab is EXTERNAL DATA** — that line is the owner's, set when
`renderRecoverySensitivity` was moved off the tab on 2026-08-02: *"it is a balance-sheet reading, and
this tab is external data."* No figure in the deck comes from the loan tape. Where a tab layer joins
our outstanding to an external number (`farm_book`, `collateral_book`, `macro_book` all do), only the
external side is used. Book readouts belong on Exposure and Risk.

The deck's job is to point at **regions, provinces and districts** where published statistics say a
household is being squeezed, early enough for a pre-emptive conversation. Turning a geography into a
call list is the Assistance tab's work and needs the book beside it.

Eighteen slides: the answer · macro backdrop and the conditions under it (2) · agriculture (6) ·
where to reach out first · collateral behind a divider (6) · the close.

### Three places the build argues with its own source, deliberately

1. **Two published prices per crop.** `crop_margin.json` (via `farm_book`) nets a **NABC daily market
   quote** against an **OAE farm-gate cost**: rice at ฿17.74/kg against a ฿9.54/kg cost reads +51%
   margin, and the layer's own headline claims all seven joined crops clear their cost.
   `crop_farmer_income.json` uses OAE's price, OAE's cost and OAE's published net return per tonne —
   one basis throughout — and reads rice at **−฿1,433 a tonne**. The costs agree (rubber ฿63.18 on
   both sides); the prices are 1.4–2.2× apart because a market quote is a milled, graded product
   several steps past the field. Slide 06 uses the OAE basis and shows the market quote in a
   separate, labelled column. **This is a live defect in `pipeline/build_crop_margin.py`, not just a
   presentation choice** — its `headline` field is wrong as written.
2. **The pickup slope.** The six-month registration window ends on a month the pipeline itself flags
   as an incentive pull-forward, so the trend column is recomputed without it (`ols_slope`) and both
   callouts say what changes — raw six-month slope +131 pickups a month, ex-January −986.
3. **The drought double-stress count** is zero only because that test is scored on world prices; the
   worked counter-example on the Thai farm gate (สุพรรณบุรี) is named instead of presenting the
   clean zero.

### Ranking discipline on slide 09

"Where to reach out first" is ordered by **how many of its four signals tripped**, with the measured
debt + unemployment composite only breaking ties. An earlier version ranked on two of the four and
displayed the other two beside the ranking, so a province tripping all four could sit at rank 30 and
never appear (สิงห์บุรี did). The lead crop comes from the full eight-crop OAE mix in
`crop_mix.json`, not `income_impact.json`'s three-crop (rice/rubber/palm) weighting — that one called
กำแพงเพชร "rice 97%" when its measured mix is 47% rice, 29% sugarcane, 18% cassava.

The crop signal trips in **70 of 77 provinces**, so the slide says out loud that it is context rather
than a discriminator; debt, unemployment and rain do the separating.

### Why python-pptx and not the html2pptx workflow

Kanit is the house font — confirmed by reading the run properties of the LTV decks, not assumed — and
it is not installed on the laptop. An HTML renderer would compute every box position with fallback
metrics and lay the deck out to the wrong widths. `deckkit.py` drives python-pptx directly and
measures text against the Kanit TTF itself through Pillow, so a box that fits at build time fits in
PowerPoint.

**The fit check is the point.** There is no LibreOffice here, so nothing can render the .pptx back for
inspection. Instead every text box is measured as it is created and any string that needs more room
than its box gets reported at the end of the build; `--preview` redraws each slide with Pillow at the
same geometry so the layout can be eyeballed. The preview is approximate by construction — it catches
a box that has run off its slide, it does not certify pixels.

### House style, read out of the reference decks rather than invented
| | |
|---|---|
| Slide | 13.333 × 7.5 in (16:9) |
| Navy | `1E2F5C` · table headers `1B2A6B` |
| Red | `CC0000` · Gold `F5C242` · Secondary text `606060` |
| Cover | navy field, gold band at L10.73 W2.60, red hairline at L10.73 W0.12, logo at 0.70/0.70 |
| Content | white field, 20pt navy title, AutoX mark at L11.63 T0.28 W1.03 H0.32, red bar at T7.38 |
| Footer | "Restricted Data – Reproduction is prohibited", 8pt |

Two deliberate departures from the reference decks:

1. **Content slides have no navy header bar.** The AutoX mark is dark navy artwork on transparency;
   the reference puts it inside that bar, where it nearly disappears. Same furniture, readable
   contrast.
2. **A desaturated green (`15795F`) was added** for tailwind figures. The house palette has no
   positive colour, and without one every number on a macro slide reads as a warning.

### Fonts
`Kanit-Regular.ttf` and `Kanit-SemiBold.ttf` live in `.fonts/` — vendored so the fit check is
reproducible on any machine rather than silently degrading to "unchecked". Kanit is SIL OFL 1.1
(Cadson Demak), which permits redistribution; see `.fonts/OFL.txt`. Override the location with
`KANIT_DIR` if you keep them elsewhere.

### Files
- `deckkit.py` — the layout kit: cover / divider / content furniture, cards, callouts, provenance
  chips, native tables, line and bar charts, the fit checker and the Pillow preview renderer. Records
  `(eyebrow, title)` per slide in `Deck.headings` so a review page needs no parallel title list.
- `build_mcom_macro_pptx.py` — the deck's content, one function, eighteen slides, speaker notes on
  each.
- `mcom-review.html` — the reviewable page: one card per slide, PNG plus the speaker note.
  Regenerated from the build, not hand-edited.
- `mcom-2026-08-05-macro.html` — the earlier HTML version of the same deck. **Superseded**: its
  commodity slide predates the measured Thai farm-gate layer that landed 2026-08-02 and is annotated
  to that effect. The .pptx is the deliverable.
- `assets/` — the เงินไชโย and AutoX marks, extracted from the reference decks.
