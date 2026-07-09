#!/usr/bin/env python3
"""
build_provenance.py — the DATA ROOM ledger (a provenance census of platform/data)
=================================================================================
Scans every committed `platform/data/*.json` (plus `provinces/index.json`) and
records, for each, whether it carries a provenance stamp (meta.label / meta.source /
meta.provenance / meta.generated_by), what that stamp says, its byte size, and its
top-level count. Emits `platform/data/provenance.json` — a deterministic listing that
powers the "Data room" card on the Command center (#home).

Three verdicts per layer:
  - MEASURED    — carries a stamp with no ESTIMATED/PROXY/SYNTH/EDITORIAL marker.
  - ESTIMATED   — carries a stamp that labels itself an estimate/proxy/synthetic/editorial.
  - UNLABELLED  — no readable meta stamp at all. This is the SHAME BOARD: files that
                  ship a numeric layer with no provenance. Named explicitly so they get fixed.

The per-province geometry basemaps (`<slug>_roads/_water/_landuse/_rail/_places/_catchment.json`)
are COLLAPSED into one "family" layer each (77 road files -> one "roads" row) so the exec card
stays readable — but any family member lacking a stamp is still counted in the per-FILE shame
tally (`files.unlabelled`) and named in `unlabelled_files`, so collapsing never hides a gap.

HONESTY RULES (sacred):
  - The verdict is read from the file's OWN meta text — nothing is invented. A file with no
    stamp is called UNLABELLED, never silently upgraded. We do NOT fabricate a source for the
    basemap geometry files that lack one; the shame board is the point.
  - Sizes/counts are read from the committed bytes on disk; --check is byte-exact.
  - provenance.json excludes itself from the scan (no self-reference).

    python3 build_provenance.py           # rebuild platform/data/provenance.json
    python3 build_provenance.py --check   # verify the committed file reproduces byte-exact

Deterministic + network-free. Pure function of the committed platform/data tree.
"""
import os, re, json, glob, argparse
from collections import Counter

ROOT = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(ROOT)
DATA = os.path.join(REPO, "platform", "data")
OUT_PATH = os.path.join(DATA, "provenance.json")
INDEX_REL = "provinces/index.json"
SELF = "provenance.json"

# meta keys that count as a provenance stamp (exactly the four named in the mandate).
PROV_KEYS = ("label", "source", "provenance", "generated_by")
# keys whose text we scan to decide MEASURED vs ESTIMATED.
VERDICT_KEYS = ("label", "source", "provenance", "objective", "title", "note",
                "honesty_caveat", "generated_with")
# markers that flip a stamped layer to ESTIMATED (uppercased substring match).
EST_MARKERS = ("ESTIMATED", "PROXY", "SYNTH", "INFERRED", "EDITORIAL", "SIMULAT")

# per-province geometry basemap families (collapsed to one row each in the card).
FAMILY_KINDS = ("catchment", "roads", "water", "places", "landuse", "rail")
KIND_LABEL = {
    "roads":     "Road-network geometry (basemap)",
    "water":     "Water-polygon geometry (basemap)",
    "landuse":   "Land-use polygon geometry (basemap)",
    "rail":      "Rail-line geometry (basemap)",
    "places":    "Named-place points",
    "catchment": "Building-footprint catchment",
}
CLS_RANK = {"unlabelled": 0, "estimated": 1, "measured": 2}


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _nonempty(v):
    """A usable provenance value: a non-blank string, or a container holding one."""
    if isinstance(v, str):
        return bool(v.strip())
    if isinstance(v, (list, tuple)):
        return any(_nonempty(x) for x in v)
    if isinstance(v, dict):
        return any(_nonempty(x) for x in v.values())
    return False


def _trunc(s, n):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _stamp_meta(d):
    """Return the meta dict iff it carries a real provenance stamp, else None."""
    if not isinstance(d, dict):
        return None
    m = d.get("meta")
    if not isinstance(m, dict):
        return None
    if any(_nonempty(m.get(k)) for k in PROV_KEYS):
        return m
    return None


def _verdict_from_meta(m):
    """MEASURED / ESTIMATED from a stamped meta dict (repo convention: estimates are tagged)."""
    parts = []
    for k in VERDICT_KEYS:
        v = m.get(k)
        if v is not None:
            parts.append(v if isinstance(v, str) else json.dumps(v, ensure_ascii=False))
    hay = " ".join(parts).upper()
    if any(mk in hay for mk in EST_MARKERS):
        return "estimated"
    return "measured"


def _label_of(m):
    """Best human label for the chip's description column."""
    for k in ("label", "source", "provenance", "generated_with", "generated_by", "title"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 160)
        if _nonempty(v):
            return _trunc(json.dumps(v, ensure_ascii=False), 160)
    return ""


def _source_of(m):
    for k in ("source", "provenance", "generated_by", "generated_with"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 140)
        if _nonempty(v):
            return _trunc(json.dumps(v, ensure_ascii=False), 140)
    return ""


def _vintage_of(m):
    for k in ("updated", "vintage", "as_of", "updated_to"):
        v = m.get(k)
        if isinstance(v, str) and v.strip():
            return _trunc(v, 24)
    return ""


def _top_count(d):
    """(count, count_of): the longest top-level list, or the root list length."""
    if isinstance(d, list):
        return len(d), "rows"
    if isinstance(d, dict):
        best_k, best_n = "", -1
        for k, v in d.items():
            if k in ("meta", "_meta"):
                continue
            if isinstance(v, list) and len(v) > best_n:
                best_k, best_n = k, len(v)
        if best_n >= 0:
            return best_n, best_k
    return 0, ""


def _scan_file(rel):
    """Read one file -> (verdict, meta_or_None, bytes, count, count_of)."""
    path = os.path.join(DATA, rel.replace("/", os.sep))
    size = os.path.getsize(path)
    try:
        d = _load(path)
    except Exception:
        return "unlabelled", None, size, 0, ""
    m = _stamp_meta(d)
    count, count_of = _top_count(d)
    if m is None:
        return "unlabelled", None, size, count, count_of
    return _verdict_from_meta(m), m, size, count, count_of


def build():
    slugs = set(p.get("slug") for p in _load(os.path.join(DATA, INDEX_REL)))

    # ---- partition top-level *.json into standalone files vs geometry families ----
    fam_re = re.compile(r"^(?P<slug>.+)_(?P<kind>%s)$" % "|".join(FAMILY_KINDS))
    standalone = []          # rel paths
    families = {}            # kind -> [rel, ...]
    for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
        rel = os.path.basename(path)
        if rel == SELF:
            continue
        stem = rel[:-5]
        mm = fam_re.match(stem)
        if mm and mm.group("slug") in slugs:
            families.setdefault(mm.group("kind"), []).append(rel)
        else:
            standalone.append(rel)
    standalone.append(INDEX_REL)   # scan the province index too (mandate)

    layers = []
    unlabelled_files = []

    # ---- standalone layers (one file = one layer) ----
    for rel in standalone:
        cls, m, size, count, count_of = _scan_file(rel)
        if cls == "unlabelled":
            unlabelled_files.append(rel)
        layers.append({
            "file": rel, "family": False, "cls": cls,
            "label": _label_of(m) if m else "",
            "source": _source_of(m) if m else "",
            "vintage": _vintage_of(m) if m else "",
            "bytes": size, "count": count, "count_of": count_of,
            "n_files": 1, "n_unlabelled": 0 if cls != "unlabelled" else 1,
        })

    # ---- geometry families (many files = one collapsed layer) ----
    for kind in sorted(families):
        members = sorted(families[kind])
        tot_bytes = 0
        tot_count = 0
        n_unlab = 0
        member_cls = []
        srcs = Counter()
        vints = Counter()
        for rel in members:
            cls, m, size, count, count_of = _scan_file(rel)
            tot_bytes += size
            tot_count += count
            member_cls.append(cls)
            if cls == "unlabelled":
                n_unlab += 1
                unlabelled_files.append(rel)
            else:
                s = _source_of(m)
                if s:
                    srcs[s] += 1
                v = _vintage_of(m)
                if v:
                    vints[v] += 1
        labelled = [c for c in member_cls if c != "unlabelled"]
        if not labelled:
            fam_cls = "unlabelled"
        elif "estimated" in labelled:
            fam_cls = "estimated"
        else:
            fam_cls = "measured"
        # source/vintage: the most common member value (deterministic tie-break: alphabetical).
        src = sorted(srcs.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if srcs else ""
        vint = sorted(vints.items(), key=lambda kv: (-kv[1], kv[0]))[0][0] if vints else ""
        layers.append({
            "file": kind, "family": True, "cls": fam_cls,
            "label": KIND_LABEL.get(kind, kind),
            "source": src, "vintage": vint,
            "bytes": tot_bytes, "count": tot_count, "count_of": "features",
            "n_files": len(members), "n_unlabelled": n_unlab,
        })

    # shame board leads (unlabelled), then estimated, then measured; stable by file within.
    layers.sort(key=lambda L: (CLS_RANK[L["cls"]], L["file"]))
    unlabelled_files = sorted(unlabelled_files)

    n_files = sum(L["n_files"] for L in layers)
    n_files_unlab = len(unlabelled_files)
    counts = {
        "layers": len(layers),
        "measured": sum(1 for L in layers if L["cls"] == "measured"),
        "estimated": sum(1 for L in layers if L["cls"] == "estimated"),
        "unlabelled": sum(1 for L in layers if L["cls"] == "unlabelled"),
    }
    meta = {
        "generated_by": "pipeline/build_provenance.py (deterministic, network-free, --check)",
        "source": ("Provenance census of platform/data/*.json (+ provinces/index.json). For each "
                   "layer it reads the file's OWN meta stamp (label/source/provenance/generated_by), "
                   "byte size and top-level count. Nothing is invented."),
        "provenance": "measured (a listing of committed files); the per-layer verdict is read from each file's own meta text",
        "provenance_note": ("MEASURED / ESTIMATED are read from each layer's self-declared meta. "
                            "UNLABELLED = no readable meta stamp at all — the shame board; those files "
                            "ship a numeric layer with no provenance and should get a meta block. "
                            "Per-province geometry basemaps are collapsed into one 'family' row each, "
                            "but any unstamped member is still counted in files.unlabelled and named in "
                            "unlabelled_files, so collapsing hides no gap."),
    }
    return {
        "meta": meta,
        "counts": counts,
        "files": {"total": n_files, "unlabelled": n_files_unlab,
                  "labelled": n_files - n_files_unlab},
        "unlabelled_files": unlabelled_files,
        "layers": layers,
    }


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def run(check=False):
    text = canonical(build())
    if check:
        if not os.path.exists(OUT_PATH):
            print("DRIFT: platform/data/provenance.json missing — run build_provenance.py")
            return 1
        with open(OUT_PATH, encoding="utf-8") as f:
            if f.read() != text:
                print("DRIFT: platform/data/provenance.json differs from a fresh build")
                return 1
        print("OK: provenance.json reproduces exactly")
        return 0
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(text)
    d = json.loads(text)
    c = d["counts"]
    print("provenance.json written — %d layers (%d measured / %d estimated / %d unlabelled) · "
          "%d files, %d without a meta stamp"
          % (c["layers"], c["measured"], c["estimated"], c["unlabelled"],
             d["files"]["total"], d["files"]["unlabelled"]))
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Data-room provenance census for #home")
    ap.add_argument("--check", action="store_true",
                    help="verify committed provenance.json reproduces exactly; exit 1 on drift")
    raise SystemExit(run(check=ap.parse_args().check))
