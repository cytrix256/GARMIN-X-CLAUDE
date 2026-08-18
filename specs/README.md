# Specs

One file per non-trivial change, written before building it. Numbered in the
order they were started: `001-`, `002-`, and so on.

A spec exists to make the disagreement happen before the code does. If a change
is obvious and small, skip the spec and just make it — a spec for a one-line fix
is bureaucracy.

Write one when: the change produces something a human reads, it touches how a
metric is computed, it adds a file to the pipeline, or you are not sure what
"done" looks like.

## Files

| Spec | Status |
|---|---|
| `001-weekly-training-review.md` | In progress — the current demo |

## Template

```
# NNN — <title>

**Status** — draft / in progress / shipped / abandoned
**Roadmap item** — which line in ROADMAP.md this serves

## Problem
What is wrong today, for whom. No solution yet.

## Output
What exists at the end that did not exist before. Be concrete — a file, a
section, a number on a page.

## Inputs available
What data this can actually use, checked against context/data.md.

## Acceptance criteria
Checkable statements. Each one is either true or false when you look.

## Non-goals
What this deliberately does not do, so scope does not drift mid-build.

## Open questions
Things that could change the design. Answer them or state the assumption.
```
