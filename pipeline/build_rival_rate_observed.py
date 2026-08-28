#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_rival_rate_observed.py — surface the MEASURED weekly re-read of every rival's OWN rate page.

THE GAP THIS CLOSES. pipeline/pull_rival_rates.py visits each operator's pinned rate_url every
week (.github/workflows/data-rival-rates.yml) and writes source-data/rival_rate_observed.json —
the verbatim rate text found on the page PLUS a per-operator `drift` comparison against the
hand-curated card (source-data/rival_rate_card.json). Until now nothing but the CI job's log ever
read that file: the app's only rate surface (#acq's rate board, build_rate_board.py) is built from
the curated card alone. So the one MEASURED read of what rivals ACTUALLY publish this week — and,
crucially, of which of them have moved OFF the rate the app measures them against — aged in silence.

WHAT THIS MAKES. platform/data/rival_rate_observed.json: a compact, app-ready projection of that
weekly read — per operator, the distinct quotes read off its own page (verbatim Thai kept), and the
drift lines where the observed quote fell OUTSIDE the band the card carries in that unit. Operators
showing drift are sorted first, by the size of the move. The app renders a "rate-card drift watch"
panel beside the rate board.

DELIBERATELY SEPARATE FROM THE CARD. This never feeds or overwrites the curated rate card — that
separation is intentional (see docs/PROGRESS_LOG.md 2026-08-17): the card is what the board and the
undercut check measure against; this is the scheduled eyes that say when the card has gone stale, for
a human to act on. Both stay MEASURED; neither is a substitute for the other.

PROVENANCE. Every quote here is MEASURED (verbatim page text on the pull date). `drift` is this
build's comparison of that measured quote against the measured card figure in the same unit — no rate
is inferred or converted. A quote whose page states no basis is shown as-is, never restated.

Deterministic and network-free: every field derives from the input file's own stamps, never the wall
clock. `--check` byte-compares; exits 3 (SKIP) when source-data/rival_rate_observed.json is absent
(the puller is Thai-IP/browser and not run in the deterministic gate).

  python3 build_rival_rate_observed.py
  python3 build_rival_rate_observed.py --check
"""
import argparse
import io
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IN = os.path.join(ROOT, "source-data", "rival_rate_observed.json")
OUT = os.path.join(ROOT, "platform", "data", "rival_rate_observed.json")

# Per operator, the distinct quotes worth carrying into the app. A few pages (e.g. a bank's
# multi-product table) list a dozen near-identical lines; beyond this the panel stops being
# readable and the rest are counted in `quotes_more`, never silently lost.
MAX_QUOTES = 6


def _distinct_quotes(quotes):
    """Distinct (value, unit, basis) quotes in first-seen order — pages repeat the same line."""
    seen = set()
    out = []
    for q in quotes or []:
        k = (q.get("value"), q.get("unit"), q.get("basis"))
        if k in seen:
            continue
        seen.add(k)
        out.append({
            "value": q.get("value"),
            "unit": q.get("unit"),
            "basis": q.get("basis"),
            "effective_pct_year": q.get("effective_pct_year"),
            "quote_th": q.get("quote_th"),
        })
    return out


def _drift_lines(drift):
    """The lines where the observed quote fell OUTSIDE the card's band, deduped, with direction."""
    lines = (drift or {}).get("lines") or []
    out = []
    seen = set()
    for ln in lines:
        if ln.get("kind") != "drift":
            continue
        obs = ln.get("observed")
        cr = ln.get("card_range") or []
        lo, hi = (cr[0], cr[1]) if len(cr) == 2 else (None, None)
        direction = None
        if obs is not None and hi is not None and obs > hi:
            direction = "above"
        elif obs is not None and lo is not None and obs < lo:
            direction = "below"
        rec = {
            "observed": obs,
            "unit": ln.get("unit"),
            "card_lo": lo,
            "card_hi": hi,
            "delta": ln.get("delta"),
            "direction": direction,
            "card_field": ln.get("card_field"),
        }
        k = (rec["observed"], rec["unit"], rec["card_lo"], rec["card_hi"])
        if k in seen:
            continue
        seen.add(k)
        out.append(rec)
    return out


def _max_abs_delta(drift_lines):
    ds = [abs(d["delta"]) for d in drift_lines if d.get("delta") is not None]
    return max(ds) if ds else 0.0


def build():
    if not os.path.exists(IN):
        return None
    with io.open(IN, encoding="utf-8") as f:
        src = json.load(f)
    sm = src.get("meta", {}) or {}
    ops_in = src.get("operators", []) or []

    ops_out = []
    n_read = n_with_quote = n_drift_ops = n_gap_ops = 0
    for o in ops_in:
        status = o.get("status")
        if status == "ok":
            n_read += 1
        dq = _distinct_quotes(o.get("quotes"))
        if dq:
            n_with_quote += 1
        drift = o.get("drift") or {}
        dl = _drift_lines(drift)
        n_gap = sum(1 for ln in (drift.get("lines") or []) if ln.get("kind") == "gap")
        if dl:
            n_drift_ops += 1
        if n_gap:
            n_gap_ops += 1
        ops_out.append({
            "key": o.get("key"),
            "name": o.get("name_th"),
            "rate_url": o.get("rate_url"),
            "status": status,
            "error": o.get("error"),
            "fetched_via": o.get("fetched_via"),
            "quotes": dq[:MAX_QUOTES],
            "quotes_more": max(0, len(dq) - MAX_QUOTES),
            "in_card": bool(drift.get("in_card")) if drift else False,
            "drift_lines": dl,
            "n_gap": n_gap,
        })

    # Drifting operators first (bigger move first), then a stable alphabetical key order.
    ops_out.sort(key=lambda op: (0 if op["drift_lines"] else 1,
                                 -_max_abs_delta(op["drift_lines"]),
                                 op["key"] or ""))

    pulled = sm.get("pulled_at")
    n_ops = len(ops_out)
    summary = ("%d operators re-read %s · %d with a parseable quote · %d now quote a rate outside "
               "the card's band · %d quote a unit the card does not carry"
               % (n_ops, pulled or "", n_with_quote, n_drift_ops, n_gap_ops))
    out = {
        "meta": {
            "title": "Rate-card drift watch — each rival's OWN page re-read vs the hand-curated card",
            "label": ("MEASURED — the verbatim rate text read off each operator's own rate_url on the "
                      "pull date; drift is this build's comparison of that measured quote against the "
                      "measured rate the hand-curated card carries in the same unit. No rate is "
                      "restated or converted here; a quote whose page states no basis is shown as-is."),
            "provenance": ("MEASURED · pipeline/pull_rival_rates.py re-reads every operator's pinned "
                           "rate_url weekly; this layer projects that read and its card comparison. It "
                           "never overwrites source-data/rival_rate_card.json, which stays hand-curated."),
            "generated_by": "pipeline/build_rival_rate_observed.py",
            "source": ("source-data/rival_rate_observed.json (pipeline/pull_rival_rates.py) compared "
                       "against source-data/rival_rate_card.json"),
            "objective": ("Competitive risk (#2) — a scheduled watch that flags when a rival's live "
                          "page moves off the rate the app measures it against, so the curated card "
                          "does not go stale unseen."),
            "pulled_at": pulled,
            "drift_tolerance": sm.get("drift_tolerance"),
            "n_operators": n_ops,
            "n_read": n_read,
            "n_with_quote": n_with_quote,
            "n_drift_operators": n_drift_ops,
            "n_card_gap_operators": n_gap_ops,
            "summary": summary,
        },
        "operators": ops_out,
    }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    out = build()
    if out is None:
        print("SKIP: source-data/rival_rate_observed.json absent")
        return 3
    txt = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if a.check:
        if not os.path.exists(OUT):
            print("SKIP: %s not built yet" % OUT)
            return 3
        with io.open(OUT, encoding="utf-8") as f:
            cur = f.read()
        if cur != txt:
            print("DRIFT: %s differs from a fresh build" % OUT)
            return 1
        print("OK: %s reproduces byte-for-byte" % OUT)
        return 0
    with io.open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(txt)
    m = out["meta"]
    print("wrote %s — %d operators (%d drift, %d card-gap) re-read %s"
          % (OUT, m["n_operators"], m["n_drift_operators"], m["n_card_gap_operators"],
             m["pulled_at"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
