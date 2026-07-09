#!/usr/bin/env bash
# Headless render of one platform/ page, fully offline except npm (CDNs are proxy-blocked).
#
# Generalised, repo-relative version of the scratchpad reference harness. It:
#   1. vendors the npm-installed deck.gl/leaflet bundles into platform/_qa_vendor/
#   2. makes a temp copy of the page with the unpkg CDN <script>/<link> refs sed-swapped to the
#      local bundles, AND a small probe script injected that captures uncaught errors + whether the
#      GL/Leaflet lib initialised, exposing both on window for the DOM dump to read back
#   3. serves platform/ over http (so the page's fetch('data/…') works)
#   4. screenshots headless with software WebGL (swiftshader)
#   5. dumps the settled DOM and greps the probe state out of it -> <out>.report.json
#   6. cleans up the temp copy + vendor dir
#
# Basemap raster tiles (cartocdn) stay blocked -> blank basemap. Expected. Geometry still renders.
#
# Usage: render.sh <page-with-optional-query> <out.png> [budget_ms] [WxH]
#   e.g. render.sh 'province.html?p=rayong' /path/out.png 12000 1100,800
set -u

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TESTS="$(dirname "$HERE")"
REPO="$(dirname "$TESTS")"
PLATFORM="$REPO/platform"
CACHE="$TESTS/.cache/node_modules"

PAGEQ="$1"; OUT="$2"; BUDGET="${3:-12000}"; SIZE="${4:-1100,800}"
PAGE="${PAGEQ%%[?#]*}"          # strip ?query / #hash for the filename
QUERY=""
case "$PAGEQ" in *[\?#]*) QUERY="${PAGEQ#"$PAGE"}";; esac

if [ ! -f "$CACHE/deck.gl/dist.min.js" ]; then
  echo "FATAL: deps not installed. Run: tests/run.sh (or 'cd tests && npm install --prefix .cache')" >&2
  exit 2
fi
if [ ! -f "$PLATFORM/$PAGE" ]; then
  echo "FATAL: no such page: platform/$PAGE" >&2
  exit 2
fi

VENDOR="$PLATFORM/_qa_vendor"
mkdir -p "$VENDOR"
cp "$CACHE/deck.gl/dist.min.js"     "$VENDOR/deckgl.min.js"
cp "$CACHE/leaflet/dist/leaflet.js"  "$VENDOR/leaflet.js" 2>/dev/null || true
cp "$CACHE/leaflet/dist/leaflet.css" "$VENDOR/leaflet.css" 2>/dev/null || true

TMP="$PLATFORM/_qa_$(basename "$PAGE")"

# Probe injected just after <head>. It creates a hidden #__qa node SYNCHRONOUSLY at parse time
# (appended to documentElement — <body> isn't parsed yet) so chrome --dump-dom (which serialises the
# live DOM, not the JS heap) is guaranteed to see it. An interval + the error listeners then update
# its attributes: captured uncaught errors, and whether deck/Leaflet actually initialised.
PROBE='<script>(function(){var of=window.fetch;window.fetch=function(u,o){var s=(typeof u==="string")?u:(u&&u.url)||"";if(/^https?:\/\//i.test(s)&&s.indexOf(location.origin)!==0){return Promise.reject(new TypeError("qa-blocked cross-origin fetch: "+s));}return of.apply(this,arguments);};var d=document.createElement("meta");d.id="__qa";d.setAttribute("data-errors","[]");d.setAttribute("data-deck","0");d.setAttribute("data-leaflet","0");document.head.appendChild(d);window.__qaErr=[];function w(){try{d.setAttribute("data-errors",JSON.stringify(window.__qaErr));d.setAttribute("data-deck",(typeof deck!=="undefined"&&!!deck.DeckGL)?"1":"0");d.setAttribute("data-leaflet",(typeof L!=="undefined"&&!!L.map)?"1":"0");}catch(e){}}window.addEventListener("error",function(e){window.__qaErr.push(String(e.message||(e.error&&e.error.message)||e));w();});window.addEventListener("unhandledrejection",function(e){window.__qaErr.push("reject:"+String((e.reason&&e.reason.message)||e.reason));w();});window.addEventListener("load",w);setInterval(w,400);})();</script>'

# Swap CDN refs -> local bundles (these target strings contain no sed-special chars, so sed is safe).
sed -e 's#https://unpkg.com/deck.gl@8.9.35/dist.min.js#_qa_vendor/deckgl.min.js#g' \
    -e 's#https://unpkg.com/leaflet@1.9.4/dist/leaflet.js#_qa_vendor/leaflet.js#g' \
    -e 's#https://unpkg.com/leaflet@1.9.4/dist/leaflet.css#_qa_vendor/leaflet.css#g' \
    "$PLATFORM/$PAGE" > "$TMP"
# Inject the probe via python LITERAL replacement — the probe contains '&' which sed would expand
# to the matched text, corrupting the script. Python str.replace has no such footgun.
PROBE="$PROBE" python3 - "$TMP" <<'PY'
import os, sys
p = sys.argv[1]
probe = os.environ["PROBE"]
s = open(p, encoding="utf-8", errors="ignore").read()
s = s.replace("<head>", "<head>" + probe, 1)
open(p, "w", encoding="utf-8").write(s)
PY

PORT=$((8700 + RANDOM % 250))
# Launch the static server directly (not in a subshell) so $! is the python PID we can later kill.
python3 -m http.server "$PORT" --directory "$PLATFORM" >/dev/null 2>&1 &
SRV=$!
trap 'kill $SRV 2>/dev/null; rm -f "$TMP"; rm -rf "$VENDOR"' EXIT INT TERM
# wait for the server to answer instead of a fixed sleep (determinism)
for _ in $(seq 1 40); do
  if curl -s -o /dev/null "http://localhost:$PORT/" 2>/dev/null; then break; fi
  sleep 0.25
done

CHROME=$(ls -d /opt/pw-browsers/chromium-*/chrome-linux/chrome 2>/dev/null | head -1)
if [ -z "$CHROME" ]; then echo "FATAL: no chromium under /opt/pw-browsers" >&2; exit 2; fi

URL="http://localhost:$PORT/_qa_$(basename "$PAGE")$QUERY"
# hard wall: each chrome pass gets (budget + 20s) wall time so a wedged swiftshader can't stall CI.
WALL=$(( BUDGET / 1000 + 20 ))
CHROME_FLAGS=(--headless=new --no-sandbox --disable-gpu --use-gl=angle --use-angle=swiftshader \
        --enable-unsafe-swiftshader --hide-scrollbars --window-size="$SIZE" \
        --virtual-time-budget="$BUDGET")

# Under software WebGL the heaviest scene (rayong-catchment, 3,631 buildings) intermittently makes
# a single chrome pass come back empty within the wall — the screenshot pass occasionally produces
# NO png, and the DOM-dump pass occasionally returns an EMPTY string — even though the page is fine.
# Both passes therefore RETRY until they yield real output (treat empty as "retry", not "fail").
# Each attempt gets its own fresh user-data-dir so a wedged profile can't poison the next try; this
# stays fully deterministic (no network, fixed virtual-time budget).
for try in 1 2 3 4; do
  rm -f "$OUT"
  SDD="$(mktemp -d)"
  timeout "$WALL" "$CHROME" "${CHROME_FLAGS[@]}" --user-data-dir="$SDD" \
          --screenshot="$OUT" "$URL" >/dev/null 2>&1 || true
  rm -rf "$SDD"
  # accept once a non-empty png exists.
  [ -s "$OUT" ] && break
done
# second pass: dump the settled DOM so the probe state (errors + lib init) is readable.
DOM=""
for try in 1 2 3 4; do
  TDD="$(mktemp -d)"
  DOM="$(timeout "$WALL" "$CHROME" "${CHROME_FLAGS[@]}" --user-data-dir="$TDD" \
          --dump-dom "$URL" 2>/dev/null || true)"
  rm -rf "$TDD"
  # accept once the dump is non-empty AND carries the synchronously-injected probe node.
  case "$DOM" in *'id="__qa"'*) break;; esac
done

# Persist the settled DOM (incl. the #__qa probe node) next to the screenshot. health.sh parses
# both the DOM (errors, lib init, hooks) and the PNG (pixel variance) to decide pass/fail.
printf '%s' "$DOM" > "${OUT%.png}.dom.html"

if [ -f "$OUT" ]; then
  echo "OK render -> $OUT ($(stat -c%s "$OUT") bytes), dom -> ${OUT%.png}.dom.html"
  exit 0
else
  echo "FAIL render -> $OUT (no screenshot produced)"
  exit 1
fi
