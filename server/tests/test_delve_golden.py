"""The scripted delve, in-process, driven through the real server tool functions.

Pins the exact seed and command prefix `docs/phase-1-plan.md` and `content.py`'s
module docstring describe: enter, light the torch (retrying until it catches), open
the door, spring the trap, fight `encounter_a` to victory, flee `encounter_b`, walk
back through both already-resolved areas without re-triggering them, and return to
town. This is the automatable proxy for Milestone A's manual Claude Code play-through
— the current test session is not running `--plugin-dir .`, so driving the tool
functions directly is how the delve is proven without the plugin loaded.
"""

import pytest
from osrlib.crawl.commands import (
    BattleDeclaration,
    EnterDungeon,
    LightSource,
    MoveParty,
    OpenDoor,
    ResolveBattleRound,
    TravelToTown,
    Wait,
)
from osrlib.crawl.dungeon import Direction

from helpers import battle_round_declarations
from osrlib_referee_mcp.content import ADVENTURE_ID, DUNGEON_ID, LIGHT_SOURCE_ATTEMPTS, SESSION_SEED
from osrlib_referee_mcp.server import execute, observe, session_new

PURSUIT_ROUND_CAP = 30


async def _new_delve_session():
    await session_new(ADVENTURE_ID, seed=SESSION_SEED)


def _event_codes(result: dict) -> list[str]:
    return [event["code"] for event in result["events"]]


@pytest.mark.anyio
async def test_scripted_delve_end_to_end():
    await _new_delve_session()

    enter = await execute(EnterDungeon(dungeon_id=DUNGEON_ID))
    assert enter["accepted"]
    assert observe()["mode"] == "exploring"

    hero_id = observe()["party"][0]["id"]
    attempts_used = 0
    lit = False
    for _attempt in range(1, LIGHT_SOURCE_ATTEMPTS + 1):
        attempts_used += 1
        light = await execute(LightSource(character_id=hero_id, item_id="torch"))
        assert light["accepted"]
        if "exploration.light.lit" in _event_codes(light):
            lit = True
            break
    assert lit, f"torch did not catch within the pinned {LIGHT_SOURCE_ATTEMPTS} attempts"
    assert attempts_used == LIGHT_SOURCE_ATTEMPTS, "the pinned seed's light-attempt count drifted"

    opened = await execute(OpenDoor(direction=Direction.EAST))
    assert opened["accepted"]

    sprung = await execute(MoveParty(direction=Direction.EAST))
    assert sprung["accepted"]
    assert "exploration.trap.sprung" in _event_codes(sprung)
    assert observe()["area"]["id"] == "trap_room"

    opened_a = await execute(MoveParty(direction=Direction.EAST))
    assert opened_a["accepted"]
    assert observe()["mode"] == "battle"
    assert observe()["area"]["id"] == "encounter_a"

    rounds = 0
    while observe()["mode"] == "battle" and rounds < 20:
        rounds += 1
        group_id = observe()["encounter"]["groups"][0]["id"]
        round_result = await execute(ResolveBattleRound(declarations=battle_round_declarations(group_id)))
        assert round_result["accepted"]
    assert observe()["mode"] == "exploring", "encounter_a did not resolve to victory"
    assert all(member["current_hp"] > 0 for member in observe()["party"]), "a party member dropped in encounter_a"

    corridor = await execute(MoveParty(direction=Direction.EAST))
    assert corridor["accepted"]

    opened_b = await execute(MoveParty(direction=Direction.EAST))
    assert opened_b["accepted"]
    assert observe()["mode"] == "battle"
    assert observe()["area"]["id"] == "encounter_b"

    retreat = tuple(
        BattleDeclaration(character_id=character_id, action="move", move="retreat")
        for character_id in observe()["encounter"]["declarers"]
    )
    fled = await execute(ResolveBattleRound(declarations=retreat))
    assert fled["accepted"]
    assert "battle.ended.fled" in _event_codes(fled)
    assert observe()["mode"] == "encounter"

    waits = 0
    while observe()["mode"] == "encounter" and waits < PURSUIT_ROUND_CAP + 5:
        waits += 1
        wait_result = await execute(Wait())
        assert wait_result["accepted"]
    assert observe()["mode"] == "exploring", "the flee never escaped to exploring"
    assert waits == PURSUIT_ROUND_CAP, "the rate-tied pursuit no longer holds the gap constant"

    back_to_corridor = await execute(MoveParty(direction=Direction.WEST))
    assert back_to_corridor["accepted"]

    revisit_a = await execute(MoveParty(direction=Direction.WEST))
    assert revisit_a["accepted"]
    assert observe()["mode"] == "exploring", "resolved encounter_a re-opened on revisit"
    assert observe()["encounter"] is None

    revisit_trap = await execute(MoveParty(direction=Direction.WEST))
    assert revisit_trap["accepted"]
    assert "exploration.trap.sprung" not in _event_codes(revisit_trap), "the sprung trap re-sprang on revisit"

    reopened_door = await execute(OpenDoor(direction=Direction.WEST))
    assert reopened_door["accepted"]

    back_to_entrance = await execute(MoveParty(direction=Direction.WEST))
    assert back_to_entrance["accepted"]
    assert observe()["area"]["id"] == "entrance"

    home = await execute(TravelToTown())
    assert home["accepted"]
    assert observe()["mode"] == "town"


@pytest.mark.anyio
async def test_trap_golden_springs_on_the_pinned_seed_and_prefix():
    """The determinism-lever golden: the exact seed + prefix springs the trap.

    Guards the seed search in `content.py` against any change to the scripted
    prefix — a different light-attempt count or a reordered prefix can shift every
    downstream `EXPLORATION_STREAM` draw.
    """
    await _new_delve_session()
    await execute(EnterDungeon(dungeon_id=DUNGEON_ID))
    hero_id = observe()["party"][0]["id"]

    for _ in range(LIGHT_SOURCE_ATTEMPTS):
        light = await execute(LightSource(character_id=hero_id, item_id="torch"))
        if "exploration.light.lit" in _event_codes(light):
            break

    await execute(OpenDoor(direction=Direction.EAST))
    sprung = await execute(MoveParty(direction=Direction.EAST))

    assert "exploration.trap.sprung" in _event_codes(sprung)
