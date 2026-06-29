#!/usr/bin/env python3
"""Mean per-pixel difference between two PNGs (pure stdlib, reuses pixvar's decoder).

Used for visual regression: a fresh render vs the committed baseline. Software-WebGL renders are
near-deterministic but not bit-identical (sub-pixel AA), so we compare with a tolerance rather than
byte equality. Prints the mean absolute RGB difference per pixel (0-255).

Usage: diffpng.py <a.png> <b.png>  -> prints JSON {mean_diff,max_dim_mismatch}
Exit 0 always; caller thresholds.
"""
import sys, json, os
sys.path.insert(0, os.path.dirname(__file__))
from pixvar import read_png  # noqa: E402


def main():
    aw, ah, ac, ap = read_png(sys.argv[1])
    bw, bh, bc, bp = read_png(sys.argv[2])
    if (aw, ah) != (bw, bh):
        print(json.dumps({"mean_diff": 255.0, "dim_mismatch": True,
                          "a": [aw, ah], "b": [bw, bh]}))
        return
    step = max(1, int(((aw * ah) / 40000) ** 0.5))
    tot = 0
    n = 0
    for y in range(0, ah, step):
        for x in range(0, aw, step):
            ia = (y * aw + x) * ac
            ib = (y * bw + x) * bc
            tot += abs(ap[ia] - bp[ib]) + abs(ap[ia + 1] - bp[ib + 1]) + abs(ap[ia + 2] - bp[ib + 2])
            n += 3
    print(json.dumps({"mean_diff": round(tot / max(1, n), 3), "dim_mismatch": False}))


if __name__ == "__main__":
    main()
