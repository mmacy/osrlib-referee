# osrlib-referee

An MCP-enabled B/X tabletop RPG referee. It runs Old-School Essentials sessions where the deterministic [`osrlib`](https://pypi.org/project/osrlib/) engine owns every roll, stat, and state transition behind an MCP server, and the LLM spends its tokens on fiction — narrating rooms, voicing NPCs, and adjudicating freeform player intent.

This is a sibling to, not a replacement for, the [`bx-referee`](https://github.com/mmacy/osr-plugins) plugin. `bx-referee` makes the LLM the rules authority; `osrlib-referee` inverts that — the engine is the authority, the LLM is the narrator.

## Status

Phase 0 (scaffolding and the packaging spike) is done. Phase 1 (proving the loop on native content) is done, with one deferred piece: the delve is playable end-to-end through the real MCP tool surface, the test ladder is green, and the `play` skill and constitution are written — but the comparative token measurement against `bx-referee`, and the manual `claude --plugin-dir .` play-through that confirms the exposed tool names live, remain a follow-on (see "Token measurement" below and `docs/phase-1-plan.md`'s "Corrections found during implementation" section). Phase 2 (content ingestion) is next. The decision-complete design and phased roadmap live in [`docs/spec.md`](docs/spec.md); the phase build records, including the packaging spike's and Phase 1's recorded verdicts, are in `docs/phase-0-plan.md` and [`docs/phase-1-plan.md`](docs/phase-1-plan.md).

## How it works

- A stdio MCP server holds a live `osrlib` `GameSession` in-process. Four tools carry the whole loop: `execute(command)` runs one typed command from the `AnyCommand` union and returns `{accepted, rejections, events}`; `observe()` returns a scoped, referee-visibility projection of current state (never the raw save document); `prose(area_id)` returns the authored read-aloud/referee-notes sidecar; `session_new`/`session_load`/`session_save` handle the lifecycle, with saves persisted durably to the user's game directory.
- Mechanics and state (dice, THAC0, saves, morale, XP, encumbrance, initiative, the explored map) are the engine's; narration and freeform-intent adjudication are the LLM's, governed by the `play` skill's [constitution](skills/play/references/constitution.md).
- Phase 1 ships one native adventure (`server/src/osrlib_referee_mcp/content.py`): a one-level barrow crypt with a scripted delve — enter, light a torch, spring a trap, fight, flee, and return to town — proven by an in-process golden test (`server/tests/test_delve_golden.py`) driving the real server tool functions.
- Published-module content ingestion (an "adventure bundle" — an `osrlib` `Adventure` spec plus a prose sidecar, compiled from a module PDF) is Phase 2, not yet built.

See the spec for the architecture, the token-efficiency thesis, the content-ingestion strategy, and the licensing boundaries.

## Playing

Inside a Claude Code session with this plugin loaded (see "Running locally" below), the `play` skill drives a session: it calls `session_new`/`session_load` to start or resume, then loops `execute`/`observe`/`prose` for the rest of the session, narrating strictly from what the engine returns.

Saves persist to `<game-root>/adventures/<adventure-id>/<save-id>.json`. `<game-root>` defaults to `~/osr-games` (never the plugin cache) and is overridable via the `OSRLIB_REFEREE_GAME_ROOT` environment variable — the same game-directory convention `bx-referee` uses.

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
