---
name: tape-pii-floor
description: MANDATORY before touching the real loan tape, any tape-derived layer, call lists, or borrower-level data (ingest_real_tape.py, build_tape_layers.py, tape_real.json, tape_geo_occ.json, Pantip/YouTube/app-review text). Encodes the disclosure floor, the no-identifier rule, and which files may never enter the repo.
---

# Loan tape and borrower-data handling

The real tape landed 2026-07-21: **382,735 real accounts, ฿46.6bn outstanding.** It is not synthetic.
These rules are not style preferences — they are the conditions under which this data is allowed to
exist in the project at all.

## The three hard rules

### 1. No identifier, ever, anywhere

Never print, log, write, or return an **account number or application number** — not to a file, not to
stdout, not into a commit message, **not into an agent report or a summary back to the user.** This
holds even in intermediate scratch output. There is no "temporary" exception.

The same applies to borrower identity in social listening (Pantip, YouTube comments, app reviews):
no name, id, handle, profile link, or avatar reaches disk, and identifiers are scrubbed from body
text too. Published output is aggregates plus short **unattributed** quotes. Only `org:true` is
retained, and only as a category — never as an identity.

### 2. `MIN_CELL = 30`

Nothing published may rest on fewer than 30 accounts. Any cell, cross, segment, branch row or
occupation bucket below the floor is suppressed — not rounded, not merged silently, **suppressed and
disclosed**. If suppression removes rows, say how many and why.

### 3. The raw file never enters the repo

The owner-side xlsx stays off-repo. `ingest_real_tape.py` reads it via `--src` or `REAL_TAPE_XLSX`
and streams it into committed **no-PII aggregates** at `source-data/staging/real_tape_aggregates.json`.
Nothing between the xlsx and that staging file is committed.

Call-list CSVs (`make_call_lists.py`) contain account numbers by design. They are written to the
owner's Documents folder — **outside the working tree** — and are never committed. If you find one
inside the tree, that is an incident, not a cleanup task.

Harvested government data (`source-data/gdcatalog_harvest/`, `source-data/dlt/raw/`) is gitignored and
stays that way.

## The gate boundary

```
owner xlsx  ──(ingest_real_tape.py, owner-side, NOT gated — input is off-repo)──▶
  source-data/staging/real_tape_aggregates.json
  ──(build_tape_layers.py, deterministic, --check GATED)──▶
    platform/data/tape_real.json + tape_geo_occ.json
```

Everything downstream of staging **is** in the determinism gate. `ingest_real_tape.py` is not, because
its input lives outside the repo — that is deliberate, not an oversight.

## Anchors and time

The months-on-book anchor is the **newest disbursement year-month present in the data** — never wall
clock. Wall-clock anchoring makes every historical vintage drift and breaks the gate. The same
principle governs every feed: date a snapshot by the source's own stamp, not by when it was fetched.

## Reading the book correctly

The tape is **two books**, and conflating them misstates credit quality in both directions:

- **Live book** — 342,686 accounts / ฿43.5bn. NPL-live 4.92% of accounts, 6.06% outstanding-weighted.
- **180+ legacy** — 40,049 accounts / ฿3.05bn, held separately.

Lead with **90+**, not 30+. Report the live book and the legacy book apart; a blended NPL figure is
not a number anyone can act on.

## Do not build on the synthetic generator

`make_synthetic_tape.py` predates the real tape. It is kept only to reproduce pre-2026-07-21 vintages
and its outputs are gitignored. Build nothing new on it.
`ingest_loan_tape.py` / `loan_tape_derived.json` were retired 2026-07-31 — do not resurrect them.

## Before you finish

- [ ] No account or application number in any output, including your own report
- [ ] Every published cell ≥ 30 accounts, suppressions disclosed
- [ ] No raw xlsx, call list, or harvest path staged for commit (`git status` before `git add`)
- [ ] Anchors derived from data, not wall clock
- [ ] Live book and 180+ legacy reported separately
