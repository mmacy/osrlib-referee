"""The user's game directory: where saves and private bundles live, never the cache.

Resolved from the `OSRLIB_REFEREE_GAME_ROOT` environment variable, defaulting to
`~/osr-games` — the convention `bx-referee` already establishes
(`~/repos/osr-plugins/CLAUDE.md`'s "game directory" section): `<game-root>/adventures/
<name>/...`. A plugin-bundled stdio server starts and stops with the Claude Code
session, so saves must survive on disk between sessions.

Compiled bundles live in two places (see [`osrlib_referee_mcp.registry`]): openly-
licensed or original bundles committed to the in-repo `adventures/` directory, and
private compiled bundles written to `<game-root>/bundles/`. The in-repo directory is
resolved from `OSRLIB_REFEREE_ADVENTURES_DIR` (the plugin sets it to
`${CLAUDE_PLUGIN_ROOT}/adventures`), falling back to a path derived from this
package's location for the local `uv run` / test launch where that variable is unset.
"""

import os
from pathlib import Path

DEFAULT_GAME_ROOT = "~/osr-games"


def resolve_game_root() -> Path:
    """Resolve the game-root directory from the environment, or the default.

    Returns:
        The expanded, absolute game-root path. Not guaranteed to exist yet.
    """
    raw = os.environ.get("OSRLIB_REFEREE_GAME_ROOT", DEFAULT_GAME_ROOT)
    return Path(raw).expanduser()


def repo_adventures_dir() -> Path:
    """Resolve the in-repo `adventures/` directory holding open/original bundles.

    Prefers `OSRLIB_REFEREE_ADVENTURES_DIR` (the plugin launch sets it to
    `${CLAUDE_PLUGIN_ROOT}/adventures`). Absent it — the local `uv run` and test
    launches — falls back to `<repo-root>/adventures`, derived from this package's
    source location (`server/src/osrlib_referee_mcp/gamedir.py` → repo root is four
    parents up). The fallback holds under the source-tree install the plugin actually
    uses (`uv run --project server`).

    An env value that still contains an unexpanded `${...}` is **ignored** in favour of
    the fallback: `Path.expanduser` does not expand `${VAR}`, so if the launcher failed
    to substitute `${CLAUDE_PLUGIN_ROOT}` the literal string would otherwise shadow the
    working fallback and make discovery find nothing. Guarding on `${` means a failed
    substitution degrades to the fallback rather than breaking silently.

    Returns:
        The in-repo `adventures/` path. Not guaranteed to exist yet.
    """
    raw = os.environ.get("OSRLIB_REFEREE_ADVENTURES_DIR")
    if raw and "${" not in raw:
        return Path(raw).expanduser()
    return Path(__file__).resolve().parents[3] / "adventures"


def game_bundles_dir(game_root: Path) -> Path:
    """The game-directory subtree holding private compiled bundles.

    Kept separate from the saves subtree (`<game-root>/adventures/<adventure_id>/`)
    so a bundle directory can never be mistaken for a save directory.

    Args:
        game_root: The resolved game-root directory.

    Returns:
        `<game-root>/bundles`. Not guaranteed to exist yet.
    """
    return game_root / "bundles"


def parties_dir(game_root: Path) -> Path:
    """The game-directory subtree holding built party documents.

    Kept separate from the saves and bundles subtrees: a party is a pre-session build
    artifact (`chargen party`), resolved by id when `session_new(party_ref=…)` starts a
    session, and never confused with a save.

    Args:
        game_root: The resolved game-root directory.

    Returns:
        `<game-root>/parties`. Not guaranteed to exist yet.
    """
    return game_root / "parties"


def party_path(game_root: Path, party_id: str) -> Path:
    """The on-disk path for one built party document.

    Args:
        game_root: The resolved game-root directory.
        party_id: The party id stem.

    Returns:
        `<game-root>/parties/<party_id>.json`.
    """
    return parties_dir(game_root) / f"{party_id}.json"


def find_party(game_root: Path, party_id: str) -> Path:
    """Locate a built party document by id, for `session_new(party_ref=…)`.

    Args:
        game_root: The resolved game-root directory.
        party_id: The party id stem.

    Returns:
        The matching path.

    Raises:
        ValueError: If no party document exists for `party_id`.
    """
    path = party_path(game_root, party_id)
    if not path.is_file():
        raise ValueError(f"no party found for party_ref {party_id!r} under {parties_dir(game_root)}")
    return path


def saves_dir(game_root: Path) -> Path:
    """The game-directory subtree holding saved games, one directory per adventure.

    Args:
        game_root: The resolved game-root directory.

    Returns:
        `<game-root>/adventures`. Not guaranteed to exist yet.
    """
    return game_root / "adventures"


def save_path(game_root: Path, adventure_id: str, save_id: str) -> Path:
    """The on-disk path for one save.

    Args:
        game_root: The resolved game-root directory.
        adventure_id: The server's adventure registry key (the `<name>` directory).
        save_id: The server-chosen save slot stem.

    Returns:
        `<game-root>/adventures/<adventure_id>/<save_id>.json`.
    """
    return saves_dir(game_root) / adventure_id / f"{save_id}.json"


def find_save(game_root: Path, save_id: str) -> Path:
    """Locate a save by id alone, without knowing which adventure it belongs to.

    A save document embeds its own `adventure` spec (`load_game` needs no external
    adventure lookup), so `session_load` takes only a `save_id`. This scans every
    adventure directory for a matching file.

    Args:
        game_root: The resolved game-root directory.
        save_id: The save slot stem to find.

    Returns:
        The matching path.

    Raises:
        ValueError: If no save or more than one save matches `save_id`.
    """
    adventures_dir = saves_dir(game_root)
    matches = sorted(adventures_dir.glob(f"*/{save_id}.json")) if adventures_dir.is_dir() else []
    if not matches:
        raise ValueError(f"no save found for save_id {save_id!r} under {adventures_dir}")
    if len(matches) > 1:
        raise ValueError(f"save_id {save_id!r} is ambiguous across adventures: {[str(m) for m in matches]}")
    return matches[0]
