#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rate_basis.py — the FLAT <-> EFFECTIVE (reducing-balance) bridge for advertised Thai vehicle rates.

WHY THIS EXISTS. Thai vehicle lending quotes two incompatible conventions, advertises them a
few pixels apart, and rarely says which one a headline number is:

  * ดอกเบี้ยคงที่ (FLAT) — interest is computed ONCE, on the full original principal, for the
    whole term, then split evenly across the instalments. You keep paying interest on money you
    have already repaid. SCB's own fine print: "ดอกเบี้ยในแต่ละงวดที่มีการคำนวณดอกเบี้ยครั้งเดียว
    จากเงินต้นเต็มจำนวน". This is the hire-purchase convention, and it is where the eye-catching
    "3.18% ต่อปี" headlines come from.
  * ลดต้นลดดอก (REDUCING BALANCE, published as "อัตราดอกเบี้ยที่แท้จริง") — interest accrues on
    the OUTSTANDING balance, so it falls as the loan amortises. This is the จำนำทะเบียน /
    title-loan convention, and it is the basis AutoX's own book is written on.

A flat 3.18%/yr and a reducing 12%/yr look nearly four times apart and are roughly the same
price. Putting both in one table without converting would not be a rough comparison, it would
be a wrong one — which is the entire reason this module exists.

THE CONVENTION, AND WHY IT IS NOT AN APR. "Effective" here means NOMINAL reducing-balance:
the monthly rate times twelve, NOT compounded. An APR/EIR would compound and read ~0.5pp higher
on the same loan. Nominal is (a) how AutoX's own book accrues — 23.99%/yr is charged as
rate/12 per month — and (b) what the Thai lenders themselves publish. CIMB prints
"0.83% - 1.56% ต่อเดือน ... หรือดอกเบี้ยลดต้นลดดอกระหว่าง 9.95% - 18.65% ต่อปี", and
0.83 x 12 = 9.96. Compounding instead would overstate every rival and make our own book look
cheap by comparison for no reason other than arithmetic convention.

VALIDATION IS AGAINST THE MARKET, NOT AGAINST OURSELVES. Several lenders publish BOTH numbers
of the pair, so this converter can be checked against figures we did not compute. PAIRS below
are those published pairs; `--selftest` (wired into tests/run.sh) asserts we reproduce each one.

The ttb pair is the clean anchor: flat 3.18 -> 5.93 and 8.70 -> 15.00 reproduce to 0.00 and
0.01pp, which is the evidence that the MODEL is right. The rest land within 0.33pp and the
residual runs BOTH ways, for reasons that are about quoting practice rather than arithmetic:
  * the lenders' "อัตราดอกเบี้ยที่แท้จริง" is inclusive of fees and ours is interest only,
    which pushes theirs UP relative to ours (TISCO, UOB);
  * we do not know which tenor each published pair was computed at — we assume the product's
    stated maximum, and a shorter one raises the effective figure;
  * a published RANGE's endpoints need not pair 1:1. SCB's flat band spans three vehicle-age
    buckets and its effective band spans the same three, but the cheapest flat and the
    cheapest effective are not obliged to be the same deal.
So the tolerance is symmetric and deliberately loose enough to admit all three effects. It is
checking that the method is sound, NOT that we can second-guess each lender's fee schedule.
Tightening it until every pair passed would be fitting the model to its own test.

TENOR IS REQUIRED, AND IT IS NOT FREE. The conversion needs the term: the same flat rate maps
to different effective rates over different tenors (flat 12%/yr is ~21.6% effective over 12
months but ~19.9% over 72). The effect is small for the low bank flat rates and material for
high ones, so an ad that quotes a flat rate with NO term cannot be converted honestly. Callers
get None and must render that as unconvertible rather than substituting a guess.

  python3 rate_basis.py --selftest
"""
import argparse
import re
import sys

# The bisection bracket for the monthly reducing-balance rate. 0 to 100%/month covers every
# rate that could lawfully be advertised (the BoT ceiling on this product is 24%/yr) with room
# to spare, and a fixed iteration count makes the result bit-identical on every platform —
# this feeds a byte-compared layer, so "close enough" is not enough.
_LO, _HI, _ITERS = 1e-12, 1.0, 200

# ---------------------------------------------------------------------------
# The published pairs. Each is a lender printing BOTH bases for the same product, so it is
# evidence we did not generate. `months` is that product's own stated maximum tenor, which is
# the term these tables are quoted at.
PAIRS = [
    # (lender, flat %/yr, lender's own stated effective %/yr, months, citation)
    ("ttb DRIVE รถแลกเงิน (โอนเล่ม), floor",  3.18,  5.93, 72,
     "https://www.checkraka.com/personalloan/ttb/1455109/"),
    ("ttb DRIVE รถแลกเงิน (โอนเล่ม), ceiling", 8.70, 15.00, 72,
     "https://www.checkraka.com/personalloan/ttb/1455109/"),
    ("CIMB Thai Auto รถปลดล็อก (โอนเล่ม), floor",   2.95,  5.40, 72,
     "https://www.cimbthaiauto.com/product/autocash"),
    ("CIMB Thai Auto รถปลดล็อก (โอนเล่ม), ceiling", 8.87, 15.00, 72,
     "https://www.cimbthaiauto.com/product/autocash"),
    ("SCB My Car My Cash, 2026-2021 floor",   2.99,  5.47, 84,
     "https://www.scb.co.th/th/personal-banking/loans/car-loans/my-car-my-cash"),
    ("SCB My Car My Cash, 2015-2011 ceiling", 8.65, 15.00, 84,
     "https://www.scb.co.th/th/personal-banking/loans/car-loans/my-car-my-cash"),
    ("UOB Car2Cash online promo", 6.00, 10.99, 72,
     "https://www.uob.co.th/personal/loans/cartocash/loans-cartocash.page"),
    ("TISCO Auto Cash floor",  7.08, 12.64, 72,
     "https://www.checkraka.com/personalloan/tisco/1435861/"),
]
# Symmetric, and sized to the three quoting effects in the module note — not to whatever makes
# the current eight pairs pass. A miss beyond this is a real modelling break: at 0.5pp the
# comparison still decides every question this board is asked, since the gap between a flat and
# an effective quote of the same product is 5-10pp, twenty times the tolerance.
TOL = 0.5


def _round2(x):
    """Half-up to 2dp, without float-repr surprises.

    Python's round() is banker's rounding on binary floats, so round(2.675, 2) is 2.67 and the
    same input can land either side of a .005 boundary depending on the platform's libm. This
    output is byte-compared by --check, so the boundary is resolved explicitly instead.
    """
    if x is None:
        return None
    neg = x < 0
    x = abs(x)
    v = int(x * 1000.0 + 0.5)          # to 3dp as an integer, half-up
    v = (v + 5) // 10                  # then 3dp -> 2dp, half-up again
    out = v / 100.0
    return -out if neg else out


def flat_to_effective(flat_pct_year, months):
    """FLAT %/yr -> NOMINAL reducing-balance %/yr over `months`. None if unconvertible.

    A flat loan's instalment is fixed by construction: total = principal + principal*f*years,
    paid in `months` equal parts. The effective rate is the monthly rate that discounts THAT
    instalment stream back to the principal — i.e. the loan's IRR — times twelve.
    """
    if flat_pct_year is None or months is None:
        return None
    try:
        f, n = float(flat_pct_year) / 100.0, int(months)
    except (TypeError, ValueError):
        return None
    if n <= 0 or f < 0:
        return None
    if f == 0:
        return 0.0
    total = 1.0 + f * (n / 12.0)       # principal 1.0 + all the flat interest
    pay = total / n
    if pay * n <= 1.0:                 # no interest to solve for
        return 0.0
    lo, hi = _LO, _HI
    for _ in range(_ITERS):            # fixed count -> identical on every platform
        mid = (lo + hi) / 2.0
        # present value of the instalment stream at monthly rate `mid`
        pv = pay * (1.0 - (1.0 + mid) ** (-n)) / mid
        if pv > 1.0:                   # discounting too little -> rate is higher
            lo = mid
        else:
            hi = mid
    return _round2((lo + hi) / 2.0 * 12.0 * 100.0)


def effective_to_flat(eff_pct_year, months):
    """NOMINAL reducing-balance %/yr -> the FLAT %/yr that produces the same instalment.

    The inverse of the above, and the direction needed to answer "what would a title lender's
    12%/yr look like if it were advertised the way a hire-purchase deal is".
    """
    if eff_pct_year is None or months is None:
        return None
    try:
        e, n = float(eff_pct_year) / 100.0, int(months)
    except (TypeError, ValueError):
        return None
    if n <= 0 or e < 0:
        return None
    if e == 0:
        return 0.0
    i = e / 12.0
    pay = i / (1.0 - (1.0 + i) ** (-n))          # amortising instalment on principal 1.0
    interest = pay * n - 1.0
    return _round2(interest / (n / 12.0) * 100.0)


def per_month_to_per_year(pct_month):
    """A monthly rate to its annual NOMINAL equivalent — x12, never compounded.

    Both bases stay on the same footing this way, which is the only reason a monthly and an
    annual quote can sit in one column at all. See the module note on why this is not an APR.
    """
    if pct_month is None:
        return None
    try:
        return _round2(float(pct_month) * 12.0)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# READING THE FINE PRINT.
#
# These classify what an ad or a factsheet SAYS about its own basis. They never infer: a rate
# whose basis is not written down comes back None, because inferring it is precisely the error
# the whole module exists to prevent. Ordered longest-cue-first so "ดอกเบี้ยคงที่" is not
# matched by a stray "คงที่" inside a different clause.
FLAT_CUES = ("ดอกเบี้ยคงที่", "อัตราดอกเบี้ยคงที่", "ดอกเบี้ยแบบคงที่", "แบบคงที่",
             "เทียบเท่าดอกเบี้ยคงที่", "อัตราคงที่", "flat rate", "flat interest")
EFF_CUES = ("ลดต้นลดดอก", "อัตราดอกเบี้ยที่แท้จริง", "ดอกเบี้ยที่แท้จริง", "แบบลดต้นลดดอก",
            "effective rate", "effective interest", "reducing balance", "eir")
# "คงที่" alone is ambiguous — it also describes a fixed (non-floating) reducing-balance rate,
# e.g. "อัตราดอกเบี้ยคงที่ตลอดอายุสัญญา". Only counted when no reducing-balance cue is present.
WEAK_FLAT = ("คงที่",)


def basis_kind_in(text):
    """'flat' | 'effective' | None — what the text SAYS its basis is. Never inferred.

    When a line states both (the lenders that publish the pair do exactly this) the reducing-
    balance reading wins, because such a line is always "flat X, equivalent to reducing Y" and
    Y is the comparable number.
    """
    if not text:
        return None
    t = text.lower()
    has_eff = any(c in t for c in EFF_CUES)
    has_flat = any(c in t for c in FLAT_CUES)
    if has_eff:
        return "effective"
    if has_flat:
        return "flat"
    if any(c in t for c in WEAK_FLAT):
        return "flat"
    return None


# ผ่อนนาน 84 เดือน / สูงสุด 72 งวด / ผ่อน 12-84 เดือน — the TERM, in months.
_TENOR_RE = re.compile(r"(\d{1,3})\s*(?:-\s*(\d{1,3})\s*)?(?:เดือน|งวด|months?)")
_TENOR_CUE = ("ผ่อน", "งวด", "นาน", "ระยะเวลา", "เดือน", "tenor", "month")


def tenor_in(text):
    """Longest stated term in months, or None. The longest is the one being advertised.

    Bounded to 6..120 months: below that the number is an instalment count in a different
    sense (or a "3 เดือนแรก" teaser), above it, it is not a vehicle loan.
    """
    if not text or not any(c in text.lower() for c in _TENOR_CUE):
        return None
    best = None
    for m in _TENOR_RE.finditer(text):
        for g in (m.group(2), m.group(1)):     # prefer the top of a stated range
            if not g:
                continue
            try:
                v = int(g)
            except ValueError:
                continue
            if 6 <= v <= 120 and (best is None or v > best):
                best = v
            break
    return best


# วงเงินสูงสุด 120% ของราคาประเมิน — the LTV.
#
# The lookbehind is load-bearing: without it `\d{1,3}\s*%` happily matches the "66" inside
# "0.66%", and Srisawad's monthly INTEREST RATE was being published as a 66% advance rate.
# A percentage that is part of a decimal is never an LTV.
_LTV_RE = re.compile(r"(?<![\d.])(\d{1,3})\s*%")
_LTV_CUE = ("ราคาประเมิน", "ราคากลาง", "วงเงิน", "มูลค่ารถ", "appraised", "valuation", "ltv")
# A rate cue near the number means the number prices the loan rather than sizing it.
_LTV_NOT = ("ดอกเบี้ย", "ลดต้นลดดอก", "อัตรา", "คงที่", "อนุมัติ", "interest", "rate")
_LTV_WINDOW = 34


def _nearest_cue(before, cues):
    """Distance from the end of `before` back to the closest of `cues`, or None."""
    best = None
    for c in cues:
        i = before.rfind(c)
        if i >= 0:
            d = len(before) - i
            if best is None or d < best:
                best = d
    return best


def ltv_in(text):
    """Stated loan-to-value as a percent of appraised vehicle value, or None.

    Cues are tested in a WINDOW around each candidate number, not across the whole text. Ad
    copy is a collage of unrelated claims — "ดอกเบี้ยเริ่มต้น 0.66% ... ให้วงเงินสูง" carries a
    rate and a valuation cue in one blob — so a whole-text test either accepts the rate as an
    LTV or rejects the LTV because a rate is present elsewhere. Both happened.

    Takes the MAXIMUM stated, which is what the ad is claiming. Bounded to 30..200%: this
    market genuinely lends above appraised value (Tidlor advertises 160%, SCB's card says
    140%, ttb 120%), so capping at 100 would discard the most aggressive offers — exactly the
    ones worth seeing.
    """
    if not text:
        return None
    best = None
    for m in _LTV_RE.finditer(text):
        try:
            v = int(m.group(1))
        except ValueError:
            continue
        if not (30 <= v <= 200):
            continue
        # Thai puts the qualifier BEFORE the number — "วงเงิน 140%", "ดอกเบี้ย 0.66%" — so the
        # cue that governs this number is whichever kind appears closest to its left. A rate
        # cue further back does not disqualify an LTV that is stated right against the number,
        # which is what a symmetric window got wrong in both directions.
        before = text[max(0, m.start() - _LTV_WINDOW):m.start()].lower()
        d_ltv = _nearest_cue(before, _LTV_CUE)
        if d_ltv is None:
            continue
        d_not = _nearest_cue(before, _LTV_NOT)
        if d_not is not None and d_not < d_ltv:
            continue
        if best is None or v > best:
            best = v
    return best


# ---------------------------------------------------------------------------
def selftest(verbose=True):
    """Assert the converter reproduces rates the LENDERS published, not rates we invented."""
    bad = 0
    for name, flat, stated, months, cite in PAIRS:
        got = flat_to_effective(flat, months)
        delta = got - stated
        okay = abs(delta) <= TOL
        if not okay:
            bad += 1
        if verbose:
            print("%-46s flat %5.2f -> %6.2f  lender says %6.2f  (%+.2f) %s"
                  % (name, flat, got, stated, delta, "ok" if okay else "FAIL"))
    # The inverse must land back where it started, or the two directions disagree and the
    # board would contradict itself depending on which way a row happened to be computed.
    for eff, months in ((12.0, 72), (18.0, 60), (23.99, 48), (9.95, 72)):
        flat = effective_to_flat(eff, months)
        back = flat_to_effective(flat, months)
        if abs(back - eff) > 0.05:
            bad += 1
            if verbose:
                print("round-trip FAIL: %.2f%%/yr eff -> %.2f flat -> %.2f eff"
                      % (eff, flat, back))
        elif verbose:
            print("round-trip ok: %5.2f%%/yr eff -> %5.2f%% flat -> %5.2f%%/yr eff over %d mo"
                  % (eff, flat, back, months))
    # The unconvertible cases must stay unconvertible rather than defaulting to something.
    for args in ((3.99, None), (None, 60), (3.99, 0), (3.99, -12)):
        if flat_to_effective(*args) is not None:
            bad += 1
            if verbose:
                print("FAIL: %r should be unconvertible" % (args,))
    # The fine-print readers, including the cases they must REFUSE.
    cases = [
        (basis_kind_in, "ดอกเบี้ยคงที่ 3.18% ต่อปี", "flat"),
        (basis_kind_in, "อัตราดอกเบี้ยลดต้นลดดอก 12% ต่อปี", "effective"),
        (basis_kind_in, "3.18% ต่อปี เทียบเท่าดอกเบี้ยลดต้นลดดอก 5.93% ต่อปี", "effective"),
        (basis_kind_in, "ดอกเบี้ยเริ่มต้น 0.66% ต่อเดือน", None),
        (basis_kind_in, "", None),
        (tenor_in, "ผ่อนนานสูงสุด 84 เดือน", 84),
        (tenor_in, "ผ่อน 12-72 งวด", 72),
        (tenor_in, "ดอกเบี้ย 3.18% ต่อปี", None),
        (ltv_in, "วงเงินสูงสุด 120% ของราคาประเมิน", 120),
        (ltv_in, "อนุมัติ 100% ทุกอาชีพ", None),
        (ltv_in, "ดอกเบี้ย 100% ลดต้นลดดอก", None),
        (ltv_in, "ให้วงเงินสูงสุด 160%", 160),
        # The regression that shipped a 66% advance rate for Srisawad: the "66" of "0.66%"
        # matched, and "วงเงิน" elsewhere in the same blob waved it through.
        (ltv_in, "ให้วงเงินสูง ดอกเบี้ยเริ่มต้น 0.66% ต่อเดือน", None),
        (ltv_in, "วงเงิน 140% ของราคาประเมิน ดอกเบี้ยคงที่ 2.99% ต่อปี", 140),
    ]
    for fn, arg, want in cases:
        got = fn(arg)
        if got != want:
            bad += 1
            if verbose:
                print("FAIL %s(%r) = %r, want %r" % (fn.__name__, arg, got, want))
    if verbose:
        print("\n%d published pair(s) + %d reader case(s): %s"
              % (len(PAIRS), len(cases), "ALL OK" if not bad else "%d FAILED" % bad))
    return bad


if __name__ == "__main__":
    # The pair labels are Thai product names and Windows consoles default to cp1252, which
    # raises UnicodeEncodeError mid-report and turns a passing selftest into a fake failure.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    sys.exit(1 if selftest(verbose=True) else 0)
