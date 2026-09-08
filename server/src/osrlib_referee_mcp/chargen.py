"""The deterministic, seed-driven character-creation CLI — off the play tool surface.

Character creation is pre-session and once-per-campaign: a tool for it on the play
`FastMCP` server would advertise its schema to every play turn that never creates a
character (the Phase-2 `bundletool` precedent — exposure discipline). So creation is a
CLI, invoked `uv run --project server python -m osrlib_referee_mcp.chargen …`, and play
sessions pay it zero standing schema.

The **seed makes the CLI stateless** — no creation-in-progress scratch file. osrlib
draws ability scores, first-level hit points, and starting gold from
`RngStreams(master_seed=S).get(CHARACTER_CREATION_STREAM)` in that fixed order
(`osrlib.core.character.create_character`), each stage a pure function of `(seed, the
choices before it)`. So each subcommand re-derives from the seed:

- **`roll --seed S`** runs `roll_ability_scores` and emits the six scores, their raw
  3d6, and the **eligible-class list** (classes whose `validate_class_choice` passes) —
  everything the score draw alone determines. It deliberately does *not* emit starting
  gold: gold is drawn *after* the class-dependent hit-point roll (the hit die's
  `randbelow` rejection-samples a class-varying number of raw draws, `core/rng.py`), so
  the stream position at gold time depends on the class. Gold is a `build`-time result.
- **`build --seed S --class … …`** re-derives the scores, then — the class now known —
  rolls hit points and gold deterministically, applies the post-roll choices, and
  returns the finished `Character` document (with rolled HP and gold shown) or a
  structured rejection list. It is idempotent per `(seed, class, choices)`: called first
  with no purchases it reveals the gold to shop against; called again with the basket it
  reproduces the identical HP/gold draws and finalizes. Same seed + same choices ⇒
  byte-identical character.
- **`party --out <party_id> <char.json> …`** wraps finished character documents into the
  stamped `party_to_document` envelope the server consumes and writes it to
  `<game-root>/parties/<party_id>.json`, so `session_new(party_ref=…)` can load it
  server-side without the whole document crossing the conversation wire.

The CLI drives the **stepwise validators** (not the raises-on-error `create_character`)
so a bad class choice or unaffordable basket returns a readable reason, not a stack
trace. It records the seed in the character document's provenance so the roll is
reproducible and audit-visible. A "reroll" is simply a fresh seed.
"""

import argparse
import json
from pathlib import Path

from osrlib.core.abilities import (
    AbilityAdjustment,
    AbilityScore,
    apply_adjustment,
    validate_adjustment,
)
from osrlib.core.alignment import Alignment
from osrlib.core.character import (
    CHARACTER_CREATION_STREAM,
    Character,
    party_to_document,
    roll_ability_scores,
    roll_hit_points,
    roll_starting_gold,
    validate_extra_languages,
    validate_starting_spells,
)
from osrlib.core.classes import ClassDefinition
from osrlib.core.items import Inventory, ItemInstance, equip, purchase, validate_equip, validate_purchase
from osrlib.core.rng import RngStreams
from osrlib.core.ruleset import Ruleset
from osrlib.core.spells import caster_profile
from osrlib.core.validation import Rejection
from osrlib.data import load_ability_tables, load_classes, load_equipment, load_spells

from osrlib_referee_mcp.gamedir import party_path, resolve_game_root

# The single per-ability numeric modifier a player weighs at creation, from the OSE
# ability-score summary: STR's attack/damage, DEX's AC adjustment (equal in magnitude to
# its missile bonus in B/X), CON's per-die hit points, CHA's reaction adjustment, WIS's
# save-versus-magic modifier, and INT's count of extra languages. The CLI computes these
# from `AbilityTables` so the skill never does the arithmetic itself.
_MODIFIER_LABELS = {
    AbilityScore.STR: "melee and missile attack/damage, and open-doors chance",
    AbilityScore.INT: "extra languages known",
    AbilityScore.WIS: "saving throws versus magic",
    AbilityScore.DEX: "armour class and missile attacks",
    AbilityScore.CON: "hit points per Hit Die",
    AbilityScore.CHA: "NPC reaction rolls",
}


def _creation_stream(seed: int):
    return RngStreams(master_seed=seed).get(CHARACTER_CREATION_STREAM)


def _modifiers(scores: dict[AbilityScore, int]) -> dict[str, int]:
    tables = load_ability_tables()
    return {
        AbilityScore.STR.value: tables.melee_modifier(scores[AbilityScore.STR]),
        AbilityScore.INT.value: tables.additional_languages(scores[AbilityScore.INT]),
        AbilityScore.WIS.value: tables.magic_save_modifier(scores[AbilityScore.WIS]),
        AbilityScore.DEX.value: tables.ac_modifier(scores[AbilityScore.DEX]),
        AbilityScore.CON.value: tables.hit_point_modifier(scores[AbilityScore.CON]),
        AbilityScore.CHA.value: tables.npc_reaction_modifier(scores[AbilityScore.CHA]),
    }


def _class_entry(definition: ClassDefinition) -> dict[str, object]:
    profile = caster_profile(definition)
    return {
        "class_id": definition.id,
        "name": definition.name,
        "hit_die": definition.hit_die,
        "prime_requisites": [ability.value for ability in definition.prime_requisites],
        "caster": profile.kind if profile is not None else None,
    }


def eligible_classes(scores: dict[AbilityScore, int]) -> tuple[list[dict], list[dict]]:
    """Partition the class catalog into legal and illegal choices for a score set.

    Both depend on the rolled scores alone (`validate_class_choice` draws nothing and
    checks pre-adjustment scores), so `roll` can present a legal-by-construction menu
    without the skill computing eligibility itself.

    Args:
        scores: The rolled ability scores.

    Returns:
        `(eligible, ineligible)`, where `eligible` entries carry class metadata and
        `ineligible` entries add the blocking rejection codes.
    """
    from osrlib.core.character import validate_class_choice

    eligible: list[dict] = []
    ineligible: list[dict] = []
    for definition in load_classes().classes:
        rejections = validate_class_choice(scores, definition)
        if rejections:
            ineligible.append(
                {
                    **_class_entry(definition),
                    "rejections": [rejection.model_dump(mode="json") for rejection in rejections],
                }
            )
        else:
            eligible.append(_class_entry(definition))
    return eligible, ineligible


def roll_result(seed: int) -> dict[str, object]:
    """Roll ability scores from a seed and derive the eligible-class menu.

    Args:
        seed: The creation master seed.

    Returns:
        The scores, each ability's raw 3d6, the principal per-ability modifiers, and the
        eligible/ineligible class partition. No starting gold — that is `build`-time.
    """
    rolls = roll_ability_scores(_creation_stream(seed))
    eligible, ineligible = eligible_classes(rolls.scores)
    return {
        "seed": seed,
        "scores": {ability.value: score for ability, score in rolls.scores.items()},
        "rolls": {ability.value: list(dice) for ability, dice in rolls.rolls.items()},
        "modifiers": _modifiers(rolls.scores),
        "modifier_legend": {ability.value: label for ability, label in _MODIFIER_LABELS.items()},
        "eligible_classes": eligible,
        "ineligible_classes": ineligible,
    }


def _reject(code: str, **params: object) -> dict[str, object]:
    return {"ok": False, "rejections": [Rejection(code=code, params=params).model_dump(mode="json")]}


def _reject_list(rejections: list[Rejection]) -> dict[str, object]:
    return {"ok": False, "rejections": [rejection.model_dump(mode="json") for rejection in rejections]}


def build_result(
    seed: int,
    *,
    class_id: str,
    alignment: Alignment,
    adjustment: AbilityAdjustment | None = None,
    spell_ids: tuple[str, ...] = (),
    extra_languages: tuple[str, ...] = (),
    purchases: tuple[tuple[str, int], ...] = (),
    equip_ids: tuple[str, ...] = (),
    name: str = "Adventurer",
) -> dict[str, object]:
    """Build a finished character from a seed and all post-roll choices, deterministically.

    Re-derives the scores from the seed (identical draws to `roll`), then — the class now
    fixed — rolls hit points and gold in the contractual order and applies the choices,
    driving the stepwise validators so any illegal choice returns a structured rejection
    rather than raising. Idempotent per `(seed, class, choices)`: because every draw
    precedes the purchase step, calling this with no purchases (to reveal the gold) and
    again with the basket reproduces byte-identical scores/HP/gold.

    Args:
        seed: The creation master seed.
        class_id: The chosen class id.
        alignment: The chosen alignment.
        adjustment: The optional creation-time ability adjustment.
        spell_ids: The arcane starting spell book (magic-user/elf only).
        extra_languages: INT-granted extra language ids.
        purchases: `(item_id, lots)` pairs bought from the starting gold, in order.
        equip_ids: Item ids to equip after purchase, in order.
        name: The character's name; a placeholder is fine for the reveal-gold call, since
            the name touches no draw.

    Returns:
        `{ok: True, seed, hit_points, starting_gold_gp, purse, character, summary}` on
        success, or `{ok: False, rejections: [...]}` at the first illegal choice.
    """
    ruleset = Ruleset()
    try:
        definition = load_classes().get(class_id)
    except ValueError:
        return _reject("creation.class.unknown", **{"class": class_id})

    stream = _creation_stream(seed)
    ability_rolls = roll_ability_scores(stream)
    scores = dict(ability_rolls.scores)

    from osrlib.core.character import validate_class_choice

    class_rejections = validate_class_choice(scores, definition)
    if class_rejections:
        return _reject_list(class_rejections)

    if adjustment is not None:
        adjust_rejections = validate_adjustment(
            scores, adjustment, definition.prime_requisites, definition.may_not_lower
        )
        if adjust_rejections:
            return _reject_list(adjust_rejections)
        scores = apply_adjustment(scores, adjustment, definition.prime_requisites, definition.may_not_lower)

    profile = caster_profile(definition)
    if spell_ids or (profile is not None and profile.kind == "arcane"):
        spell_rejections = validate_starting_spells(definition, load_spells(), spell_ids)
        if spell_rejections:
            return _reject_list(spell_rejections)

    con_modifier = load_ability_tables().hit_point_modifier(scores[AbilityScore.CON])
    hit_point_roll = roll_hit_points(definition, con_modifier, ruleset, stream)

    language_rejections = validate_extra_languages(definition, scores[AbilityScore.INT], extra_languages)
    if language_rejections:
        return _reject_list(language_rejections)

    gold_roll = roll_starting_gold(stream)

    inventory = Inventory()
    inventory.purse.gp = gold_roll.total
    equipment = load_equipment()
    for item_id, lots in purchases:
        try:
            template = equipment.get(item_id)
        except ValueError:
            return _reject("creation.equipment.unknown_item", item=item_id)
        purchase_rejections = validate_purchase(inventory.purse, template, lots)
        if purchase_rejections:
            return _reject_list(purchase_rejections)
        purchase(inventory, template, lots)

    for equip_id in equip_ids:
        instance = next(
            (
                candidate
                for candidate in inventory.items
                if isinstance(candidate, ItemInstance) and candidate.template.id == equip_id
            ),
            None,
        )
        if instance is None:
            return _reject("creation.equip.not_in_inventory", item=equip_id)
        equip_rejections = validate_equip(definition, instance, inventory)
        if equip_rejections:
            return _reject_list(equip_rejections)
        equip(inventory, definition, instance)

    character = Character(
        name=name,
        class_id=definition.id,
        race=definition.race,
        level=1,
        xp=0,
        scores=scores,
        alignment=alignment,
        extra_languages=tuple(extra_languages),
        max_hp=hit_point_roll.hit_points,
        current_hp=hit_point_roll.hit_points,
        inventory=inventory,
        spell_book=tuple(spell_ids),
    )
    document = character.to_document()
    document["provenance"] = {"chargen_seed": seed, "class_id": definition.id}
    return {
        "ok": True,
        "seed": seed,
        "hit_points": {"rolls": list(hit_point_roll.rolls), "total": hit_point_roll.hit_points},
        "starting_gold_gp": gold_roll.total,
        "purse": inventory.purse.model_dump(mode="json"),
        "character": document,
        "summary": {
            "name": character.name,
            "class_id": character.class_id,
            "level": character.level,
            "max_hp": character.max_hp,
            "armour_class": character.armour_class,
            "armour_class_ascending": character.armour_class_ascending,
            "spell_book": list(character.spell_book),
        },
    }


def _parse_adjustment(lower: list[str] | None, raise_: list[str] | None) -> AbilityAdjustment | None:
    if not lower and not raise_:
        return None
    lowered: dict[AbilityScore, int] = {}
    raised: dict[AbilityScore, int] = {}
    for spec, bucket in ((lower or [], lowered), (raise_ or [], raised)):
        for entry in spec:
            ability_name, _, amount = entry.partition("=")
            bucket[AbilityScore(ability_name)] = int(amount)
    return AbilityAdjustment(lowered=lowered, raised=raised)


def _parse_purchases(buy: list[str] | None) -> tuple[tuple[str, int], ...]:
    purchases: list[tuple[str, int]] = []
    for entry in buy or []:
        item_id, _, lots = entry.partition(":")
        purchases.append((item_id, int(lots) if lots else 1))
    return tuple(purchases)


def _cmd_roll(args: argparse.Namespace) -> int:
    print(json.dumps(roll_result(args.seed), indent=2))
    return 0


def _cmd_build(args: argparse.Namespace) -> int:
    result = build_result(
        args.seed,
        class_id=args.class_id,
        alignment=Alignment(args.alignment),
        adjustment=_parse_adjustment(args.lower, args.raise_),
        spell_ids=tuple(args.spell or ()),
        extra_languages=tuple(args.extra_language or ()),
        purchases=_parse_purchases(args.buy),
        equip_ids=tuple(args.equip or ()),
        name=args.name,
    )
    print(json.dumps(result, indent=2))
    if not result["ok"]:
        return 1
    if args.out is not None:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(result["character"], indent=2))
    return 0


def _cmd_party(args: argparse.Namespace) -> int:
    members: list[Character] = []
    for char_path in args.character:
        document = json.loads(Path(char_path).read_text())
        members.append(Character.from_document(document))
    party_document = party_to_document(members)
    destination = party_path(resolve_game_root(), args.out)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(party_document, indent=2))
    print(json.dumps({"party_id": args.out, "path": str(destination), "members": len(members)}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the `chargen` argument parser.

    Returns:
        The parser, with `roll`, `build`, and `party` subcommands.
    """
    parser = argparse.ArgumentParser(prog="chargen", description="Deterministic, seed-driven character creation.")
    sub = parser.add_subparsers(dest="command", required=True)

    roll = sub.add_parser("roll", help="Roll ability scores from a seed; emit scores + the eligible-class menu.")
    roll.add_argument("--seed", type=int, required=True, help="The creation master seed.")
    roll.set_defaults(func=_cmd_roll)

    build = sub.add_parser("build", help="Build a finished character from a seed and all post-roll choices.")
    build.add_argument("--seed", type=int, required=True, help="The creation master seed (same as the roll).")
    build.add_argument("--class", dest="class_id", required=True, help="The chosen class id.")
    build.add_argument("--alignment", required=True, choices=[a.value for a in Alignment], help="The chosen alignment.")
    build.add_argument(
        "--lower", action="append", metavar="ABILITY=N", help="Adjustment: lower an ability (repeatable)."
    )
    build.add_argument(
        "--raise", dest="raise_", action="append", metavar="ABILITY=N", help="Adjustment: raise a prime requisite."
    )
    build.add_argument("--spell", action="append", metavar="SPELL_ID", help="Arcane starting spell (magic-user/elf).")
    build.add_argument("--extra-language", action="append", metavar="LANG_ID", help="INT-granted extra language.")
    build.add_argument("--buy", action="append", metavar="ITEM_ID[:LOTS]", help="Buy a purchase lot (repeatable).")
    build.add_argument("--equip", action="append", metavar="ITEM_ID", help="Equip a purchased item (repeatable).")
    build.add_argument(
        "--name", default="Adventurer", help="The character's name (a placeholder is fine to reveal gold)."
    )
    build.add_argument("--out", default=None, help="Write the finished character document to this path.")
    build.set_defaults(func=_cmd_build)

    party = sub.add_parser("party", help="Assemble character documents into a party in the game directory.")
    party.add_argument(
        "--out", required=True, metavar="PARTY_ID", help="The party id (writes <game-root>/parties/<id>.json)."
    )
    party.add_argument("character", nargs="+", help="The finished character document files, in marching order.")
    party.set_defaults(func=_cmd_party)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: The argument vector; defaults to `sys.argv[1:]`.

    Returns:
        The process exit code.
    """
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
