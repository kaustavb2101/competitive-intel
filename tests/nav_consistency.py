#!/usr/bin/env python3
"""Nav consistency + route reachability gate.

Two failures this catches, both of which had already happened silently:

1. **Nav drift.** The main nav is hand-copied into six pages (index, data, province,
   rayong-catchment, branch-explorer, status). There is no build step, so nothing kept them in
   sync — status.html was left on the PRE-five-pillar labels (Overview / National / Exposure /
   Trend) with no Assistance or Acquisition entry at all, and data.html never got the Explore
   menu the other pages had. Anyone landing on those pages met a menu that contradicted the app.

2. **Orphan routes.** index.html builds one <section class="view" id="v-X"> per hash route. Three
   of them — #branches, #provinces, #market — lost their menu entries in the 2026-07-25 five-pillar
   cleanup and never got a replacement link, so they rendered perfectly and were reachable only by
   typed URL. Nothing failed; they just quietly stopped existing for users.

So: every page's nav must carry the same five-pillar sequence and the same Explore menu, and every
route index.html builds must be reachable from that nav — or be listed in LEGACY_ROUTES with a
reason, which makes keeping an unlinked route a deliberate, reviewed act instead of an accident.

Offline, stdlib only. Exit 0 = pass, 1 = fail.
"""
import html.parser
import io
import os
import re
import sys

PLATFORM = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "platform")

# The journey. Order matters — this IS the narrative sequence, and index.html's "Next in the
# story" chain walks it in exactly this order.
PILLARS = [
    ("Home",        "#home"),
    ("Macro",       "#overview"),
    ("Acquisition", "data.html"),
    ("Assistance",  "#assist"),
    ("Risk",        "#exposure"),
    ("Competition", "#acq"),
]

# The tools tier — everything that is NOT a step in the journey.
EXPLORE = [
    ("Risk trend",        "#trend"),
    ("Map view",          "#map"),
    ("Provinces 3D",      "#provinces"),
    ("Branches",          "data.html?branches"),
    ("Market assessment", "#market"),
    ("Simulator",         "#sim"),
    ("Live board",        "live.html"),
]

# Routes index.html builds that are deliberately NOT in the nav. Each needs a reason.
LEGACY_ROUTES = {
    "branches": "superseded by data.html?branches (does strictly more); kept alive for old bookmarks",
}

PAGES = ["index.html", "data.html", "province.html", "rayong-catchment.html",
         "branch-explorer.html", "status.html", "live.html"]


class NavParser(html.parser.HTMLParser):
    """Pull the anchors out of <nav id="nav">, tracking whether each sits in the Explore menu."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0            # >0 once inside <nav id="nav">
        self.menu_depth = 0       # >0 once inside .nav-more-menu
        self.links = []           # (label, href, in_menu)
        self._href = None
        self._buf = []
        self._hidden = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "nav" and a.get("id") == "nav":
            self.depth = 1
            return
        if not self.depth:
            return
        if tag == "nav":                       # a nested <nav> (the Competition jump-nav)
            self.depth += 1
        if "nav-more-menu" in (a.get("class") or ""):
            self.menu_depth = 1
        elif self.menu_depth:
            self.menu_depth += 1
        if tag == "a":
            self._href = a.get("href")
            self._hidden = "hidden" in a
            self._buf = []

    def handle_data(self, d):
        if self._href is not None:
            self._buf.append(d)

    def handle_endtag(self, tag):
        if not self.depth:
            return
        if tag == "a" and self._href is not None:
            if not self._hidden:
                label = re.sub(r"\s+", " ", "".join(self._buf)).strip()
                self.links.append((label, self._href, self.menu_depth > 0))
            self._href = None
        if self.menu_depth:
            self.menu_depth -= 1
        if tag == "nav":
            self.depth -= 1


def norm(href):
    """index.html#x, /#x and #x all name the same route; keep page links as-is."""
    if href is None:
        return ""
    h = href.strip()
    for prefix in ("index.html", "/", "./"):
        if h.startswith(prefix + "#"):
            return h[len(prefix):]
    return h


def strip_arrow(label):
    return label.replace("↗", "").replace("→", "").strip()


def check_page(name, errors):
    path = os.path.join(PLATFORM, name)
    p = NavParser()
    p.feed(io.open(path, encoding="utf-8").read())

    links = [(strip_arrow(l), norm(h), m) for (l, h, m) in p.links if strip_arrow(l)]

    got_pillars = [(l, h) for (l, h, m) in links if not m and (l, h) in PILLARS]
    if got_pillars != PILLARS:
        errors.append("%s: pillar sequence is %s, expected %s"
                      % (name, [l for l, _ in got_pillars], [l for l, _ in PILLARS]))

    got_explore = [(l, h) for (l, h, m) in links if m]
    if got_explore != EXPLORE:
        errors.append("%s: Explore menu is %s, expected %s"
                      % (name, got_explore, EXPLORE))

    return set(h for _, h, _ in links)


def main():
    errors = []
    reachable = set()
    for name in PAGES:
        reachable |= check_page(name, errors)

    # Every route index.html builds must be reachable from the nav (or declared legacy).
    src = io.open(os.path.join(PLATFORM, "index.html"), encoding="utf-8").read()
    routes = re.findall(r'<section class="view[^"]*" id="v-([a-z0-9_-]+)"', src)
    if len(routes) < 5:
        errors.append("index.html: found only %d view sections — the route regex has gone stale"
                      % len(routes))
    for r in routes:
        if "#" + r in reachable or r in LEGACY_ROUTES:
            continue
        errors.append("index.html: route #%s renders but nothing in the nav links to it "
                      "(add it to the nav, or to LEGACY_ROUTES with a reason)" % r)

    # ...and a route declared legacy must actually still exist, or the note is a lie.
    for r in LEGACY_ROUTES:
        if r not in routes:
            errors.append("LEGACY_ROUTES lists #%s but index.html no longer builds it — drop the entry" % r)

    if errors:
        for e in errors:
            print("  FAIL " + e)
        print("nav_consistency: %d problem(s)" % len(errors))
        return 1
    print("nav_consistency: %d pages share one nav; %d routes, all reachable (%d legacy)"
          % (len(PAGES), len(routes), len(LEGACY_ROUTES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
