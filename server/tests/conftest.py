import pytest

from osrlib_referee_mcp import server as server_module
from osrlib_referee_mcp.store import SessionStore


@pytest.fixture(autouse=True)
def _fresh_store(tmp_path, monkeypatch):
    """Give every test its own session store and game directory.

    `server`'s tool functions look up `_store` as a module global, so swapping the
    module attribute isolates every test from the others (and from the user's real
    `~/osr-games`) without touching the tool functions themselves.
    """
    store = SessionStore()
    store.game_root = tmp_path
    monkeypatch.setattr(server_module, "_store", store)
    return store
