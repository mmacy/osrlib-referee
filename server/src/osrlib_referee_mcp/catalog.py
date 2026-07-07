"""The mode-scoped command menu: the runtime pruning the standing union schema can't do.

The `AnyCommand` union schema is advertised in full every turn regardless of mode —
mode-gating is a runtime precheck inside `GameSession.execute`, not a schema pruner.
`list_command_types(mode)` gives the model the menu the schema itself cannot: which
`command_type`s are actually legal right now, split into player-intent commands (mode-
gated) and the 11 authorial commands (legal in every mode — `GrantItem`, `GrantCoins`,
`AwardXP`, `SetFlag`, `SpawnMonsters`, `SpawnNpcParty`, `SetDoorState`, `PlaceParty`,
`AdvanceTime`, `IdentifyItem`, `RollDice`), which would otherwise flood every list.
"""

from osrlib.crawl.commands import ALL_COMMAND_CLASSES, SessionMode

_ALL_MODES = frozenset(SessionMode)


def _command_type(command_class: type) -> str:
    return command_class.model_fields["command_type"].default


def list_command_types(mode: SessionMode | str | None = None) -> dict[str, list[str]]:
    """List legal `command_type` values, split into player-intent and authorial.

    Args:
        mode: The session mode to gate player-intent commands by. `None` lists every
            player-intent command regardless of mode.

    Returns:
        `{"player_intent": [...], "authorial": [...]}`, each sorted for stable output.
        `authorial` is legal in every mode and is not filtered by `mode`.
    """
    session_mode = SessionMode(mode) if mode is not None else None
    player_intent = []
    authorial = []
    for command_class in ALL_COMMAND_CLASSES:
        if command_class.allowed_modes == _ALL_MODES:
            authorial.append(_command_type(command_class))
        elif session_mode is None or session_mode in command_class.allowed_modes:
            player_intent.append(_command_type(command_class))
    return {"player_intent": sorted(player_intent), "authorial": sorted(authorial)}
