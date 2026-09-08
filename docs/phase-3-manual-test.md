# Phase 3 manual play-through

The manual gate for Phase 3: run the full campaign lifecycle inside `claude --plugin-dir .` and confirm the reconciled skill graph (`referee` → `character` / `play` / `session`, plus `compile-adventure`) routes correctly and every tool name resolves. The automated in-process proxy is green; this is the final human check, as in Phases 1 and 2.

Use the **`sunken_chapel`** adventure — it keys treasure to recover and sell, so it exercises the whole town economy (`barrow_crypt`, the native adventure, keys no treasure).

Legend for each act: **Do** is what you type as the player; **Pass** is what confirms it worked.

## The level-up caveat, up front

> Neither shipped adventure hands a fresh party enough XP to cross a threshold in one delve — `sunken_chapel`'s whole haul is about 660 XP (620 gp of treasure plus two zombies) and a fighter needs 2,000 for level 2. That is a content-size limit, not a bug. So Act 6 **forces** the level-up with an explicit escape-hatch request, which still exercises the exact narration path (`AwardXP` → `XpAwardedEvent.level_after` → the play skill's inference and the no-HP-restore divergence).

## Setup

```bash
cd /Users/mmacy/repos/osrlib-referee
uv sync --project server      # once, if you haven't
claude --plugin-dir .
```

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

- **Do:** Quit Claude, relaunch `claude --plugin-dir .`, then `Continue my saved game.`
- **Pass:** It lists saves (`gametool saves`), loads yours (`session_load`), and gives a **recap** of where you left off (from the cold `observe` event tail) before handing back to `play`.

## Act 9 — the roll-log

`session_audit`, the audit `bx-referee` structurally cannot do.

- **Do:** `Can I see the dice rolls from that zombie fight?`
- **Do:** `Show me the full referee roll history.`
- **Pass:** It calls `session_audit`. Mid-scene it shows **your** characters' rolls and revealed outcomes; the full-history request surfaces the complete referee log now that the scene is over.

## Red flags

Any of these is a constitution or skill bug, not a play choice:

- Any **number it made up** — a THAC0, a hit-point total, a gold amount, an XP total, a hit-die roll — instead of one traced to a tool result.
- A **numbered action menu** ("1) open door, 2) search…") or a **"What do you do?"** prompt.
- **Leaked target numbers** ("the zombie needs a 15 to hit you") or a monster named or statted before it is revealed.
- A tool call that **errors as "not found / not authorized"** — that is an `allowed-tools` or tool-name mismatch.
- Level-up narrated as a **full heal**.
