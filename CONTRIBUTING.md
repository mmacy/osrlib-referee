# Contributing to osrlib-referee

The design, the tool surface, the invariants, and the phased roadmap are in [`docs/spec.md`](docs/spec.md). The plan for each phase that has shipped is in [`docs/phase-0-plan.md`](docs/phase-0-plan.md), [`docs/phase-1-plan.md`](docs/phase-1-plan.md), [`docs/phase-2-plan.md`](docs/phase-2-plan.md), and [`docs/phase-3-plan.md`](docs/phase-3-plan.md), and [`docs/phase-3-manual-test.md`](docs/phase-3-manual-test.md) is the checklist for playing the full campaign lifecycle through the plugin by hand. [`AGENTS.md`](AGENTS.md) covers how work lands in this repository: the toolchain, the plan-then-implement loop, the review loop, and licensing.

## Running from a clone

To work on the plugin, load it from your checkout instead of the installed copy:

```bash
claude --plugin-dir .
```

Claude Code loads the plugin from the checkout for that session only, so your edits to the skills and the server are what runs. You can also pass the checkout's path instead of the dot and run the command from any folder. The first time you launch it, `uv` builds `server/.venv` from the committed lockfile. In a test with an empty `uv` cache, that took about 12 seconds, and the server was ready before the first tool call. To build the environment ahead of time and see any install error before you start a session, run this once:

```bash
uv sync --project server
```

## Running the tools by hand

The skills run three command-line tools through `uv`, and you can run them yourself from the checkout.

### Character creation

The `character` skill drives `chargen`, which rolls from a seed. `roll` shows the ability scores the seed produces and the classes those scores allow. `build` produces the same scores again, then rolls hit points and gold for the class you chose, and writes the finished character. `party` writes finished characters to the game root as a party:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42                       # scores + the eligible-class menu
uv run --project server python -m osrlib_referee_mcp.chargen build --seed 42 --class fighter \
  --alignment lawful --buy sword --buy chainmail --equip sword --equip chainmail --name Brakka --out brakka.json
uv run --project server python -m osrlib_referee_mcp.chargen party --out heroes brakka.json wynn.json
```

The same seed and the same choices always produce the same character, and `build` records the seed in the character so anyone can reproduce it. A reroll is a new seed.

### Reference tables

`gametool` prints the tables Claude reads during play: the equipment catalog and prices, the temple's healing services, each class's XP thresholds, and the saved games in the game root:

```bash
uv run --project server python -m osrlib_referee_mcp.gametool catalog     # ids, names, cost_gp, lot sizes, damage
uv run --project server python -m osrlib_referee_mcp.gametool services     # the six temple services and prices
uv run --project server python -m osrlib_referee_mcp.gametool thresholds fighter
uv run --project server python -m osrlib_referee_mcp.gametool saves        # the resume menu
```

### Bundles

`bundletool` validates a compiled bundle, renders its map for the review step, computes an edge key, and reads a module's pages out of a shelf-of-holding index:

```bash
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool render-map adventures/<bundle-id>
uv run --project server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-find "isle of dread"
uv run --project server python -m osrlib_referee_mcp.bundletool shelf-text <sha-prefix> --pages 4-16 --out module.md
```

## Compiling a module

The `compile-adventure` skill turns a module (PDF or Markdown) into a *bundle*, a directory of three JSON files: `adventure.json` with the map and keyed areas, `prose.json` with the read-aloud text and referee notes for each area, and `manifest.json`. [`skills/compile-adventure/references/bundle-format.md`](skills/compile-adventure/references/bundle-format.md) pins the exact shapes. Every session after the compile plays from the bundle, so a module costs one compile instead of a re-read per session, and the same module plays the same way every time.

Claude does the reading and the judgment calls. For the steps where a mistake would corrupt the bundle, it runs `bundletool`: every edge key comes from `edge-key`, never by hand, `validate` checks the bundle against the engine's content model, and `render-map` produces the map for the review step. A bundle isn't done until both review gates pass: `validate` reports no problems, and the user has compared the rendered map with the module's map and accepted it.

A bundle is SRD-only. Every keyed template and item id resolves against the stock SRD catalog, so a bundle adds no custom content and needs no engine change. Claude reskins a creature that isn't in the SRD to its nearest SRD template, squares a map that isn't on the 10-foot grid to one, and sends a scene the rules can't express to the referee's escape hatch. The manifest's approximation log lists every one of these changes. `adventures/sunken_chapel/` is a compiled original module with its source document alongside it as an example.

If you have a [shelf-of-holding](https://github.com/mmacy/shelf-of-holding) index on your machine (a separate project that converts the PDFs in a folder to Markdown, one text per page, and stores them in a SQLite database), `shelf-find` and `shelf-text` read the module's pages out of it instead of paging through the PDF. Both subcommands open the index read-only and never run the `shelf` command, whose subcommands write. Set `SHELF_DB` to a snapshot's path to read that instead of the live database. Without an index, both subcommands say so and exit, and Claude compiles from whatever text the user supplies.

Where the bundle goes depends on the module's license. A bundle for an openly-licensed or original module goes in the plugin's `adventures/` directory and can be committed. A bundle for any other module goes in `<game-root>/bundles/` and is never committed, because its read-aloud text is the publisher's. For more on that, see the Licensing section of [`AGENTS.md`](AGENTS.md).

## How it's put together

The plugin is a stdio MCP server under `server/`, a `uv` project that keeps a live `osrlib` `GameSession` in memory, plus the skills under `skills/`. The server exposes ten tools: `session_new`, `session_load`, and `session_save` for the lifecycle, `execute` to run one typed command and return the accepted flag, rejections, and events, `observe` for a referee-visibility projection of the current state, `character_sheet` for a member's derived numbers, `session_audit` for the roll and command log, `prose` for an area's read-aloud text and referee notes, and `list_commands` and `list_adventures` for the menus. Character creation, the reference tables, and module compilation run as the command-line tools above instead, so their schemas are never sent to the model during play. The `referee`, `character`, `play`, and `session` skills share one [constitution](skills/referee/references/constitution.md).

osrlib-referee is a sibling of the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin, where the LLM is the rules authority and reads the module live every session. Here the engine is the authority. Work item F of the Phase 3 plan compares the two feature by feature. One comparison is still open: counting the tokens each plugin spends on the same delve. This script writes this project's fixed per-turn costs (the command schema, every tool's output schema, and sample `observe` payloads in town, exploring, and battle) to JSON:

```bash
uv run --project server python server/scripts/capture_token_artifacts.py --out-dir /path/to/artifacts
```

It doesn't count tokens. The comparison needs a matching `bx-referee` transcript of the same delve and one pass over both sides with the Anthropic token-counting API, and work item 9 of the Phase 1 plan describes how to do it.

## Packaging

Claude Code launches the server with the command in `.mcp.json`: `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp`. That command builds `server/.venv` under the plugin root, so the root has to be writable. A tool call has run through all three ways of loading the plugin: the checkout with `--plugin-dir` (work item 7 of the Phase 0 plan, on a clean profile), the GitHub archive with `--plugin-url`, and a marketplace install, where the plugin lands under `~/.claude/plugins/cache/` and the environment builds there. The tool name Claude Code exposes is `mcp__plugin_osrlib-referee_osrlib__execute`, and the same form for the other tools, which is what the skills' `allowed-tools` lists use. The repository is its own marketplace through `.claude-plugin/marketplace.json`, so `/plugin marketplace add mmacy/osrlib-referee` needs no separate catalog.
