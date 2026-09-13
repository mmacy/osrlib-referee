# Phase 3 manual play-through

The manual gate for Phase 3: run the full campaign lifecycle in a plugin session and confirm the reconciled skill graph (`referee` → `character` / `play` / `session`, plus `compile-adventure`) routes correctly and every tool name resolves. The automated in-process proxy is green; this is the final human check, as in Phases 1 and 2.

Use the **`sunken_chapel`** adventure — it keys treasure to recover and sell, so it exercises the whole town economy (`barrow_crypt`, the native adventure, keys no treasure).

Legend for each act: **Do** is what you type as the player; **Pass** is what confirms it worked.

## The level-up caveat, up front

> Neither shipped adventure hands a fresh party enough XP to cross a threshold in one delve — `sunken_chapel`'s whole haul is about 660 XP (620 gp of treasure plus two zombies) and a fighter needs 2,000 for level 2. That is a content-size limit, not a bug. So Act 6 **forces** the level-up with an explicit escape-hatch request, which still exercises the exact narration path (`AwardXP` → `XpAwardedEvent.level_after` → the play skill's inference and the no-HP-restore divergence).

## Setup

```bash
uv sync --project ~/repos/osrlib-referee/server   # once, if you haven't
cd ~/osr-games
claude --plugin-dir ~/repos/osrlib-referee
```

Launch from the game directory, **not** the checkout. That's how an installed plugin runs, and it keeps the repo's `CLAUDE.md`, which is contributor documentation, out of the referee's context window. The skills resolve the server through `${CLAUDE_PLUGIN_ROOT}`, so `chargen`, `gametool`, and `bundletool` run from any working directory.

Artifacts land in the game directory (`~/osr-games` by default, or wherever `OSRLIB_REFEREE_GAME_ROOT` points): built parties under `parties/`, saves under `adventures/<adventure-id>/`.

## Act 1 — make a party

Routes `referee` → `character`, driving the `chargen` CLI.

- **Do:** `Let's play some Old-School Essentials. I want to make a party first.`
- **Do:** Roll a couple of characters — accept a class from the menu it offers, buy a kit, name them. Try asking to **reroll** one.
- **Pass:** It runs `chargen roll` / `build` (you'll see it shell out via Bash) and presents **rolled** scores and gold — never made-up numbers. The class menu shows only **eligible** classes. A reroll is a fresh seed. It reports a **party id** and writes `~/osr-games/parties/<id>.json`.

## Act 2 — start the adventure

Routes `referee` → `play`, calling `session_new(party_ref=…)`.

- **Do:** `Start the Sunken Chapel adventure with that party.`
- **Pass:** It calls `session_new` with your `party_ref`, then reads an opening scene from `prose` (the town of Millford). No "what do you do?" prompt-menu.

## Act 3 — delve

Exploration and battle in the `play` loop.

- **Do:** `We head into the chapel.` Then explore freeform — light a torch, open doors, move room to room. Find the **reliquary** (treasure) and the **ossuary** (two zombies; fight them).
- **Pass:** Every roll and outcome is narrated from engine events; monsters are described by appearance, not stat blocks; damage comes from `execute` events, never invented.

## Act 4 — recover treasure, return to town

The automatic return-trip XP award.

- **Do:** Grab the coins and the gem ("Tear of Neth"), walk back to the entrance, then `We travel back to town.`
- **Pass:** On return it narrates an **automatic XP award** (the `AdventureXpAwardEvent` — monster plus treasure XP). This is the parity-plus beat `bx-referee` does not have. Mode is now `town`.

## Act 5 — town economy

`SellTreasure` / `PurchaseEquipment` / `PurchaseHealing`, with prices from `gametool`.

- **Do:** `Sell the gem.` then `What can I buy? I want a shield and some torches.` then `Anyone hurt should get healed at the temple.`
- **Pass:** Selling credits the purse; prices come from `gametool catalog` / `services` (it shells out, it does not quote from memory); an over-budget basket is refused whole; healing debits gold and restores HP.

## Act 6 — level up

Forced, to exercise the narration path.

- **Do:** `[out of character] To test the level-up flow, award my fighter enough XP to reach level 2.`
- **Do:** `Show me the fighter's sheet.`
- **Pass:** It issues `AwardXP` (the escape hatch), then **narrates the advance** — new level, new max HP — and `character_sheet` returns the new THAC0/saves. **Check the divergence:** if the fighter was wounded, they are **still wounded** after leveling (osrlib heals no damage on level-up; it must not say "restored to full").

## Act 7 — save

- **Do:** `Save the game.`
- **Pass:** `session_save` reports a `save_id`, and a file exists at `~/osr-games/adventures/sunken_chapel/<save_id>.json`.

## Act 8 — resume with a recap

The `session` skill.

- **Do:** Quit Claude, relaunch it the same way from `~/osr-games`, then `Continue my saved game.`
- **Pass:** It lists saves (`gametool saves`), loads yours (`session_load`), and gives a **recap** of where you left off (from the cold `observe` event tail) before handing back to `play`.

## Act 9 — the roll-log

`session_audit`, the audit `bx-referee` structurally cannot do.

- **Do:** `Can I see the dice rolls from that zombie fight?`
- **Do:** `Show me the full referee roll history.`
- **Pass:** It calls `session_audit`. Mid-scene it shows **your** characters' rolls and revealed outcomes; the full-history request surfaces the complete referee log now that the scene is over.

## Red flags in play

Any of these is a constitution or skill bug, not a play choice:

- Any **number it made up** — a THAC0, a hit-point total, a gold amount, an XP total, a hit-die roll — instead of one traced to a tool result.
- A **numbered action menu** ("1) open door, 2) search…") or a **"What do you do?"** prompt.
- **Leaked target numbers** ("the zombie needs a 15 to hit you") or a monster named or statted before it is revealed.
- A tool call that **errors as "not found / not authorized"** — that is an `allowed-tools` or tool-name mismatch.
- Level-up narrated as a **full heal**.
- A CLI call that fails to find a `pyproject.toml`, or a bare `server` path in the command. That means `${CLAUDE_PLUGIN_ROOT}` didn't substitute, and the skills won't run outside the checkout.

## Act 10 — compile a module from the shelf

Not a Phase 3 act. The shelf-of-holding text source and the `compile-adventure` stage 0 landed after Phase 3 (#18), and none of the acts above touch them. Run this one in its own sitting: it needs no game session.

Use **X1 The Isle of Dread**, and compile only the Taboo Island temple: areas 31-37 on level 1 and 38-40 on level 2. Ten keyed areas over two levels is small enough to finish in a sitting, and it still covers a trap, a secret door, treasure, and creatures with no SRD template. X1 is a commercial TSR module, so it exercises the licensing gate too.

The index must be on the machine (`~/.shelf-of-holding/shelf.db`). If a conversion run is writing to it, point at a snapshot first:

```bash
export SHELF_DB=~/.shelf-snapshots/shelf-20260907T1625.db
```

### Act 10a — get the text

- **Do:** `Compile the Taboo Island temple from X1 The Isle of Dread into a bundle.`
- **Pass:** It runs `bundletool shelf-find "isle of dread"`, gets back `bf860050  38/38 pages with text`, and pulls the pages with `shelf-text --out <scratch>/x01.md`. It then reads the file it wrote. It never pages the PDF for prose, and it never invokes the `shelf` CLI, whose `scan`, `triage`, `convert`, and `gold` subcommands write.

### Act 10b — the licensing gate

- **Pass:** Before it compiles anything, it establishes that X1 is a commercial TSR module and puts the bundle in `~/osr-games/bundles/<bundle_id>/`. Asking you to confirm the license is fine. Compiling into the repo's `adventures/` without asking is not.

### Act 10c — the page offset

- **Do:** `Which PDF pages is the temple key on, and how do you know?`
- **Pass:** It establishes the offset against a known page instead of trusting the printed number. X1's front matter offsets by one: the contents list "Key to Temple Level 2 .... 25", and that section is on **PDF page 26**. The temple key spans PDF pages 25-27.

### Act 10d — maps come from the PDF, not the text

- **Pass:** For Map 12 and Map 13 it reads the PDF page as an image (`Read` with `pages:`) and lays out the grid from that. Geometry doesn't survive OCR: the shelf text keeps a map's labels and loses its shape. A grid built from `shelf-text` output is wrong no matter how plausible it looks.

### Act 10e — the two gates

- **Do:** Let it finish, then look at what it hands back.
- **Pass:** `bundletool validate` prints `OK`. It shows you a `render-map` render next to the source map for the cell-for-cell diff. `manifest.approximations` lists every reskin (the Great One and the guardians are the likely ones), every geometry approximation, and every escape-hatch beat, and each entry states what the approximation costs.

### Act 10f — no index (optional)

- **Do:** `SHELF_DB=/nonexistent/shelf.db` in the environment, then ask for a compile.
- **Pass:** The command says `no shelf index at /nonexistent/shelf.db. Set SHELF_DB to one, or compile from text you supply instead.` and exits 1. The skill then asks you for the text instead of treating the missing index as a dead end.

### Red flags for the compile

- A bundle for X1 written into the repo's `adventures/`, or committed anywhere.
- A grid built without ever reading a map page as an image.
- Page ranges taken from the printed folio with no offset check.
- Any `shelf` CLI invocation instead of the read-only `bundletool` commands.
- `validate` not reaching `OK`, or a reskin that plays as its SRD stand-in with no manifest entry.
