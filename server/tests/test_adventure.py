from osrlib.crawl.adventure import validate_adventure
from osrlib.data import load_equipment, load_monsters

from osrlib_referee_mcp.content import build_adventure


def test_native_adventure_validates_against_the_shipped_catalogs():
    adventure = build_adventure()

    validate_adventure(adventure, load_monsters(), load_equipment())


def test_both_keyed_monster_templates_resolve_against_the_shipped_catalog():
    monsters = load_monsters()

    assert monsters.get("giant_rat").id == "giant_rat"
    assert monsters.get("skeleton").id == "skeleton"
