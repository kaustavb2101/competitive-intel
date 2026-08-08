---
name: determinism-gate
description: Run or debug the byte-exact determinism gate (tests/run.sh check, any build_*.py --check, provenance regeneration). Use whenever a --check reports drift, before committing a data-layer change, or when reconciling a red gate. Encodes which environment is authoritative and the four traps that produce false verdicts.
---

# The determinism gate

Every derive/build script in `pipeline/` is deterministic and network-free and carries `--check`,
which reproduces its output and compares byte-for-byte. `bash tests/run.sh check` runs them all.

**The gate is the product's quality model.** A layer that does not reproduce byte-exactly is a layer
whose numbers cannot be trusted. Do not work around a red gate — diagnose it.

## Rule 1 — two environments, neither complete alone

| | determinism verdict | `node --check` |
|---|---|---|
| **WSL + uv cpython-3.11 (LF mirror)** | **AUTHORITATIVE** | impossible — no Node installed |
| **Windows Python 3.14** | false drift, do not trust | works |

Consequences you must internalise before reading any gate output:

- **A clean mirror run reads `RESULT: N passed, 9 failed`.** Those 9 are the `node --check` steps,
  failing because WSL has no Node. That is an environment gap, not a defect. A mirror run showing
  *more* than 9 failures has real drift; a run showing exactly 9 is green.
- **Windows Python 3.14 produces false float drift** on roughly 9 layers (`derive.py`,
  `build_branch_agri.py`, `build_regional_outlook.py`, `build_farmgate_platform.py`,
  `build_branch_risk.py`, `build_opportunity_score.py`, `build_macro_book.py`,
  `build_crop_landuse.py`, `build_provenance.py`). Never conclude a layer is broken from a Windows
  `--check` alone.
- Use Windows **only** for `node --check` on page JS. Use the mirror for everything numeric.

## Rule 2 — invoke the mirror through PowerShell, never Git Bash

Two traps stack here and both produce silent wrong answers:

1. **Git Bash expands `$VAR` before the inner shell sees it.** A command like
   `wsl -- bash -c 'for f in $LIST; ...'` arrives with `$LIST` already blanked. Symptom: a sweep that
   reports `MISS` for everything.
2. **Git Bash rewrites `/mnt/c/...` into `C:/Program Files/Git/mnt/c/...`** when it looks like a path
   argument. Symptom: `exit 127`, command not found.

**The working pattern:** write the script to a file, convert CRLF→LF, then invoke it from the
**PowerShell** tool (not Bash):

```powershell
$s = "<scratchpad>/gate.sh"
[IO.File]::WriteAllText($s, ($body -replace "`r`n","`n"))
wsl -- bash /mnt/c/.../gate.sh
```

## Rule 3 — strip ANSI before grepping the output

The gate colours its verdicts, so `[FAIL]` lines actually begin with an escape sequence.
`grep "^\[FAIL\]"` matches nothing and you will read a red gate as green.

```bash
... | sed 's/\x1b\[[0-9;]*m//g' | grep '^\[FAIL\]'
```

## Rule 4 — never hand-merge `platform/data/provenance.json`

It is the universal collision point: every data branch touches it, so every data PR conflicts there.

It is also a **pure function of the committed sources** — a conflict is two stale copies of one
computation, not two competing edits. Resolve by replay, never by merge:

1. Clear the conflict marker (take either side; the content is about to be overwritten).
2. Regenerate on the **LF mirror**: `python pipeline/build_provenance.py`.
3. Confirm `--check` passes.

The same logic applies to every derived layer under `platform/data/`. **Replay, don't merge.**

## Rule 5 — a pull without a re-derive is a red gate

A raw network pull that is not propagated leaves every downstream layer reproducing from the *old*
bytes, so the next gate run fails and the app ships the previous vintage. This has bitten repeatedly.

**Do not hand-maintain the chain.** `pipeline/rederive_drift.py` parses `tests/run.sh` for every
`--check`-gated builder, runs them, re-runs whatever drifts, iterates to a fixed point (2–3 passes
typical), and runs `build_provenance.py` last. It deliberately refuses to auto-run anything prefixed
`pull_`.

```bash
# after ANY network pull, exactly once:
python pipeline/rederive_drift.py
```

## Rule 6 — the two drift traps that are real

When the mirror reports genuine drift, suspect these before anything else:

- **`round()` at a `.5` boundary.** Banker's rounding plus a float representation a hair either side
  of the boundary flips the last digit between runs on different inputs. Fix the computation, not the
  comparison.
- **CRLF vs LF byte sizes.** `provenance.json` records byte sizes. A file written with CRLF on Windows
  has different sizes than the same file on the LF mirror, so provenance drifts even though the
  content is identical. Anything that writes and then compares must do both in LF
  (see the `crop_stress` / `crop_farmer_income` fix).

## Checklist before committing a data change

- [ ] Regenerated on the LF mirror (not Windows)
- [ ] `rederive_drift.py` run once if any raw source changed
- [ ] Mirror gate shows exactly 9 failures (the Node gap), no more
- [ ] `node --check` run on Windows for any page JS touched
- [ ] `provenance.json` regenerated last, on the mirror
