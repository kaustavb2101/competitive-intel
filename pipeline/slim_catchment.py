#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
slim_catchment.py — shrink the committed 3D catchment JSONs for faster mobile load, with ZERO
visual change beyond <=1m coordinate rounding.

WHAT IT DOES (per building in platform/data/<city>_catchment.json):
  - quantize polygon vertex coords to 5 decimals (~1.1m) and cx/cy centroid to 5 decimals
  - round height h to 0.1m
  - DROP the `nm` field entirely — it is always "" and the scene never reads a building name
    (buildings are non-interactive scenery; rayong-catchment.html reads only p/h/fa/cx/cy/ty)
  - DROP `ty` when it is "mixed" or "house" — the renderer treats those (and absent ty) identically
    (`b.ty && b.ty!=='mixed' && b.ty!=='house' ? TINT[...] : null`), so this is behaviour-preserving
  - re-emit MINIFIED (no indent, compact separators)
Building COUNT and ORDER are never changed — the footprint set is identical, only lighter.

  python3 slim_catchment.py            # slim the committed catchments in place
  python3 slim_catchment.py --check    # verify they are already slimmed (idempotent, byte-exact)

--check re-runs the transform on each committed file and asserts it is a no-op (byte-identical),
so the gate proves the committed files are canonical-slim and reproducible. Skip-passes cleanly if a
target file is absent.
"""
import os, sys, json, argparse

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TARGETS = ["rayong_catchment.json", "bangkok_catchment.json"]

def q5(v):
    # round to 5 decimals; return int when whole to shave the ".0"
    r = round(float(v), 5)
    return int(r) if r == int(r) else r

def slim_building(b):
    out = {}
    # polygon: list of [lng,lat] rings-of-points (single ring in these files)
    p = b.get("p")
    if p is not None:
        out["p"] = [[q5(pt[0]), q5(pt[1])] for pt in p]
    if "h" in b and b["h"] is not None:
        h = round(float(b["h"]), 1)
        out["h"] = int(h) if h == int(h) else h
    if "fa" in b and b["fa"] is not None:
        out["fa"] = int(b["fa"])
    if "cx" in b and b["cx"] is not None:
        out["cx"] = q5(b["cx"])
    if "cy" in b and b["cy"] is not None:
        out["cy"] = q5(b["cy"])
    ty = b.get("ty")
    if ty and ty not in ("mixed", "house"):      # drop the render-default types (behaviour-identical)
        out["ty"] = ty
    return out

def slim_payload(d):
    b = d.get("buildings")
    if not isinstance(b, list):
        return None            # not a catchment building file we understand -> leave alone
    out = dict(d)              # preserve center + any other top-level keys verbatim
    out["buildings"] = [slim_building(x) for x in b]
    return out

def dumps(d):
    return json.dumps(d, ensure_ascii=False, separators=(",", ":"))

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    any_drift = False
    for name in TARGETS:
        path = os.path.join(ROOT, "platform", "data", name)
        if not os.path.exists(path):
            print(f"skip {name}: absent")
            continue
        raw = open(path, encoding="utf-8").read()
        d = json.loads(raw)
        slim = slim_payload(d)
        if slim is None:
            print(f"skip {name}: not a building-catchment shape")
            continue
        new = dumps(slim)
        if a.check:
            # canonical form = slim(current). Assert current file already equals it byte-for-byte.
            if raw != new:
                # allow a re-slim to converge (idempotency): slim(slim) must equal slim
                if dumps(slim_payload(json.loads(new))) != new:
                    print(f"[FAIL] {name}: slim is not idempotent"); any_drift = True
                else:
                    print(f"[DRIFT] {name}: committed file is not the slim canonical form "
                          f"(run: python3 pipeline/slim_catchment.py)"); any_drift = True
            else:
                print(f"[ok] {name}: already slim ({len(raw)/1048576:.1f} MB)")
        else:
            before = len(raw) / 1048576
            with open(path, "w", encoding="utf-8") as f:
                f.write(new)
            after = len(new) / 1048576
            n = len(slim["buildings"])
            print(f"{name}: {before:.1f} -> {after:.1f} MB ({100*(1-after/before):.0f}% smaller, {n} buildings)")
    if a.check and any_drift:
        sys.exit(1)

if __name__ == "__main__":
    main()
