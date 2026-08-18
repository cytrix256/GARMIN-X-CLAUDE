# Routine — weekly review

Run on a Monday, or any day the week needs looking at. Takes a few minutes.

1. **Get current data.**
   ```bash
   git pull --ff-only
   ```
   CI syncs daily at 05:30 UTC. If `data/garmin_data.json` has not changed in
   more than two days, stop and run `routines/sync-health-check.md` first — a
   review built on stale data is worse than no review.

2. **Generate the review.**
   ```bash
   python weekly_review.py
   ```
   Writes `demos/YYYY-MM-DD-weekly-review.md`. (Until spec 001 ships, do this
   step by reading the dashboard and writing the file by hand — that is the
   version of the routine worth testing first.)

3. **Read it end to end.** Not skim. The question is whether you would read the
   next one.

4. **Check three things about it.**
   - Does any number look wrong? Trace it to the function that computed it.
   - Does any sentence claim more than the data supports?
   - Is anything missing that you went looking for?

5. **Fix what step 4 found**, or write it down. Small fix: make it now and
   follow `routines/ship-a-change.md`. Larger: add it to the Next column in
   `ROADMAP.md`, or open a spec in `specs/`.

6. **Commit the demo.**
   ```bash
   git add demos && git commit -m "Weekly review YYYY-MM-DD" && git push
   ```
   Keep it even if it read badly. Especially then.

7. **Record it.** One entry in `REVIEW.md` if anything shipped or anything was
   learned. Skip if the honest answer is "nothing changed".
