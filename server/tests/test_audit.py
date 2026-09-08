"""`session_audit`'s shape: the real roll trajectory, filtered and visibility-scoped.

The audit is a superset over `bx-referee` (which keeps no roll-log). It reads the live
event log — a referee's `RollDice` adjudication and a battle round's attack/save rolls —
filtered by kind and by the constitution-Article-II visibility boundary.
"""

import pytest
from osrlib.crawl.commands import (
    EnterDungeon,
    LightSource,
    MoveParty,
    OpenDoor,
    ResolveBattleRound,
    RollDice,
)
from osrlib.crawl.dungeon import Direction

from helpers import battle_round_declarations
from osrlib_referee_mcp.content import ADVENTURE_ID, DUNGEON_ID, LIGHT_SOURCE_ATTEMPTS, SESSION_SEED
from osrlib_referee_mcp.server import execute, observe, session_audit, session_new


def _codes(result):
    return [event["code"] for event in result["events"]]


async def _delve_into_battle():
    await session_new(ADVENTURE_ID, seed=SESSION_SEED)
    await execute(EnterDungeon(dungeon_id=DUNGEON_ID))
    hero_id = observe()["party"][0]["id"]
    for _ in range(LIGHT_SOURCE_ATTEMPTS):
        if "exploration.light.lit" in _codes(await execute(LightSource(character_id=hero_id, item_id="torch"))):
            break
    await execute(OpenDoor(direction=Direction.EAST))
    await execute(MoveParty(direction=Direction.EAST))
    await execute(MoveParty(direction=Direction.EAST))
    assert observe()["mode"] == "battle"


@pytest.mark.anyio
async def test_audit_surfaces_a_referee_roll_and_battle_rolls(_fresh_store):
    await _delve_into_battle()
    # A referee freeform adjudication roll (referee visibility).
    await execute(RollDice(expression="1d20"))
    # One battle round produces attack rolls (player visibility).
    group_id = observe()["encounter"]["groups"][0]["id"]
    await execute(ResolveBattleRound(declarations=battle_round_declarations(group_id)))

    audit = session_audit()
    event_types = {event["event_type"] for event in audit["events"]}
    assert "dice_rolled" in event_types  # the referee's RollDice
    assert "attack_rolled" in event_types  # the battle round
    assert audit["command_count"] >= 1


@pytest.mark.anyio
async def test_audit_visibility_boundary_hides_referee_rolls_from_the_player_view(_fresh_store):
    await _delve_into_battle()
    await execute(RollDice(expression="2d6"))

    referee_view = session_audit(visibility="referee")
    player_view = session_audit(visibility="player")

    # The referee's own adjudication roll is referee-only until the fiction reveals it.
    assert any(e["event_type"] == "dice_rolled" for e in referee_view["events"])
    assert all(e["event_type"] != "dice_rolled" for e in player_view["events"])
    assert all(e["visibility"] == "player" for e in player_view["events"])


@pytest.mark.anyio
async def test_audit_filters_by_kind_and_bounds_by_limit(_fresh_store):
    await _delve_into_battle()
    await execute(RollDice(expression="1d6"))
    await execute(RollDice(expression="1d6"))

    only_dice = session_audit(kinds=["dice_rolled"])
    assert only_dice["events"]
    assert all(e["event_type"] == "dice_rolled" for e in only_dice["events"])

    bounded = session_audit(kinds=["dice_rolled"], limit=1)
    assert bounded["returned"] == 1
    assert bounded["total_matched"] >= 2

    # limit=0 bounds to nothing (a naive matched[-0:] would return the whole list).
    none = session_audit(kinds=["dice_rolled"], limit=0)
    assert none["returned"] == 0
    assert none["events"] == []
    assert none["total_matched"] >= 2
