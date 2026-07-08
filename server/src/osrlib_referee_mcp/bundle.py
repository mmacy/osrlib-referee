"""The adventure bundle: an on-disk `Adventure` + prose sidecar + manifest, and its gates.

`osrlib` ships no adventure file format and no adventure loader — adventures are built
in pure Python. The bundle format and loader are entirely this repo's to invent, from
the building blocks osrlib provides: the `Adventure` model, `model_validate`/
`model_dump`, and `validate_adventure`.

A bundle is a directory of three JSON files:

- `adventure.json` — `Adventure.model_dump(mode="json")`. Keyed `template_id`s are
  **always stock SRD ids** (reskins are resolved to SRD templates at compile time).
- `prose.json` — `{area_id: {read_aloud, referee_notes}}`, keyed by `AreaSpec.id`, plus
  the reserved `"town"` key. Scene-setting only; it never renames a reskinned creature.
- `manifest.json` — `{bundle_id, name, description, osrlib_version, license,
  approximations}`, where `approximations` is `{reskins, geometry, escape_hatch}` — the
  audit log of everything the compile approximated or pushed to the escape hatch. There
  is **no `catalog.json`**: an SRD-only bundle injects nothing.

[`load_bundle`][osrlib_referee_mcp.bundle.load_bundle] reconstructs the `Adventure`
(the loader the play server calls); [`validate_bundle`][osrlib_referee_mcp.bundle.validate_bundle]
is the compile-time gate — it runs `validate_adventure` against the stock catalogs plus
the two checks `validate_adventure` skips (edge-key integrity and wandering-table
resolution). Both live off the play tool surface (see
[`osrlib_referee_mcp.bundletool`][osrlib_referee_mcp.bundletool]).
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

from osrlib.crawl.adventure import Adventure, validate_adventure
from osrlib.crawl.dungeon import Direction, LevelSpec
from osrlib.data import load_equipment, load_monsters
from osrlib.errors import ContentValidationError
from pydantic import ValidationError

ADVENTURE_FILE = "adventure.json"
PROSE_FILE = "prose.json"
MANIFEST_FILE = "manifest.json"

# A bundle id doubles as the on-disk save-directory name and the discovery key, so it
# must be a filesystem-safe slug that can never be confused with a path fragment.
_BUNDLE_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9_-]*[a-z0-9])?$")

# The canonical edge-key grammar: a non-negative cell plus `north` or `west` only
# (`edge_key` never emits `:south`/`:east`). Free-form `edges` keys are otherwise
# unvalidated by osrlib.
_EDGE_KEY_RE = re.compile(r"^(\d+),(\d+):(north|west)$")


@dataclass(frozen=True)
class LoadedBundle:
    """A bundle reconstructed from disk: the model, the prose sidecar, and the manifest."""

    bundle_id: str
    name: str
    description: str
    adventure: Adventure
    prose: dict[str, dict[str, str]]
    manifest: dict[str, object]


def _read_json(path: Path) -> object:
    if not path.is_file():
        raise ContentValidationError(f"bundle file {path.name!r} is missing under {path.parent}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ContentValidationError(f"bundle file {path.name!r} is not valid JSON: {exc}") from exc


def _require_mapping(value: object, what: str) -> dict:
    if not isinstance(value, dict):
        raise ContentValidationError(f"{what} must be a JSON object, got {type(value).__name__}")
    return value


def load_bundle(bundle_dir: Path) -> LoadedBundle:
    """Reconstruct a bundle from its directory — the loader the play server calls.

    Reconstructs the `Adventure` with `Adventure.model_validate`, re-firing every model
    validator so a malformed spec raises at load rather than surfacing in play. This does
    **not** call `validate_adventure`: `GameSession.new` self-validates against the stock
    catalog, so the loadable check happens there (see
    [`validate_bundle`][osrlib_referee_mcp.bundle.validate_bundle] for the compile gate).

    Args:
        bundle_dir: The bundle directory holding `adventure.json`, `prose.json`, and
            `manifest.json`.

    Returns:
        The loaded bundle.

    Raises:
        ContentValidationError: A file is missing, malformed, or the adventure spec
            fails schema validation.
    """
    manifest = _require_mapping(_read_json(bundle_dir / MANIFEST_FILE), "manifest.json")
    prose = _require_mapping(_read_json(bundle_dir / PROSE_FILE), "prose.json")
    adventure_dict = _require_mapping(_read_json(bundle_dir / ADVENTURE_FILE), "adventure.json")

    try:
        adventure = Adventure.model_validate(adventure_dict)
    except ValidationError as exc:
        raise ContentValidationError(f"adventure.json failed schema validation:\n{exc}") from exc

    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id:
        raise ContentValidationError(f"manifest.json needs a non-empty string 'bundle_id', got {bundle_id!r}")
    name = manifest.get("name") if isinstance(manifest.get("name"), str) else adventure.name
    description = manifest.get("description") if isinstance(manifest.get("description"), str) else adventure.description
    return LoadedBundle(
        bundle_id=bundle_id,
        name=name,
        description=description,
        adventure=adventure,
        prose={str(key): dict(value) for key, value in prose.items() if isinstance(value, dict)},
        manifest=manifest,
    )


def read_manifest(bundle_dir: Path) -> dict[str, object]:
    """Read a bundle's manifest alone — the cheap read `list_adventures` uses.

    Listing every discovered bundle must not reconstruct every `Adventure` (one bad
    bundle would break the whole list), so discovery reads only the manifest for a
    bundle's id, name, and description.

    Args:
        bundle_dir: The bundle directory.

    Returns:
        The manifest dict.

    Raises:
        ContentValidationError: The manifest is missing or malformed.
    """
    return _require_mapping(_read_json(bundle_dir / MANIFEST_FILE), "manifest.json")


def edge_key_integrity_errors(adventure: Adventure) -> list[str]:
    """Report `edges` keys the engine will silently never read — the dead-entry check.

    `LevelSpec.edges` keys are free-form and unvalidated by osrlib, and `LevelSpec.edge`
    returns a wall unless **both** cells the edge separates are in bounds. A key naming a
    boundary edge (owner in bounds, neighbour off-grid — e.g. `"0,0:west"`), or a key not
    in canonical `"{x},{y}:north|west"` form at all, is a dead entry the engine ignores.
    This mirrors `LevelSpec.edge`'s own in-bounds rule — a grid test, **not** membership
    in an `AreaSpec` (a legitimate corridor edge can belong to a bare cell in no area).

    Args:
        adventure: The reconstructed adventure.

    Returns:
        One message per dead or malformed edge key; empty when every key is live.
    """
    errors: list[str] = []
    for dungeon in adventure.dungeons:
        for level in dungeon.levels:
            owner = f"{dungeon.id} level {level.number}"
            for key in level.edges:
                match = _EDGE_KEY_RE.match(key)
                if match is None:
                    errors.append(f"{owner}: edge key {key!r} is not a canonical '{{x}},{{y}}:north|west' key")
                    continue
                x, y, side = int(match.group(1)), int(match.group(2)), match.group(3)
                owner_cell = (x, y)
                neighbour = (x, y - 1) if side == "north" else (x - 1, y)
                if not level.in_bounds(owner_cell) or not level.in_bounds(neighbour):
                    errors.append(
                        f"{owner}: edge key {key!r} names a boundary edge "
                        f"(separates {owner_cell} and {neighbour}); the engine never reads it"
                    )
    return errors


def wandering_table_errors(adventure: Adventure, monsters) -> list[str]:
    """Report wandering-table monster ids that don't resolve against the stock catalog.

    `validate_adventure` resolves keyed-encounter and feature ids but **never** a
    `WanderingSpec.table`'s template ids, so a bad id there passes validation and fails
    at `spawn`. This resolves every monster row of every level's custom wandering table.

    Args:
        adventure: The reconstructed adventure.
        monsters: The stock monster catalog (`load_monsters()`).

    Returns:
        One message per unresolved id; empty when every wandering id resolves.
    """
    errors: list[str] = []
    for dungeon in adventure.dungeons:
        for level in dungeon.levels:
            table = level.wandering.table
            if table is None:
                continue
            owner = f"{dungeon.id} level {level.number}"
            for row in table.rows:
                entry = row.entry
                if getattr(entry, "kind", None) != "monster":
                    continue
                for monster_id in entry.monster_ids:
                    try:
                        monsters.get(monster_id)
                    except ValueError:
                        errors.append(
                            f"{owner}: wandering table row {row.roll} references unknown monster {monster_id!r}"
                        )
    return errors


def _prose_key_errors(adventure: Adventure, prose: dict[str, dict[str, str]]) -> list[str]:
    area_ids = {area.id for dungeon in adventure.dungeons for level in dungeon.levels for area in level.areas}
    valid = area_ids | {"town"}
    return [f"prose.json key {key!r} is neither 'town' nor a real area id" for key in prose if key not in valid]


def validate_bundle(bundle_dir: Path) -> None:
    """The compile-time gate: reconstruct, validate against stock, and report all at once.

    Runs `Adventure.model_validate` then `validate_adventure` **passing the stock
    catalogs** (as `GameSession.new` does), so keyed `template_id`s and feature `item_id`s
    resolve against stock — that already catches a reskin that named a non-existent SRD
    template, the reserved `'pile'` feature id, id-uniqueness, and (via the model itself)
    a `KeyedMonster` that fails exactly-one-of. On top, it adds the two checks
    `validate_adventure` genuinely skips — edge-key integrity and wandering-table
    resolution — plus a manifest `bundle_id` slug check and a prose-key sanity check, so
    every problem is reported in one pass.

    Args:
        bundle_dir: The bundle directory to validate.

    Raises:
        ContentValidationError: The bundle is missing files, malformed, or carries any
            unresolved reference or dead edge key. The message lists every problem found.
    """
    manifest = _require_mapping(_read_json(bundle_dir / MANIFEST_FILE), "manifest.json")
    prose = _require_mapping(_read_json(bundle_dir / PROSE_FILE), "prose.json")
    adventure_dict = _require_mapping(_read_json(bundle_dir / ADVENTURE_FILE), "adventure.json")

    errors: list[str] = []
    bundle_id = manifest.get("bundle_id")
    if not isinstance(bundle_id, str) or not _BUNDLE_ID_RE.match(bundle_id):
        errors.append(f"manifest.json 'bundle_id' must be a slug matching {_BUNDLE_ID_RE.pattern}, got {bundle_id!r}")

    try:
        adventure = Adventure.model_validate(adventure_dict)
    except ValidationError as exc:
        # A spec that won't even reconstruct can't be cross-referenced; report and stop.
        raise ContentValidationError(f"adventure.json failed schema validation:\n{exc}") from exc

    monsters = load_monsters()
    try:
        validate_adventure(adventure, monsters, load_equipment())
    except ContentValidationError as exc:
        errors.append(str(exc))
    errors.extend(edge_key_integrity_errors(adventure))
    errors.extend(wandering_table_errors(adventure, monsters))
    errors.extend(_prose_key_errors(adventure, {str(key): value for key, value in prose.items()}))

    if errors:
        raise ContentValidationError("bundle validation failed:\n" + "\n".join(errors))


def render_map(level: LevelSpec) -> str:
    """Render a level's grid — cells, edges, and doors — as text for the map-diff gate.

    The visual review gate a human uses to compare the compiled map against the source
    module's map before accepting a bundle. Edges are queried through `LevelSpec.edge`,
    so the render honours the same boundary-is-wall rule the engine plays by.

    Args:
        level: The level to render.

    Returns:
        A monospaced grid: `@` the entrance, a letter per keyed area (with a legend),
        `.` corridor, `D` a door, `|`/`-` walls, and blank an open passage.
    """
    labels: dict[str, str] = {}
    legend: list[str] = []
    for index, area in enumerate(level.areas):
        letter = chr(ord("A") + index) if index < 26 else "?"
        labels[area.id] = letter
        legend.append(f"  {letter} = {area.id}" + (f" ({area.name})" if area.name else ""))

    def hedge(cell: tuple[int, int], direction: Direction) -> str:
        kind = level.edge(cell, direction).kind
        return {"door": "-D-", "open": "   "}.get(kind.value, "---")

    def vedge(cell: tuple[int, int], direction: Direction) -> str:
        kind = level.edge(cell, direction).kind
        return {"door": "D", "open": " "}.get(kind.value, "|")

    def content(cell: tuple[int, int]) -> str:
        if cell == level.entrance:
            char = "@"
        else:
            area = level.area_at(cell)
            char = labels.get(area.id, "?") if area is not None else "."
        return f" {char} "

    lines: list[str] = []
    for y in range(level.height):
        lines.append("+" + "+".join(hedge((x, y), Direction.NORTH) for x in range(level.width)) + "+")
        row = "".join(vedge((x, y), Direction.WEST) + content((x, y)) for x in range(level.width))
        lines.append(row + vedge((level.width - 1, y), Direction.EAST))
    lines.append("+" + "+".join(hedge((x, level.height - 1), Direction.SOUTH) for x in range(level.width)) + "+")

    out = "\n".join(lines)
    if legend:
        out += "\n\nLegend:\n" + "\n".join(legend)
    out += "\n  @ = entrance   . = corridor   D = door"
    return out
