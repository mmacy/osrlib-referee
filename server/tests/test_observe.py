"""`observe`'s shape: the scoped projection, never the raw `RefereeView`."""

import pytest
from osrlib.crawl.adventure import Adventure, TownSpec
from osrlib.crawl.commands import EnterDungeon, LightSource, MoveParty, OpenDoor
from osrlib.crawl.dungeon import (
    AreaSpec,
    Direction,
    DoorSpec,
    DungeonSpec,
    Edge,
    EdgeKind,
    LevelSpec,
    edge_key,
)
from osrlib.crawl.party import Party
from osrlib.crawl.session import GameSession

from osrlib_referee_mcp.content import (
    ADVENTURE_ID,
    DUNGEON_ID,
    LIGHT_SOURCE_ATTEMPTS,
    SESSION_SEED,
    build_scripted_party,
)
from osrlib_referee_mcp.projection import build_observation
from osrlib_referee_mcp.server import execute, observe, session_new


def _secret_door_adventure() -> Adventure:
    """A minimal one-room adventure with an undiscovered secret door.

    A standalone fixture rather than a change to the scripted-delve adventure: the
    referee un-masking assertion needs a secret door, which the golden delve does
    not otherwise exercise.
    """
    level = LevelSpec(
        number=1,
        width=2,
        height=1,
        entrance=(0, 0),
        edges={edge_key((0, 0), Direction.EAST): Edge(kind=EdgeKind.DOOR, door=DoorSpec(kind="secret"))},
        areas=(AreaSpec(id="cell", name="Cell", cells=((0, 0),)),),
    )
    dungeon = DungeonSpec(id="vault", name="Vault", levels=(level,))
    town = TownSpec(name="Nowhere", travel_turns={"vault": 1})
    return Adventure(name="Secret Door Fixture", town=town, dungeons=(dungeon,))


def _secret_door_session() -> GameSession:
    party = Party(members=list(build_scripted_party().members))
    session = GameSession.new(party, _secret_door_adventure(), seed=1)
    session.execute(EnterDungeon(dungeon_id="vault"))
    return session


def test_projection_never_carries_the_whole_adventure_or_the_full_event_log():
    session = _secret_door_session()

    observation = build_observation(session, cold=True)

    assert "adventure" not in observation
    assert "command_log" not in observation
    assert "rng_streams" not in observation
    assert "master_seed" not in observation
    assert len(observation["events"]) <= 20


def test_area_is_null_in_a_corridor():
    """`area_at()` returns `None` outside any keyed area; the projection must too."""
    level = LevelSpec(
        number=1,
        width=2,
        height=1,
        entrance=(0, 0),
        edges={edge_key((0, 0), Direction.EAST): Edge(kind=EdgeKind.OPEN)},
    )
    dungeon = DungeonSpec(id="empty", name="Empty", levels=(level,))
    town = TownSpec(name="Nowhere", travel_turns={"empty": 1})
    adventure = Adventure(name="Corridor Fixture", town=town, dungeons=(dungeon,))
    party = Party(members=list(build_scripted_party().members))
    session = GameSession.new(party, adventure, seed=1)
    session.execute(EnterDungeon(dungeon_id="empty"))

    observation = build_observation(session)

    assert observation["area"] is None


def test_referee_view_unmasks_undiscovered_secret_doors():
    """The player view masks an undiscovered secret door to `"wall"`; the referee
    projection must show its true kind — the one masking `observe` reverses."""
    session = _secret_door_session()

    observation = build_observation(session)

    assert observation["edges"]["east"]["kind"] == "door"
    assert observation["edges"]["east"]["secret"] is True


@pytest.mark.anyio
async def test_referee_view_shows_real_monster_hp_in_battle():
    await session_new(ADVENTURE_ID, seed=SESSION_SEED)
    await execute(EnterDungeon(dungeon_id=DUNGEON_ID))

    hero_id = observe()["party"][0]["id"]
    for _ in range(LIGHT_SOURCE_ATTEMPTS):
        result = await execute(LightSource(character_id=hero_id, item_id="torch"))
        if any(e["code"] == "exploration.light.lit" for e in result["events"]):
            break
    await execute(OpenDoor(direction=Direction.EAST))
    await execute(MoveParty(direction=Direction.EAST))
    await execute(MoveParty(direction=Direction.EAST))

    observation = observe()

    assert observation["mode"] == "battle"
    monster = observation["encounter"]["groups"][0]["monsters"][0]
    assert monster["current_hp"] == monster["max_hp"]
    assert monster["current_hp"] > 0


def test_legal_commands_are_split_player_intent_and_authorial():
    session = _secret_door_session()

    observation = build_observation(session)

    assert "move_party" in observation["legal_commands"]["player_intent"]
    assert "set_flag" in observation["legal_commands"]["authorial"]
    assert "set_flag" not in observation["legal_commands"]["player_intent"]
