"""The mode-scoped command menu: the runtime pruning the standing union schema can't do.

The `AnyCommand` union schema is advertised in full every turn regardless of mode —
mode-gating is a runtime precheck inside `GameSession.execute`, not a schema pruner.
`list_command_types(mode)` gives the model the menu the schema itself cannot: which
`command_type`s are actually legal right now, split into player-intent commands (each
scoped to a phase of play) and the authorial commands the referee reaches for at any
point in a live session — `GrantItem`, `GrantCoins`, `AwardXP`, `SetFlag`,
`SpawnMonsters`, `SpawnNpcParty`, `SetDoorState`, `PlaceParty`, `AdvanceTime`,
`IdentifyItem`, `RollDice`, and the quest, trigger, journal, and note bookkeeping —
which would otherwise flood every list.

osrlib marks no command as authorial, so the split is inferred: a command legal in
every *non-terminal* mode is one no phase of play gates, which is exactly what makes
it authorial. The narrower test — legal in literally every mode — no longer works,
because `SpawnMonsters`, `SpawnNpcParty`, and `PlaceParty` are barred from a session
that has already ended (engine 1.5.0), and they are referee commands all the same.
"""

from osrlib.crawl.commands import ALL_COMMAND_CLASSES, SessionMode

_LIVE_MODES = frozenset(mode for mode in SessionMode if not mode.terminal)


def _command_type(command_class: type) -> str:
    return command_class.model_fields["command_type"].default


def list_command_types(mode: SessionMode | str | None = None) -> dict[str, list[str]]:
    """List legal `command_type` values, split into player-intent and authorial.

    Args:
        mode: The session mode to gate both lists by. `None` lists every command
            regardless of mode.

    Returns:
        `{"player_intent": [...], "authorial": [...]}`, each sorted for stable output.
        Both lists are filtered by `mode`, so a terminal session drops the authorial
        commands that would resume play: `SpawnMonsters` and `SpawnNpcParty` in
        `game_over` and `victory`, and `PlaceParty` in `victory`.
    """
    session_mode = SessionMode(mode) if mode is not None else None
    player_intent = []
    authorial = []
    for command_class in ALL_COMMAND_CLASSES:
        if session_mode is not None and session_mode not in command_class.allowed_modes:
            continue
        bucket = authorial if _LIVE_MODES <= command_class.allowed_modes else player_intent
        bucket.append(_command_type(command_class))
    return {"player_intent": sorted(player_intent), "authorial": sorted(authorial)}
