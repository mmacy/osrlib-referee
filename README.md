# osrlib-referee

osrlib-referee is a Claude Code plugin that runs B/X (Basic/Expert) tabletop RPG sessions with Claude as the referee. The [`osrlib`](https://pypi.org/project/osrlib/) rules engine makes every roll and keeps all game state. Claude does what a human referee does at the table: it narrates rooms, voices NPCs, and adjudicates whatever you say your character does. The engine runs as a Model Context Protocol (MCP) server that Claude Code starts along with the plugin. `osrlib` implements the [Old-School Essentials System Reference Document](https://oldschoolessentials.necroticgnome.com/srd/), an Open Game Content restatement of the 1981 B/X rules.

## Requirements

- [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's command-line coding agent. The plugin runs inside it.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/), the Python package manager that runs the plugin's server. You don't need to install Python yourself: the server needs Python 3.14 or later, and `uv` downloads it if your machine doesn't have it.
- A clone of this repository.

## Running locally

Launch Claude Code from any folder and point `--plugin-dir` at your clone:

```bash
claude --plugin-dir /path/to/osrlib-referee
```

That loads the plugin (the skills plus the bundled `osrlib` MCP server) for that session only. Launching without `--plugin-dir` doesn't load it. The first launch takes a few seconds longer while `uv` installs the server's dependencies. After that it's fast.

If you're working on the plugin, launch from the repository checkout instead:

```bash
claude --plugin-dir .
```

Claude Code starts the server with `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp`, as `.mcp.json` specifies. That launch was checked on a clean profile (see work item 7 of `docs/phase-0-plan.md`): no `PATH` problems, no cold-start timeout even with no `server/.venv` and an empty `uv` cache, and the exposed tool name is `mcp__plugin_osrlib-referee_osrlib__execute`, as expected. That check covers loading with `--plugin-dir` only. An installed plugin with a read-only plugin root is untested, and is a concern for when the plugin is distributed.

## Playing

In a Claude Code session with this plugin loaded (see "Running locally" above), the `referee` skill is the entry point. To start it, type its namespaced slash command:

```text
/osrlib-referee:referee
```

You can also just say what you want, like "let's play a B/X game" or "continue my saved game". Claude starts the skill on its own when your message matches its description. Either way, the skill asks whether you want to create characters, start a new adventure, or continue a saved game, then hands off to the skill that does it. The skills:

- **`referee`** - the entry point and router. It resolves the adventure you choose, sends an uncompiled module through `compile-adventure` first, then hands off. It runs no play, creation, or saving itself.
- **`character`** - seeded party creation over the `chargen` CLI. The engine rolls every ability score, hit-point total, and gold piece.
- **`play`** - the turn loop in one skill: exploration, encounters, battle, the town economy, and level-up narration.
- **`session`** - save, resume with a recap, an optional human-readable journal, and the roll-log audit.
- **`compile-adventure`** - the build-time module compiler.
- All four play-facing skills share one [constitution](skills/referee/references/constitution.md).

A whole campaign runs end to end. You make a party, start a native or compiled adventure, explore, return to town to buy, sell, or heal, cross a level threshold (the engine advances the character and Claude narrates it), save, resume in a later session with a recap, and ask to see the roll log.

Saves go to `<game-root>/adventures/<adventure-id>/<save-id>.json` and built parties to `<game-root>/parties/<party-id>.json`. `<game-root>` is your *game directory*, the folder where the plugin keeps everything you make. It's `~/osr-games` by default, never the plugin cache, and the plugin creates it the first time it writes there. To put it somewhere else, set the `OSRLIB_REFEREE_GAME_ROOT` environment variable.

## Making a party

Character creation is a command-line tool kept **off** the play tool surface, like the compiler, so it costs nothing during play. It's *seeded*: you give it a number, and the same number always produces the same rolls. The `character` skill runs it for you in conversation, but you can also run it yourself:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42                       # scores + the eligible-class menu
uv run --project server python -m osrlib_referee_mcp.chargen build --seed 42 --class fighter \
  --alignment lawful --buy sword --buy chainmail --equip sword --equip chainmail --name Brakka --out brakka.json
uv run --project server python -m osrlib_referee_mcp.chargen party --out heroes brakka.json wynn.json
```

The **seed determines every roll**. `roll` shows the ability scores the seed produces and the classes those scores allow. `build` re-derives the same scores, rolls hit points and gold for the chosen class, and produces the finished character. The same seed and the same choices always produce a byte-identical character. A reroll is a new seed, so every character can be traced back to the number that made it. A second command-line tool, `gametool`, prints the static reference tables: the equipment catalog and prices, the temple services, class XP thresholds, and the list of saved games.

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog     # ids, names, cost_gp, lot sizes, damage
uv run --project server python -m osrlib_referee_mcp.gametool services     # the six temple services and prices
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter
uv run --project server python -m osrlib_referee_mcp.gametool saves        # the resume menu
```

## Compiling a module

The `compile-adventure` skill turns a written module (PDF or Markdown) into a bundle. For the steps that have to be exactly right, it uses the `bundletool` command-line tool, which is kept **off** the play tool surface and so costs play sessions nothing:

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool render-map adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
```

The first compile step is getting the module's text. If a [shelf-of-holding](https://github.com/mmacy/shelf-of-holding) index is on the machine, `bundletool` reads the text from it as one Markdown page per PDF page, already converted, instead of paging through the PDF. The index is optional. Both commands are read-only: they open the index through a read-only SQLite connection and never run the `shelf` command, whose subcommands write. Set `SHELF_DB` to read a snapshot instead of the live store.

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-find "isle of dread"
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-text <sha-prefix> --pages 4-16 --out module.md
```

A bundle compiled from an openly licensed or original module can be committed to `adventures/`. A bundle compiled from a module that isn't openly licensed stays private in `<game-root>/bundles/` and is never committed. For the rules, see the Licensing section of `AGENTS.md`. Every keyed id resolves against the stock SRD catalog, so a bundle adds no custom content.

## How it works

- An MCP server keeps a live `osrlib` `GameSession` in memory for the length of your Claude Code session. Its tools cover the whole play loop. `execute(command)` runs one typed command from the `AnyCommand` union and returns `{accepted, rejections, events}`. `observe()` returns the current state, scoped to what the referee may see, never the raw save document. `character_sheet(character_id)` returns the full derived sheet (THAC0, AC, saves, movement, spell slots). `session_audit(...)` returns the recorded rolls and commands. `prose(area_id)` returns the authored read-aloud text and referee notes. `session_new`, `session_load`, and `session_save` start, load, and save a game, and saves are written to your game directory. Everything static or build-time stays **off** the play tool surface and runs as a command-line tool instead (`chargen`, `gametool`, `bundletool`): character creation, the equipment, services, and XP threshold reference tables, the list of saved games, and module compilation. None of those add to the token cost of a turn.
- The engine owns mechanics and state: dice, THAC0, saves, morale, XP, encumbrance, initiative, the explored map, character creation, and advancement. Claude owns narration and the adjudication of freeform intent, under the shared [constitution](skills/referee/references/constitution.md).
- One native adventure ships with the plugin (`server/src/osrlib_referee_mcp/content.py`): a one-level barrow crypt with a scripted delve. You enter, light a torch, spring a trap, fight, flee, and return to town. A golden test (`server/tests/test_delve_golden.py`) plays it through the real server tool functions.
- Published modules play as **adventure bundles**. A bundle is a directory on disk (`adventure.json`, `prose.json`, and `manifest.json`) that the same tools load and play like native content. The `compile-adventure` skill turns a written module into a bundle. It transcribes the map to the grid, splits read-aloud text from referee notes, and *reskins* any creature that isn't in the SRD to its nearest stock SRD template, logging each reskin in the manifest's approximation log. A bundle adds **no custom catalog**, so every id resolves against the stock SRD. That means no engine change and no change to how the `play` skill behaves. `adventures/sunken_chapel/` is a compiled original demo module.

For the architecture, the token-efficiency argument, how content gets into the game, and the licensing boundaries, see [`docs/spec.md`](docs/spec.md).

## Status

Phases 0 through 3 of the roadmap are done, so a whole campaign plays end to end today: seeded character creation and party build (`chargen`), one native adventure and an on-disk **adventure bundle** format for compiled modules, the `compile-adventure` skill with its `validate_bundle` compile gate, a compiled demo module (`adventures/sunken_chapel/`), the **town economy** (buy, sell, heal, depart) with automatic return-trip XP, **engine-automatic level-up** that Claude narrates, **save and resume with a recap**, a **roll-log audit** (`session_audit`), and a skill graph of a `referee` router over `character`, `play`, and `session` sharing one constitution. Two Phase 1 items remain follow-on work: the token comparison against [`bx-referee`](https://github.com/mmacy/osr-plugins), an earlier plugin where Claude, not an engine, is the rules authority (see "Token measurement" below) and a manual `claude --plugin-dir .` play-through that confirms the exposed tool names live (see the "Corrections found during implementation" section of `docs/phase-1-plan.md`). The [parity scorecard](#parity-with-bx-referee) below lists every `bx-referee` feature and marks it reproduced, engine-divergent, or out of scope. The design and phased roadmap are in [`docs/spec.md`](docs/spec.md). The phase build records are in `docs/phase-0-plan.md`, [`docs/phase-1-plan.md`](docs/phase-1-plan.md), [`docs/phase-2-plan.md`](docs/phase-2-plan.md), and [`docs/phase-3-plan.md`](docs/phase-3-plan.md).

## Parity with bx-referee

The goal is **feature parity with `bx-referee`** for native and compiled content. The tables below list each player-facing `bx-referee` feature and mark it reproduced, done differently by the engine (sometimes better, sometimes a gap), or out of scope.

### Reproduced

| Feature | How |
|---|---|
| The play loop (exploration, encounters, battle) | One `play` skill. The engine's default monster-action policy resolves the enemy side. |
| Character creation (full step flow) | The seeded `chargen` CLI over osrlib's stepwise creation functions. The engine rolls every score, HP total, and gold piece. |
| Adventure lifecycle (new / resume / save / recap) | `session_new`, `session_load`, and `session_save`, plus the `gametool saves` list and the recap tail that `observe` returns right after a load. |
| Town economy (buy / sell / heal / depart) | The `PurchaseEquipment`, `SellTreasure`, `PurchaseHealing`, and `EnterDungeon` commands, legal only in town, with prices from `gametool`. |
| Level-up | The engine levels a character up automatically on any XP award. The `play` skill reads the new level from `XpAwardedEvent.level_after` and narrates it. |
| The character sheet | `character_sheet(character_id)` returns the full derived sheet (THAC0, AC, saves, movement, spell slots) on demand. |

### Engine-divergent (documented)

| Feature | The divergence |
|---|---|
| Level-up HP | osrlib adds the rolled HP to both max and current but **heals no existing damage**, so a wounded character who levels is still wounded. `bx-referee` sets current HP to full. The `play` skill narrates what osrlib does. |
| Level-up cap | One level **per award**, enforced by the engine. In `bx-referee` the skill enforces one level per session. There's no separate level-up step: the `play` skill narrates it in place. |
| Creation house rules | osrlib rolls **3d6 in order** only. There's no 4d6-drop-lowest, no maximum HP at level 1, and no reroll of a single ability. A reroll is a new seed, which keeps it auditable. Other methods would need an engine change, which is deferred. |
| Treasure XP | **Better than parity:** the engine awards treasure XP (1 XP per gp recovered) automatically when the party returns to town. `bx-referee` doesn't implement it. |
| Roll transparency | **Better than parity:** the engine records every roll, and `session_audit` returns the log. `bx-referee` has no roll log and resolves rolls silently. |

### Play a published module, reproduced by compiling it

`bx-referee` points at a module PDF or Markdown file and **reads it every session**, because there Claude is the rules authority. osrlib-referee **compiles the module once** into a bundle and then plays the bundle. You still bring your own module, by a different route. The trade:

- **Gained:** determinism, replayability, and lower cost over time, since you compile once instead of re-reading the module every visit.
- **Paid:** an explicit compile step, and **SRD-only fidelity**. Creatures that aren't in the SRD are reskinned to their nearest SRD template, the map is approximated to the grid, and beats the engine has no command for go to the *authorial escape hatch*, where the `play` skill runs them live with the referee's own commands. The bundle's manifest logs all of it.
- **The coverage gap:** a module whose central creature's *mechanics are the encounter*, and which no SRD template approximates, **cannot be compiled faithfully** until the deferred injectable-catalog engine change lands. For that kind of module, `bx-referee`, which can narrate any creature freehand, can do more today.

### Out of scope (out of scope for bx-referee too)

Retainers, henchmen, and mercenaries in the party, banking and vaults, training to gain a level, paid identification in town, a general shop and service catalog, and strongholds, domain management, and mass or ship combat. No engine command covers these. Each is handled through the authorial escape hatch or as narration only, and `bx-referee` scopes most of them out as well.

## Token measurement

The claim behind the project is that moving mechanics and state into `osrlib` cuts the tokens `bx-referee` spends re-deriving combat math and re-reading SRD pages, while leaving the narration budget alone. Proving it means counting both sides with one tokenizer. The osrlib-referee side is automated by a script in the repo:

```bash
uv run --project server python server/scripts/capture_token_artifacts.py --out-dir /path/to/artifacts
```

The script writes the standing-cost artifacts to JSON: the `AnyCommand` union's input schema, every tool's output schema, and representative `observe()` payloads in town, while exploring, and in battle. **It does not count tokens.** A tokenizer built for another vendor's models, like `tiktoken`, would give a number you can't compare with a `bx-referee` transcript counted a different way. The comparison is still to do: the per-turn and cumulative token counts, a matching `bx-referee` baseline, and the result. To produce it, write the baseline, capture its transcript the same way, and run both through one Anthropic `count_tokens` pass. For the full method, see work item 9 of `docs/phase-1-plan.md`.

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).

osrlib-referee is an independent project, not affiliated with or endorsed by Necrotic Gnome. "Old-School Essentials" is a trademark of Necrotic Gnome, used here only to identify the source document its rules come from. osrlib-referee makes no claim of compatibility.
