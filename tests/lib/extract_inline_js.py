#!/usr/bin/env python3
"""Extract every inline <script> (no src=) from an HTML page to separate .js files for `node --check`.

Inline scripts in the platform pages contain the real rendering logic (deck.gl layer setup, panel
DOM wiring). `node --check` catches syntax errors before a browser ever runs them — cheap, offline,
deterministic. Each block is written so node parses it standalone; we wrap in a function to allow
top-level `return`/`await`-free blocks and avoid redeclaration collisions across blocks.

Usage: extract_inline_js.py <page.html> <outdir>
Writes <outdir>/<basename>.<n>.js for each inline block; prints the count.
"""
import sys, os, re

page = sys.argv[1]
outdir = sys.argv[2]
os.makedirs(outdir, exist_ok=True)
base = os.path.basename(page)
html = open(page, encoding="utf-8", errors="ignore").read()

# match <script ...>...</script>, capture attrs + body
n = 0
for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S | re.I):
    attrs, body = m.group(1), m.group(2)
    if re.search(r"\bsrc\s*=", attrs, re.I):
        continue  # external script, nothing inline to check
    if not body.strip():
        continue
    n += 1
    # Wrap so that top-level statements valid only inside a function (rare) still parse, and so
    # `const X=...` in two blocks don't clash. IIFE preserves the block's own scope semantics
    # closely enough for a syntax check.
    wrapped = "(function(){\n" + body + "\n});\n"
    with open(os.path.join(outdir, "%s.%d.js" % (base, n)), "w", encoding="utf-8") as f:
        f.write(wrapped)

print(n)
