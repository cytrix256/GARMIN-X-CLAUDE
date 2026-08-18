"""Derived training analytics.

Everything here is computed from history rather than read back from Garmin.
These are the numbers the Garmin app does not show you, because they need
weeks of context and a model rather than a single day's reading:

  * Fitness / Fatigue / Form  -- the Banister impulse-response model
  * Acute:chronic workload    -- the injury-risk ratio
  * HRV baseline deviation    -- low or high relative to *your* normal
  * Recovery score            -- a transparent composite, formula below
  * Sleep debt                -- rolling shortfall against Garmin's own need
  * Lagged correlations       -- does last night's sleep predict tomorrow?

Every formula is documented where it is implemented. Nothing is a black box.
"""

from __future__ import annotations

import math
from datetime import date, timedelta
from typing import Any

# Banister model time constants, in days. 42/7 is the endurance-sport
# convention (TrainingPeaks CTL/ATL); short enough to react, long enough
# that one big session does not swamp the trend.
CTL_TAU = 42
ATL_TAU = 7


def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if x != x else x


def day_range(start: str, end: str) -> list[str]:
    """Every calendar day in the window -- gaps included, so the models decay
    correctly on rest days instead of skipping them."""
    a, b = date.fromisoformat(start), date.fromisoformat(end)
    return [(a + timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def daily_load(activities: list[dict]) -> dict[str, float]:
    """Sum Garmin's per-activity training load onto calendar days."""
    out: dict[str, float] = {}
    for a in activities:
        if not isinstance(a, dict):
            continue
        stamp = str(a.get("startTimeLocal") or a.get("startTimeGMT") or "")[:10]
        load = _f(a.get("activityTrainingLoad"))
        if len(stamp) == 10 and load:
            out[stamp] = out.get(stamp, 0.0) + load
    return out


def fitness_fatigue(load: dict[str, float], days: list[str]) -> list[dict]:
    """Banister impulse-response: two exponentially weighted averages of load.

    Fitness (CTL) is the slow one, Fatigue (ATL) the fast one. Form (TSB) is
    fitness minus fatigue: positive means fresh and ready to perform, negative
    means carrying fatigue. Sustained deep-negative Form is the classic
    overreaching signature -- and it is the number Garmin never shows.
    """
    k_ctl, k_atl = 1 - math.exp(-1 / CTL_TAU), 1 - math.exp(-1 / ATL_TAU)
    ctl = atl = 0.0
    out = []
    for d in days:
        today = load.get(d, 0.0)
        ctl += (today - ctl) * k_ctl
        atl += (today - atl) * k_atl
        out.append({
            "d": d,
            "load": round(today, 1),
            "fitness": round(ctl, 1),
            "fatigue": round(atl, 1),
            "form": round(ctl - atl, 1),
        })
    return out


def acwr(load: dict[str, float], days: list[str]) -> list[dict]:
    """Acute:chronic workload ratio -- 7-day mean over 28-day mean.

    The sports-medicine literature puts elevated injury risk above ~1.5
    (ramping too fast) and detraining below ~0.8. It needs 28 days of history,
    so the first four weeks are omitted rather than shown as noise.
    """
    out = []
    for i, d in enumerate(days):
        if i < 28:
            continue
        acute = sum(load.get(x, 0.0) for x in days[i - 6:i + 1]) / 7
        chronic = sum(load.get(x, 0.0) for x in days[i - 27:i + 1]) / 28
        if chronic > 0:
            out.append({"d": d, "v": round(acute / chronic, 2)})
    return out


def monotony_strain(load: dict[str, float], days: list[str]) -> list[dict]:
    """Foster monotony (weekly mean / SD) and strain (weekly load x monotony).

    Training the same amount every single day, with no hard/easy variation,
    predicts illness and overreaching better than raw volume does.
    """
    out = []
    for i, d in enumerate(days):
        if i < 6:
            continue
        week = [load.get(x, 0.0) for x in days[i - 6:i + 1]]
        mean = sum(week) / 7
        if mean <= 0:
            continue
        sd = math.sqrt(sum((x - mean) ** 2 for x in week) / 7)
        mono = mean / sd if sd > 0.01 else 0.0
        if mono:
            out.append({
                "d": d,
                "monotony": round(mono, 2),
                "strain": round(sum(week) * mono, 0),
            })
    return out


def hrv_table(hrv_range: Any) -> dict[str, dict]:
    """Nightly HRV plus Garmin's own personalised balanced range."""
    rows: dict[str, dict] = {}
    summaries = None
    if isinstance(hrv_range, dict):
        summaries = hrv_range.get("hrvSummaries")
    for r in summaries or []:
        if not isinstance(r, dict):
            continue
        d = str(r.get("calendarDate") or "")[:10]
        v = _f(r.get("lastNightAvg"))
        if len(d) != 10 or not v:
            continue
        base = r.get("baseline") if isinstance(r.get("baseline"), dict) else {}
        rows[d] = {
            "hrv": v,
            "weekly": _f(base and r.get("weeklyAvg")),
            "low": _f(base.get("balancedLow")),
            "high": _f(base.get("balancedUpper")),
            "status": r.get("status"),
        }
    return rows


def hrv_deviation(hrv: dict[str, dict]) -> list[dict]:
    """Where each night sits inside your own balanced band.

    Zero is the middle of the band, -100 its low edge, +100 its high edge.
    Expressing it this way means "low HRV" is low *for you*, which a raw
    millisecond number can never say.
    """
    out = []
    for d in sorted(hrv):
        r = hrv[d]
        lo, hi, v = r.get("low"), r.get("high"), r.get("hrv")
        if not (lo and hi and v) or hi <= lo:
            continue
        mid, half = (lo + hi) / 2, (hi - lo) / 2
        # On days when Garmin reports a very narrow balanced band, a single
        # off night divides by almost nothing and produces figures like
        # -664%, which flattens every other day on the chart. Anything past
        # twice the band width is already "far outside normal", so cap it
        # there rather than let one outlier set the scale.
        dev = max(-200.0, min(200.0, (v - mid) / half * 100))
        out.append({
            "d": d,
            "v": v,
            "low": lo,
            "high": hi,
            "dev": round(dev, 1),
            "status": r.get("status"),
        })
    return out


def merged_daily(data: dict) -> dict[str, dict]:
    """One record per day, combining both sources.

    The per-day fetch is rich but only covers a recent window (45 days); the
    nightly sleep range endpoint is thinner but spans the whole period (171
    days) and carries resting HR, respiration and SpO2 as well. Merging them
    roughly quadruples the sample size every correlation is computed on.
    """
    out: dict[str, dict] = {}

    for row in (data.get("ranges") or {}).get("sleep_daily") or []:
        if not isinstance(row, dict):
            continue
        d = str(row.get("calendarDate") or "")[:10]
        vals = row.get("values") if isinstance(row.get("values"), dict) else {}
        if len(d) != 10 or not vals:
            continue
        rec: dict[str, Any] = {}
        for key, field in (
            ("sleep_seconds", "totalSleepTimeInSeconds"),
            ("resting_hr", "restingHeartRate"),
            ("respiration", "respiration"),
            ("spo2", "spO2"),
            ("bb_change", "bodyBatteryChange"),
            ("sleep_deep", "deepTime"),
            ("sleep_rem", "remTime"),
            ("sleep_awake", "awakeTime"),
        ):
            v = _f(vals.get(field))
            if v is not None:
                rec[key] = v
        if rec:
            out[d] = rec

    # The per-day records win where they overlap: they are the fuller source.
    for d, rec in (data.get("daily") or {}).items():
        if isinstance(rec, dict):
            out.setdefault(d, {}).update({k: v for k, v in rec.items() if v is not None})

    return out


def _baseline(values: dict[str, float], days: list[str], i: int, window: int):
    """Mean and SD of the preceding days that actually have data."""
    hist = [values[x] for x in days[max(0, i - window):i] if x in values]
    if len(hist) < 5:
        return None, None
    mean = sum(hist) / len(hist)
    sd = math.sqrt(sum((x - mean) ** 2 for x in hist) / len(hist))
    return mean, sd


def _band(x: float, lo: float, hi: float) -> float:
    """Map a value within a range onto 0..100, clamped."""
    if hi <= lo:
        return 50.0
    return max(0.0, min(100.0, (x - lo) / (hi - lo) * 100))


def recovery(days: list[str], daily: dict[str, dict], hrv: dict[str, dict],
             ff: list[dict]) -> list[dict]:
    """A transparent recovery score, 0-100, with its components exposed.

    Weighted: HRV against your balanced band 40%, resting HR against its own
    30-day baseline 25%, sleep 25%, accumulated fatigue 10%. Whoop keeps its
    formula secret; this one is printed directly above the code implementing
    it, and every component is returned so you can see which one moved it.
    """
    rhr_by_day = {d: v["resting_hr"] for d, v in daily.items() if v.get("resting_hr")}
    form_by_day = {r["d"]: r["form"] for r in ff}
    fatigue_vals = [r["fatigue"] for r in ff if r["fatigue"] > 0]
    fat_max = max(fatigue_vals) if fatigue_vals else 1.0

    weights = {"hrv": 0.40, "rhr": 0.25, "sleep": 0.25, "load": 0.10}
    out = []

    for i, d in enumerate(days):
        rec = daily.get(d) or {}
        parts: dict[str, float] = {}

        h = hrv.get(d)
        if h and h.get("low") and h.get("high") and h.get("hrv"):
            # The band's low edge scores 35 and its high edge 100: sitting
            # above your balanced range is not a problem to be penalised.
            parts["hrv"] = _band(h["hrv"], h["low"] * 0.85, h["high"]) * 0.65 + 35

        rhr = rec.get("resting_hr")
        if rhr:
            mean, sd = _baseline(rhr_by_day, days, i, 30)
            if mean and sd and sd > 0.3:
                # Lower than baseline is good, so the z-score is inverted.
                parts["rhr"] = max(0.0, min(100.0, 50 - ((rhr - mean) / sd) * 22))

        if rec.get("sleep_score"):
            parts["sleep"] = float(rec["sleep_score"])
        elif rec.get("sleep_seconds"):
            parts["sleep"] = _band(rec["sleep_seconds"] / 3600, 4.5, 8.0)

        f = form_by_day.get(d)
        if f is not None and fat_max > 0:
            parts["load"] = max(0.0, min(100.0, 50 + (f / fat_max) * 40))

        # A partial day -- today, before the watch has synced a night --
        # leaves only resting HR and load, which produces a confident-looking
        # score from almost no evidence. Require a night's worth of signal.
        if not ({"hrv", "sleep"} & set(parts)) or len(parts) < 2:
            continue

        total = sum(weights[k] for k in parts)
        value = sum(parts[k] * weights[k] for k in parts) / total
        out.append({
            "d": d,
            "v": round(value),
            "parts": {k: round(v) for k, v in parts.items()},
        })
    return out


def sleep_debt(days: list[str], daily: dict[str, dict],
               need_by_day: dict[str, float]) -> list[dict]:
    """Rolling 7-day shortfall against Garmin's own nightly sleep need."""
    out = []
    for i, d in enumerate(days):
        if i < 6:
            continue
        debt = 0.0
        counted = 0
        for x in days[i - 6:i + 1]:
            rec = daily.get(x) or {}
            secs = rec.get("sleep_seconds")
            need = need_by_day.get(x)
            if secs and need:
                debt += (need * 60 - secs) / 3600
                counted += 1
        if counted >= 4:
            out.append({"d": d, "v": round(debt, 1)})
    return out


def pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 12:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx <= 0 or dy <= 0:
        return None
    return num / (dx * dy)


def correlate(days: list[str], src: dict[str, float], dst: dict[str, float],
              lag: int) -> tuple[float | None, int]:
    """Correlation between src on a day and dst that many days later."""
    xs: list[float] = []
    ys: list[float] = []
    for i, d in enumerate(days):
        j = i + lag
        if j >= len(days):
            break
        a, b = src.get(d), dst.get(days[j])
        if a is not None and b is not None:
            xs.append(float(a))
            ys.append(float(b))
    return pearson(xs, ys), len(xs)


def scatter_data(days: list[str], daily: dict[str, dict],
                 hrv: dict[str, dict], ff: list[dict]) -> dict[str, dict]:
    """Aligned daily series, so the page can plot any pair the reader picks."""
    return {
        "Training load": {r["d"]: r["load"] for r in ff if r["load"] > 0},
        "Sleep hours": {d: round(v["sleep_seconds"] / 3600, 2)
                        for d, v in daily.items() if v.get("sleep_seconds")},
        "Sleep score": {d: v["sleep_score"] for d, v in daily.items()
                        if v.get("sleep_score")},
        "Stress": {d: v["stress_avg"] for d, v in daily.items()
                   if v.get("stress_avg")},
        "Steps": {d: v["steps"] for d, v in daily.items() if v.get("steps")},
        "HRV": {d: v["hrv"] for d, v in hrv.items() if v.get("hrv")},
        "Resting HR": {d: v["resting_hr"] for d, v in daily.items()
                       if v.get("resting_hr")},
        "Readiness": {d: v["readiness"] for d, v in daily.items()
                      if v.get("readiness")},
        "Body Battery": {d: v["bb_high"] for d, v in daily.items()
                         if v.get("bb_high")},
        "Respiration": {d: v["respiration"] for d, v in daily.items()
                        if v.get("respiration")},
        "Blood oxygen": {d: v["spo2"] for d, v in daily.items()
                         if v.get("spo2")},
    }


def insights(days: list[str], scatter: dict[str, dict]) -> list[dict]:
    """Lagged correlations between what you control and how you feel.

    Correlation is not causation, and n is reported alongside r so a weak
    result on thin data stays visible instead of hiding behind a
    confident-looking number.
    """
    pairs = [
        ("Training load", "Resting HR", 1),
        ("Training load", "HRV", 1),
        ("Training load", "Sleep score", 0),
        ("Training load", "Readiness", 1),
        ("Sleep hours", "Readiness", 0),
        ("Sleep score", "HRV", 0),
        ("Sleep hours", "Resting HR", 0),
        ("Stress", "Sleep score", 0),
        ("Stress", "HRV", 1),
        ("Steps", "Sleep hours", 0),
        ("HRV", "Readiness", 0),
        ("Sleep score", "Readiness", 0),
        ("Training load", "Respiration", 1),
        ("Sleep hours", "HRV", 0),
        ("Training load", "Blood oxygen", 1),
    ]

    out = []
    for a, b, lag in pairs:
        if a not in scatter or b not in scatter:
            continue
        r, n = correlate(days, scatter[a], scatter[b], lag)
        if r is None:
            continue
        out.append({
            "from": a,
            "to": b,
            "lag": lag,
            "r": round(r, 2),
            "n": n,
            "strength": ("strong" if abs(r) >= 0.5 else
                         "moderate" if abs(r) >= 0.3 else "weak"),
        })
    out.sort(key=lambda x: -abs(x["r"]))
    return out


def weekday_profile(scatter: dict[str, dict]) -> dict[str, list]:
    """Average of each metric by day of week -- exposes routine effects."""
    names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    out: dict[str, list] = {}
    for metric, values in scatter.items():
        buckets: list[list[float]] = [[] for _ in range(7)]
        for d, v in values.items():
            try:
                buckets[date.fromisoformat(d).weekday()].append(float(v))
            except ValueError:
                continue
        if sum(len(b) for b in buckets) < 14:
            continue
        out[metric] = [
            {"d": names[i], "v": round(sum(b) / len(b), 1) if b else None}
            for i, b in enumerate(buckets)
        ]
    return out


def build(data: dict, activities: list[dict]) -> dict:
    """Assemble every derived metric into one payload for the dashboard."""
    window = data.get("window") or {}
    start, end = window.get("start"), window.get("end")
    if not (start and end):
        return {}

    days = day_range(start, end)
    daily = merged_daily(data)
    ranges = data.get("ranges") or {}

    load = daily_load(activities)
    ff = fitness_fatigue(load, days)
    hrv = hrv_table(ranges.get("hrv_range"))

    need_by_day: dict[str, float] = {}
    for row in ranges.get("sleep_daily") or []:
        if not isinstance(row, dict):
            continue
        d = str(row.get("calendarDate") or "")[:10]
        vals = row.get("values") if isinstance(row.get("values"), dict) else {}
        need = _f(vals.get("sleepNeed"))
        if len(d) == 10 and need:
            need_by_day[d] = need

    scatter = scatter_data(days, daily, hrv, ff)

    return {
        "days": days,
        "fitness_fatigue": ff,
        "acwr": acwr(load, days),
        "monotony": monotony_strain(load, days),
        "hrv": hrv_deviation(hrv),
        "recovery": recovery(days, daily, hrv, ff),
        "sleep_debt": sleep_debt(days, daily, need_by_day),
        "insights": insights(days, scatter),
        "scatter": scatter,
        "weekday": weekday_profile(scatter),
    }
