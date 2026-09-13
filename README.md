# osrlib-referee

osrlib-referee is a Claude Code plugin that runs B/X (Basic/Expert) tabletop RPG sessions with Claude as the referee. You play in the terminal, in plain English. Claude describes the rooms, voices the NPCs, and rules on whatever you try. A rules engine called [`osrlib`](https://pypi.org/project/osrlib/) rolls every die and tracks every hit point, and you can ask to see every roll. The rules come from the [Old-School Essentials System Reference Document](https://oldschoolessentials.necroticgnome.com/srd/), a free, openly licensed version of the 1981 B/X rules.

## What you need

- [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's command-line coding agent. The plugin runs inside it.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/), which runs the plugin's rules engine. You don't need to install Python yourself. The engine requires Python 3.14 or later, and `uv` downloads it if your machine doesn't have it.

## Install

In Claude Code, add this repository as a plugin marketplace, then install the plugin from it:

```text
/plugin marketplace add mmacy/osrlib-referee
/plugin install osrlib-referee@osrlib-referee
```

Restart Claude Code. From then on, the plugin is available every time you start Claude Code. The first time you (or Claude) invoke `osrlib-referee` after you've installed it, expect a few extra seconds while `uv` fetches the `osrlib` engine's dependencies. To update later, run `/plugin marketplace update osrlib-referee` and then `/plugin update osrlib-referee@osrlib-referee`.

## Play

Type the referee's slash command:

```text
/osrlib-referee:referee
```

Or say what you want in your own words, and Claude should invoke the referee skill on its own:

```text
Let's play some B/X. I'd like to start a new adventure.
```

Either way, the referee asks whether you want to create characters, start a new adventure, or continue a saved game.

**Characters.** You can skip this step. Every new adventure comes with a ready-made party of three: a fighter, a cleric, and a thief. If you'd rather make your own, the referee walks you through it the B/X way: roll 3d6 in order for each ability, pick a class your scores allow, pick an alignment, buy gear, and name your character. The engine builds characters from 3d6 in order, and the referee's rules say not to use any other method, so there's no 4d6-drop-lowest and no rerolling a single bad score. If you want a reroll, you start the character over.

**Adventures.** Two come with the plugin. *The Barrow Crypt* is a short one-level crypt outside town. *The Sunken Chapel of Neth* is an original module for 3-5 characters of levels 1-2. You can also bring a published module of your own. See "Bring your own module" below.

**Playing.** Say what your character does. Claude describes what happens and runs the rules through the engine: exploring, encounters, combat, morale, torches and light, encumbrance, and the rest. Back in town you can buy and sell gear and pay the temple for healing. When the party returns to town, the engine awards XP for the monsters you defeated and the treasure you brought back, and a character with enough experience points gains a level.

**Saving.** Ask to save at any point:

```text
Save the game here.
```

To pick up later, choose "continue a saved game" when the referee asks, or say so:

```text
Continue my Sunken Chapel game.
```

The referee recaps where you left off. You can also ask to see the roll log at any time, every die the engine rolled and what came of it:

```text
Show me the roll log.
```

Your saves and characters live in `~/osr-games`, which the plugin creates for you the first time you start an adventure. To keep them somewhere else, set the `OSRLIB_REFEREE_GAME_ROOT` environment variable to another folder.

## Bring your own module

The referee can run a published module, but it doesn't read the PDF during play. Instead, you compile the module once into a *bundle* the engine can run, and from then on the referee plays from the bundle. To start, point the referee at the module's PDF or Markdown file when it asks which adventure to play. Claude takes it from there with the `compile-adventure` skill. It shows you the map to check and lists everything it had to approximate, and you sign off before it'll use the bundle.

Compiling a module bundle changes a few things:

- The engine has rules only for the monsters and items in the OSE SRD. Claude plays a creature that isn't in the SRD as the closest SRD monster, using the module's description of it, and the bundle keeps a list of every such swap.
- Claude redraws the map on a square grid, so caves and irregular rooms come out squared off.
- The engine has no rule for a puzzle, a custom magic item, or a monster whose special power is the point of the encounter, where swapping in a stock SRD monster would lose what the fight is about. Claude flags those while compiling and runs them by hand during play, rolling dice through the engine as needed.

If a module's centerpiece is a creature that no SRD monster resembles, the bundle won't do it justice. That's the one kind of module this plugin doesn't handle well yet.

You can share a bundle you compiled from an openly licensed or original module, and it's welcome in this repository's `adventures/` folder. A bundle compiled from a commercial module contains the module's text, so keep it to yourself. Claude puts it in `~/osr-games/bundles/`, outside this repository.

## How it works

The `osrlib` engine runs as a Model Context Protocol (MCP) server that Claude Code starts with the plugin. The engine keeps the whole game state and handles every mechanic: dice, to-hit rolls, saving throws, morale, initiative, XP, encumbrance, the map you've explored, character creation, and advancement. Claude doesn't do the math. It sends your action to the engine as a command, gets back what happened, and narrates. That's why no roll is ever made up, why the roll log is complete, and why a saved game picks up exactly where you stopped.

A few things work differently from what you might be used to at the table:

- When you level up, the new hit die goes on both your maximum and your current hit points, but damage you've already taken stays.
- You gain at most one level each time XP is handed out, even if you've earned enough for two.
- Ability scores are 3d6 in order.
- You get treasure XP automatically: 1 XP per gold piece of treasure the party brings back to town.

The engine has no rules for some parts of B/X: hirelings and retainers, banks, training to gain a level, paying to identify items, strongholds, domain management, and mass or ship combat. Claude can still narrate them, but as story, with no rules behind it.

## For contributors

Clone the repository and load the plugin from the clone instead of installing it:

```bash
claude --plugin-dir /path/to/osrlib-referee
```

Claude Code then loads the skills and the bundled MCP server for that session only, from whatever folder you're in. Both ways of loading the plugin were tested: `--plugin-dir` on a clean profile with no `server/.venv` and an empty `uv` cache (see work item 7 of `docs/phase-0-plan.md`), and a marketplace install, which puts the plugin under `~/.claude/plugins/cache/` and starts the server from there.

Everything the referee does outside of play runs as a command-line tool in the `server` project, so none of it adds to the token cost of a play session. There are three: `chargen` for character creation, `gametool` for the equipment catalog, temple services, XP thresholds, and the list of saved games, and `bundletool` for validating a bundle, rendering its map, and reading module text from a [shelf-of-holding](https://github.com/mmacy/shelf-of-holding) index. The tools open the index read-only. Set `SHELF_DB` to point them at a snapshot instead of the live index. For example:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42
uv run --project server python -m osrlib_referee_mcp.gametool catalog
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/sunken_chapel
```

`AGENTS.md` is the contributor guide. `docs/spec.md` is the design and roadmap, and each `docs/phase-N-plan.md` is the build record for one phase. Phases 0 through 3 are done. Two follow-ons from Phase 1 remain: the token-cost comparison against [`bx-referee`](https://github.com/mmacy/osr-plugins), for which `server/scripts/capture_token_artifacts.py` gathers this project's half of the numbers (see work item 9 of `docs/phase-1-plan.md`), and a play-through in Claude Code to confirm the tool names match (see the "Corrections found during implementation" section of `docs/phase-1-plan.md`).

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).

osrlib-referee is an independent project, not affiliated with or endorsed by Necrotic Gnome. "Old-School Essentials" is a trademark of Necrotic Gnome, used here only to identify the source document its rules come from. osrlib-referee makes no claim of compatibility.
