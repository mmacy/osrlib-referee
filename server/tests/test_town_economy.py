"""The town economy and the automatic return-trip XP award, in-process.

Drives the `TOWN`-gated commands the `play` skill executes — buy, sell, heal, depart —
and then the delve's return, where the engine awards monster + treasure XP automatically
and a big-enough treasure haul crosses a level threshold, firing the engine-owned,
eventless level-up. All through the real server tool functions.
"""

import pytest
from osrlib.core.items import MagicItemInstance, ValuableInstance
from osrlib.crawl.commands import (
    BattleDeclaration,
    EnterDungeon,
    LightSource,
    MoveParty,
    OpenDoor,
    PurchaseEquipment,
    PurchaseHealing,
    ResolveBattleRound,
    SellTreasure,
    TravelToTown,
)
from osrlib.crawl.dungeon import Direction

from osrlib_referee_mcp.content import ADVENTURE_ID, DUNGEON_ID, LIGHT_SOURCE_ATTEMPTS, SESSION_SEED
from osrlib_referee_mcp.server import execute, observe, session_new


def _codes(result):
    return [event["code"] for event in result["events"]]


@pytest.mark.anyio
async def test_purchase_equipment_affordable_succeeds_over_budget_rejects_atomically(_fresh_store):
    await session_new(ADVENTURE_ID, seed=1)
    hero = observe()["party"][0]
    hero_id = hero["id"]

    bought = await execute(PurchaseEquipment(character_id=hero_id, item_ids=("torch",)))
    assert bought["accepted"]

    before = observe()["party"][0]["purse"]
    over_budget = tuple("plate_mail" for _ in range(100))
    rejected = await execute(PurchaseEquipment(character_id=hero_id, item_ids=over_budget))
    assert not rejected["accepted"]
    assert any(rej["code"] == "items.purchase.insufficient_funds" for rej in rejected["rejections"])
    # Atomic: an unaffordable basket buys nothing and debits nothing.
    assert observe()["party"][0]["purse"] == before


@pytest.mark.anyio
async def test_sell_treasure_valuable_sells_magic_item_rejects(_fresh_store):
    await session_new(ADVENTURE_ID, seed=1)
    session = _fresh_store.session
    member = session.party.members[0]
    member.inventory.valuables.append(ValuableInstance(instance_id="gem-1", kind="gem", name="a ruby", value_gp=500))
    before_gp = member.inventory.purse.gp

    sold = await execute(SellTreasure(item_ids=("gem-1",)))
    assert sold["accepted"]
    assert any(e["event_type"] == "treasure_sold" and e["gp_value"] == 500 for e in sold["events"])
    assert session.party.members[0].inventory.purse.gp == before_gp + 500

    # A magic item has no fixed sale value (RAW) and rejects.
    member.inventory.items.append(MagicItemInstance(instance_id="mi-1", template_id="armour_plus_1"))
    rejected = await execute(SellTreasure(item_ids=("mi-1",)))
    assert not rejected["accepted"]
    assert any(rej["code"] == "town.sell.no_fixed_value" for rej in rejected["rejections"])


@pytest.mark.anyio
async def test_purchase_healing_heals_and_debits_the_purse(_fresh_store):
    await session_new(ADVENTURE_ID, seed=1)
    session = _fresh_store.session
    member = session.party.members[0]
    member.current_hp = 1  # wound the member so the cure has something to restore
    member.inventory.purse.gp = 100
    hero_id = member.id

    healed = await execute(PurchaseHealing(character_id=hero_id, service="cure_light_wounds"))
    assert healed["accepted"]
    assert any(e["event_type"] == "healing_purchased" and e["cost_gp"] == 25 for e in healed["events"])
    after = session.party.members[0]
    assert after.inventory.purse.gp == 100 - 25
    assert after.current_hp > 1


@pytest.mark.anyio
async def test_return_trip_awards_monster_and_treasure_xp_and_levels_up(_fresh_store):
    """The scripted delve's return: defeat the keyed rats, recover a big haul, return.

    Reuses the Phase-1 golden's proven encounter_a victory at `SESSION_SEED`, then grants
    a large treasure and returns — so the engine's automatic on-return award carries both
    a positive `monster_xp` (the giant rats) and the exact granted `treasure_xp`, and the
    haul is large enough that every survivor crosses their level-2 threshold (the engine
    clamps to exactly one level per award).
    """
    await session_new(ADVENTURE_ID, seed=SESSION_SEED)
    await execute(EnterDungeon(dungeon_id=DUNGEON_ID))
    hero_id = observe()["party"][0]["id"]

    for _ in range(LIGHT_SOURCE_ATTEMPTS):
        light = await execute(LightSource(character_id=hero_id, item_id="torch"))
        if "exploration.light.lit" in _codes(light):
            break

    await execute(OpenDoor(direction=Direction.EAST))
    await execute(MoveParty(direction=Direction.EAST))  # spring the trap, into the antechamber
    await execute(MoveParty(direction=Direction.EAST))  # into the nesting hollow — battle opens
    assert observe()["mode"] == "battle"

    rounds = 0
    while observe()["mode"] == "battle" and rounds < 20:
        rounds += 1
        group_id = observe()["encounter"]["groups"][0]["id"]
        declarations = tuple(
            BattleDeclaration(character_id=member["id"], action="attack", target_group_id=group_id)
            for member in observe()["party"]
            if member["current_hp"] > 0
        )
        await execute(ResolveBattleRound(declarations=declarations))
    assert observe()["mode"] == "exploring", "encounter_a did not resolve to victory"

    # Recover a large treasure after the departure snapshot: 1 gp = 1 XP on return. A
    # near-weightless gem, not coins — coins weigh 1 each and a 30,000-coin haul would
    # overload the party past its max load, and treasure XP counts a valuable's value_gp
    # exactly as a coin's, so this is a faithful stand-in for a recovered cache.
    haul_gp = 30_000
    _fresh_store.session.party.members[0].inventory.valuables.append(
        ValuableInstance(instance_id="haul", kind="gem", name="a great emerald", value_gp=haul_gp, weight_coins=1)
    )

    # Walk back to the entrance cell (the only legal spot for TravelToTown).
    await execute(MoveParty(direction=Direction.WEST))  # into the antechamber
    await execute(OpenDoor(direction=Direction.WEST))  # the entrance door swung shut behind us
    await execute(MoveParty(direction=Direction.WEST))  # onto the entrance cell
    assert observe()["area"]["id"] == "entrance"

    levels_before = {m["id"]: m["level"] for m in observe()["party"]}
    home = await execute(TravelToTown())
    assert home["accepted"]
    assert observe()["mode"] == "town"

    awards = [e for e in home["events"] if e["event_type"] == "adventure_xp_award"]
    assert len(awards) == 1
    award = awards[0]
    assert award["treasure_xp"] == haul_gp
    assert award["monster_xp"] > 0  # the defeated giant rats

    xp_events = [e for e in home["events"] if e["event_type"] == "xp_awarded"]
    assert xp_events, "no per-member XP awarded"
    # The haul dwarfs every class's level-2 threshold; the engine clamps to exactly one level.
    for event in xp_events:
        assert event["level_after"] == levels_before[event["character_id"]] + 1
