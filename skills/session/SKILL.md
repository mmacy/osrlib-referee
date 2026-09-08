---
name: session
description: Save, resume, and audit an osrlib-referee game — enumerate saved games, resume one with a recap, save at a pause with an optional human-readable journal, and inspect the engine's roll/command log. Use when the player wants to continue a saved game, save the current one, or see the roll-log / audit trail.
allowed-tools: mcp__plugin_osrlib-referee_osrlib__session_load mcp__plugin_osrlib-referee_osrlib__session_save mcp__plugin_osrlib-referee_osrlib__observe mcp__plugin_osrlib-referee_osrlib__session_audit mcp__plugin_osrlib-referee_osrlib__character_sheet Bash Read Write AskUserQuestion
---

# Session

The lifecycle skill: resume a saved game with a recap, save at a pause, and inspect the roll-log. The `save_game` document the engine persists is the single source of truth; everything here reads or writes *around* it. When resume finishes, hand off to `play` for the turn loop.

**Read [the referee's constitution](../referee/references/constitution.md) before anything else.** In particular, Article VII.4 governs what the roll-log may reveal to the player mid-scene.

## Resume a saved game

1. **Enumerate saves.** Read the game directory with the `gametool` CLI via `Bash` (a filesystem read, off the play surface):

   ```bash
   uv run --project server python -m osrlib_referee_mcp.gametool saves
   ```

   It returns `{saves: [{adventure_id, save_id, schema_version, engine_version, mtime}, …]}`, newest first. If there's exactly one, use it; otherwise `AskUserQuestion` which `save_id` to continue.
2. **Load it.** `session_load(save_id)` re-activates the session — the adventure spec is embedded in the save, so no `adventure_id` is needed.
3. **Recap from the cold `observe`.** Call `observe()`; right after a load it comes back "cold" with a bounded tail of recent events. Narrate "here's where you left off" from that tail and the current `mode`/`area`/`party`. If a journal file exists for this save (see below), `Read` it for a richer narrative recap — it is prose context, never reloaded as state.
4. **Hand off to `play`** to continue the turn loop.

## Save

`session_save()` persists the active session to its current slot and returns the `save_id`. Report it back. A session keeps multiple named saves per adventure through distinct `save_id` stems (set at `session_new`); `session_save` writes to whichever slot is active.

### The optional journal

You may write a human-readable journal alongside the save — a session log and current-situation note, `bx-referee`'s `SESSION.md` role — as a **convenience for the player and for recaps, never canonical.** Write it as a `.md` sibling of the save in the game directory:

```
<game-root>/adventures/<adventure_id>/<save_id>.journal.md
```

(`<game-root>` is `~/osr-games` by default or wherever `OSRLIB_REFEREE_GAME_ROOT` points; `gametool saves` gives the `adventure_id`/`save_id`.) It is derived and disposable: the `save_game` document is the one source of truth, and the journal is never read back to reconstruct game state — only as recap prose.

## Audit — the roll-log

`bx-referee` has no roll-log; it resolves rolls silently and hides target numbers. osrlib-referee can do what it structurally cannot: the engine records every roll, and `session_audit` surfaces the real trajectory — dice rolls, attack and save resolutions, XP awards.

```
session_audit(kinds?, visibility?, limit?)
```

- `kinds` narrows to specific `event_type`s (e.g. `["dice_rolled", "attack_rolled", "saving_throw_rolled", "xp_awarded"]`); `limit` bounds the tail.
- **`visibility` draws the information-discipline boundary (constitution Article VII.4 / Article II).** Mid-scene, request `visibility="player"` — it returns the player-visibility events (a character's own attacks and saves, XP awards, already-revealed outcomes) and withholds the referee-only rolls (a morale check, a reaction roll, an unrevealed monster's stats, your own `RollDice` adjudications). The filter is mechanical — it keys on each event's own visibility, so a *monster's* attack or save roll against a PC is player-visible too (a revealed in-fiction outcome, not a leak); apply your own judgment before surfacing anything that would spoil a beat still hidden in the fiction. At a **scene boundary, in town, or at session end**, the full referee trajectory is fair game — omit `visibility` (or pass `"referee"`) and show the complete roll history. That post-hoc transparency is precisely the eval-ability this project was built for.

Present the audit as a readable log — what was rolled, what it needed (only when revealing is allowed), and the outcome — never as a raw event dump. Use `character_sheet(character_id)` when the player wants a member's full derived numbers alongside the log.

## Tool reference

| Tool | Use |
|---|---|
| `gametool saves` (Bash) | Enumerate saved games (adventure_id, save_id, engine version, mtime), newest first. |
| `session_load(save_id)` | Resume a save; the adventure is embedded in it. |
| `session_save()` | Persist the active session to its current slot. |
| `observe(scope="current")` | The cold recap tail right after a load; current mode/area/party. |
| `session_audit(kinds?, visibility?, limit?)` | The live roll/command trajectory, bounded and visibility-scoped. |
| `character_sheet(character_id)` | A member's full derived sheet, on request. |
