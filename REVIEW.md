# Review log

Newest first. One entry per thing shipped, or per review cycle. The point is to
be honest about whether the work moved the promise, not to log activity.

Each entry answers four questions:

- **What shipped** — plainly, what is now true that was not before
- **Against the promise** — did this make it more like paid Strava, individualised, free?
- **What is wrong with it** — the known weakness, stated before someone finds it
- **Next** — what this makes possible or necessary

---

## 2026-08-18 — Baseline review of what exists

**What shipped** (before this workspace existed): a working pipeline. Garmin
Connect → `data/` → `analytics.py` → `docs/index.html`, running daily in CI and
committing itself back. The dashboard has six tabs and carries derived metrics
Garmin does not surface: fitness/fatigue/form from a Banister model, acute:chronic
workload ratio, Foster monotony and strain, HRV against a personal band, a
transparent recovery score, rolling sleep debt, and lagged correlations with `n`
reported so thin data looks thin.

**Against the promise.** Strongly on "individualised" and "free" — the derived
layer genuinely needs history and a model, which is exactly what a subscription
usually sells. Weak on "replacement": the output is a wall of charts. Charts are
what you look at when you already know what you are looking for. The paid thing
being replaced also tells you what to think.

**What is wrong with it.**
- Nothing reads the numbers *for* me. The interpretation is left entirely to the reader.
- `daily` covers 45 days against a 180-day range window, so anything keyed on
  per-day detail runs on a third of the available history.
- Nobody has confirmed whether this repo is public. It contains resting heart
  rate, sleep, and body weight.
- One user, one device, one lifetime of data. Every "it works" so far is n=1.

**Next.** `specs/001-weekly-training-review.md` — make the data say something.

---

## Template

```
## YYYY-MM-DD — <what it was>

**What shipped**

**Against the promise**

**What is wrong with it**

**Next**
```
