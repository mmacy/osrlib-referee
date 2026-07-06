from osrlib_referee_mcp.server import execute


def test_set_flag_is_accepted_and_emits_flag_set_event():
    result = execute({"command_type": "set_flag", "key": "ping", "value": True})

    assert result["accepted"] is True
    assert result["rejections"] == []
    assert len(result["events"]) == 1
    assert result["events"][0]["event_type"] == "flag_set"
    assert result["events"][0]["key"] == "ping"
    assert result["events"][0]["value"] is True


def test_move_party_in_town_is_rejected_wrong_mode():
    result = execute({"command_type": "move_party", "direction": "north"})

    assert result["accepted"] is False
    assert result["events"] == []
    assert result["rejections"][0]["code"] == "session.command.wrong_mode"


def test_unknown_command_type_is_a_structured_result_not_an_error():
    result = execute({"command_type": "not_a_real_command"})

    assert result == {
        "accepted": False,
        "error": "unknown_command_type",
        "command_type": "not_a_real_command",
    }
