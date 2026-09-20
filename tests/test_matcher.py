import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from flathunt.matcher import Matcher, extract_rents  # noqa: E402
from flathunt.models import Post  # noqa: E402

CFG = yaml.safe_load(
    (Path(__file__).resolve().parents[1] / "config/criteria.yaml").read_text()
)
M = Matcher(CFG)
NOW = datetime.now(timezone.utc)


def _post(text, when=None):
    return Post(text=text, url="http://x", posted_at=when or NOW)


def test_extract_rents_variants():
    assert extract_rents("rent 22k per head") == [22000]
    assert extract_rents("Rs 35,000 per month") == [35000]
    assert 30000 in extract_rents("30000 deposit two months")
    # phone numbers / pincodes should not be read as rent
    assert extract_rents("call 9876543210 pincode 560103") == []


def test_shortlists_good_male_room_in_area():
    r = M.evaluate(_post(
        "One room available in 3BHK at Adarsh Palm Retreat, Bellandur. "
        "Male flatmate, rent 22k per head, walkable to RMZ Ecoworld."
    ))
    assert r.shortlisted
    assert r.rent == 22000


def test_rejects_female_only():
    r = M.evaluate(_post("Spare room in 2bhk, females only, rent 18000"))
    assert not r.shortlisted
    assert any("female" in x for x in r.rejections)


def test_mixed_gender_is_allowed():
    r = M.evaluate(_post(
        "Roommate for 3 bhk in Prestige Jade Pavilion, male/female, "
        "rent 30k sharing, gated community near ecoworld"
    ))
    assert r.shortlisted


def test_rejects_over_budget():
    r = M.evaluate(_post(
        "4BHK villa Sarjapur Road rent 95000 per month, room available"
    ))
    assert not r.shortlisted
    assert any("budget" in x for x in r.rejections)


def test_rejects_seeker_and_pg():
    seeker = M.evaluate(_post("Flat wanted, looking for a room near Bellandur, male"))
    assert not seeker.shortlisted
    pg = M.evaluate(_post("PG for gents in Marathahalli, 14000/month, single bed"))
    assert not pg.shortlisted


def test_rejects_too_old():
    from datetime import timedelta
    old = M.evaluate(_post(
        "Room available male flatmate Bellandur 20k rent",
        when=NOW - timedelta(hours=1000),
    ))
    assert not old.shortlisted
    assert any("old" in x for x in old.rejections)
