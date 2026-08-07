#!/usr/bin/env python3
"""merge_append_log.py — union-merge an append-at-top log during a conflicted git merge.

THE PROBLEM
-----------
docs/PROGRESS_LOG.md is reverse-chronological: every branch writes a new `## <date> — ...` block at
the top of the file, and nobody ever edits anyone else's block. So any two branches collide there,
guaranteed, on a line neither of them disagrees about — the same shape as the provenance.json
collision that resolve_derived_conflicts.sh already handles, one file up. Working from two places at
once makes it the normal case: three of the six open PRs on 2026-08-07 were blocked on nothing but
this. Git cannot know two top-inserted blocks are independent. This can.

THE PRECONDITION (this is what makes automating it safe)
--------------------------------------------------------
It refuses unless the merge is PURELY ADDITIVE: every block present in the merge BASE must still be
present, byte-identical, on BOTH sides, and the preamble must be unchanged by at least one side. If
either side edited, reworded or deleted an existing entry, that is a real disagreement about shared
text and it exits 3 so a human settles it. Union-merging is only correct for append-only files, so
the script proves the file was appended to before treating it as one.

ORDERING
--------
Output is master's file with this branch's new blocks slotted in by date, each placed BELOW every
block dated the same day or later. Same-day entries therefore read master-first: master's landed
while this branch's was still open, so it is the later of the two in wall-clock terms even though
the date string matches.

    python3 pipeline/merge_append_log.py --base B --ours O --theirs T --out FILE
    python3 pipeline/merge_append_log.py --selftest

Exit 0 = wrote the union. 3 = not purely additive; the caller must abort and leave it to a human.
1 = usage or I/O error.
"""
import argparse
import os
import re
import sys

BLOCK_RE = re.compile(r"^## ", re.M)
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})")

RC_OK, RC_ERR, RC_NOT_ADDITIVE = 0, 1, 3


def split_blocks(text):
    """-> (preamble, [block, ...]). A block runs from its `## ` heading to the next one."""
    marks = [m.start() for m in BLOCK_RE.finditer(text)]
    if not marks:
        return text, []
    blocks = []
    for i, start in enumerate(marks):
        end = marks[i + 1] if i + 1 < len(marks) else len(text)
        blocks.append(text[start:end])
    return text[: marks[0]], blocks


def heading(block):
    return block.split("\n", 1)[0].strip()


def date_of(block):
    m = DATE_RE.match(block)
    return m.group(1) if m else ""


def union(base, ours, theirs):
    """-> (merged_text, None) or (None, reason). `theirs` is the base branch (master)."""
    pre_b, blocks_b = split_blocks(base)
    pre_o, blocks_o = split_blocks(ours)
    pre_t, blocks_t = split_blocks(theirs)

    # The preamble is shared prose. One side may update it; both changing it differently is a real
    # conflict about the same words.
    if pre_o == pre_t:
        preamble = pre_o
    elif pre_o == pre_b:
        preamble = pre_t
    elif pre_t == pre_b:
        preamble = pre_o
    else:
        return None, "both sides rewrote the preamble differently"

    by_head_o = {heading(b): b for b in blocks_o}
    by_head_t = {heading(b): b for b in blocks_t}

    # PURELY ADDITIVE, checked both ways: nothing from the base may be dropped or reworded.
    for b in blocks_b:
        h = heading(b)
        for side, table in (("this branch", by_head_o), ("the base branch", by_head_t)):
            if h not in table:
                return None, "%s deleted an existing entry: %s" % (side, h[:70])
            if table[h] != b:
                return None, "%s edited an existing entry: %s" % (side, h[:70])

    base_heads = {heading(b) for b in blocks_b}
    result = list(blocks_t)  # master's file: base blocks + whatever master added, in its own order

    for b in blocks_o:
        h = heading(b)
        if h in base_heads:
            continue  # already present, unchanged (proven above)
        if h in by_head_t:
            # Both sides added an entry under the same heading.
            if by_head_t[h] == b:
                continue  # identical — the same commit reached both sides; dedupe silently
            return None, "both sides added a different entry titled: %s" % h[:70]
        d = date_of(b)
        if not d:
            result.insert(0, b)  # undated: newest-first is the file's rule, so it goes on top
            continue
        pos = len(result)
        for i, existing in enumerate(result):
            if date_of(existing) < d:
                pos = i
                break
        result.insert(pos, b)

    return preamble + "".join(result), None


# --------------------------------------------------------------------------------------- selftest
def _selftest():
    def blk(date, title, body="body\n"):
        return "## %s — %s\n\n%s\n" % (date, title, body)

    pre = "# LOG\n\nNewest first.\n\n"
    passed = failed = 0

    def check(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print("  [PASS] %s" % name)
        else:
            failed += 1
            print("  [FAIL] %s\n         got:  %r\n         want: %r" % (name, got, want))

    old = blk("2026-08-01", "old entry")
    base = pre + old
    mine = blk("2026-08-06", "branch entry")
    master = blk("2026-08-06", "master entry")

    # 1. the everyday case: both sides appended, nothing else moved
    out, err = union(base, pre + mine + old, pre + master + old)
    check("no error on a purely additive merge", err, None)
    check("kept all three entries", out, pre + master + mine + old)

    # 2. same-day ordering puts master's already-landed entry above the open branch's
    check("master-first within a date", out.index("master entry") < out.index("branch entry"), True)

    # 3. dates still descend after the splice
    older = blk("2026-07-30", "older")
    out2, _ = union(pre + older, pre + blk("2026-08-02", "b") + older,
                    pre + blk("2026-08-05", "m") + older)
    check("slots by date, not blindly on top", [date_of(x) for x in split_blocks(out2)[1]],
          ["2026-08-05", "2026-08-02", "2026-07-30"])

    # 4/5. a shared entry that either side changed is a REAL conflict, not an append
    _, err = union(base, pre + mine + blk("2026-08-01", "old entry", "reworded\n"), pre + master + old)
    check("refuses when this branch edited a shared entry", err is not None, True)
    _, err = union(base, pre + mine + old, pre + master)
    check("refuses when the base branch deleted a shared entry", err is not None, True)

    # 6. the same commit reaching both sides must not be duplicated
    same = blk("2026-08-06", "same entry")
    out3, err = union(base, pre + same + old, pre + same + old)
    check("dedupes an identical entry added on both sides", (err, out3), (None, pre + same + old))

    # 7. two different entries under one heading is a genuine disagreement
    _, err = union(base, pre + blk("2026-08-06", "dup", "mine\n") + old,
                   pre + blk("2026-08-06", "dup", "theirs\n") + old)
    check("refuses two different entries sharing a heading", err is not None, True)

    # 8. an empty base (new file on both sides) still unions
    out4, err = union("", mine, master)
    check("handles an empty base", (err, out4), (None, master + mine))

    print("  %d passed, %d failed" % (passed, failed))
    return RC_OK if failed == 0 else RC_ERR


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--base")
    ap.add_argument("--ours")
    ap.add_argument("--theirs")
    ap.add_argument("--out")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        return _selftest()
    if not all([a.base, a.ours, a.theirs, a.out]):
        ap.error("--base, --ours, --theirs and --out are all required")

    try:
        texts = []
        for p in (a.base, a.ours, a.theirs):
            # A stage can be legitimately absent (added-on-one-side); treat that as empty.
            if os.path.exists(p):
                with open(p, "r", encoding="utf-8", newline="") as fh:
                    texts.append(fh.read())
            else:
                texts.append("")
    except OSError as e:
        print("cannot read a merge stage: %s" % e, file=sys.stderr)
        return RC_ERR

    merged, reason = union(*texts)
    if merged is None:
        print("not a purely additive merge — %s" % reason, file=sys.stderr)
        return RC_NOT_ADDITIVE

    # newline="\n" is load-bearing on Windows: CRLF here would change the file's byte size and be
    # picked up as drift by anything that censuses it.
    with open(a.out, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(merged)
    return RC_OK


if __name__ == "__main__":
    sys.exit(main())
