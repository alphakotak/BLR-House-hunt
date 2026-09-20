"""One-time helper: log in to Facebook in a real browser and save the session.

Run this ONCE on your own machine (not on GitHub):

    pip install -r requirements.txt
    python -m playwright install chromium
    python scripts/save_session.py

A browser window opens. Log in to Facebook normally (complete any 2FA).
When your news feed is fully loaded, come back to the terminal and press
Enter. Your session is written to data/fb_state.json.

Then, for GitHub Actions, turn that file into a secret:

    base64 -w0 data/fb_state.json        # Linux
    base64 data/fb_state.json | tr -d '\\n'   # macOS

Copy the output into a repo secret named FB_STORAGE_STATE_B64.

NOTE: this file is your login. It is git-ignored on purpose. Never commit it.
Facebook sessions expire; if the job starts hitting a login/checkpoint page,
re-run this script and refresh the secret.
"""
from __future__ import annotations

import os
from pathlib import Path

OUT = os.environ.get("FB_STORAGE_STATE_PATH", "data/fb_state.json")


def main() -> None:
    from playwright.sync_api import sync_playwright

    Path(OUT).parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        context = browser.new_context(locale="en-IN")
        page = context.new_page()
        page.goto("https://www.facebook.com/", wait_until="domcontentloaded")
        print("\n=== Log in to Facebook in the browser window. ===")
        input("Once your feed has loaded, press Enter here to save the session... ")
        context.storage_state(path=OUT)
        print(f"Saved session to {OUT}")
        browser.close()


if __name__ == "__main__":
    main()
