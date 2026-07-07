# osrlib-referee — spec and roadmap

This is the decision-complete source of truth for the project (osrlib's `docs/spec.md` plays the same role for the engine). Read it before implementation; build in phase order.

Working title for the new project: **`osrlib-referee`** (changeable). This spec leaves `bx-referee` untouched and stands up a sibling that inverts its architecture: the deterministic `osrlib` engine owns all mechanics and state, an MCP server holds the live `GameSession`, and thin skills keep the LLM on narration and adjudication.

## The milestone

A playable B/X dungeon crawl, driven from Claude Code, where every roll, stat, and state transition is computed by `osrlib` behind an MCP server, and the LLM spends its tokens on fiction — not on reloading SRD tables, re-deriving THAC0, or re-emitting Markdown state files. Success is measured, not asserted: a scripted delve (enter, explore, spring a trap, fight, flee, return) played both ways, with a token count showing the mechanical/state overhead collapse and the narration budget preserved.

## Why this is worth doing

Three payoffs, in priority order:

1. **Token efficiency.** The `bx-referee` port map shows the current design spends its tokens re-loading reference text to do arithmetic in prose: a single combat's setup reads `Combat.md` + `Combat_Tables.md` + `Morale…` + a monster page — roughly 4,000 tokens *before a die is rolled* — and pays it again every fight. Add per-visit module PDF re-reads, the three-hop SRD lookup tax, and state-file re-emission. All of that is MECHANICS and STATE, and `osrlib` owns all of it deterministically. What remains — narrating rooms, voicing NPCs, adjudicating "I search the tapestry" — is exactly what we *want* tokens spent on.

2. **Correctness.** No arithmetic drift, no forgotten spell slot, no lost initiative order when a session compacts. `osrlib` is the single source of truth; the LLM cannot miscount HP because it never counts HP. The current design's weakest state — exploration progress (which rooms searched, which secret doors found) — is "weak/implicit, lives in conversation history" today and becomes authoritative for free (`DungeonState`: explored cells, door overlays, sprung traps, emptied caches).

3. **Eval-ability.** `osrlib`'s determinism contract (seed + accepted command log ⇒ byte-identical game) means a play session is a reproducible trajectory. That unlocks regression-testing a prompt change by replaying the same seeds, and diffing two models on identical dungeons — a testing story `bx-referee` structurally cannot have.

This is not an incremental change to `bx-referee`. It **inverts its philosophy**: today the LLM is the rules authority; here the engine is, and the LLM is the narrator plus the adjudicator of freeform intent. Both models are legitimate; this plan builds the second alongside the first.

## Architecture

### The three layers

| Layer | Owner | Responsibility |
|---|---|---|
| Mechanics + state | `osrlib` `GameSession` (in the MCP server, in-process) | Dice, THAC0/attacks, saves, morale, XP, encumbrance, initiative, surprise/reaction/distance, evasion, resources, level-up, and all persistent state (party, position, effects, flags, explored map, doors, piles). |
| Narration + adjudication | LLM skills | Deliver authored prose, voice NPCs, pace scenes, and translate freeform player intent into engine commands (or into authorial commands when intent falls outside the content model). |
| Content | An **adventure bundle** (compiled `Adventure` spec + prose sidecar + manifest) loaded by the server | The map, keyed areas, encounters, traps, treasure — plus the authored read-aloud prose the engine has no place for. |

The `encounter → combat` handoff block is the *only* machine-readable contract in `bx-referee` today. This architecture generalizes that one good idea into the whole interface: the engine owns the entire MECHANICS + STATE columns and emits structured events; the LLM is restricted to NARRATION over CONTENT.

### The command/observation loop

The engine's shape is already the agent loop's shape (osrlib's own `llm-referees.md` says so): typed commands in, typed events out, a full-knowledge view to observe. The play loop, in OSE terms — player intent in, engine events out, fiction around them:

```
player describes action
  → skill maps intent to one or more osrlib commands (mode-gated menu)
  → MCP execute(command)
  → engine returns CommandResult{accepted, rejections, events}
  → skill narrates from the event codes + fields (never invents outcomes)
  → skill reads a scoped observation when it needs current state
```

A rejection is *feedback*, not an error (`accepted:false` + a machine code like `session.command.wrong_mode`), so an illegal command costs nothing and the model self-corrects — the same rejection discipline the FastAPI example leans on.

### The MCP tool surface (recommended)

Deliberately small — the union does the heavy lifting:

- **`execute(command)`** — one tool taking the `AnyCommand` discriminated union (osrlib ships it: `TypeAdapter(AnyCommand).json_schema()`, keyed on `command_type`, 45 members, validation free via `parse_command`). Returns `{accepted, rejections, events}`, dumping each rejection and event individually (a `model_dump` on the `CommandResult` container drops event subclass fields, since `events` is base-`Event`-typed). Each event carries its `code` and typed `fields` (`event.model_dump()`), and `format_message(event)` renders a default English line — `format_message` returns only that line, not a combined `{code, fields, default_line}` dict, which a consumer assembles from the event if it wants one. Events ride unfiltered: the player-visibility filter the FastAPI example applies at its wire is a player-client concern, not this trusted-referee server's. One union tool is far more compact than 45 separate tool definitions — but be honest: the union schema inlines all 45 variants and is advertised in full every turn regardless of mode (mode-gating is a *runtime* precheck inside `execute`, not a schema pruner). That standing schema is a fixed context cost to **measure in Phase 1**, not a saving. The narrate path reads events straight off this result — the model does not need a separate fetch.
- **`observe(scope="current")`** — a pure current-state snapshot. **Not** the raw `RefereeView`: that is `session_state(include_event_log=True)` minus RNG/seed — the entire save document *including the full unbounded event log, the always-on command log, and the whole adventure spec*. Pulling that every turn would erase the token win. Instead the server computes a **scoped referee projection**: `mode`, the mode-legal command names, the current area (id, cells, visible edges/doors), party (HP, effects, position, marching order), any active encounter/battle with real monster HP, and session flags. It does *not* re-ship events — those come from `execute`'s envelope; `observe` returns events only when called cold (e.g. right after `session_load`). This scoped projection is the single most important server-side design decision.
- **`prose(area_id)`** — returns the authored sidecar for an area: `{read_aloud, referee_notes}`. This is how the LLM narrates from the module's real text; it bridges the content gap osrlib leaves open (the engine's `AreaSpec.description` is one opaque, engine-ignored string).
- **Lifecycle:** `session_new(party_document, adventure_id, seed?)`, `session_load(save_id)`, `session_save()`. Note PC creation is *not* a command — there is no character-creation entry in `AnyCommand`; `create_character` runs before `GameSession.new`. So the server also needs a small **pre-session build surface** (`create_character` + `party_to_document`) that yields the `party_document` fed to `session_new`. The server holds one `GameSession` per game in-process behind a lock (`GameSession` is not thread-safe by contract; for a single-client stdio server the lock is safety insurance rather than a concurrency necessity). Saves are **durably persisted to the user's game directory**, not held in memory — see cross-cutting concerns below.
- **Helpers (optional):** `list_adventures()`, `list_commands(mode?)` — the latter gives the model a mode-scoped menu to steer command choice, since the schema itself can't be pruned by mode.

Because the referee agent is *trusted* (unlike a wire client), it may see referee-visibility data — but for tokens, `observe` still scopes hard rather than dumping. This is the one place the plan diverges from both shipped examples: not the player whitelist (too little — the referee needs monster HP and hidden rolls), not the raw referee view (too much — the whole log). A purpose-built middle projection.

### The authorial escape hatch

B/X is freeform; the content model is finite. The reconciliation is already in osrlib's command union — the referee/authorial commands, legal in every mode:

- `SetFlag` — record a durable fact ("the lever was pulled") that later narration and listeners react to.
- `SpawnMonsters` / `SpawnNpcParty` — open an encounter the module didn't key, at a chosen distance.
- `GrantItem` / `GrantCoins` / `AwardXP` — place a reward the LLM improvised.
- `SetDoorState` — reveal, lock, or wedge any door anywhere.
- `PlaceParty` / `AdvanceTime` — teleport the party, advance the clock.

So when a player does something the content model can't express (solves a puzzle, tricks an NPC, triggers a bespoke trap), the loop is: **LLM adjudicates the outcome in fiction → commits it to authoritative state via an authorial command → the engine's determinism and save/replay stay intact.** Freeform play stays flexible; canonical state stays deterministic. This is what makes the whole thing evaluable rather than just cheaper.

**Adjudication discipline — where the dice come from.** "LLM adjudicates the outcome" carries a guardrail. Every outcome must enter the trajectory as a **logged command** — a committed `SetFlag` re-executes byte-for-byte on replay, so a referee *ruling* is captured in the reproducible record, not invented-and-lost (the model's decisions were never *inside* the determinism guarantee, which promises only that the engine reproduces a logged command sequence; committing them as commands folds them into it). Beyond that, a *judgment* and a roll of the *dice* are handled differently: a judgment ("the guard believes the bluff") is legitimately the model's call, but anything that represents **chance** must be rolled by the engine from the seeded stream — so its value is grounded in an auditable event and re-derivable from the seed, never a number the model invented (ungrounded, unauditable, fudgeable) and never a die rolled **out-of-band** by a side tool (whose result sits outside the seeded streams, so it can't be held fixed when the same seed is replayed against a changed prompt or a different model — the exact comparison the eval story needs).

osrlib 1.1.0 added exactly this (issue [osrlib-python#22](https://github.com/mmacy/osrlib-python/issues/22)): **`RollDice`** (`command_type: "roll_dice"`) — an authorial command, legal in every mode, that rolls an arbitrary dice `expression` through the session's dedicated **`adjudication`** RNG stream, is accepted and logged like any command, and emits a referee-visibility **`DiceRolledEvent`** (`dice_rolled`) carrying the expression, total, and individual dice. A malformed expression is rejected at construction, so it consumes no RNG. The dedicated stream is the point: an ad-hoc referee roll never perturbs a keyed mechanic's draw sequence, so keyed content stays byte-stable on replay. It is the same shape `SpawnMonsters` already uses when it rolls its count — the authorial surface now *rolls* as well as *commits*. (Only `RollDice` landed; dedicated `Check`/`Save` commands with pass/fail semantics remain an optional future addition — until then an ability check or save is a `RollDice` plus the referee reading the result against the target.) Constitution guardrails still bind: no invented roll results, no out-of-band roller, no roll-shopping (re-rolling the seeded draw for a better number — the roll log makes it visible).

## The content problem (the honest part)

This is the hardest design decision and it dictates the sequencing. The content-fit assessment is unambiguous about what fits and what doesn't.

**Fits cleanly** (osrlib's mechanical layer): the 10-ft-square map grid (`LevelSpec` + `edges`), keyed rooms (`AreaSpec.cells`), doors/secret/locked (`Edge`+`DoorSpec`), stairs/trapdoors/chutes (`TransitionSpec`), fixed encounters with SRD monsters (`KeyedEncounter`+`KeyedMonster`), structured traps (`TrapSpec`/`TrapEffect` — darts, pits, save-or-die, conditions, slides), and treasure both hand-placed (`FeatureSpec`) and generated (`AreaTreasureSpec`).

**Sits outside the engine** (three real gaps):

1. **Authored read-aloud prose.** One `AreaSpec.description: str` per area, display-only, engine-ignored, with no player/referee split. A published key (boxed text + DM notes + tactics + development) collapses into one opaque blob. → **Solution: the prose sidecar**, keyed by area id, is a first-class part of the adventure bundle and served by `prose(area_id)`. Prose lives out-of-band by design, not by accident.

2. **Custom / unique monsters and items — where the engine's frozen catalog bites.** `KeyedMonster.template_id` must resolve against the monster catalog. It fails first at session start — `GameSession.new` calls `validate_adventure(adventure, load_monsters(), load_equipment())` — so an adventure module's named boss or re-statted creature is rejected before play. `validate_adventure` *itself is already parameterized* on `(monsters, equipment)`; it's `.new` that hardcodes the *loader calls*. But fixing `.new` is not enough: template resolution against the shipped `@cache`d singleton loaders is duplicated across the play paths too — `GameSession.spawn` and `_handle_spawn_monsters` read `load_monsters()`, the keyed-encounter and wandering paths in `exploration.py` read it again, and equipment resolution (`load_equipment()`) is baked into the **`osrlib.core` layer** — `core/character.py`, `core/items.py`, `core/combat.py`, `core/treasure.py`, `core/npc.py` — where *no session is in scope at all* (and `core` cannot import `crawl`). A truly custom stat block would need a genuine upstream change making the catalogs session-owned and threaded through every spawn/handler site, plus an override layer for the core-layer equipment lookups — a **cross-cutting engine change** with its own spike, not a one-line param. → **Solution for Phase 2: reskin, don't inject.** A non-SRD creature is compiled to its **nearest SRD template** — stats and mechanical identity both (a module's "barrow wight" *is* an SRD `skeleton` to the engine) — with the substitution logged as an approximation; the referee narrates by appearance (constitution Article II.3), so neither name is spoken and the reskin is invisible in the fiction. This needs **no engine change and no behavioral skill change**, because a reskinned `template_id` resolves exactly like a native SRD one. The injectable-catalog engine change is **deferred to a future phase**, reached only when a module has a creature whose mechanics *are* the encounter and no SRD template approximates — those beats go to the authorial escape hatch until then. (Rejected alternatives: monkeypatching the `@cache`d loaders — fragile and global; a prose-driven monster-renaming layer over the SRD name — fragile scaffolding for little gain, since the engine surfaces monster names in player-visible events with no content field to override.)

3. **Puzzles, tricks, bespoke trap logic, organic maps, NPC roleplay.** No mechanical representation; inert prose (`description`, `TrapEffect.manual`, `FeatureSpec kind="custom"`) only. → **Solution: the authorial escape hatch above.** The LLM runs these in fiction and commits outcomes via `SetFlag`/`GrantItem`/`SetDoorState`. Non-grid maps get approximated to the grid at compile time (an explicit, logged fidelity loss).

**Authoring cost is real.** osrlib ships no adventure file format and no adventure loader — only SRD-catalog loaders. Content is built as pydantic models in Python, or as your-own JSON/YAML you deserialize with `Adventure.model_validate`. The heaviest single cost is the `edges` map: walls are the default, so every passage and door is enumerated as a canonical `"{x},{y}:{side}"` entry — a 20×20 level has hundreds of interior edges. For a 30–60-room adventure module this is substantial, error-prone hand-transcription, arguably heavier than transcribing the keyed content. This is why adventure-module ingestion is **Phase 2, not Phase 1** — we prove the architecture on native content first, then confront the transcription problem with eyes open.

**One honest note on the compile step's own token cost.** Compiling an adventure module (LLM reads the whole PDF, emits spec + prose) is itself expensive — but it is a *one-time* cost amortized over every future session of that module, versus `bx-referee`'s per-visit re-read. Net win, stated plainly rather than hidden.

## Where it should live

**Recommendation: a standalone repo (`~/repos/osrlib-referee`) that is simultaneously the Python MCP-server package and a valid Claude Code plugin.** Layout:

```
osrlib-referee/                      (git repo; also the plugin root)
├── .claude-plugin/plugin.json       (plugin manifest)
├── .mcp.json                        (launches the bundled server via ${CLAUDE_PLUGIN_ROOT})
├── skills/                          (referee, play, character, session … SKILL.md)
├── server/                          (the MCP server — a uv project)
│   ├── pyproject.toml               (depends on osrlib>=1, mcp SDK)
│   ├── uv.lock
│   └── src/osrlib_referee_mcp/…
├── adventures/                      (compiled adventure bundles: spec + prose sidecar + manifest)
├── docs/                            (this plan lands here; phase plans follow)
└── AGENTS.md                        (its own dev discipline, mirroring osrlib's)
```

Rationale:

- The server is a *real* Python package (deps: `osrlib` from PyPI, an MCP SDK), unlike `bx-referee`'s single-file PEP-723 scripts. It wants a `pyproject.toml`, `uv.lock`, tests, and CI. Wedging that into `osr-plugins/plugins/` — which has no Python packaging setup — is architecturally awkward.
- A sibling to `osrlib` benefits from the same discipline (phase plans, rubber-duck reviews, golden tests, tag-driven release) that AGENTS.md codifies. A standalone repo gives it room to have that.
- `bx-referee` stays pristine — it's a different repo entirely, no risk of collision.
- Distribution still works: `osr-plugins`'s `marketplace.json` can list it as an external plugin `source` (git URL), or it's installed directly with `claude --plugin-dir ~/repos/osrlib-referee`. Either way the `.mcp.json` + `${CLAUDE_PLUGIN_ROOT}` mechanism is identical.

**The alternative** — a new plugin folder inside `osr-plugins` (`plugins/osrlib-referee`) — is lower-friction for distribution (same marketplace) and still leaves `bx-referee` untouched, but forces a Python package to live among single-file-script plugins with nowhere clean for `pyproject.toml`/CI. **Decided (2026-07-05): the standalone repo.**

## Packaging: MCP server inside a plugin

Confirmed mechanics (verify exact field names against current Claude Code docs at build time):

- Declare the server in **`.mcp.json` at the plugin root** (not inside `.claude-plugin/`), under `mcpServers`, stdio transport. `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin dir for referencing bundled files.
- Tool names surface as `mcp__plugin_<plugin-name>_<server-key>__<tool>`; skills pre-approve them via `allowed-tools`.
- **The main packaging risk: `uv`/Python on PATH is not guaranteed** for an arbitrary user's machine, and stdio servers start synchronously with a short startup budget (tune via `MCP_TIMEOUT`). Mitigations, in order of preference: (a) `command: "uvx"` against the published `osrlib` + a published server package so uv fetches deps on first run; (b) `command: "uv", args: ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", …]`; (c) document a one-time `uv sync` install. Phase 0 decides this by testing on a clean machine profile.
- Requires Python ≥3.14 (osrlib's floor). Note this in the plugin README as a prerequisite.

## Cross-cutting concerns

Three things thread through every phase and must not be inherited by accident from the example front ends.

**Durable saves in the game directory.** The FastAPI example's save store is explicitly in-memory ("a deliberate simplification") — fine for a demo, fatal here. A plugin-bundled stdio server starts and stops with the Claude Code session, so an in-memory store loses the game between sessions and breaks the entire "continue an existing adventure, resume with a recap" value proposition. The server must **persist `save_game()` documents to disk in the user-chosen game directory** (the repo's established convention: `~/osr-games/…`, never the plugin cache), and `session_load(save_id)` reads them back. `save_id` maps to a file under `<game-root>/adventures/<name>/`. A human-readable session-metadata/journal file (the `SESSION.md` role) can live alongside the opaque save document for recaps and for the player to read; the save document is the canonical state, the journal is a convenience.

**Version handshake, migration, and error mapping.** osrlib stamps every document with `schema_version` and `engine_version` (`session.metadata`) and raises typed `OsrlibError`s — `ContentValidationError` (malformed content), `SaveVersionError` (a save newer than this engine), `ReplayVersionError`. When the bundled `osrlib` is upgraded, loading an older save runs the migration chain; a *newer* save raises `SaveVersionError`. The MCP boundary must map these deliberately, exactly as the FastAPI status map does: an in-fiction command **rejection** is a normal tool *result* (`accepted:false` + code), while an out-of-fiction `OsrlibError` is a tool *error* the skill surfaces to the player as "this save is from a newer engine" rather than a stack trace. Pin the bundled osrlib version and treat an upgrade as a migration event.

**Licensing.** (a) The project's own license: code, skills, prompts, docs, and compiled *original* content are dedicated to the public domain under **CC0 1.0 Universal** (`LICENSE`). `osrlib`, the engine, is likewise CC0, so there is no internal code/data license boundary to police. (b) **Adventure-module-compilation licensing is a real, separate constraint** — about third-party content, not this repo's own license. The OSE SRD is openly licensed, but most *published commercial adventure modules* are not. Compiling one into an adventure bundle — especially the prose sidecar with verbatim read-aloud text — and committing it to a repo is a copyright problem. Constraint: compiled bundles for non-open modules stay **local/private to the user's game directory**; only OGL/CC-licensed or original-authored modules ship in the repo. The compiler skill writes bundles into the game directory by default, not the plugin.

## Phased roadmap

Each phase ships as a plan then an implementation, both run through the create → rubber-duck → revise-until-solid loop (the osrlib AGENTS.md discipline).

**Phase 0 — scaffolding and the packaging spike.** Stand up the repo, the `server/` uv project (deps resolve, `osrlib` imports, `AnyCommand` schema generates), the plugin skeleton (`plugin.json`, `.mcp.json`, one no-op skill), CI (ruff/pytest), and — the real risk-retirement — **prove the plugin-bundled stdio server launches and a tool call round-trips inside Claude Code on a clean profile.** Definition of done: `execute(a trivial command)` works end-to-end through the MCP boundary. Decide the PATH/packaging option here.

**Phase 1 — prove the loop on native content.** No published module yet. Use a small osrlib-native `Adventure` as the content — the `tui_crawler` barrow is a good model, but it lives in osrlib's `examples/`, which the PyPI wheel does not ship, so copy or re-author the pattern rather than importing it. Build the server's four core tools (`execute`, `observe` scoped projection, `prose`, lifecycle) and a single `play` skill plus a `constitution`. Play a scripted delve: enter, explore, spring a trap, fight a keyed encounter, flee, return. **Then measure:** run the same delve through `bx-referee` and diff token counts. Definition of done: the delve is playable and the mechanical/state token overhead is demonstrably collapsed. This validates the entire thesis before we pay the content-ingestion tax.

**Phase 2 — the content bridge (SRD-only modules).** Scoped to content the OSE SRD can express, in two parts plus a demo. (This supersedes an earlier three-part framing that led with an injectable-catalog engine change; that change is deferred — see below and content gap #2. Full plan: [`docs/phase-2-plan.md`](phase-2-plan.md).)

- **The bundle format + loader.** An adventure bundle = a JSON `Adventure` spec (deserialized via `Adventure.model_validate`, self-validated by `GameSession.new`/`validate_adventure`, which reports every problem at once) + a prose sidecar keyed by area id + a manifest (id, license, and an `approximations` audit log). **No injected catalog** — every keyed `template_id` is a stock SRD id. The server discovers bundles from `adventures/` (in-repo, open/original) and the game directory (private, licensing), unions them with the native registry, and scopes `prose` and save ids per adventure.
- **The adventure-module-compiler skill.** Reads a published (or published-shaped) adventure module (PDF/MD) and emits the bundle: prose → sidecar; geometry → grid + `edges` (with a fidelity-loss log for non-grid maps, an `edge_key` helper, a `validate_bundle` edge-key/wandering-table check, and a visual map-diff review gate); **non-SRD creatures → reskinned to their nearest SRD template** and logged; puzzles/tricks/bespoke traps/genuinely-novel creatures → flagged for the escape hatch. The compiler's helper tools stay off the play tool surface so they cost play sessions no standing schema.

Definition of done: one small **openly-licensed or original-authored** module (not a commercial one — see licensing), with at least one reskin, compiles and is playable end-to-end, with a documented list of what was reskinned, approximated, or pushed to the authorial escape hatch. No engine change; no behavioral skill change.

**Phase 3 — skill-graph parity and polish.** Fill in the rest of `bx-referee`'s surface on the new substrate: character creation via `create_character` (deterministic, seeded), town/economy commands, level-up (engine-owned via `AwardXP`/advancement), save/resume, and a session audit/roll-log skill. Reconcile the skill graph into a clean shape: a `referee` orchestrator, a `play` loop that owns the encounter and battle lifecycles, and a `session` skill for save/audit. Definition of done: feature parity with `bx-referee` for native + compiled content.

**Phase 4 (optional) — the eval harness.** Lean on determinism: record seed + command log per session, replay offline to score trajectories, regression-test prompt changes against fixed seeds. This is the payoff osrlib's design was built for and `bx-referee` can't offer.

## Skill layer design

The skill layer follows osrlib's own LLM-referee doctrine — the deterministic engine does the mechanics, the LLM narrates — with OSE voice and conventions borrowed from `bx-referee`:

- A **constitution** (behavioral contract): the engine is the source of truth (never invent a roll or a stat); the player owns mechanical choices (present options, wait — never auto-pick, never auto-burn analog); no silent state changes (every `execute` is the audit trail); information discipline (strip referee-visibility data before narrating — the `observe` projection carries it, the fiction must not leak it).
- A **`play` loop** owning the encounter and battle lifecycles, so there is no separate combat skill re-deriving anything — combat is `ResolveBattleRound` with the player's declarations, and the engine's **default monster action policy resolves the enemy side**, so the LLM declares only the party's actions. The ~4,000-token combat setup is gone; the per-round monster reasoning is gone too.
- State updates are no longer "Read → edit Markdown → Write." State lives in the engine; the skills read `observe` and narrate. The Markdown state files (`PARTY.md` etc.) disappear as canonical stores — at most an optional human-readable session journal remains.

## Risks and open questions

- **Packaging/PATH (Phase 0 retires this).** If plugin-bundled uv proves unreliable cross-platform, fall back to a documented `uv sync` prerequisite or a published server on PyPI invoked via `uvx`.
- **Reskin fidelity (Phase 2).** Scoping module content to the SRD means a non-SRD creature is reskinned to its nearest SRD template — it takes the SRD stats and mechanical identity — so it can *behave* unlike the source module intends (a "barrow wight" is an SRD `skeleton`, minus energy drain). Narration is unaffected (the referee describes by appearance per the constitution, announcing neither name), so the mechanical loss is the real trade — an accepted, logged one, judged per creature at the map-diff / approximation-log review gate; a creature whose mechanics *are* the encounter goes to the escape hatch instead. The injectable-catalog engine change that would support true customs (session-owned catalogs threaded through spawn/handlers/exploration, plus core-layer equipment lookups that hold no session) is **deferred** to a future phase, reached only when a target module demands it — it remains the single largest engine-side unknown when that day comes.
- **Geometry transcription cost.** Even automated, compiling a large adventure module's `edges` is the dominant Phase 2 effort and the likeliest place fidelity slips. Mitigate with `validate_bundle`'s edge-key integrity check (the free-form `edges` map is exactly what `validate_adventure` does *not* validate) and a visual map-diff review step.
- **Observation scope tuning.** Too little in `observe` and the LLM asks for more (round-trips); too much and the token win erodes. Needs empirical tuning in Phase 1 against real play.
- **Does osrlib want this upstream?** Its `llm-referees.md` says "a complete example agent is on the roadmap" but none ships. This project could *become* that reference consumer. Worth a conversation about whether the server lives here or feeds back to osrlib.

## Decisions pinned

- One `execute` tool over the `AnyCommand` union, not 45 tools — beats 45 tool defs, though the union schema is a fixed per-turn context cost to measure (mode does not prune it).
- `observe` is a scoped current-state snapshot, never the raw `RefereeView` (whole event log + command log + adventure); it does not re-ship events (those ride `execute`'s envelope).
- Prose lives in an out-of-band sidecar keyed by area id, served by `prose(area_id)`.
- Phase 2 is scoped to SRD-only modules: non-SRD monsters are reskinned to their nearest SRD template (SRD stats and mechanical identity; the referee still narrates by appearance), the substitution logged; the injectable-catalog engine change (session-owned catalogs) is deferred to a future phase for genuinely-novel stat blocks. Monkeypatching the `@cache`d loaders stays rejected (fragile, global), as does a prose-driven monster-renaming layer.
- Saves are durably persisted to the user's game directory; the in-memory example store is not inherited.
- PC creation is a pre-session build surface (`create_character` → party document), not an `execute` command.
- Content ingestion is Phase 2; the architecture is proven on native content in Phase 1 first.
- The engine's default monster action policy resolves the enemy side of combat; the LLM declares only party actions.
- Authorial commands are the sanctioned escape hatch for anything the content model can't express.
- Adjudication obeys one rule: every outcome enters the trajectory as a logged command, and any *chance* outcome (as opposed to a referee *judgment*) is rolled by the engine from the seeded stream — never invented, never out-of-band, never re-rolled for a better result. osrlib 1.1.0's `RollDice` (the dedicated `adjudication` stream + `DiceRolledEvent`) is the mechanism; a *judgment* remains a declared `SetFlag` ruling.
- Compiled bundles for non-open modules stay private to the game directory; only openly-licensed or original-authored modules ship in the repo.

## Resolved decisions

- **Repo location (2026-07-05):** a standalone `~/repos/osrlib-referee` — chosen over a plugin folder inside `osr-plugins` — so the MCP server can be a proper `uv` package with its own tests and CI while `bx-referee` stays untouched. The repo is itself a Claude Code plugin (skills + `.mcp.json` at root; server under `server/`).
- **Adjudication-roll engine command (2026-07-05):** landed upstream as osrlib 1.1.0's `RollDice` ([osrlib-python#22](https://github.com/mmacy/osrlib-python/issues/22)) — an authorial arbitrary-dice command drawing from a dedicated `adjudication` RNG stream and emitting `DiceRolledEvent`, so freeform *chance* outcomes are rolled through the seeded session, logged, and replayable. Dedicated `Check`/`Save` commands were not part of 1.1.0 and remain an optional future addition.
- **Phase 2 scoped to SRD-only modules (2026-07-06):** Phase 2 (the content bridge) drops the injectable-catalog engine change and defers custom/unique stat blocks. A published module compiles to a bundle (an `Adventure` spec + prose sidecar + manifest, **no injected catalog**); a non-SRD creature is reskinned to its nearest SRD template — SRD stats and mechanical identity, the referee still narrating by appearance — with the substitution logged as an approximation, needing no engine change and no behavioral skill change. A prose-driven monster-renaming layer was considered and rejected as fragile scaffolding (the engine surfaces monster names in player-visible events with no content field to override). Genuinely-novel creatures (mechanics that *are* the encounter) and true custom magic items go to the authorial escape hatch or wait for the deferred injectable-catalog change. Full plan: [`docs/phase-2-plan.md`](phase-2-plan.md).
