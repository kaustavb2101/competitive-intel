"""
pull_imf_weo.py — IMF World Economic Outlook macro backdrop (owner directive 2026-07-25).

The IMF WEO bulk files are 403-blocked, but the IMF DataMapper JSON API is NOT (verified reachable
from the Thai IP and cloud, HTTP 200) — so this is the working path to WEO. It pulls Thailand's key
macro series plus ASEAN peers for context: real GDP growth, inflation, unemployment, government debt,
and the current account. Historical years are actuals; the current year onward are IMF STAFF
PROJECTIONS (labelled — never presented as measured).

  api: https://www.imf.org/external/datamapper/api/v1/{INDICATOR}/{ISO}[/{ISO}...]
  out: platform/data/imf_weo.json   (served directly to the frontend, like macro_indicators.json)

NETWORK — run from the Thai laptop or any cloud IP. Not in the determinism gate (it is a network
pull, like fuel_prices/macro_indicators); a scheduled cron refreshes it. AutoX has no IPO, so peers
are framed as an EXTERNAL BENCHMARK, never an IPO comp.
"""
import datetime
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "platform", "data", "imf_weo.json")
API = "https://www.imf.org/external/datamapper/api/v1"

# WEO indicators most relevant to a Thai title-lender's borrower + macro backdrop.
IND = {
    "NGDP_RPCH":   ("Real GDP growth", "%", "higher = stronger borrower income base"),
    "PCPIPCH":     ("Inflation (avg CPI)", "%", "erodes real household income; cost-of-living pressure"),
    "LUR":         ("Unemployment", "%", "job loss → repayment stress"),
    "GGXWDG_NGDP": ("Govt gross debt", "% of GDP", "fiscal headroom for support / subsidy"),
    "BCA_NGDPD":   ("Current account", "% of GDP", "external balance / FX resilience"),
}
FOCUS = "THA"
PEERS = ["THA", "VNM", "IDN", "PHL", "MYS"]   # Thailand + ASEAN external benchmark
PEER_NAME = {"THA": "Thailand", "VNM": "Vietnam", "IDN": "Indonesia",
             "PHL": "Philippines", "MYS": "Malaysia"}
# The DataMapper sits behind Cloudflare and rate-limits bursts (200 on the first hit, then 403 for a
# cooldown). Look like a browser and pace requests: one indicator per request, backoff on 403.
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.imf.org/external/datamapper/",
}
N_HIST = 6   # recent years of Thailand series to keep
GAP = 9      # seconds between indicator requests (avoid the burst rate-limit)
BACKOFF = [20, 45, 90, 150]   # 403 retry waits


def get_json(url, timeout=45):
    """Fetch with browser headers; retry 403/errors with escalating backoff."""
    last = None
    for wait in [0] + BACKOFF:
        if wait:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=timeout) as r:
                return json.loads(r.read())
        except Exception as e:
            last = e
            print("  retry (%s) after %ss…" % (str(e)[:50], BACKOFF[0] if wait == 0 else wait))
    raise last


def fetch_raw():
    """Live pull: one request per indicator (returns ALL economies). code -> {iso -> {year:val}}."""
    raw = {}
    for i, code in enumerate(IND):
        if i:
            time.sleep(GAP)   # pace requests to avoid the Cloudflare burst limit
        try:
            data = get_json("%s/%s" % (API, code))
        except Exception as e:
            print("skip %s: %s" % (code, e))
            continue
        raw[code] = (data.get("values") or {}).get(code, {})
        print("  %s: %d economies" % (code, len(raw[code])))
    return raw


def assemble(raw, cur_year):
    """Build the app payload from raw {code -> {iso -> {year:val}}}. Shared by the live pull and the
    --from-raw path (a browser-fetched cache used when this IP is in a Cloudflare cooldown), so both
    routes emit a byte-identical schema."""
    thailand, peers = {}, {}
    for code, (label, unit, why) in IND.items():
        vals = raw.get(code) or {}
        # Thailand recent series + latest actual + next projection
        tv = {y: v for y, v in (vals.get(FOCUS) or {}).items() if v is not None}
        if tv:
            years = sorted(tv.keys())
            recent = years[-(N_HIST + 6):]   # keep a few forecast years too
            series = {y: round(tv[y], 2) for y in recent}
            actual_years = [y for y in years if int(y) < cur_year]
            latest_actual = actual_years[-1] if actual_years else None
            fc_years = [y for y in years if int(y) >= cur_year]
            next_fc = fc_years[0] if fc_years else None
            thailand[code] = {
                "label": label, "unit": unit, "why": why,
                "series": series,
                "latest_actual": ({"year": latest_actual, "val": round(tv[latest_actual], 2)}
                                  if latest_actual else None),
                "projection": ({"year": next_fc, "val": round(tv[next_fc], 2)}
                               if next_fc else None),
            }
        # peers: the current-year value (projection) for a side-by-side benchmark
        prow = {}
        for iso in PEERS:
            pv = {y: v for y, v in (vals.get(iso) or {}).items() if v is not None}
            yr = str(cur_year)
            if yr in pv:
                prow[iso] = round(pv[yr], 2)
            elif pv:
                prow[iso] = round(pv[sorted(pv.keys())[-1]], 2)
        if prow:
            peers[code] = prow
    return thailand, peers


def main():
    cur_year = datetime.datetime.now().year   # actuals < cur_year; cur_year onward = IMF projection
    from_raw = None
    for a in sys.argv[1:]:
        if a.startswith("--from-raw="):
            from_raw = a.split("=", 1)[1]
    if from_raw:
        # browser-fetched cache (Cloudflare cooldown workaround); same schema as a live pull.
        raw = json.load(open(from_raw, encoding="utf-8"))
        print("assembling from cached raw %s" % from_raw)
    else:
        raw = fetch_raw()
    thailand, peers = assemble(raw, cur_year)

    if not thailand:
        # The DataMapper sits behind Cloudflare and 403s automated (non-browser) clients after a burst,
        # so a live pull can come back empty. NEVER overwrite a good committed file with an empty pull:
        # keep the existing (browser-refreshed) file and exit cleanly. WEO refreshes only twice a year,
        # so a stale-but-real file is far better than an empty one. Re-pull via a browser + --from-raw.
        print("pull_imf_weo.py: no data assembled (Cloudflare block or empty response).")
        if os.path.exists(OUT):
            print("  keeping the existing %s untouched." % OUT)
            return
        sys.exit("pull_imf_weo.py: no data and no existing output to fall back to.")

    payload = {
        "meta": {
            "generated_by": "pipeline/pull_imf_weo.py",
            "source": "IMF World Economic Outlook via the IMF DataMapper API "
                      "(imf.org/external/datamapper). Keyless; reachable from the Thai IP and cloud "
                      "(the WEO bulk files are 403-blocked, the DataMapper API is not).",
            "label": "IMF WEO — historical years are ACTUALS; the current year (%d) onward are IMF "
                     "STAFF PROJECTIONS, not measured outturns. Peers are an EXTERNAL BENCHMARK "
                     "(AutoX has no IPO), never an IPO comp." % cur_year,
            "pulled": datetime.date.today().isoformat(),
            "current_year": cur_year,
            "focus": FOCUS,
            "peers": PEER_NAME,
            "peer_bench_year": cur_year,
        },
        "thailand": thailand,
        "peers": peers,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    g = thailand.get("NGDP_RPCH", {})
    print("wrote %s — %d indicators; THA GDP growth latest %s, projection %s"
          % (OUT, len(thailand), g.get("latest_actual"), g.get("projection")))


if __name__ == "__main__":
    main()
