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

DATA_DIR = Path("data")
OUT_DIR = Path("docs")
OUT_FILE = OUT_DIR / "index.html"

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
    }


# --------------------------------------------------------------------------
# HTML
# --------------------------------------------------------------------------

HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  color-scheme: light;
  --page: #f9f9f7;
  --surface: #fcfcfb;
  --text-primary: #0b0b0b;
  --text-secondary: #52514e;
  --muted: #898781;
  --grid: #e1e0d9;
  --axis: #c3c2b7;
  --border: rgba(11,11,11,0.10);
  --series-1: #2a78d6;
  --series-2: #eb6834;
  --good: #0ca30c;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --page: #0d0d0d;
    --surface: #1a1a19;
    --text-primary: #ffffff;
    --text-secondary: #c3c2b7;
    --muted: #898781;
    --grid: #2c2c2a;
    --axis: #383835;
    --border: rgba(255,255,255,0.10);
    --series-1: #3987e5;
    --series-2: #d95926;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--page);
  color: var(--text-primary);
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  font-size: 15px;
  line-height: 1.5;
}
.wrap { max-width: 1180px; margin: 0 auto; padding: 32px 20px 64px; }
header { margin-bottom: 28px; }
h1 { font-size: 26px; margin: 0 0 6px; letter-spacing: -0.01em; }
.sub { color: var(--text-secondary); font-size: 13px; }
h2 { font-size: 15px; margin: 0 0 2px; }
.card-sub { color: var(--muted); font-size: 12px; margin-bottom: 14px; }
.grid { display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); }
.kpis { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); margin-bottom: 22px; }
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 16px 18px;
}
.kpi .label { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .06em; }
.kpi .value { font-size: 27px; font-weight: 600; letter-spacing: -0.02em; margin-top: 4px; }
.kpi .unit { font-size: 13px; color: var(--text-secondary); font-weight: 400; margin-left: 2px; }
.chart { width: 100%; height: 190px; display: block; overflow: visible; }
.wide { grid-column: 1 / -1; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
th {
  text-align: left; font-weight: 600; color: var(--muted); font-size: 11px;
  text-transform: uppercase; letter-spacing: .05em;
  padding: 6px 10px 6px 0; border-bottom: 1px solid var(--grid);
}
td { padding: 7px 10px 7px 0; border-bottom: 1px solid var(--grid); font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
td.name { font-variant-numeric: normal; }
.num { text-align: right; }
.scroll { overflow-x: auto; }
.chip {
  display: inline-block; padding: 1px 8px; border-radius: 99px;
  background: var(--grid); color: var(--text-secondary); font-size: 11px;
}
.tt {
  position: fixed; pointer-events: none; opacity: 0; transition: opacity .1s;
  background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 6px 10px; font-size: 12px; z-index: 20;
  box-shadow: 0 4px 14px rgba(0,0,0,.14); white-space: nowrap;
}
.tt .tt-d { color: var(--muted); font-size: 11px; }
.tt .tt-v { font-weight: 600; font-variant-numeric: tabular-nums; }
footer { margin-top: 32px; color: var(--muted); font-size: 12px; }
.empty { color: var(--muted); font-size: 13px; padding: 22px 0; text-align: center; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>__HEADING__</h1>
    <div class="sub" id="sub"></div>
  </header>
  <div class="kpis" id="kpis"></div>
  <div class="grid" id="grid"></div>
  <footer id="footer"></footer>
</div>
<div class="tt" id="tt"></div>

<script id="garmin-data" type="application/json">__DATA__</script>
<script>
const DATA = JSON.parse(document.getElementById('garmin-data').textContent);
const NS = 'http://www.w3.org/2000/svg';
const tt = document.getElementById('tt');

const fmtDate = d => {
  const dt = new Date(d + 'T00:00:00');
  return isNaN(dt) ? d : dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
};
const hms = s => {
  s = Math.round(s);
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
  return h ? `${h}:${String(m).padStart(2,'0')}:${String(sec).padStart(2,'0')}`
           : `${m}:${String(sec).padStart(2,'0')}`;
};
const pace = s => s ? `${Math.floor(s/60)}:${String(Math.round(s%60)).padStart(2,'0')}/km` : '—';
const kmh = ms => ms ? (ms * 3.6).toFixed(1) + ' km/h' : '—';

// A record's units depend on what kind of record it is, not its magnitude.
function fmtRecord(r) {
  switch (r.kind) {
    case 'distance':  return (r.value / 1000).toFixed(2) + ' km';
    // No thousands separator: in a de-DE locale "1.000 m" reads as 1 metre.
    case 'metres':    return Math.round(r.value) + ' m';
    case 'elevation': return Math.round(r.value) + ' m';
    case 'power':     return Math.round(r.value) + ' W';
    case 'days':      return Math.round(r.value) + (r.value === 1 ? ' day' : ' days');
    case 'count':     return Math.round(r.value).toLocaleString();
    default:          return hms(r.value);
  }
}

function el(tag, attrs = {}) {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  return n;
}
function showTip(evt, label, value) {
  tt.innerHTML = `<div class="tt-d">${label}</div><div class="tt-v">${value}</div>`;
  tt.style.opacity = 1;
  const pad = 14;
  let x = evt.clientX + pad, y = evt.clientY - pad;
  if (x + tt.offsetWidth > innerWidth - 8) x = evt.clientX - tt.offsetWidth - pad;
  if (y < 8) y = 8;
  tt.style.left = x + 'px';
  tt.style.top = y + 'px';
}
const hideTip = () => { tt.style.opacity = 0; };

// Shared plot frame: computes scales, draws gridlines, y ticks and x labels.
function frame(svg, series, opts) {
  const W = 640, H = 190, L = 44, R = 12, T = 12, B = 26;
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.setAttribute('preserveAspectRatio', 'none');

  const vals = series.map(p => p.v);
  let lo = opts.zero ? 0 : Math.min(...vals);
  let hi = Math.max(...vals);
  if (lo === hi) { lo = opts.zero ? 0 : lo - 1; hi = hi + 1; }
  const padY = (hi - lo) * 0.12;
  hi += padY;
  if (!opts.zero) lo = Math.max(0, lo - padY);

  const x = i => L + (series.length === 1 ? (W - L - R) / 2
                    : i * (W - L - R) / (series.length - 1));
  const y = v => T + (H - T - B) * (1 - (v - lo) / (hi - lo));

  // Narrow ranges need decimals, or ticks repeat (76, 75, 75, 74).
  const span = hi - lo;
  const dp = span >= 12 ? 0 : span >= 1.5 ? 1 : 2;
  const fmtY = opts.fmtY || (v => v.toFixed(dp));

  for (let t = 0; t <= 3; t++) {
    const v = lo + span * t / 3, yy = y(v);
    svg.appendChild(el('line', {
      x1: L, x2: W - R, y1: yy, y2: yy,
      stroke: 'var(--grid)', 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke'
    }));
    const lbl = el('text', {
      x: L - 7, y: yy + 4, 'text-anchor': 'end',
      fill: 'var(--muted)', 'font-size': 10
    });
    lbl.textContent = fmtY(v);
    svg.appendChild(lbl);
  }

  const step = Math.max(1, Math.ceil(series.length / 6));
  series.forEach((p, i) => {
    if (i % step && i !== series.length - 1) return;
    const t = el('text', {
      x: x(i), y: H - 8, 'text-anchor': 'middle',
      fill: 'var(--muted)', 'font-size': 10
    });
    t.textContent = opts.fmtX ? opts.fmtX(p.d) : fmtDate(p.d);
    svg.appendChild(t);
  });

  return { x, y, W, H, L, R, T, B };
}

function lineChart(host, series, opts = {}) {
  const svg = el('svg', { class: 'chart' });
  host.appendChild(svg);
  const f = frame(svg, series, opts);
  const color = opts.color || 'var(--series-1)';

  const d = series.map((p, i) => `${i ? 'L' : 'M'}${f.x(i)},${f.y(p.v)}`).join(' ');
  svg.appendChild(el('path', {
    d, fill: 'none', stroke: color, 'stroke-width': 2,
    'stroke-linejoin': 'round', 'stroke-linecap': 'round',
    'vector-effect': 'non-scaling-stroke'
  }));

  // Invisible wide hit bands so hovering anywhere in a column works.
  const bw = (f.W - f.L - f.R) / Math.max(1, series.length);
  series.forEach((p, i) => {
    const cx = f.x(i), cy = f.y(p.v);
    const dot = el('circle', {
      cx, cy, r: 3.5, fill: color,
      stroke: 'var(--surface)', 'stroke-width': 2, opacity: 0
    });
    svg.appendChild(dot);
    const hit = el('rect', {
      x: cx - bw / 2, y: f.T, width: bw, height: f.H - f.T - f.B, fill: 'transparent'
    });
    hit.addEventListener('mousemove', e => {
      dot.setAttribute('opacity', 1);
      showTip(e, fmtDate(p.d), (opts.fmtV ? opts.fmtV(p.v) : p.v) + (opts.unit || ''));
    });
    hit.addEventListener('mouseleave', () => { dot.setAttribute('opacity', 0); hideTip(); });
    svg.appendChild(hit);
  });
}

function barChart(host, series, opts = {}) {
  const svg = el('svg', { class: 'chart' });
  host.appendChild(svg);
  const f = frame(svg, series, { ...opts, zero: true });
  const color = opts.color || 'var(--series-1)';
  const slot = (f.W - f.L - f.R) / series.length;
  const bw = Math.max(2, slot - 2); // 2px surface gap between bars

  series.forEach((p, i) => {
    const cx = f.L + slot * (i + 0.5);
    const yy = f.y(p.v);
    const h = Math.max(1, f.y(0) - yy);
    const r = el('rect', {
      x: cx - bw / 2, y: yy, width: bw, height: h,
      fill: color, rx: Math.min(4, bw / 2)
    });
    r.addEventListener('mousemove', e =>
      showTip(e, opts.fmtX ? opts.fmtX(p.d) : fmtDate(p.d),
              (opts.fmtV ? opts.fmtV(p.v) : p.v) + (opts.unit || '')));
    r.addEventListener('mouseleave', hideTip);
    svg.appendChild(r);
  });
}

function card(title, sub, render, wide) {
  const c = document.createElement('div');
  c.className = 'card' + (wide ? ' wide' : '');
  const h = document.createElement('h2'); h.textContent = title;
  const s = document.createElement('div'); s.className = 'card-sub'; s.textContent = sub || '';
  c.appendChild(h); c.appendChild(s);
  render(c);
  document.getElementById('grid').appendChild(c);
}

function chartCard(title, sub, series, kind, opts) {
  if (!series || series.length < 2) return;   // hide rather than render an empty frame
  card(title, sub, host => (kind === 'bar' ? barChart : lineChart)(host, series, opts || {}));
}

// ---- header + KPIs -------------------------------------------------------
const w = DATA.window || {};
document.getElementById('sub').textContent =
  `${DATA.athlete} · ${w.start || ''} to ${w.end || ''}` +
  (DATA.devices && DATA.devices.length ? ` · ${DATA.devices.filter(Boolean).join(', ')}` : '');

const kpiDefs = [
  ['Activities', DATA.totals.count, ''],
  ['Distance', DATA.totals.km, ' km'],
  ['Moving time', DATA.totals.hours, ' h'],
  ['Elevation', DATA.totals.elev, ' m'],
  ['VO₂ max', DATA.kpis.vo2max, ''],
  ['Resting HR', DATA.kpis.resting_hr, ' bpm'],
  ['Readiness', DATA.kpis.readiness, ''],
  ['Sleep', DATA.kpis.sleep, ' h'],
  ['Last 4 weeks', DATA.kpis.last_4wk_km, ' km'],
];
const kpiHost = document.getElementById('kpis');
for (const [label, value, unit] of kpiDefs) {
  if (value === null || value === undefined || value === 0) continue;
  const d = document.createElement('div');
  d.className = 'card kpi';
  d.innerHTML = `<div class="label"></div><div class="value"></div>`;
  d.querySelector('.label').textContent = label;
  d.querySelector('.value').innerHTML =
    `${Math.round(value * 10) / 10}<span class="unit">${unit}</span>`;
  kpiHost.appendChild(d);
}

// ---- charts --------------------------------------------------------------
const C = DATA.charts;
const weekLabel = d => fmtDate(d);

chartCard('Weekly training volume', 'Kilometres per week', C.weekly_km, 'bar',
          { unit: ' km', fmtX: weekLabel });
chartCard('Weekly training time', 'Hours per week', C.weekly_hours, 'bar',
          { unit: ' h', fmtX: weekLabel, color: 'var(--series-2)' });
chartCard('VO₂ max', 'Estimated aerobic capacity', C.vo2max, 'line');
chartCard('Resting heart rate', 'Beats per minute', C.resting_hr, 'line',
          { unit: ' bpm', color: 'var(--series-2)' });
chartCard('Training readiness', 'Daily score out of 100', C.readiness, 'line');
chartCard('Sleep duration', 'Hours per night', C.sleep, 'bar', { unit: ' h' });
chartCard('Sleep score', 'Garmin nightly score out of 100', C.sleep_score, 'line');
chartCard('Calories burned', 'Total per day', C.calories, 'bar',
          { unit: ' kcal', color: 'var(--series-2)' });
chartCard('Daily stress', 'Average all-day stress', C.stress, 'line',
          { unit: '', color: 'var(--series-2)' });
chartCard('Daily steps', 'Steps per day', C.steps, 'bar',
          { unit: '', fmtY: v => v >= 1000 ? (v / 1000).toFixed(0) + 'k' : Math.round(v) });
chartCard('Body Battery peak', 'Highest level reached each day', C.body_battery, 'line');
chartCard('Weight', 'Kilograms', C.weight, 'line', { unit: ' kg', color: 'var(--series-2)' });

// ---- race predictions ----------------------------------------------------
if (DATA.races && DATA.races.length) {
  card('Race predictions', 'Garmin projected finish times', host => {
    const g = document.createElement('div');
    g.style.cssText = 'display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(110px,1fr))';
    for (const r of DATA.races) {
      const b = document.createElement('div');
      b.innerHTML = `<div class="label" style="color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.06em"></div>
                     <div style="font-size:20px;font-weight:600;font-variant-numeric:tabular-nums"></div>`;
      b.children[0].textContent = r.label;
      b.children[1].textContent = hms(r.seconds);
      g.appendChild(b);
    }
    host.appendChild(g);
  });
}

// ---- sport split ---------------------------------------------------------
if (DATA.types && DATA.types.length) {
  card('Activity breakdown', 'By sport', host => {
    const t = document.createElement('table');
    t.innerHTML = '<thead><tr><th>Sport</th><th class="num">Count</th>' +
                  '<th class="num">km</th><th class="num">Hours</th></tr></thead>';
    const tb = document.createElement('tbody');
    for (const r of DATA.types.slice(0, 12)) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="name"></td><td class="num"></td><td class="num"></td><td class="num"></td>`;
      tr.children[0].textContent = r.name;
      tr.children[1].textContent = r.count;
      tr.children[2].textContent = r.km ? r.km.toFixed(1) : '—';
      tr.children[3].textContent = r.hours ? r.hours.toFixed(1) : '—';
      tb.appendChild(tr);
    }
    t.appendChild(tb);
    const s = document.createElement('div'); s.className = 'scroll'; s.appendChild(t);
    host.appendChild(s);
  });
}

// ---- personal records ----------------------------------------------------
if (DATA.records && DATA.records.length) {
  card('Personal records', 'All-time bests', host => {
    const t = document.createElement('table');
    t.innerHTML = '<thead><tr><th>Record</th><th class="num">Value</th><th class="num">Date</th></tr></thead>';
    const tb = document.createElement('tbody');
    for (const r of DATA.records) {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td class="name"></td><td class="num"></td><td class="num"></td>`;
      tr.children[0].textContent = r.label;
      tr.children[1].textContent = fmtRecord(r);
      tr.children[2].textContent = r.date || '—';
      tb.appendChild(tr);
    }
    t.appendChild(tb);
    const s = document.createElement('div'); s.className = 'scroll'; s.appendChild(t);
    host.appendChild(s);
  });
}

// ---- recent activities ---------------------------------------------------
if (DATA.recent && DATA.recent.length) {
  card('Recent activities', `Latest ${DATA.recent.length}`, host => {
    const t = document.createElement('table');
    t.innerHTML = '<thead><tr><th>Date</th><th>Activity</th><th>Sport</th>' +
                  '<th class="num">km</th><th class="num">Time</th><th class="num">Pace / speed</th>' +
                  '<th class="num">Avg HR</th><th class="num">Elev</th></tr></thead>';
    const tb = document.createElement('tbody');
    for (const a of DATA.recent) {
      const tr = document.createElement('tr');
      tr.innerHTML = '<td class="num"></td><td class="name"></td><td class="name"></td>' +
                     '<td class="num"></td><td class="num"></td><td class="num"></td>' +
                     '<td class="num"></td><td class="num"></td>';
      const c = tr.children;
      c[0].textContent = a.date || '—';
      c[1].textContent = a.name;
      c[2].innerHTML = `<span class="chip"></span>`;
      c[2].firstChild.textContent = a.type;
      c[3].textContent = a.km ? a.km.toFixed(2) : '—';
      c[4].textContent = a.duration ? hms(a.duration) : '—';
      c[5].textContent = a.pace_s_per_km ? pace(a.pace_s_per_km) : kmh(a.avg_speed);
      c[6].textContent = a.avg_hr ? Math.round(a.avg_hr) : '—';
      c[7].textContent = a.elev ? a.elev + ' m' : '—';
      tb.appendChild(tr);
    }
    t.appendChild(tb);
    const s = document.createElement('div'); s.className = 'scroll'; s.appendChild(t);
    host.appendChild(s);
  }, true);
}

if (!document.getElementById('grid').children.length) {
  const d = document.createElement('div');
  d.className = 'card empty';
  d.textContent = 'No data yet. Run: python fetch_garmin_data.py';
  document.getElementById('grid').appendChild(d);
}

document.getElementById('footer').textContent =
  `Generated ${DATA.generated_at || ''}` +
  (DATA.failures && DATA.failures.length
    ? ` · ${DATA.failures.length} metric(s) unavailable for this device`
    : '');
</script>
</body>
</html>
"""


def main() -> int:
    try:
        payload = build_payload()
    except (FileNotFoundError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 1

    title = f"{payload['athlete']} — Training Dashboard"
    html = (
        HTML_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__HEADING__", "Training Dashboard")
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
