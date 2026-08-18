# Routines

Step-by-step procedures. When one is invoked, follow it in order and do not
improvise the sequence — the point of a routine is that it comes out the same
way every time.

These are written procedures, not automation, on purpose: automating a process
before running it twice by hand tends to automate the wrong process. See
`context/decisions.md`. The only scheduled thing in this repo is the daily
Garmin sync in `.github/workflows/garmin-sync.yml`.

## Files

| Routine | When |
|---|---|
| `weekly-review.md` | Monday, or whenever the week needs looking at |
| `ship-a-change.md` | Any change to code that the dashboard depends on |
| `sync-health-check.md` | When the data looks stale or a sync failed |

## Writing a new one

A routine earns its place when a sequence has been done twice and got done
differently the second time. Numbered steps, one action each, and a last step
that says where the result is recorded.
