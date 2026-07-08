import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from osrlib_referee_mcp import server as server_module
from osrlib_referee_mcp.store import SessionStore

FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURE_BUNDLE_ID = "fixture_crypt"


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    """Give every test its own session store, game directory, and bundle roots.

    `server`'s tool functions look up `_store` as a module global, so swapping the
    module attribute isolates every test from the others (and from the user's real
    `~/osr-games` and the in-repo `adventures/`) without touching the tool functions.
    The two bundle roots start empty; a test drops a bundle into one via `install_bundle`.
    """
    store = SessionStore()
    store.game_root = tmp_path
    store.adventures_dir = tmp_path / "repo_adventures"
    store.game_bundles_dir = tmp_path / "game_bundles"
    monkeypatch.setattr(server_module, "_store", store)
    return store


@pytest.fixture
def install_bundle() -> Callable[..., Path]:
    """Copy the committed fixture bundle into a discovery root, returning its path."""

    def _install(dest_root: Path, bundle_id: str = FIXTURE_BUNDLE_ID) -> Path:
        dest = dest_root / bundle_id
        shutil.copytree(FIXTURES_DIR / "bundles" / bundle_id, dest)
        return dest

    return _install
