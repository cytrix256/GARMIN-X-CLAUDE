# Data

What exists, where it comes from, and where the gaps are. Check here before
designing anything that assumes a metric is available.

Verified against `data/garmin_data.json` on 2026-08-18.

## Pipeline

    Garmin Connect
      -> fetch_garmin_data.py  -> data/garmin_data.json, data/activities.json
      -> analytics.py          -> derived metrics
      -> build_dashboard.py + dashboard_template.html
      -> docs/index.html

`data/` and `docs/` are committed build outputs. CI regenerates both daily.

## data/garmin_data.json

Top-level keys: `schema`, `generated_at`, `window`, `profile`, `ranges`,
`daily`, `activity_count_fetched`, `failures`.

`schema` is versioned and must match between `fetch_garmin_data.py` and
`build_dashboard.py`. On a mismatch, re-fetch rather than patching the reader.

### daily — one reduced record per day

Keyed by date. Currently **45 days** — this is the tight constraint on
everything derived. Fields:

`readiness`, `readiness_level`, `resting_hr`, `sleep_seconds`, `sleep_score`,
`sleep_deep`, `sleep_light`, `sleep_rem`, `sleep_awake`, `stress_avg`,
`stress_max`, `bb_high`, `bb_low`, `steps`, `floors`, `calories`,
`intensity_min`, `vigorous_min`.

Garmin's raw per-day responses carry minute-by-minute arrays (~140 KB per night
for sleep alone). `reduce_day()` collapses each day to ~15 numbers before
writing, because CI commits this file daily. `--keep-raw` dumps the unreduced
payloads to a gitignored file for ad-hoc work.

### ranges — longer history, coarser

Currently **180 days**: `body_battery`, `calories_daily`, `daily_steps`,
`endurance_score`, `hill_score`, `hrv_range`, `intensity_minutes`,
`race_predictions`, `resting_hr`, `running_tolerance`, `sleep_daily`, `vo2max`,
`weekly_stress`, `weight`.

`sleep_daily` is the valuable one: it carries nightly sleep together with
resting HR, respiration and SpO2, and it supplies Garmin's own `sleepNeed` per
night, which is what sleep debt is measured against.

`analytics.merged_daily()` merges `daily` with the range rows, which is what
takes correlations from ~45 samples to ~175.

### failures

Endpoints that returned nothing. Empty as of the last sync. Garmin enables
metrics per device, so a populated `failures` list is usually a device
limitation rather than a bug. It surfaces in the dashboard footer.

## data/activities.json

Individual activities, cached and merged on each run so scheduled syncs only
fetch new days. Delete it to force a full refetch. This is the input to
`daily_load()`, and therefore to every training-load metric.

## Derived metrics (analytics.py)

`analytics.build()` returns: `days`, `fitness_fatigue`, `acwr`, `monotony`,
`hrv`, `recovery`, `sleep_debt`, `insights`, `scatter`, `weekday`.

Each formula is documented at its implementation. Constants worth knowing:
`CTL_TAU = 42`, `ATL_TAU = 7` — the endurance-sport convention for the Banister
model.

## Known gaps

- **No GPS traces.** Nothing route-, segment- or map-shaped is possible without
  changing the fetch.
- **45 days of per-day detail** against 180 days of range data. Widening it is
  rate-limit-bound, not code-bound. Roadmap item 3.
- **Rate limits are real.** Garmin throttles aggressively. Per-day endpoints are
  paced by `CALL_DELAY` in `fetch_garmin_data.py`; range endpoints do the heavy
  lifting. HTTP 429 means raise the delay, not retry harder.
- **Tokens expire** roughly yearly, and immediately on a password change. CI
  cannot write refreshed tokens back to the secret, so the refresh token's
  lifetime is what actually matters.
