---
name: play
description: Play a B/X dungeon crawl through the osrlib-referee MCP server, where the osrlib engine owns every roll and all game state and the LLM narrates and adjudicates freeform intent. Covers dungeon exploration, encounters, battle, the town economy, and level-up narration. Use when starting or continuing an osrlib-referee session, exploring a dungeon, running an encounter, resolving battle, or shopping and healing in town.
allowed-tools: mcp__plugin_osrlib-referee_osrlib__execute mcp__plugin_osrlib-referee_osrlib__observe mcp__plugin_osrlib-referee_osrlib__prose mcp__plugin_osrlib-referee_osrlib__session_new mcp__plugin_osrlib-referee_osrlib__session_save mcp__plugin_osrlib-referee_osrlib__character_sheet mcp__plugin_osrlib-referee_osrlib__list_commands mcp__plugin_osrlib-referee_osrlib__list_adventures Bash AskUserQuestion
---

# Play

One loop owns exploration, encounters, battle, and town — there is no separate combat skill re-deriving anything the engine already computed. `osrlib` holds the live session behind the MCP boundary; you narrate from what it returns and adjudicate freeform intent through the authorial commands.

**Read [the referee's constitution](../referee/references/constitution.md) before doing anything else.** It is the supreme, non-negotiable set of rules governing all referee behavior. The central rule it establishes: the engine computes everything — no THAC0, no target numbers, no hit-point arithmetic, ever, from you.

## Starting a session

The `referee` skill is the front door and routes here with the adventure already chosen. If you arrive directly:

1. **AskUserQuestion** — which adventure? Call `list_adventures` for the available `adventure_id`s (native adventures and discovered compiled bundles alike). If there's exactly one, use it without asking; if there's more than one, ask which. (To *resume* a save with a recap, that's the `session` skill.)
2. Call `session_new(adventure_id)` — add `party_ref=<party_id>` if the player built a party with the `character` skill, else the frozen pregen roster starts. This is the schema/engine-version handshake — it never returns the seed, and you never need it.
3. Call `observe()`. Right after `session_new` this comes back "cold" — it includes a bounded tail of recent events. Call `prose(area.id)` (or `prose("town")` if `area` is the town) and deliver its `read_aloud` verbatim as the opening scene.

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
- **Read the round's roster off `observe`'s `encounter` block — never assume it.** `declarers` is exactly who must be named. `front_rank` is who may declare a melee `attack`; anyone behind it rejects with `battle.declaration.not_in_front_rank`. `immobile` names who may not `close` or `withdraw`, and `reloading` who may not fire a reload weapon this round. Each list stands against one rejection that would bounce the whole round, so a round built from all four is a round the engine accepts.
- **Formation width follows the space the party fights in**, not the party's size: ten feet of frontage seats two characters side by side, so a corridor leaves the rest of the line with no swing. Give a back-rank character something they can actually do — `action: "hold"`, a missile `attack`, or a `cast` — and narrate it as the press of bodies in a tight passage, which is what it is. The rank re-forms between rounds as members fall, so re-read `front_rank` every round.
- **Fleeing is `move: "retreat"` for every declarer in the same round** — a mixed round (some retreat, some not) is not a party retreat at all. A clean escape is not immediate: it opens a pursuit in `encounter` mode, resolved by repeated `wait` calls (the engine reports `encounter.pursuit.round` each time) until it escapes or is caught.
- **`move: "withdraw"` is a legal value that does nothing.** It validates and consumes a declaration slot but produces no distance change and no mode transition — a known engine sharp edge. Use `"close"`, `"fighting_withdrawal"`, or the all-member `"retreat"` above.
- Never narrate a monster's tactics or intent beyond what the events show — the enemy side is the engine's, not yours to invent.

## Town

Town is a first-class mode, not just a bookend — a fresh session starts there, and the delve returns there. The rhythm: **return, sell, buy, heal, depart.**

`observe`'s town branch (present only in town) carries what you narrate from: each member's **purse** and **valuables**, their **level/xp/next_level_xp**, and the town's **service prose** (`area.services` — flavour, not the mechanical price list). Prices and the catalog are **not** in `observe` — they are static reference data, read off the play surface with the `gametool` CLI via `Bash`:

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog     # ids, names, cost_gp, lot sizes, damage
uv run --project server python -m osrlib_referee_mcp.gametool services     # the six temple services and prices
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter   # a class's XP-and-level table
```

The town commands are already in the `AnyCommand` union you `execute` — each `TOWN`-gated:

- **`SellTreasure(item_ids)`** — sell carried valuables at full `value_gp` (their `instance_id`s are in `observe`'s `valuables`). A magic item rejects `town.sell.no_fixed_value`.
- **`PurchaseEquipment(character_id, item_ids)`** — buy from the catalog; each entry is one purchase lot. The **whole basket must be affordable or nothing buys** (`items.purchase.insufficient_funds`).
- **`PurchaseHealing(character_id, service)`** — one of the six temple services (`gametool services` lists them and their prices); the engine heals and debits the purse.
- **`EnterDungeon(dungeon_id)`** — depart town for the delve. This is the **town** command that starts an expedition; it snapshots the party's treasure valuation for the return-trip XP delta.

**The sharp edge:** returning home is not a town command. `TravelToTown` is an `EXPLORING` command issued while standing on the dungeon **entrance cell** — walk the party back there first. `EnterDungeon` is how you leave town; `TravelToTown` is how you come back.

**Return-trip XP is automatic — and a free win over `bx-referee`.** On `TravelToTown`, the engine awards `monster_xp` + `treasure_xp` (1 gp recovered = 1 XP) automatically, emitting one `AdventureXpAwardEvent` (with the totals and per-head `share`) then a per-survivor `XpAwardedEvent`. Narrate the award from those events; never compute an XP total yourself. `bx-referee` never implements treasure XP, so this beat is parity-plus for free. Because an award can cross a threshold, this is exactly where a level-up fires.

## Level-up

Advancement is **engine-automatic and eventless.** There is no `LevelUp` command and no level-up event — leveling is a side effect of any XP award (the common trigger is the return-trip award above), clamped to one level per award. The only signal is `XpAwardedEvent.level_after`.

- **Infer the advance:** when a member's `XpAwardedEvent.level_after` is higher than the level they held before the award, announce the new level. Read the **new max HP** from `observe` (or `character_sheet(character_id)` for the full new derived sheet — new THAC0, saves, spell slots — to narrate any new capability).
- **Never fabricate the hit-die roll.** The engine rolled it and committed the result, but emits it in no event; report the outcome (the new max HP `observe` now shows), never an invented die (constitution Article III.1 / VII.3).
- **Two honest divergences from `bx-referee`, narrated as osrlib actually behaves:**
  - **Level-up does not restore HP.** osrlib adds the rolled HP to both max and current, but heals no existing damage — a wounded character who levels is **still wounded**. Never narrate `bx-referee`'s full-heal-on-level.
  - **One level per *award*, not one per session, and no separate level-up step.** The engine advances inline and clamps one level per award; there is no skill hop and no once-per-session cap. Narrate it in place.

## Sharp edges to hold onto

- **Light before anything requiring it.** `light_source` is one attempt per call (a 2-in-6 chance unless an open flame is already burning) and burns a round either way — reissue it on a miss. `search`/`pick_lock` require light; check `observe`'s party effects or just attempt and read the rejection.
- **Stand on the entrance cell before `travel_to_town`.** It rejects `exploration.travel.not_at_entrance` otherwise — walk the party back first.
- **Doors close behind the party.** A door you opened to pass through may need `open_door` again on the way back; don't assume it's still open.

## Saving

Call `session_save()` at natural pause points (returning to town, ending the session) or whenever the player asks for a quick save. Report the `save_id` back so they know what to resume with. For **resuming a save with a recap**, an **optional session journal**, or **reviewing the roll-log**, that is the `session` skill. The save-slot layout lives in the user's game directory (`~/osr-games` by default, or wherever `OSRLIB_REFEREE_GAME_ROOT` points) — never the plugin cache, and never something this skill manages directly.

## Tool reference

| Tool | Use |
|---|---|
| `session_new(adventure_id, seed?, party_document?, party_ref?, save_id?)` | Start a fresh session; persists immediately. `party_ref` loads a `chargen`-built party by id; `save_id` defaults to the `adventure_id`. |
| `session_save()` | Persist the active session to its current slot. |
| `execute(command)` | Run one `AnyCommand`-union command; returns `{accepted, rejections, events}`. |
| `observe(scope="current")` | The scoped current-state projection: mode, legal commands, location, area (+ town services), edges, party (+ level/xp/next-threshold, + purse/valuables in town), effects, flags, encounter/battle. |
| `character_sheet(character_id)` | The full derived sheet — THAC0, AC, saves, movement, spell slots — for a sheet display or narrating a new capability after an advance. |
| `prose(area_id)` | The authored `{read_aloud, referee_notes}` for an area, or `"town"`. |
| `list_commands(mode?)` | The mode-scoped command menu, split player-intent / authorial. |
| `list_adventures()` | The adventures this server can start — native builders and discovered on-disk bundles. |
| `gametool …` (Bash) | Static reference reads off the play surface: `catalog`, `services`, `thresholds <class>`. |
