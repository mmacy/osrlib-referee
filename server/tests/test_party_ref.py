"""Party assembly, the `chargen party` CLI, and `session_new(party_ref=…)` precedence.

Proves a built party reaches a session by a short id — the whole (large) document stays
off the conversation wire — and that party resolution follows the pinned precedence
`party_document` > `party_ref` > pregen default.
"""

import json

import pytest
from osrlib.core.alignment import Alignment
from osrlib.core.character import Character, party_to_document

from osrlib_referee_mcp import chargen
from osrlib_referee_mcp import server as server_module


def _character_document(seed, class_id, alignment, name, purchases=(), equip_ids=()):
    result = chargen.build_result(
        seed, class_id=class_id, alignment=alignment, purchases=purchases, equip_ids=equip_ids, name=name
    )
    assert result["ok"], result
    return result["character"]


@pytest.mark.anyio
async def test_chargen_party_cli_writes_a_loadable_party(_fresh_store, tmp_path, monkeypatch):
    # Point the CLI's game-root resolver at the same tmp dir the store loads party refs from.
    monkeypatch.setenv("OSRLIB_REFEREE_GAME_ROOT", str(_fresh_store.game_root))
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    brakka = build_dir / "brakka.json"
    wynn = build_dir / "wynn.json"
    brakka.write_text(
        json.dumps(_character_document(101, "fighter", Alignment.LAWFUL, "Brakka", (("sword", 1),), ("sword",)))
    )
    wynn.write_text(json.dumps(_character_document(102, "cleric", Alignment.LAWFUL, "Wynn", (("mace", 1),), ("mace",))))

    code = chargen.main(["party", "--out", "heroes", str(brakka), str(wynn)])
    assert code == 0

    await server_module.session_new("barrow_crypt", seed=1, party_ref="heroes")
    party = server_module.observe()["party"]
    assert [(m["name"], m["class_id"]) for m in party] == [("Brakka", "fighter"), ("Wynn", "cleric")]
    # GameSession.new assigns entity ids to members that carry none pre-session.
    assert all(m["id"] for m in party)


def _write_party(store, party_id, characters):
    document = party_to_document(characters)
    path = store.game_root / "parties" / f"{party_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document))


@pytest.mark.anyio
async def test_party_precedence_document_then_ref_then_pregen(_fresh_store):
    store = _fresh_store
    ref_member = Character.from_document(_character_document(200, "thief", Alignment.NEUTRAL, "Sable"))
    _write_party(store, "refparty", [ref_member])
    inline = party_to_document(
        [Character.from_document(_character_document(201, "fighter", Alignment.LAWFUL, "Inline"))]
    )

    # Inline document wins even when a ref is also supplied.
    await server_module.session_new(
        "barrow_crypt", seed=1, party_document=inline, party_ref="refparty", save_id="prec_doc"
    )
    assert [m["name"] for m in server_module.observe()["party"]] == ["Inline"]

    # The ref is used when no inline document is given.
    await server_module.session_new("barrow_crypt", seed=1, party_ref="refparty", save_id="prec_ref")
    assert [m["name"] for m in server_module.observe()["party"]] == ["Sable"]

    # The frozen pregen roster (fighter, cleric, thief) starts when neither is given.
    await server_module.session_new("barrow_crypt", seed=1, save_id="prec_pregen")
    pregen = server_module.observe()["party"]
    assert [m["class_id"] for m in pregen] == ["fighter", "cleric", "thief"]


@pytest.mark.anyio
async def test_unknown_party_ref_is_an_error(_fresh_store):
    with pytest.raises(ValueError, match="no party found"):
        await server_module.session_new("barrow_crypt", seed=1, party_ref="does-not-exist")
