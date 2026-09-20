"""Facebook group reader using Playwright + your saved login session.

IMPORTANT / read this:
  * This logs in as YOU, using a session you create locally with
    scripts/save_session.py. There is no official Facebook API for reading
    group posts anymore, so this drives a real browser.
  * Facebook's DOM is obfuscated and changes often. This reader is written
    defensively: if a selector breaks it logs and moves on rather than
    crashing the whole run. Expect to occasionally adjust selectors.
  * Automated reading is against Facebook's Terms of Service and carries an
    account-ban risk. Keep the cadence gentle (the 10h schedule is fine),
    do not hammer it, and treat a checkpoint/login prompt as a signal to
    refresh your session cookies rather than to retry harder.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List
from urllib.parse import urljoin

from ..models import Post

log = logging.getLogger("flathunt.facebook")

# Anchors whose href points at an actual post permalink.
_PERMALINK_RE = re.compile(r"/(posts|permalink)/|story_fbid=|/groups/\d+/posts/")

# Rough relative-time parser for "2 hrs", "35 mins", "Yesterday", "3 d".
_REL_RE = re.compile(r"(\d+)\s*(min|hour|hr|day|d|h|m|week|w)", re.IGNORECASE)


def _parse_relative_time(label: str, now: datetime) -> datetime | None:
    label = label.lower()
    if "just now" in label or "few seconds" in label:
        return now
    if "yesterday" in label:
        return now - timedelta(days=1)
    m = _REL_RE.search(label)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit in ("m", "min"):
        return now - timedelta(minutes=n)
    if unit in ("h", "hr", "hour"):
        return now - timedelta(hours=n)
    if unit in ("d", "day"):
        return now - timedelta(days=n)
    if unit in ("w", "week"):
        return now - timedelta(weeks=n)
    return None


class FacebookSource:
    def __init__(self, storage_state: str, headless: bool = True):
        self.storage_state = storage_state
        self.headless = headless

    def collect(self, groups: List[dict], scroll_rounds: int = 6,
                search_terms: List[str] | None = None) -> List[Post]:
        # Imported lazily so the matcher/tests do not require Playwright.
        from playwright.sync_api import sync_playwright

        if not Path(self.storage_state).exists():
            raise FileNotFoundError(
                f"Facebook session not found at {self.storage_state}. "
                "Create it locally with: python scripts/save_session.py"
            )

        posts: List[Post] = []
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=self.headless)
            context = browser.new_context(
                storage_state=self.storage_state,
                viewport={"width": 1280, "height": 1600},
                locale="en-IN",
            )
            page = context.new_page()
            for g in groups:
                try:
                    posts.extend(
                        self._read_group(page, g, scroll_rounds, search_terms or [])
                    )
                except Exception as exc:  # never let one group kill the run
                    log.warning("group %s failed: %s", g.get("name"), exc)
            context.close()
            browser.close()
        log.info("collected %d raw posts", len(posts))
        return posts

    def _read_group(self, page, group: dict, scroll_rounds: int,
                    search_terms: List[str]) -> List[Post]:
        name = group.get("name", "")
        base_url = group["url"].rstrip("/")
        # If search terms are given, use the group's ?q= search; else read feed.
        urls = [f"{base_url}/search/?q={t.replace(' ', '%20')}" for t in search_terms] \
            or [base_url]

        found: List[Post] = []
        now = datetime.now(timezone.utc)
        for url in urls:
            log.info("reading %s (%s)", name, url)
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            self._dismiss_dialogs(page)
            for _ in range(scroll_rounds):
                page.mouse.wheel(0, 3200)
                page.wait_for_timeout(1800)  # let lazy content load

            # Each feed story sits in a role=article container.
            articles = page.locator("div[role='article']")
            count = min(articles.count(), 120)
            for i in range(count):
                try:
                    art = articles.nth(i)
                    text = (art.inner_text(timeout=2000) or "").strip()
                    if len(text) < 40:
                        continue
                    href = self._first_permalink(art, base_url)
                    posted = self._extract_time(art, now)
                    found.append(
                        Post(
                            text=text,
                            url=href or url,
                            source="facebook",
                            group_name=name,
                            posted_at=posted,
                        )
                    )
                except Exception:
                    continue
        return found

    @staticmethod
    def _first_permalink(article, base_url: str) -> str | None:
        anchors = article.locator("a[href]")
        for i in range(min(anchors.count(), 15)):
            href = anchors.nth(i).get_attribute("href") or ""
            if _PERMALINK_RE.search(href):
                return urljoin(base_url + "/", href.split("?")[0]
                               if "story_fbid" not in href else href)
        return None

    @staticmethod
    def _extract_time(article, now: datetime) -> datetime | None:
        # FB puts a relative timestamp in the first small link/abbr of a story.
        try:
            candidates = article.locator("a[role='link'], abbr")
            for i in range(min(candidates.count(), 8)):
                label = (candidates.nth(i).inner_text(timeout=800) or "").strip()
                parsed = _parse_relative_time(label, now)
                if parsed:
                    return parsed
        except Exception:
            pass
        return None

    @staticmethod
    def _dismiss_dialogs(page) -> None:
        for label in ("Allow all cookies", "Close", "Not now"):
            try:
                btn = page.get_by_role("button", name=label)
                if btn.count():
                    btn.first.click(timeout=1500)
                    page.wait_for_timeout(500)
            except Exception:
                pass
