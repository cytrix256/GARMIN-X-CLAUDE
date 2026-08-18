# Decisions

Choices already made, with the reasoning. Do not silently reverse one — if a
decision looks wrong, add a new dated entry that supersedes it and say why.

---

**2026-08-18 — Autonomy: commit and push to main directly.**
The daily sync already commits to `main` unattended, so requiring review for
hand-written changes would be inconsistent theatre. The guardrails in CLAUDE.md
replace the review gate: never commit secrets, never push a dashboard that does
not build, never invent a number, ask before anything outward-facing.

**2026-08-18 — v1 scope is the analytics layer, not features.**
Segments, maps and social are the parts of Strava that need infrastructure. The
analysis layer is the part that needs history and a model, which is exactly what
we have and exactly what the subscription was charging for.

**2026-08-18 — Routines are written procedures, not automation.**
A checklist that a human or Claude follows on demand. The daily sync stays the
only scheduled thing. Automating a process before running it twice by hand tends
to automate the wrong process.

**Earlier — Reduce Garmin's per-day payloads before writing them.**
About 15 numbers per day instead of the full minute-by-minute arrays. CI commits
this file daily; unreduced, the repo would grow by gigabytes a year. `--keep-raw`
exists for ad-hoc analysis and is gitignored.

**Earlier — The dashboard is one self-contained HTML file.**
It embeds its own data and draws its own SVG. No CDN. It works from a `file://`
URL and from GitHub Pages alike, and cannot break because someone else's CDN
went down.

**Earlier — Probe candidate keys; hide empty cards.**
Garmin returns different shapes per device and firmware. A card with no data
hides itself rather than rendering an empty frame.

**Earlier — Two dependencies: garminconnect and curl_cffi.**
Keep it there. Anything new needs a reason and an entry here.
