"""Pull training data from Garmin Connect into data/.

    python fetch_garmin_data.py              # default 180-day window
    python fetch_garmin_data.py --days 7     # quick connection test
    python fetch_garmin_data.py --full       # 3 years of activity history

Design notes:
  * Range endpoints are preferred over per-day loops -- one HTTP call for a
    whole series instead of one per day. Garmin throttles aggressively.
  * Per-day endpoints (sleep, readiness, HRV detail) are limited to a recent
    window and paced with a delay.
  * Activity history is cached and merged, so scheduled runs only fetch the
    days they have not seen. Deleting data/activities.json forces a refetch.
  * Every endpoint is individually guarded. Garmin enables metrics per device,
    so a missing endpoint is normal, not fatal.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable

from garmin_auth import authenticate
from sanitize import (
    collect_identifiers,
    sanitize_activities,
    sanitize_payload,
    verify_clean,
)

DATA_DIR = Path("data")
ACTIVITIES_FILE = DATA_DIR / "activities.json"
SUMMARY_FILE = DATA_DIR / "garmin_data.json"

# Seconds between per-day API calls. Lower is faster but risks HTTP 429.
CALL_DELAY = 0.35
# Per-day endpoints only run over this many recent days.
DAILY_WINDOW = 45

_failures: list[str] = []
_attempts = 0

# Above this share of failed calls the sync is not "partially degraded", it is
# broken -- exit non-zero so a scheduled run goes red instead of quietly
# committing a nearly empty file.
FAILURE_ABORT_RATIO = 0.30


def safe(label: str, fn: Callable[[], Any], default: Any = None) -> Any:
    """Run one API call, converting any failure into a logged default."""
    global _attempts
    _attempts += 1
    try:
        result = fn()
    except Exception as exc:
        _failures.append(f"{label}: {type(exc).__name__}: {exc}")
        print(f"    ! {label} unavailable ({type(exc).__name__})")
        return default
    return default if result is None else result


def iso(d: date) -> str:
    return d.isoformat()


def fetch_activities(client, start: date, end: date) -> list[dict]:
    """Fetch activities, merging into the on-disk cache by activityId."""
    cached: list[dict] = []
    if ACTIVITIES_FILE.exists():
        try:
            cached = json.loads(ACTIVITIES_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print("    ! activities cache corrupt, refetching from scratch")
            cached = []

    by_id = {str(a.get("activityId")): a for a in cached if a.get("activityId")}

    def cached_bound(reducer):
        stamps = [a.get("startTimeLocal", "")[:10] for a in by_id.values()]
        stamps = [s for s in stamps if s]
        if not stamps:
            return None
        try:
            return date.fromisoformat(reducer(stamps))
        except ValueError:
            return None

    newest = cached_bound(max)
    oldest = cached_bound(min)

    # Two windows, so widening --days backfills history instead of silently
    # returning only what the cache already covers.
    windows: list[tuple[date, date]] = []
    if newest is None:
        windows.append((start, end))
    else:
        windows.append((max(start, newest - timedelta(days=1)), end))
        if oldest and start < oldest:
            windows.append((start, oldest))

    print(f"  activities {iso(start)} -> {iso(end)} ({len(by_id)} cached)")

    added = 0
    for w_start, w_end in windows:
        if w_start > w_end:
            continue
        print(f"    window {iso(w_start)} -> {iso(w_end)}")
        fresh = safe(
            f"get_activities_by_date {iso(w_start)}",
            lambda a=w_start, b=w_end: client.get_activities_by_date(iso(a), iso(b)),
            default=[],
        )
        for act in fresh or []:
            aid = str(act.get("activityId"))
            if not aid:
                continue
            if aid not in by_id:
                added += 1
            by_id[aid] = act

    merged = sorted(
        by_id.values(), key=lambda a: a.get("startTimeLocal", ""), reverse=True
    )
    merged = sanitize_activities(merged)
    ACTIVITIES_FILE.write_text(json.dumps(merged, indent=1), encoding="utf-8")
    print(f"    {added} new, {len(merged)} total")
    return merged


def chunked(fn: Callable[[str, str], Any], start: date, end: date,
            days: int, label: str) -> list:
    """Call a range endpoint in slices and concatenate the results.

    Some Garmin range endpoints cap how wide a window they accept.
    """
    out: list = []
    cursor = start
    while cursor <= end:
        stop = min(end, cursor + timedelta(days=days - 1))
        part = safe(
            f"{label} {iso(cursor)}",
            lambda a=cursor, b=stop: fn(iso(a), iso(b)),
            default=[],
        )
        if isinstance(part, list):
            out.extend(part)
        elif part:
            out.append(part)
        cursor = stop + timedelta(days=1)
        time.sleep(CALL_DELAY)
    return out


def fetch_ranges(client, start: date, end: date) -> dict[str, Any]:
    """Series endpoints that accept a date range -- cheap, one call each."""
    s, e = iso(start), iso(end)
    print("  range metrics")
    return {
        "daily_steps": safe("daily_steps", lambda: client.get_daily_steps(s, e), []),
        "resting_hr": safe("rhr_daily", lambda: client.get_rhr_daily(s, e), []),
        "sleep_daily": safe("sleep_daily", lambda: client.get_sleep_daily(s, e), []),
        "calories_daily": safe(
            "calories_daily", lambda: client.get_calories_daily(s, e), []
        ),
        # Garmin rejects wide body-battery ranges with HTTP 400
        # ("requested date range is too big"), so ask in monthly slices.
        "body_battery": chunked(
            client.get_body_battery, start, end, days=28, label="body_battery"
        ),
        "vo2max": safe(
            "max_metrics_range", lambda: client.get_max_metrics_range(s, e), {}
        ),
        "hrv_range": safe("hrv_range", lambda: client.get_hrv_data_range(s, e), {}),
        "weight": safe("weigh_ins", lambda: client.get_weigh_ins(s, e), {}),
        "endurance_score": safe(
            "endurance_score", lambda: client.get_endurance_score(s, e), {}
        ),
        "hill_score": safe("hill_score", lambda: client.get_hill_score(s, e), {}),
        "intensity_minutes": safe(
            "weekly_intensity_minutes",
            lambda: client.get_weekly_intensity_minutes(s, e),
            [],
        ),
        "weekly_stress": safe(
            "weekly_stress", lambda: client.get_weekly_stress(e, 52), []
        ),
        # get_race_predictions takes all three arguments or none at all --
        # passing only a date range raises ValueError.
        "race_predictions": safe(
            "race_predictions", lambda: client.get_race_predictions(), {}
        ),
        "running_tolerance": safe(
            "running_tolerance", lambda: client.get_running_tolerance(s, e), []
        ),
    }


def pick(d: Any, *keys: str) -> Any:
    """First present, non-null value among keys. Tolerates non-dicts."""
    if not isinstance(d, dict):
        return None
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return None


def reduce_day(summary: Any, sleep: Any, readiness: Any,
               status: Any, stress: Any) -> dict:
    """Collapse one day of raw payloads into the ~15 numbers we actually plot.

    Garmin's per-day responses carry minute-by-minute arrays -- hundreds of KB
    a day that the dashboard reduces to a single point anyway. Reducing here
    keeps the committed file small enough to version daily.
    """
    rec: dict[str, Any] = {}

    rec["steps"] = pick(summary, "totalSteps")
    rec["resting_hr"] = pick(summary, "restingHeartRate")
    rec["calories"] = pick(summary, "totalKilocalories")
    rec["floors"] = pick(summary, "floorsAscended")
    rec["bb_high"] = pick(summary, "bodyBatteryHighestValue")
    rec["bb_low"] = pick(summary, "bodyBatteryLowestValue")
    rec["intensity_min"] = pick(summary, "moderateIntensityMinutes")
    rec["vigorous_min"] = pick(summary, "vigorousIntensityMinutes")

    dto = sleep.get("dailySleepDTO") if isinstance(sleep, dict) else None
    if isinstance(dto, dict):
        rec["sleep_seconds"] = pick(dto, "sleepTimeSeconds")
        rec["sleep_deep"] = pick(dto, "deepSleepSeconds")
        rec["sleep_light"] = pick(dto, "lightSleepSeconds")
        rec["sleep_rem"] = pick(dto, "remSleepSeconds")
        rec["sleep_awake"] = pick(dto, "awakeSleepSeconds")
        rec["sleep_score"] = pick(
            pick(dto, "sleepScores") or {}, "overall"
        )
        if isinstance(rec["sleep_score"], dict):
            rec["sleep_score"] = pick(rec["sleep_score"], "value")

    first = readiness[0] if isinstance(readiness, list) and readiness else readiness
    rec["readiness"] = pick(first, "score", "trainingReadinessScore")
    rec["readiness_level"] = pick(first, "level")

    rec["training_status"] = pick(status, "trainingStatusKey", "trainingStatus")

    rec["stress_avg"] = pick(stress, "avgStressLevel", "overallStressLevel")
    rec["stress_max"] = pick(stress, "maxStressLevel")

    # Drop empty keys so a sparse day costs almost nothing.
    return {k: v for k, v in rec.items() if v is not None}


def fetch_daily(client, end: date, window: int,
                keep_raw: bool) -> tuple[dict[str, dict], dict]:
    """Per-day endpoints over a recent window, reduced to compact records."""
    days = [end - timedelta(days=i) for i in range(window)]
    compact: dict[str, dict] = {}
    raw: dict[str, dict] = {}

    print(f"  per-day metrics over {window} days")
    for i, d in enumerate(days, 1):
        key = iso(d)
        if i % 10 == 0 or i == len(days):
            print(f"    {i}/{len(days)} ({key})")

        summary = safe(
            f"user_summary {key}", lambda k=key: client.get_user_summary(k), {}
        )
        time.sleep(CALL_DELAY)
        sleep_raw = safe(f"sleep {key}", lambda k=key: client.get_sleep_data(k), {})
        time.sleep(CALL_DELAY)
        readiness = safe(
            f"readiness {key}", lambda k=key: client.get_training_readiness(k), []
        )
        time.sleep(CALL_DELAY)
        status = safe(
            f"training_status {key}", lambda k=key: client.get_training_status(k), {}
        )
        time.sleep(CALL_DELAY)
        stress = safe(
            f"stress {key}", lambda k=key: client.get_all_day_stress(k), {}
        )
        time.sleep(CALL_DELAY)

        rec = reduce_day(summary, sleep_raw, readiness, status, stress)
        if rec:
            compact[key] = rec

        if keep_raw:
            raw[key] = {
                "summary": summary, "sleep": sleep_raw, "readiness": readiness,
                "training_status": status, "stress": stress,
            }

    return compact, raw


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Garmin Connect data")
    parser.add_argument("--days", type=int, default=180, help="history window")
    parser.add_argument(
        "--full", action="store_true", help="fetch ~3 years of activities"
    )
    parser.add_argument(
        "--daily-window",
        type=int,
        default=DAILY_WINDOW,
        help="days of per-day detail metrics",
    )
    parser.add_argument(
        "--keep-raw",
        action="store_true",
        help="also dump unreduced per-day payloads to data/raw_daily.json "
             "(gitignored; hundreds of KB per day)",
    )
    args = parser.parse_args()

    end = date.today()
    start = end - timedelta(days=1095 if args.full else args.days)

    print("Authenticating...")
    try:
        client = authenticate()
    except (RuntimeError, ValueError) as exc:
        print(f"\n{exc}", file=sys.stderr)
        return 1

    name = safe("full_name", client.get_full_name, "Athlete")
    print(f"Connected as: {name}\n")

    DATA_DIR.mkdir(exist_ok=True)

    activities = fetch_activities(client, start, end)
    ranges = fetch_ranges(client, start, end)
    daily, raw_daily = fetch_daily(
        client, end, max(1, args.daily_window), args.keep_raw
    )

    if args.keep_raw:
        raw_path = DATA_DIR / "raw_daily.json"
        raw_path.write_text(json.dumps(raw_daily, indent=1), encoding="utf-8")
        print(f"  raw payloads -> {raw_path} ({raw_path.stat().st_size / 1e6:.1f} MB)")

    print("  profile and records")
    profile = {
        "name": name,
        "unit_system": safe("unit_system", client.get_unit_system, "metric"),
        "personal_records": safe("personal_record", client.get_personal_record, []),
        "devices": safe("devices", client.get_devices, []),
        "hr_zones": safe("heart_rate_zones", client.get_heart_rate_zones, []),
        "activity_count": safe("count_activities", client.count_activities, 0),
    }

    payload = {
        # Bumped when the on-disk shape changes, so the dashboard can tell a
        # stale file from a corrupt one.
        "schema": 2,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "window": {"start": iso(start), "end": iso(end)},
        "profile": profile,
        "ranges": ranges,
        "daily": daily,
        "activity_count_fetched": len(activities),
        "failures": _failures,
    }
    # Check the rendered text against the real values, not just key names.
    identifiers = sorted(
        collect_identifiers(payload)
        | {name, str(getattr(client, "display_name", "") or "")}
    )
    summary_text = json.dumps(sanitize_payload(payload), indent=1)
    verify_clean(summary_text, identifiers)
    verify_clean(ACTIVITIES_FILE.read_text(encoding="utf-8"), identifiers)
    SUMMARY_FILE.write_text(summary_text, encoding="utf-8")
    print(f"  sanitised: {len(identifiers)} identifying values checked for")

    size_kb = SUMMARY_FILE.stat().st_size / 1024
    print(f"\nWrote {SUMMARY_FILE} ({size_kb:.0f} KB) and {ACTIVITIES_FILE}")
    ratio = len(_failures) / _attempts if _attempts else 0.0
    print(
        f"Activities: {len(activities)}   "
        f"Failed calls: {len(_failures)}/{_attempts} ({ratio:.0%})"
    )

    if ratio > FAILURE_ABORT_RATIO:
        # Show distinct reasons rather than the same message a hundred times.
        reasons = sorted({f.split(": ", 1)[-1][:130] for f in _failures})
        print("\nToo many endpoints failed -- treating this sync as failed.",
              file=sys.stderr)
        for r in reasons[:5]:
            print(f"  {r}", file=sys.stderr)
        return 1

    if _failures:
        print("Unavailable endpoints are usually metrics your device does not record.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
