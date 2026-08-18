# Routine — sync health check

Run when the dashboard looks stale, a scheduled sync failed, or a number has
stopped moving.

1. **When did data last change?**
   ```bash
   git log -1 --format=%cd -- data/garmin_data.json
   ```
   CI runs daily at 05:30 UTC, though GitHub queues cron under load — treat it
   as "early morning", not an exact time. More than two days is a real gap.

2. **Check the Actions tab** for the last Garmin sync run, and read the failure
   if there was one.

3. **Read `failures` in the data.**
   ```bash
   python -c "import json;print(json.load(open('data/garmin_data.json'))['failures'])"
   ```
   Non-empty usually means a metric this device does not populate, not a bug. It
   surfaces in the dashboard footer by design.

4. **If it is an authentication error**, the tokens have expired — they last
   roughly a year, and die immediately on a Garmin password change. CI cannot
   write refreshed tokens back to the secret, so this is expected eventually.
   Fixing it needs a password and is therefore a human job:
   - Run `python login.py` (interactive; never run unattended, and never ask for
     the password in chat).
   - Update the `GARMIN_TOKENS_B64` repo secret with the contents of
     `garmin_token_b64.txt`.
   - Delete `garmin_token_b64.txt` locally.

5. **If it is HTTP 429**, Garmin is throttling. Raise `CALL_DELAY` in
   `fetch_garmin_data.py` rather than retrying harder, then follow
   `routines/ship-a-change.md`.

6. **Verify locally before trusting CI again.**
   ```bash
   python fetch_garmin_data.py --days 7
   ```
   Prints the account it connected as, then writes `data/`.

7. **Record it** in `REVIEW.md` if the cause was anything other than a transient
   failure.
