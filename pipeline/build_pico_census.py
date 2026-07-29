#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pico_census.py — per-province census of licensed PICO-finance operators (MEASURED).

Distils the FPO (Fiscal Policy Office) national registry of licensed พิโกไฟแนนซ์ (PICO-finance)
operators into a clean, canonical-77-province-keyed count layer. PICO-finance operators are small
non-bank lenders (licence-capped small-ticket personal/title loans) — a DIRECT competitor class to
AutoX, and one DISTINCT from the big-4 title lenders (Muangthai/Srisawad/Tidlor/Heng) already carried
in competitors_census.json. This is the measured national competitor read the Competition (#acq) view
was missing outside the coordinate-based big-4 census.

INPUT  source-data/datagoth/fpo_pico.csv — the FPO open-data registry (one row per licensed operator
       service point; columns include ชื่อนิติบุคคล / ประเภทสำนักงาน (office type: head vs branch) /
       จังหวัดที่ให้บริการ (province of service) / ที่อยู่ (address)). Pulled by pull_datagoth.py
       (--only fpo_pico) from catalog.fpo.go.th. The raw CSV is gitignored + re-pullable; this
       builder's committed OUTPUT is the repo's source of truth.

OUTPUT platform/data/pico_census.json — { meta, by_province{prov:{total,head,branch,recent,recent_op}}, zero_provinces, top }.
       Every count is MEASURED (a straight tally of the government registry by its own province field);
       no synthesis, no scoring. Province strings are folded to the canonical 77 via regionmap.canonical.

PROVENANCE is stable + byte-exact: the output is a pure function of the CSV CONTENT (not of the pull
timestamp). The registry snapshot vintage + download URL are pinned as constants below (from the FPO
resource filename picofinanceoperate-22052026.csv); bump them when a newer snapshot is pulled.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored fpo_pico.csv
is absent (the CI gate has no Thai-IP pull), so the determinism gate never breaks on a missing input.

  python3 build_pico_census.py
  python3 build_pico_census.py --check
"""
import argparse, csv, json, os, sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical, REGION

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_IN = os.path.join(ROOT, "source-data", "datagoth", "fpo_pico.csv")
OUT = os.path.join(ROOT, "platform", "data", "pico_census.json")

# Pinned to the pulled FPO resource (catalog.fpo.go.th …/picofinanceoperate-22052026.csv). These are
# constants — NOT read from the volatile pull manifest — so the output is byte-stable across re-pulls.
SNAPSHOT_URL = ("https://catalog.fpo.go.th/dataset/2b8aadd9-e0a7-45fc-8301-ea2fbdb781a2/resource/"
                "32edd6d3-a44e-4bf0-9f54-41d51cd9d4aa/download/picofinanceoperate-22052026.csv")
SNAPSHOT_VINTAGE = "2026-05-22"  # from the resource filename (DDMMYYYY)

COL_TYPE = "ประเภทสำนักงาน"        # office type: สำนักงานใหญ่ (head) / สำนักสาขา (branch)
COL_PROV = "จังหวัดที่ให้บริการ"    # province of service
COL_LICDATE = "วันที่ได้รับใบอนุญาต"  # FPO licence-grant date (ISO YYYY-MM-DD) — the "entry" signal
COL_OPDATE = "วันที่เริ่มดำเนินการ"  # FPO commencement / go-live date (ISO) — the "actually-operating" signal
HEAD_TOKEN = "ใหญ่"                # substring identifying a head office ("สำนักงานใหญ่")

# Licensing-momentum window (objective #2): operators whose licence was granted within RECENT_MONTHS
# before the registry snapshot count as RECENT entries — a rising-competitive-pressure read (where the
# sub-scale PICO field is NEWEST, not just densest). The cutoff is derived from the PINNED snapshot
# vintage, NOT wall-clock, so the count is deterministic + byte-stable across re-runs.
#
# We track TWO recency lenses on the same window, because they answer different questions and (measured
# on this snapshot) diverge materially — only ~140 of ~193/200 operators overlap:
#   • licence-grant date (COL_LICDATE)  — when FPO ISSUED the licence      → "where rival entry is newest"
#   • commencement date  (COL_OPDATE)   — when the operator WENT LIVE      → "where rivals recently went live"
# The commencement lens catches operators licensed >RECENT_MONTHS ago that only recently opened their
# doors — live competitive pressure the licence-grant lens misses entirely.
RECENT_MONTHS = 24
_sy, _sm, _sd = (int(x) for x in SNAPSHOT_VINTAGE.split("-"))
_cut = (_sy * 12 + (_sm - 1)) - RECENT_MONTHS
CUTOFF_DATE = "%04d-%02d-%02d" % (_cut // 12, _cut % 12 + 1, _sd)  # 2026-05-22 − 24mo → 2024-05-22


def _valid_iso(s):
    # zero-padded YYYY-MM-DD → lexicographic compare == chronological compare (no datetime needed)
    return (len(s) == 10 and s[4] == "-" and s[7] == "-"
            and s[:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit())


def build():
    by_prov = {}          # canonical prov -> [total, head, branch, other, recent, recent_op]
    n_total = n_head = n_branch = n_other = n_unmapped = 0
    n_recent = n_lic_parsed = n_lic_unparsed = 0
    n_recent_op = n_op_parsed = n_op_unparsed = n_op_after_snapshot = 0
    with open(CSV_IN, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            prov = canonical((row.get(COL_PROV) or "").strip())
            if not prov:
                n_unmapped += 1
                continue
            rec = by_prov.setdefault(prov, [0, 0, 0, 0, 0, 0])
            rec[0] += 1
            n_total += 1
            otype = (row.get(COL_TYPE) or "").strip()
            if HEAD_TOKEN in otype:
                rec[1] += 1; n_head += 1
            elif otype:
                rec[2] += 1; n_branch += 1
            else:
                rec[3] += 1; n_other += 1
            # licence-grant recency (MEASURED, deterministic vs the pinned snapshot cutoff)
            lic = (row.get(COL_LICDATE) or "").strip()
            if _valid_iso(lic):
                n_lic_parsed += 1
                if lic >= CUTOFF_DATE:
                    rec[4] += 1; n_recent += 1
            else:
                n_lic_unparsed += 1
            # commencement / go-live recency (MEASURED — the "actually-operating" lens, deterministic)
            opd = (row.get(COL_OPDATE) or "").strip()
            if _valid_iso(opd):
                n_op_parsed += 1
                if opd >= CUTOFF_DATE:
                    rec[5] += 1; n_recent_op += 1
                    if opd >= SNAPSHOT_VINTAGE:
                        n_op_after_snapshot += 1   # declared/imminent go-lives at or after the snapshot
            else:
                n_op_unparsed += 1

    by_province = {p: {"total": v[0], "head": v[1], "branch": v[2],
                       "recent": v[4], "recent_op": v[5]}
                   for p, v in sorted(by_prov.items())}
    # honestly surface the "other" office-type bucket only where non-zero
    for p, v in by_prov.items():
        if v[3]:
            by_province[p]["other"] = v[3]

    all_canon = set(REGION.keys())                       # the canonical 77
    zero_provinces = sorted(all_canon - set(by_prov.keys()))
    top = sorted(((p, v["total"]) for p, v in by_province.items()),
                 key=lambda kv: (-kv[1], kv[0]))[:15]
    # licensing-momentum rollup: provinces where the sub-scale PICO field is NEWEST (top by recent count)
    top_recent = sorted(((p, v["recent"], v["total"]) for p, v in by_province.items() if v["recent"]),
                        key=lambda t: (-t[1], t[0]))[:15]
    # operating-momentum rollup: provinces where the most PICO rivals recently WENT LIVE (top by recent_op)
    top_recent_op = sorted(((p, v["recent_op"], v["total"]) for p, v in by_province.items() if v["recent_op"]),
                           key=lambda t: (-t[1], t[0]))[:15]

    meta = {
        "generated_by": "pipeline/build_pico_census.py",
        "label": ("MEASURED per-province census of LICENSED PICO-finance (พิโกไฟแนนซ์) operators — a "
                  "direct small-ticket non-bank competitor class to AutoX, distinct from the big-4 "
                  "title lenders in competitors_census.json. Counts per canonical province, split by "
                  "head office vs branch office."),
        "source": ("MEASURED — FPO (Fiscal Policy Office) open-data licensed-operator registry, "
                   "catalog.fpo.go.th (picofinanceoperate CSV). One row per licensed operator service "
                   "point carrying its province of service; tallied by canonical province — a direct "
                   "count of the registry, not modelled or weighted."),
        "provenance": "measured (government licence registry, tallied by the registry's own province field)",
        "source_url": SNAPSHOT_URL,
        "vintage": SNAPSHOT_VINTAGE,
        "n_operators": n_total,
        "n_head_office": n_head,
        "n_branch_office": n_branch,
        "n_other_office_type": n_other,
        "n_unmapped_province": n_unmapped,
        "n_provinces_present": len(by_prov),
        "n_provinces_zero": len(zero_provinces),
        "office_types": {"สำนักงานใหญ่": "head office (registered HQ)",
                         "สำนักสาขา": "branch office / service point"},
        "licence_momentum": {
            "label": ("MEASURED licensing momentum — operators whose FPO licence-grant date "
                      "(วันที่ได้รับใบอนุญาต) falls within the trailing %d months before the registry "
                      "snapshot. A rising-competitive-pressure read for objective #2: where the "
                      "sub-scale PICO rival field is NEWEST, not just densest. The cutoff is derived "
                      "from the pinned snapshot vintage (deterministic), never wall-clock." % RECENT_MONTHS),
            "column": "วันที่ได้รับใบอนุญาต (licence-grant date, ISO)",
            "window_months": RECENT_MONTHS,
            "cutoff_date": CUTOFF_DATE,
            "snapshot_date": SNAPSHOT_VINTAGE,
            "n_recent": n_recent,
            "recent_share_pct": round(100.0 * n_recent / n_total, 1) if n_total else 0.0,
            "n_licence_dates_parsed": n_lic_parsed,
            "n_licence_dates_unparsed": n_lic_unparsed,
            "top_recent": top_recent,
        },
        "operating_momentum": {
            "label": ("MEASURED operating momentum — operators whose FPO commencement / go-live date "
                      "(วันที่เริ่มดำเนินการ) falls within the trailing %d months before the registry "
                      "snapshot. This is the \"actually went live\" lens, distinct from licence-grant: "
                      "it catches sub-scale rivals licensed earlier that only recently opened their "
                      "doors — live competitive pressure the licensing lens misses. Deterministic "
                      "cutoff (pinned snapshot vintage), never wall-clock." % RECENT_MONTHS),
            "column": "วันที่เริ่มดำเนินการ (commencement / go-live date, ISO)",
            "window_months": RECENT_MONTHS,
            "cutoff_date": CUTOFF_DATE,
            "snapshot_date": SNAPSHOT_VINTAGE,
            "n_recent": n_recent_op,
            "recent_share_pct": round(100.0 * n_recent_op / n_total, 1) if n_total else 0.0,
            "n_commence_dates_parsed": n_op_parsed,
            "n_commence_dates_unparsed": n_op_unparsed,
            "n_at_or_after_snapshot": n_op_after_snapshot,
            "note_at_or_after_snapshot": ("Of the recent go-lives, %d carry a commencement date at or "
                                          "after the pinned snapshot vintage (%s) — declared / imminent "
                                          "openings recorded in the registry; the FPO resource is "
                                          "refreshed in place (its download filename lags its content)."
                                          % (n_op_after_snapshot, SNAPSHOT_VINTAGE)),
            "top_recent": top_recent_op,
        },
        "objective": ("Competitive risk (#2): measured density of a distinct licensed non-bank rival "
                      "class across the existing AutoX footprint, province by province."),
        "gaps": [
            "Counts are per PROVINCE (the registry's own จังหวัดที่ให้บริการ field), not geocoded to a "
            "coordinate — so this layer COMPLEMENTS the coordinate-based rival_pressure.json rather than "
            "feeding it. The free-text address carries a district (อำเภอ) but it is not parsed here.",
            "PICO-finance is a licence category (small-ticket, licence-capped); these operators overlap "
            "AutoX's small personal/title segment but are not an identical product.",
            "The registry lists LICENSED operators as of the snapshot; a licence does not by itself "
            "guarantee an active storefront, and lapsed licences may linger a cycle.",
        ],
    }
    return {"meta": meta, "by_province": by_province, "zero_provinces": zero_provinces, "top": top}


def serialize(o):
    return json.dumps(o, ensure_ascii=False, separators=(",", ":"))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    for s in (sys.stdout, sys.stderr):
        try: s.reconfigure(encoding="utf-8")
        except Exception: pass

    if not os.path.exists(CSV_IN):
        if args.check:
            print("build_pico_census.py --check: SKIP (source-data/datagoth/fpo_pico.csv absent — "
                  "Thai-IP pull, not committed)")
            sys.exit(3)
        sys.exit("fpo_pico.csv missing — run: python3 pull_datagoth.py --only fpo_pico")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_pico_census.py --check: SKIP (pico_census.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_pico_census.py --check: pico_census.json drifted — run "
                     "python3 pipeline/build_pico_census.py")
        print("build_pico_census.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d operators across %d provinces; %d head / %d branch; %d provinces with none)"
          % (OUT, m["n_operators"], m["n_provinces_present"], m["n_head_office"],
             m["n_branch_office"], m["n_provinces_zero"]))
    print("  top: %s" % ", ".join("%s=%d" % (p, n) for p, n in obj["top"][:6]))
    lm = m["licence_momentum"]
    print("  licence-momentum: %d licensed in trailing %dmo (>=%s) = %.1f%% of field; newest: %s"
          % (lm["n_recent"], lm["window_months"], lm["cutoff_date"], lm["recent_share_pct"],
             ", ".join("%s=%d" % (p, r) for p, r, _ in lm["top_recent"][:6])))
    om = m["operating_momentum"]
    print("  operating-momentum: %d went live in trailing %dmo = %.1f%% of field (%d at/after snapshot); "
          "newest live: %s"
          % (om["n_recent"], om["window_months"], om["recent_share_pct"], om["n_at_or_after_snapshot"],
             ", ".join("%s=%d" % (p, r) for p, r, _ in om["top_recent"][:6])))
    if obj["zero_provinces"]:
        print("  zero-PICO provinces: %s" % ", ".join(obj["zero_provinces"]))


if __name__ == "__main__":
    main()
