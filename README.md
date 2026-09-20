# BLR House Hunt

Scans the Facebook groups you already belong to for flat/flatmate listings
near **RMZ Ecoworld, Bellandur**, filters them against your criteria, and
emails you a digest of fresh matches every ~10 hours.

## What it looks for

- Area within ~0-3 km of RMZ Ecoworld (Bellandur and nearby societies)
- A single room going in a shared **2/3/4 BHK** (not PGs, not whole flats)
- Listings **open to males** (female-only posts are dropped)
- Rent **under ₹40,000/month** (small tolerance for "negotiable")

All of this lives in [`config/criteria.yaml`](config/criteria.yaml). That is
the one file you tune as your search sharpens. Add every society name and
group you come across.

## Honest limitations (read this)

- **No official Facebook API** exists for reading group posts anymore, so the
  tool drives a real browser logged in as you. This is against Facebook's
  Terms of Service and carries an account-ban risk. The 10-hour cadence is
  gentle on purpose. Do not crank it up.
- **Facebook's page structure changes often.** The reader is written to fail
  softly, but a listing it cannot parse is simply skipped. Expect to tweak
  selectors in `src/flathunt/sources/facebook.py` occasionally.
- **GitHub's runner IPs** are more likely to trigger Facebook's login checks
  than your home IP. If the job starts landing on a login/checkpoint page,
  either refresh your session (below) or run the job from your own machine
  instead (see "Run it from your own machine").

## Setup

### 1. Save your Facebook session (once, on your own machine)

```bash
pip install -r requirements.txt
python -m playwright install chromium
python scripts/save_session.py
```

A browser opens. Log in to Facebook, finish any 2FA, wait for your feed, then
press Enter in the terminal. This writes `data/fb_state.json` (git-ignored).

### 2. Add your groups and criteria

Edit `config/criteria.yaml`:
- Paste each group's URL under `facebook.groups`.
- Add society names under `location.societies`.
- Adjust `budget.max_rent`, `search.min_score`, etc.

### 3. Test locally without touching Facebook

```bash
PYTHONPATH=src POSTS_FIXTURE=tests/fixtures/sample_posts.json \
  python -m flathunt.run --dry-run
```

Then a real dry-run against Facebook (prints, does not email):

```bash
cp .env.example .env   # fill in your values, then:
set -a; . .env; set +a
PYTHONPATH=src python -m flathunt.run --dry-run
```

### 4. Wire up GitHub Actions (the every-10-hours job)

In your repo, go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
| --- | --- |
| `FB_STORAGE_STATE_B64` | `base64 -w0 data/fb_state.json` output |
| `SMTP_HOST` | `smtp.gmail.com` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | your Gmail address |
| `SMTP_PASS` | a Gmail **App Password** (not your login password) |
| `EMAIL_FROM` | your Gmail address |
| `EMAIL_TO` | where the digest should land |

Gmail App Password: <https://myaccount.google.com/apppasswords> (needs 2FA on).

The workflow [`.github/workflows/flathunt.yml`](.github/workflows/flathunt.yml)
then runs on its own. Trigger it manually first from the **Actions** tab
(**Run workflow**) to confirm the email arrives.

### Refreshing an expired session

If runs start failing on a Facebook login page, re-run
`python scripts/save_session.py` locally and update the
`FB_STORAGE_STATE_B64` secret with the new base64.

## Run it from your own machine instead

If GitHub's IPs keep getting checkpointed, run the same job from your laptop
or a small VPS with cron. Example crontab (every 10 hours):

```
0 */10 * * * cd /path/to/BLR-House-hunt && set -a && . .env && set +a && \
  PYTHONPATH=src /path/to/.venv/bin/python -m flathunt.run >> run.log 2>&1
```

## How matching works

Each post is scored on rent-in-budget, society/area mentions, room-share
signals, and male-friendliness; hard rejections (female-only, over budget,
PG, "flat wanted", too old) drop it outright. The digest shows the exact
reasons each listing was shortlisted, so you can tune the config with
confidence. Logic lives in `src/flathunt/matcher.py`, tested in
`tests/test_matcher.py`.

## Layout

```
config/criteria.yaml          your tunable search settings
src/flathunt/matcher.py       scoring + filtering (the brain)
src/flathunt/sources/facebook.py   Playwright group reader
src/flathunt/notify/email_digest.py   HTML email
src/flathunt/run.py           collect -> match -> dedupe -> email
scripts/save_session.py       one-time Facebook login capture
tests/                        matcher tests + sample fixture
.github/workflows/flathunt.yml   the 10-hourly schedule
```
