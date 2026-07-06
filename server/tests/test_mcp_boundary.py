import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from osrlib_referee_mcp.server import mcp


@pytest.mark.anyio
async def test_execute_round_trips_through_the_mcp_boundary():
    async with create_connected_server_and_client_session(mcp._mcp_server, raise_exceptions=True) as client:
        result = await client.call_tool(
            "execute",
            {"command": {"command_type": "set_flag", "key": "ping", "value": True}},
        )

    assert not result.isError
    assert result.structuredContent["accepted"] is True
    assert result.structuredContent["rejections"] == []
    assert result.structuredContent["events"][0]["event_type"] == "flag_set"
    assert result.structuredContent["events"][0]["key"] == "ping"
