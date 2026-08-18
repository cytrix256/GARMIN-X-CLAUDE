# Me — the only customer

Owner of the repo, the watch, and the data. Everything here is built for this
one reader until ROADMAP.md says otherwise.

## Trains

From `data/activities.json`, 73 activities between 2026-02-19 and 2026-08-16:

| Sport | Sessions |
|---|---|
| Strength training | 46 |
| Indoor cardio | 11 |
| Running | 9 |
| Lap swimming | 4 |
| Cycling (indoor + outdoor) | 3 |

Roughly three sessions a week, strength-dominant, with running and swimming as
supporting work. **This is not an endurance-athlete profile**, and that matters —
see the open question below.

## Device and data

A Garmin watch that populates readiness, sleep stages, HRV, resting HR, stress,
Body Battery, steps, intensity minutes, VO2 max, race predictions, weight and
per-activity training load. No endpoints have failed on recent syncs.

History: 180 days of range data, 45 days of per-day detail, and an activity
cache that can be backfilled further.

## Wants

- To not pay for Strava Premium.
- Numbers that mean something for this body, not for a population.
- To see the working. A score with no visible inputs is not trusted.
- Something worth opening on a Monday morning without being reminded to.

## Would stop using it if

- It becomes another dashboard to check out of guilt.
- It says something confidently wrong — a recommendation the data does not
  support is worse than saying nothing.
- Maintaining it costs more time than the subscription cost money.

## Open questions

- **The models assume endurance training.** `CTL_TAU = 42` / `ATL_TAU = 7`, the
  acute:chronic workload bands, and Foster monotony and strain all come from
  endurance and team-sport literature. With 46 of 73 sessions being strength
  work, "training load" is measuring something the model was not designed for.
  Worth deciding: recalibrate, caveat it on the page, or accept it knowingly.
- **Which Strava paid features were actually used** before cancelling? The whole
  v1 scope rests on the answer being "the analysis".
- **What is a good week?** The review cannot say "good week" until it knows what
  this reader is training toward. Nothing in the data says.
