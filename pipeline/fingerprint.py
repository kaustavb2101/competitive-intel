"""fingerprint.py — shared branches-index fingerprint (tamper-evident alignment).

Several platform/data layers are INDEX-ALIGNED to branches.json (entry i <-> branch i).
A length check alone cannot catch a REORDERED or partially-swapped branches.json — the
layers would still be the right length but silently describe the WRONG branches. This
helper gives every builder one canonical fingerprint of the branch ORDER + IDENTITY:

    branches_fingerprint = sha256 hex over the ordered [[x, y, n], ...] sequence,
    serialized with json.dumps(separators=(",", ":"), ensure_ascii=False), utf-8.

derive.py stamps it into platform/data/meta.json; every index-aligned builder stamps
the CURRENT value into its own output meta as `branches_fingerprint`. The validator
(tests/validate_data.py) recomputes it independently and fails any layer whose stamp
does not match — "stale layer — re-run its builder".
"""
import hashlib
import json
import os

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRANCHES_PATH = os.path.join(_REPO, "platform", "data", "branches.json")


def branches_fingerprint(branches):
    """sha256 hex of the ordered (x, y, n) identity sequence of branch records."""
    seq = [[b["x"], b["y"], b["n"]] for b in branches]
    blob = json.dumps(seq, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def branches_fingerprint_from_file(path=BRANCHES_PATH):
    """Fingerprint of the committed platform/data/branches.json (or another path)."""
    with open(path, encoding="utf-8") as f:
        return branches_fingerprint(json.load(f))
