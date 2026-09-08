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

from osrlib_referee_mcp.catalog import list_command_types
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


async def _delve_into_encounter_a():
    """Walk the scripted prefix at `SESSION_SEED` until the giant rats open battle."""
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
    assert observe()["mode"] == "battle"


@pytest.mark.anyio
async def test_referee_view_shows_real_monster_hp_in_battle():
    await _delve_into_encounter_a()

    observation = observe()

    monster = observation["encounter"]["groups"][0]["monsters"][0]
    assert monster["current_hp"] == monster["max_hp"]
    assert monster["current_hp"] > 0


@pytest.mark.anyio
async def test_encounter_block_carries_the_round_roster_the_engine_will_accept():
    """The four id tuples that decide which declarations `ResolveBattleRound` accepts.

    Without them the referee has to guess a formation width, and a wrong guess costs the
    party its round. The barrow crypt's level is one cell tall, so 10 feet of frontage
    seats two of the three members — the front rank is a strict subset of the declarers,
    and that gap is the whole reason these ship.
    """
    await _delve_into_encounter_a()

    encounter = observe()["encounter"]

    party_ids = [member["id"] for member in observe()["party"]]
    assert encounter["declarers"] == party_ids  # all three are living and able
    assert encounter["front_rank"] == party_ids[:2]  # a 10-foot corridor seats two
    assert encounter["immobile"] == []
    assert encounter["reloading"] == []


def test_legal_commands_are_split_player_intent_and_authorial():
    session = _secret_door_session()

    observation = build_observation(session)

    assert "move_party" in observation["legal_commands"]["player_intent"]
    assert "set_flag" in observation["legal_commands"]["authorial"]
    assert "set_flag" not in observation["legal_commands"]["player_intent"]


def test_referee_commands_barred_from_a_terminal_mode_still_read_as_authorial():
    """`SpawnMonsters` and `PlaceParty` are the referee's, not a phase of play's.

    Engine 1.5.0 barred them from an ended session, so "legal in every mode" no longer
    identifies an authorial command — only "legal in every *live* mode" does. Classifying
    them by the old test would file the constitution's own escape hatch under player
    intent, and a terminal session would still advertise commands that resume play.
    """
    live = list_command_types("exploring")
    assert "spawn_monsters" in live["authorial"]
    assert "place_party" in live["authorial"]
    assert live["player_intent"] and "spawn_monsters" not in live["player_intent"]

    ended = list_command_types("victory")
    assert ended["player_intent"] == []
    assert "spawn_monsters" not in ended["authorial"]
    assert "place_party" not in ended["authorial"]
    assert "set_flag" in ended["authorial"]  # the referee can still land an adventure's rewards


def _town_session_with_services() -> GameSession:
    """A session whose town carries service prose, for the town-branch assertions."""
    base = _secret_door_adventure()
    town = TownSpec(
        name="Threshold",
        description="A palisaded waystation.",
        services=("a temple", "a smith"),
        travel_turns=base.town.travel_turns,
    )
    adventure = base.model_copy(update={"town": town})
    party = Party(members=list(build_scripted_party().members))
    return GameSession.new(party, adventure, seed=1)


def test_town_branch_surfaces_purse_valuables_advancement_and_service_prose():
    session = _town_session_with_services()

    observation = build_observation(session)

    assert observation["mode"] == "town"
    # The town's front-end service prose (not the mechanical healing list).
    assert observation["area"]["id"] == "town"
    assert observation["area"]["services"] == ["a temple", "a smith"]
    member = observation["party"][0]
    # The town spend surface plus the advancement fields.
    assert "purse" in member
    assert "valuables" in member
    assert member["level"] == 1
    assert member["xp"] == 0
    assert member["next_level_xp"] == 2000  # the fighter's level-2 threshold
    # Still scoped: never the whole adventure or the full event log.
    assert "adventure" not in observation
    assert "events" not in observation


def test_dungeon_branch_omits_the_town_spend_surface_but_keeps_advancement():
    session = _town_session_with_services()
    session.execute(EnterDungeon(dungeon_id="vault"))

    observation = build_observation(session)

    member = observation["party"][0]
    # Purse/valuables ship only in town; the advancement integers ship every turn.
    assert "purse" not in member
    assert "valuables" not in member
    assert "level" in member
    assert "next_level_xp" in member
