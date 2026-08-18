# Garmin Training Dashboard

Pulls your Garmin Connect training data and renders a self-contained HTML
dashboard. Runs itself daily via GitHub Actions. No Strava subscription, no
third-party service holding your data.

## What you get

**Headline numbers** — activity count, total distance, moving time, elevation,
current VO₂ max, resting HR, training readiness, sleep, last-4-week volume.

**Charts** — weekly volume (km and hours), VO₂ max trend, resting HR, training
readiness, sleep duration, daily stress, daily steps, Body Battery, weight.
Every chart has hover tooltips.

**Tables** — race predictions (5K/10K/half/marathon), sport breakdown, personal
records, and your 25 most recent activities with pace, HR and elevation.

Charts whose metrics your device does not record hide themselves rather than
rendering empty frames.

## Setup

### 1. Install

```bash
pip install -r requirements.txt
```

### 2. Log in once

```bash
python login.py
```

Enter your Garmin email, then your password (hidden as you type, and prompted
for an MFA code if your account uses one). The password is used once to obtain
OAuth tokens and is never stored or logged.

This writes two things:

- `tokens/` — your local token store, used by every later run
- `garmin_token_b64.txt` — the same tokens encoded for CI

### 3. Verify the connection

```bash
python fetch_garmin_data.py --days 7
```

Prints the account name it connected as, then writes `data/`.

### 4. Build the dashboard

```bash
python build_dashboard.py
```

Open `docs/index.html` in any browser.

### 5. Automate it

Create a GitHub repo and push:

```bash
git init && git add . && git commit -m "Garmin dashboard" && git branch -M main
```

Then add the remote GitHub gives you and push.

Add the CI secret:

1. Repo → **Settings → Secrets and variables → Actions → New repository secret**
2. Name: `GARMIN_TOKENS_B64`
3. Value: the entire contents of `garmin_token_b64.txt`
4. **Delete `garmin_token_b64.txt` locally** once saved (it is gitignored, but
   there is no reason to keep a token bundle lying around)

Serve the dashboard:

- Repo → **Settings → Pages** → Source: `main` branch, `/docs` folder
- Your dashboard lands at `https://<user>.github.io/<repo>/`

Run it once by hand to confirm: **Actions → Garmin sync → Run workflow**.
After that it runs daily at 05:30 UTC and commits refreshed data back.

## Files

| File | Role |
|---|---|
| `login.py` | One-time interactive login. The only script that touches a password. |
| `garmin_auth.py` | Loads tokens from `$GARMIN_TOKENS_B64` (CI) or `tokens/` (local). |
| `fetch_garmin_data.py` | Pulls Garmin data into `data/`. |
| `build_dashboard.py` | Renders `data/` into `docs/index.html`. |
| `.github/workflows/garmin-sync.yml` | Daily scheduled run. |

## Options

```bash
python fetch_garmin_data.py --days 365        # wider history window
python fetch_garmin_data.py --full            # ~3 years of activities
python fetch_garmin_data.py --daily-window 90 # more per-day detail (slower)
python fetch_garmin_data.py --keep-raw        # also dump unreduced payloads
```

`--days` sets the range-endpoint window; `--daily-window` independently controls
how many days of per-day detail are pulled (default 45). Widening either one
backfills history — the activity cache fetches both newer and older gaps.

Activity history is cached in `data/activities.json` and merged on each run, so
scheduled syncs only fetch new days. Delete that file to force a full refetch.

### Why the data file stays small

Garmin's per-day responses carry minute-by-minute arrays — roughly 140 KB per
night for sleep alone — that the dashboard reduces to one point per day anyway.
`fetch_garmin_data.py` reduces each day to ~15 numbers before writing, keeping a
sync near 1 MB instead of 12 MB. That matters because the workflow commits the
file daily; unreduced, the repo would grow by gigabytes a year.

Use `--keep-raw` to also write `data/raw_daily.json` with the full payloads. It
is gitignored, and nothing reads it — it is there for ad-hoc analysis.

The on-disk format carries a `schema` version. If `build_dashboard.py` reports a
schema mismatch, re-run the fetch to regenerate `data/garmin_data.json`.

## Notes

**Rate limits.** Garmin throttles aggressively. Per-day endpoints are paced with
a delay and capped to a recent window; range endpoints do the heavy lifting. If
you see HTTP 429, raise `CALL_DELAY` in `fetch_garmin_data.py`.

**Token expiry.** Tokens last roughly a year, and are invalidated if you change
your Garmin password. When the sync starts failing with an authentication error,
re-run `python login.py` and update the `GARMIN_TOKENS_B64` secret. Tokens
refreshed during a CI run are not written back to the secret, which is why the
underlying refresh token's lifetime is what matters.

**Missing metrics.** Garmin enables metrics per device. Endpoints your watch
does not populate are reported at the end of a sync and listed in the dashboard
footer — that is expected, not an error.

**Privacy.** This is an unofficial client using the same endpoints as the Garmin
Connect web app. Your data stays in your repo. If your training history is
private, keep the repo private — note that GitHub Pages on a private repo
requires a paid plan, in which case open `docs/index.html` locally instead.
