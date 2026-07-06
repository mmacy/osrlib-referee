# osrlib-referee

An MCP-enabled B/X tabletop RPG referee. It runs Old-School Essentials sessions where the deterministic [`osrlib`](https://pypi.org/project/osrlib/) engine owns every roll, stat, and state transition behind an MCP server, and the LLM spends its tokens on fiction — narrating rooms, voicing NPCs, and adjudicating freeform player intent.

This is a sibling to, not a replacement for, the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin. `bx-referee` makes the LLM the rules authority; `osrlib-referee` inverts that — the engine is the authority, the LLM is the narrator.

## Status

Phase 0 (scaffolding and the packaging spike) is done: the `server/` uv project, one `execute` MCP tool over a fixed-seed walking-skeleton session, the plugin skeleton, CI, and the packaging decision below. Phase 1 (the real tool surface and the token-efficiency measurement) is next. The decision-complete design and phased roadmap live in [`docs/spec.md`](docs/spec.md); the Phase 0 build record, including the packaging spike's recorded verdict, is in [`docs/phase-0-plan.md`](docs/phase-0-plan.md).

## How it will work

- A stdio MCP server holds a live `osrlib` `GameSession` in-process; skills drive it with typed commands and narrate from the typed events it returns.
- Mechanics and state (dice, THAC0, saves, morale, XP, encumbrance, initiative, the explored map) are the engine's; narration and adjudication are the LLM's.
- Published-module content is compiled into an "adventure bundle" — an `osrlib` `Adventure` spec plus a prose sidecar for the authored read-aloud text the engine has no place for.

See the spec for the architecture, the token-efficiency thesis, the content-ingestion strategy, and the licensing boundaries.

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
