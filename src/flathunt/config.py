"""Load YAML criteria and environment-based settings."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml


def load_criteria(path: Optional[str] = None) -> dict:
    p = Path(path or os.environ.get("CRITERIA_PATH", "config/criteria.yaml"))
    if not p.exists():
        raise FileNotFoundError(f"criteria file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class EmailSettings:
    host: str
    port: int
    user: str
    password: str
    sender: str
    recipients: list

    @classmethod
    def from_env(cls) -> "EmailSettings":
        recipients = os.environ.get("EMAIL_TO", "").strip()
        return cls(
            host=os.environ.get("SMTP_HOST", "smtp.gmail.com"),
            port=int(os.environ.get("SMTP_PORT", "587")),
            user=os.environ.get("SMTP_USER", ""),
            password=os.environ.get("SMTP_PASS", ""),
            sender=os.environ.get("EMAIL_FROM", os.environ.get("SMTP_USER", "")),
            recipients=[r.strip() for r in recipients.split(",") if r.strip()],
        )

    def validate(self) -> None:
        missing = [
            name
            for name, val in {
                "SMTP_USER": self.user,
                "SMTP_PASS": self.password,
                "EMAIL_TO": self.recipients,
            }.items()
            if not val
        ]
        if missing:
            raise RuntimeError(
                "Missing email settings: " + ", ".join(missing)
                + ". Set them as environment variables / GitHub secrets."
            )


@dataclass
class Runtime:
    storage_state: str = os.environ.get("FB_STORAGE_STATE_PATH", "data/fb_state.json")
    seen_store: str = os.environ.get("SEEN_STORE_PATH", "data/seen.json")
    headless: bool = os.environ.get("HEADLESS", "1") != "0"
    # When set, skip Facebook entirely and read posts from this JSON fixture.
    # Handy for testing the matcher + email without touching Facebook.
    fixture: Optional[str] = os.environ.get("POSTS_FIXTURE") or None
