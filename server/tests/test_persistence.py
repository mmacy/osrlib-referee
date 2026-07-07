"""Save round-trip: byte-identity, and the adjudication RNG stream surviving reload."""

import json

import pytest
from osrlib.crawl.commands import RollDice
from osrlib.persistence import load_game, save_game

from osrlib_referee_mcp.content import ADVENTURE_ID, SESSION_SEED
from osrlib_referee_mcp.server import execute, session_load, session_new, session_save


@pytest.mark.anyio
async def test_save_load_save_is_byte_identical(_fresh_store):
    await session_new(ADVENTURE_ID, seed=SESSION_SEED, save_id="round-trip")
    session = _fresh_store.session

    document = save_game(session)
    reloaded = load_game(document)
    re_saved = save_game(reloaded)

    assert re_saved == document


@pytest.mark.anyio
async def test_adjudication_stream_survives_a_save_reload(_fresh_store):
    await session_new(ADVENTURE_ID, seed=SESSION_SEED, save_id="rng-continuity")
    session = _fresh_store.session

    first_roll = session.execute(RollDice(expression="3d6"))
    document = save_game(session)
    second_roll_original = session.execute(RollDice(expression="3d6"))

    reloaded = load_game(document)
    second_roll_reloaded = reloaded.execute(RollDice(expression="3d6"))

    assert first_roll.accepted and second_roll_original.accepted and second_roll_reloaded.accepted
    assert second_roll_reloaded.events[0].total == second_roll_original.events[0].total


@pytest.mark.anyio
async def test_session_save_then_session_load_resumes_the_same_state(_fresh_store):
    await session_new(ADVENTURE_ID, seed=SESSION_SEED, save_id="resume")
    await execute(RollDice(expression="1d20"))
    saved = await session_save()

    loaded = await session_load("resume")

    assert loaded["save_id"] == "resume"
    assert loaded["schema_version"] == saved["schema_version"]
    assert loaded["engine_version"] == saved["engine_version"]


def test_malformed_save_document_raises_content_validation_error(_fresh_store, tmp_path):
    from osrlib.errors import ContentValidationError

    adventures_dir = _fresh_store.game_root / "adventures" / "bogus"
    adventures_dir.mkdir(parents=True)
    (adventures_dir / "broken.json").write_text(json.dumps({"not": "a save document"}))

    with pytest.raises(ContentValidationError):
        load_game(json.loads((adventures_dir / "broken.json").read_text()))
