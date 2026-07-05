# Agent guide for osrlib-referee

osrlib-referee is an MCP-enabled B/X tabletop RPG referee. A stdio MCP server holds a live [`osrlib`](https://pypi.org/project/osrlib/) `GameSession` in-process; thin Claude Code skills keep the LLM on narration and adjudication while the deterministic engine owns every roll and all game state. It is a sibling to the `bx-referee` plugin (in `~/repos/osr-plugins`), not a replacement — `bx-referee` makes the LLM the rules authority; here the engine is.

## Start here

- `docs/spec.md` is the single source of truth. Read it before any implementation work. It is decision-complete: architecture, the MCP tool surface, cross-cutting concerns, a phased roadmap, and pinned decisions. Build in phase order — **Phase 0 first** (it retires the MCP-packaging/PATH risk before any game code).
- The engine is `osrlib` (source at `~/repos/osrlib-python`, published on PyPI as `osrlib`). Its own `AGENTS.md`, `docs/`, and source are authoritative for engine behavior. When a question is about a command, event, view, the content model, or determinism, **read osrlib's source/docs rather than working from memory.** Do not edit osrlib from this repo — engine changes (notably the Phase 2a injectable-catalog work) land as their own PRs in the osrlib repo.
- `bx-referee` and `ironsworn-referee` (in `~/repos/osr-plugins`) are the house patterns for skill authoring. Mirror their voice and structure: a behavioral constitution plus a `play` loop that owns the encounter and battle lifecycles.

## Repository layout

- Plugin root: `.claude-plugin/plugin.json` + `.mcp.json` (launches the bundled server via `${CLAUDE_PLUGIN_ROOT}`, stdio transport) + `skills/`.
- `server/` — the MCP server, a self-contained `uv` project (`pyproject.toml`, `uv.lock`, `src/`, `tests/`). Depends on `osrlib` and an MCP SDK.
- `adventures/` — compiled adventure bundles (an osrlib `Adventure` spec + a prose sidecar). Only openly-licensed or original content is committed here; see Licensing.
- `docs/` — `spec.md` (source of truth) and, once phases begin, `phase-N-plan.md` documents.

## Running locally

```bash
claude --plugin-dir .
```

## Authoritative references

The moving parts below evolve faster than any training data. **Consult the live specifications — do not rely on memory** for wire formats, manifest shapes, or tool-naming rules. Fetch the current version, and where a spec is date- or version-stamped, check for a newer revision before you build against it. These are pointers, not vendored copies; treat them as the source of truth when this guide or the spec disagrees with them on a detail, and reconcile the discrepancy.

- **Model Context Protocol** — [modelcontextprotocol.io](https://modelcontextprotocol.io); the dated specification, e.g. [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) (confirm it's the latest). The authority for transports, the server/tool interface, and message shapes. Also see the MCP SDK docs for the language you implement the server in.
- **Agent Skills** — [agentskills.io](https://agentskills.io) and its [specification](https://agentskills.io/specification). The authority for `SKILL.md` frontmatter (`name`, `description`, `allowed-tools`), the directory contract, and progressive disclosure.
- **Claude Code plugins & MCP** — the official Claude Code documentation (docs.claude.com / code.claude.com) for how a plugin bundles an MCP server: the `.mcp.json` manifest shape, `${CLAUDE_PLUGIN_ROOT}`, stdio transport, and the `mcp__plugin_<plugin>_<server>__<tool>` tool-name format that a skill's `allowed-tools` must match. The Phase 0 packaging/PATH spike depends on getting these current, not remembered.
- **osrlib** — the engine's own docs ([mmacy.github.io/osrlib-python](https://mmacy.github.io/osrlib-python)) and source (`~/repos/osrlib-python`: `AGENTS.md`, `docs/`, `src/`) are authoritative for the command/event/view API, the content model, and determinism. Prefer reading its source over inferring behavior.

## The phase loop

Each roadmap phase in `docs/spec.md` ships as two PRs — a plan, then an implementation — and both follow the same create → rubber-duck → revise-until-solid → PR loop.

### Planning a phase

1. Research first: the phase's spec entry, the prior phase plans, the existing code, and the exact osrlib API surface the phase consumes.
2. Write `docs/phase-N-plan.md`: milestone, scope (in and out), work items, sequencing, definition of done. Decision-complete — every choice an implementer would otherwise guess at is pinned with a rationale.
3. Branch `phase-N-plan`; commit the draft; rubber-duck it; open the PR.

### Implementing a phase

The same loop on `phase-N-impl`: implement to the plan with tests green, rubber-duck the result, address findings. The plan is the contract — if implementation proves it wrong, amend the plan on the same branch so plan and code never diverge.

### The rubber-duck loop

Spawn a fresh subagent as a skeptical senior reviewer. Give it an ordered reading list — the spec, prior plans, this file, the artifact under review, the relevant code, and the exact osrlib source touched — and require evidence: every finding quotes the spec, osrlib source, or the artifact, is ranked blocking vs non-blocking, and the review ends in a verdict (SOLID or NEEDS REVISION) plus a verified-good list of claims it actively checked. Judge findings on the merits — verify disputed osrlib behavior against source yourself and push back on findings that are wrong. Loop until SOLID.

## Toolchain

- Python ≥ 3.14 (osrlib's floor). Package management with `uv` exclusively (`uv add`, `uv sync`, `uv run`) — never `pip`. The server is a `uv` project under `server/`.
- Format with `ruff format`, lint with `ruff check`, test with `pytest` (not unittest). Run the suite before committing.
- Type hints use built-in generics (`list[str]`, `dict[str, int]`). Do not import `List`/`Dict`/`Tuple` from `typing`, and do not use `from __future__ import annotations`.
- Docstrings are Google style, written in Markdown, max line length 120.
- Markdown: blank lines around headings, lists, code blocks, and tables; sentence-case headings; no `---` dividers.

## Design invariants (from the spec)

- **The engine is the source of truth.** Skills never invent a roll, a stat, or an outcome. Every state change goes through `execute()`; narration renders from the returned events (`format_message`, or event codes plus fields), never from the model's own bookkeeping.
- **One `execute` tool over the `AnyCommand` union**, not 44 separate tools. Plus a scoped `observe` (a current-state snapshot — never the raw `RefereeView`, which is the whole save document including the full event log) and `prose(area_id)` for authored read-aloud text.
- **The engine's default monster action policy resolves the enemy side of combat**; skills declare only the party's actions in `ResolveBattleRound`.
- **Authorial commands** (`SetFlag`, `SpawnMonsters`, `SpawnNpcParty`, `GrantItem`, `GrantCoins`, `AwardXP`, `SetDoorState`, `PlaceParty`, `AdvanceTime`) are the sanctioned escape hatch for freeform play the content model can't express: adjudicate the outcome in fiction, then commit it to authoritative state.
- **The player owns mechanical choices.** Present options and wait; never auto-pick.
- **Information discipline.** The `observe` projection carries referee-visibility data (monster HP, hidden rolls); the fiction must not leak it. This is prompt-enforced, not a structural wire boundary — the referee agent is trusted.
- **Saves are durable in the user's game directory** (`~/osr-games/…`), never the plugin cache. The in-memory example store from osrlib's FastAPI example is not inherited.

## Determinism and eval

osrlib guarantees seed + accepted command log ⇒ byte-identical game (under an identical engine version). Preserve that property: record the seed and the command log per session so trajectories can be replayed offline to score runs and regression-test prompt changes. Honor osrlib's contracts — its frozen public API, `schema_version` additivity, and the determinism/replay guarantee.

## Greenfield discipline

Pre-release: there is no frozen public API here yet, so refactor to the better factoring outright and update every call site — tests and CI are the safety net. No back-compat shims, no dual import paths, no deprecation scaffolding, no dead accommodation code. Prose that justifies a design by "so the old path still works" is the tell; if it names no current consumer, the accommodation should not exist.

## Licensing

- The project — code, server, skills, prompts, docs, and compiled *original* content — is dedicated to the public domain under **CC0 1.0 Universal** (see `LICENSE`). The engine it builds on, `osrlib`, is likewise CC0, so there is no code/data license boundary to police within this repo.
- **Adventure-module compilation is a separate, third-party constraint** (nothing to do with this repo's own license): the OSE SRD is openly licensed, but most published commercial adventure modules are not. Compiled adventure bundles — especially the prose sidecar with verbatim read-aloud text — for non-open modules stay **private in the user's game directory** and are never committed. Only openly-licensed or original-authored modules ship in `adventures/`.
