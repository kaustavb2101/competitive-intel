#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""context_statusline.py — a Claude Code STATUS LINE that watches token usage and tells you when
to compact, so long sessions don't quietly run up token cost.

This is the honest, supported way to get "a background process that watches my conversation size":
Claude Code runs this script on every status-line refresh (event-driven) and pipes it a JSON blob
about the live session on stdin — including the context window's used tokens / percentage. We render
a one-line gauge and, past a threshold, a loud COMPACT nudge.

Why not "auto-run /compact from a script"? You can't — `/compact` is an in-REPL command against the
running CLI's in-memory state; no external process can inject it, and even hooks can only *react* to
compaction, not start it (Claude Code docs, hooks.md). The real automation is the CLI's BUILT-IN
auto-compact (settings key `autoCompactEnabled`, tuned lower with the env vars in
.claude/settings.local.json) — this status line just makes the threshold visible so you (or the
auto-compactor) act in time.

Wire-up (already added to .claude/settings.local.json):
  "statusLine": { "type": "command",
                  "command": "python \"<repo>/tools/context_statusline.py\"" }
Env knobs (optional): AUTOX_CTX_WARN (default 200000), AUTOX_CTX_HOT (default 350000) — input-token
thresholds for the yellow / red nudge.

Test it by hand:  echo '{"context_window":{"total_input_tokens":410000,"context_window_size":1000000}}' | python tools/context_statusline.py
"""
import json
import os
import sys


def dig(d, *paths):
    """Return the first present value among dotted paths."""
    for p in paths:
        cur = d
        ok = True
        for k in p.split("."):
            if isinstance(cur, dict) and k in cur:
                cur = cur[k]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return None


def human(n):
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    if n >= 1000:
        return "%.0fk" % (n / 1000.0)
    return "%d" % int(n)


def main():
    # Windows consoles default to cp1252, which can't encode the gauge glyphs — force UTF-8.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        d = json.load(sys.stdin)
    except Exception:
        d = {}

    used = dig(d, "context_window.total_input_tokens", "context_window.used_tokens",
               "contextWindow.totalInputTokens", "tokens.input")
    size = dig(d, "context_window.context_window_size", "context_window.size",
               "contextWindow.contextWindowSize")
    pct = dig(d, "context_window.used_percentage", "contextWindow.usedPercentage")
    if pct is None and used and size:
        try:
            pct = 100.0 * float(used) / float(size)
        except (TypeError, ValueError, ZeroDivisionError):
            pct = None

    model = dig(d, "model.display_name", "model.id", "model") or "Claude"
    cwd = dig(d, "workspace.current_dir", "cwd", "workspace.cwd") or ""
    base = os.path.basename(cwd.rstrip("/\\")) if cwd else ""

    warn = int(os.environ.get("AUTOX_CTX_WARN", "200000"))
    hot = int(os.environ.get("AUTOX_CTX_HOT", "350000"))

    # ANSI colours (status lines render them)
    G, Y, R, DIM, RESET = "\033[32m", "\033[33m", "\033[31m", "\033[2m", "\033[0m"

    # context gauge
    ctx = ""
    if used is not None:
        u = int(float(used))
        col = G if u < warn else (Y if u < hot else R)
        pctxt = ("%.0f%%" % pct) if pct is not None else ""
        bar_n = 10
        filled = min(bar_n, int((pct or 0) / 10)) if pct is not None else 0
        bar = "█" * filled + "░" * (bar_n - filled)
        nudge = ""
        if u >= hot:
            nudge = R + "  ⚠ COMPACT NOW (/compact) or /clear" + RESET
        elif u >= warn:
            nudge = Y + "  ▲ getting large — consider /compact soon" + RESET
        ctx = "%sctx %s %s %s%s%s" % (col, bar, human(u), pctxt, RESET, nudge)
    else:
        ctx = DIM + "ctx —" + RESET

    parts = [DIM + str(model) + RESET]
    if base:
        parts.append(DIM + base + RESET)
    parts.append(ctx)
    sys.stdout.write("  ".join(parts))


if __name__ == "__main__":
    main()
