"""The user's game directory: where saves live, never the plugin cache.

Resolved from the `OSRLIB_REFEREE_GAME_ROOT` environment variable, defaulting to
`~/osr-games` — the convention `bx-referee` already establishes
(`~/repos/osr-plugins/CLAUDE.md`'s "game directory" section): `<game-root>/adventures/
<name>/...`. A plugin-bundled stdio server starts and stops with the Claude Code
session, so saves must survive on disk between sessions.
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


def save_path(game_root: Path, adventure_id: str, save_id: str) -> Path:
    """The on-disk path for one save.

    Args:
        game_root: The resolved game-root directory.
        adventure_id: The server's adventure registry key (the `<name>` directory).
        save_id: The server-chosen save slot stem.

    Returns:
        `<game-root>/adventures/<adventure_id>/<save_id>.json`.
    """
    return game_root / "adventures" / adventure_id / f"{save_id}.json"


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
    adventures_dir = game_root / "adventures"
    matches = sorted(adventures_dir.glob(f"*/{save_id}.json")) if adventures_dir.is_dir() else []
    if not matches:
        raise ValueError(f"no save found for save_id {save_id!r} under {adventures_dir}")
    if len(matches) > 1:
        raise ValueError(f"save_id {save_id!r} is ambiguous across adventures: {[str(m) for m in matches]}")
    return matches[0]
