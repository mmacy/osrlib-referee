"""`session_audit(...)`: the live roll/command trajectory — a superset over `bx-referee`.

`bx-referee` has no roll-log, audit trail, or roll-transparency mechanism — its
constitution actively *hides* target numbers and resolves rolls silently. osrlib-referee
can do what `bx-referee` structurally cannot: the engine keeps a full, ordered event log
and command log in the session (the save document embeds both), so every roll is real,
recorded, and replayable. This read surfaces that trajectory — dice rolls
(`DiceRolledEvent`), attack and save resolutions, XP awards (each `XpAwardedEvent`
carrying the `level_after` that signals an advance — there is no level-up event to
surface) — from the **live** session's event log, since the on-disk save may lag the
running session.

It reads the live log, so it is a play-server tool, not a CLI. A `visibility` filter
draws the constitution-Article-II boundary mechanically: `"player"` returns only
player-visibility events (a character's own attacks, saves, XP), withholding the
referee-only rolls (morale, reaction, the referee's freeform `RollDice` adjudications)
until the fiction reveals them; the full referee trajectory is available on request at a
scene boundary, in town, or at session end. A `kinds` filter and a tail `limit` keep the
payload bounded.
"""

from osrlib.crawl.session import GameSession

DEFAULT_AUDIT_LIMIT = 50


def _as_dict(entry) -> dict:
    return entry if isinstance(entry, dict) else entry.model_dump(mode="json")


def build_audit(
    session: GameSession,
    *,
    kinds: list[str] | None = None,
    visibility: str | None = None,
    limit: int = DEFAULT_AUDIT_LIMIT,
) -> dict:
    """Build the roll/command trajectory from the live session's event log.

    Args:
        session: The running session (never the on-disk save, which may lag).
        kinds: Optionally restrict to these `event_type` values (e.g.
            `["dice_rolled", "attack_rolled", "xp_awarded"]`). Omit for every kind.
        visibility: `"player"` for player-visibility events only (the mid-play,
            player-facing view that leaks no undiscovered secret), `"referee"` for the
            referee-only rolls, or omit for both. The constitution-Article-II boundary,
            drawn mechanically off each event's own `visibility`.
        limit: The maximum number of matching events to return, taken as the most recent
            tail so the payload stays bounded. `0` returns none; a negative value is the
            unbounded escape (every match).

    Returns:
        `{events, total_matched, returned, command_count}` — the bounded tail of matching
        events, how many matched before the tail cut, how many were returned, and the
        total accepted-command count for trajectory context.
    """
    matched: list[dict] = []
    for raw in session.event_log:
        entry = _as_dict(raw)
        if visibility is not None and entry.get("visibility") != visibility:
            continue
        if kinds is not None and entry.get("event_type") not in kinds:
            continue
        matched.append(entry)
    if limit < 0:
        tail = matched  # the unbounded escape
    elif limit == 0:
        tail = []  # bounded to nothing (matched[-0:] would be the whole list, not empty)
    else:
        tail = matched[-limit:]
    return {
        "events": tail,
        "total_matched": len(matched),
        "returned": len(tail),
        "command_count": len(session.command_log),
    }
