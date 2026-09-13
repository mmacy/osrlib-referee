# osrlib-referee

osrlib-referee is a Claude Code plugin that runs B/X (Basic/Expert) tabletop RPG sessions with Claude as the referee. You play in the terminal, in plain English. Claude describes the rooms, voices the NPCs, and rules on whatever you try. A rules engine called [`osrlib`](https://pypi.org/project/osrlib/) rolls every die and tracks every hit point, so the dice are real and you can ask to see every roll. The rules are those of the [Old-School Essentials System Reference Document](https://oldschoolessentials.necroticgnome.com/srd/), an open restatement of the 1981 B/X rules.

## What you need

- [Claude Code](https://code.claude.com/docs/en/overview), Anthropic's command-line coding agent. The plugin runs inside it.
- [`uv`](https://docs.astral.sh/uv/getting-started/installation/), which runs the plugin's rules engine. You don't need to install Python yourself. The engine needs Python 3.14 or later, and `uv` downloads it if your machine doesn't have it.

## Install

In Claude Code, add this repository as a plugin marketplace, then install the plugin from it:

```text
/plugin marketplace add mmacy/osrlib-referee
/plugin install osrlib-referee@osrlib-referee
```

Restart Claude Code and the plugin loads in every session. The first launch after installing takes a few seconds longer while `uv` fetches the engine's dependencies. To update later, run `/plugin marketplace update osrlib-referee` and then `/plugin update osrlib-referee@osrlib-referee`.

## Play

Type the referee's slash command, or say you'd like to play a B/X game:

```text
/osrlib-referee:referee
```

The referee asks whether you want to create characters, start a new adventure, or continue a saved game.

**Characters.** You can skip this step. Every new adventure comes with a ready-made party of three: a fighter, a cleric, and a thief. If you'd rather make your own, the referee walks you through it the B/X way: roll 3d6 in order for each ability, pick a class your scores allow, pick an alignment, buy gear, and name your character. The engine only knows 3d6 in order, so there's no 4d6-drop-lowest and no rerolling a single bad score. If you want a reroll, you start the character over.

**Adventures.** Two come with the plugin. *The Barrow Crypt* is a short one-level crypt outside town. *The Sunken Chapel of Neth* is an original module for 3-5 characters of levels 1-2. You can also bring a published module of your own. See "Bring your own module" below.

**Playing.** Say what your character does. Claude describes what happens and runs the rules through the engine: exploring, encounters, combat, morale, light, encumbrance, and the rest. Back in town you can buy and sell gear and pay the temple for healing. When the party returns to town, the engine awards XP for the monsters you defeated and the treasure you brought back (1 XP per gold piece), and a character who crosses a threshold levels up on the spot.

**Saving.** Ask to save at any point. To pick up later, choose "continue a saved game" and the referee recaps where you left off. You can also ask to see the roll log at any time: every die the engine rolled and what came of it.

Your saves and characters live in `~/osr-games`, which the plugin creates the first time it needs it. To keep them somewhere else, set the `OSRLIB_REFEREE_GAME_ROOT` environment variable to another folder.

## Bring your own module

The referee can run a published module, but it doesn't read the PDF during play. Instead, you compile the module once into a *bundle* the engine can run, and every session after that plays from the bundle. To start, point the referee at the module's PDF or Markdown file when it asks which adventure to play. The `compile-adventure` skill takes it from there. It shows you the map to check before the bundle is accepted, and tells you everything it had to approximate.

Compiling changes a few things:

- The engine only knows the monsters and items in the OSE SRD. A creature that isn't in the SRD is played as the closest SRD monster, described the way the module describes it. The compiler records every such swap.
- The map is redrawn on a square grid. Caves and odd shapes get approximated.
- A puzzle, a custom magic item, or a creature whose special ability is the whole fight has no engine rule to run. The compiler flags those, and Claude runs them during play, rolling dice through the engine as needed.

If a module's centerpiece is a creature that no SRD monster resembles, the bundle won't do it justice. That's the one kind of module this plugin doesn't handle well yet.

A bundle compiled from an openly licensed or original module can be shared, and is welcome in this repository's `adventures/` folder. A bundle compiled from a commercial module contains the module's text, so keep it to yourself. The compiler puts it in `~/osr-games/bundles/`, and it's never committed here.

## How it works

The `osrlib` engine runs as a Model Context Protocol (MCP) server that Claude Code starts with the plugin. The engine keeps the whole game state and handles every mechanic: dice, to-hit rolls, saving throws, morale, initiative, XP, encumbrance, the map you've explored, character creation, and advancement. Claude doesn't do the math. It sends your action to the engine as a command, gets back what happened, and narrates. That's what makes the dice real, the roll log complete, and a saved game pick up exactly where it stopped.

A few things work differently from what a house-ruled table might expect:

- Leveling up adds the new hit die to your maximum and current hit points but doesn't heal damage you've already taken.
- You gain at most one level per XP award.
- Ability scores are 3d6 in order, no exceptions.
- Treasure XP is automatic: 1 XP per gold piece of treasure the party brings back to town.

Some parts of B/X aren't in the engine at all: hirelings and retainers, banks, training to gain a level, paying to identify items, strongholds, domain management, and mass or ship combat. Claude can narrate them, but there are no rules behind them.

## For contributors

Clone the repository and load the plugin from the clone instead of installing it:

```bash
claude --plugin-dir /path/to/osrlib-referee
```

That loads the skills and the bundled MCP server for that session only, from whatever folder you're in. Both ways of loading the plugin have been checked: `--plugin-dir` on a clean profile with no `server/.venv` and an empty `uv` cache (see work item 7 of `docs/phase-0-plan.md`), and a marketplace install, where the plugin lands under `~/.claude/plugins/cache/` and the server starts from there.

Everything the referee does outside of play runs as a command-line tool in the `server` project, so a play session doesn't pay for it: `chargen` (character creation), `gametool` (the equipment catalog, temple services, XP thresholds, and the list of saved games), and `bundletool` (bundle validation, map rendering, and reading module text from a [shelf-of-holding](https://github.com/mmacy/shelf-of-holding) index, read-only, with `SHELF_DB` pointing at a snapshot if you want one). For example:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen roll --seed 42
uv run --project server python -m osrlib_referee_mcp.gametool catalog
uv run --project server python -m osrlib_referee_mcp.bundletool validate adventures/sunken_chapel
```

`AGENTS.md` is the contributor guide. `docs/spec.md` is the design and roadmap, and `docs/phase-N-plan.md` records each phase's build. Phases 0 through 3 are done. Two follow-ons from Phase 1 remain: the token-cost comparison against [`bx-referee`](https://github.com/mmacy/osr-plugins), for which `server/scripts/capture_token_artifacts.py` captures this side of the data (see work item 9 of `docs/phase-1-plan.md`), and a manual play-through that confirms the tool names live (see the "Corrections found during implementation" section of `docs/phase-1-plan.md`).

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).

osrlib-referee is an independent project, not affiliated with or endorsed by Necrotic Gnome. "Old-School Essentials" is a trademark of Necrotic Gnome, used here only to identify the source document its rules come from. osrlib-referee makes no claim of compatibility.
