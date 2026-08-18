"""Render data/ into a self-contained dashboard at docs/index.html.

    python build_dashboard.py

No network access and no external assets -- the HTML embeds its own data and
draws its own SVG, so it works from a file:// URL or GitHub Pages alike.

Garmin returns different shapes depending on device and firmware, so every
extractor here probes a list of candidate keys and a card that ends up with no
data hides itself rather than rendering an empty frame.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

import analytics

DATA_DIR = Path("data")
OUT_DIR = Path("docs")
OUT_FILE = OUT_DIR / "index.html"
TEMPLATE_FILE = Path("dashboard_template.html")

M_PER_KM = 1000.0
SCHEMA = 2  # must match fetch_garmin_data.py


def pick(d: Any, *keys: str, default: Any = None) -> Any:
    """First present, non-null value among keys. Tolerates non-dicts."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        v = d.get(k)
        if v is not None:
            return v
    return default


def as_float(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f  # drop NaN


def day_key(v: Any) -> str | None:
    """Normalise assorted Garmin date encodings to YYYY-MM-DD."""
    if isinstance(v, (int, float)) and v > 1e11:  # epoch millis
        return datetime.fromtimestamp(v / 1000).date().isoformat()
    if isinstance(v, str) and len(v) >= 10:
        candidate = v[:10]
        try:
            date.fromisoformat(candidate)
        except ValueError:
            return None
        return candidate
    return None


def series_from(rows: Iterable[Any], date_keys: tuple, value_keys: tuple,
                scale: float = 1.0) -> list[dict]:
    """Build a sorted [{d, v}] series from a list of Garmin records."""
    out: dict[str, float] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        d = day_key(pick(row, *date_keys))
        v = as_float(pick(row, *value_keys))
        if d and v is not None and v > 0:
            out[d] = v * scale
    return [{"d": k, "v": round(out[k], 2)} for k in sorted(out)]


# --------------------------------------------------------------------------
# extractors
# --------------------------------------------------------------------------

def is_foot_sport(type_key: str) -> bool:
    """min/km is only meaningful on foot. Cyclists read km/h, swimmers /100m."""
    k = type_key.lower()
    if "cycl" in k or "bike" in k or "biking" in k or "swim" in k:
        return False
    return any(w in k for w in ("run", "walk", "hik", "treadmill"))


def activity_stats(activities: list[dict]) -> dict:
    """Weekly volume, sport split, recent list, and headline totals."""
    weekly_km: dict[str, float] = defaultdict(float)
    weekly_hours: dict[str, float] = defaultdict(float)
    by_type: dict[str, dict] = defaultdict(lambda: {"count": 0, "km": 0.0, "hours": 0.0})

    total_km = total_hours = total_elev = 0.0
    recent = []

    for a in activities:
        if not isinstance(a, dict):
            continue
        start = day_key(pick(a, "startTimeLocal", "startTimeGMT"))
        dist_m = as_float(pick(a, "distance", default=0)) or 0.0
        dur_s = as_float(pick(a, "duration", "elapsedDuration", default=0)) or 0.0
        elev = as_float(pick(a, "elevationGain", default=0)) or 0.0

        km = dist_m / M_PER_KM
        hours = dur_s / 3600.0
        total_km += km
        total_hours += hours
        total_elev += elev

        type_obj = a.get("activityType") or {}
        tkey = pick(type_obj, "typeKey", default="other") if isinstance(type_obj, dict) else "other"
        tname = str(tkey).replace("_", " ").title()
        by_type[tname]["count"] += 1
        by_type[tname]["km"] += km
        by_type[tname]["hours"] += hours

        if start:
            d = date.fromisoformat(start)
            monday = (d - timedelta(days=d.weekday())).isoformat()
            weekly_km[monday] += km
            weekly_hours[monday] += hours

        if len(recent) < 25:
            recent.append({
                "date": start or "",
                "name": pick(a, "activityName", default="Activity"),
                "type": tname,
                "km": round(km, 2),
                "duration": round(dur_s),
                "avg_hr": as_float(pick(a, "averageHR")),
                "max_hr": as_float(pick(a, "maxHR")),
                "calories": as_float(pick(a, "calories")),
                "elev": round(elev),
                "pace_s_per_km": (
                    round(dur_s / km)
                    if km > 0.3 and is_foot_sport(str(tkey)) else None
                ),
                "avg_speed": as_float(pick(a, "averageSpeed")),
                "training_effect": as_float(pick(a, "aerobicTrainingEffect")),
                "load": as_float(pick(a, "activityTrainingLoad")),
            })

    types = sorted(
        (
            {"name": k, "count": v["count"], "km": round(v["km"], 1),
             "hours": round(v["hours"], 1)}
            for k, v in by_type.items()
        ),
        key=lambda x: x["count"],
        reverse=True,
    )

    return {
        "weekly_km": [{"d": k, "v": round(weekly_km[k], 1)} for k in sorted(weekly_km)],
        "weekly_hours": [{"d": k, "v": round(weekly_hours[k], 2)} for k in sorted(weekly_hours)],
        "types": types,
        "recent": recent,
        "totals": {
            "count": len(activities),
            "km": round(total_km, 1),
            "hours": round(total_hours, 1),
            "elev": round(total_elev),
        },
    }


def vo2max_series(raw: Any) -> list[dict]:
    """get_max_metrics_range returns generic/cycling VO2max blocks.

    The calendarDate lives inside the "generic" block, not on the row, so the
    date has to be read from whichever of the two actually carries it.
    """
    if isinstance(raw, list):
        rows = raw
    elif isinstance(raw, dict):
        rows = raw.get("metrics", [])
    else:
        rows = []

    out: dict[str, float] = {}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        generic = row.get("generic") if isinstance(row.get("generic"), dict) else row
        d = day_key(pick(generic, "calendarDate", "date")) or \
            day_key(pick(row, "calendarDate", "date"))
        v = as_float(pick(generic, "vo2MaxPreciseValue", "vo2MaxValue"))
        if d and v:
            out[d] = v
    return [{"d": k, "v": out[k]} for k in sorted(out)]


def sleep_range_rows(raw: Any) -> dict[str, dict]:
    """get_sleep_daily nests everything under "values". Far wider coverage
    than the per-day window, so it is worth unpacking properly."""
    out: dict[str, dict] = {}
    for row in (raw or []):
        if not isinstance(row, dict):
            continue
        d = day_key(pick(row, "calendarDate", "date"))
        values = row.get("values") if isinstance(row.get("values"), dict) else row
        if d and isinstance(values, dict):
            out[d] = values
    return out


def daily_series(daily: dict, field: str, scale: float = 1.0,
                 positive: bool = True) -> list[dict]:
    """Series from one field of the compact per-day records."""
    out: dict[str, float] = {}
    for key, rec in (daily or {}).items():
        v = as_float(pick(rec, field))
        if v is not None and (v > 0 or not positive):
            out[key] = round(v * scale, 2)
    return [{"d": k, "v": out[k]} for k in sorted(out)]


def sleep_series(daily: dict, range_rows: dict[str, dict]) -> list[dict]:
    """Prefer per-day detail, fall back to the much wider range endpoint."""
    out = {p["d"]: p["v"] for p in daily_series(daily, "sleep_seconds", 1 / 3600.0)}

    for d, values in range_rows.items():
        secs = as_float(pick(values, "totalSleepTimeInSeconds",
                             "sleepTimeSeconds", "totalSleepSeconds"))
        if secs and d not in out:
            out[d] = round(secs / 3600.0, 2)

    return [{"d": k, "v": out[k]} for k in sorted(out)]


def steps_series(daily: dict, range_steps: Any) -> list[dict]:
    out: dict[str, float] = {}
    for row in (range_steps or []):
        if not isinstance(row, dict):
            continue
        d = day_key(pick(row, "calendarDate", "date"))
        v = as_float(pick(row, "totalSteps", "steps"))
        if d and v:
            out[d] = v
    for p in daily_series(daily, "steps"):
        out.setdefault(p["d"], p["v"])
    return [{"d": k, "v": out[k]} for k in sorted(out)]


def rhr_series(raw: Any, daily: dict, range_rows: dict[str, dict]) -> list[dict]:
    """get_rhr_daily nests the value under "values"; older payloads are flat."""
    out: dict[str, float] = {}
    for row in (raw or []):
        if not isinstance(row, dict):
            continue
        d = day_key(pick(row, "calendarDate", "date"))
        values = row.get("values")
        v = as_float(
            pick(values, "restingHeartRate", "wellnessRestingHeartRate")
            if isinstance(values, dict) else pick(row, "restingHeartRate")
        )
        if d and v:
            out[d] = v

    # Per-day records, then the sleep range, backfill days the RHR endpoint
    # skipped -- the nightly sleep payload carries resting HR too.
    for p in daily_series(daily, "resting_hr"):
        out.setdefault(p["d"], p["v"])

    for d, values in range_rows.items():
        v = as_float(pick(values, "restingHeartRate"))
        if v:
            out.setdefault(d, v)

    return [{"d": k, "v": out[k]} for k in sorted(out)]


def weight_series(raw: Any) -> list[dict]:
    """Weigh-ins come back in grams, and latestWeight is itself an object."""
    rows = raw.get("dailyWeightSummaries", []) if isinstance(raw, dict) else (raw or [])
    out: dict[str, float] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        d = day_key(pick(row, "summaryDate", "calendarDate", "date"))
        latest_obj = row.get("latestWeight")
        grams = as_float(
            pick(latest_obj, "weight") if isinstance(latest_obj, dict)
            else pick(row, "latestWeight", "weight")
        )
        if d and grams:
            out[d] = round(grams / 1000.0, 1)
    return [{"d": k, "v": out[k]} for k in sorted(out)]


def race_predictions(raw: Any) -> list[dict]:
    rec = raw[0] if isinstance(raw, list) and raw else raw
    if not isinstance(rec, dict):
        return []
    labels = [("5K", "time5K"), ("10K", "time10K"),
              ("Half Marathon", "timeHalfMarathon"), ("Marathon", "timeMarathon")]
    out = []
    for label, key in labels:
        secs = as_float(rec.get(key))
        if secs:
            out.append({"label": label, "seconds": round(secs)})
    return out


# Garmin identifies each personal record by typeId; the activityName is just
# the place it happened, which says nothing about which
# record it is. These labels and units come from inspecting live payloads.
PR_TYPES: dict[int, tuple[str, str]] = {
    1:  ("Best 1 km", "time"),
    2:  ("Best 1 mile", "time"),
    3:  ("Best 5 km", "time"),
    4:  ("Best 10 km", "time"),
    5:  ("Best half marathon", "time"),
    6:  ("Best marathon", "time"),
    7:  ("Longest run", "distance"),
    8:  ("Longest ride", "distance"),
    9:  ("Biggest ascent", "elevation"),
    10: ("Best 20 min power", "power"),
    12: ("Most steps in a day", "count"),
    13: ("Most steps in a week", "count"),
    14: ("Most steps in a month", "count"),
    15: ("Longest goal streak", "days"),
    16: ("Current goal streak", "days"),
    17: ("Longest swim", "metres"),
    18: ("Best 100 m swim", "time"),
    19: ("Best 400 m swim", "time"),
    20: ("Best 750 m swim", "time"),
}


def pr_kind_from_label(label: str) -> str:
    """Fallback for typeIds not in the table above."""
    low = label.lower()
    if "longest" in low or "distance" in low:
        return "distance"
    if "ascent" in low or "elevation" in low or "climb" in low:
        return "elevation"
    if "step" in low:
        return "count"
    return "time"


def personal_records(raw: Any) -> list[dict]:
    rows = raw if isinstance(raw, list) else (raw or {}).get("personalRecords", [])
    out = []
    for r in rows or []:
        if not isinstance(r, dict):
            continue

        value = as_float(pick(r, "value"))
        if not value:  # zero-valued records are placeholders, not achievements
            continue

        tid = pick(r, "typeId")
        known = PR_TYPES.get(int(tid)) if isinstance(tid, (int, float)) else None
        activity = pick(r, "activityName", "typeName")

        if known:
            label, kind = known
        else:
            label = str(activity or "Record")
            kind = pr_kind_from_label(label)

        when = day_key(
            pick(r, "activityStartDateTimeLocalFormatted", "prStartTimeLocal",
                 "prStartTimeGmt", "activityStartDateTimeInGMT")
        )

        out.append({
            "label": label,
            "value": value,
            "kind": kind,
            "where": str(activity) if known and activity else "",
            "date": when or "",
        })

    # Present in the order the table above defines, not Garmin's.
    order = {label: i for i, (label, _) in enumerate(PR_TYPES.values())}
    out.sort(key=lambda r: order.get(r["label"], 99))
    return out[:16]


def latest(series: list[dict]) -> float | None:
    return series[-1]["v"] if series else None


def build_payload() -> dict:
    summary_path = DATA_DIR / "garmin_data.json"
    activities_path = DATA_DIR / "activities.json"

    if not summary_path.exists():
        raise FileNotFoundError(
            f"{summary_path} not found. Run `python fetch_garmin_data.py` first."
        )

    data = json.loads(summary_path.read_text(encoding="utf-8"))

    if data.get("schema") != SCHEMA:
        raise ValueError(
            f"{summary_path} uses schema {data.get('schema', 1)}, "
            f"but this build expects {SCHEMA}.\n"
            "Re-run `python fetch_garmin_data.py` to regenerate it."
        )

    activities = []
    if activities_path.exists():
        activities = json.loads(activities_path.read_text(encoding="utf-8"))

    ranges = data.get("ranges", {})
    daily = data.get("daily", {})
    profile = data.get("profile", {})

    acts = activity_stats(activities)

    sleep_rows = sleep_range_rows(ranges.get("sleep_daily"))

    charts = {
        "weekly_km": acts["weekly_km"],
        "weekly_hours": acts["weekly_hours"],
        "vo2max": vo2max_series(ranges.get("vo2max")),
        "resting_hr": rhr_series(ranges.get("resting_hr"), daily, sleep_rows),
        "sleep": sleep_series(daily, sleep_rows),
        "sleep_score": daily_series(daily, "sleep_score"),
        "readiness": daily_series(daily, "readiness"),
        "stress": daily_series(daily, "stress_avg"),
        "steps": steps_series(daily, ranges.get("daily_steps")),
        "calories": daily_series(daily, "calories"),
        "body_battery": daily_series(daily, "bb_high"),
        "weight": weight_series(ranges.get("weight")),
    }

    recent_km = sum(w["v"] for w in acts["weekly_km"][-4:])

    return {
        "generated_at": data.get("generated_at", ""),
        "window": data.get("window", {}),
        "athlete": profile.get("name") or "Athlete",
        "devices": [pick(d, "productDisplayName", "displayName", default="")
                    for d in (profile.get("devices") or []) if isinstance(d, dict)][:3],
        "totals": acts["totals"],
        "kpis": {
            "vo2max": latest(charts["vo2max"]),
            "resting_hr": latest(charts["resting_hr"]),
            "readiness": latest(charts["readiness"]),
            "sleep": latest(charts["sleep"]),
            "last_4wk_km": round(recent_km, 1),
        },
        "charts": charts,
        "types": acts["types"],
        "recent": acts["recent"],
        "races": race_predictions(ranges.get("race_predictions")),
        "records": personal_records(profile.get("personal_records")),
        "failures": data.get("failures", []),
        "analytics": analytics.build(data, activities),
    }


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

def main() -> int:
    try:
        payload = build_payload()
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    if not TEMPLATE_FILE.exists():
        print(f"{TEMPLATE_FILE} not found.", file=sys.stderr)
        return 1

    html = (
        TEMPLATE_FILE.read_text(encoding="utf-8")
        .replace("__TITLE__", f"{payload['athlete']} — Training Dashboard")
        # </script> inside the JSON payload would close the host tag early.
        .replace("__DATA__", json.dumps(payload).replace("</", "<\\/"))
    )

    OUT_DIR.mkdir(exist_ok=True)
    OUT_FILE.write_text(html, encoding="utf-8")
    kb = OUT_FILE.stat().st_size / 1024
    print(f"Wrote {OUT_FILE} ({kb:.0f} KB)")
    print(f"  activities: {payload['totals']['count']}")
    charted = [k for k, v in payload["charts"].items() if len(v) >= 2]
    print(f"  charts with data: {', '.join(charted) if charted else 'none'}")
    an = payload.get("analytics") or {}
    print(f"  derived series: {', '.join(k for k, v in an.items() if isinstance(v, list) and v)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
