"""The Phase-2 demo: the compiled Sunken Chapel bundle validates, loads, and plays.

The automated proxy for the DoD's manual Claude Code play-through (as in Phase 1). The
delve is navigation-only — enter, light, walk to the font hall, save/reload — because a
loaded bundle plays byte-identically to native content; reskin correctness was proven at
compile time (the manifest audit + `validate_bundle`'s stock-resolution check), not here.
The route deliberately avoids the ossuary (the reskinned-zombie fight) and the stuck door,
so the test turns on no combat outcome and no force-door roll.
"""

import shutil
from pathlib import Path

import pytest
from osrlib.crawl.commands import EnterDungeon, LightSource, MoveParty
from osrlib.crawl.dungeon import Direction

from osrlib_referee_mcp.bundle import load_bundle, validate_bundle
from osrlib_referee_mcp.server import execute, observe, prose, session_load, session_new, session_save

DEMO_DIR = Path(__file__).resolve().parents[2] / "adventures" / "sunken_chapel"
DEMO_ID = "sunken_chapel"


def _event_codes(result: dict) -> list[str]:
    return [event["code"] for event in result["events"]]


def test_demo_bundle_validates_and_has_a_reskin_in_its_audit_log():
    validate_bundle(DEMO_DIR)  # does not raise

    manifest = load_bundle(DEMO_DIR).manifest
    reskins = manifest["approximations"]["reskins"]
    assert any(entry["template_id"] == "zombie" for entry in reskins), "the demo must exercise the reskin path"
    assert manifest["approximations"]["escape_hatch"], "the demo must log its escape-hatch beats"


@pytest.mark.anyio
async def test_demo_bundle_plays_end_to_end(_fresh_store):
    shutil.copytree(DEMO_DIR, _fresh_store.adventures_dir / DEMO_ID)

    new = await session_new(DEMO_ID, seed=11)
    assert new["save_id"] == DEMO_ID
    assert observe()["location"]["kind"] == "town"
    assert prose("town")["found"] is True

    enter = await execute(EnterDungeon(dungeon_id=DEMO_ID))
    assert enter["accepted"]
    assert observe()["area"]["id"] == "entrance"

    hero_id = observe()["party"][0]["id"]
    lit = False
    for _ in range(40):
        light = await execute(LightSource(character_id=hero_id, item_id="torch"))
        assert light["accepted"]
        if "exploration.light.lit" in _event_codes(light):
            lit = True
            break
    assert lit, "torch never caught"

    # Entrance (2,3) -> corridor (2,2) -> junction (2,1) -> corridor (1,1) -> font hall (0,1).
    # Every edge on this route is an open passage, so the walk turns on no door or combat.
    for direction in (Direction.NORTH, Direction.NORTH, Direction.WEST, Direction.WEST):
        step = await execute(MoveParty(direction=direction))
        assert step["accepted"]
    assert observe()["area"]["id"] == "font_hall"
    assert prose("font_hall")["found"] is True

    saved = await session_save()
    reloaded = await session_load(saved["save_id"])

    assert reloaded["save_id"] == DEMO_ID
    assert observe()["area"]["id"] == "font_hall"  # the reload resumes in the font hall
