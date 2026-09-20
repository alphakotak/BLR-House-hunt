"""Entry point: collect -> match -> dedupe -> email.

Run locally:
    python -m flathunt.run
Test the pipeline without touching Facebook:
    POSTS_FIXTURE=tests/fixtures/sample_posts.json python -m flathunt.run --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from typing import List

from .config import EmailSettings, Runtime, load_criteria
from .dedupe import SeenStore
from .matcher import Matcher, MatchResult
from .models import Post
from .notify.email_digest import send_digest

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("flathunt")


def _load_fixture(path: str) -> List[Post]:
    raw = json.loads(open(path, "r", encoding="utf-8").read())
    posts = []
    for item in raw:
        posted = item.get("posted_at")
        posts.append(
            Post(
                text=item["text"],
                url=item.get("url", ""),
                group_name=item.get("group_name", "fixture"),
                posted_at=datetime.fromisoformat(posted) if posted else None,
            )
        )
    return posts


def collect_posts(cfg: dict, rt: Runtime) -> List[Post]:
    if rt.fixture:
        log.info("using fixture %s (Facebook skipped)", rt.fixture)
        return _load_fixture(rt.fixture)

    from .sources.facebook import FacebookSource

    fb_cfg = cfg.get("facebook", {})
    source = FacebookSource(storage_state=rt.storage_state, headless=rt.headless)
    return source.collect(
        groups=fb_cfg.get("groups", []),
        scroll_rounds=int(fb_cfg.get("scroll_rounds", 6)),
        search_terms=fb_cfg.get("search_terms", []),
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Bellandur flat-hunt digest")
    parser.add_argument("--dry-run", action="store_true",
                        help="print matches instead of emailing")
    args = parser.parse_args(argv)

    cfg = load_criteria()
    rt = Runtime()
    matcher = Matcher(cfg)
    seen = SeenStore(rt.seen_store)

    posts = collect_posts(cfg, rt)
    log.info("evaluating %d posts", len(posts))

    hits: List[MatchResult] = []
    for post in posts:
        if seen.has(post.fingerprint):
            continue
        result = matcher.evaluate(post)
        if result.shortlisted:
            hits.append(result)
        # Mark seen regardless, so a non-match is not re-evaluated forever.
        seen.add(post.fingerprint)

    hits.sort(key=lambda r: r.score, reverse=True)
    log.info("%d new shortlisted match(es)", len(hits))

    if args.dry_run:
        for r in hits:
            print(f"[{r.score}] ₹{r.rent or 0:,} {r.post.group_name} :: "
                  f"{' | '.join(r.reasons)}")
            print(f"     {r.post.url}")
        print(f"\n{len(hits)} match(es).")
    else:
        if hits:
            send_digest(EmailSettings.from_env(), hits)
            log.info("digest emailed")
        else:
            log.info("no new matches; no email sent")

    seen.prune(keep_days=30)
    seen.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
