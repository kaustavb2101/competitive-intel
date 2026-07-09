"""Validator (QA) — the committee's acceptance gate.
Every candidate change passes through here before it can be merged into the master.
Pure functions, no side effects; returns (accepted, rejected) with reasons.
"""
import math

THAILAND_BBOX = (5.5, 97.3, 20.5, 105.7)  # S, W, N, E

def haversine_km(a, b, c, d):
    R = 6371.0; p = math.pi / 180
    x = math.sin((c-a)*p/2)**2 + math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return 2 * R * math.asin(math.sqrt(x))

def in_thailand(lat, lng):
    s, w, n, e = THAILAND_BBOX
    return s <= lat <= n and w <= lng <= e

def gate_geocode(branch, candidate, max_shift_km=12.0, brand_token="ไชโย"):
    """Gate one geocoding upgrade.
    branch:    {code, name, lat, lng, prec, ...}   (current master record)
    candidate: {name, lat, lng, token, phone?, rating?}  (Geocoder proposal)
    Returns (ok: bool, reason: str, patch: dict|None)
    """
    if candidate is None:
        return False, "no candidate", None
    la, ln = candidate["lat"], candidate["lng"]
    if not in_thailand(la, ln):
        return False, "outside Thailand bbox", None
    if brand_token not in candidate.get("name", ""):
        return False, "brand token missing in result", None
    token = candidate.get("token", "")
    if token and token not in branch["name"]:
        return False, "name/token mismatch", None           # ambiguous match -> manual review
    shift = haversine_km(branch["lat"], branch["lng"], la, ln)
    if shift > max_shift_km:
        return False, f"shift {shift:.1f}km > {max_shift_km}km", None
    patch = {"code": branch["code"], "lat": round(la, 6), "lng": round(ln, 6),
             "prec": "places", "shift_km": round(shift, 2),
             "phone": candidate.get("phone"), "rating": candidate.get("rating"),
             "source": "google_places", "prev_prec": branch.get("prec")}
    return True, "ok", patch

def no_regression(scorecard_before, scorecard_after):
    """No headline metric may drop. Returns (ok, offending_metric|None)."""
    for k, v in scorecard_before.items():
        if isinstance(v, (int, float)) and k in scorecard_after:
            if scorecard_after[k] < v:
                return False, k
    return True, None

def run_batch_gate(branches_by_code, candidates_by_code, **kw):
    accepted, rejected = [], []
    for code, cand in candidates_by_code.items():
        b = branches_by_code.get(code)
        if not b:
            rejected.append((code, "unknown branch code")); continue
        ok, reason, patch = gate_geocode(b, cand, **kw)
        (accepted if ok else rejected).append(patch if ok else (code, reason))
    return accepted, rejected
