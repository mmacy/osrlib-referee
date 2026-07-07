"""Generate the committed fixture bundle — a tiny, licensing-safe stock-SRD adventure.

Run to regenerate the on-disk fixture the bundle round-trip and in-process delve tests
load:

```bash
uv run python tests/fixtures/build_fixture_bundle.py
```

Original content (CC0), stock SRD template ids only, so it commits in-repo. Deliberately
small: one town, one dungeon, one 3x1 level — an entrance, a vault (a treasure cache),
and a rat den (a keyed `giant_rat`). It carries a valid custom wandering table (never
fired, `chance_in_six=0`) purely so `validate_bundle`'s wandering-resolution check runs
against a real table.
"""

import json
from pathlib import Path

from osrlib.core.items import Coins
from osrlib.core.tables import EncounterTable, EncounterTableRow, MonsterEncounterEntry
from osrlib.crawl.adventure import Adventure, TownSpec
from osrlib.crawl.dungeon import (
    AreaSpec,
    Direction,
    DoorSpec,
    DungeonSpec,
    Edge,
    EdgeKind,
    FeatureSpec,
    KeyedEncounter,
    KeyedMonster,
    LevelSpec,
    WanderingSpec,
    edge_key,
)
from osrlib.versioning import engine_version

BUNDLE_ID = "fixture_crypt"
DUNGEON_ID = "redhollow_vault"

FIXTURE_DIR = Path(__file__).resolve().parent / "bundles" / BUNDLE_ID


def _wandering_table() -> EncounterTable:
    rows = tuple(
        EncounterTableRow(
            roll=roll,
            name="Giant rats",
            entry=MonsterEncounterEntry(monster_ids=("giant_rat",)),
            count_fixed=1,
        )
        for roll in range(1, 21)
    )
    return EncounterTable(id="fixture_wander", label="Fixture wandering", min_level=1, rows=rows)


def build_adventure() -> Adventure:
    """Build the fixture adventure spec.

    Returns:
        The `Adventure` the fixture bundle serializes.
    """
    edges: dict[str, Edge] = {
        edge_key((0, 0), Direction.EAST): Edge(kind=EdgeKind.DOOR, door=DoorSpec()),
        edge_key((1, 0), Direction.EAST): Edge(kind=EdgeKind.OPEN),
    }
    level = LevelSpec(
        number=1,
        width=3,
        height=1,
        entrance=(0, 0),
        edges=edges,
        areas=(
            AreaSpec(
                id="entrance",
                name="Vault door",
                description="A low stone door in the hillside.",
                cells=((0, 0),),
            ),
            AreaSpec(
                id="vault",
                name="Strong room",
                description="A dry stone chamber, its far wall lined with rotted shelving.",
                cells=((1, 0),),
                features=(
                    FeatureSpec(
                        id="strongbox",
                        kind="treasure_cache",
                        description="An iron-banded strongbox.",
                        item_ids=("dagger",),
                        coins=Coins(gp=25),
                    ),
                ),
            ),
            AreaSpec(
                id="den",
                name="Rat den",
                description="A reeking hollow of gnawed bone.",
                cells=((2, 0),),
                encounter=KeyedEncounter(monsters=(KeyedMonster(template_id="giant_rat", count_fixed=1),)),
            ),
        ),
        wandering=WanderingSpec(chance_in_six=0, table=_wandering_table()),
    )
    dungeon = DungeonSpec(id=DUNGEON_ID, name="The Redhollow Vault", levels=(level,))
    town = TownSpec(name="Redhollow", description="A muddy hamlet.", travel_turns={DUNGEON_ID: 1})
    return Adventure(
        name="The Redhollow Vault",
        description="A one-room fixture vault for round-trip and delve tests.",
        town=town,
        dungeons=(dungeon,),
    )


PROSE: dict[str, dict[str, str]] = {
    "town": {
        "read_aloud": "Redhollow is a scatter of turf-roofed huts around a green.",
        "referee_notes": "Safe ground. The vault lies one turn to the north.",
    },
    "entrance": {
        "read_aloud": "A squat stone door, ajar on darkness, is set into the hillside.",
        "referee_notes": "The only legal cell for TravelToTown. A plain door bars the way east.",
    },
    "vault": {
        "read_aloud": "The strong room is dry and still. An iron-banded strongbox sits against the shelving.",
        "referee_notes": "The strongbox holds a dagger and 25 gp — TakeTreasure(feature_id='strongbox').",
    },
    "den": {
        "read_aloud": "The passage ends in a reeking hollow. Something heavy shifts in the bone-litter.",
        "referee_notes": "One giant rat, no stance pin — a reaction roll opens the beat.",
    },
}


def build_manifest() -> dict[str, object]:
    """Build the fixture manifest.

    Returns:
        The `manifest.json` content.
    """
    return {
        "bundle_id": BUNDLE_ID,
        "name": "The Redhollow Vault",
        "description": "A one-room fixture vault for round-trip and delve tests.",
        "osrlib_version": engine_version(),
        "license": "CC0-1.0",
        "approximations": {"reskins": [], "geometry": [], "escape_hatch": []},
    }


def main() -> None:
    """Write the fixture bundle's three JSON files to the committed fixtures directory."""
    FIXTURE_DIR.mkdir(parents=True, exist_ok=True)
    (FIXTURE_DIR / "adventure.json").write_text(json.dumps(build_adventure().model_dump(mode="json"), indent=2) + "\n")
    (FIXTURE_DIR / "prose.json").write_text(json.dumps(PROSE, indent=2) + "\n")
    (FIXTURE_DIR / "manifest.json").write_text(json.dumps(build_manifest(), indent=2) + "\n")
    print(f"wrote fixture bundle to {FIXTURE_DIR}")


if __name__ == "__main__":
    main()
