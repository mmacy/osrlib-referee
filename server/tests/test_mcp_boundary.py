import pytest
from mcp.shared.memory import create_connected_server_and_client_session

from osrlib_referee_mcp.content import ADVENTURE_ID, DUNGEON_ID, SESSION_SEED
from osrlib_referee_mcp.server import mcp


@pytest.mark.anyio
async def test_lifecycle_and_execute_round_trip_through_the_mcp_boundary():
    async with create_connected_server_and_client_session(mcp._mcp_server, raise_exceptions=True) as client:
        new_result = await client.call_tool(
            "session_new", {"adventure_id": ADVENTURE_ID, "seed": SESSION_SEED, "save_id": "mcp-boundary"}
        )
        assert not new_result.isError
        assert new_result.structuredContent["save_id"] == "mcp-boundary"

        exec_result = await client.call_tool(
            "execute",
            {"command": {"command_type": "set_flag", "key": "ping", "value": True}},
        )
        assert not exec_result.isError
        assert exec_result.structuredContent["accepted"] is True
        assert exec_result.structuredContent["rejections"] == []
        assert exec_result.structuredContent["events"][0]["event_type"] == "flag_set"
        assert exec_result.structuredContent["events"][0]["key"] == "ping"

        observe_result = await client.call_tool("observe", {})
        assert not observe_result.isError
        assert observe_result.structuredContent["mode"] == "town"
        assert observe_result.structuredContent["flags"] == {"ping": True}
        hero_id = observe_result.structuredContent["party"][0]["id"]

        enter_result = await client.call_tool(
            "execute", {"command": {"command_type": "enter_dungeon", "dungeon_id": DUNGEON_ID}}
        )
        assert not enter_result.isError

        prose_result = await client.call_tool("prose", {"area_id": "entrance"})
        assert not prose_result.isError
        assert prose_result.structuredContent["found"] is True
        assert "read_aloud" in prose_result.structuredContent

        missing_prose = await client.call_tool("prose", {"area_id": "nonexistent"})
        assert not missing_prose.isError
        assert missing_prose.structuredContent["found"] is False

        commands_result = await client.call_tool("list_commands", {"mode": "exploring"})
        assert not commands_result.isError
        assert "move_party" in commands_result.structuredContent["player_intent"]

        adventures_result = await client.call_tool("list_adventures", {})
        assert not adventures_result.isError

        sheet_result = await client.call_tool("character_sheet", {"character_id": hero_id})
        assert not sheet_result.isError
        assert sheet_result.structuredContent["id"] == hero_id
        assert "thac0" in sheet_result.structuredContent
        assert "saves" in sheet_result.structuredContent

        audit_result = await client.call_tool("session_audit", {"limit": 10})
        assert not audit_result.isError
        assert "events" in audit_result.structuredContent
        assert "command_count" in audit_result.structuredContent

        save_result = await client.call_tool("session_save", {})
        assert not save_result.isError
        assert save_result.structuredContent["save_id"] == "mcp-boundary"

        load_result = await client.call_tool("session_load", {"save_id": "mcp-boundary"})
        assert not load_result.isError
        assert load_result.structuredContent["save_id"] == "mcp-boundary"


@pytest.mark.anyio
async def test_unknown_command_type_fails_union_validation_as_a_tool_error():
    """Retyping `execute` over the real `AnyCommand` union means an unknown
    `command_type` fails discriminated-union validation at the FastMCP/pydantic
    boundary before the handler ever runs — a tool error, not a reachable
    in-handler result field (Phase 0's `unknown_command_type` result branch is
    gone)."""
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        await client.call_tool("session_new", {"adventure_id": ADVENTURE_ID, "seed": SESSION_SEED})

        result = await client.call_tool("execute", {"command": {"command_type": "not_a_real_command"}})

        assert result.isError


@pytest.mark.anyio
async def test_unknown_save_id_is_a_tool_error_at_the_boundary():
    async with create_connected_server_and_client_session(mcp._mcp_server) as client:
        result = await client.call_tool("session_load", {"save_id": "does-not-exist"})

        assert result.isError
