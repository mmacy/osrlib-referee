# osrlib-referee

osrlib-referee is a Claude Code plugin that runs a solo B/X (Basic/Expert) tabletop RPG session with Claude as the referee. The [`osrlib`](https://pypi.org/project/osrlib/) engine makes every roll and keeps all game state. Claude narrates the rooms, voices the NPCs, and decides what happens when you try something the rules don't cover. Claude never invents a roll.

The rules are the ones in the [Old-School Essentials System Reference Document](https://oldschoolessentials.necroticgnome.com/srd/), an Open Game Content restatement of the 1981 B/X rules. `osrlib` implements only that document, and so does the plugin.

## Requirements

- [Claude Code](https://code.claude.com/docs/en/overview).
- [`uv`](https://docs.astral.sh/uv/) on your `PATH`. The plugin's server needs Python 3.14, and `uv` downloads it the first time it runs the server if you don't have it.

## Trying it for one session

To play without installing anything, start Claude Code with the plugin fetched from this repository:

```bash
claude --plugin-url https://github.com/mmacy/osrlib-referee/archive/refs/heads/main.zip
```

Claude Code downloads the archive and loads the plugin for that session only. The first tool call waits while `uv` builds the server's environment. In a test with a warm `uv` cache, that call answered about 17 seconds after launch. Every session started this way downloads and builds again, so install the plugin once you know you'll keep playing.

## Installing it

Inside Claude Code, add this repository as a plugin marketplace and install the plugin from it:

```text
/plugin marketplace add mmacy/osrlib-referee
/plugin install osrlib-referee@osrlib-referee
```

Claude Code copies the plugin under `~/.claude/plugins/cache/` and loads it in the current session and every later one. After a session starts, Claude Code checks the marketplace for a newer version and tells you when one is ready to load.

## Playing

Start with the `referee` skill:

```text
/osrlib-referee:referee
```

Or describe what you want in your own words:

```text
Let's play some B/X. Start a new adventure.
```

Claude asks whether you want to create characters, start a new adventure, or continue a saved game, and then does what you chose. If you start an adventure without building a party, you play a pregenerated one. Two adventures ship with the plugin:

- **The Barrow Crypt** (`barrow_crypt`) - a one-level crypt reached from the town of Threshold. Enter, light a torch, spring a trap, fight, flee, and return to town.
- **The Sunken Chapel of Neth** (`sunken_chapel`) - an original one-level module for characters of levels 1-2, dedicated to the public domain and compiled into the bundle format described under [Playing a published module](#playing-a-published-module).

In play, say what the party does. Claude maps it to an engine command, the engine resolves it, and Claude narrates the result. The engine resolves combat, morale, saving throws, encumbrance, initiative, light, doors, and the map. When your intent has no command (a bluff, a puzzle, a trick), Claude adjudicates it in the fiction and commits the outcome to the engine. A session starts in town, and a delve ends there too. Back in town you can sell treasure, buy equipment, and pay the temple to heal. The engine awards XP for the trip when you arrive, and a character who crosses a threshold levels up in the same award.

To save, ask:

```text
Save the game.
```

Claude reports the save id. To continue later, start the `referee` skill again and choose to continue a saved game. Claude recaps where you left off before play resumes. To see what the dice did, ask:

```text
Show me the roll log.
```

Mid-scene, Claude shows only what your characters could see: their own attacks and saves, XP awards, and outcomes already revealed. In town, at a scene break, or at the end of a session, ask again for the full log, including morale and reaction rolls.

Saves go to `<game-root>/adventures/<adventure-id>/<save-id>.json`, and parties you build go to `<game-root>/parties/<party-id>.json`. The game root is `~/osr-games` unless you set the `OSRLIB_REFEREE_GAME_ROOT` environment variable, and the plugin creates it the first time you start an adventure or build a party.

## Making a party

Choose to create characters when the `referee` skill asks, or say so:

```text
Roll up a party of four.
```

Claude asks you for the choices the rules leave to the player (class from the list your scores allow, alignment, an optional ability adjustment, a starting spell for arcane casters, equipment, and a name) and runs a command-line tool for every roll. The tool rolls ability scores, hit points, and starting gold from a seed it records in the character, so the same seed and the same choices always produce the same character, and a reroll is a new seed. Claude reports the party id when the party is written, and that id is what starts an adventure with it.

## Playing a published module

To play a module of your own, point the `referee` skill at its PDF or Markdown file:

```text
Start a new adventure from ~/modules/my-module.pdf
```

Claude compiles it once with the `compile-adventure` skill into a *bundle*, a directory of three JSON files: the adventure's map and keyed areas, the read-aloud text and referee notes for each area, and a manifest. Every session after that plays from the bundle, so a module costs one compile instead of a re-read per session, and the same module plays the same way every time. Before the adventure starts, Claude renders the compiled map, compares it with the module's map, and you decide at that step whether the compile is close enough.

Claude does the reading and the judgment calls. For the steps where a mistake would corrupt the bundle (the edge keys of the map, the bundle's validation, the map render for your review), it runs a command-line tool. If you have a [shelf-of-holding](https://github.com/mmacy/shelf-of-holding) index on your machine (a separate project that converts the PDFs in a folder to Markdown, one text per page, and stores them in a SQLite database), the same tool reads the module's pages out of it instead of paging through the PDF. It opens the database read-only, and you can set `SHELF_DB` to a snapshot's path to read that instead of the live database. Without an index, Claude compiles from whatever text you give it.

Where the bundle goes depends on the module's license. A bundle for an openly-licensed or original module goes in the plugin's `adventures/` directory and can be committed to this repository. A bundle for any other module goes in `<game-root>/bundles/` and stays there, because its read-aloud text is the publisher's. For more on that, see the Licensing section of [`AGENTS.md`](AGENTS.md).

## What to expect from the engine

The engine has rules only for the monsters, items, and mechanics in the SRD, and a few of its rules differ from what a referee at the table would do.

- **Character creation is 3d6 in order.** The engine rolls abilities that way and no other way, and the referee's rules say not to fake a different method, so there's no 4d6-drop-lowest, no maximum hit points at first level, and no reroll of a single score. A reroll is a new seed.
- **Leveling up doesn't heal.** The engine adds the new hit die to both maximum and current hit points, so a wounded character who levels is still wounded.
- **One level per award.** An XP award that would cross two thresholds stops 1 XP short of the second, and the character gains one level.
- **Treasure XP is automatic.** When the party returns to town, the engine compares what the party is carrying with what it left with and awards 1 XP per gold piece gained, plus the XP for monsters defeated, split evenly among the living members. If the whole party dies, there's no award.
- **A compiled module is SRD-only.** At compile time, Claude replaces a creature that isn't in the SRD with the nearest SRD monster, squares a map that isn't on a 10-foot grid to one, and leaves a scene the rules can't express for live adjudication. The bundle's manifest lists every one of these changes. A module whose central monster has no SRD counterpart, where swapping in a stock monster would lose what the fight is about, can't be compiled faithfully.
- **Not supported.** Retainers, henchmen, and mercenaries in the party. Banking and vaults. Training for levels. Paid identification of magic items. Shops and services beyond the equipment catalog and the temple. Strongholds, domain play, mass combat, and ship combat. The engine has no commands for any of these. Claude can narrate them, but no rule in the engine resolves them.

## For contributors

The design, the tool surface, the invariants, and the phased roadmap are in [`docs/spec.md`](docs/spec.md). The plan for each phase that has shipped is in [`docs/phase-0-plan.md`](docs/phase-0-plan.md), [`docs/phase-1-plan.md`](docs/phase-1-plan.md), [`docs/phase-2-plan.md`](docs/phase-2-plan.md), and [`docs/phase-3-plan.md`](docs/phase-3-plan.md), and [`docs/phase-3-manual-test.md`](docs/phase-3-manual-test.md) is the checklist for playing the full campaign lifecycle through the plugin by hand. [`AGENTS.md`](AGENTS.md) covers how work lands in this repository: the toolchain, the plan-then-implement loop, and licensing.

### Running from a clone

To work on the plugin, load it from your checkout instead of the installed copy:

```bash
claude --plugin-dir .
```

Claude Code loads the plugin from the checkout for that session only, so your edits to the skills and the server are what runs. You can also pass the checkout's path instead of the dot and run the command from any folder. The first time you launch it, `uv` builds `server/.venv` from the committed lockfile. In a test with an empty `uv` cache, that took about 12 seconds, and the server was ready before the first tool call. To build the environment ahead of time and see any install error before you start a session, run this once:

```bash
uv sync --project server
```

### Running the tools by hand

The skills run three command-line tools through `uv`, and you can run them yourself from the checkout. The character creation tool rolls from a seed: `roll` shows the ability scores the seed produces and the classes those scores allow, `build` produces the same scores again, then rolls hit points and gold for the class you chose, and writes the finished character, and `party` writes finished characters to the game root as a party:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42                       # scores + the eligible-class menu
uv run --project server python -m osrlib_referee_mcp.chargen build --seed 42 --class fighter \
  --alignment lawful --buy sword --buy chainmail --equip sword --equip chainmail --name Brakka --out brakka.json
uv run --project server python -m osrlib_referee_mcp.chargen party --out heroes brakka.json wynn.json
```

The reference tool prints the tables Claude reads during play: the equipment catalog and prices, the temple's healing services, each class's XP thresholds, and your saved games:

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog     # ids, names, cost_gp, lot sizes, damage
uv run --project server python -m osrlib_referee_mcp.gametool services     # the six temple services and prices
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter
uv run --project server python -m osrlib_referee_mcp.gametool saves        # the resume menu
```

The bundle tool validates a compiled bundle, renders its map for the review step, computes an edge key, and reads a module's pages out of a shelf-of-holding index. The two `shelf` subcommands open the index read-only and never run the `shelf` command, whose subcommands write:

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool render-map adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-find "isle of dread"
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-text <sha-prefix> --pages 4-16 --out module.md
```

### How it's put together

The plugin is a stdio MCP server under `server/`, a `uv` project that keeps a live `osrlib` `GameSession` in memory, plus the skills under `skills/`. The server exposes ten tools: `session_new`, `session_load`, and `session_save` for the lifecycle, `execute` to run one typed command and return the accepted flag, rejections, and events, `observe` for a referee-visibility projection of the current state, `character_sheet` for a member's derived numbers, `session_audit` for the roll and command log, `prose` for an area's read-aloud text and referee notes, and `list_commands` and `list_adventures` for the menus. Character creation, the reference tables, and module compilation run as the command-line tools above instead, so their schemas are never sent to the model during play. The `referee`, `character`, `play`, and `session` skills share one [constitution](skills/referee/references/constitution.md).

osrlib-referee is a sibling of the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin, where the LLM is the rules authority and reads the module live every session. Here the engine is the authority. Work item F of the Phase 3 plan compares the two feature by feature. One comparison is still open: counting the tokens each plugin spends on the same delve. This script writes this project's fixed per-turn costs (the command schema, every tool's output schema, and sample `observe` payloads in town, exploring, and battle) to JSON:

```bash
uv run --project server python server/scripts/capture_token_artifacts.py --out-dir /path/to/artifacts
```

It doesn't count tokens. The comparison needs a matching `bx-referee` transcript of the same delve and one pass over both sides with the Anthropic token-counting API, and work item 9 of the Phase 1 plan describes how to do it.

Claude Code launches the server with the command in `.mcp.json`: `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp`. That command builds `server/.venv` under the plugin root, so the root has to be writable. A tool call has run through all three ways of loading the plugin: the checkout with `--plugin-dir` (work item 7 of the Phase 0 plan, on a clean profile), the GitHub archive with `--plugin-url`, and a marketplace install, where the plugin lands under `~/.claude/plugins/cache/` and the environment builds there. The tool name Claude Code exposes is `mcp__plugin_osrlib-referee_osrlib__execute`, and the same form for the other tools, which is what the skills' `allowed-tools` lists use. The repository is its own marketplace through `.claude-plugin/marketplace.json`, so `/plugin marketplace add mmacy/osrlib-referee` needs no separate catalog.

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).

osrlib-referee is an independent project, not affiliated with or endorsed by Necrotic Gnome. "Old-School Essentials" is a trademark of Necrotic Gnome, used here only to identify the source document its rules come from. osrlib-referee makes no claim of compatibility.
