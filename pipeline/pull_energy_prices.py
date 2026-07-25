"""
pull_energy_prices.py — crude-oil price baseline for the income engine's fuel channel (2026-07-25).

Owner directive: the income-impact engine's fuel driver was 0 because the committed retail-diesel
layer is a same-day snapshot with no baseline to diff. The fuel move should use "the beginning of
the year, or the same comparison period as crops." The crop drivers are World Bank Pink Sheet YoY,
so this pulls the SAME workbook's ENERGY section — crude oil — and computes both a 12-month YoY (to
match the crops exactly) and a year-to-date move (vs January of the current year). MEASURED, same
source and period as the crop drivers.

NETWORK — run from the Thai laptop / any cloud IP (thedocs.worldbank.org is reachable). Writes the
COMMITTED source-data/energy_prices.json that the deterministic, network-free build_income_impact.py
then reads. Global crude is a proxy for the Thai borrower's fuel cost: Thai retail diesel is
subsidy/fund-buffered, so pass-through is partial — the income engine labels it as such (the crop
drivers carry the identical global-proxy caveat).

  out: source-data/energy_prices.json   {crude_avg:{latest,date,yoy,ytd,jan_ref}, ...}
"""
import json
import os
import re
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "pipeline", ".cache")
OUT = os.path.join(ROOT, "source-data", "energy_prices.json")

# Same Pink Sheet workbook that feeds the crop drivers (autox_enrich_loop.stage_commodities).
PINKSHEET_PAGE = "https://www.worldbank.org/en/research/commodity-markets"
PINKSHEET = ("https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/"
             "related/CMO-Historical-Data-Monthly.xlsx")
# Preference order of crude columns (the "Monthly Prices" sheet has several).
CRUDE_COLS = ["Crude oil, average", "Crude oil, Brent", "Crude oil, Dubai", "Crude oil, WTI"]
UA = {"User-Agent": "Mozilla/5.0 (AutoX energy-baseline puller)"}


def get(url, timeout=120):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout).read()


def pinksheet_url():
    """Scrape the current CMO xlsx link off the landing page; fall back to the known hash."""
    try:
        html = get(PINKSHEET_PAGE, 60).decode("utf-8", "ignore")
        m = re.findall(r'https?://[^\s"\'<>]*CMO-Historical-Data-Monthly\.xlsx', html)
        if m:
            return m[0]
    except Exception:
        pass
    return PINKSHEET


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def main():
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "pinksheet.xlsx")
    if "--use-cache" not in sys.argv or not os.path.exists(path):
        print("downloading Pink Sheet workbook…")
        open(path, "wb").write(get(pinksheet_url(), 180))
    import openpyxl
    ws = openpyxl.load_workbook(path, read_only=True, data_only=True)["Monthly Prices"]
    rows = [list(r) for r in ws.iter_rows(values_only=True)]
    hdr = rows[4]
    data = rows[6:]

    # locate the first available crude column
    col = None
    label = None
    for want in CRUDE_COLS:
        for j, n in enumerate(hdr):
            if n and str(n).strip() == want:
                col, label = j, want
                break
        if col is not None:
            break
    if col is None:
        sys.exit("pull_energy_prices.py: no crude-oil column found in the Pink Sheet header.")

    series = [num(r[col]) for r in data]
    dates = [str(r[0]) for r in data]
    li = max(i for i in range(len(series)) if series[i] is not None)
    latest, latest_date = series[li], dates[li]
    # 12-month YoY (identical method to the crop drivers)
    yi = li - 12
    yoy = round(100 * (latest - series[yi]) / series[yi], 1) if yi >= 0 and series[yi] else None
    # year-to-date: vs the first month of the latest year present (e.g. "2026M01")
    year = latest_date[:4]
    jan_idx = next((i for i in range(len(dates)) if dates[i].startswith(year) and series[i] is not None), None)
    jan_ref = series[jan_idx] if jan_idx is not None else None
    jan_date = dates[jan_idx] if jan_idx is not None else None
    ytd = round(100 * (latest - jan_ref) / jan_ref, 1) if jan_ref else None

    payload = {
        "meta": {
            "generated_by": "pipeline/pull_energy_prices.py",
            "source": "World Bank Pink Sheet — CMO-Historical-Data-Monthly.xlsx, 'Monthly Prices' "
                      "sheet (thedocs.worldbank.org). Same workbook and YoY method as the crop drivers.",
            "label": "MEASURED — global crude-oil price (World Bank Pink Sheet). Used as the income "
                     "engine's fuel-cost driver, same source and period as the crop drivers. Global "
                     "crude is a PROXY for the Thai borrower's fuel cost — Thai retail diesel is "
                     "subsidy/fund-buffered, so pass-through is partial (the crop drivers carry the "
                     "same global-proxy caveat).",
            "column": label,
            "unit": "USD/bbl",
            "vintage": latest_date,
        },
        "crude_avg": {
            "latest": round(latest, 3), "date": latest_date,
            "yoy": yoy, "ytd": ytd, "jan_ref": (round(jan_ref, 3) if jan_ref else None),
            "jan_date": jan_date,
        },
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    print("wrote %s — %s %s = %.2f USD/bbl, YoY %s%%, YTD %s%% (vs %s)"
          % (OUT, label, latest_date, latest, yoy, ytd, jan_date))


if __name__ == "__main__":
    main()
