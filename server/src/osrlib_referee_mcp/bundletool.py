"""The compiler's deterministic helper CLI — off the play tool surface, by design.

The adventure-module compiler leans on three deterministic, correctness-checkable
helpers: canonical edge keys, bundle validation, and a text map render for the visual
map-diff review gate. These must **not** be registered as `@mcp.tool()` on the play
server: FastMCP advertises every tool's schema in every session that loads the plugin,
so a compiler tool there would add a standing per-turn cost to play sessions that never
compile anything. Instead the compiler skill invokes this module as a script:

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/my-module
uv run --project server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
uv run --project server python -m osrlib_referee_mcp.bundletool render-map adventures/my-module
```

so it costs play sessions zero.
"""

import argparse
import sys
from pathlib import Path

from osrlib.crawl.dungeon import Direction, edge_key
from osrlib.errors import OsrlibError

from osrlib_referee_mcp.bundle import load_bundle, render_map, validate_bundle


def _cmd_validate(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.bundle_dir)
    try:
        validate_bundle(bundle_dir)
    except OsrlibError as exc:
        print(f"INVALID: {bundle_dir}\n{exc}", file=sys.stderr)
        return 1
    print(f"OK: {bundle_dir} is a valid bundle")
    return 0


def _cmd_edge_key(args: argparse.Namespace) -> int:
    print(edge_key((args.x, args.y), Direction(args.direction)))
    return 0


def _cmd_render_map(args: argparse.Namespace) -> int:
    bundle_dir = Path(args.bundle_dir)
    try:
        bundle = load_bundle(bundle_dir)
    except OsrlibError as exc:
        print(f"could not load bundle {bundle_dir}: {exc}", file=sys.stderr)
        return 1
    for dungeon in bundle.adventure.dungeons:
        for level in dungeon.levels:
            if args.level is not None and level.number != args.level:
                continue
            print(f"# {dungeon.id} level {level.number} ({level.width}x{level.height})\n")
            print(render_map(level))
            print()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the `bundletool` argument parser.

    Returns:
        The parser, with `validate`, `edge-key`, and `render-map` subcommands.
    """
    parser = argparse.ArgumentParser(prog="bundletool", description="Adventure-bundle compile helpers.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate a bundle against the stock SRD catalogs.")
    validate.add_argument("bundle_dir", help="The bundle directory to validate.")
    validate.set_defaults(func=_cmd_validate)

    edge = sub.add_parser("edge-key", help="Print the canonical edge key for a cell and direction.")
    edge.add_argument("x", type=int, help="The cell x coordinate.")
    edge.add_argument("y", type=int, help="The cell y coordinate.")
    edge.add_argument("direction", choices=[d.value for d in Direction], help="The edge's direction.")
    edge.set_defaults(func=_cmd_edge_key)

    render = sub.add_parser("render-map", help="Render a bundle's level maps as text for the map-diff gate.")
    render.add_argument("bundle_dir", help="The bundle directory to render.")
    render.add_argument("--level", type=int, default=None, help="Render only this level number.")
    render.set_defaults(func=_cmd_render_map)

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
