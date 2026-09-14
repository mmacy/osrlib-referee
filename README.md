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
- **The Sunken Chapel of Neth** (`sunken_chapel`) - an original one-level module for characters of levels 1-2, dedicated to the public domain.

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

Claude asks you for the choices the rules leave to the player (class from the list your scores allow, alignment, an optional ability adjustment, a starting spell for arcane casters, equipment, and a name), and the engine rolls everything else. Claude reports the party id when the party is written, and that id is what starts an adventure with it.

## Playing your own module

To play a module you have as a PDF or Markdown file, point the `referee` skill at it:

```text
Start a new adventure from ~/modules/my-module.pdf
```

Claude compiles the module once into a form the engine can play, and every later session plays from that instead of re-reading the module. Before the adventure starts, Claude shows you the compiled map next to the module's map, and you decide whether it's close enough. A compiled module stays on your machine under `<game-root>/bundles/` unless the module is openly licensed or your own work. For how the compile works and what it changes, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## What to expect from the engine

The engine has rules only for the monsters, items, and mechanics in the SRD, and a few of its rules differ from what a referee at the table would do.

- **Character creation is 3d6 in order.** The engine rolls abilities that way and no other way, and the referee's rules say not to fake a different method, so there's no 4d6-drop-lowest, no maximum hit points at first level, and no reroll of a single score. A reroll is a new set of six.
- **Leveling up doesn't heal.** The engine adds the new hit die to both maximum and current hit points, so a wounded character who levels is still wounded.
- **One level per award.** An XP award that would cross two thresholds stops 1 XP short of the second, and the character gains one level.
- **Treasure XP is automatic.** When the party returns to town, the engine compares what the party is carrying with what it left with and awards 1 XP per gold piece gained, plus the XP for monsters defeated, split evenly among the living members. If the whole party dies, there's no award.
- **A compiled module is SRD-only.** At compile time, Claude replaces a creature that isn't in the SRD with the nearest SRD monster, squares a map that isn't on a 10-foot grid to one, and leaves a scene the rules can't express for live adjudication. A module whose central monster has no SRD counterpart, where swapping in a stock monster would lose what the fight is about, can't be compiled faithfully.
- **Not supported.** Retainers, henchmen, and mercenaries in the party. Banking and vaults. Training for levels. Paid identification of magic items. Shops and services beyond the equipment catalog and the temple. Strongholds, domain play, mass combat, and ship combat. The engine has no commands for any of these. Claude can narrate them, but no rule in the engine resolves them.

## Contributing

To work on the plugin itself, see [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).

osrlib-referee is an independent project, not affiliated with or endorsed by Necrotic Gnome. "Old-School Essentials" is a trademark of Necrotic Gnome, used here only to identify the source document its rules come from. osrlib-referee makes no claim of compatibility.
