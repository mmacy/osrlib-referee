---
name: referee
description: Entry point and router for B/X (Basic/Expert) tabletop play on the osrlib-referee engine. Routes to character creation, a new or resumed adventure, and the play loop. Use when starting or continuing a B/X session, or when the user mentions B/X, OSE, old-school D&D, a referee, a game master, or an adventure.
allowed-tools: mcp__plugin_osrlib-referee_osrlib__list_adventures AskUserQuestion
---

# Referee

The front door. This skill decides *what the player wants to do* and routes to the skill that does it — it does not run play, creation, compilation, or persistence itself. Keep it thin.

**Read [references/constitution.md](references/constitution.md) before anything else.** It is the supreme, non-negotiable contract governing every skill in this plugin — play, creation, town, and audit alike. Never violate it.

## Routing

Open with an `AskUserQuestion`: **create characters**, **start a new adventure**, or **continue a saved game**? Then route:

- **Create characters** → the **`character`** skill. It rolls a party through the deterministic `chargen` CLI and reports a `party_id`. When it returns, offer to start a new adventure on that party.
- **Continue a saved game** → the **`session`** skill to pick a save and resume with a recap, then the **`play`** skill for the turn loop.
- **Start a new adventure** → resolve the choice (below), then the **`play`** skill, which calls `session_new` and runs the loop. If the player built a party, pass its `party_id` through as `session_new(party_ref=<party_id>)`; otherwise the frozen pregen roster starts a zero-setup game.

## Resolving a new adventure — where published-module parity lives

Call `list_adventures` for the startable ids: native builders and already-compiled bundles. Then:

- **A known `adventure_id`** (native or a compiled bundle) → hand off to `play` to start it directly.
- **A path to an uncompiled module** (a PDF or Markdown the player points at, not in `list_adventures`) → hand off to the **`compile-adventure`** skill first. It compiles the module into a bundle *and passes both review gates — the `validate_bundle` check and the visual map-diff — before the bundle is accepted*; only then hand off to `play` to start the resulting bundle. **Never start a session on a half-reviewed bundle.**

This is the project's deliberate divergence from `bx-referee`, made honest: `bx-referee` points at a module PDF and re-reads it live every session; here the module is read **once, at compile time**, into a deterministic bundle that then plays identically every time. Same "bring your own module" outcome, by a route that makes the session replayable — at the cost of an explicit compile step and SRD-only fidelity (a module whose central creature can't be reskinned to an SRD template is the one class of content `bx-referee` can still narrate freehand and this substrate cannot; the compile skill's approximation log names it).

## What this skill does not do

It routes; it does not do the work. It issues no `execute`, `session_new`, `session_save`, or compile call itself — those belong to `play`, `session`, `character`, and `compile-adventure`. Its only tools are `list_adventures` (to decide the route) and `AskUserQuestion` (to learn the intent).
