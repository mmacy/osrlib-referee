# osrlib-referee

An MCP-enabled B/X tabletop RPG referee. It runs Old-School Essentials sessions where the deterministic [`osrlib`](https://pypi.org/project/osrlib/) engine owns every roll, stat, and state transition behind an MCP server, and the LLM spends its tokens on fiction — narrating rooms, voicing NPCs, and adjudicating freeform player intent.

This is a sibling to, not a replacement for, the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin. `bx-referee` makes the LLM the rules authority; `osrlib-referee` inverts that — the engine is the authority, the LLM is the narrator.

## Status

Planning. The decision-complete design and phased roadmap live in [`docs/spec.md`](docs/spec.md).

## How it will work

- A stdio MCP server holds a live `osrlib` `GameSession` in-process; skills drive it with typed commands and narrate from the typed events it returns.
- Mechanics and state (dice, THAC0, saves, morale, XP, encumbrance, initiative, the explored map) are the engine's; narration and adjudication are the LLM's.
- Published-module content is compiled into an "adventure bundle" — an `osrlib` `Adventure` spec plus a prose sidecar for the authored read-aloud text the engine has no place for.

See the spec for the architecture, the token-efficiency thesis, the content-ingestion strategy, and the licensing boundaries.

## License

Dedicated to the public domain under [CC0 1.0 Universal](LICENSE).
