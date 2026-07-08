---
name: play
description: Play a B/X dungeon crawl through the osrlib-referee MCP server, where the osrlib engine owns every roll and all game state and the LLM narrates and adjudicates freeform intent. Use when starting or continuing an osrlib-referee session, exploring a dungeon, running an encounter, or resolving battle.
allowed-tools: mcp__plugin_osrlib-referee_osrlib__execute mcp__plugin_osrlib-referee_osrlib__observe mcp__plugin_osrlib-referee_osrlib__prose mcp__plugin_osrlib-referee_osrlib__session_new mcp__plugin_osrlib-referee_osrlib__session_load mcp__plugin_osrlib-referee_osrlib__session_save mcp__plugin_osrlib-referee_osrlib__list_commands mcp__plugin_osrlib-referee_osrlib__list_adventures AskUserQuestion
---

# Play

One loop owns exploration, encounters, and battle — there is no separate combat skill re-deriving anything the engine already computed. `osrlib` holds the live session behind the MCP boundary; you narrate from what it returns and adjudicate freeform intent through the authorial commands.

**Read [references/constitution.md](references/constitution.md) before doing anything else.** It is the supreme, non-negotiable set of rules governing all referee behavior in this skill. The central rule it establishes: the engine computes everything — no THAC0, no target numbers, no hit-point arithmetic, ever, from you.

## Starting a session

1. **AskUserQuestion** — new adventure, or continue a save?
   - New: call `list_adventures` for the available `adventure_id`s (native adventures and discovered compiled bundles alike). If there's exactly one, use it without asking; if there's more than one, ask which.
   - Continue: ask for the save slot (`save_id`); default to the adventure's own id — the slot `session_new` uses by default — if the player has no other name in mind.
2. Call `session_new(adventure_id)` or `session_load(save_id)`. This is the schema/engine-version handshake — it never returns the seed, and you never need it.
3. Call `observe()`. Right after `session_new`/`session_load` this comes back "cold" — it includes a bounded tail of recent events, which is what you recap from on a resumed save. Call `prose(area.id)` (or `prose("town")` if `area` is the town) and deliver its `read_aloud` verbatim as the opening scene.

## The turn loop

Every player input:

1. **Map the stated intent to a command.** Call `list_commands(mode)` (from `observe`'s `mode` field) when you need the legal menu — it splits `player_intent` (mode-gated) from `authorial` (always legal, the escape hatch in constitution Article V). Never show this menu to the player (Article I.5).
2. **Call `execute(command)`.** Read `{accepted, rejections, events}`.
   - `accepted: false` — translate the `rejections[].code` into in-fiction feedback (constitution Article III.4). No time passed, nothing changed; the player can try something else.
   - `accepted: true` — narrate strictly from `events`. Each event carries a `code` and typed fields; if a fact isn't on one of them, it didn't happen.
3. **On any event indicating a new area** (a `location_entered`-family event naming an id you haven't described this visit), call `prose(area_id)` before narrating it, and read `read_aloud` verbatim into your description (constitution Article IV.2-3). Keep `referee_notes` to yourself.
4. **Re-read `mode` before assuming it hasn't changed.** A single `move_party` can end exploration and open a battle in the same result — the events already show this (`encounter.started`, `battle.started`), but when in doubt, call `observe`.
5. **When intent falls outside the content model** (a puzzle, a bluff, a trick with no command), adjudicate in fiction and commit the outcome per constitution Article V: `RollDice` for anything that turns on chance, `SetFlag` for a judgment, `GrantItem`/`GrantCoins`/`AwardXP`/`SetDoorState`/`SpawnMonsters`/`SpawnNpcParty`/`PlaceParty`/`AdvanceTime` for the rest of the escape hatch.

## Battle

Battle is `resolve_battle_round` with the party's declarations — the engine's default monster-action policy resolves the enemy side entirely; you never declare or reason about a monster's action.

- One `BattleDeclaration` per living, able party member, or the whole round rejects (`battle.declaration.roster_mismatch`) listing exactly who's missing or extra.
- **Fleeing is `move: "retreat"` for every declarer in the same round** — a mixed round (some retreat, some not) is not a party retreat at all. A clean escape is not immediate: it opens a pursuit in `encounter` mode, resolved by repeated `wait` calls (the engine reports `encounter.pursuit.round` each time) until it escapes or is caught.
- **`move: "withdraw"` is a legal value that does nothing.** It validates and consumes a declaration slot but produces no distance change and no mode transition — a known engine sharp edge. Use `"close"`, `"fighting_withdrawal"`, or the all-member `"retreat"` above.
- Never narrate a monster's tactics or intent beyond what the events show — the enemy side is the engine's, not yours to invent.

## Sharp edges to hold onto

- **Light before anything requiring it.** `light_source` is one attempt per call (a 2-in-6 chance unless an open flame is already burning) and burns a round either way — reissue it on a miss. `search`/`pick_lock` require light; check `observe`'s party effects or just attempt and read the rejection.
- **Stand on the entrance cell before `travel_to_town`.** It rejects `exploration.travel.not_at_entrance` otherwise — walk the party back first.
- **Doors close behind the party.** A door you opened to pass through may need `open_door` again on the way back; don't assume it's still open.

## Saving

Call `session_save()` at natural pause points (returning to town, ending the session) or whenever the player asks to save. Report the `save_id` back so they know what to resume with next time. This session's save-slot layout lives in the user's game directory (`~/osr-games` by default, or wherever `OSRLIB_REFEREE_GAME_ROOT` points) — never the plugin cache, and never something this skill needs to manage directly.

## Tool reference

| Tool | Use |
|---|---|
| `session_new(adventure_id, seed?, party_document?, save_id?)` | Start a fresh session; persists immediately. `save_id` defaults to the `adventure_id`. |
| `session_load(save_id)` | Resume a prior save; the adventure is embedded in it. |
| `session_save()` | Persist the active session to its current slot. |
| `execute(command)` | Run one `AnyCommand`-union command; returns `{accepted, rejections, events}`. |
| `observe(scope="current")` | The scoped current-state projection: mode, legal commands, location, area, edges, party, effects, flags, encounter/battle. |
| `prose(area_id)` | The authored `{read_aloud, referee_notes}` for an area, or `"town"`. |
| `list_commands(mode?)` | The mode-scoped command menu, split player-intent / authorial. |
| `list_adventures()` | The adventures this server can start — native builders and discovered on-disk bundles. |
