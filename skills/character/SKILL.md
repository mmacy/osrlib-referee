---
name: character
description: Create Old-School Essentials (B/X) characters and assemble a party through the deterministic, seeded chargen CLI, where the osrlib engine rolls every ability score, hit-point total, and gold piece — never the LLM. Use when creating a new character, rolling up a PC, or building a party before starting an adventure.
allowed-tools: Bash AskUserQuestion
---

# Character

Build a party the engine can start. Every die — ability scores, hit points, starting gold — is rolled by osrlib's deterministic `chargen` CLI from a recorded seed, so the party is auditable and reproducible, never LLM-invented. Your job is to run the CLI, present what it returns verbatim, and collect the player's *administrative* build choices with `AskUserQuestion`.

**Read [the referee's constitution](../referee/references/constitution.md) before doing anything else.** It governs creation as well as play: the engine rolls every number (Article III.1), and `AskUserQuestion` is for administrative build choices only — never in-world play (Article I.5).

## The CLI

Character creation runs off the play server, as a CLI (the once-per-campaign, pre-session shape — like `compile-adventure`'s `bundletool`), so play sessions pay it zero standing schema. Invoke it with `Bash`:

```bash
uv run --project server python -m osrlib_referee_mcp.chargen <subcommand> …
```

The **seed carries the whole roll state** — there is no scratch file. `roll` emits the scores and the legal-class menu; `build` re-derives the same scores, then rolls HP and gold once the class is known, and finalizes. Same seed + same choices ⇒ byte-identical character. Pick a distinct seed per character (any integer — e.g. a timestamp or an incrementing counter); a **"reroll" is simply a new seed**, which is why it is auditable. osrlib offers no in-place single-ability reroll and no 4d6-drop-lowest / max-HP method — those are documented engine-limited gaps, not something to fake.

## Building one character

1. **Roll ability scores.** `chargen roll --seed S`. Present the six scores and their `modifiers` (the `modifier_legend` in the payload says what each governs) to the player. Offer a reroll — that is a fresh `roll` with a new seed. The payload's `eligible_classes` is the legal-by-construction class menu; `ineligible_classes` carries the classes the scores lock out, with reasons (present them only if the player asks why a class is missing).

2. **Choose class, alignment, adjustment, spell.** `AskUserQuestion`, in this order:
   - **Class** — present *only* `eligible_classes` (the CLI's `validate_class_choice` is the gate; never re-derive eligibility yourself).
   - **Alignment** — lawful, neutral, or chaotic.
   - **Adjustment** (optional) — the creation-time two-for-one trade lowering STR/INT/WIS to raise a prime requisite. Offer it; most players skip it. Pass it as `--lower ABILITY=N --raise ABILITY=N`.
   - **Starting spell** — magic-user and elf only (their `caster` is `"arcane"` in the class entry). One first-level arcane spell for the spell book; pass it as `--spell SPELL_ID`.

3. **Reveal gold, then buy equipment.** `chargen build --seed S --class … --alignment …` with those choices and **no purchases** reveals `hit_points` and `starting_gold_gp`. Present the gold total, then `AskUserQuestion` for equipment against that number: a standard class kit, or a manual pick. Weapons and armour buy one at a time (`--buy sword`); gear and ammunition buy in lots (`--buy torch` is one lot = six torches). Equip what should be worn/wielded with `--equip`.

4. **Finalize.** `chargen build` again with the equipment (`--buy …`, `--equip …`), the `--name`, and `--out <path>` to write the finished character document to a scratch file. If it returns `{"ok": false, …}` (an unaffordable basket, an illegal equip), surface the rejection's reason in plain language and re-ask — nothing was committed. On `{"ok": true, …}` deliver the HP, gold, and AC the CLI reports, verbatim.

Deliver every rolled number straight from the CLI; never invent or adjust a stat (Article III.1). `AskUserQuestion` is used only for these build choices — never for anything that happens in the fiction.

## Assembling the party

Build each member to its own scratch file, then assemble:

```bash
BUILD=$(mktemp -d)
uv run --project server python -m osrlib_referee_mcp.chargen build --seed 101 --class fighter --alignment lawful \
  --buy sword --buy chainmail --equip sword --equip chainmail --name Brakka --out "$BUILD/brakka.json"
# …repeat for each member…
uv run --project server python -m osrlib_referee_mcp.chargen party --out heroes "$BUILD/brakka.json" "$BUILD/wynn.json"
```

`chargen party --out <party_id>` writes the stamped party document to `<game-root>/parties/<party_id>.json` (the game directory, `~/osr-games` by default or wherever `OSRLIB_REFEREE_GAME_ROOT` points). Report the `party_id` back — that is what starts the adventure: the `play`/`referee` flow passes it as `session_new(party_ref=<party_id>)`, so the whole party document never crosses the conversation wire. Members carry no entity ids yet; the engine assigns them when the session begins.

## Tool reference

| Command | Use |
|---|---|
| `chargen roll --seed S` | Roll ability scores; emit scores, modifiers, and the eligible-class menu. |
| `chargen build --seed S --class … --alignment … [--lower/--raise …] [--spell …] [--buy …] [--equip …] [--name …] [--out PATH]` | Roll HP + gold and finalize a character, or return structured rejections. |
| `chargen party --out PARTY_ID CHAR.json …` | Assemble finished character documents into a party in the game directory. |
