"""The `gametool` static reference reads: catalog, services, and class thresholds.

These are the off-play-surface reads the `play` and `session` skills invoke during a town
or resume exchange. (Save enumeration is covered by test_session_lifecycle.)
"""

import pytest

from osrlib_referee_mcp import gametool


def test_catalog_carries_shopping_fields_for_every_kind():
    catalog = gametool.catalog_result()
    by_id = {item["id"]: item for item in catalog["items"]}
    # A weapon carries damage; armour carries AC; gear carries a lot size.
    assert by_id["sword"]["item_type"] == "weapon"
    assert by_id["sword"]["damage"]
    assert by_id["leather"]["item_type"] == "armour"
    assert by_id["leather"]["cost_gp"] == 20
    torch = by_id["torch"]
    assert torch["item_type"] == "gear"
    assert torch["lot_size"] == 6  # one lot of torches is six torches


def test_catalog_kind_filter_restricts_the_list():
    armour_only = gametool.catalog_result("armour")
    assert armour_only["items"]
    assert all(item["item_type"] == "armour" for item in armour_only["items"])


def test_services_match_the_purchase_healing_service_ids():
    services = gametool.services_result()["services"]
    ids = {entry["service"] for entry in services}
    assert ids == {
        "cure_light_wounds",
        "cure_serious_wounds",
        "cure_disease",
        "neutralize_poison",
        "remove_curse",
        "raise_dead",
    }
    cure_light = next(s for s in services if s["service"] == "cure_light_wounds")
    assert cure_light["cost_gp"] == 25


def test_thresholds_report_the_full_progression():
    fighter = gametool.thresholds_result("fighter")
    assert fighter["max_level"] == 14
    rows = {row["level"]: row["xp"] for row in fighter["progression"]}
    assert rows[1] == 0
    assert rows[2] == 2000


def test_thresholds_unknown_class_raises():
    with pytest.raises(ValueError, match="unknown class id"):
        gametool.thresholds_result("paladin")
