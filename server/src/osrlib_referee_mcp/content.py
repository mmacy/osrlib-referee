"""The Phase 0 session fixture: a hardcoded, fixed-seed, in-memory walking skeleton.

This is a stand-in for Phase 1's real session lifecycle (`session_new`/`session_load`/
`session_save`). It is deliberately native — built entirely from `osrlib`'s installed
public API, per
[`docs/front-ends/llm-referees.md`](https://mmacy.github.io/osrlib-python/front-ends/llm-referees/)
— and is thrown away once Phase 1 lands. Do not import from `osrlib.examples`: the
published wheel does not ship it.
"""

from osrlib.core.alignment import Alignment
from osrlib.core.character import CHARACTER_CREATION_STREAM, create_character
from osrlib.core.rng import RngStreams
from osrlib.core.ruleset import Ruleset
from osrlib.crawl.adventure import Adventure, TownSpec
from osrlib.crawl.dungeon import DungeonSpec, Edge, EdgeKind, LevelSpec
from osrlib.crawl.party import Party
from osrlib.crawl.session import GameSession


def build_session(seed: int = 7) -> GameSession:
    """Build the Phase 0 fixture: one fighter in a two-cell dungeon, at round 0 in town.

    Args:
        seed: The master seed. Fixed by default so the fixture is reproducible.

    Returns:
        A fresh `GameSession` in `SessionMode.TOWN`.
    """
    ruleset = Ruleset()
    stream = RngStreams(master_seed=seed).get(CHARACTER_CREATION_STREAM)
    hero = create_character(
        name="Hild",
        class_id="fighter",
        alignment=Alignment.LAWFUL,
        ruleset=ruleset,
        stream=stream,
    )
    level = LevelSpec(
        number=1,
        width=2,
        height=1,
        entrance=(0, 0),
        edges={"1,0:west": Edge(kind=EdgeKind.OPEN)},
    )
    crypt = DungeonSpec(id="crypt", name="The Old Crypt", levels=(level,))
    town = TownSpec(name="Threshold", travel_turns={"crypt": 1})
    adventure = Adventure(name="A First Delve", town=town, dungeons=(crypt,))
    return GameSession.new(Party(members=[hero.character]), adventure, seed=seed)
