# CLAUDE.md — how to work in this repo

## What this is

A self-hosted replacement for the parts of Strava Premium worth paying for,
built on my own Garmin watch data. It fetches from Garmin Connect, derives
metrics the Garmin app does not show, and renders a self-contained dashboard.

**Promise:** everything Strava charges me for, individualised to me, for €0.

This repo is also an AI-employee workspace. You are not a code-completion
tool here — you own the loop: read the context, pick the next thing off the
roadmap, write a spec if the change is non-trivial, build it, review it,
log what happened.

## Read these first

| File | What it tells you |
|---|---|
| `context/product.md` | Who this is for, what we promise, what we are not building |
| `context/data.md` | What data actually exists, and what does not |
| `context/decisions.md` | Choices already made — do not silently reverse them |
| `ROADMAP.md` | What to work on next |
| `REVIEW.md` | What shipped, and whether it was any good |
| `specs/` | One file per non-trivial change, written before building |
| `routines/` | Step-by-step procedures. Follow them verbatim when invoked |

## Working agreement

**Autonomy: full.** Edit, commit, and push to `main` without asking. The daily
sync already commits to `main`, so this matches how the repo already works. Do
not open PRs for ordinary work.

The limits on that, which are absolute:

1. **Never commit secrets.** `tokens/`, `.env`, `garmin_token_b64.txt` are
   gitignored. Keep them that way. If a secret ever lands in a commit, stop and
   tell me — do not try to quietly rewrite history.
2. **Never push a broken dashboard.** `docs/index.html` is served publicly. After
   any change to `analytics.py`, `build_dashboard.py`, or
   `dashboard_template.html`, run `python build_dashboard.py` and confirm it
   exits 0 and the file regenerated.
3. **Never invent a number.** Every figure shown to a user traces to code that
   computed it from real data. If data is missing, say so on the page rather
   than filling the gap.
4. **Ask before anything outward-facing** — publishing to a new surface, emailing
   or messaging anyone, adding a real person's data, changing repo visibility.
5. **Ask before adding a dependency.** The stack is two packages. Keep it that way
   unless there is a real reason, and log it in `context/decisions.md`.

## How to run it

```bash
python fetch_garmin_data.py --days 180   # pull from Garmin into data/
python build_dashboard.py                # render data/ into docs/index.html
```

`login.py` is the only script that touches a password, and it is interactive —
never run it unattended, and never ask me for my Garmin password in chat.

CI (`.github/workflows/garmin-sync.yml`) runs the same two commands daily at
05:30 UTC and commits `data/` and `docs/` back to `main`.

## Conventions

- **Python, standard library first.** Dependencies: `garminconnect`, `curl_cffi`.
- **The dashboard is self-contained.** No CDN, no external assets, no network at
  view time. It has to work from a `file://` URL.
- **Garmin's shapes vary by device.** Probe candidate keys; a card with no data
  hides itself rather than rendering an empty frame. Follow that pattern.
- **`data/` and `docs/` are build outputs.** Committed on purpose, never hand-edited.
- **Comments explain why, formulas explain themselves.** Every derived metric is
  documented beside its implementation. Match that density.
- **Commit messages say what changed and why**, in plain sentences.

## Definition of done

A change is done when: it runs, the dashboard rebuilds, the numbers are
traceable, the spec (if there was one) is ticked off, `ROADMAP.md` reflects
reality, and there is a line in `REVIEW.md` if something shipped.
