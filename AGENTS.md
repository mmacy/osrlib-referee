# Agent guide for osrlib-referee

osrlib-referee is an MCP-enabled B/X tabletop RPG referee. A stdio MCP server holds a live [`osrlib`](https://pypi.org/project/osrlib/) `GameSession` in-process; thin Claude Code skills keep the LLM on narration and adjudication while the deterministic engine owns every roll and all game state. It is a sibling to the `bx-referee` plugin (in `~/repos/osr-plugins`), not a replacement — `bx-referee` makes the LLM the rules authority; here the engine is.

## Start here

**This guide is durable; the spec is not.** `AGENTS.md` is how we work in this repo, and it outlives any single spec. `docs/spec.md` is the *current* source of truth for **what** to build — a decision-complete design and phased roadmap — but it is a phase-of-life artifact that will be superseded. So this guide points at the current spec instead of restating it: read the spec, build in the order it lays out, and treat its invariants as binding — but do not expect design details, invariants, or phase specifics to be duplicated here, because they would rot the moment the spec turns over.

- **Read `docs/spec.md` first** for the architecture, the tool surface, the invariants, the roadmap, and the pinned decisions. It is the design authority.
- The engine is `osrlib` (source at `~/repos/osrlib-python`, published on PyPI as `osrlib`). Its own `AGENTS.md`, `docs/`, and source are authoritative for engine behavior. When a question is about a command, event, view, the content model, or determinism, **read osrlib's source/docs rather than working from memory.** Do not edit osrlib from this repo — engine changes land as their own PRs in the osrlib repo, and honor osrlib's contracts there: its frozen public API, `schema_version` additivity, and the determinism/replay guarantee.
- `bx-referee` (in `~/repos/osr-plugins`) is the house reference for OSE skill-authoring voice and conventions — a behavioral constitution, information discipline, the game-directory layout. Mirror its style, but mind the architectural inversion: `bx-referee` makes the LLM the rules authority, whereas here the engine is. The "engine owns mechanics, LLM narrates" split comes from osrlib's own design (`llm-referees.md`), not from another plugin.

## Scope

**OSE / B/X only.** osrlib implements the Old-School Essentials (B/X) rules and nothing else, and so does this project. Do not add abstraction layers, configuration, or skills aimed at supporting other rulesets — cross-ruleset generality is out of scope and pure overhead here. Build directly against osrlib's OSE model; do not design for a hypothetical second system.

## Repository layout

- Plugin root: `.claude-plugin/plugin.json` + `.mcp.json` (launches the bundled server via `${CLAUDE_PLUGIN_ROOT}`, stdio transport) + `skills/`.
- `server/` — the MCP server, a self-contained `uv` project (`pyproject.toml`, `uv.lock`, `src/`, `tests/`). Depends on `osrlib` and an MCP SDK.
- `adventures/` — compiled adventure bundles (their format is the current spec's / phase plan's to define, not this file's). Only openly-licensed or original content is committed here; see Licensing.
- `docs/` — the current `spec.md` and, once phases begin, `phase-N-plan.md` documents.

## Running locally

```bash
claude --plugin-dir .
```

## Authoritative references

The moving parts below evolve faster than any training data. **Consult the live specifications — do not rely on memory** for wire formats, manifest shapes, or tool-naming rules. Fetch the current version, and where a spec is date- or version-stamped, check for a newer revision before you build against it. These are pointers, not vendored copies; treat them as the source of truth when this guide or the spec disagrees with them on a detail, and reconcile the discrepancy.

- **Model Context Protocol** — [modelcontextprotocol.io](https://modelcontextprotocol.io); the dated specification, e.g. [2025-11-25](https://modelcontextprotocol.io/specification/2025-11-25) (confirm it's the latest). The authority for transports, the server/tool interface, and message shapes. Also see the MCP SDK docs for the language you implement the server in.
- **Agent Skills** — [agentskills.io](https://agentskills.io) and its [specification](https://agentskills.io/specification). The authority for `SKILL.md` frontmatter (`name`, `description`, `allowed-tools`), the directory contract, and progressive disclosure.
- **Claude Code plugins & MCP** — the official Claude Code documentation (docs.claude.com / code.claude.com) for how a plugin bundles an MCP server: the `.mcp.json` manifest shape, `${CLAUDE_PLUGIN_ROOT}`, stdio transport, and the `mcp__plugin_<plugin>_<server>__<tool>` tool-name format that a skill's `allowed-tools` must match. Getting the plugin-bundled-server packaging right depends on these being current, not remembered.
- **osrlib** — the engine's own docs ([mmacy.github.io/osrlib-python](https://mmacy.github.io/osrlib-python)) and source (`~/repos/osrlib-python`: `AGENTS.md`, `docs/`, `src/`) are authoritative for the command/event/view API, the content model, and determinism. Prefer reading its source over inferring behavior.

## The phase loop

Each roadmap phase in the current spec ships as two PRs — a plan, then an implementation — and both follow the same create → rubber-duck → revise-until-solid → PR loop.

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

## Greenfield discipline

Pre-release: there is no frozen public API here yet, so refactor to the better factoring outright and update every call site — tests and CI are the safety net. No back-compat shims, no dual import paths, no deprecation scaffolding, no dead accommodation code. Prose that justifies a design by "so the old path still works" is the tell; if it names no current consumer, the accommodation should not exist.

## Licensing

- The project — code, server, skills, prompts, docs, and compiled *original* content — is dedicated to the public domain under **CC0 1.0 Universal** (see `LICENSE`). The engine it builds on, `osrlib`, is likewise CC0, so there is no code/data license boundary to police within this repo.
- **Adventure-module compilation is a separate, third-party constraint** (nothing to do with this repo's own license): the OSE SRD is openly licensed, but most published commercial adventure modules are not. Compiled adventure bundles — especially the prose sidecar with verbatim read-aloud text — for non-open modules stay **private in the user's game directory** and are never committed. Only openly-licensed or original-authored modules ship in `adventures/`.
