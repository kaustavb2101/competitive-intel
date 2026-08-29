#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_pico_district.py — per-DISTRICT (amphoe) census of licensed PICO-finance operators (MEASURED).

Sharpens pico_census.json from province grain to DISTRICT (อำเภอ) grain by parsing the district out
of each licensed operator's free-text service address — the gap build_pico_census.py explicitly left
open ("the free-text address carries a district (อำเภอ) but it is not parsed here"). PICO-finance
operators are small non-bank lenders (licence-capped small-ticket personal/title loans) — a DIRECT
competitor class to AutoX, distinct from the big-4 title lenders in competitors_census.json. A
district-grain read of where that sub-scale rival field is densest is the competitive-risk signal the
Competition (#acq) view was missing below province level.

INPUT  source-data/datagoth/fpo_pico.csv — the FPO open-data registry (one row per licensed operator
       service point; columns include ประเภทสำนักงาน (head vs branch) / จังหวัดที่ให้บริการ (province of
       service) / ที่อยู่ (free-text address carrying ตำบล/อำเภอ/จังหวัด) / วันที่ได้รับใบอนุญาต (licence
       date)). Pulled by pull_datagoth.py (--only fpo_pico) from catalog.fpo.go.th. The raw CSV is
       gitignored + re-pullable; this builder's committed OUTPUT is the repo's source of truth.
       platform/data/amphoe.json — the authoritative set of the 928 canonical districts (Thai amphoe
       name + province_th), the SAME identity used by factories_by_district.json and the app's district
       lenses, so this layer's "province_th|amphoe" keys join cleanly.

OUTPUT platform/data/pico_district.json — { meta, by_district{ "prov|amphoe": {total,head,branch,recent} },
       top_districts, unresolved_samples }. Every count is MEASURED (a straight tally of the government
       registry); the only inference is the string-match of the parsed อำเภอ token to the district
       master, and every operator whose district cannot be resolved to a real amphoe is counted in the
       honest n_unresolved tally (NOT silently dropped). Province strings fold to the canonical 77 via
       regionmap.canonical; district keys are validated to exist in amphoe.json by construction.

PROVENANCE is stable + byte-exact: the output is a pure function of the CSV + amphoe.json CONTENT (not
of the pull timestamp). The registry snapshot vintage + URL are pinned as constants (shared with
build_pico_census.py); the licence-recency cutoff is derived from the pinned snapshot vintage, never
wall-clock, so the momentum count is deterministic across re-runs.

DETERMINISTIC + NETWORK-FREE. Carries --check; SKIP-passes (exit 3) when the gitignored fpo_pico.csv
is absent (the raw CSV is re-pullable, not committed — the FPO CKAN is reachable from CI, not
Thai-IP-gated), same convention as build_pico_census.py.

  python3 build_pico_district.py
  python3 build_pico_district.py --check
"""
import argparse, csv, json, os, re, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib.regionmap import canonical

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CSV_IN = os.path.join(ROOT, "source-data", "datagoth", "fpo_pico.csv")
AMPHOE = os.path.join(ROOT, "platform", "data", "amphoe.json")
OUT = os.path.join(ROOT, "platform", "data", "pico_district.json")

# Pinned to the pulled FPO resource (shared with build_pico_census.py) — constants, NOT read from the
# volatile pull manifest, so the output is byte-stable across re-pulls of the same snapshot.
SNAPSHOT_URL = ("https://catalog.fpo.go.th/dataset/2b8aadd9-e0a7-45fc-8301-ea2fbdb781a2/resource/"
                "32edd6d3-a44e-4bf0-9f54-41d51cd9d4aa/download/picofinanceoperate-22052026.csv")
SNAPSHOT_VINTAGE = "2026-05-22"  # from the resource filename (DDMMYYYY)

COL_TYPE = "ประเภทสำนักงาน"        # office type: สำนักงานใหญ่ (head) / สำนักสาขา (branch)
COL_PROV = "จังหวัดที่ให้บริการ"    # province of service
COL_ADDR = "ที่อยู่"                # free-text address (carries ตำบล/อำเภอ/จังหวัด)
COL_LICDATE = "วันที่ได้รับใบอนุญาต"  # FPO licence-grant date (ISO YYYY-MM-DD) — the "entry" signal
COL_OPDATE = "วันที่เริ่มดำเนินการ"  # FPO commencement / go-live date (ISO) — the "actually-operating" signal
HEAD_TOKEN = "ใหญ่"                # substring identifying a head office ("สำนักงานใหญ่")

# Momentum window (objective #2) — identical definition to build_pico_census.py so the two layers agree.
# TWO recency lenses on the same trailing-RECENT_MONTHS window, tallied per DISTRICT (they answer
# different questions and diverge materially at province grain, so they do at district grain too):
#   • licence-grant date (COL_LICDATE) — when FPO ISSUED the licence  → "where rival ENTRY is newest"
#   • commencement date  (COL_OPDATE)  — when the operator WENT LIVE  → "where rivals recently WENT LIVE"
# The commencement lens catches operators licensed >RECENT_MONTHS ago that only recently opened their
# doors — live competitive pressure the licence-grant lens misses. Cutoff derived from the pinned
# snapshot vintage, never wall-clock, so both counts are deterministic + byte-stable across re-runs.
RECENT_MONTHS = 24
_sy, _sm, _sd = (int(x) for x in SNAPSHOT_VINTAGE.split("-"))
_cut = (_sy * 12 + (_sm - 1)) - RECENT_MONTHS
CUTOFF_DATE = "%04d-%02d-%02d" % (_cut // 12, _cut % 12 + 1, _sd)  # 2026-05-22 − 24mo → 2024-05-22

# District markers in the Thai address: อำเภอ for the provinces, เขต for Bangkok khets. The district
# name is the token immediately after the marker, up to the next province marker / whitespace / digit.
_STOP = re.compile(r"(จังหวัด|กรุงเทพ|\s|\d)")


def _valid_iso(s):
    return (len(s) == 10 and s[4] == "-" and s[7] == "-"
            and s[:4].isdigit() and s[5:7].isdigit() and s[8:10].isdigit())


def parse_amphoe(addr):
    """Extract the district name from a Thai free-text address. Returns '' if no district marker."""
    for marker in ("อำเภอ", "เขต"):
        i = addr.find(marker)
        if i >= 0:
            rest = addr[i + len(marker):]
            m = _STOP.search(rest)
            return (rest[:m.start()] if m else rest).strip()
    return ""


def _district_master():
    """(prov_th -> set(amphoe names)) from amphoe.json — the authoritative 928-district identity."""
    amp = json.load(open(AMPHOE, encoding="utf-8"))["amphoe"]
    by_prov = {}
    for a in amp:
        by_prov.setdefault(a["province_th"], set()).add(a["name"])
    return by_prov


def build():
    master = _district_master()
    by_dist = {}          # "prov|amphoe" -> [total, head, branch, other, recent, recent_op]
    n_total = n_resolved = n_head = n_branch = n_other = 0
    n_recent = n_lic_parsed = n_lic_unparsed = 0
    n_recent_op = n_op_parsed = n_op_unparsed = n_op_after_snapshot = 0
    n_unmapped_prov = 0
    n_no_marker = 0       # address carried no อำเภอ/เขต marker at all
    n_off_master = 0      # parsed a district token, but it is not in the 928-district master
    off_master = {}       # (prov, amphoe) -> count, for the honest unresolved sample

    with open(CSV_IN, encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            n_total += 1
            prov = canonical((row.get(COL_PROV) or "").strip())
            if not prov or prov not in master:
                n_unmapped_prov += 1
                continue
            amphoe = parse_amphoe((row.get(COL_ADDR) or "").strip())
            if not amphoe:
                n_no_marker += 1
                continue
            if amphoe not in master[prov]:
                n_off_master += 1
                off_master[(prov, amphoe)] = off_master.get((prov, amphoe), 0) + 1
                continue

            key = "%s|%s" % (prov, amphoe)
            rec = by_dist.setdefault(key, [0, 0, 0, 0, 0, 0])
            rec[0] += 1
            n_resolved += 1
            otype = (row.get(COL_TYPE) or "").strip()
            if HEAD_TOKEN in otype:
                rec[1] += 1; n_head += 1
            elif otype:
                rec[2] += 1; n_branch += 1
            else:
                rec[3] += 1; n_other += 1
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

    by_district = {}
    for k, v in sorted(by_dist.items()):
        d = {"total": v[0], "head": v[1], "branch": v[2], "recent": v[4], "recent_op": v[5]}
        if v[3]:
            d["other"] = v[3]
        by_district[k] = d

    top_districts = sorted(((k, v["total"]) for k, v in by_district.items()),
                           key=lambda kv: (-kv[1], kv[0]))[:20]
    # licence-momentum rollup: districts where the sub-scale PICO field is NEWEST (top by recent entries)
    top_recent = sorted(((k, v["recent"], v["total"]) for k, v in by_district.items() if v["recent"]),
                        key=lambda t: (-t[1], t[0]))[:20]
    # operating-momentum rollup: districts where the most PICO rivals recently WENT LIVE (top by recent_op)
    top_recent_op = sorted(((k, v["recent_op"], v["total"]) for k, v in by_district.items() if v["recent_op"]),
                           key=lambda t: (-t[1], t[0]))[:20]
    # honest, deterministic sample of the districts that could not be joined to the 928-master
    unresolved_samples = [{"province": p, "amphoe": a, "n": c}
                          for (p, a), c in sorted(off_master.items(), key=lambda t: (-t[1], t[0]))[:20]]

    n_unresolved = n_unmapped_prov + n_no_marker + n_off_master
    meta = {
        "generated_by": "pipeline/build_pico_district.py",
        "label": ("MEASURED per-DISTRICT (อำเภอ) census of LICENSED PICO-finance (พิโกไฟแนนซ์) operators "
                  "— a direct small-ticket non-bank competitor class to AutoX. Sharpens pico_census.json "
                  "from province to district grain by parsing the อำเภอ out of each operator's registered "
                  "service address; keys are 'province_th|amphoe', joinable to amphoe.json / "
                  "factories_by_district.json."),
        "source": ("MEASURED — FPO (Fiscal Policy Office) open-data licensed-operator registry, "
                   "catalog.fpo.go.th (picofinanceoperate CSV). Per-district counts are a direct tally of "
                   "the registry; the only inference is the exact string-match of the district token "
                   "parsed from the free-text address to the 928-district master (amphoe.json)."),
        "provenance": ("measured (government licence registry; district resolved by exact-name match of "
                       "the address's อำเภอ token to the canonical 928-district master)"),
        "source_url": SNAPSHOT_URL,
        "vintage": SNAPSHOT_VINTAGE,
        "district_master": "platform/data/amphoe.json (928 canonical amphoe, province_th + Thai name)",
        "n_operators": n_total,
        "n_district_resolved": n_resolved,
        "n_districts_present": len(by_district),
        "resolution_pct": round(100.0 * n_resolved / n_total, 1) if n_total else 0.0,
        "n_unresolved": n_unresolved,
        "unresolved_breakdown": {
            "unmapped_province": n_unmapped_prov,
            "no_district_marker_in_address": n_no_marker,
            "district_not_in_928_master": n_off_master,
        },
        "n_head_office": n_head,
        "n_branch_office": n_branch,
        "n_other_office_type": n_other,
        "licence_momentum": {
            "label": ("MEASURED licensing momentum at district grain — operators whose FPO licence-grant "
                      "date falls within the trailing %d months before the pinned registry snapshot. "
                      "Where the sub-scale PICO rival field is NEWEST, not just densest (objective #2). "
                      "Cutoff derived from the pinned snapshot vintage, never wall-clock." % RECENT_MONTHS),
            "column": "วันที่ได้รับใบอนุญาต (licence-grant date, ISO)",
            "window_months": RECENT_MONTHS,
            "cutoff_date": CUTOFF_DATE,
            "snapshot_date": SNAPSHOT_VINTAGE,
            "n_recent": n_recent,
            "recent_share_pct": round(100.0 * n_recent / n_resolved, 1) if n_resolved else 0.0,
            "n_licence_dates_parsed": n_lic_parsed,
            "n_licence_dates_unparsed": n_lic_unparsed,
            "top_recent": top_recent,
        },
        "operating_momentum": {
            "label": ("MEASURED operating momentum at district grain — resolved operators whose FPO "
                      "commencement / go-live date (วันที่เริ่มดำเนินการ) falls within the trailing %d "
                      "months before the pinned registry snapshot. The \"actually went live\" lens, "
                      "distinct from licence-grant: it catches sub-scale rivals licensed earlier that "
                      "only recently opened their doors — live competitive pressure the licensing lens "
                      "misses, now localised to the อำเภอ. Deterministic cutoff (pinned snapshot "
                      "vintage), never wall-clock." % RECENT_MONTHS),
            "column": "วันที่เริ่มดำเนินการ (commencement / go-live date, ISO)",
            "window_months": RECENT_MONTHS,
            "cutoff_date": CUTOFF_DATE,
            "snapshot_date": SNAPSHOT_VINTAGE,
            "n_recent": n_recent_op,
            "recent_share_pct": round(100.0 * n_recent_op / n_resolved, 1) if n_resolved else 0.0,
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
        "objective": ("Competitive risk (#2): measured DISTRICT-level density of a distinct licensed "
                      "non-bank rival class across the existing AutoX footprint — the grain below "
                      "pico_census.json's province read."),
        "gaps": [
            "The province-level total in pico_census.json is authoritative; this layer resolves %.1f%% "
            "of operators to a district. The unresolved %d are counted honestly in unresolved_breakdown "
            "(mostly real districts absent from the 928-polygon master, e.g. some Bangkok khets), NOT "
            "dropped from the province census." % (round(100.0 * n_resolved / n_total, 1) if n_total else 0.0,
                                                   n_unresolved),
            "Resolution is by the registry's registered service address, which is the operator's HQ/branch "
            "address — a licensed storefront's district, not a modelled catchment. It COMPLEMENTS the "
            "coordinate-based rival_pressure.json rather than feeding it.",
            "PICO-finance is a licence category (small-ticket, licence-capped) overlapping AutoX's small "
            "personal/title segment but not an identical product; a licence does not guarantee an active "
            "storefront.",
        ],
    }
    return {"meta": meta, "by_district": by_district,
            "top_districts": top_districts, "unresolved_samples": unresolved_samples}


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
            print("build_pico_district.py --check: SKIP (source-data/datagoth/fpo_pico.csv absent — "
                  "Thai-IP pull, not committed)")
            sys.exit(3)
        sys.exit("fpo_pico.csv missing — run: python3 pull_datagoth.py --only fpo_pico")

    payload = serialize(build())
    if args.check:
        if not os.path.exists(OUT):
            print("build_pico_district.py --check: SKIP (pico_district.json not generated yet)")
            sys.exit(3)
        if open(OUT, encoding="utf-8").read() != payload:
            sys.exit("build_pico_district.py --check: pico_district.json drifted — run "
                     "python3 pipeline/build_pico_district.py")
        print("build_pico_district.py --check: OK (byte-exact)")
        return
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(payload)
    obj = json.loads(payload)
    m = obj["meta"]
    print("wrote %s (%d operators; %d resolved to %d districts = %.1f%%; %d unresolved)"
          % (OUT, m["n_operators"], m["n_district_resolved"], m["n_districts_present"],
             m["resolution_pct"], m["n_unresolved"]))
    print("  top districts: %s"
          % ", ".join("%s=%d" % (k, n) for k, n in obj["top_districts"][:6]))


if __name__ == "__main__":
    main()
