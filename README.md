# osrlib-referee

An MCP-enabled B/X tabletop RPG referee. It runs Old-School Essentials sessions where the deterministic [`osrlib`](https://pypi.org/project/osrlib/) engine owns every roll, stat, and state transition behind an MCP server, and the LLM spends its tokens on fiction — narrating rooms, voicing NPCs, and adjudicating freeform player intent.

This is a sibling to, not a replacement for, the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin. `bx-referee` makes the LLM the rules authority; `osrlib-referee` inverts that — the engine is the authority, the LLM is the narrator.

## Status

Phase 0 (scaffolding and the packaging spike) is done. Phase 1 (proving the loop on native content) is done, with one deferred piece: the comparative token measurement against `bx-referee`, and the manual `claude --plugin-dir .` play-through that confirms the exposed tool names live, remain a follow-on (see "Token measurement" below and `docs/phase-1-plan.md`'s "Corrections found during implementation" section). Phase 2 (the SRD-only content bridge) is done: an on-disk **adventure bundle** format and loader, discovery that unions native builders with compiled bundles, the `validate_bundle` compile gate, the `compile-adventure` skill, and a compiled demo module (`adventures/sunken_chapel/`) that plays end-to-end. Phase 3 (skill-graph parity and polish) is done: deterministic seeded **character creation** and party build (`chargen`), the **town economy** (buy/sell/heal/depart) with automatic return-trip XP, **engine-automatic level-up** narrated by inference, **save/resume with a recap**, a **roll-log audit** (`session_audit`), and a reconciled skill graph — a `referee` orchestrator routing to `character` / `play` / `session` over one shared constitution. The [parity scorecard](#parity-with-bx-referee) below walks every `bx-referee` feature and marks it reproduced, engine-divergent, or out-of-scope. The decision-complete design and phased roadmap live in [`docs/spec.md`](docs/spec.md); the phase build records are in `docs/phase-0-plan.md`, [`docs/phase-1-plan.md`](docs/phase-1-plan.md), [`docs/phase-2-plan.md`](docs/phase-2-plan.md), and [`docs/phase-3-plan.md`](docs/phase-3-plan.md).

## How it works

- A stdio MCP server holds a live `osrlib` `GameSession` in-process. Its live-session tools carry the whole loop: `execute(command)` runs one typed command from the `AnyCommand` union and returns `{accepted, rejections, events}`; `observe()` returns a scoped, referee-visibility projection of current state (never the raw save document); `character_sheet(character_id)` returns the full derived sheet (THAC0, AC, saves, movement, spell slots); `session_audit(...)` returns the recorded roll/command trajectory; `prose(area_id)` returns the authored read-aloud/referee-notes sidecar; `session_new`/`session_load`/`session_save` handle the lifecycle, with saves persisted durably to the user's game directory. Everything static or build-time — character creation, the equipment/services/threshold reference reads, save enumeration, and module compilation — stays **off** the play tool surface as a CLI (`chargen`, `gametool`, `bundletool`), so play sessions pay it no standing per-turn schema.
- Mechanics and state (dice, THAC0, saves, morale, XP, encumbrance, initiative, the explored map, character creation, advancement) are the engine's; narration and freeform-intent adjudication are the LLM's, governed by the shared [constitution](skills/referee/references/constitution.md).
- Phase 1 ships one native adventure (`server/src/osrlib_referee_mcp/content.py`): a one-level barrow crypt with a scripted delve — enter, light a torch, spring a trap, fight, flee, and return to town — proven by an in-process golden test (`server/tests/test_delve_golden.py`) driving the real server tool functions.
- Phase 2 adds **adventure bundles**: a compiled module is an on-disk directory (`adventure.json` + `prose.json` + `manifest.json`) that the same tools load and play like native content. The `compile-adventure` skill turns a written module into a bundle — transcribing its map to the grid, splitting read-aloud text from referee notes, and **reskinning** any non-SRD creature to its nearest stock SRD template (logged in the manifest's approximation audit). A bundle carries **no custom catalog**: every id resolves against the stock SRD, so there is no engine change and no change to how the `play` skill behaves. `adventures/sunken_chapel/` is a compiled original demo module.

See the spec for the architecture, the token-efficiency thesis, the content-ingestion strategy, and the licensing boundaries.

## Playing

Inside a Claude Code session with this plugin loaded (see "Running locally" below), the `referee` skill is the front door: it asks whether you want to create characters, start a new adventure, or continue a saved game, and routes to the skill that does it. The reconciled skill graph:

- **`referee`** — the thin entry point and router; it resolves the chosen adventure (routing an uncompiled module through `compile-adventure` first) and hands off, but runs no play, creation, or persistence itself.
- **`character`** — deterministic, seeded party creation over the `chargen` CLI; the engine rolls every ability score, hit-point total, and gold piece.
- **`play`** — the turn loop: exploration, encounters, battle, the town economy, and level-up narration, in one skill.
- **`session`** — save, resume with a recap, an optional human-readable journal, and the roll-log audit.
- **`compile-adventure`** — the build-time module compiler (unchanged from Phase 2).
- All four play-facing skills share one [constitution](skills/referee/references/constitution.md).

The **full campaign lifecycle** runs end-to-end: make a deterministic party, start a native or compiled adventure, delve, return to town and buy/sell/heal, cross a level threshold (engine-automatic, narrated), save, resume in a later session with a recap, and ask to see the roll-log.

Saves persist to `<game-root>/adventures/<adventure-id>/<save-id>.json` and built parties to `<game-root>/parties/<party-id>.json`. `<game-root>` defaults to `~/osr-games` (never the plugin cache) and is overridable via the `OSRLIB_REFEREE_GAME_ROOT` environment variable — the same game-directory convention `bx-referee` uses.

## Making a party

Character creation is a deterministic, seeded CLI kept **off** the play tool surface (the same discipline as the compiler). The `character` skill drives it conversationally, but you can run it directly:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42                       # scores + the eligible-class menu
uv run --project server python -m osrlib_referee_mcp.chargen build --seed 42 --class fighter \
  --alignment lawful --buy sword --buy chainmail --equip sword --equip chainmail --name Brakka --out brakka.json
uv run --project server python -m osrlib_referee_mcp.chargen party --out heroes brakka.json wynn.json
```

The **seed carries the whole roll state** — `roll` shows the scores the seed determines and the classes they make legal; `build` re-derives the same scores, then rolls hit points and gold once the class is known, and finalizes. Same seed + same choices ⇒ byte-identical character. A "reroll" is simply a fresh seed, which is what makes it auditable. Static play references — the equipment catalog and prices, the temple services, class XP thresholds, and the save list — come from a second CLI kept off the play surface:

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog     # ids, names, cost_gp, lot sizes, damage
uv run --project server python -m osrlib_referee_mcp.gametool services     # the six temple services and prices
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter
uv run --project server python -m osrlib_referee_mcp.gametool saves        # the resume menu
```

## Compiling a module

The `compile-adventure` skill turns a written module (PDF or Markdown) into a bundle. It leans on a deterministic helper CLI kept **off** the play tool surface — so it costs play sessions nothing — for the correctness-critical steps:

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool render-map adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
```

A compiled bundle for an openly-licensed or original module commits to `adventures/`; a bundle for a non-open module stays private in `<game-root>/bundles/` and is never committed (see the Licensing section of `AGENTS.md`). Every keyed id resolves against the stock SRD catalog — bundles inject no custom content.

## Parity with bx-referee

Phase 3's definition of done is **feature parity with `bx-referee`** for native and compiled content. This scorecard walks its player-facing surface and marks each feature honestly — reproduced, delivered *better* by the engine, or an engine-limited gap. The divergences are stated, never faked in prose.

### Reproduced

| Feature | How |
|---|---|
| The play loop (exploration, encounters, battle) | Phases 1–2: one `play` skill; the engine's default monster-action policy resolves the enemy side. |
| Character creation (full step flow) | Deterministic, seeded `chargen` CLI over osrlib's stepwise creation functions — the engine rolls every score, HP total, and gold piece. |
| Adventure lifecycle (new / resume / save / recap) | `session_new` / `session_load` / `session_save` plus `gametool saves` enumeration and the cold-`observe` recap tail. |
| Town economy (buy / sell / heal / depart) | The `TOWN`-gated `PurchaseEquipment` / `SellTreasure` / `PurchaseHealing` / `EnterDungeon` commands, with prices from `gametool`. |
| Level-up | Engine-automatic on any XP award; the `play` skill narrates the advance by inference from `XpAwardedEvent.level_after`. |
| The character sheet | `character_sheet(character_id)` materializes the full derived sheet (THAC0, AC, saves, movement, spell slots) on demand. |

### Engine-divergent (documented)

| Feature | The divergence |
|---|---|
| Level-up HP | osrlib adds the rolled HP to both max and current but **heals no existing damage** — a wounded character who levels is still wounded. `bx-referee` sets current HP to full. The `play` skill narrates osrlib's behavior. |
| Level-up cap | One level **per award** (engine-clamped), not one per session (skill-enforced in `bx-referee`); no separate level-up step — the `play` skill narrates it in place. |
| Creation house rules | osrlib rolls **3d6 in order** only — no 4d6-drop-lowest, no max-HP-at-1, no in-place single-ability reroll. A "reroll" is a fresh seed (auditable). Supporting other methods is a deferred engine change. |
| Treasure XP | **Parity-plus:** the engine awards treasure XP (1 gp recovered = 1 XP) automatically on the return trip. `bx-referee` never implements it. |
| Roll transparency | **Parity-plus:** the engine records every roll, and `session_audit` surfaces the real trajectory. `bx-referee` has no roll-log and resolves rolls silently. |

### Play a published module — reproduced *via compile* (the consequential divergence)

`bx-referee` points at a module PDF/MD and **reads it live every session** (the LLM is the rules authority). osrlib-referee **compiles the module once** into a deterministic bundle, then plays the bundle — the same "bring your own module" outcome by a different route. The trade, stated honestly:

- **Gained:** determinism, replayability, and amortized cost (compile once vs. re-read per visit).
- **Paid:** an explicit compile step, and **SRD-only fidelity** — non-SRD creatures are reskinned to their nearest SRD template, geometry is approximated to the grid, and novel beats go to the authorial escape hatch (all logged in the bundle's approximation manifest).
- **The real coverage gap:** a module whose central creature's *mechanics are the encounter* and which no SRD template approximates **cannot be faithfully compiled** until the deferred injectable-catalog engine change. For that class of module, `bx-referee` — which can narrate any creature freehand — is strictly more capable today. Naming this is the point.

### Out of scope (out of scope for bx-referee too)

Retainers / henchmen / mercenaries in the party, banking / vaults, training-for-levels, paid town identification, a generic shop/service catalog, and strongholds / domain / mass / ship combat. No engine command surfaces these; each is the authorial escape hatch or narrative-only, and `bx-referee` scopes most of them out as well.

## Token measurement

Phase 1's thesis is that moving mechanics and state into `osrlib` collapses the token overhead `bx-referee` spends re-deriving combat math and re-reading SRD pages, while preserving the narration budget. Proving that requires counting both sides with one tokenizer. The osrlib-referee side is fully automated and captured in-repo:

```bash
uv run --project server python server/scripts/capture_token_artifacts.py --out-dir /path/to/artifacts
```

This dumps the exact standing-cost artifacts — the `AnyCommand` union's input schema, every tool's output schema, and representative `observe()` payloads at town/exploring/battle — to JSON. **It does not tokenize them.** No Anthropic `count_tokens` access or tokenizer library was available in the environment Phase 1 was built in, and a mismatched local tokenizer (`tiktoken`, built for OpenAI models) would produce a number that can't be honestly compared to a `bx-referee` transcript counted a different way. The recorded verdict — the actual per-turn and cumulative token counts, the matched `bx-referee` baseline, and the comparison — is a follow-on: author the baseline, capture its transcript the same way, and run both through one Anthropic `count_tokens` pass. See `docs/phase-1-plan.md`, work item 9, for the full methodology.

## Requirements

- Python ≥ 3.14 and [`uv`](https://docs.astral.sh/uv/) on `PATH`.
- One-time install: `uv sync --project server`. This builds `server/.venv` from the committed lockfile so the plugin's first launch doesn't pay a cold dependency resolve.

## Running locally

```bash
claude --plugin-dir .
```

This loads the plugin (skills + the bundled `osrlib` MCP server) for the session only. The `.mcp.json` launch mechanism is `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp` — confirmed on a clean profile in the Phase 0 packaging spike (see `docs/phase-0-plan.md`, work item 7): no PATH issues, no cold-start timeout even against a fully empty `uv` cache, and the exposed tool name matches `mcp__plugin_osrlib-referee_osrlib__execute` exactly. That verdict covers the `--plugin-dir` dev-loading path only; an installed plugin with a read-only plugin root remains untested and is a distribution-phase concern.

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).
