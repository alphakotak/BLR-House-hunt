"""Tiny JSON-backed store so a post is emailed at most once."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict


class SeenStore:
    def __init__(self, path: str):
        self.path = Path(path)
        self._seen: Dict[str, str] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._seen = json.loads(self.path.read_text("utf-8"))
            except (json.JSONDecodeError, OSError):
                self._seen = {}

    def has(self, fingerprint: str) -> bool:
        return fingerprint in self._seen

    def add(self, fingerprint: str) -> None:
        self._seen[fingerprint] = datetime.now(timezone.utc).isoformat()

    def prune(self, keep_days: int = 30) -> None:
        """Drop entries older than keep_days to stop the file growing forever."""
        cutoff = datetime.now(timezone.utc).timestamp() - keep_days * 86400
        kept = {}
        for fp, iso in self._seen.items():
            try:
                ts = datetime.fromisoformat(iso).timestamp()
            except ValueError:
                ts = cutoff  # unparseable -> drop
            if ts >= cutoff:
                kept[fp] = iso
        self._seen = kept

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._seen, indent=0), "utf-8")
