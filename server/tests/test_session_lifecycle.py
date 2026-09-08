"""Save enumeration, resume with a cold recap, and the optional journal.

The `session` skill's lifecycle: `gametool saves` enumerates the resume menu,
`session_load` re-activates a save, the first `observe` after a load comes back "cold"
with an event tail to recap from, and a human-readable journal round-trips as *text* —
derived and disposable, never reloaded as game state.
"""

import json

import pytest

from osrlib_referee_mcp import gametool
from osrlib_referee_mcp.content import ADVENTURE_ID
from osrlib_referee_mcp.server import execute, observe, session_load, session_new, session_save


@pytest.mark.anyio
async def test_gametool_saves_enumerates_the_resume_menu(_fresh_store):
    store = _fresh_store
    await session_new(ADVENTURE_ID, seed=1, save_id="alpha")
    await session_new(ADVENTURE_ID, seed=2, save_id="beta")

    result = gametool.saves_result(store.game_root)

    save_ids = {entry["save_id"] for entry in result["saves"]}
    assert save_ids == {"alpha", "beta"}
    for entry in result["saves"]:
        assert entry["adventure_id"] == ADVENTURE_ID
        # The version stamps come from the on-disk save-game envelope.
        assert entry["schema_version"] is not None
        assert entry["engine_version"] is not None


@pytest.mark.anyio
async def test_saves_result_is_empty_before_any_save(_fresh_store):
    assert gametool.saves_result(_fresh_store.game_root)["saves"] == []


@pytest.mark.anyio
async def test_load_reactivates_and_observe_returns_a_cold_recap_tail(_fresh_store):
    from osrlib.crawl.commands import SetFlag

    await session_new(ADVENTURE_ID, seed=1, save_id="recap")
    await execute(SetFlag(key="lever", value=True))
    # The warm observe consumes the cold flag; the save embeds the event log.
    observe()
    await session_save()

    await session_load("recap")
    recap = observe()

    # Right after a load the projection is cold: it carries a bounded event tail to recap.
    assert "events" in recap
    assert recap["flags"] == {"lever": True}
    # A second observe in the same cycle is warm — events ride execute's envelope instead.
    assert "events" not in observe()


@pytest.mark.anyio
async def test_optional_journal_round_trips_as_text_and_is_not_reloaded_as_state(_fresh_store):
    store = _fresh_store
    new = await session_new(ADVENTURE_ID, seed=1, save_id="journaled")
    # The journal lives beside the save as a .md sibling — a convenience, never canonical.
    save_dir = store.game_root / "adventures" / ADVENTURE_ID
    journal = save_dir / f"{new['save_id']}.journal.md"
    journal.write_text("# Session log\n\nThe party delved and returned.\n")

    # It round-trips as prose…
    assert "delved and returned" in journal.read_text()
    # …and the save-game document — the single source of truth — is untouched by it.
    save_document = json.loads((save_dir / f"{new['save_id']}.json").read_text())
    assert save_document["kind"] == "save"
    assert "journal" not in save_document
