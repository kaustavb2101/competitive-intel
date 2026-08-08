---
name: distill
description: Turn what was learned in a work session into durable memory or a reusable skill. Run at the end of a substantive session, after a wave ships, or when the user says "remember this" / "distill" / "what did we learn". Sorts each learning into fact-vs-procedure and applies the promotion rule that keeps skills from sprawling.
---

# Distill a session into memory or a skill

Most learnings from a session evaporate. The ones that survive are filed in the wrong place: a
**procedure** written down as a **fact** has to be re-derived from scratch every time it comes up.
This skill fixes the sorting.

## The distinction that does the work

| | **Memory** | **Skill** |
|---|---|---|
| holds | a fact to recall | a procedure to follow |
| loaded | index, every session | on demand, when the task matches |
| cost | must stay cheap | can be long |
| example | "AutoX has no IPO" | "how to run the determinism gate" |

If the answer to "what is this?" is a *sentence*, it is a memory.
If the answer is *steps, traps, or a checklist*, it is a skill.

## The promotion rule

**A learning graduates from memory to skill only when it has bitten twice, or cost real rework the
first time.**

This rule exists to protect curation. There are ~4,200 skills on disk and ~14 installed — that ratio
is deliberate. A skill created from a single unremarkable incident is noise that makes the useful
ones harder to find. When in doubt, write the memory; the second occurrence is what earns the skill.

Signals that something has earned promotion:
- it produced a **false verdict** (a green read of a red state, or vice versa)
- it cost a **re-run, a revert, or a wasted wave**
- it is a **safety condition** — those are promoted immediately, on the first occurrence, because the
  second occurrence is the incident you are trying to prevent

## Procedure

1. **Sweep the session** for: corrections the user made, defects found in my own shipped work,
   environment traps, and anything I had to rediscover that was already known.
2. **Sort each one** — fact or procedure, by the test above.
3. **For facts**: check `memory/MEMORY.md` for an existing entry that already covers it and *update
   that file* rather than adding a near-duplicate. Delete memories that turned out to be wrong.
4. **For procedures**: apply the promotion rule. If it qualifies, draft it with the `skill-creator`
   skill.
5. **Scope it correctly** (below).
6. **Report** what was written, what was updated, and — importantly — what was *rejected* and why.
   A distill pass that promotes everything has not exercised any judgement.

## Scoping: project skill or user skill?

- **`competitive-intel/.claude/skills/`** — anything true of *this repo*: the determinism gate, the
  tape disclosure floor, the re-derive chain, Thai government source reachability. These are checked
  in, travel with the codebase, and apply to anyone working here.
- **`~/.claude/skills/`** — anything true of *this laptop or this person* across projects: Excel COM
  because there is no LibreOffice, Windows/WSL invocation patterns, document-generation preferences.

Getting this wrong is the common failure. A repo-specific procedure filed as a user skill fires on
unrelated projects; a laptop-specific one filed in the repo misleads anyone else who clones it.

## What not to write down

- Anything the repo already records — code structure, git history, `CLAUDE.md`, a fixed bug
- Anything that only mattered inside one conversation
- Restatements of general knowledge with no local specificity

If asked to save one of these, ask what was *non-obvious* about it and save that instead.

## Verify before writing

A memory or skill reflects what was true when written. Before recording that a file, function, or
flag exists — **check that it still does.** A confidently wrong skill is worse than no skill, because
it is loaded automatically and trusted.
