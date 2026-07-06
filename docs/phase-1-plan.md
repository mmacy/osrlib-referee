# Phase 1 plan — prove the loop on native content

Implementation plan for Phase 1 of [the osrlib-referee spec](spec.md). Phase 0 proved the wire: a plugin-bundled stdio MCP server launches inside Claude Code and round-trips one `execute` call. Phase 1 proves the **thesis**: that moving all mechanics and state into the `osrlib` engine — behind a small, purpose-built tool surface — makes a real B/X dungeon delve playable from Claude Code while collapsing the mechanical/state token overhead that `bx-referee` spends on reloading rules and re-emitting Markdown.

Phase 1 builds no published module and no content-ingestion pipeline (that is Phase 2). It authors one small **native** `osrlib` adventure, builds the four core tools the architecture rests on (`execute`, `observe`, `prose`, lifecycle), writes a single `play` skill governed by a `constitution`, plays a scripted delve end-to-end, and then **measures** the delve both ways — through osrlib-referee and through `bx-referee` — to show the overhead collapse with numbers, not assertion.

## The milestone

A scripted delve — **enter a dungeon, explore between keyed rooms, spring a trap, fight a keyed encounter, flee, return to town** — is played end-to-end through the MCP boundary inside Claude Code, with every roll, stat, and state transition computed by `osrlib` and the LLM spending its tokens only on fiction. Then the same delve is run through `bx-referee`, and a token count shows the mechanical/state overhead demonstrably collapsed after honestly netting osrlib-referee's own standing costs (the `AnyCommand` union schema advertised every turn, and the `observe` projection shipped each turn).

## Scope

In scope:

- **The native adventure bundle.** One small `osrlib` `Adventure` (a single-level dungeon + a town), authored in Python against the installed public content model — re-authored in the spirit of the `tui_crawler` barrow, never imported from `examples/` (the wheel does not ship it). Plus its out-of-band **prose sidecar** (`{area_id: {read_aloud, referee_notes}}`), original CC0 content committed in-repo.
- **`execute` over the real `AnyCommand` union.** Upgrade Phase 0's raw-`dict` argument to the typed discriminated union (`command_type` discriminator, 45 members). This is the design the spec pins — the union schema is advertised in full every turn — so Phase 1 both *builds* it and *measures* its standing per-turn cost rather than hiding it behind a `dict`.
- **`observe(scope="current")` — the scoped referee projection.** A hand-built, current-state snapshot reading live `GameSession` attributes (never `session_state()`), carrying mode, mode-legal commands, current area, party, active encounter/battle with real monster HP, and flags — at referee visibility. The spec calls this "the single most important server-side design decision."
- **`prose(area_id)`.** Returns the authored sidecar `{read_aloud, referee_notes}` for an area — the bridge across the content gap osrlib leaves open (one opaque `AreaSpec.description`).
- **The session lifecycle + durable saves.** `session_new`, `session_load`, `session_save`, persisting the full `save_game` document to the user's game directory (`~/osr-games/…`), never the plugin cache. Includes a minimal internal, seeded pre-session party build (`create_character` → `party_to_document`).
- **The `OsrlibError` → tool-error taxonomy.** Map in-fiction rejections to normal tool results and out-of-fiction `OsrlibError`s (`ContentValidationError`/`SaveVersionError`/`ReplayVersionError`) to tool errors, mirroring the FastAPI example's status map.
- **A single `play` skill + a `constitution`**, borrowing `bx-referee`'s OSE voice and information discipline but inverting its rules-authority role: the engine owns mechanics; the LLM narrates from events and adjudicates freeform intent via the authorial commands.
- **A test ladder** (adventure validation, in-process scripted delve, `observe` shape, save round-trip, error map, seed-locked trap golden) plus the manual Claude Code play-through.
- **The token measurement** — methodology, the matched `bx-referee` baseline, and a recorded verdict.

Out of scope (named so the phase does not over-reach):

- **Adventure-module ingestion, the bundle format/loader, and the injectable-catalog engine change** — **Phase 2**. Phase 1 uses only native content with standard SRD monsters, which resolve against the shipped catalog without any engine change (see work item 1).
- **A player-facing character-creation tool, town/economy commands, and interactive level-up UI** — **Phase 3**. Phase 1 runs `create_character` only internally to build a fixed pregen party; the party document surface as a *tool* waits.
- **Multi-level dungeons and `TransitionSpec` (stairs/chutes)** — not needed for a single-level scripted delve; deferred until content demands it.
- **The eval/replay harness** (record seed + command log, replay offline to score trajectories) — **Phase 4**. Phase 1 *relies* on determinism for its golden test and notes that the osrlib side of the measurement is a replayable trajectory, but builds no scoring harness.
- **Wandering monsters as a scripted beat.** The demo level pins `WanderingSpec(chance_in_six=0)` so the scripted run is deterministic; the wandering path exists in the engine and the play skill tolerates it, but the delve does not depend on it.
- **The `list_adventures`/`list_commands` helpers beyond the minimum.** `list_commands(mode)` ships (it is the runtime menu the union schema cannot provide); `list_adventures` is a trivial registry read. Neither is load-bearing for the thesis.

## The scripted delve we are proving

The delve is the same six beats the spec's milestone names, plus the town bookends. Each beat maps to concrete `osrlib` commands and modes (all citations are `file:line` in `~/repos/osrlib-python/src/osrlib`):

| Beat | Command(s) | `command_type` → mode | Engine source |
|---|---|---|---|
| Enter the dungeon | `EnterDungeon(dungeon_id)` | TOWN → EXPLORING | `crawl/exploration.py:991`; allowed_modes `{town}` `crawl/commands.py:984` |
| Light a torch (party has no infravision) | `LightSource(character_id, item_id)` | EXPLORING | `crawl/commands.py:600`; light is a hard prereq for Search/PickLock `crawl/commands.py:434,400` |
| Explore room-to-room | `MoveParty(direction)` / `TurnParty(facing)` | EXPLORING | `crawl/commands.py:151` (MoveParty, `{EXPLORING}` at :175), `:181` (TurnParty) |
| Open a door | `OpenDoor(direction)` (`ForceDoor`/`PickLock` fallbacks) | EXPLORING | `crawl/commands.py:229,286,382` |
| Spring a trap | *no command* — 2-in-6 side effect of `MoveParty` entry into the trapped area | EXPLORING | spring roll `crawl/exploration.py:687-691` |
| Encounter appears + fight opens | *no command* — side effect of `MoveParty` into the keyed cell; the pinned `ATTACKS` stance opens battle in the same result | EXPLORING → BATTLE | `crawl/exploration.py:830-870`; pinned-stance auto-open `crawl/encounter.py:215-217,224-237` → `crawl/battle.py:514` |
| Fight | `ResolveBattleRound(declarations)` — battle is already open (stance-pinned), so **no `EngageBattle`** (it is `{ENCOUNTER}`-only and would be rejected wrong-mode) | BATTLE | `crawl/commands.py:1301`; battle `crawl/battle.py:1022`; `EngageBattle` gate `crawl/commands.py:1207` |
| Flee | `ResolveBattleRound` with every member `move="retreat"` → pursuit; then `Wait` repeated until the pursuit resolves to an escape (up to the pursuit round cap) | BATTLE → ENCOUNTER → EXPLORING | retreat `crawl/battle.py:550-559,1170-1174`; escape via repeated `Wait` `crawl/encounter.py:560-564`, mode reset `crawl/encounter.py:763-764` |
| Walk back to entrance | `MoveParty(direction)` | EXPLORING | as above |
| Return to town | `TravelToTown` (must stand on the entrance cell) | EXPLORING → TOWN | `crawl/exploration.py:1002`; rejects `exploration.travel.not_at_entrance` `crawl/commands.py:1002` |

**Three determinism levers make the scripted beats reliable** (the engine has real randomness the demo must control):

1. **The fight is pinned, not seed-gambled.** A keyed encounter's reaction is a 2d6 roll (`crawl/encounter.py:218-221`), but `_keyed_encounter_check` passes `pinned_stance=area.encounter.stance` (`crawl/exploration.py:860-870`) and a pinned stance **skips the reaction roll entirely** (`crawl/encounter.py:215-217`). Author the keyed area with `stance=ATTACKS` so battle opens on entry regardless of seed.
2. **The trap is seed-locked.** A room trap springs on a hardcoded **2-in-6** roll drawn from the exploration stream on `MoveParty` entry (`crawl/exploration.py:687-691`) — there is no "always spring" content flag, and `RollDice` cannot fire it. Because the server owns the master seed and the exact command sequence, the exploration-stream draw at the scripted entry is deterministic. The demo adventure ships with a **chosen seed** where the scripted entry springs the trap, pinned by a golden test. Corollary: the scripted party must **not** `Search(kind="room_traps")` the trap room — a found trap no longer springs (`crawl/exploration.py:684,1251`) — and the party must contain no dwarf (passive 2-in-6 detection). **Note the stream coupling:** the first `LightSource` also draws a variable-retry tinder-strike 2-in-6 from the *same* `EXPLORATION_STREAM` (`crawl/exploration.py:1608-1612`, fails ~4-in-6 and burns the round on failure), so lighting the torch consumes draws ahead of the trap. The seed search must therefore hold the *entire* command prefix fixed — including however many `LightSource` attempts the chosen seed needs — and the golden test encodes that exact prefix. (An all-infravision party would remove the light variable, but the plan deliberately keeps a non-infravision party to exercise the `LightSource` beat; the cost is this tighter seed coupling.)
3. **The flee escape is seed-checked.** Escaping a pursuit is not guaranteed; the golden test pins the seed and the encounter distance so the scripted retreat resolves to a clean escape back to EXPLORING. If a clean escape proves seed-fragile, the fallback is to widen the initial encounter distance (favoring evasion) — a content lever, recorded in the test.

The demo trap is a **room trap, `trigger="enter"`, `damage_dice="1d8"`, no save** (`crawl/dungeon.py:276-289,230-273`) — deterministic once sprung, non-lethal, single event path. Explicitly **not** a `kills=True` save-or-die trap, which one-shots a PC on a failed death save (`crawl/exploration.py:725-728`).

## The four core tools

The tool surface is deliberately small; the design lives in the projection and the error map, not in tool count.

### `execute(command: AnyCommand)`

Phase 0 typed the argument as a raw `dict` to defer the union-schema cost. Phase 1 pays it deliberately: the argument becomes the `AnyCommand` discriminated union (`crawl/commands.py`, `command_type` discriminator, `ALL_COMMAND_CLASSES` at `crawl/commands.py:1650-1696`), because *that standing per-turn cost is exactly what the spec pins Phase 1 to measure*. Dropping to raw `dict` would measure a design the spec does not describe and rig the comparison in osrlib-referee's favor.

- Return shape is unchanged from Phase 0 and load-bearing: `{accepted, rejections: [...], events: [...]}`, dumping each rejection and event **individually** (`e.model_dump(mode="json")` per element, or the `AnyEvent` TypeAdapter at `crawl/events.py:732-735`). `events` is typed as the base `Event` (`crawl/commands.py:148`), so a container dump silently drops `event_type` and every subclass field — the entire token thesis is narrating from event fields, so the tool must not lose them.
- The FastMCP annotation lesson from Phase 0 carries: the return must be annotated `dict[str, object]` so FastMCP emits an output schema and populates `structuredContent`.
- **A Phase-1 work-item spike, not an assumption: confirm FastMCP accepts a 45-variant discriminated union as an *input* argument** and generates a discriminated input schema that round-trips a real command. Phase 0 already surfaced one FastMCP schema wrinkle (`-> dict` vs `dict[str, object]`); a large discriminated *input* union is untested. If FastMCP mishandles it, the fallback is to keep the argument a `dict` but ship the union schema to the model another way (a resource, or the `list_commands` payload) — and the measurement must then note that the union cost is advertised via that channel, not the tool arg. Decide from evidence.

### `observe(scope="current")` — the scoped referee projection

The most important server-side decision. It must **not** return the raw `RefereeView`: `build_referee_view` is literally `session_state(include_event_log=True)` minus `rng_streams` and `master_seed` (`crawl/views.py:404-418`) — the whole adventure spec + the full unbounded event log + the always-on command log (`persistence.py:79-117`). Shipping that every turn erases the token win. Instead the server builds a projection **by hand from live `GameSession` attributes** (the `build_player_view` pattern at `crawl/views.py:245-322`, minus the player masking), never calling `session_state()`.

The projection schema, each field annotated with its osrlib source:

| Field | Source (`file:line`) | Notes |
|---|---|---|
| `mode` | `session.mode.value` (`crawl/session.py:224`; enum `crawl/commands.py:93-104`) | town/exploring/encounter/battle/game_over |
| `legal_commands` | `ALL_COMMAND_CLASSES` filtered by `cls.allowed_modes` (`crawl/commands.py:1650-1696,124`) | split player-intent from referee/authorial commands (the 11 authorial commands inherit all modes and would otherwise flood every list) |
| `clock_rounds` | `session.clock.rounds` (`crawl/session.py:223`) | |
| `location` | `session.dungeon_state.location` → position, facing (`crawl/dungeon.py:589-608`) | |
| `area` | `level.area_at(position)` → id, name, description, cells (`crawl/dungeon.py:526-538`, `AreaSpec` `437-460`) | **null in corridors** (`area_at()` returns `None`) — defined fallback: null area id + current cell only |
| `edges` | `level.edge(cell, dir)` + `dungeon_state.doors[edge_ref]` (`crawl/dungeon.py:509-524,611-624`; recipe `crawl/views.py:334-365`) | **referee-only:** show undiscovered secret doors (do *not* mask to "wall" as `crawl/views.py:356` does for players) |
| `party` | `session.party.members` (list order = marching order); HP `member.current_hp`/`max_hp` (`crawl/party.py:28`, `crawl/views.py:260-261`) | |
| `effects` | `session.ledger.effects` filtered by member ref (`core/effects.py:505-535`) | **referee-only:** compute true remaining rounds even for potions (`crawl/views.py:238-239` nulls them for players) |
| `flags` | `session.flags` (`crawl/session.py:228`) | **referee-only:** `PlayerView` has no flags field |
| `encounter` | `session.encounter` → stance, distance, groups (`crawl/encounter.py:89-105`) | present only in encounter/battle |
| `encounter.groups[].monsters[]` | per-monster `session.combatant(id)` → `current_hp`/`max_hp` (`crawl/session.py:382-398`, `core/monsters.py:462-466`) | **referee-only:** real monster HP; keep `group.id` — it is the `target_group_id` command vocabulary (`crawl/views.py:104-108`) |
| `battle` | `session.battle` → round, engagements (`crawl/battle.py:110-122`) | present only in battle |
| `events` (cold call only) | bounded tail of `session.event_log` (`crawl/session.py:232`) | omit on warm calls (events ride `execute`'s envelope); on cold calls, ship the last scene's referee-visible events; tolerate raw-`dict` log entries (`persistence.py:270-273`) |

**The three player-masks the referee projection reverses** — the precise referee-visibility list — are monster HP, undiscovered secret doors, and effect durations. **The token bound is the scoping itself:** ship only the *current* area's cells/prose and the *current* scene, never the whole `adventure` or the whole explored map (`crawl/views.py:334-335` iterates the unbounded explored dict — the projection must not). Residual hotspot: a single large keyed area's `cells` tuple — cap it or ship current-cell-plus-adjacent if it balloons. **The exact field set is a Phase-1 empirical tuning target** (the spec pins observation-scope tuning to real play): too little and the LLM round-trips for more; too much and the win erodes. The first milestone plays the delve, the second tunes the projection from that play, then measures.

### `prose(area_id)`

Returns the authored sidecar for an area: `{read_aloud, referee_notes}`. This is the content gap made concrete: `AreaSpec.description` is one opaque, display-only string the engine never branches on (`crawl/dungeon.py:441-443,449`), with no player/referee split anywhere in the model. The only stable handle is `AreaSpec.id` (`crawl/dungeon.py:447`), which is the sidecar key.

- **Division of labor with `observe`:** `observe` carries the live *mechanical* scene (including the opaque `description` string, verbatim); `prose(area_id)` carries the *authored* narration split into player-facing read-aloud and referee-only notes. The play skill calls `prose` **on first entering a new area** (a `LocationEnteredEvent`), and reads `observe` **every turn** for current state.
- On-disk/in-bundle format: pinned in work item 1.

### Lifecycle — `session_new`, `session_load`, `session_save`

osrlib does **zero file I/O and assigns no save ids** — persistence is pure dict-in/dict-out (`persistence.py`). Durable disk saves, the `save_id`, and adventure resolution are entirely the server's to invent; the FastAPI example's in-memory store is explicitly *not* inherited.

- **`session_new(adventure_id, seed?, party_document?)`** — resolve `adventure_id` against the server's own native registry (osrlib has no adventure loader; `session_new` unknown id → tool error). Build the party: in Phase 1, when no `party_document` is supplied, construct a **fixed, seeded pregen roster internally** via `create_character` (`core/character.py:628-640`) → `party_to_document` (`core/character.py:339-351`); the `party_document` parameter exists for the Phase-3 character tool but Phase 1 supplies a default. Then `members = party_from_document(doc)` → `GameSession.new(Party(members=members), adventure, seed=seed)` (`crawl/session.py:254`). `GameSession.new` runs `validate_adventure(adventure, load_monsters(), load_equipment())` (`crawl/session.py:273`) — dangling content → `ContentValidationError`. Seed defaults to a server secret if omitted. Mint a `save_id` and **persist immediately** so the game is durable from turn 0. Return the `{schema_version, engine_version}` handshake (`crawl/session.py:286`), never the seed.
- **`session_save()`** — `document = save_game(session)` (`persistence.py:120`), a JSON-ready dict, written **verbatim** to `<game-root>/adventures/<name>/<save_id>.json`. Verbatim matters: determinism depends on `master_seed` plus the snapshots of every *touched* RNG stream (untouched streams re-derive from the seed) (`core/rng.py:268-277`); any lossy re-encode or a dropped seed breaks byte-identity and replay. `save_id` is the server's chosen filename stem (a stable slot, not a `token_hex` blob per save).
- **`session_load(save_id)`** — read the file, `session = load_game(document)` (`persistence.py:160`); missing file → tool error, malformed → `ContentValidationError`, newer-engine → `SaveVersionError`. No `adventure_id` needed — the adventure is embedded in the save (`persistence.py:83`). **Re-register any listeners/action policies after load** (`load_game` does not restore them; determinism guide). On a load, `observe` is called cold and ships a bounded event tail so the skill can recap.

A **lock** returns here (deferred in Phase 0): `GameSession` is not thread-safe by contract, and Phase 1 has a real multi-tool lifecycle. A single `asyncio`/threading lock around session mutation is safety insurance for the single-client stdio server.

## Work items

### 1. The native adventure bundle — `content.py` (rewritten) + prose sidecar

Retire Phase 0's throwaway two-cell fixture. Author one small native adventure that supports every scripted beat, plus its prose sidecar.

- **The adventure** (`server/src/osrlib_referee_mcp/adventures/…` or a `content.py` module — pinned during implementation): one `Adventure` (`crawl/adventure.py:46`) with one `TownSpec` (`travel_turns={dungeon_id: 2}` for the return beat, `crawl/adventure.py:43`), one `DungeonSpec` (`crawl/dungeon.py:555`), one `LevelSpec` (`crawl/dungeon.py:477`) — **single level, no `TransitionSpec`**. Geometry ~6×3 with a corridor path so "exploration" is real:
  - `entrance=(0,0)` (de-facto required — validation fails if no level has one, `crawl/adventure.py:117-118`), with a clear walk-back path to it (for `TravelToTown`).
  - `edges`: OPEN edges forming entrance → trap room → encounter room A → encounter room B, authored through a small `_open`/`_door` helper via `edge_key()` so edge ownership (a south/east passage is stored as the neighbour's `north`/`west`, `crawl/dungeon.py:118-137`) is never hand-miscomputed. Absent key = wall. Optionally one `DoorSpec` (stuck or locked) for the door beat. **The return path routes back through already-cleared keyed areas** — the *victorious* encounter room A and the sprung trap room — so the delve exercises a *keyed-area revisit* (the beat that forces `bx-referee` to re-read a location while osrlib-referee re-reads nothing, work item 9) **without re-triggering a fight**. This is the reason for the fight/flee role assignment below: only a *defeated* encounter is marked resolved (`end_encounter` appends to `resolved_encounters` only when `all_defeated`, `crawl/encounter.py:746-747`), and only a resolved area short-circuits the keyed-encounter check on re-entry (`crawl/exploration.py:840`). Re-entering a *fled* area would spawn a fresh `stance=ATTACKS` battle; a sprung trap will not re-spring (`crawl/exploration.py:684`).
  - **Trap area** — `AreaSpec(id="…", cells=(…), trap=TrapSpec(kind="room", trigger="enter", effect=TrapEffect(damage_dice="1d8")))`.
  - **Two encounter areas with distinct monster types** — the measurement needs ≥2 distinct fights (work item 9), so author two keyed encounters, e.g. **A** `KeyedEncounter(monsters=(KeyedMonster(template_id="skeleton", count_fixed=3),), stance=ATTACKS)` and **B** `KeyedEncounter(monsters=(KeyedMonster(template_id="giant_rat", count_fixed=4),), stance=ATTACKS)`. Distinct types are deliberate: they make `bx-referee` pay a *second* SRD monster-page lookup while osrlib-referee pays ~0 marginal (the stats ride the encounter events). Both `skeleton` (10 XP) and `giant_rat` (5 XP) resolve against the shipped 233-monster catalog (`data/monsters.json`, catalog `.get` `core/monsters.py:425`) with **no Phase-2 change** — only custom/unique monsters need injection. `stance=ATTACKS` on each pins the fights deterministic. **The scripted delve fights encounter A (the nearer room) to victory — the spec's "fight" beat — and flees encounter B (the deeper room) — the "flee" beat.** This role assignment is load-bearing (see the edges bullet): A is on the walk-back path, so it must be *resolved* (fought to victory) to re-enter cleanly; B is the deepest area and is never re-entered after the flee. Note the asymmetry this puts on the seed lock: fleeing is mechanically deterministic (all-retreat always opens pursuit), but *winning* A depends on favorable attack/damage draws with no PC dropping. So make encounter A **trivially winnable by content** — few, weak monsters (the `skeleton` ×3 is a starting point; reduce or weaken if a clean sweep proves seed-fragile) — rather than hinging A's victory on the chosen seed. The seed-lock (determinism lever #2) then carries only the trap spring and B's clean escape, keeping the golden test robust instead of brittle.
  - **Optional treasure** — a `FeatureSpec(kind="treasure_cache", …)` (`crawl/dungeon.py:364-385`) the delve *may* grab via `TakeTreasure` to exercise the path, but the core beats do not require it.
  - `WanderingSpec(chance_in_six=0)` on the level (`tui_crawler/content.py:109`) so no random wandering perturbs the scripted run — both fights are keyed and pinned, not wandering-driven.
  - Validate at construction with `validate_adventure(adv, load_monsters(), load_equipment())` (`crawl/adventure.py:94`) — a test asserts it passes.
- **The prose sidecar** — a committed data file (JSON or Python literal, pinned in impl) keyed by `AreaSpec.id`: `{area_id: {read_aloud: str, referee_notes: str}}`, original CC0 text for each keyed area (`entrance`, trap room, both encounter rooms, and the town). Loaded by the server and served by `prose(area_id)`.
- **The chosen session seed.** Record the master session seed at which the exact scripted command prefix (including the `LightSource` attempts, per determinism lever #2) springs the trap, lets encounter A be fought to victory, and yields a clean flee-escape from encounter B; a golden test (work item 8) pins seed + sequence. This session seed is **distinct from** the frozen pregen-roster creation seed (work item 5) — re-tuning the delve seed must never re-roll the party's stats.
- Content sharp edges to honor: `KeyedMonster` needs exactly one of `count_fixed`/`count_dice` (`crawl/dungeon.py:414-418`); feature id `"pile"` is reserved (`crawl/adventure.py:126-129`); area/feature ids unique per level; all specs are frozen pydantic (build at construction).

### 2. `execute` over `AnyCommand` + `list_commands` — `server.py`

- Retype `execute`'s argument from `dict` to `AnyCommand`; keep the per-element dump and the `dict[str, object]` return annotation. Run the FastMCP input-union spike (see the `execute` design above) *first* in this work item and record the verdict; if FastMCP cannot generate the discriminated input schema, fall back to `dict` + surface the union another way, and note it for the measurement.
- **Unknown `command_type` becomes a validation error, and Phase 0's `unknown_command_type` result branch is deleted.** Once the argument is the typed `AnyCommand` union, a payload with an unknown `command_type` fails discriminated-union validation at the FastMCP/pydantic boundary *before* the handler runs — so it is a tool error, not a reachable in-handler result field. Per greenfield discipline, remove the Phase-0 `parse_command(...) is None` → structured-result branch rather than leaving dead accommodation code. (If the FastMCP spike forces the `dict` fallback, the unknown-`command_type` case returns as a tool error mapped in work item 6, not a result field — pinned there.)
- Add `list_commands(mode?)` — `[c.model_fields["command_type"].default for c in ALL_COMMAND_CLASSES if mode in c.allowed_modes]`, splitting player-intent from authorial commands. This is the runtime, mode-scoped menu the standing union schema cannot provide (mode-gating is a runtime precheck, not a schema pruner).
- Add `list_adventures()` — a trivial read of the server's native adventure registry.
- Wrap session mutation in the lock.

### 3. `observe` — the scoped projection

Implement the projection schema above as a hand-built function reading live `GameSession` attributes (never `session_state()`). Cover the corridor fallback (`area_at()` → `None`), the referee un-masking of the three player-masked fields, the warm-vs-cold event handling, and the current-area cell bound. A test asserts the projection's shape and that it never contains the whole adventure or the full event log.

### 4. `prose` — the sidecar server

Load the sidecar at server start; `prose(area_id)` returns `{read_aloud, referee_notes}` or a structured not-found result for an unknown id. Trivial, but pin the not-found contract (result, not error — an unknown area id is a content bug the skill should surface, not a stack trace).

### 5. Session lifecycle + durable saves + the party surface

- Implement `session_new`/`session_load`/`session_save` per the contracts above, with the on-disk layout `~/osr-games/<game>/adventures/<adventure-name>/<save_id>.json`. The game-root is resolved from configuration/environment with the `~/osr-games` default; **never** the plugin cache.
- The internal seeded party builder: a fixed pregen roster (composition pinned in impl — e.g. a fighter + a thief + a cleric, no dwarf so the trap seed-lock holds, and no infravision so the `LightSource` beat is exercised) built via `create_character` → `party_to_document`. **The roster is built from its own fixed creation seed, frozen as a committed `party_document`, independent of the tunable session seed.** Character-creation RNG is a separate stream from session RNG (`core/character.py:83`, `CHARACTER_CREATION_STREAM`), and the `party_document` freezes finished `Character` models — so tuning the trap/flee session seed (work item 1) never re-rolls party stats. Phase 1 ships the frozen document; `session_new` feeds it to `GameSession.new` and does not re-generate the party.
- Multiple named saves per adventure are allowed (distinct `save_id` stems); the play/session skill chooses the slot. A human-readable session journal (`SESSION.md` role) alongside the opaque save is optional in Phase 1 and, if included, is a convenience for recaps, not canonical state.

### 6. The `OsrlibError` → tool-error map

Map at the MCP boundary, mirroring the FastAPI status map (`examples/fastapi_crawler/app.py`):

| Signal | Boundary treatment |
|---|---|
| `result.accepted is False` (+ `rejections[].code`) | tool **result** (in-fiction feedback; no draws, no clock, no log entry) |
| `ContentValidationError` (bad party doc / malformed save / bad content) | tool **error**, surfaced as a clean message |
| `SaveVersionError` (save from a newer engine) | tool **error** — "this save is from a newer engine; upgrade" |
| `ReplayVersionError` | tool **error** (only if replay is implemented — it is not, in Phase 1) |
| unknown `command_type` | tool **error** — with the typed `AnyCommand` argument this is a union-validation failure at the boundary (see work item 2); Phase 0's structured-result branch is removed |
| unknown `save_id`/`adventure_id` | tool **error** (server-defined, 404-analog) |
| stdlib `ValueError`/`TypeError` / any other `OsrlibError` | tool **error** (server-bug bucket) |

Full `OsrlibError` subtree today: base `OsrlibError` + `ContentValidationError`, `SaveVersionError`, `ReplayVersionError` (`errors.py:18-57`). Key the taxonomy on the base and branch on the three concrete subclasses. The one-way rule the skill honors: **rejections stay results; `OsrlibError`s become errors.**

### 7. The `play` skill + the `constitution`

- **`constitution.md`** — the behavioral contract, adapted from `bx-referee`'s (`skills/referee/references/constitution.md`), keeping its OSE voice and information discipline while inverting the rules-authority role:
  - **Keep verbatim:** the deadly-by-design preamble; player agency (never narrate character actions/decisions, never auto-pick, never offer action menus during play); information discipline (never reveal target numbers or monster stats before combat — strip referee-visibility data before narrating, since the `observe` projection carries it and the fiction must not leak it); neutral adjudication (no softening, no escalating, no fudging).
  - **Invert / strengthen:** the LLM computes **nothing** — no THAC0, no target numbers, no HP arithmetic (`bx-referee`'s combat skill instructs the LLM *how to compute*; here the engine's `ResolveBattleRound` does). "Never invent content" becomes "**never invent a roll or a stat**"; the source of truth is the `observe` projection and `prose` sidecar, not a module PDF.
  - **Add (no `bx-referee` ancestor):** no silent state changes — every `execute` is the audit trail; no roll-shopping — a chance outcome is rolled by the engine from the seeded stream (via `RollDice` for freeform chance, `crawl/session.py:961-968`, `DiceRolledEvent` code `adjudication.dice_rolled`), never invented, never out-of-band, never re-rolled for a better number (the roll log makes it visible); a *judgment* (the guard believes the bluff) is a declared `SetFlag` ruling.
  - **Drop:** "don't re-read SRD pages already in context" — moot; there are no SRD pages.
- **The `play` skill (`SKILL.md`)** — one loop that owns exploration, encounter, and battle lifecycles (no separate combat skill re-deriving anything). It maps player intent to commands via `list_commands(mode)`, calls `execute`, narrates from the returned event fields (via `osrlib.messages.format_message` for default lines, never inventing outcomes), reads `observe` for current state, and calls `prose(area_id)` on entering a new area. `allowed-tools` pre-approves the exact tool names (`mcp__plugin_osrlib-referee_osrlib__execute`, `…__observe`, `…__prose`, the lifecycle tools, `…__list_commands`) — confirmed against the live exposed names, as Phase 0 did for `execute`.
  - Play-skill guardrails from the engine's sharp edges: emit only `close`/`retreat`/`fighting_withdrawal` battle moves (the `withdraw` enum validates but is a silent no-op, `crawl/battle.py:1177-1219`); re-read `session.mode` after every `MoveParty` (a single move can jump EXPLORING → BATTLE); `LightSource` before any Search/PickLock in the dark; `MoveParty` back to the entrance cell before `TravelToTown`.

### 8. Tests — the ladder plus the golden delve

Pytest rungs, all runnable in CI without Claude Code:

- **Adventure validation** — `validate_adventure(adv, load_monsters(), load_equipment())` passes; both `skeleton` and `giant_rat` resolve against the shipped catalog.
- **The scripted delve, in-process** — drive the full command sequence against a fresh seeded `GameSession` (the tool functions are plain callables) and assert each beat's events: `EnterDungeon` → EXPLORING; the trap-room entry emits the trap event; entering encounter A opens the battle (stance-pinned) and `ResolveBattleRound` fights it to **victory** → EXPLORING; entering encounter B opens its battle; the all-retreat round opens pursuit and the escape returns to EXPLORING; **the walk-back re-enters resolved room A and the sprung trap room and asserts neither re-opens a battle or re-springs** (the invariant the fight/flee role assignment rests on, work item 1); `TravelToTown` → TOWN.
- **The seed-locked trap golden** — pin the exact seed + command sequence and assert the trap **springs** on the scripted entry (guards the determinism lever against any change to the sequence).
- **`observe` projection** — assert the field set, the corridor fallback, referee un-masking (monster HP present, secret door unmasked), and that the payload contains neither the whole adventure nor the full event log.
- **Save round-trip** — `save_game(load_game(document)) == document` (byte-identity; determinism guide), and that a `RollDice` before the save reproduces on reload (the `adjudication` stream survives).
- **The error map** — a malformed save raises `ContentValidationError` → tool error; an in-fiction rejection is a normal result.
- **The MCP boundary** — the Phase-0 in-memory client rung, extended to `observe`/`prose`/lifecycle, confirming FastMCP serialization of the union input and the projection output.

**The manual gate:** inside `claude --plugin-dir .`, play the scripted delve through the `play` skill end-to-end, confirming the tool names resolve and the fiction reads from events.

### 9. The token measurement — methodology and verdict

Treat this like Phase 0 treated the packaging spike: an in-repo methodology and a **recorded verdict**, sequenced *after* the delve is playable.

- **Author the matched `bx-referee` baseline.** `bx-referee` runs from a keyed-location module doc, not a Python `Adventure` — so the same barrow must be authored in `bx-referee`'s format too (a small module + `LOCATIONS.md` keyed entries). Operationalize "the same delve": **identical player inputs, verbatim, on both sides; the same beats fired** (if the osrlib trap is seed-locked to spring, the `bx-referee` run must also spring it, or a 6-beat delve is being compared to a 5-beat one). Same model and settings.
- **Separate what genuinely compounds from what is amortized — this is the honest core of the measurement.** Do *not* frame the ~4,000-token combat rules load as "re-paid every fight": within one context window `bx-referee`'s Article V.2 ("don't re-read SRD pages already in context") makes it a **one-time** cost, and re-paying it is a cross-compaction phenomenon this delve does not force. The measurement therefore reports three distinct components rather than one headline:
  1. **One-time loads osrlib-referee eliminates outright** — the ~4k combat rules setup (`Combat.md` + `Combat_Tables.md` + `Morale…`) and the ~1.9–3.3k SRD submap, which osrlib-referee never loads at all. Real, but count them as one-time, not per-fight.
  2. **The genuinely recurring, non-cacheable sink: per-round combat re-derivation.** `bx-referee` computes THAC0 / target number / modifiers *in prose* on every attack of every round (`skills/combat/SKILL.md:110-117`); this cannot be cached the way a file read can, so it scales with rounds × fights. osrlib-referee's `ResolveBattleRound` (plus the default monster-action policy) drives it to ~0 model tokens — the LLM declares only party actions. **This is the compounding headline.**
  3. **Per-distinct-monster lookups.** Each new monster type costs `bx-referee` a fresh monster-page read (~300 tokens) and, worst case, the ~3.3k monster submap; osrlib-referee pays ~0 marginal (stats ride the encounter events). The delve's **two distinct monster types** (work item 1) surface this; the **keyed-area revisit** (work item 1) surfaces `bx-referee`'s re-read-on-revisit while osrlib-referee re-reads nothing.
- **Count both sides honestly, with one tokenizer.** Capture both full transcripts (system prompt + tool schemas + every turn) and tokenize with the same method (Anthropic `count_tokens` over the captured messages, or Claude Code session usage logs) — never a `chars÷4` estimate against a real count. For osrlib-referee, **count the standing costs too, or the comparison is rigged**: the `AnyCommand` union schema advertised every turn (captured directly from `TypeAdapter(AnyCommand).json_schema()`), the `observe` projection shipped each turn, and — named for completeness though the union dominates — the output schemas of `observe`/`prose`/the lifecycle tools/`list_commands`, all standing per-turn. Net these against the savings. Break the totals into narration vs mechanics/state so the thesis — mechanical/state overhead collapses while the narration budget is preserved — is *visible*, not a single aggregate. **Report per-fight marginal cost explicitly** (component 2 above) so the compounding win is legible even though the one-time rules load (component 1) is amortized within the window.
- State-file re-reads rank as a **minor** sink (`bx-referee` updates via targeted `Edit` deltas, not full re-emission — do not inflate this).
- **Honesty about the baseline's nature:** the osrlib-referee side is a seed-deterministic, replayable trajectory; the `bx-referee` side rolls in prose and cannot be replayed identically. The measurement is therefore **one honest sample per side**, not a replayable both-sides eval — that is Phase 4. Say so; do not overclaim reproducibility for the baseline.
- **Record the verdict** — the per-turn and cumulative numbers, the category split, and the net-of-standing-costs conclusion — in this plan and the README, as Phase 0 recorded its packaging verdict.

### 10. README and docs touch-ups

- README: how to start a game and play the scripted delve; the game-directory convention (`~/osr-games/…`); the Python-≥3.14 / `uv`-on-PATH prerequisites (carried from Phase 0).
- Record the measurement verdict (work item 9) in the README.
- Confirm the prose sidecar's CC0 status and that only original/openly-licensed content is committed.

## Sequencing

The build order front-loads the engine wiring and gates the measurement on a working delve:

1. **Work item 1 (adventure + sidecar)** first — everything tests against it.
2. **Work items 2–6 (the four tools + error map)** — `execute` upgrade and the FastMCP union spike, then `observe`, `prose`, lifecycle, error map. Test rungs (work item 8) alongside, test-first where practical.
3. **Work item 7 (skill + constitution)** once the tools are green in isolation.
4. **Milestone A — playable:** the manual Claude Code play-through of the scripted delve succeeds.
5. **Tune `observe` scope** from that real play (the spec pins this as empirical in Phase 1) — adjust the projection field set against round-trip behavior.
6. **Milestone B — measured:** author the `bx-referee` baseline, run both sides, record the verdict (work item 9).
7. **Work item 10 (README/docs)** closes out.

Keep it **one phase** — the spec defines Phase 1 as a single coherent thesis. If the rubber-duck finds it too large, splitting into 1a (playable) / 1b (measured) is a plan-amendment conversation on the same branch, not a preemptive decision.

## Definition of done

- The native adventure validates and the scripted delve is **playable end-to-end** through the MCP boundary inside Claude Code — enter, explore, spring the trap, fight, flee, return — with the LLM narrating only from events and `prose`, never computing a stat or inventing a roll.
- The four core tools are implemented to their pinned contracts: `execute` over `AnyCommand`, `observe` as the scoped referee projection, `prose` from the sidecar, and the `session_new`/`session_load`/`session_save` lifecycle with durable saves in the game directory.
- The test ladder is green in CI (adventure validation, in-process delve, seed-locked trap golden, `observe` shape, save round-trip, error map, MCP boundary).
- The `constitution` and `play` skill enforce the engine-as-truth discipline, and the exposed tool names match the skill's `allowed-tools`.
- **The token measurement is run and its verdict recorded** — the mechanical/state overhead is demonstrably collapsed after netting osrlib-referee's standing costs (the union schema and the `observe` projection), with the narration budget preserved. The verdict reports the recurring per-round/per-fight sink (combat re-derivation, per-distinct-monster lookups) separately from the one-time SRD/rules loads, so the compounding win is legible rather than conflated with an amortized cost.

## Decisions pinned

- **`execute` takes the real `AnyCommand` union** (not Phase 0's raw `dict`), because the union schema's standing per-turn cost is exactly what the spec pins Phase 1 to measure; hiding it behind a `dict` would measure a different design. `list_commands(mode)` supplies the runtime menu the schema cannot prune. A FastMCP input-union spike de-risks the retyping first.
- **`observe` is a hand-built scoped projection from live `GameSession` attributes**, never `session_state()` and never the raw `RefereeView`. It ships only the current area and scene, un-masks exactly three referee-visibility fields (monster HP, undiscovered secret doors, effect durations), and does not re-ship events on warm calls. Its exact field set is tuned empirically from Milestone-A play.
- **`prose(area_id)` serves the out-of-band sidecar**; `observe` carries the live mechanical scene. The skill calls `prose` on entering a new area and `observe` every turn.
- **The fights are deterministic via `stance=ATTACKS`** (pins the reaction roll off, opens battle on entry — so `ResolveBattleRound` drives combat directly, never `EngageBattle`); **the trap is deterministic via a chosen session seed** (no content flag forces a 2-in-6 spring; the same `EXPLORATION_STREAM` also carries the variable `LightSource` tinder rolls, so the whole command prefix is pinned) with the trap room un-searched by the script; the flee-escape is seed-checked. A golden test pins seed + sequence. This session seed is distinct from the frozen pregen-roster creation seed.
- **The demo trap is a no-save 1d8 room trap**, not a save-or-die trap (which would one-shot a PC).
- **Standard SRD monsters (e.g. `skeleton`) resolve against the shipped catalog with no engine change** — the injectable-catalog work is Phase 2 and only unique/custom monsters need it.
- **Saves are the full `save_game` document written verbatim** to `~/osr-games/<game>/adventures/<name>/<save_id>.json`; `save_id` is the server's chosen filename stem. osrlib assigns no id and does no file I/O.
- **The party is built internally from a fixed seeded pregen roster** (`create_character` → `party_to_document`), frozen as a committed `party_document` built from its own creation seed independent of the tunable session seed; the player-facing character tool, economy, and level-up UI are Phase 3. The roster has no dwarf (trap seed-lock) and no infravision (exercises the `LightSource` beat).
- **Rejections are tool results; `OsrlibError`s are tool errors** — the FastAPI status map, adapted to MCP.
- **The constitution keeps `bx-referee`'s voice and information discipline but inverts its rules-authority role** — the LLM computes nothing; the engine owns every mechanic; freeform chance is an engine `RollDice`, freeform judgment a `SetFlag` ruling.
- **The measurement counts osrlib-referee's standing costs** (union schema + per-turn `observe`) as line items, uses one tokenizer across both sides, and includes ≥2 fights + a revisit to surface compounding sinks. It is one honest sample per side, not a replayable both-sides eval (Phase 4).
- **One phase, two internal milestones** (playable → measured); no preemptive 1a/1b split.

## Risks and open questions

- **FastMCP and the 45-variant discriminated input union.** Untested that FastMCP generates a clean discriminated input schema and round-trips a command as a typed arg. De-risked by a spike first in work item 2; fallback is `dict` + the union surfaced via another channel (recorded in the measurement).
- **`observe` scope tuning.** Too little and the LLM round-trips for more; too much and the token win erodes. The spec pins this as empirical — Milestone A plays, then the projection is tuned, then measured. The field set in this plan is the starting point, not the final word.
- **Scripted-beat determinism is seed-coupled.** The trap spring and the flee-escape depend on a chosen seed plus an exact command sequence; any change to the sequence can move them. The golden test is the guard, but it means the demo script is rigid — an acceptable cost for an honest engine-driven demonstration (versus faking the beats through the escape hatch).
- **The measurement's `bx-referee` baseline is real work and asymmetric.** Authoring the same barrow in `bx-referee`'s module format, matching the beats, and accepting that `bx-referee` is a single non-replayable sample are all load-bearing for a fair comparison. Under-scoping this is the most likely way the definition of done softens into hand-waving.
- **Open: does the measurement land in the `phase-1-impl` PR or as a follow-on manual gate?** The delve-playable work and the measurement are separable (Milestones A and B). Decide during implementation whether Milestone B ships in the same PR or as a recorded follow-on, and make the DoD unambiguous either way. Leaning: same PR, since the thesis is the point of the phase and the DoD names the measurement.
- **Prose sidecar format.** JSON vs Python literal, and where it lives relative to the adventure module, is pinned in implementation (work item 1) — a low-stakes call, flagged so it is decided, not defaulted.
