"""`observe(scope="current")`: the hand-built, scoped referee projection.

The single most important server-side design decision (per `docs/spec.md`). This is
**not** the raw `RefereeView` — that is `session_state(include_event_log=True)` minus
`rng_streams`/`master_seed`: the whole adventure spec, the full unbounded event log,
and the always-on command log. Shipping that every turn would erase the token win.

Instead this reads live `GameSession` attributes directly (never `session_state()`),
scoped to the current area and scene only, adapting the `build_player_view` pattern
(`osrlib.crawl.views`) but reversing its three player-visibility masks — monster HP,
undiscovered secret doors, and effect durations — since the referee agent is trusted.
Events are not re-shipped here on warm calls; they ride `execute`'s own envelope. A
cold call (e.g. right after `session_load`) includes a bounded tail of the event log
so the skill can recap.
"""

from osrlib.core.effects import Condition, has_condition
from osrlib.crawl.dungeon import Direction, EdgeKind, edge_ref
from osrlib.crawl.session import GameSession

from osrlib_referee_mcp.catalog import list_command_types

COLD_EVENT_TAIL = 20


def _next_level_xp(member) -> int | None:
    """The XP threshold for the member's next level, or `None` at the class cap.

    Read from the class progression row (`ClassDefinition.row(level+1).xp`) — the same
    lookup advancement uses — so the referee (and, appropriately, the player) can see how
    close each character is to levelling. There is no level-up event to surface; this
    field plus `XpAwardedEvent.level_after` is how an advance is inferred (work item C).
    """
    definition = member.definition
    if member.level >= definition.max_level:
        return None
    return definition.row(member.level + 1).xp


def _member_view(member, *, in_town: bool) -> dict:
    view = {
        "id": member.id,
        "name": member.name,
        "class_id": member.class_id,
        "level": member.level,
        "xp": member.xp,
        "next_level_xp": _next_level_xp(member),
        "current_hp": member.current_hp,
        "max_hp": member.max_hp,
        "conditions": [active.condition.value for active in member.conditions],
    }
    if in_town:
        # The town spend surface: the purse the player buys and heals against, and the
        # valuables they can sell. Shipped only in town, so the dungeon payload stays
        # scoped — the advancement integers above are the only per-turn growth.
        view["purse"] = member.inventory.purse.model_dump(mode="json")
        view["valuables"] = [
            {
                "instance_id": valuable.instance_id,
                "kind": valuable.kind,
                "name": valuable.name,
                "value_gp": valuable.value_gp,
            }
            for valuable in member.inventory.valuables
        ]
    return view


def _effect_view(session, effect) -> dict:
    remaining_rounds = None if effect.expires_round is None else max(0, effect.expires_round - session.clock.rounds)
    return {
        "character_id": effect.target_ref,
        "kind": effect.definition.kind,
        "remaining_rounds": remaining_rounds,
    }


def _monster_view(session, monster_id: str) -> dict:
    monster = session.combatant(monster_id)
    return {
        "id": monster_id,
        "template_id": monster.template.id,
        "current_hp": monster.current_hp,
        "max_hp": monster.max_hp,
        "conditions": [active.condition.value for active in monster.conditions],
        "dead": has_condition(monster, Condition.DEAD),
    }


def _encounter_view(session) -> dict | None:
    state = session.encounter
    if state is None:
        return None
    groups = [
        {
            "id": group.id,
            "label": group.label,
            "distance_feet": group.distance_feet,
            "fleeing": group.fleeing,
            "fled": group.fled,
            "surrendered": group.surrendered,
            "monsters": [_monster_view(session, monster_id) for monster_id in group.monster_ids],
        }
        for group in state.groups
    ]
    return {
        "kind": state.kind,
        "stance": state.stance,
        "groups": groups,
        "pursuit_gap_feet": state.pursuit.gap_feet if state.pursuit is not None else None,
    }


def _battle_view(session) -> dict | None:
    battle = session.battle
    if battle is None:
        return None
    return {"round": battle.round}


def _area_and_edges(session, location) -> tuple[dict | None, dict]:
    """The current area (or `None` in a corridor) and this cell's four edges.

    Referee-visibility, not player-visibility: an undiscovered secret door reports
    its true kind here (the player view masks it to `"wall"`); this trusted server
    never leaks hidden geometry to a wire client because there is no wire client —
    only the LLM referee, over `observe`.
    """
    level = session.adventure.dungeon(location.dungeon_id).level(location.level_number)
    cell = location.position
    area_spec = level.area_at(cell)
    area = (
        None
        if area_spec is None
        else {
            "id": area_spec.id,
            "name": area_spec.name,
            "description": area_spec.description,
            "cells": [list(c) for c in area_spec.cells],
        }
    )
    edges: dict[str, dict] = {}
    for direction in Direction:
        edge = level.edge(cell, direction)
        if edge.kind is EdgeKind.DOOR:
            ref = edge_ref(location.dungeon_id, location.level_number, cell, direction)
            door_state = session.dungeon_state.doors.get(ref)
            edges[direction.value] = {
                "kind": "door",
                "secret": edge.door.kind == "secret",
                "locked": edge.door.locked,
                "stuck": edge.door.stuck,
                "open": bool(door_state.open) if door_state is not None else edge.door.starts_open,
                "wedged": bool(door_state.wedged) if door_state is not None else False,
                "discovered": bool(door_state.discovered) if door_state is not None else False,
            }
        else:
            edges[direction.value] = {"kind": edge.kind.value}
    return area, edges


def build_observation(session: GameSession, *, cold: bool = False) -> dict:
    """Build the scoped referee projection from live session state.

    Args:
        session: The running session.
        cold: True right after a fresh `session_new`/`session_load` — includes a
            bounded event-log tail so the skill can recap. Warm (mid-turn) calls omit
            events; those ride `execute`'s own result envelope.

    Returns:
        The projection dict: `mode`, `legal_commands`, `clock_rounds`, `location`,
        `area` (`None` in a corridor), `edges`, `party`, `effects`, `flags`,
        `encounter`, `battle`, and — cold calls only — `events`.
    """
    location = session.dungeon_state.location
    mode = session.mode.value
    in_town = location.kind != "dungeon"
    if location.kind == "dungeon":
        area, edges = _area_and_edges(session, location)
        location_view = {
            "kind": "dungeon",
            "dungeon_id": location.dungeon_id,
            "level_number": location.level_number,
            "position": list(location.position),
            "facing": location.facing.value,
        }
    else:
        town = session.adventure.town
        # `services` is the town's front-end prose (flavour: "a temple, a smith"), *not*
        # the mechanical healing-service list — that price table is static reference data,
        # delivered off the play surface by the `gametool services` CLI.
        area = {
            "id": "town",
            "name": town.name,
            "description": town.description,
            "services": list(town.services),
        }
        edges = {}
        location_view = {"kind": "town"}

    member_ids = {member.id for member in session.party.members}
    observation = {
        "mode": mode,
        "legal_commands": list_command_types(mode),
        "clock_rounds": session.clock.rounds,
        "location": location_view,
        "area": area,
        "edges": edges,
        "party": [_member_view(member, in_town=in_town) for member in session.party.members],
        "effects": [
            _effect_view(session, effect) for effect in session.ledger.effects if effect.target_ref in member_ids
        ],
        "flags": dict(session.flags),
        "encounter": _encounter_view(session),
        "battle": _battle_view(session),
    }
    if cold:
        tail = session.event_log[-COLD_EVENT_TAIL:]
        observation["events"] = [entry if isinstance(entry, dict) else entry.model_dump(mode="json") for entry in tail]
    return observation


def build_character_sheet(session: GameSession, character_id: str) -> dict:
    """Build the full derived character sheet for one party member.

    osrlib computes THAC0, AC, saves, movement, and spell slots as properties from
    stored state — never storing them, so they can't desync — and `observe` does not
    ship them per turn. This read materializes them on request from the **live** session
    (the party member and the session's ruleset), giving parity with `bx-referee`'s sheet
    display and the numbers the `character`/`session` skills render on demand. It is a
    play-server tool because it needs the live member.

    Args:
        session: The running session.
        character_id: A party member's id (from `observe`'s `party[].id`).

    Returns:
        The derived sheet: identity, scores, level/xp/next-threshold, hit points, the
        combat numbers (THAC0, attack bonus, both AC formats), the five saves, movement
        rate, languages, spell slots, and the caster's book/memorized spells.

    Raises:
        ValueError: If `character_id` names no party member.
    """
    member = session.member(character_id)
    definition = member.definition
    row = definition.row(member.level)
    return {
        "id": member.id,
        "name": member.name,
        "class_id": member.class_id,
        "class_name": definition.name,
        "race": member.race,
        "alignment": member.alignment.value,
        "level": member.level,
        "xp": member.xp,
        "next_level_xp": _next_level_xp(member),
        "max_hp": member.max_hp,
        "current_hp": member.current_hp,
        "scores": {ability.value: score for ability, score in member.scores.items()},
        "thac0": member.thac0,
        "attack_bonus": member.attack_bonus,
        "armour_class": member.armour_class,
        "armour_class_ascending": member.armour_class_ascending,
        "saves": member.saves.model_dump(mode="json"),
        "movement_rate": member.movement_rate(session.ruleset),
        "languages": list(member.languages),
        "spell_slots": list(row.spell_slots),
        "spell_book": list(member.spell_book),
        "memorized_spells": [prepared.model_dump(mode="json") for prepared in member.memorized_spells],
        "conditions": [active.condition.value for active in member.conditions],
    }
