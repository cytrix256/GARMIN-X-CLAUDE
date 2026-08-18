# Routine — ship a change

For any change to `analytics.py`, `build_dashboard.py`, `dashboard_template.html`
or `fetch_garmin_data.py`. Autonomy is full — commit and push to `main` without
asking — which is exactly why these steps are not optional.

1. **Know what you are changing and why.** If it is non-trivial, there is a spec
   in `specs/`. If there is no spec and you cannot state "done" in one sentence,
   write the spec first.

2. **Check the ground truth.** Read `context/data.md` before assuming a field
   exists. Garmin's shapes vary by device, and a field present in one account is
   absent in another.

3. **Make the change.** Match the surrounding style: standard library first,
   probe candidate keys, hide cards with no data, and document a formula beside
   its implementation.

4. **Rebuild.**
   ```bash
   python build_dashboard.py
   ```
   It must exit 0 and `docs/index.html` must have a new timestamp. A failed
   build is never pushed — the page is served publicly.

5. **Look at the rendered output**, not just the code. Open `docs/index.html`.
   Four real bugs in this repo's history were found by looking at the page and
   noticing two views disagreeing about the same number.

6. **Check the numbers moved the way you expected.** If a metric changed, know
   why. If it did not change, know why not.

7. **Commit and push.**
   ```bash
   git add -A && git commit && git push
   ```
   The message says what changed and why, in plain sentences. Never
   `git add` anything under `tokens/`, `.env` or `garmin_token_b64.txt` — they
   are gitignored; keep it that way.

8. **Update the paperwork.** Tick the criterion in the spec, move the item in
   `ROADMAP.md`, add a line to `REVIEW.md` if something shipped, and add a dated
   entry to `context/decisions.md` if a choice was made that a future reader
   would otherwise reverse by accident.
