# Phase 3 plan — skill-graph parity and polish

Implementation plan for Phase 3 of [the osrlib-referee spec](spec.md). Phase 0 proved the wire; Phase 1 proved the **thesis** (engine owns mechanics/state, tokens go to fiction) on native content; Phase 2 built the **content bridge** (compile a published-shaped module into a playable bundle). Those three phases delivered the *play loop* — dungeon exploration, encounters, battle — on a deterministic substrate. Phase 3 fills in **everything around the delve**: making a party, spending gold in town, gaining levels, saving and resuming with a recap, and inspecting the roll-log — then reconciles the skills into a clean graph. The milestone is **feature parity with `bx-referee` for native + compiled content**.

Every engine claim below is grounded in verified v1.1.0 source (`~/repos/osrlib-python`, tag `v1.1.0`; the wheel in `server/.venv` matches), read against the installed source during planning. Citations are `file:line` relative to `src/osrlib/`.

## The milestone

A **full campaign lifecycle** runs end-to-end through Claude Code on the existing MCP substrate:

1. **Make a party** — roll ability scores, choose class/alignment/adjustment/spells, buy starting equipment, name the character; assemble several into a party — all rolled by the engine from a recorded seed, so the party is deterministic and auditable, never LLM-invented.
2. **Start an adventure** on that party — native (`barrow_crypt`), a shipped bundle (`sunken_chapel`), or **a published module the player points at**: if it isn't compiled yet, the orchestrator routes through `compile-adventure` (Phase 2) first, then starts the session on the resulting bundle. (Compile-then-play, not `bx-referee`'s live per-session PDF re-read — the deliberate architectural divergence, see work items E and F.)
3. **Delve** — the Phase-1/2 loop (explore, trap, fight, flee, return).
4. **Town** — return, sell recovered treasure, buy gear, pay for temple healing; the engine awards return-trip XP automatically.
5. **Level up** — engine-automatic when XP crosses a threshold; the referee narrates the advance.
6. **Save, then resume in a later session with a recap.**
7. **Audit** — the player can ask to see the roll-log; the engine's deterministic command/event trajectory makes it real, not reconstructed.

Definition of done is **parity with `bx-referee`**: every player-facing feature `bx-referee` offers is either reproduced on this substrate, delivered *better* by the engine (treasure XP, roll transparency), or documented as an engine-limited gap — with the divergences stated honestly, never faked in prose.

## Scope

In scope:

- **Character creation + the party-build surface (work item A).** A deterministic, seeded `chargen` CLI (the build-time, off-the-play-surface pattern Phase 2 established with `bundletool`) driving osrlib's stepwise creation functions, plus party-document persistence and a `session_new` `party_ref` so the built party reaches a session without shipping the whole document over the wire. The `character` skill drives it conversationally.
- **Town / economy (work item B).** No new `execute` path — the town commands are already in the `AnyCommand` union. What Phase 3 adds is the **town branch of the `observe` projection** (party purse, XP/level, town services), a **static reference read** (equipment catalog, healing services, XP thresholds) delivered off the play surface, and **town-mode guidance in the `play` skill**.
- **Level-up narration (work item C).** Advancement is engine-owned and automatic; there is **no `LevelUp` command and no level-up event** (`crawl/events.py`, confirmed below). Phase 3 surfaces `level`/`xp`/next-threshold in `observe`, adds a live `character_sheet` read for the full derived sheet, and teaches the `play` skill to narrate an advance by inference — honestly, including where osrlib diverges from `bx-referee`.
- **Save / resume / recap + the session-audit skill (work item D).** `session_new`/`load`/`save` already exist; Phase 3 adds save enumeration for the resume flow, the recap experience (riding `observe`'s cold event tail), an optional human-readable journal, and a **live `session_audit` read** of the roll/command log. A new `session` skill owns save/resume/audit.
- **Skill-graph reconciliation (work item E).** A `referee` orchestrator (entry + routing), the `play` loop (exploration/encounter/battle/town), the `character` skill (creation), the `session` skill (save/resume/audit), the shared `constitution`, and the Phase-2 `compile-adventure` (build-time, unchanged). The Phase-0 `ping` no-op is retired. Constitution updated for town, creation, and audit information-discipline.
- **The parity scorecard (work item F).** Walk `bx-referee`'s complete feature list; mark each reproduced / engine-divergent / out-of-scope, with the divergences documented.
- **Tests.** A deterministic character-creation golden, a town-economy in-process delve (buy/sell/heal/enter/return/auto-XP/auto-level-up), a level-up inference test, save/resume/recap, the audit-log shape, and party-document round-trip + `session_new` `party_ref`.

Out of scope (named so the phase does not over-reach):

- **Retainers / henchmen / mercenaries in the party.** No engine surface exists: CHA `max_retainers`/`retainer_loyalty` are inert data (`core/abilities.py:141-142`) consumed by nothing, and `SpawnNpcParty` fields an *adversary* NPC party, not a party joiner (`crawl/commands.py:1497`, handler `crawl/session.py:844-875`). `bx-referee` scopes followers out too (`README.md:57`). A friendly retainer is project glue past this phase or the authorial escape hatch.
- **Banking / vault, training-for-levels, paid town identification, a generic shop/service catalog.** No engine commands (see "The honest part — engine-limited parity gaps"). Anything beyond `PurchaseEquipment` + `SellTreasure` + the six `PurchaseHealing` services is the authorial escape hatch or narrative-only.
- **The 4d6-drop-lowest and max-HP-at-1 creation house rules** `bx-referee` offers. osrlib's `create_character` rolls **3d6 straight, in fixed order**, with no method choice (`core/character.py:412-431`); the only reroll knob is the ruleset's per-die `hp_reroll_at_first_level` on a 1-2 (`core/character.py:481-484`). Supporting arbitrary roll methods is an engine change — deferred. A "reroll the character" is a fresh seed (auditable), which Phase 3 *does* support.
- **Strongholds, domain management, mass/ship combat.** Out of scope for `bx-referee` too (`README.md:57`); out of scope here.
- **The eval/replay harness (Phase 4).** Phase 3's deterministic, seeded party + the already-replayable session trajectory *unblock* Phase 4, but no scoring harness is built here.
- **The token measurement.** Phase 1's deferred Milestone-B follow-on; not re-opened. Phase 3 does, however, keep honest account of the standing per-turn schema cost of any tool it adds to the play server (see the honesty note).

## Work item A — character creation + the party-build surface

Today the server builds one **fixed pregen party** internally (`content.py:build_scripted_party` → `default_party_document`), and `session_new` falls back to it when no `party_document` is supplied (`store.py:90`). Phase 3 makes the party the *player's*, built deterministically.

### The engine surface (grounded)

osrlib exposes creation two ways (`core/character.py`):

- **`create_character(*, name, class_id, alignment, ruleset, stream, adjustment=None, starting_spell_ids=(), extra_languages=(), purchases=(), equip_ids=())`** (`core/character.py:628-640`) — an all-choices-upfront convenience that runs the whole SRD sequence and **raises `ValueError` on any illegal decision** (`core/character.py:676-680`), collapsing structured reasons into an exception. This is what the pregen path uses.
- **The stepwise pure functions** — `roll_ability_scores(stream)` (`:412`), `validate_class_choice(scores, definition)` → `list[Rejection]` (`:434`), `validate_adjustment`/`apply_adjustment` (`abilities.py:342`/`:416`), `roll_hit_points(...)` (`:461`), `roll_starting_gold(stream)` = 3d6×10 gp (`:616`), and `validate_purchase`/`purchase`/`validate_equip`/`equip` (`items.py:1418`/`:1442`/`:1575`/`:1660`). These return **structured `Rejection`s** and the **raw rolls** (`AbilityScoreRolls`, `HitPointRoll`, `RollResult`) for display — the right surface for an interactive flow that must explain *why* a choice is illegal.

Two facts shape the design decisively:

1. **Ordering is fixed and RNG-draw order is contractual** (`core/character.py:646-647`): scores → (validate class, no draw) → (adjustment, no draw) → (spells, no draw) → HP → (languages, no draw) → gold → purchase → equip. **Scores, HP, and gold are the only draws, in that order.** So a player *must* see rolled scores before legally picking a class (class requirements validate against pre-adjustment scores, `:438-448`).
2. **Creation is pre-session and seed-decoupled.** It emits no events and touches no session (`core/character.py:21-24`); its RNG is `RngStreams(master_seed=S).get(CHARACTER_CREATION_STREAM)` (`:83`), wholly unrelated to the eventual session seed. `GameSession.new` takes a finished `Party` and only assigns entity ids — it never re-rolls (`crawl/session.py:281-283`).

### The decision: a stateless, seed-driven `chargen` CLI — off the play surface

**Character creation does not go on the play `FastMCP` server.** Phase 2 pinned the principle: FastMCP advertises every tool's schema in *every* session that loads the plugin, so a tool used only at build time adds a standing per-turn cost to play sessions that never use it — which is why the compiler helpers became the `bundletool` CLI (Phase 2 plan §"Exposure — off the play surface"). Character creation is the same shape: **once per campaign, pre-session, never during the turn loop.** It goes in a `chargen` CLI (a sibling of the Phase-2 `bundletool`), so play sessions pay **zero** standing schema for it.

**The seed makes the CLI stateless** — no creation-in-progress scratch file. Because scores/HP/gold are drawn in fixed order from `RngStreams(S).get(CHARACTER_CREATION_STREAM)` (`core/character.py:646-647`), each stage is a pure function of `(seed, the choices before it)`. Two CLI subcommands, invoked `uv run --project server python -m osrlib_referee_mcp.chargen …`:

- **`chargen roll --seed S`** → runs `roll_ability_scores` and emits, as JSON: the six scores plus each ability's raw 3d6, and the **eligible-class list** — the classes whose `validate_class_choice(scores, definition)` returns no rejection (`:434`). Both depend on the scores alone (validation draws nothing), so `roll` can present *only* legal classes without the skill computing eligibility itself, and without yet knowing the class. **It deliberately does *not* emit starting gold**: gold is drawn *after* HP (order scores→HP→gold), and the HP draw's stream consumption is **class-dependent** — `randbelow` uses rejection sampling whose raw-draw count varies by bound (`core/rng.py:191-193`: power-of-two bounds like the d4/d8 hit dice never reject, but a d6 hit die can), so the stream position at gold-time, and thus the gold value, depends on the class. Gold is therefore a `build`-time result, not a `roll`-time one.
- **`chargen build --seed S --class fighter --alignment lawful [--adjust …] [--spell …] [--buy sword,leather,…] [--equip sword,leather] --name Brakka`** → re-derives the same scores from `S`, then (class now known) rolls HP and gold deterministically, applies the post-roll choices, and returns either the finished `Character` document — **with the rolled HP and starting gold shown** — or a **structured rejection list** the skill narrates. `build` is idempotent per `(seed, class, choices)`: **called first with no `--buy`/`--equip`, it reveals the gold** so the player can shop against a real number; **called again with the purchases**, it reproduces the identical HP/gold draws and finalizes the character. Same seed + same choices ⇒ byte-identical character. (Rolling gold after the class is chosen also matches `bx-referee`'s own order — it rolls starting gold at the equipment step, well after class, `character/SKILL.md:80-86`.)
- A **"reroll"** is a new seed (`bx-referee`'s sub-par reroll, made auditable). The engine will not reroll a single ability in place; that is not an osrlib affordance.

The CLI drives the **stepwise validators** (not the raises-on-error `create_character`) so a bad class choice or unaffordable basket comes back as a readable reason, not a stack trace. It records the seed in the character document's provenance so the roll is reproducible and audit-visible.

### Party assembly and how it reaches a session

- **`chargen party --out <party_id> <char.json> <char.json> …`** (or the skill assembling from individual character files) → wraps the members with `party_to_document(members)` (`core/character.py:339`, the stamped `kind:"party"` envelope the server already consumes) and writes it to **`<game-root>/parties/<party_id>.json`**. Members carry `id=None` pre-session, which is correct — `GameSession.new` assigns ids (`crawl/session.py:281-283`).
- **`session_new` gains a `party_ref` parameter** — a party id resolved server-side against `<game-root>/parties/`. This keeps the whole (large) party document **off the conversation wire**: the skill passes a short id, the server loads the JSON and feeds `party_from_document` → `GameSession.new`. The existing `party_document` dict param stays (tests and programmatic callers use it); the pregen fallback stays for a zero-setup start.

Resolution is by precedence, not error: `party_document` (inline) > `party_ref` (by id) > pregen default. Supplying both an inline document and a ref is resolved in the document's favor rather than rejected — one fewer error path, and the common case (exactly one of the three) is unambiguous either way.

### The `character` skill

A conversational front-end over the CLI, mirroring `bx-referee`'s `character` skill flow (`skills/character/SKILL.md`) but with the engine — never the LLM — rolling every die:

1. `chargen roll` → present the scores (and modifiers) and offer a reroll = new seed. The `roll` payload carries the **eligible-class list**, so the next step's menu is legal-by-construction.
2. `AskUserQuestion` for class (present only the eligible classes `roll` returned — the CLI's `validate_class_choice` is the gate, never the skill's own arithmetic), then alignment, the optional adjustment, and the arcane starting spell (magic-user/elf only).
3. `chargen build` with those choices and **no purchases** → reveals the rolled **HP and starting gold**. Present the gold, then `AskUserQuestion` for equipment (a standard class kit or a manual pick) against that number.
4. `chargen build` again with the equipment choices and the name → the finished character; on a rejection (e.g. an unaffordable basket), surface the reason and re-ask.
5. Repeat for each party member; `chargen party` to assemble; report the `party_id` the player will start with.

`AskUserQuestion` is used **only for these administrative build choices** — never for in-world gameplay (constitution Article I.5). The skill delivers rolled numbers verbatim from the CLI and never invents a stat (constitution Article III.1).

## Work item B — town / economy

Town is one of osrlib's five session modes (`TOWN`, `crawl/commands.py:93-104`); a fresh session starts in it (`crawl/session.py:224`). The delve already returns to town (`TravelToTown`, Phase 1). Phase 3 makes town **playable**, not just a bookend.

### No new `execute` path — the commands already exist

The economy verbs are already in the `AnyCommand` union the `play` skill executes, each gated to `TOWN` (verified `frozenset({SessionMode.TOWN})`):

- **`PurchaseEquipment(character_id, item_ids)`** (`crawl/commands.py:1019`, modes `:1040`) — buy from the catalog; the whole basket must be affordable or nothing buys (handler `crawl/exploration.py:1759`).
- **`SellTreasure(item_ids)`** (`:1047`, modes `:1071`) — sell carried valuables at full `value_gp`; magic items reject (`town.sell.no_fixed_value`).
- **`PurchaseHealing(character_id, service)`** (`:1077`, modes `:1103`) — one of six temple services (`cure_light_wounds`, `cure_serious_wounds`, `cure_disease`, `neutralize_poison`, `remove_curse`, `raise_dead`); price table `crawl/exploration.py:2726-2733`.
- **`EnterDungeon(dungeon_id)`** (`:961`, modes `:984`) — depart; **snapshots party treasure valuation** for the return XP delta (`crawl/exploration.py:988`).

Plus the town-legal field commands (`_FIELD_MODES = {TOWN, EXPLORING}`, `crawl/commands.py:108`): `Rest`, `EquipItem`/`UnequipItem`, `ReorderParty`, `PrepareSpells`, `CastSpell`, `LightSource`. `list_commands("town")` already surfaces the legal menu.

So the `play` skill's turn loop already *can* run town — it needs **guidance** (a town section: the return-buy-sell-heal-depart rhythm, the sharp edge that `TravelToTown` is an `EXPLORING` command issued on the entrance cell, not a town command) and it needs to **see** town state and prices, which today it cannot.

### The two real gaps: `observe` has no town branch, and prices are out-of-band

1. **`observe` town branch.** The projection (`projection.py:build_observation`) was built for dungeon scenes. In town it must surface: each member's **purse and valuables** (the gold available to spend — `MemberView.inventory` masked via `_masked_inventory`, `crawl/views.py:217-228`), **level/XP** per member, and the **town's service prose** (`TownSpec.name/description/services`, `crawl/adventure.py:40-42` — note `services` is front-end prose, *not* the mechanical healing list). Grounded from live `GameSession` attributes exactly as the dungeon branch is, never `session_state()`.
2. **Prices/catalog are not in any view.** `PlayerView` carries no catalog (`crawl/views.py:132-153`); the purchase handler calls `load_equipment()` itself (`crawl/exploration.py:1763`). The player shopping needs to *see* item ids, names, and `cost_gp` (`core/items.py`), plus the six healing-service prices (`HEALING_SERVICES`, `crawl/exploration.py:2726`). **This is static reference data** — it never changes mid-session — so it is delivered **off the play surface**, by a **`gametool` CLI** (a sibling of the Phase-2 `bundletool`, invoked `python -m osrlib_referee_mcp.gametool …`): `gametool catalog` (the equipment catalog: id, name, `cost_gp`, lot size, damage), `gametool services` (the six healing services + prices), and `gametool thresholds <class>` (the class XP progression). The `play` skill invokes it during a town turn the way `chargen` is invoked during creation. No standing play-schema cost for a static lookup.

### Return-trip XP is a free win over `bx-referee`

On `TravelToTown` with the default `ON_RETURN` timing (`core/ruleset.py:105-110`), the engine awards `monster_xp` + `treasure_xp` automatically: `treasure_xp = max(0, (current_valuation − departure_snapshot) // 100)`, i.e. 1 gp recovered = 1 XP, split among survivors (`crawl/session.py:593-642`), emitting one `AdventureXpAwardEvent` (`crawl/events.py:562`, fields `monster_xp`/`treasure_xp` at `:570-571`) then per-survivor `XpAwardedEvent`. `bx-referee` **never implements treasure XP** — its combat skill awards monster XP only (`combat/SKILL.md:177`). So this beat is parity-plus for free; the `play` skill simply narrates the `AdventureXpAwardEvent`. (And because an XP award can cross a level threshold, this is exactly where a level-up fires — see work item C.)

## Work item C — level-up narration

Advancement is **engine-owned and fully automatic**, and this shapes the whole design: there is **no `LevelUp`/`AdvanceCharacter` command** (verified — the only advancement-adjacent command is `AdvanceTime`, `crawl/commands.py:1590`) and **no level-up event class** (verified — no `LevelUp`/`Advance`/`LeveledUp` event in `crawl/events.py`). Leveling is a side effect of *any* XP award: `apply_xp` calls `level_up` inline when the new total crosses the next threshold (`core/classes.py:816`), with a one-level-per-award clamp (`:809-814`). The only surface command is `AwardXP` (`crawl/commands.py:1408`); the automatic return-trip award (work item B) is the common trigger.

**The narration gap, stated plainly.** `level_up` rolls a hit die and returns a `LevelUpResult` (new level, hp rolled, hp gained, con applied — `core/classes.py:358-371`), but **none of that is emitted in any event.** The only signal a play skill gets is `XpAwardedEvent.level_after` (`crawl/events.py:637`). So:

- **`observe` surfaces advancement state.** Per party member, the projection adds `level`, `xp`, and the **next-level XP threshold** (computed from the class row, `ClassDefinition.row(level+1).xp`, `core/classes.py:305`), so the referee — and the player, appropriately — can see how close each character is to advancing.
- **A live `character_sheet(character_id)` read** returns the full **derived** sheet — THAC0, AC, saves, movement, spell slots — which osrlib computes as properties but never stores (`core/character.py:153-303`) and `observe` does not ship per turn. This gives parity with `bx-referee`'s character-sheet display and is what the `character`/`session` skills render on request. It reads the **live session**, so it is a small play-server tool (see the exposure rule below), not a CLI.
- **The `play` skill narrates an advance by inference:** when an `XpAwardedEvent.level_after` exceeds the level it held before the award, announce the new level and — read from `observe`/`character_sheet` — the new **max HP** and any new capabilities. It **must not fabricate the hit-die roll** (not in any event; the constitution forbids inventing a roll, Article III.1). It reports the outcome the engine committed, not a reconstructed die.

**Two honest divergences from `bx-referee`, narrated as the engine actually behaves:**

- **Level-up does not restore HP.** osrlib adds the rolled HP to *both* `max_hp` and `current_hp` but heals no existing damage (`core/classes.py:457-458`); `bx-referee` sets current HP to full on level-up (`character/SKILL.md:164`). The `play` skill narrates osrlib's behavior — a wounded character who levels is still wounded — never `bx-referee`'s.
- **No separate level-up step and no skill-enforced one-level-per-session cap.** `bx-referee` hops to its `character` skill for advancement and caps it at one level per session (`character/SKILL.md:141`). Here the engine advances inline and clamps **one level per award** (`core/classes.py:809-814`) — a different, engine-owned rule. There is no level-up skill hop; the `play` skill narrates it in place. This is a simplification the engine's ownership buys.

## Work item D — save / resume / recap + the session-audit skill

### Save / resume / recap

`session_new`/`session_load`/`session_save` already persist the full `save_game` document verbatim to `<game-root>/adventures/<adventure_id>/<save_id>.json` (Phase 1). Phase 3 completes the lifecycle:

- **Enumerate saves for the resume flow.** `bx-referee` globs `SESSION.md` files to offer "which to continue" (`adventure/SKILL.md:146-153`). Here, add a **`gametool saves`** CLI read (game-directory enumeration is a filesystem read, not live-session state — CLI, no standing play cost) that lists saved games (`adventure_id`, `save_id`, engine version, mtime). The `referee`/`session` skill presents the list.
- **Recap.** `observe` already returns a **cold** bounded event tail right after `session_load` (`server.py:122-124`, `store.needs_recap`). That is the mechanical recap source — the skill narrates "here's where you left off" from it. A richer narrative recap comes from the optional journal below.
- **The optional journal.** A human-readable `SESSION.md`-role file (`bx-referee`'s session log + current-situation, `adventure/SKILL.md:198-233`) the `session` skill may write alongside the save — **a convenience for the player and for recaps, never canonical**. The `save_game` document is the single source of truth (an explicit Phase-1/spec decision); the journal is derived and disposable. Multiple named saves per adventure already work (distinct `save_id` stems).

### The session-audit skill — a superset over `bx-referee`

`bx-referee` has **no roll-log, audit trail, or roll-transparency mechanism** — its constitution actively *hides* target numbers and resolves rolls silently (`constitution.md:36-41`). osrlib-referee can do what `bx-referee` structurally cannot: the engine keeps a full, ordered **event log and command log** in the session (the save document embeds both), so every roll is real, recorded, and replayable.

- **A live `session_audit(...)` read** returns the roll/command trajectory — dice rolls (`DiceRolledEvent`, `adjudication.dice_rolled`, `crawl/events.py:664`), attack and save resolutions, and XP awards (each `XpAwardedEvent` carrying the `level_after` that signals an advance — there is no level-up event to surface, per work item C) — from the **live session's** event log (the on-disk save may lag, so this reads the running session, not the file). A small filter argument (e.g. by scene or event kind) keeps the payload bounded. It is a play-server tool because it needs the live log.
- **Information discipline still binds (constitution Article II).** The audit is a **referee-visibility** read; what the `session` skill shows the *player* mid-session must not leak an undiscovered secret door's existence or a monster's unrevealed stats. Post-hoc (after a scene resolves, in town, at session end) the full roll history is fair game — that transparency is precisely the eval-ability the whole project was built for. The skill presents a player-appropriate view during play and the full trajectory on request when nothing is being spoiled.

## Work item E — skill-graph reconciliation

Today: `play` (+ `constitution`), `compile-adventure` (Phase 2, build-time), and the Phase-0 `ping` no-op. The spec's Phase-3 target is a `referee` orchestrator, a `play` loop that owns the encounter/battle lifecycles, and a `session` skill for save/audit. The reconciled graph:

- **`referee`** — the entry point and router, mirroring `bx-referee`'s orchestrator (`referee/SKILL.md`). At session start it asks new-adventure / continue / create-characters, and routes: create → `character`; continue → the session lifecycle (`session` resume) then `play`; new → start the chosen content, then `play`. **"New" is where published-module parity lives.** `bx-referee`'s new-adventure flow points at a module PDF and reads it live every session (`adventure/SKILL.md:37-141`); here the same intent — *"play this module"* — is one guided journey with a **compile step folded in**: the orchestrator resolves the chosen adventure against `list_adventures` (native builders + already-compiled bundles), and **if the player points at an uncompiled module (PDF/MD), it routes through `compile-adventure` first** (Phase 2 — producing a private bundle in the game directory, per Licensing), then starts the session on that bundle and enters `play`. So "point at a module and play it" reaches parity at the *workflow* level, differing only in that the PDF is read **once at compile time**, not re-read every session — the project's core inversion, which is what makes the resulting session deterministic and replayable. The orchestrator is thin: it does not run play or compilation itself, it routes.
- **`character`** — creation + party build (work item A), driving `chargen`. (No level-up hop — advancement is engine-automatic inside `play`, work item C.)
- **`play`** — the turn loop, now covering **town** as a first-class mode (work item B) and **level-up narration** (work item C) alongside the existing exploration/encounter/battle it already owns. Still one loop, no separate combat skill.
- **`session`** — save / resume / recap / audit (work item D).
- **`compile-adventure`** — the Phase-2 build-time content compiler, unchanged (a different concern from play; stays its own skill).
- **`constitution`** — the shared behavioral contract. It **moves** from its Phase-1 home `skills/play/references/constitution.md` to a shared location referenced by `play`, `character`, and `session` alike — `skills/referee/references/constitution.md`, the orchestrator owning the shared contract (mirroring `bx-referee`, where `skills/referee/references/constitution.md` governs every skill, `referee/SKILL.md:34-36`). Its opening framing ("governing all referee behavior **during play**") widens to cover creation and audit too. Updated for: town/economy narration, creation (the engine rolls every score/HP/gold; `AskUserQuestion` for administrative build choices only, never in-world play — Article I.5), and audit information-discipline (Article II governs what the roll-log reveals to the player mid-scene).
- **Retire `ping`** — the Phase-0 no-op has no place in the parity graph (greenfield discipline: no dead scaffolding, `AGENTS.md` §Greenfield).

Each skill's `allowed-tools` is reconciled against the **live exposed tool names** (as Phase 0/1 did), including any new play-server tools (`character_sheet`, `session_audit`) and the unchanged lifecycle/`observe`/`execute` set. CLI-backed operations (`chargen`, `gametool`) need `Bash`, not an MCP tool grant.

## The honest part — the play server's tool surface, and engine-limited parity gaps

**The standing-schema discipline is the through-line of this project, and Phase 3 is where the play server's tool count is most tempted to grow.** The rule, pinned: **a tool goes on the play `FastMCP` server only if it needs the live running session; everything static or build-time is a CLI.** Applying it:

- **On the play surface (live-session reads, small schemas):** `character_sheet(character_id)` and `session_audit(...)`. Plus the existing eight (`execute`, `observe`, `prose`, `list_commands`, `list_adventures`, `session_new`, `session_load`, `session_save`) — ten standing tools in all. That is the entire standing per-turn cost Phase 3 adds — two small tools — and it is accounted here, not hidden. The `AnyCommand` union still dominates the standing cost (Phase 1's finding); these two add little, but "little" is not "nothing," and the plan says so.
- **Off the play surface (CLIs, zero standing play cost):** `chargen` (creation), `gametool` (static catalog/services/threshold reads and save enumeration). Used at build time or via `Bash` during a town/creation exchange — never advertised to a play turn.

`observe` grows too (a town branch, per-member level/XP/next-threshold) — but `observe` is one already-standing tool whose *payload* grows, not a new tool; the town branch ships only in town, and the advancement fields are a few integers per member. Net: the projection stays scoped, per the Phase-1 tuning discipline.

**Engine-limited parity gaps — documented, never faked in prose** (each would need an osrlib change, all deferred):

1. **No 4d6-drop-lowest / max-HP creation house rules.** `create_character` is 3d6-in-order only (`core/character.py:412-431`). Reroll = new seed; arbitrary roll methods wait for an engine option.
2. **No retainers/henchmen, banking, training-for-levels, paid town identification, or generic shop.** No engine commands (`IdentifyItem` is a free *referee* command, `crawl/commands.py:909`; there is no hire/deposit/train verb). The escape hatch covers improvised cases; the domain is otherwise narrative-only, and `bx-referee` scopes most of it out as well.
3. **No level-up event.** The hit-die roll is computed but unemitted; the `play` skill narrates the *outcome* (new level, new max HP from `observe`), never a fabricated roll.

These are the truthful edges of "parity." The scorecard (work item F) marks each so a reviewer sees the fidelity budget, exactly as Phase 2's approximation log did for content.

## Work item F — the parity scorecard

A committed checklist (in this plan's closeout and/or the README) walking `bx-referee`'s complete player-facing surface, each item marked **reproduced** / **engine-divergent (how)** / **out-of-scope (why)**:

- **Reproduced:** the play loop (exploration/encounter/battle — Phases 1/2); character creation (full step flow, engine-rolled); adventure lifecycle (new/resume/save/recap); town economy (buy/sell/heal/depart); level-up (engine-automatic, narrated); the character sheet.
- **Engine-divergent (documented):** level-up does not restore HP; one-level-per-*award* not per-session; no creation house rules (seed reroll instead); treasure XP is automatic (parity-plus); roll transparency exists (parity-plus).
- **Play a published adventure module — reproduced *via compile*, the single most consequential divergence.** `bx-referee` points at a module PDF/MD and **reads it live every session** (LLM as rules authority, `adventure/SKILL.md:37-141`, `constitution.md:49` "Read before describing"). osrlib-referee **compiles the module once** (Phase 2's `compile-adventure`) into a deterministic bundle, then plays the bundle — the same "bring your own module" outcome by a different route. The scorecard states the trade honestly rather than claiming a clean match: **gained** — determinism, replayability, and amortized cost (compile once vs. re-read per visit); **paid** — an explicit compile step, and **SRD-only fidelity** (non-SRD creatures reskinned to their nearest template, geometry approximated, novel beats pushed to the escape hatch — Phase 2's approximation log). **The real coverage gap:** a module whose central creature's *mechanics are the encounter* and no SRD template approximates **cannot be faithfully compiled** until the deferred injectable-catalog engine change (spec §Resolved decisions) — for that class of module, `bx-referee` (which can narrate any creature freehand) is strictly more capable today. Naming this is the point; hiding it behind "compiled content" would be the faked parity this plan forbids.
- **Out-of-scope:** retainers, banking, training, generic shops, strongholds/domain play (out of scope for `bx-referee` too).

This scorecard *is* the definition of done made legible.

## Tests

The ladder extends Phase 1/2's in-process approach (real server tool functions + CLI entry points as plain callables, no Claude Code):

- **Deterministic character-creation golden.** `chargen roll --seed S` and `chargen build --seed S …` produce a byte-identical `Character` across runs; a fixed seed yields fixed scores/HP/gold; an illegal choice (under-min class, unaffordable basket) returns a structured rejection, not an exception, at the CLI boundary.
- **Party round-trip + `session_new` party_ref.** `party_to_document` → write → `session_new(party_ref=…)` → `party_from_document` reconstructs the members and `GameSession.new` assigns ids; precedence (`party_document` > `party_ref` > pregen) holds.
- **Town-economy in-process delve.** From town: `PurchaseEquipment` (affordable basket succeeds; over-budget rejects atomically), `SellTreasure` (valuable sells, magic item rejects `town.sell.no_fixed_value`), `PurchaseHealing` heals and debits, `EnterDungeon` snapshots, a scripted delve recovers treasure, `TravelToTown` emits `AdventureXpAwardEvent` with the expected `treasure_xp`/`monster_xp`, and — seed-chosen so the return award crosses a threshold — the automatic level-up fires (`XpAwardedEvent.level_after` increments).
- **Level-up inference.** Given a pre/post `level_after` delta with no level-up event, the projection exposes the new `level`/`max_hp`, and a wounded character that levels is asserted **still wounded** (the HP-restore divergence is pinned by test, not just prose).
- **`observe` town branch.** Asserts the town projection carries purse/valuables, per-member level/XP/next-threshold, and town service prose — and still never contains the whole adventure or the full event log.
- **Save / resume / recap.** `gametool saves` enumerates; `session_load` re-activates; the cold `observe` ships an event tail; the optional journal, if written, round-trips as text and is not read back as state.
- **`session_audit` shape.** A session with a `RollDice` and a battle round exposes those rolls in the audit read, bounded by the filter, at referee visibility.
- **The MCP boundary.** The Phase-1 in-memory client rung extended to `character_sheet` and `session_audit`, confirming FastMCP serialization of the two new tools.

**The manual gate** (as in every phase): inside `claude --plugin-dir .`, run the full lifecycle — make a party, start an adventure, delve, return to town and shop/heal, cross a level threshold, save, resume with a recap, and ask to see the roll-log — confirming the reconciled skill graph routes correctly and the tool names resolve.

## Sequencing

1. **Work item A (character creation + party surface)** first — the party is the entry point to everything, and the deterministic golden is what later tests build parties with. `chargen` CLI + `session_new` `party_ref` + the `character` skill.
2. **Work item B (town/economy)** — the `observe` town branch, the `gametool` static reads, and the `play` skill's town section. Its in-process delve test depends on a real party (step 1).
3. **Work item C (level-up narration)** — `observe` advancement fields, `character_sheet`, the `play` skill's inference-and-narrate. Tests ride the town delve (step 2), where the return award triggers the level.
4. **Work item D (save/resume/recap + audit)** — `gametool saves`, the recap flow, the optional journal, `session_audit`, and the `session` skill.
5. **Work item E (skill-graph reconciliation)** — the `referee` orchestrator, retire `ping`, wire routing, update the constitution. Done once the skills it routes to exist.
6. **Milestone — playable lifecycle:** the manual Claude Code run of the full lifecycle succeeds end-to-end.
7. **Work item F (parity scorecard) + README** close out, documenting every reproduced / divergent / out-of-scope feature.

## Definition of done

- The **full campaign lifecycle** is playable end-to-end through Claude Code: make a deterministic, seeded party → start a native or compiled adventure → delve → return to town and buy/sell/heal → cross a level threshold (engine-automatic, narrated) → save → resume with a recap → inspect the roll-log. **Automated proxy done:** the lifecycle passes in-process through the real server tool functions and CLI entry points; the manual Claude Code play-through is the final gate (as in Phases 1/2).
- The **skill graph is reconciled** to `referee` / `character` / `play` / `session` + `compile-adventure` + the shared `constitution`; `ping` is retired; every skill's `allowed-tools` matches the live exposed tool names.
- **Character creation, town/economy, level-up, and save/resume/recap** all run on the engine substrate with the engine rolling every die — no LLM-invented stat, gold total, or hit-die roll anywhere.
- The **test ladder is green in CI** (creation golden, party round-trip + `party_ref`, town-economy delve with auto-XP and auto-level-up, level-up inference incl. the HP-restore divergence, `observe` town branch, save/resume/recap, `session_audit` shape, MCP boundary).
- The **parity scorecard** documents every `bx-referee` feature as reproduced / engine-divergent / out-of-scope, with the divergences (level-up HP, one-level-per-award, no creation house rules, treasure XP, roll transparency) stated honestly.
- The **standing play-server schema cost** Phase 3 adds is exactly the two live-session tools (`character_sheet`, `session_audit`); everything static or build-time is a CLI; the cost is accounted, not hidden.

## Decisions pinned

- **Character creation is a deterministic, seeded `chargen` CLI, off the play surface** (the Phase-2 `bundletool` precedent) — never a live play-server tool, because it is pre-session and once-per-campaign and would otherwise add standing per-turn schema to every play session. The **seed carries the roll state** (stateless: `chargen roll` emits scores + the eligible-class list from the seed; `chargen build` re-derives the scores, then rolls HP and gold once the class is known — gold is class-dependent because the HP hit die's `randbelow` rejection consumes a class-varying number of raw draws, `core/rng.py:191-193`, so `build`, not `roll`, reveals it — and applies the post-roll choices), so no creation-in-progress scratch file is needed. `build` is idempotent per `(seed, class, choices)`, so calling it without purchases (to show gold) then with them (to finalize) reproduces identical draws. The CLI drives the **stepwise validators** (structured rejections), not the raises-on-error `create_character`.
- **A "reroll" is a fresh seed**, auditable; osrlib offers no in-place ability reroll and no 4d6-drop-lowest / max-HP method — those are engine-limited gaps, documented, not faked.
- **Built parties persist to `<game-root>/parties/<party_id>.json`; `session_new` gains a `party_ref` param** (loads server-side) so the large party document stays off the wire. Resolution is by precedence, not error: `party_document` (inline) > `party_ref` (by id) > pregen default; both supplied resolves in the document's favor.
- **Town/economy adds no `execute` path** — `PurchaseEquipment`/`SellTreasure`/`PurchaseHealing`/`EnterDungeon` are already `TOWN`-gated union commands. Phase 3 adds an **`observe` town branch** (purse/valuables, level/XP, service prose) and delivers **static shop/price/threshold data via a CLI** (`gametool`), never a play tool. `TravelToTown` stays an `EXPLORING` command issued on the entrance cell.
- **Return-trip XP (monster + treasure) is engine-automatic** on `TravelToTown` and is narrated from `AdventureXpAwardEvent` — a parity-plus over `bx-referee`, which never implements treasure XP.
- **Level-up is engine-automatic and eventless.** No `LevelUp` command, no level-up event, no separate level-up skill hop, and the cap is one level **per award** (engine-clamped), not one per session (skill-enforced, as in `bx-referee`). The `play` skill **infers** an advance from `XpAwardedEvent.level_after` and narrates the new level + new max HP from `observe`/`character_sheet`, never a fabricated hit-die roll. **osrlib does not restore HP on level-up** (unlike `bx-referee`) — the engine's actual behavior is narrated.
- **`observe` surfaces per-member `level`/`xp`/next-threshold; a live `character_sheet(character_id)` tool** returns the full derived sheet (THAC0/AC/saves/movement/spell slots osrlib computes but never stores) for parity display.
- **Save/resume/recap:** lifecycle tools already exist; add a **`gametool saves`** CLI enumeration for the resume menu; the recap rides `observe`'s cold event tail; an **optional human-readable journal** is a convenience, the `save_game` document stays canonical.
- **Session audit is a superset over `bx-referee`** (which has none): a live **`session_audit`** read of the engine's roll/command log, presented by the `session` skill under constitution Article II. The mid-play boundary is decided, not left empirical: **during play the audit shows the player their own characters' rolls and already-revealed outcomes only** — referee-only data (an undiscovered secret, an unrevealed monster's stats) is withheld until the fiction reveals it — and **the full referee trajectory is available on request at a scene boundary, in town, or at session end.**
- **Skill graph:** `referee` (thin orchestrator/router — it routes and does **not** run play, compilation, or persistence itself) → `character` / `play` / `session`, with **`session` owning save/resume/recap/audit** (the boundary is decided this way — not folded into `referee` as `bx-referee` folds save into `adventure`); plus `compile-adventure` (build-time) and the shared `constitution`, which **moves to `skills/referee/references/constitution.md`** and widens past its "during play" framing to govern creation and audit. `ping` retired.
- **Playing a published module is compile-then-play, orchestrated as one `referee` flow.** The new-adventure path resolves the player's choice against `list_adventures`: a **known adventure id starts the session directly**, while a **path to an uncompiled module (PDF/MD) routes through `compile-adventure` first** — and compilation, **including its map-diff/approximation review gate, completes and the bundle is accepted before the session starts** (never a half-reviewed bundle). The module is read once, at compile time, never live per session — the project's deterministic inversion of `bx-referee`'s per-visit re-read. Fidelity is **SRD-only**; a module whose central creature can't be reskinned to an SRD template waits for the deferred injectable-catalog engine change (parity scorecard, work item F) — the one class of module where `bx-referee` is more capable today.
- **The play server gains exactly two standing tools** (`character_sheet`, `session_audit`), both live-session reads with small schemas; **everything static or build-time is a CLI**: `chargen` (creation) and `gametool` (static catalog/services/thresholds + save enumeration), both siblings of the Phase-2 `bundletool`. The standing-schema cost is accounted.
- **Out of scope, engine-limited:** retainers/henchmen, banking, training-for-levels, paid town identification, generic shops, creation house rules, strongholds/domain play — each documented in the parity scorecard, most also out of scope for `bx-referee`.

## Corrections found during implementation

Small plan-vs-code reconciliations surfaced while building; recorded here so the plan and the shipped code never diverge.

- **`chargen build`'s `--name` defaults to a placeholder.** The plan's step flow reveals gold (step 3, no purchases) *before* the name is chosen (step 4), but a `Character` requires a non-empty name to construct. Since the name touches no RNG draw, `--name` defaults to `"Adventurer"` for the reveal-gold call and is replaced verbatim at finalize — the placeholder never affects the byte-identical scores/HP/gold, so idempotence holds.
- **`session_save` stays available to the `play` skill for pause-point saves.** The plan pins `session` as the owner of save/resume/recap/audit, and it is — the resume/recap/journal/audit *experiences* live there. But forcing a skill hop for a one-call save at a natural pause (returning to town, ending a session) is poor UX, so `play` keeps `session_save` in its `allowed-tools` for the trivial persist and documents `session` as the owner of the richer lifecycle. Resume-with-recap and the roll-log remain `session`-only.
- **The town-economy test injects a weightless valuable, not granted coins, to reach the level threshold.** Coins weigh 1 each and osrlib's max load is 1,600 coins, so a 30,000-coin treasure haul overloads the party and blocks the walk back to the entrance. Because treasure XP counts a valuable's `value_gp` exactly as a coin's, the test recovers a near-weightless gem instead — a faithful stand-in for a recovered cache that keeps the party mobile. (A play session recovers real treasure through content caches; the native barrow crypt keys none, so the in-process test injects one.)
- **The save-game document's stamped `kind` is `"save"`, not `"save_game"`** (osrlib's `persistence.save_game` → `stamp_document("save", …)`). The `session` skill's "the `save_game` document is the source of truth" prose refers to that document; the on-disk envelope's `kind` field is `"save"`.
