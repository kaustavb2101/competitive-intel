# docs/decks — presentation builds

## MCOM · 5 August 2026 — the Macro tab

```bash
python docs/decks/build_mcom_macro_pptx.py              # -> mcom-2026-08-05-macro.pptx
python docs/decks/build_mcom_macro_pptx.py --preview    # + preview/slideNN.png thumbnails
```

Deterministic, network-free, and it reads live layers out of `platform/data/` (currently
`used_vehicle_value.json` for the resale chart), so a rebuild after a data refresh picks the new
numbers up. Scope is the **Macro tab only** — external conditions, no loan book, no competition,
no branch readouts.

**Why python-pptx and not the html2pptx workflow.** Kanit is the house font — confirmed by reading
the run properties of the LTV decks, not assumed — and it is not installed on the laptop. An HTML
renderer would compute every box position with fallback metrics and lay the deck out to the wrong
widths. `deckkit.py` drives python-pptx directly and measures text against the Kanit TTF itself
through Pillow, so a box that fits at build time fits in PowerPoint.

**The fit check is the point.** There is no LibreOffice here, so nothing can render the .pptx back
for inspection. Instead every text box is measured as it is created and any string that needs more
room than its box gets reported at the end of the build; `--preview` redraws each slide with Pillow
at the same geometry so the layout can be eyeballed. The preview is approximate by construction —
it catches a box that has run off its slide, it does not certify pixels.

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
  chips, native tables, line and bar charts, the fit checker and the Pillow preview renderer.
- `build_mcom_macro_pptx.py` — the deck's content, one function, twelve slides, speaker notes on
  each.
- `mcom-2026-08-05-macro.html` — the earlier HTML version of the same deck. **Superseded**: its
  commodity slide predates the measured Thai farm-gate layer that landed 2026-08-02 and is annotated
  to that effect. The .pptx is the deliverable.
- `assets/` — the เงินไชโย and AutoX marks, extracted from the reference decks.
