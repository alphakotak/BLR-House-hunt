"""Data model for a single scraped post."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Post:
    """A post pulled from a source (Facebook group, etc.)."""

    text: str
    url: str
    source: str = "facebook"
    group_name: str = ""
    author: str = ""
    posted_at: Optional[datetime] = None  # tz-aware if known
    scraped_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def fingerprint(self) -> str:
        """Stable id used for de-duplication.

        Prefer the permalink; fall back to a hash of the text so a post
        without a clean URL is still de-duped.
        """
        basis = self.url.strip() if self.url.strip() else self.text.strip()
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    def age_hours(self, now: Optional[datetime] = None) -> Optional[float]:
        if self.posted_at is None:
            return None
        now = now or datetime.now(timezone.utc)
        return (now - self.posted_at).total_seconds() / 3600.0
