"""The FastMCP server: the four core tools plus session lifecycle.

Phase 0 proved the wire with one raw-`dict` tool over a throwaway fixture. Phase 1
retypes `execute` over the real `AnyCommand` union (the FastMCP spike confirmed a
clean discriminated input schema and a working round-trip), adds the scoped `observe`
projection, `prose`, `list_commands`/`list_adventures`, and the real session
lifecycle with durable saves — see [`SessionStore`][osrlib_referee_mcp.store.SessionStore].

Session mutation (`execute` and the three lifecycle tools) runs under one
`asyncio.Lock`: `GameSession` is not thread-safe by contract, and a single stdio
server now has a real multi-tool lifecycle where commands could otherwise interleave.
"""

import asyncio

from mcp.server.fastmcp import FastMCP
from osrlib.crawl.commands import AnyCommand

from osrlib_referee_mcp.catalog import list_command_types
from osrlib_referee_mcp.projection import build_observation
from osrlib_referee_mcp.registry import list_adventure_entries
from osrlib_referee_mcp.store import SessionStore

mcp = FastMCP("osrlib-referee")
_store = SessionStore()
_lock = asyncio.Lock()


@mcp.tool()
async def session_new(
    adventure_id: str,
    seed: int | None = None,
    party_document: dict[str, object] | None = None,
    save_id: str | None = None,
) -> dict[str, object]:
    """Start a fresh session on an adventure and persist it immediately.

    Args:
        adventure_id: A native adventure id or a discovered bundle id
            (`list_adventures` lists the known ids).
        seed: The master seed. Omit for a fresh, unpredictable seed; pin it for a
            reproducible session.
        party_document: A `party_to_document`-shaped document. Omit to use the
            frozen pregen roster (a fighter, a cleric, and a thief).
        save_id: The save slot stem this session persists under. Omit to default to
            the `adventure_id` — a globally-unique slot so coexisting adventures never
            collide; pass a distinct name to keep more than one save per adventure.

    Returns:
        `{schema_version, engine_version, save_id}` — never the seed.
    """
    async with _lock:
        return _store.new(adventure_id, seed=seed, party_document=party_document, save_id=save_id)


@mcp.tool()
async def session_load(save_id: str) -> dict[str, object]:
    """Load a save by id and make it the active session.

    Args:
        save_id: The save slot stem to load (as returned by `session_new` or a prior
            `session_save`).

    Returns:
        `{schema_version, engine_version, save_id}`.
    """
    async with _lock:
        return _store.load(save_id)


@mcp.tool()
async def session_save() -> dict[str, object]:
    """Persist the active session to its current save slot.

    Returns:
        `{schema_version, engine_version, save_id}`.
    """
    async with _lock:
        return _store.save()


@mcp.tool()
async def execute(command: AnyCommand) -> dict[str, object]:
    """Execute one command against the active session.

    Args:
        command: A member of the `AnyCommand` discriminated union, keyed on
            `command_type`.

    Returns:
        `{accepted, rejections, events}`. A rejected command is in-fiction feedback,
        not an error: it costs no time and touches no state. Each rejection and
        event is dumped individually (never through the `CommandResult` container),
        since `events` is base-`Event`-typed and a container dump would drop every
        subclass field the narration reads.
    """
    async with _lock:
        result = _store.session.execute(command)
    return {
        "accepted": result.accepted,
        "rejections": [rejection.model_dump(mode="json") for rejection in result.rejections],
        "events": [event.model_dump(mode="json") for event in result.events],
    }


@mcp.tool()
def observe(scope: str = "current") -> dict[str, object]:
    """Read the scoped referee projection of the active session's current state.

    Args:
        scope: Only `"current"` is implemented in Phase 1.

    Returns:
        The scoped projection — see
        [`build_observation`][osrlib_referee_mcp.projection.build_observation].
        Right after `session_new`/`session_load`, this includes a bounded event-log
        tail to recap; on every later call in the same turn cycle, it does not —
        events ride `execute`'s own envelope instead.
    """
    if scope != "current":
        raise ValueError(f"unsupported observe scope {scope!r}; only 'current' is implemented")
    cold = _store.needs_recap
    observation = build_observation(_store.session, cold=cold)
    _store.needs_recap = False
    return observation


@mcp.tool()
def prose(area_id: str) -> dict[str, object]:
    """Read the authored prose sidecar for an area.

    Args:
        area_id: An `AreaSpec.id` (or `"town"`) from `observe`'s `area.id` field.

    Returns:
        `{found: True, area_id, read_aloud, referee_notes}`, or
        `{found: False, area_id}` for an unknown id — a content bug the skill should
        surface, not a tool error.
    """
    entry = _store.active_prose.get(area_id)
    if entry is None:
        return {"found": False, "area_id": area_id}
    return {"found": True, "area_id": area_id, **entry}


@mcp.tool()
def list_commands(mode: str | None = None) -> dict[str, list[str]]:
    """List legal `command_type` values, split into player-intent and authorial.

    The runtime, mode-scoped menu the standing `AnyCommand` union schema cannot
    provide on its own (mode-gating is a runtime precheck inside `execute`, not a
    schema pruner).

    Args:
        mode: A `SessionMode` value to gate player-intent commands by. Omit to list
            every player-intent command regardless of mode.

    Returns:
        `{"player_intent": [...], "authorial": [...]}`. The 11 authorial commands
        are legal in every mode and are not filtered by `mode`.
    """
    return list_command_types(mode)


@mcp.tool()
def list_adventures() -> list[dict[str, str]]:
    """List the adventures this server can start — native builders and on-disk bundles.

    Returns:
        One `{adventure_id, name, description}` entry per resolvable adventure: the
        native registry first, then compiled bundles discovered in the in-repo
        `adventures/` directory and the game directory's `bundles/`.
    """
    return list_adventure_entries([_store.adventures_dir, _store.game_bundles_dir])


def main() -> None:
    """Run the server over stdio."""
    mcp.run()
