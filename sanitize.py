"""Strip identifying details before anything is written to disk.

This repo is public, so the committed data must not carry anything that
identifies you or where you train. Sanitising happens at fetch time rather
than at publish time so nothing identifying is ever committed in the first
place -- a scrubber that runs later still leaves the original in git history.

What is removed:
  * GPS coordinates (start/end latitude and longitude)
  * account identifiers (user ids, profile ids, the display-name UUID)
  * your name, replaced by ATHLETE_NAME (default "Athlete")
  * activity titles, replaced by the sport -- Garmin names activities after
    the place they happened, which pins down where you live and train just
    as precisely as a coordinate does

What is kept: every training number the dashboard plots.
"""

from __future__ import annotations

import os
from typing import Any

ATHLETE_NAME = os.getenv("ATHLETE_NAME", "Athlete")

# Dropped wherever they appear, at any nesting depth.
SENSITIVE_KEYS = frozenset({
    "startLatitude", "startLongitude", "endLatitude", "endLongitude",
    "latitude", "longitude", "locationName",
    "userId", "userProfileId", "userProfilePK", "userProfileNumber",
    "userProfileDisplayName", "displayName", "ownerId", "ownerDisplayName",
    "ownerFullName", "ownerProfileImageUrlSmall", "ownerProfileImageUrlMedium",
    "ownerProfileImageUrlLarge", "profileImageUrlSmall", "profileImageUrlMedium",
    "profileImageUrlLarge", "email", "fullName",
    "deviceId", "manufacturer", "serialNumber", "unitId", "deviceTypePk",
})

# Values under these keys must not survive into the output. This is deliberately
# narrower than SENSITIVE_KEYS: a device's "displayName" is its model
# ("Forerunner 265"), which millions of people own and which the dashboard
# shows on purpose. Harvesting that would flag a non-secret as a leak.
HARVEST_KEYS = frozenset({
    "userid", "userprofileid", "userprofilepk", "userprofilenumber",
    "ownerid", "ownerdisplayname", "ownerfullname", "fullname", "email",
    "deviceid", "serialnumber", "unitid",
    "startlatitude", "startlongitude", "endlatitude", "endlongitude",
    "locationname",
})


# Garmin is not consistent about casing -- the same field appears as both
# "userProfilePK" and "userProfilePk" -- so keys are matched case-insensitively.
_SENSITIVE_LOWER = frozenset(k.lower() for k in SENSITIVE_KEYS)


def scrub(node: Any) -> Any:
    """Recursively drop sensitive keys from any nested structure."""
    if isinstance(node, dict):
        return {
            k: scrub(v)
            for k, v in node.items()
            if k.lower() not in _SENSITIVE_LOWER
        }
    if isinstance(node, list):
        return [scrub(v) for v in node]
    return node


def sport_label(activity: dict) -> str:
    """A neutral title: the sport, not where it happened."""
    type_obj = activity.get("activityType")
    key = type_obj.get("typeKey") if isinstance(type_obj, dict) else None
    return str(key or "activity").replace("_", " ").title()


# Activities are whitelisted rather than blacklisted. A Garmin activity carries
# ~70 fields; the dashboard reads a dozen. Listing what to keep means a field
# added by Garmin later cannot leak into a public repo by default.
ACTIVITY_FIELDS = (
    "activityId",          # needed to merge the cache across runs
    "startTimeLocal", "startTimeGMT",
    "distance", "duration", "elapsedDuration", "movingDuration",
    "elevationGain", "steps", "calories",
    "averageHR", "maxHR", "averageSpeed",
    "aerobicTrainingEffect", "anaerobicTrainingEffect", "activityTrainingLoad",
    "moderateIntensityMinutes", "vigorousIntensityMinutes",
)


def sanitize_activities(activities: list[dict]) -> list[dict]:
    """Keep only known-safe fields, and title each activity by its sport."""
    out = []
    for a in activities:
        if not isinstance(a, dict):
            continue
        clean = {f: a[f] for f in ACTIVITY_FIELDS if f in a}
        type_obj = a.get("activityType")
        if isinstance(type_obj, dict) and type_obj.get("typeKey"):
            clean["activityType"] = {"typeKey": type_obj["typeKey"]}
        clean["activityName"] = sport_label(a)
        out.append(clean)
    return out


def collect_identifiers(node: Any, found: set[str] | None = None) -> set[str]:
    """Gather the actual values stored under sensitive keys.

    Harvested from the raw payload before scrubbing, these are exactly the
    strings that must not appear in the output -- which makes the check
    independent of whether the denylist spelled every key correctly.
    """
    if found is None:
        found = set()

    if isinstance(node, dict):
        for k, v in node.items():
            if k.lower() in HARVEST_KEYS and isinstance(v, (str, int, float)):
                found.add(str(v))
            else:
                collect_identifiers(v, found)
    elif isinstance(node, list):
        for v in node:
            collect_identifiers(v, found)

    return found


def verify_clean(blob: str, secrets: list[str]) -> None:
    """Raise if anything identifying survived into the text about to be written.

    A denylist can always miss a key Garmin spells differently, so this checks
    the actual output for the real values instead of trusting the key names.
    """
    leaked = sorted({
        s for s in secrets
        if s and len(str(s)) > 3 and str(s).lower() in blob.lower()
    })
    if leaked:
        raise RuntimeError(
            "Refusing to write: identifying values survived sanitising "
            f"({', '.join(repr(x) for x in leaked)}). "
            "Add the offending key to SENSITIVE_KEYS in sanitize.py."
        )


def sanitize_payload(payload: dict) -> dict:
    """Scrub the summary payload and replace the athlete name."""
    clean = scrub(payload)

    profile = clean.get("profile")
    if isinstance(profile, dict):
        profile["name"] = ATHLETE_NAME

        # Devices carry ids and serials under several spellings. The dashboard
        # only shows the model, so keep that and drop the rest outright.
        devices = profile.get("devices")
        if isinstance(devices, list):
            profile["devices"] = [
                {"productDisplayName": d.get("productDisplayName")}
                for d in devices
                if isinstance(d, dict) and d.get("productDisplayName")
            ]

        # Personal records are titled with the activity they were set in,
        # which is a place name. The dashboard labels them from typeId, so
        # the raw title is not needed.
        for rec in profile.get("personal_records") or []:
            if isinstance(rec, dict) and rec.get("activityName"):
                rec["activityName"] = None

    return clean
