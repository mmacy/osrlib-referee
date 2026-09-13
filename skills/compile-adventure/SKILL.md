---
name: compile-adventure
description: Compile a B/X adventure module (PDF or Markdown) into an osrlib-referee bundle — an Adventure spec, a prose sidecar, and a manifest — that the play skill can load and run. Use when turning a written module into playable content: transcribing its map, keyed areas, and read-aloud text, reskinning non-SRD creatures to their nearest SRD template, and logging every approximation. Not for playing a session (that is the play skill).
allowed-tools: Read Write Edit Bash Glob Grep
---

# Compile adventure

Turn a written module into a **bundle**: an on-disk `Adventure` spec plus a prose sidecar and a manifest that the `play` skill loads through `session_new`. Interpretation — reading a map, splitting boxed text from DM notes, choosing the nearest SRD template for a non-SRD creature — is your judgment. Everything where correctness is *checkable* rides the deterministic `bundletool` helpers, so the fidelity-critical parts never depend on model arithmetic.

**Read [references/bundle-format.md](references/bundle-format.md) before writing any files** — it pins the exact JSON shapes of `adventure.json`, `prose.json`, and `manifest.json`, and it is the contract [`load_bundle`][osrlib_referee_mcp.bundle.load_bundle] and `validate_bundle` enforce. The osrlib content model those shapes come from (`AreaSpec`, `LevelSpec`, `KeyedEncounter`, `edge_key`, …) is authoritative; read its source (`osrlib.crawl.dungeon`, `osrlib.crawl.adventure`) when a field is unclear.

This is **SRD-only** content: every keyed `template_id` and feature `item_id` must resolve against the stock OSE SRD catalog. Non-SRD creatures and items are **reskinned** to their nearest SRD template; content whose *mechanics themselves* are the encounter goes to the authorial escape hatch. Both are logged in the manifest.

## The licensing gate — do this first

Compile a module only if it is **openly licensed (OGL/CC) or original-authored**. Verify the license; never assume it. This decides where the bundle lives:

- **Open or original** → the plugin's own `${CLAUDE_PLUGIN_ROOT}/adventures/<bundle_id>/` directory, which is the repo checkout when you launch with `--plugin-dir .`. It commits with the repo.
- **Anything else (a commercial module, verbatim prose you can't relicense)** → the user's game directory, `~/osr-games/bundles/<bundle_id>/` (or wherever `OSRLIB_REFEREE_GAME_ROOT` points). **Never commit it.**

If the module's license is unclear, stop and ask the user. Do not compile-and-commit on assumption.

## Stage 0 — get the module's text

Every stage below assumes you have the module as text. If the user hands you Markdown, use it. Otherwise check the **shelf-of-holding index** (`~/repos/shelf-of-holding`), which already stores one Markdown text per page for every PDF under `~/rpgbook`, converted by the best converter that covered that page. Reading it costs a fraction of reading the PDF.

Find the book, then pull the pages you need:

```bash
uv run --project ${CLAUDE_PLUGIN_ROOT}/server python -m osrlib_referee_mcp.bundletool shelf-find "isle of dread"
uv run --project ${CLAUDE_PLUGIN_ROOT}/server python -m osrlib_referee_mcp.bundletool shelf-text bf860050 --pages 4-16 --out <scratch>/x01.md
```

`shelf-find` prints a sha prefix, the text coverage, and the path of every match. Pass the **sha prefix** to `shelf-text`: a title fragment often matches several cuts of one product, and the OSE, 5e, and Shadowdark editions of a module are three separate books with three separate keys. `shelf-text` writes Markdown with an HTML comment before each page naming the PDF page and the converter behind it, and it reports on stderr any requested page the index has no text for. Read the file you wrote rather than paging the PDF.

Four things to get right:

- **`--pages` takes PDF page indexes, not the page numbers printed on the page.** Front matter offsets them: X1's printed page 24 is PDF page 25. Establish the offset once against a known page before you trust a range.
- **Maps do not survive OCR.** A map page comes back as its labels in reading order with the geometry gone, so stage 1's grid never comes from this text. Read map pages from the PDF itself — `Read` the file with `pages: "12"` — and lay out the grid from the image.
- **Some pages read badly and look fine.** A book whose text layer is junk, or a table MinerU merged across a page break, yields plausible-looking wrong text. When an area's numbers or a table's rows look off, check that page against the PDF.
- **The index is optional.** With no index on the machine, or a module that is not on the shelf, both commands say so and exit 1. Compile from whatever text the user supplies.

The shelf is mostly commercial product. A module being easy to read here says nothing about where its bundle may live — the licensing gate above decides that, unchanged.

These commands only ever read the index, and never through the `shelf` CLI, whose `scan`, `triage`, `convert`, and `gold` subcommands write. The store is live, and a bulk conversion run may be writing to it. When one is running, point `SHELF_DB` at one of shelf-of-holding's dated snapshots instead:

```bash
export SHELF_DB=~/.shelf-snapshots/shelf-20260907T1625.db
```

## The compile stages

Work one dungeon level at a time. For each:

1. **Geometry → grid + edges.** Lay the module's map onto the 10′ cell grid (`x` east, `y` south from the northwest corner). Walls are the default — you declare only the *passages*: every open edge and every door is an explicit entry in `edges`, keyed by the canonical edge key. **Compute every edge key with the helper, never by hand:**

   ```bash
   uv run --project ${CLAUDE_PLUGIN_ROOT}/server python -m osrlib_referee_mcp.bundletool edge-key 3 2 east
   ```

   A non-grid or organic map is *approximated* to the grid — record each such approximation in `manifest.approximations.geometry`. Set the level `entrance` to the cell town-travel and `EnterDungeon` land on.

2. **Prose → sidecar.** Split each area's authored text into `read_aloud` (the module's boxed/read-aloud text, delivered verbatim in play) and `referee_notes` (DM tactics, development, secrets), keyed by the `AreaSpec.id` you assigned in step 1. The reserved key `"town"` carries the town's scene. Prose **sets the scene; it never renames a reskinned creature** — by the play constitution the referee describes a monster by appearance, not type-name, so an evocative area description carries the beat without ever speaking either the source name or the SRD name.

3. **Keyed content → specs, with the reskin stage.** Encounters become `KeyedEncounter`/`KeyedMonster`; traps `TrapSpec`/`TrapEffect`; treasure `FeatureSpec`/`AreaTreasureSpec`.
   - A creature **already in the SRD** → its stock `template_id`.
   - A **non-SRD creature** → *reskin* it: pick the nearest SRD template by mechanical profile (HD, AC, attacks/damage, movement, morale, special qualities), emit **that** stock `template_id`, and record `{source_name, template_id, area_id}` in `manifest.approximations.reskins`. The creature then plays as its SRD self; the area prose sets the scene without naming it.
   - A creature **no SRD template meaningfully approximates** (its unique mechanic *is* the fight), a true **custom magic item**, a bespoke trap/puzzle/trick, or NPC roleplay with no command → **do not fake it.** Flag it for the authorial escape hatch (the play skill runs it live via `SpawnMonsters` of an SRD stand-in, a `RollDice`-adjudicated effect, `SetFlag`, etc.) and record it in `manifest.approximations.escape_hatch`.

4. **Write the three files** into the bundle directory, exactly as [references/bundle-format.md](references/bundle-format.md) specifies. There is **no `catalog.json`** — an SRD-only bundle injects nothing.

## The review gates — a bundle is not done until both pass

`<bundle_dir>` below is the directory the licensing gate sent the bundle to. Pass the path, not a bare id: `validate` and `render-map` both take a directory, and the session's working directory is the player's game directory rather than the checkout.

1. **`validate_bundle`** — the deterministic gate. It reconstructs the `Adventure`, resolves every keyed/feature/wandering id against the stock catalog, and checks edge-key integrity:

   ```bash
   uv run --project ${CLAUDE_PLUGIN_ROOT}/server python -m osrlib_referee_mcp.bundletool validate <bundle_dir>
   ```

   Fix every error it reports (an unresolved `template_id` usually means a reskin named a template that doesn't exist; a "boundary edge" or "not a canonical key" means an edge-key mistake). Do not proceed until it prints `OK`.

2. **Visual map-diff** — the human gate. Render the compiled map and compare it, cell for cell, against the source module's map:

   ```bash
   uv run --project ${CLAUDE_PLUGIN_ROOT}/server python -m osrlib_referee_mcp.bundletool render-map <bundle_dir>
   ```

   Present the render to the user alongside the source map. Geometry is the likeliest place fidelity slips; this gate catches a transposed passage or a missing door that `validate_bundle` cannot.

## The manifest is the audit log — be honest

`manifest.approximations` is the record of everything the compile approximated. It is not optional bookkeeping; it is how a reviewer sees the fidelity budget instead of discovering it in play. **Every reskin, every geometry approximation, every escape-hatch beat gets an entry.** The reskin's cost — an evocatively-named creature loses its name and plays as a plain SRD nearest-likeness (a "barrow wight" statted as a `skeleton` has no energy drain) — is stated in the log, never smoothed over. When you are unsure a reskin is close enough, say so in the entry and let the user decide at the map-diff gate whether it should be an escape-hatch beat instead.

## Handing off

When both gates pass, tell the user the `bundle_id`, where the bundle lives, and a one-line summary of the approximation log (how many reskins, geometry notes, escape-hatch beats). They start it with the `play` skill: `session_new("<bundle_id>")`.
