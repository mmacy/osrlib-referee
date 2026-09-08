"""Level-up inference from `observe`, and the honest HP-restore divergence.

Advancement is engine-automatic and eventless: no `LevelUp` command, no level-up event —
the only signal is `XpAwardedEvent.level_after` rising, and the new state is read from the
projection. This pins that inference path, and pins osrlib's divergence from `bx-referee`:
a wounded character who levels is *still wounded* (osrlib heals no existing damage).
"""

import pytest
from osrlib.crawl.commands import AwardXP

from osrlib_referee_mcp.content import ADVENTURE_ID
from osrlib_referee_mcp.projection import build_character_sheet
from osrlib_referee_mcp.server import execute, observe, session_new


@pytest.mark.anyio
async def test_award_crossing_a_threshold_levels_up_and_observe_shows_the_new_state(_fresh_store):
    await session_new(ADVENTURE_ID, seed=1)
    session = _fresh_store.session
    fighter = session.party.members[0]
    fighter.current_hp = 1  # wound the fighter to 1 HP before the level-up
    hero_id = fighter.id

    before = next(m for m in observe()["party"] if m["id"] == hero_id)
    assert before["level"] == 1
    max_hp_before = before["max_hp"]

    # A big award: no level-up event exists, so the advance is inferred from level_after.
    result = await execute(AwardXP(character_id=hero_id, amount=50_000))
    assert result["accepted"]
    xp_event = next(e for e in result["events"] if e["event_type"] == "xp_awarded")
    assert xp_event["level_after"] == 2, "the award did not cross the level-2 threshold"

    after = next(m for m in observe()["party"] if m["id"] == hero_id)
    assert after["level"] == 2
    assert after["max_hp"] > max_hp_before, "leveling added no hit points to max"
    # The HP-restore divergence: osrlib adds the rolled HP to both max and current but
    # heals no damage — a wounded character who levels is still wounded.
    assert after["current_hp"] < after["max_hp"], "level-up wrongly restored the wound"
    assert after["current_hp"] == 1 + (after["max_hp"] - max_hp_before)

    # The full derived sheet materializes the new level's numbers on demand.
    sheet = build_character_sheet(session, hero_id)
    assert sheet["level"] == 2
    assert sheet["max_hp"] == after["max_hp"]


@pytest.mark.anyio
async def test_next_level_threshold_is_surfaced_per_member(_fresh_store):
    await session_new(ADVENTURE_ID, seed=1)
    fighter = next(m for m in observe()["party"] if m["class_id"] == "fighter")
    # The fighter's level-2 threshold, read from the progression row — how close to advancing.
    assert fighter["next_level_xp"] == 2000
    assert fighter["xp"] == 0
