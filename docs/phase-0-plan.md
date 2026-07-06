# Phase 0 plan — scaffolding and the packaging spike

Implementation plan for Phase 0 of [the osrlib-referee spec](spec.md). Phase 0 stands up the project skeleton — the `server/` uv project, the plugin manifest, one no-op skill, CI — and retires the one risk that can sink the whole architecture: **can a plugin-bundled Python stdio MCP server actually launch inside Claude Code and round-trip a tool call on a clean profile?** It also decides the uv/PATH launch mechanism the rest of the project depends on.

Phase 0 builds no game. It builds the thinnest possible thing that proves the wire works end-to-end, and nothing more — the real tool surface (`observe`, `prose`, lifecycle) and the token thesis are Phase 1.

## The milestone

`execute(a trivial command)` returns a real `osrlib` `CommandResult` envelope to a skill, through the MCP boundary, inside Claude Code, on a clean machine profile — and the packaging/PATH option is chosen from evidence, not guessed.

## Scope

In scope:

- `server/` — a self-contained `uv` project (`pyproject.toml`, `uv.lock`, `src/` layout, `py.typed`, `tests/`, ruff + pytest config) depending on `osrlib` and the `mcp` SDK.
- A minimal, native, fixed-seed `GameSession` fixture built entirely from the installed `osrlib` public API (no `examples/` import — the wheel does not ship it).
- One MCP tool, `execute`, that parses a command payload and runs it against that session, returning the serialized `CommandResult`.
- The plugin skeleton: `.claude-plugin/plugin.json`, `.mcp.json` at the plugin root, and one no-op smoke skill (`ping`) that calls `execute`.
- A three-rung test ladder that verifies the boundary without launching Claude Code (schema-generates, in-process session, in-memory MCP client), plus GitHub Actions CI running ruff + pytest.
- The packaging spike: launch the bundled server inside Claude Code on a clean profile, confirm the exact exposed tool name, characterize cold-start, and **decide the launch option** (with a documented fallback ladder).
- README/prerequisite and licensing touch-ups for the new server + plugin.

Out of scope (later phases, named here so the skeleton does not over-reach):

- The `observe` scoped projection, `prose(area_id)`, and the session lifecycle tools (`session_new`/`session_load`/`session_save`) — **Phase 1**. Phase 0's session is a hardcoded walking skeleton, thrown away when Phase 1 builds real lifecycle.
- Durable saves in the game directory, the `SESSION.md` journal, and any disk persistence — **Phase 1**. Phase 0's session is ephemeral and in-memory.
- Typing the `execute` argument as the full `AnyCommand` union and **measuring the union schema's standing per-turn context cost** — **Phase 1** (the spec pins this as a Phase 1 measurement; Phase 0's tool takes a raw `dict`, see work item 3).
- The pre-session character-build surface (`create_character` → party document) as a *tool* — **Phase 3**. Phase 0 calls `create_character` only internally, to construct the fixture.
- The `OsrlibError` → tool-error mapping taxonomy (`ContentValidationError`/`SaveVersionError`/version handshake) — **Phase 1**, when it has a lifecycle to protect. Phase 0 handles only the unknown-`command_type` case as a result field; a *known* command with a malformed payload raises `ContentValidationError` from `parse_command`, which Phase 0 lets propagate as a tool error — the smoke payload is well-formed so it never fires, and the full map is Phase 1.
- Adventure-module ingestion, the bundle format, and the injectable-catalog engine change — **Phase 2**.
- Listing the plugin in `osr-plugins`' `marketplace.json`. Phase 0 verifies via `claude --plugin-dir .`; distribution is a later concern.
- Publishing the server to PyPI. Phase 0 runs the bundled source in place (see work item 7); a published-package/`uvx` path is a distribution-phase fallback.

## The round-trip we are proving

The engine survey pinned the cheapest genuine boundary crossing. The minimal session is the canonical recipe from osrlib's own `docs/front-ends/llm-referees.md:138-159` — one fighter, a two-cell dungeon with an entrance, a named town — built from installed-package imports only and seeded, so a fixed seed yields a byte-stable session:

- `create_character(name="Hild", class_id="fighter", alignment=Alignment.LAWFUL, ruleset=Ruleset(), stream=RngStreams(master_seed=seed).get(CHARACTER_CREATION_STREAM))`
- a `LevelSpec` (`number=1, width=2, height=1, entrance=(0,0)`, one `edges` entry), a `DungeonSpec`, a `TownSpec`, an `Adventure`, then `GameSession.new(Party(members=[hero.character]), adventure, seed=seed)`.

The session starts in `SessionMode.TOWN` at round 0. Two trivial commands exercise both `CommandResult` branches, and neither needs a dungeon delve, combat, or party bookkeeping:

- **Accepted branch — `SetFlag(key="ping", value=True)`** (`command_type: "set_flag"`). A referee/authorial command legal in every mode; its handler emits one `FlagSetEvent` and returns zero rejections. Result: `accepted=True`, one event. This is the "trivial command" the definition of done names.
- **Rejected branch — `MoveParty(direction=Direction.NORTH)`** (`command_type: "move_party"`). Its `allowed_modes` is `{EXPLORING}`; against the fresh TOWN session it is refused at the pure mode gate before any handler runs. Result: `accepted=False`, `rejections[0].code == "session.command.wrong_mode"`, no RNG consumed, nothing mutated.

A rejection is a normal, valuable result — it proves the envelope carries structured feedback, which is the discipline the whole architecture rests on. `execute` dumps each rejection and event *individually* (see work item 3) into `{accepted, rejections: [{code, params}], events: [{event_type, code, visibility, …}]}`. It must **not** call `model_dump()` on the `CommandResult` container: `CommandResult.events` is typed as the base `Event`, so a container dump serializes only the base fields (`code`, `visibility`) and silently drops `event_type` and every subclass field.

## Work items

### 1. The server uv project

Create `server/` as a standard `uv` src-layout project.

- `server/pyproject.toml`:
  - `[project]` name `osrlib-referee-mcp`, `requires-python = ">=3.14"` (osrlib's floor; the SDK floor is lower and non-binding), `license = "CC0-1.0"`, version `0.1.0`.
  - Runtime dependencies: `osrlib>=1.1,<2` and `mcp>=1.28,<2`. **Pin `mcp` below 2.0** — the SDK's `main` is a `2.0.0b1` pre-release with a different `MCPServer` API; unpinned installs resolve to stable v1.x, and v1 is the maintained line. We target the `mcp.server.fastmcp.FastMCP` API.
  - `[dependency-groups] dev`: `pytest`, `ruff`, `anyio` (the in-memory MCP client test is async; the `anyio` pytest plugin runs it).
  - `[project.scripts] osrlib-referee-mcp = "osrlib_referee_mcp.server:main"` — the console entry point `.mcp.json` invokes. Also ship `src/osrlib_referee_mcp/__main__.py` so `python -m osrlib_referee_mcp` works as a fallback.
  - Build backend `uv_build` (matches osrlib). ruff config mirroring osrlib/the house style: line length 120, Google docstring convention, import ordering stdlib/third-party/local. pytest configured with `[tool.pytest.ini_options] anyio_mode = "auto"` so async tests run without a per-test marker.
- `src/osrlib_referee_mcp/` with `__init__.py`, `py.typed` (this is a typed package from day one), `server.py`, `content.py`, `__main__.py`.
- `.python-version` pinned to `3.14`. `uv.lock` committed (deterministic resolution; also makes clean-profile sync as fast as it can be).
- Smoke-check the deps-resolve contract the spec calls for: `uv sync --project server` succeeds, and `uv run --project server python -c "import osrlib; from osrlib.crawl.commands import AnyCommand; from pydantic import TypeAdapter; TypeAdapter(AnyCommand).json_schema()"` exits 0. This is folded into test work item 4 as an assertion rather than left as a manual step.

### 2. The minimal session fixture — `content.py`

`content.py` owns the fixture and nothing else. It is the Phase 0 stand-in for Phase 1's real lifecycle, and it is deliberately native:

- One public function, `build_session(seed: int = 7) -> GameSession`, implementing the `llm-referees.md:138-159` recipe verbatim (seed `7` matches the recipe) (imports: `Alignment`, `create_character`/`CHARACTER_CREATION_STREAM`, `RngStreams`, `Ruleset`, `Adventure`/`TownSpec`, `DungeonSpec`/`Edge`/`EdgeKind`/`LevelSpec`, `Party`, `GameSession`).
- **Do not import from `examples/`.** The osrlib wheel ships `osrlib/core`, `osrlib/crawl`, and `osrlib/data` only — the `tui_crawler` barrow is repo-only and unavailable to an installed dependency. The fixture is authored against the public content model. (This same constraint governs Phase 1's content choice; surfacing it here saves Phase 1 the discovery.)
- Fixed default seed so the fixture is reproducible and tests can assert on stable output.
- No listeners, no persistence, no quest wiring — the barest session that accepts a command.

### 3. The `execute` tool and the FastMCP server — `server.py`

A single-file FastMCP server holding one session and exposing one tool.

- `mcp = FastMCP("osrlib-referee")`; module-level `_session = build_session()` constructed at import.
- The tool, mirroring the shape the FastAPI example proved (`examples/fastapi_crawler/app.py:147-166`):

  ```python
  @mcp.tool()
  def execute(command: dict) -> dict[str, object]:
      """Parse one command payload and execute it against the session."""
      parsed = parse_command(command)
      if parsed is None:
          return {"accepted": False, "error": "unknown_command_type",
                  "command_type": command.get("command_type")}
      result = _session.execute(parsed)
      return {
          "accepted": result.accepted,
          "rejections": [r.model_dump(mode="json") for r in result.rejections],
          "events": [e.model_dump(mode="json") for e in result.events],
      }
  ```

  **Return annotation correction (found during implementation):** a bare `-> dict` return type gives FastMCP no output schema, so `mcp.types.CallToolResult.structuredContent` comes back `None` — only a JSON-text `content` block round-trips. Confirmed empirically against installed `mcp==1.28.1`: annotating `-> dict[str, object]` makes FastMCP emit an output schema (`{"additionalProperties": true, ...}`) and populate `structuredContent` with the real envelope. Rung 3 (work item 4) asserts on `structuredContent`, so the annotation must be `dict[str, object]`, not the plan's original illustrative `dict`.

- **Dump each rejection and event individually, never the `CommandResult` container.** `CommandResult.events` is declared `tuple[Event, ...]` — the base class — so `result.model_dump(mode="json")` on the whole result serializes only base-class fields (`code`, `visibility`) and drops `event_type` plus every subclass field (`FlagSetEvent`'s `key`/`value`). Per-element `.model_dump(mode="json")` — exactly what the FastAPI example does (`examples/fastapi_crawler/app.py:165`) — preserves them; `model_dump(mode="json", serialize_as_any=True)` is the one-line alternative. This is load-bearing: the entire token thesis is narrating from event fields, so the tool must not lose them.
- **The argument is a raw `dict`, not the `AnyCommand` union.** Rationale: Phase 0 is a walking skeleton, and the spec pins "measure the union schema's standing per-turn context cost" to Phase 1. Typing the tool with the 45-variant union now would bake that cost in before there is anything to measure it against. The `ping` skill hands the model the literal payload, so no argument schema is needed for the smoke test. Phase 1 owns the union-as-tool-definition decision and its measurement.
- Unknown `command_type` (where `parse_command` returns `None`) returns a structured result field, not a raised error. A known-but-malformed payload raises `ContentValidationError` from `parse_command` (`commands.py:1697-1699`); Phase 0 lets that propagate as a tool error rather than mapping it — the full `OsrlibError` → tool-error map is Phase 1, and the smoke payload never triggers it.
- No lock. `GameSession` is not thread-safe by contract, but a single stdio server serves one client and Phase 0 exposes one tool — commands cannot interleave. The lock returns with the real lifecycle in Phase 1; adding it now would be accommodation for a consumer that does not exist.
- `def main() -> None: mcp.run()` — `mcp.run()` with no argument defaults to stdio transport. `__main__.py` calls `main()`.

### 4. Tests — the in-isolation ladder

Three pytest rungs, all runnable in CI without Claude Code. This is the fast dev loop; the Claude Code launch (work item 7) is the manual gate on top.

- `tests/test_schema.py` — the scaffolding contract: `import osrlib` succeeds and `TypeAdapter(AnyCommand).json_schema()` generates with `discriminator.propertyName == "command_type"` and `len(oneOf) == len(ALL_COMMAND_CLASSES)`. Retires "do our deps even resolve and does the union schema build."
- `tests/test_session.py` — the engine round-trip in-process: `build_session()`, then assert `execute` on `SetFlag(key="ping", value=True)` yields `accepted=True` with a `FlagSetEvent`, and `MoveParty(direction=NORTH)` yields `accepted=False` with `rejections[0].code == "session.command.wrong_mode"`. Test the tool function directly (it is a plain callable).
- `tests/test_mcp_boundary.py` — the boundary itself: use the SDK's `create_connected_server_and_client_session(mcp, raise_exceptions=True)` in-memory transport (async, `@pytest.mark.anyio`), `call_tool("execute", {"command": {"command_type": "set_flag", "key": "ping", "value": True}})`, and assert the returned structured content is the accepted envelope. This validates serialization and the FastMCP tool wiring end-to-end, no subprocess.

### 5. The plugin skeleton

The repo root is the plugin root.

- `.claude-plugin/plugin.json` — mirror `bx-referee`'s shape: `name` `osrlib-referee`, `description`, `author`, `repository`, `license` `CC0-1.0`, `keywords`. **Omit `version`** (matches the house convention that the marketplace entry is the version authority; also avoids the update-detection footgun if the plugin is later listed as an external source). The `name` here is what feeds the tool prefix — see work item 7.
- `.mcp.json` at the plugin root (not inside `.claude-plugin/`), top-level `mcpServers`, server key `osrlib`:

  ```json
  {
    "mcpServers": {
      "osrlib": {
        "command": "uv",
        "args": ["run", "--project", "${CLAUDE_PLUGIN_ROOT}/server", "osrlib-referee-mcp"]
      }
    }
  }
  ```

  Stdio is the default transport, so no `type` field. `${CLAUDE_PLUGIN_ROOT}` resolves to the plugin install directory. No `env` needed — the session is ephemeral. (When Phase 1 adds durable *game* saves, they go under `${CLAUDE_PLUGIN_DATA}` or the user's game directory, never bundled next to code.) Caveat: `uv run --project ${CLAUDE_PLUGIN_ROOT}/server` writes `server/.venv` under the plugin root, so the launch mechanism assumes that root is writable — true for `--plugin-dir` dev loading, but an installed plugin's root may be a non-writable cache. The launch decision is therefore **provisional for the distribution path** until tested against a read-only root (see work item 7).
- `skills/ping/SKILL.md` — the one no-op skill. Frontmatter `name: ping`, a description marking it a manual boundary smoke test, and `allowed-tools: mcp__plugin_osrlib-referee_osrlib__execute`. Body: instruct the model to call that tool once with the literal payload `{"command_type": "set_flag", "key": "ping", "value": true}` and report the returned envelope verbatim. This is the human-driven half of the definition of done and the thing that confirms the `allowed-tools` name matches what Claude Code actually exposes.

### 6. Continuous integration

- `.github/workflows/ci.yml` — on push and pull request: `astral-sh/setup-uv` with the committed lockfile, then `uv sync --project server`, `uv run --project server ruff format --check`, `uv run --project server ruff check`, `uv run --project server pytest`.
- Python 3.14, ubuntu + macos matrix. The second OS is nearly free and the packaging story is platform-sensitive (PATH, uv resolution), so exercising both turns an implicit portability claim into a tested one — and the user's own machine is macOS.
- CI cannot launch Claude Code, so the work-item-7 spike is explicitly a **manual gate documented in the plan and README**, not a CI job. CI covers rungs 1–3 of the test ladder.

### 7. The packaging spike — the risk retirement

This is the reason Phase 0 exists. Everything above is table-setting for this.

**Default launch option to test first: `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp`** (work item 5's `.mcp.json`). This diverges from the spec's stated preference order, which lists `uvx` against a published package first — a deliberate, reasoned divergence for Phase 0: the `uv run --project` form needs no PyPI publish gate and directly exercises the bundled source we are trying to prove. Publishing-for-`uvx` is retained as a distribution-phase fallback, not a Phase 0 prerequisite.

**Procedure:**

1. Pre-warm the server env once: `uv sync --project server`. Document this as the supported one-time install step in the README. It builds `server/.venv` from the lockfile so Claude Code's launch does not pay a cold resolve.
2. Launch: `claude --plugin-dir .` from the repo root.
3. Invoke the `ping` skill; confirm it calls the `execute` tool and the returned envelope is `accepted=True` with a `FlagSetEvent`.
4. **Record the exact exposed tool name** and confirm it equals `mcp__plugin_osrlib-referee_osrlib__execute`. Hyphens in the plugin name are preserved in the tool name (verified against the live docs), and the `allowed-tools` string must match character-for-character — this is the single most likely silent failure, so confirm it empirically rather than trusting the derivation.
5. **Characterize cold start.** Repeat step 2 with `server/.venv` removed to simulate a truly clean profile. MCP startup is non-blocking by default (servers connect in the background) and `MCP_TIMEOUT` defaults to **5000 ms** — a bare Python + uv cold resolve can exceed that. Record whether the tool becomes available promptly, and whether a first-call race occurs before the server finishes connecting. Do **not** set `alwaysLoad: true` (it would block startup on the 5 s cap).
6. **Note the provisional boundary.** `claude --plugin-dir .` loads from the writable repo, so the spike retires the launch mechanism only for the *dev-loading* path. Whether `uv run --project` works when `${CLAUDE_PLUGIN_ROOT}` is an installed, possibly read-only, cache is a distribution-time question — record the Phase 0 verdict as **provisional pending a read-only-root test**, and confirm against live Claude Code docs whether an installed plugin root is writable. If it is not, the fallback ladder's rung 4 (published package via `uvx`, which resolves into uv's own tool cache, not the plugin root) becomes the distribution answer.

**Definition of "clean profile":** at minimum, `server/.venv` removed so the first launch pays real resolution cost; ideally also a login shell without dev-shell PATH hooks (or a fresh user), to surface the "uv not on the PATH Claude inherits" failure that a warm dev machine hides.

**The decision and its fallback ladder** — pick the first rung that passes the spike, and record the verdict in this plan and the README:

1. `uv run --project` with a documented one-time `uv sync` pre-warm (the default above). Expected to win.
2. If uv is not resolvable on Claude's inherited PATH: an absolute path in `command`, or a small wrapper script under `${CLAUDE_PLUGIN_ROOT}` that locates uv.
3. If cold start is intractable even warm: document `uv sync` as a hard prerequisite and/or raise `MCP_TIMEOUT` in the launch instructions (`MCP_TIMEOUT=15000 claude`).
4. Last resort: publish the server to PyPI and switch `.mcp.json` to `uvx osrlib-referee-mcp`, accepting the publish/release overhead.

**Dev loop before the manual gate:** rungs 1–3 of the test ladder, then an optional interactive `uv run --project server mcp dev src/osrlib_referee_mcp/server.py` (the MCP Inspector) to click the tool before wiring into Claude Code.

**Recorded verdict (2026-07-05):** rung 1 wins, exactly as expected, with no fallback needed.

- `claude --plugin-dir .` from the repo root, prompted headlessly with `/ping` (`claude --plugin-dir . -p "/ping" --output-format stream-json --verbose`), called the tool and returned `{"accepted":true,"rejections":[],"events":[{"code":"session.flag.set","visibility":"referee","event_type":"flag_set","key":"ping","value":true}]}` — the exact envelope the definition of done calls for.
- **Exact exposed tool name, confirmed from the stream-json transcript's `tool_use` block:** `mcp__plugin_osrlib-referee_osrlib__execute`, character-for-character matching both the prediction and `skills/ping/SKILL.md`'s `allowed-tools` entry. `permission_denials` was empty — the skill's pre-approval worked. Hyphens in the plugin name are preserved, confirmed both against live docs and now empirically.
- **Cold start, characterized two ways, neither showed a problem:** (a) `server/.venv` removed, warm `uv` package cache — total wall time ~8.9 s, tool available immediately, no race. (b) `server/.venv` removed **and** a throwaway empty `UV_CACHE_DIR` (a genuinely cold `uv`, forcing all 37 dependency wheels to re-download from PyPI) — total wall time ~11.8 s, still no timeout, no first-call race, no `MCP_TIMEOUT` failure. `uv run --project`'s auto-sync-on-invocation absorbs the cold-resolve cost transparently; the documented `uv sync` pre-warm (work item 1) is still worth keeping as a fast-fail install check, but it is not load-bearing for launch reliability the way the risk write-up assumed.
- **Not tested (still open, as the plan anticipated):** a login shell without dev-shell PATH hooks / a fresh user account, so a "`uv` absent from Claude's inherited PATH" failure remains theoretical rather than ruled out. And per the plan's own note-6 caveat, this spike only exercises the `--plugin-dir` dev-loading path — an installed plugin with a read-only `${CLAUDE_PLUGIN_ROOT}` remains untested and the verdict for that path stays **provisional**, deferred to the distribution phase along with the marketplace listing.
- **Decision:** ship the `uv run --project ${CLAUDE_PLUGIN_ROOT}/server osrlib-referee-mcp` launch mechanism as-is (work item 5's `.mcp.json`, unchanged). No fallback rung was needed.

### 8. README and licensing touch-ups

- Add a "Requirements / install" note to the repo README: Python ≥ 3.14 and `uv` on PATH are prerequisites; the one-time install step is `uv sync --project server`; local run is `claude --plugin-dir .`.
- Confirm `plugin.json` `license` is `CC0-1.0`, consistent with the repo's root `LICENSE`. There is no OGL/SRD split to police in Phase 0 — the engine is CC0 and Phase 0 vendors no adventure content.
- Record the packaging verdict from work item 7 in the README so a fresh clone knows the supported launch path.

## Sequencing

The build order minimizes rework and front-loads the risk:

1. Work item 1 (server project) → 2 (fixture) → 3 (`execute` tool). The server must exist before anything can test it.
2. Work item 4 (tests) alongside 3 — test-first where practical; the three rungs are the in-isolation proof and gate the manual spike.
3. Work item 5 (plugin skeleton) and 6 (CI) once the server is green in isolation.
4. Work item 7 (the packaging spike) last — it depends on everything above and is where the phase's real uncertainty lives. **If the spike surfaces a blocker, amend this plan on the same branch** (per the repo's phase loop) so plan and reality never diverge.
5. Work item 8 (README/licensing) closes out, recording the spike's verdict.

## Definition of done

- `uv sync --project server` resolves, `osrlib` imports, and `TypeAdapter(AnyCommand).json_schema()` generates (test rung 1, green in CI).
- The in-process round-trip proves both the accepted (`SetFlag` → `FlagSetEvent`) and rejected (`MoveParty` in TOWN → `session.command.wrong_mode`) branches (rung 2).
- The in-memory MCP client round-trips `execute` and gets the accepted envelope back (rung 3).
- CI is green on the ubuntu + macos / Python 3.14 matrix (ruff format, ruff check, pytest).
- **The manual gate:** inside `claude --plugin-dir .` on a clean profile, the `ping` skill calls `execute` with a trivial command and receives `accepted=True` with a `FlagSetEvent` — the spec's "execute(a trivial command) works end-to-end through the MCP boundary."
- The exact exposed tool name is confirmed and matches the `ping` skill's `allowed-tools`.
- **The packaging/PATH option is decided** from the spike and recorded in this plan and the README.

## Decisions pinned

- **Server runs bundled source via `uv run --project ${CLAUDE_PLUGIN_ROOT}/server`**, not `uvx` against a published package — no publish gate, exercises the real bundled path. Reasoned divergence from the spec's preference order; `uvx`/publish is a documented fallback rung.
- **`mcp` pinned to `>=1.28,<2`.** The v2 pre-release on `main` has a different API; v1 (`mcp.server.fastmcp.FastMCP`) is the maintained line.
- **`execute` takes a raw `dict`, not the `AnyCommand` union.** Keeps the skeleton minimal and defers the union-schema-as-tool-definition and its standing per-turn context cost to Phase 1, where the spec pins the measurement.
- **The Phase 0 session is a hardcoded, fixed-seed, in-memory walking skeleton**, native (no `examples/` import), thrown away when Phase 1 builds the real lifecycle. No persistence, no lock, no `observe`/`prose`.
- **`SetFlag` is the canonical trivial command** (accepted + one event, legal in every mode, references no dungeon or character); `MoveParty` in TOWN is the rejection demonstrator.
- **One no-op skill, `ping`**, whose sole job is the manual boundary proof and confirming the `allowed-tools` tool-name match.
- **Server key `osrlib`** → tool `mcp__plugin_osrlib-referee_osrlib__execute`, to be confirmed empirically in the spike.
- **`plugin.json` omits `version`** (marketplace entry is the version authority; avoids update-detection breakage).
- **CI runs the three in-isolation test rungs; the Claude Code launch is a manual gate**, since CI cannot run Claude Code.

## Risks and open questions

- **Clean-profile cold start vs the 5 s `MCP_TIMEOUT`.** Non-blocking startup softens this, and the documented `uv sync` pre-warm should eliminate it, but the spike must confirm no first-call race and no hard timeout. Fallback: raise `MCP_TIMEOUT` in launch docs.
- **uv on Claude's inherited PATH.** A GUI-launched Claude may have a minimal PATH that omits `~/.local/bin`. The spike's "clean profile" is designed to catch this; fallback is an absolute path or a locator wrapper.
- **Tool-name exactness.** The `allowed-tools` string must match the exposed name character-for-character, hyphens included. Confirmed empirically in the spike; a mismatch fails silently (the skill simply cannot call the tool).
- **`mcp` v1 → v2 churn.** Pinned `<2` for now; the eventual v2 migration is a deliberate future task, not drift to inherit accidentally.
