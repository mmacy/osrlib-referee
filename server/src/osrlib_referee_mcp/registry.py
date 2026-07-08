"""Adventure discovery: the union of native Python builders and on-disk bundles.

Phase 1 served one native adventure from a module-global registry. Phase 2 unions that
with compiled bundles discovered on disk — openly-licensed or original bundles in the
in-repo `adventures/` directory, and private compiled bundles in the game directory's
`bundles/`. `session_new`, `session_load`, and `list_adventures` resolve either kind of
adventure through this module.

A native adventure always wins a `bundle_id` collision (native ids are the fixed core;
a dropped-in bundle can never shadow one), and among bundles the first root scanned wins
(the in-repo directory before the game directory). A bundle whose manifest is unreadable
is silently skipped during discovery so one bad bundle never breaks the whole list; a
`session_new` that names it directly still raises, through
[`load_bundle`][osrlib_referee_mcp.bundle.load_bundle].
"""

from dataclasses import dataclass
from pathlib import Path

from osrlib.crawl.adventure import Adventure
from osrlib.errors import ContentValidationError

from osrlib_referee_mcp.bundle import load_bundle, read_manifest
from osrlib_referee_mcp.content import NATIVE_ADVENTURES


@dataclass(frozen=True)
class ResolvedAdventure:
    """A resolved adventure ready to start a session: the model plus its prose sidecar."""

    adventure_id: str
    name: str
    description: str
    adventure: Adventure
    prose: dict[str, dict[str, str]]


def _bundle_subdirs(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(path for path in root.iterdir() if path.is_dir())


def discover_bundle_dirs(roots: list[Path]) -> dict[str, Path]:
    """Map each discovered `bundle_id` to its directory, scanning `roots` in order.

    Args:
        roots: The bundle roots to scan, in precedence order (earlier wins a collision).

    Returns:
        `{bundle_id: directory}` for every bundle whose manifest reads and whose id
        neither collides with a native adventure nor an earlier-scanned bundle.
    """
    found: dict[str, Path] = {}
    for root in roots:
        for subdir in _bundle_subdirs(root):
            try:
                manifest = read_manifest(subdir)
            except ContentValidationError:
                continue
            bundle_id = manifest.get("bundle_id")
            if not isinstance(bundle_id, str) or not bundle_id:
                continue
            if bundle_id in NATIVE_ADVENTURES or bundle_id in found:
                continue
            found[bundle_id] = subdir
    return found


def resolve_adventure(adventure_id: str, roots: list[Path]) -> ResolvedAdventure:
    """Resolve an `adventure_id` to a startable adventure — native builder or bundle.

    Args:
        adventure_id: A native adventure id or a discovered `bundle_id`.
        roots: The bundle roots to search when the id is not native.

    Returns:
        The resolved adventure.

    Raises:
        ValueError: The id resolves to neither a native adventure nor a bundle.
        ContentValidationError: The id names a bundle whose spec fails to load.
    """
    native = NATIVE_ADVENTURES.get(adventure_id)
    if native is not None:
        adventure = native.build()
        return ResolvedAdventure(adventure_id, adventure.name, adventure.description, adventure, native.prose)
    bundle_dirs = discover_bundle_dirs(roots)
    bundle_dir = bundle_dirs.get(adventure_id)
    if bundle_dir is None:
        known = sorted(list(NATIVE_ADVENTURES) + list(bundle_dirs))
        raise ValueError(f"unknown adventure_id {adventure_id!r}; known: {known}")
    loaded = load_bundle(bundle_dir)
    return ResolvedAdventure(loaded.bundle_id, loaded.name, loaded.description, loaded.adventure, loaded.prose)


def resolve_prose(adventure_id: str, roots: list[Path]) -> dict[str, dict[str, str]]:
    """Resolve an adventure's prose sidecar alone — best-effort, for `session_load`.

    A save embeds its adventure spec but not the out-of-band prose, so a loaded session
    re-fetches prose by `adventure_id`. If the source is gone or unreadable, prose is
    empty (the save still plays; only authored prose is missing) rather than an error.

    Args:
        adventure_id: The adventure id recorded in the save's directory name.
        roots: The bundle roots to search when the id is not native.

    Returns:
        The prose map, or `{}` if the adventure source can no longer be resolved.
    """
    native = NATIVE_ADVENTURES.get(adventure_id)
    if native is not None:
        return native.prose
    bundle_dir = discover_bundle_dirs(roots).get(adventure_id)
    if bundle_dir is None:
        return {}
    try:
        return load_bundle(bundle_dir).prose
    except ContentValidationError:
        return {}


def list_adventure_entries(roots: list[Path]) -> list[dict[str, str]]:
    """List every discoverable adventure — native first, then on-disk bundles.

    Reads only bundle manifests (never reconstructing every `Adventure`), so a single
    malformed bundle is skipped rather than breaking the list.

    Args:
        roots: The bundle roots to scan.

    Returns:
        One `{adventure_id, name, description}` entry per resolvable adventure.
    """
    entries: list[dict[str, str]] = []
    for adventure_id, native in NATIVE_ADVENTURES.items():
        adventure = native.build()
        entries.append({"adventure_id": adventure_id, "name": adventure.name, "description": adventure.description})
    for bundle_id, bundle_dir in discover_bundle_dirs(roots).items():
        try:
            manifest = read_manifest(bundle_dir)
        except ContentValidationError:
            continue
        name = manifest.get("name")
        description = manifest.get("description")
        entries.append(
            {
                "adventure_id": bundle_id,
                "name": name if isinstance(name, str) else bundle_id,
                "description": description if isinstance(description, str) else "",
            }
        )
    return entries
