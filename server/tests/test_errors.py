"""The `OsrlibError` -> tool-error map: rejections stay results, `OsrlibError`s
become errors.

FastMCP's own boundary (`mcp/server/lowlevel/server.py`) turns any exception raised
inside a tool function into `CallToolResult(isError=True, content=[str(exception)])`
— confirmed by reading the installed SDK. So this server's whole error-map
contribution is: let `OsrlibError`s and this store's own `ValueError`s propagate
uncaught (they already carry clean, human-readable messages), and never raise for an
in-fiction rejection. This file pins that contract at the tool-function layer;
`test_mcp_boundary.py` pins it at the real protocol boundary.
"""

import pytest
from osrlib.crawl.commands import MoveParty
from osrlib.crawl.dungeon import Direction
from osrlib.errors import ContentValidationError

from osrlib_referee_mcp.content import ADVENTURE_ID, SESSION_SEED
from osrlib_referee_mcp.server import execute, session_load, session_new


@pytest.mark.anyio
async def test_an_in_fiction_rejection_is_a_normal_result_not_an_exception():
    await session_new(ADVENTURE_ID, seed=SESSION_SEED)

    result = await execute(MoveParty(direction=Direction.NORTH))  # still in town: wrong mode

    assert result["accepted"] is False
    assert result["events"] == []
    assert result["rejections"][0]["code"] == "session.command.wrong_mode"


@pytest.mark.anyio
async def test_unknown_save_id_raises_a_clean_value_error():
    with pytest.raises(ValueError, match="no save found"):
        await session_load("does-not-exist")


@pytest.mark.anyio
async def test_unknown_adventure_id_raises_a_clean_value_error():
    with pytest.raises(ValueError, match="unknown adventure_id"):
        await session_new("not-a-real-adventure")


@pytest.mark.anyio
async def test_malformed_party_document_raises_content_validation_error():
    with pytest.raises(ContentValidationError):
        await session_new(ADVENTURE_ID, party_document={"kind": "party", "schema_version": 1, "payload": {}})
