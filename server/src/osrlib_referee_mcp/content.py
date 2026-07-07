"""The native Phase-1 adventure: a one-level barrow crypt reached from a town.

Authored directly against `osrlib`'s installed public content model, in the spirit of
the `tui_crawler` example (`~/repos/osrlib-python/examples/tui_crawler/content.py`) —
never imported from `osrlib.examples`, since the published wheel does not ship it.

The level is a straight corridor: `entrance` (town-side, no content of its own) → a
door → `trap_room` (a no-save 1d8 room trap) → `encounter_a` (a weak, trivially
winnable `giant_rat` pack — the fight beat) → a bare corridor cell → `encounter_b` (a
`skeleton` guard, the flee beat). `encounter_a` sits on the walk-back path so the
scripted delve exercises a keyed-area revisit (already resolved, so it does not
re-open) without re-triggering a fight; `encounter_b` is the dead end and is never
revisited after the flee.

`encounter_b`'s monster choice is deliberate, not incidental: a `skeleton`'s base
ground movement rate (60 ft/turn) exactly ties the scripted party's slowest member
(a chainmail-armoured fighter/cleric under `EncumbranceMode.BASIC`, also 60 ft/turn).
`crawl.encounter._pursuit_round` computes the per-round pursuit gap as
`gap + party_run_rate - pursuer_rate` with no random draw on this path (the
distraction roll only fires on the pre-battle `Evade` command, never reachable once a
pinned `stance=ATTACKS` opens battle directly) — so a rate tie holds the gap exactly
constant every round, guaranteeing the party reaches the round cap
(`PURSUIT_ROUND_CAP = 30`) and escapes cleanly, regardless of seed. This is a content
lever, not a seed lever: a faster monster (e.g. `giant_rat`, 120 ft/turn) would close
the gap by 60 ft every round and catch the party almost immediately.
"""

from collections.abc import Callable

from osrlib.core.alignment import Alignment
from osrlib.core.character import CHARACTER_CREATION_STREAM, create_character, party_to_document
from osrlib.core.rng import RngStreams
from osrlib.core.ruleset import Ruleset
from osrlib.core.tables import ReactionResult
from osrlib.crawl.adventure import Adventure, TownSpec
from osrlib.crawl.dungeon import (
    AreaSpec,
    Direction,
    DoorSpec,
    DungeonSpec,
    Edge,
    EdgeKind,
    KeyedEncounter,
    KeyedMonster,
    LevelSpec,
    TrapEffect,
    TrapSpec,
    WanderingSpec,
    edge_key,
)
from osrlib.crawl.party import Party

DUNGEON_ID = "barrow_crypt"
ADVENTURE_NAME = "The Barrow Crypt"

# The server's adventure-registry key (`session_new`/`list_adventures`), a distinct
# concept from `DUNGEON_ID` (the `EnterDungeon(dungeon_id=...)` command argument) that
# happens to share a value while Phase 1 ships exactly one adventure with one dungeon.
ADVENTURE_ID = DUNGEON_ID

# The frozen pregen roster: a fighter, a cleric, and a thief, each in chainmail or
# leather (no infravision, so the LightSource beat is exercised — the trap's
# automatic on-entry 2-in-6 spring roll never consults party composition at all;
# a dwarf's passive detection only matters via an explicit Search, which the
# scripted delve never issues in the trap room). Built from its own fixed
# creation seed, independent of the tunable session seed below — re-tuning the
# session seed must never re-roll the party's stats.
PARTY_CREATION_SEED = 1
_SCRIPT_PARTY = (
    (
        "Brakka",
        "fighter",
        Alignment.LAWFUL,
        (("sword", 1), ("chainmail", 1), ("shield", 1), ("torch", 1), ("tinder_box", 1)),
        ("sword", "chainmail", "shield"),
    ),
    ("Wynn", "cleric", Alignment.LAWFUL, (("mace", 1), ("chainmail", 1)), ("mace", "chainmail")),
    ("Sable", "thief", Alignment.NEUTRAL, (("short_sword", 1), ("leather", 1)), ("short_sword", "leather")),
)

# The tunable session seed: the exact scripted command prefix (EnterDungeon, the
# LightSource attempts it takes to catch, OpenDoor, MoveParty into trap_room) springs
# the trap at this seed, wins encounter_a with a comfortable margin (no member below
# 60% HP), and — though this leg is a content-level guarantee, not a seed lever, see
# the module docstring — cleanly escapes encounter_b. Found by search over the exact
# scripted prefix. Distinct from `PARTY_CREATION_SEED`.
SESSION_SEED = 187
LIGHT_SOURCE_ATTEMPTS = 5
"""How many `LightSource` commands the scripted delve issues at `SESSION_SEED` before
the torch catches. Fixed alongside the seed — the golden test pins this exact count."""


def build_scripted_party() -> Party:
    """Build the frozen pregen roster from its own fixed creation seed.

    Returns:
        A three-member `Party`: fighter, cleric, thief.
    """
    ruleset = Ruleset()
    stream = RngStreams(master_seed=PARTY_CREATION_SEED).get(CHARACTER_CREATION_STREAM)
    members = []
    for name, class_id, alignment, purchases, equip_ids in _SCRIPT_PARTY:
        result = create_character(
            name=name,
            class_id=class_id,
            alignment=alignment,
            ruleset=ruleset,
            stream=stream,
            purchases=purchases,
            equip_ids=equip_ids,
        )
        members.append(result.character)
    return Party(members=members)


def _open(position: tuple[int, int], direction) -> dict[str, Edge]:
    return {edge_key(position, direction): Edge(kind=EdgeKind.OPEN)}


def _door(position: tuple[int, int], direction) -> dict[str, Edge]:
    return {edge_key(position, direction): Edge(kind=EdgeKind.DOOR, door=DoorSpec())}


def build_adventure() -> Adventure:
    """Build the native Phase-1 adventure: one town, one dungeon, one level.

    Returns:
        The frozen `Adventure` spec. Validate with `validate_adventure` before use.
    """
    edges: dict[str, Edge] = {}
    edges.update(_door((0, 0), Direction.EAST))
    edges.update(_open((1, 0), Direction.EAST))
    edges.update(_open((2, 0), Direction.EAST))
    edges.update(_open((3, 0), Direction.EAST))

    level = LevelSpec(
        number=1,
        width=5,
        height=1,
        entrance=(0, 0),
        edges=edges,
        areas=(
            AreaSpec(
                id="entrance",
                name="Crypt entrance",
                description="A crumbling stone archway, choked with roots.",
                cells=((0, 0),),
            ),
            AreaSpec(
                id="trap_room",
                name="Sunken antechamber",
                description="The flagstones here sag, cracked by some old weight.",
                cells=((1, 0),),
                trap=TrapSpec(kind="room", trigger="enter", effect=TrapEffect(damage_dice="1d8")),
            ),
            AreaSpec(
                id="encounter_a",
                name="Nesting hollow",
                description="Gnawed bones and a rank, ammoniac stench.",
                cells=((2, 0),),
                encounter=KeyedEncounter(
                    monsters=(KeyedMonster(template_id="giant_rat", count_fixed=2),),
                    stance=ReactionResult.ATTACKS,
                ),
            ),
            AreaSpec(
                id="encounter_b",
                name="Guarded crypt",
                description="A stone sarcophagus, its lid pushed aside from within.",
                cells=((4, 0),),
                encounter=KeyedEncounter(
                    monsters=(KeyedMonster(template_id="skeleton", count_fixed=3),),
                    stance=ReactionResult.ATTACKS,
                ),
            ),
        ),
        wandering=WanderingSpec(chance_in_six=0),
    )
    dungeon = DungeonSpec(id=DUNGEON_ID, name="The Barrow Crypt", levels=(level,))
    town = TownSpec(name="Threshold", travel_turns={DUNGEON_ID: 2})
    return Adventure(name=ADVENTURE_NAME, town=town, dungeons=(dungeon,))


# The out-of-band prose sidecar: authored read-aloud + referee notes per area id,
# original content. `AreaSpec.description` (above) is the engine-visible, opaque,
# display-only string; this is the narration split the engine has no place for.
PROSE_SIDECAR: dict[str, dict[str, str]] = {
    "town": {
        "read_aloud": (
            "Threshold huddles behind a timber palisade where the moor road gives out. "
            "Smoke bends sideways off the tavern chimney; a shrine bell tolls the hour."
        ),
        "referee_notes": (
            "Safe ground. No wandering checks, no clock pressure. Departure snapshots party "
            "treasure for the return-trip XP award."
        ),
    },
    "entrance": {
        "read_aloud": (
            "A crumbling stone archway leans out of the hillside, its lintel carved with weathered "
            "spirals. Roots have split the threshold stone. Cold air breathes up out of the dark."
        ),
        "referee_notes": (
            "The dungeon entrance and the only legal cell for TravelToTown. A stout door bars the passage east."
        ),
    },
    "trap_room": {
        "read_aloud": (
            "The passage opens into a low antechamber. The flagstones here sag visibly, cracked "
            "in a rough circle, as though something heavy once rested on them and then did not."
        ),
        "referee_notes": (
            "A no-save 1d8 room trap, trigger=enter, springs on a 2-in-6 exploration-stream roll the "
            "instant the party steps onto the cell (not on searching it). A search that finds the trap "
            "first disarms this beat entirely — the scripted delve does not search here."
        ),
    },
    "encounter_a": {
        "read_aloud": (
            "Gnawed bones are scattered across the floor, and the air is thick with a rank, ammoniac "
            "reek. Something skitters in the dark just as the light finds it: a knot of huge rats, "
            "already lunging."
        ),
        "referee_notes": (
            "Two giant rats, stance pinned to ATTACKS: battle opens the instant the party enters, no "
            "reaction roll. Weak (1d4 HP, 1d3 bite, morale 8) — content-trivial for a 3-member armed "
            "party. Marked resolved on victory, so the walk-back revisit does not reopen it."
        ),
    },
    "encounter_b": {
        "read_aloud": (
            "A stone sarcophagus dominates the crypt's back wall, its lid shoved askew from within. "
            "A skeletal guardian rises from the dark behind it, jaw working soundlessly, and comes on."
        ),
        "referee_notes": (
            "Three skeletons, stance pinned to ATTACKS. This is the flee beat: the skeleton's 60 ft/turn "
            "ground speed exactly ties the party's own (chainmail-slowed) rate, so an all-member retreat "
            "holds the pursuit gap constant and guarantees a clean escape at the 30-round pursuit cap — "
            "a content-level guarantee, not a seed-dependent one. Never re-entered after the flee (a fled, "
            "not-defeated encounter never joins `resolved_encounters`)."
        ),
    },
}


def default_party_document() -> dict[str, object]:
    """The frozen pregen party, serialized as `session_new`'s default `party_document`.

    Returns:
        The `party_to_document` output for the frozen pregen roster's members.
    """
    return party_to_document(build_scripted_party().members)


ADVENTURE_REGISTRY: dict[str, Callable[[], Adventure]] = {ADVENTURE_ID: build_adventure}
"""The server's native adventure registry — one entry in Phase 1; Phase 2's module
ingestion grows it."""
