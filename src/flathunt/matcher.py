"""Scores a post against your criteria and decides if it is a shortlist hit.

The scoring is deliberately transparent: every post carries a list of the
reasons it passed or failed, so the email digest can show *why* something
was shortlisted. Tune weights and terms in config/criteria.yaml, not here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

from .models import Post


@dataclass
class MatchResult:
    post: Post
    score: int
    rent: Optional[int]
    reasons: List[str] = field(default_factory=list)
    rejections: List[str] = field(default_factory=list)
    shortlisted: bool = False


# Matches money written as: 35k, 35,000, 35000, rs 35000, ₹35k, 40 k
_RENT_RE = re.compile(
    r"(?:rs\.?|inr|₹)?\s*"
    r"(\d{1,3}(?:,\d{3})+|\d{2,6})"
    r"\s*(k|thousand)?",
    re.IGNORECASE,
)


def _contains_any(text: str, terms: List[str]) -> List[str]:
    """Return the terms that appear in text (already lower-cased)."""
    return [t for t in terms if t.lower() in text]


def extract_rents(text: str) -> List[int]:
    """Pull plausible monthly-rent figures (INR) out of free text.

    Returns every candidate; the matcher decides which to trust. We only
    keep values in a sane rent band (5k-200k) to avoid picking up phone
    numbers, pincodes, square footage, etc.
    """
    rents: List[int] = []
    for raw_num, k in _RENT_RE.findall(text):
        num = int(raw_num.replace(",", ""))
        if k:  # "35k" -> 35000
            num *= 1000
        if 5000 <= num <= 200000:
            rents.append(num)
    return rents


class Matcher:
    def __init__(self, config: dict):
        self.cfg = config
        s = config.get("search", {})
        self.min_score = int(s.get("min_score", 3))
        self.max_age_hours = float(s.get("max_age_hours", 240))

        b = config.get("budget", {})
        self.max_rent = int(b.get("max_rent", 40000))
        self.tolerance = float(b.get("tolerance", 1.10))

        self.gender = config.get("gender", {})
        self.room = config.get("room", {})
        loc = config.get("location", {})
        self.societies = loc.get("societies", [])
        self.neighbourhoods = loc.get("neighbourhoods", [])
        self.rent_signals = config.get("rent_signal_terms", [])

    def evaluate(self, post: Post) -> MatchResult:
        text = " ".join(post.text.lower().split())  # normalise whitespace
        res = MatchResult(post=post, score=0, rent=None)

        # --- Hard rejections first -------------------------------------
        age = post.age_hours()
        if age is not None and age > self.max_age_hours:
            res.rejections.append(f"too old ({age:.0f}h)")
            return res

        female_hits = _contains_any(text, self.gender.get("exclude_terms", []))
        # "male/female" contains "female only"? no, but guard the combined case.
        female_hits = [t for t in female_hits if not self._is_mixed_gender(text, t)]
        if female_hits:
            res.rejections.append(f"female-only: {female_hits[0]}")
            return res

        seeker_hits = _contains_any(text, self.room.get("exclude_terms", []))
        if seeker_hits:
            res.rejections.append(f"unwanted type: {seeker_hits[0]}")
            return res

        # --- Rent -------------------------------------------------------
        rents = extract_rents(text)
        if rents:
            # A room-share post usually quotes the per-head/lowest figure as
            # the relevant one; take the smallest sane candidate.
            res.rent = min(rents)
            hard_cap = self.max_rent * self.tolerance
            if res.rent > hard_cap:
                res.rejections.append(f"over budget (₹{res.rent:,})")
                return res
            if res.rent <= self.max_rent:
                res.score += 2
                res.reasons.append(f"rent ₹{res.rent:,} within budget")
            else:
                res.score += 1
                res.reasons.append(f"rent ₹{res.rent:,} slightly over, flagged")

        # --- Location (society names weigh more than neighbourhoods) ----
        soc = _contains_any(text, self.societies)
        nbh = _contains_any(text, self.neighbourhoods)
        if soc:
            res.score += 3
            res.reasons.append(f"society: {', '.join(soc[:3])}")
        if nbh:
            res.score += 2
            res.reasons.append(f"area: {', '.join(nbh[:3])}")
        if not soc and not nbh:
            res.rejections.append("no target location mentioned")
            # not an instant reject; just no location points

        # --- Room / share signal ---------------------------------------
        room_hits = _contains_any(text, self.room.get("positive_terms", []))
        if room_hits:
            res.score += 2
            res.reasons.append(f"room signal: {', '.join(room_hits[:3])}")

        # --- Gender positive --------------------------------------------
        male_hits = _contains_any(text, self.gender.get("positive_terms", []))
        if male_hits:
            res.score += 1
            res.reasons.append(f"open to males: {', '.join(male_hits[:2])}")

        # --- Is this even a rental post? --------------------------------
        if _contains_any(text, self.rent_signals):
            res.score += 1
            res.reasons.append("rental keywords present")

        res.shortlisted = res.score >= self.min_score
        if not res.shortlisted and not res.rejections:
            res.rejections.append(f"score {res.score} < {self.min_score}")
        return res

    @staticmethod
    def _is_mixed_gender(text: str, female_term: str) -> bool:
        """Guard: 'male/female' or 'male or female' means open to males."""
        return bool(re.search(r"male\s*[/&+or]{1,3}\s*female", text))
