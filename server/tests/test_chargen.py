"""The deterministic character-creation golden, driven through the chargen CLI functions.

Pins the seed-driven determinism the whole party surface rests on: a fixed seed yields
fixed scores/HP/gold, `build` is byte-identical across runs and idempotent with or
without purchases, and an illegal choice comes back as a *structured rejection* at the
CLI boundary — never a stack trace.
"""

import json

from osrlib.core.alignment import Alignment

from osrlib_referee_mcp import chargen

# The seed-42 golden. Pinned against osrlib v1.1.0; a change here means a creation-draw
# or ordering change in the engine, which the party surface must notice.
GOLDEN_SEED = 42
GOLDEN_SCORES = {"str": 10, "int": 12, "wis": 15, "dex": 15, "con": 11, "cha": 11}
GOLDEN_FIGHTER_HP = 5
GOLDEN_FIGHTER_GOLD = 140


def test_roll_is_deterministic_and_pins_the_golden_scores():
    first = chargen.roll_result(GOLDEN_SEED)
    second = chargen.roll_result(GOLDEN_SEED)
    assert first == second
    assert first["scores"] == GOLDEN_SCORES
    # Every eligible class is legal-by-construction; the payload carries no gold (gold is
    # class-dependent and therefore a build-time result, never a roll-time one).
    assert "starting_gold_gp" not in first
    eligible_ids = {entry["class_id"] for entry in first["eligible_classes"]}
    assert "fighter" in eligible_ids


def test_build_is_byte_identical_across_runs_and_pins_hp_and_gold():
    kwargs = dict(class_id="fighter", alignment=Alignment.LAWFUL, name="Brakka")
    first = chargen.build_result(GOLDEN_SEED, **kwargs)
    second = chargen.build_result(GOLDEN_SEED, **kwargs)
    assert first["ok"] and second["ok"]
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert first["hit_points"]["total"] == GOLDEN_FIGHTER_HP
    assert first["starting_gold_gp"] == GOLDEN_FIGHTER_GOLD


def test_build_is_idempotent_with_and_without_purchases():
    reveal = chargen.build_result(GOLDEN_SEED, class_id="fighter", alignment=Alignment.LAWFUL)
    final = chargen.build_result(
        GOLDEN_SEED,
        class_id="fighter",
        alignment=Alignment.LAWFUL,
        purchases=(("sword", 1), ("leather", 1)),
        equip_ids=("sword", "leather"),
        name="Brakka",
    )
    # Every draw precedes the purchase step, so revealing gold and then finalizing
    # reproduces byte-identical scores/HP/gold — only the purse and inventory differ.
    assert reveal["hit_points"] == final["hit_points"]
    assert reveal["starting_gold_gp"] == final["starting_gold_gp"]
    assert reveal["character"]["payload"]["scores"] == final["character"]["payload"]["scores"]
    assert final["purse"]["gp"] == GOLDEN_FIGHTER_GOLD - (10 + 20)  # sword 10 gp, leather 20 gp


def test_illegal_class_choice_returns_a_structured_rejection():
    # At seed 3 CON is 7, below the dwarf's minimum — a rejection, not an exception.
    result = chargen.build_result(3, class_id="dwarf", alignment=Alignment.LAWFUL, name="Durin")
    assert result["ok"] is False
    assert any(rej["code"] == "creation.class.requirements_not_met" for rej in result["rejections"])


def test_unaffordable_basket_returns_a_structured_rejection():
    over_budget = tuple(("plate_mail", 1) for _ in range(4))  # 60 gp each, far past 140
    result = chargen.build_result(
        GOLDEN_SEED, class_id="fighter", alignment=Alignment.LAWFUL, purchases=over_budget, name="Brakka"
    )
    assert result["ok"] is False
    assert any(rej["code"] == "items.purchase.insufficient_funds" for rej in result["rejections"])


def test_unknown_equipment_id_returns_a_structured_rejection():
    result = chargen.build_result(
        GOLDEN_SEED, class_id="fighter", alignment=Alignment.LAWFUL, purchases=(("nonesuch", 1),), name="Brakka"
    )
    assert result["ok"] is False
    assert any(rej["code"] == "creation.equipment.unknown_item" for rej in result["rejections"])


def test_arcane_caster_records_the_starting_spell_book():
    result = chargen.build_result(
        GOLDEN_SEED, class_id="magic_user", alignment=Alignment.NEUTRAL, spell_ids=("magic_missile",), name="Vex"
    )
    assert result["ok"] is True
    assert result["character"]["payload"]["spell_book"] == ["magic_missile"]
    assert result["summary"]["spell_book"] == ["magic_missile"]


def test_cli_boundary_returns_exit_code_one_on_a_rejection(capsys):
    code = chargen.main(["build", "--seed", "3", "--class", "dwarf", "--alignment", "lawful"])
    assert code == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["rejections"]


def test_cli_roll_emits_the_eligible_class_menu(capsys):
    code = chargen.main(["roll", "--seed", str(GOLDEN_SEED)])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["scores"] == GOLDEN_SCORES
    assert payload["eligible_classes"]
