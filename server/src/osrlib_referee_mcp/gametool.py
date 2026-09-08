"""Static reference reads for play — off the play tool surface, by design.

Shopping in town, narrating an advance, and offering a resume menu all need reference
data that **never changes mid-session**: the equipment catalog and its prices, the six
temple healing services, a class's XP progression, and the list of saved games. None of
it depends on the live session, so — by the standing-schema rule that governs the whole
project — none of it goes on the play `FastMCP` server (a tool there advertises its
schema to every play turn). It is a CLI instead, the sibling of `bundletool` and
`chargen`, invoked during a town or resume exchange:

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog
uv run --project server python -m osrlib_referee_mcp.gametool services
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter
uv run --project server python -m osrlib_referee_mcp.gametool saves
```

so it costs play sessions zero standing schema.
"""

import argparse
import json
import sys
from pathlib import Path

from osrlib.core.classes import ClassDefinition
from osrlib.crawl.exploration import HEALING_SERVICES
from osrlib.data import load_classes, load_equipment

from osrlib_referee_mcp.gamedir import resolve_game_root, saves_dir


def _weapon_entry(template) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "item_type": "weapon",
        "cost_gp": template.cost_gp,
        "lot_size": 1,
        "damage": template.damage,
        "weight_coins": template.weight_coins,
    }


def _armour_entry(template) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "item_type": "armour",
        "cost_gp": template.cost_gp,
        "lot_size": 1,
        "ac": template.ac,
        "ac_ascending": template.ac_ascending,
        "ac_bonus": template.ac_bonus,
        "weight_coins": template.weight_coins,
    }


def _gear_entry(template) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "item_type": "gear",
        "cost_gp": template.cost_gp,
        "lot_size": template.lot_size,
        "damage": template.combat.damage if template.combat is not None else None,
    }


def _ammunition_entry(template) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "item_type": "ammunition",
        "cost_gp": template.cost_gp,
        "lot_size": template.lot_size,
    }


def catalog_result(kind: str | None = None) -> dict[str, object]:
    """Read the SRD equipment catalog — ids, names, costs, lot sizes, damage.

    Args:
        kind: Optionally restrict to `"weapon"`, `"armour"`, `"gear"`, or
            `"ammunition"`. Omit for the whole catalog.

    Returns:
        `{items: [...]}`, one entry per equipment template, each carrying the fields a
        player needs to shop against a gold total.
    """
    catalog = load_equipment()
    items: list[dict[str, object]] = []
    if kind in (None, "weapon"):
        items.extend(_weapon_entry(template) for template in catalog.weapons)
    if kind in (None, "armour"):
        items.extend(_armour_entry(template) for template in catalog.armour)
    if kind in (None, "gear"):
        items.extend(_gear_entry(template) for template in catalog.gear)
    if kind in (None, "ammunition"):
        items.extend(_ammunition_entry(template) for template in catalog.ammunition)
    return {"items": items}


def services_result() -> dict[str, object]:
    """Read the temple's six healing services and their gp prices.

    Returns:
        `{services: [{service, spell_id, cost_gp}, ...]}`, from osrlib's `HEALING_SERVICES`
        table — the `service` value is exactly what `PurchaseHealing(service=…)` expects.
    """
    services = [
        {"service": service, "spell_id": spell_id, "cost_gp": cost_gp}
        for service, (spell_id, cost_gp) in HEALING_SERVICES.items()
    ]
    return {"services": services}


def _progression_row(definition: ClassDefinition, level: int) -> dict[str, object]:
    row = definition.row(level)
    return {
        "level": row.level,
        "xp": row.xp,
        "hit_dice": {"count": row.hit_dice.count, "die": row.hit_dice.die, "bonus": row.hit_dice.bonus},
        "thac0": row.thac0,
    }


def thresholds_result(class_id: str) -> dict[str, object]:
    """Read a class's full XP-and-level progression.

    Args:
        class_id: A class id, e.g. `"fighter"`.

    Returns:
        `{class_id, name, max_level, progression: [{level, xp, hit_dice, thac0}, ...]}`.

    Raises:
        ValueError: If `class_id` names no class.
    """
    definition = load_classes().get(class_id)
    return {
        "class_id": definition.id,
        "name": definition.name,
        "max_level": definition.max_level,
        "progression": [_progression_row(definition, level) for level in range(1, definition.max_level + 1)],
    }


def saves_result(game_root: Path) -> dict[str, object]:
    """Enumerate saved games in the game directory — the resume menu.

    Game-directory enumeration is a filesystem read, not live-session state, so it is a
    CLI (no standing play cost). Newest first, by file modification time.

    Args:
        game_root: The resolved game-root directory.

    Returns:
        `{saves: [{adventure_id, save_id, schema_version, engine_version, mtime}, ...]}`.
    """
    root = saves_dir(game_root)
    entries: list[dict[str, object]] = []
    if root.is_dir():
        for path in root.glob("*/*.json"):
            entry: dict[str, object] = {
                "adventure_id": path.parent.name,
                "save_id": path.stem,
                "mtime": path.stat().st_mtime,
                "schema_version": None,
                "engine_version": None,
            }
            try:
                document = json.loads(path.read_text())
            except json.JSONDecodeError, OSError:
                document = {}
            if isinstance(document, dict):
                entry["schema_version"] = document.get("schema_version")
                entry["engine_version"] = document.get("engine_version")
            entries.append(entry)
    entries.sort(key=lambda entry: entry["mtime"], reverse=True)
    return {"saves": entries}


def _cmd_catalog(args: argparse.Namespace) -> int:
    print(json.dumps(catalog_result(args.kind), indent=2))
    return 0


def _cmd_services(args: argparse.Namespace) -> int:
    print(json.dumps(services_result(), indent=2))
    return 0


def _cmd_thresholds(args: argparse.Namespace) -> int:
    try:
        result = thresholds_result(args.class_id)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2))
    return 0


def _cmd_saves(args: argparse.Namespace) -> int:
    print(json.dumps(saves_result(resolve_game_root()), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the `gametool` argument parser.

    Returns:
        The parser, with `catalog`, `services`, `thresholds`, and `saves` subcommands.
    """
    parser = argparse.ArgumentParser(prog="gametool", description="Static play reference reads.")
    sub = parser.add_subparsers(dest="command", required=True)

    catalog = sub.add_parser("catalog", help="The SRD equipment catalog: ids, names, costs, lot sizes, damage.")
    catalog.add_argument(
        "--kind", choices=["weapon", "armour", "gear", "ammunition"], default=None, help="Restrict to one item kind."
    )
    catalog.set_defaults(func=_cmd_catalog)

    services = sub.add_parser("services", help="The six temple healing services and their prices.")
    services.set_defaults(func=_cmd_services)

    thresholds = sub.add_parser("thresholds", help="A class's XP-and-level progression.")
    thresholds.add_argument("class_id", help="The class id, e.g. 'fighter'.")
    thresholds.set_defaults(func=_cmd_thresholds)

    saves = sub.add_parser("saves", help="Enumerate saved games in the game directory (the resume menu).")
    saves.set_defaults(func=_cmd_saves)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: The argument vector; defaults to `sys.argv[1:]`.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
