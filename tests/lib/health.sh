#!/usr/bin/env bash
# Per-page health gate. Reads the rendered screenshot + dumped DOM produced by render.sh and a
# manifest row, then asserts:
#   (1) no uncaught JS error was captured by the injected probe  (#__qa data-errors == [])
#   (2) the required library initialised                          (data-deck / data-leaflet == 1)
#   (3) the screenshot is non-blank                               (pixvar: enough distinct lumas
#                                                                   AND a non-trivial non-blank frac)
#   (4) every required DOM hook id exists in the settled DOM and is non-empty
#
# Usage: health.sh <out.png> <gl:webgl|leaflet> <min_canvas> <hooks_csv>
# Exit 0 = healthy, 1 = failed (prints the failing assertions).
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PNG="$1"; GL="$2"; MINCANVAS="$3"; HOOKS="$4"
DOM="${PNG%.png}.dom.html"
fail=0
say(){ printf '    %s %s\n' "$1" "$2"; }

if [ ! -f "$PNG" ]; then say "FAIL" "no screenshot"; exit 1; fi
if [ ! -f "$DOM" ]; then say "FAIL" "no dumped DOM"; exit 1; fi

# (1) uncaught errors — pull data-errors="..." off the #__qa probe node.
ERRJSON="$(grep -oE 'id="__qa"[^>]*data-errors="[^"]*"' "$DOM" | grep -oE 'data-errors="[^"]*"' | head -1 | sed 's/^data-errors="//; s/"$//')"
# &quot; entity-decode for grep readability
ERRJSON_DEC="$(printf '%s' "$ERRJSON" | sed 's/&quot;/\"/g')"
if [ -n "$ERRJSON_DEC" ] && [ "$ERRJSON_DEC" != "[]" ]; then
  say "FAIL" "uncaught JS error(s): $ERRJSON_DEC"; fail=1
else
  say "ok  " "no uncaught JS errors"
fi

# (2) library init
if [ "$GL" = "webgl" ]; then
  if grep -qE 'id="__qa"[^>]*data-deck="1"' "$DOM"; then say "ok  " "deck.gl initialised"; else say "FAIL" "deck.gl did not initialise"; fail=1; fi
elif [ "$GL" = "leaflet" ]; then
  if grep -qE 'id="__qa"[^>]*data-leaflet="1"' "$DOM"; then say "ok  " "leaflet initialised"; else say "FAIL" "leaflet did not initialise"; fail=1; fi
else
  say "ok  " "no GL lib required (gl=$GL)"
fi

# (3) non-blank screenshot
PV="$(python3 "$HERE/pixvar.py" "$PNG" 2>/dev/null)"
DL="$(printf '%s' "$PV" | sed -n 's/.*"distinct_lumas": *\([0-9]*\).*/\1/p')"
NB="$(printf '%s' "$PV" | sed -n 's/.*"non_blank_frac": *\([0-9.]*\).*/\1/p')"
DL="${DL:-0}"; NB="${NB:-0}"
# blank/solid page -> distinct_lumas ~1-3 and non_blank_frac ~0. Require variety + drawn content.
if [ "$DL" -ge 6 ] && python3 -c "import sys;sys.exit(0 if float('$NB')>=0.01 else 1)"; then
  say "ok  " "non-blank screenshot (lumas=$DL nonblank=$NB)"
else
  say "FAIL" "screenshot looks blank (lumas=$DL nonblank=$NB)"; fail=1
fi

# (3b) canvas presence (deck.gl/leaflet both create <canvas>; leaflet preferCanvas too)
NCANVAS="$(grep -oE '<canvas' "$DOM" | wc -l | tr -d ' ')"
if [ "$NCANVAS" -ge "$MINCANVAS" ]; then say "ok  " "$NCANVAS canvas element(s)"; else say "FAIL" "expected >=$MINCANVAS canvas, found $NCANVAS"; fail=1; fi

# (4) DOM hooks present & non-empty
IFS=',' read -ra IDS <<< "$HOOKS"
for id in "${IDS[@]}"; do
  [ -z "$id" ] && continue
  # element exists?
  if ! grep -qE "id=\"$id\"" "$DOM"; then say "FAIL" "missing #$id"; fail=1; continue; fi
  # non-empty? grab the element's inner text crudely: content between this id's tag and the next </
  CONTENT="$(python3 - "$DOM" "$id" <<'PY'
import sys,re
dom=open(sys.argv[1],encoding='utf-8',errors='ignore').read()
hid=sys.argv[2]
m=re.search(r'id="%s"[^>]*>(.*?)</'%re.escape(hid),dom,re.S)
inner=m.group(1) if m else ''
# strip tags+whitespace
txt=re.sub(r'<[^>]+>','',inner).strip()
print(len(txt))
PY
)"
  if [ "${CONTENT:-0}" -gt 0 ] 2>/dev/null; then
    say "ok  " "#$id present & non-empty"
  else
    # map containers (#map) are legitimately empty of text but hold a canvas — accept if canvas present
    if [ "$id" = "map" ] && [ "$NCANVAS" -ge 1 ]; then
      say "ok  " "#map present (canvas-backed)"
    else
      say "FAIL" "#$id empty"; fail=1
    fi
  fi
done

exit $fail
