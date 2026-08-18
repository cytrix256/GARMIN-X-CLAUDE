# Roadmap

Updated 2026-08-18.

## Current goal

**A simple process, and one demo that proves it.** The demo is a weekly
training review: a one-pager generated from my own data that says what my week
was, what it means, and what to do next. If I would actually read it on a
Monday, the loop works.

Not the goal right now: friends, accounts, coaching plans, maps, anything
multi-user.

## Now

| # | Item | Why | Done when |
|---|---|---|---|
| 1 | **Weekly training review demo** — `specs/001-weekly-training-review.md` | The demo. Turns metrics into something readable | A file lands in `demos/`, generated from real data, and I read it without wincing |
| 2 | **Confirm repo visibility** | Health data + GitHub Pages. Nobody has actually checked whether this repo is public | Answer written into `context/product.md`, and the choice is deliberate |
| 3 | **Widen the daily window** | `daily` holds 45 days against a 180-day range window, so half the derived metrics run on thin history | A sync fetches ≥120 days of per-day detail without tripping Garmin's rate limit |

## Next

- **Prose that survives contact.** The review's wording is generated once and
  then read every week. Check it still reads well when the week was boring, when
  the week was terrible, and when data is missing.
- **A second week.** Run the routine twice. A process that works once is a demo;
  a process that works twice is a process.
- **Trend memory.** The review should know what it said last week and notice
  when something changed.

## Later

Not committed to, and deliberately vague until the Now column is empty.

- **Friends.** One friend, their own tokens, their own dashboard. Needs the
  onboarding path to be less than an hour of my time, and a real answer on where
  their data lives.
- **Coaching.** Move from "here is what happened" to "here is what to do".
  Only worth it once the analytics have earned trust.
- **The bits of Strava I have not replaced.** Segments, routes, maps. Requires
  GPS traces we do not currently fetch. Cheapest to skip until I miss them.

## Explicitly not doing

- A social feed, kudos, or leaderboards. The point is that this is for me.
- A hosted service, accounts, or billing. The promise is free of charge.
- A mobile app. The dashboard is a web page and that is enough.
