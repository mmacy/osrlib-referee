"""Capture the osrlib-referee side of the Phase 1 token measurement.

This is instrumentation, not a verdict: it dumps the exact standing-cost artifacts
the measurement methodology (`docs/phase-1-plan.md`, work item 9) needs counted —
the `AnyCommand` input union schema, every tool's output schema, and a representative
`observe()` payload at each of the scripted delve's three distinct scenes (town,
exploring, battle) — to JSON files under `--out-dir`.

This script does **not** tokenize anything. No Anthropic API key or `count_tokens`
access is configured in the environment this was built in, and a mismatched local
tokenizer (e.g. `tiktoken`, built for OpenAI models) would produce a number that
cannot be honestly compared against a `bx-referee` transcript counted a different
way — worse than no number at all. Run these artifacts, plus an equivalently captured
`bx-referee` transcript, through one Anthropic `count_tokens` pass when that
comparison is made (Milestone B, a same-branch follow-on — see `docs/phase-1-plan.md`).

Usage:
    uv run python scripts/capture_token_artifacts.py --out-dir artifacts/
"""

import argparse
import asyncio
import json
import tempfile
from pathlib import Path

from osrlib.crawl.commands import AnyCommand, EnterDungeon, LightSource, MoveParty, OpenDoor
from pydantic import TypeAdapter

from osrlib_referee_mcp import server as server_module
from osrlib_referee_mcp.content import ADVENTURE_ID, DUNGEON_ID, LIGHT_SOURCE_ATTEMPTS, SESSION_SEED
from osrlib_referee_mcp.server import execute, mcp, observe, session_new
from osrlib_referee_mcp.store import SessionStore


def _write(out_dir: Path, name: str, payload: object) -> Path:
    path = out_dir / f"{name}.json"
    text = json.dumps(payload, indent=2, sort_keys=True)
    path.write_text(text)
    return path


async def _capture_observe_scenes(out_dir: Path) -> None:
    """`observe()` at town, exploring, and battle — the standing per-turn payload."""
    await session_new(ADVENTURE_ID, seed=SESSION_SEED, save_id="token-capture")
    _write(out_dir, "observe_town", observe())

    await execute(EnterDungeon(dungeon_id=DUNGEON_ID))
    hero_id = observe()["party"][0]["id"]
    for _ in range(LIGHT_SOURCE_ATTEMPTS):
        result = await execute(LightSource(character_id=hero_id, item_id="torch"))
        if any(event["code"] == "exploration.light.lit" for event in result["events"]):
            break
    await execute(OpenDoor(direction="east"))
    await execute(MoveParty(direction="east"))
    _write(out_dir, "observe_exploring", observe())

    await execute(MoveParty(direction="east"))
    _write(out_dir, "observe_battle", observe())


async def _capture_tool_schemas(out_dir: Path) -> None:
    """Every tool's input/output schema, as FastMCP generates it for the model."""
    tools = await mcp.list_tools()
    schemas = {tool.name: {"inputSchema": tool.inputSchema, "outputSchema": tool.outputSchema} for tool in tools}
    _write(out_dir, "tool_schemas", schemas)


def _capture_any_command_union_schema(out_dir: Path) -> None:
    """The standing `execute` input union schema alone — the plan's headline cost."""
    schema = TypeAdapter(AnyCommand).json_schema()
    _write(out_dir, "any_command_union_schema", schema)


async def main() -> None:
    """Parse `--out-dir` and capture every artifact into it."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    # This capture session is disposable — it must never write a save into the
    # user's real game directory. Point the store at a throwaway temp dir instead
    # of the `~/osr-games` default `SessionStore()` would otherwise resolve.
    with tempfile.TemporaryDirectory() as scratch_game_root:
        server_module._store = SessionStore()
        server_module._store.game_root = Path(scratch_game_root)

        _capture_any_command_union_schema(args.out_dir)
        await _capture_tool_schemas(args.out_dir)
        await _capture_observe_scenes(args.out_dir)

    sizes = {path.name: path.stat().st_size for path in sorted(args.out_dir.glob("*.json"))}
    print(f"Captured {len(sizes)} artifacts to {args.out_dir}:")
    for name, size in sizes.items():
        print(f"  {name}: {size:,} bytes")
    print(
        "\nThese are byte sizes, not token counts. Tokenize these files and an "
        "equivalently captured bx-referee transcript with one Anthropic count_tokens "
        "pass to produce the actual Phase 1 measurement verdict."
    )


if __name__ == "__main__":
    asyncio.run(main())
