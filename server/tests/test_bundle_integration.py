"""The bundle server integration: discovery union, session-scoped prose, save scoping,
the loader error map, and an in-process delve driven through the real tool functions.

The Phase-1 `test_delve_golden` pattern applied to a *loaded* bundle: `session_new` on a
discovered bundle, then `observe`/`execute`/`prose` through a short delve to a save
round-trip. The delve is navigation-only (retry the light, no pinned combat outcome),
because a loaded bundle plays byte-identically to native content — the play-through
proves the bundle loads and plays, not anything reskin-specific.
"""

import json
import shutil
from pathlib import Path

import pytest
from osrlib.crawl.commands import EnterDungeon, LightSource, MoveParty, OpenDoor
from osrlib.crawl.dungeon import Direction
from osrlib.errors import ContentValidationError

from osrlib_referee_mcp.content import ADVENTURE_ID as NATIVE_ID
from osrlib_referee_mcp.server import execute, list_adventures, observe, session_load, session_new, session_save

FIXTURES = Path(__file__).parent / "fixtures" / "bundles" / "fixture_crypt"
FIXTURE_ID = "fixture_crypt"
FIXTURE_DUNGEON_ID = "redhollow_vault"


def _install_broken_bundle(root: Path) -> str:
    """Copy the fixture into `root` as a new bundle whose keyed monster doesn't resolve."""
    bundle_id = "broken_crypt"
    dest = root / bundle_id
    shutil.copytree(FIXTURES, dest)
    adventure = json.loads((dest / "adventure.json").read_text())
    den = next(a for a in adventure["dungeons"][0]["levels"][0]["areas"] if a["id"] == "den")
    den["encounter"]["monsters"][0]["template_id"] = "not_a_real_monster"
    (dest / "adventure.json").write_text(json.dumps(adventure))
    manifest = json.loads((dest / "manifest.json").read_text())
    manifest["bundle_id"] = bundle_id
    (dest / "manifest.json").write_text(json.dumps(manifest))
    return bundle_id


def _event_codes(result: dict) -> list[str]:
    return [event["code"] for event in result["events"]]


async def _light_torch() -> None:
    hero_id = observe()["party"][0]["id"]
    for _ in range(40):
        light = await execute(LightSource(character_id=hero_id, item_id="torch"))
        assert light["accepted"]
        if "exploration.light.lit" in _event_codes(light):
            return
    raise AssertionError("torch never caught in 40 attempts")


def test_list_adventures_unions_native_and_bundles(_fresh_store, install_bundle):
    install_bundle(_fresh_store.adventures_dir)

    ids = {entry["adventure_id"] for entry in list_adventures()}

    assert NATIVE_ID in ids
    assert FIXTURE_ID in ids


def test_list_adventures_skips_a_malformed_bundle(_fresh_store, install_bundle):
    install_bundle(_fresh_store.adventures_dir)
    broken = _fresh_store.adventures_dir / "malformed"
    broken.mkdir(parents=True)
    (broken / "manifest.json").write_text("{ not valid json")

    ids = {entry["adventure_id"] for entry in list_adventures()}

    assert FIXTURE_ID in ids  # the good bundle still lists; the bad one is skipped


@pytest.mark.anyio
async def test_session_new_on_a_bundle_loads_from_disk(_fresh_store, install_bundle):
    install_bundle(_fresh_store.game_bundles_dir)

    result = await session_new(FIXTURE_ID, seed=7)

    assert result["save_id"] == FIXTURE_ID  # default slot is adventure-scoped
    assert observe()["location"]["kind"] == "town"


@pytest.mark.anyio
async def test_bundle_load_failure_raises_through_the_tool(_fresh_store):
    # The play-path error map: session_new -> GameSession.new self-validates against
    # stock, a different path from validate_bundle's compile gate.
    bundle_id = _install_broken_bundle(_fresh_store.game_bundles_dir)

    with pytest.raises(ContentValidationError):
        await session_new(bundle_id, seed=1)


@pytest.mark.anyio
async def test_prose_is_session_scoped_across_a_shared_area_id(_fresh_store, install_bundle):
    from osrlib_referee_mcp.server import prose

    install_bundle(_fresh_store.game_bundles_dir)

    # Both the fixture and the native adventure key an area "entrance" — a module-global
    # prose lookup would be wrong once both exist.
    await session_new(FIXTURE_ID, seed=1)
    bundle_entrance = prose("entrance")
    assert bundle_entrance["found"] is True
    assert "stone door" in bundle_entrance["read_aloud"]

    await session_new(NATIVE_ID, seed=1)
    native_entrance = prose("entrance")
    assert native_entrance["found"] is True
    assert "archway" in native_entrance["read_aloud"]
    assert native_entrance["read_aloud"] != bundle_entrance["read_aloud"]


@pytest.mark.anyio
async def test_prose_re_resolves_after_a_bundle_reload(_fresh_store, install_bundle):
    from osrlib_referee_mcp.server import prose

    install_bundle(_fresh_store.game_bundles_dir)
    await session_new(FIXTURE_ID, seed=1)
    await session_save()

    await session_load(FIXTURE_ID)
    vault = prose("vault")

    assert vault["found"] is True
    assert "strong room" in vault["read_aloud"].lower()


@pytest.mark.anyio
async def test_default_save_slots_do_not_collide_across_adventures(_fresh_store, install_bundle):
    install_bundle(_fresh_store.game_bundles_dir)

    await session_new(FIXTURE_ID, seed=1)  # default slot "fixture_crypt"
    await session_new(NATIVE_ID, seed=1)  # default slot "barrow_crypt"

    loaded_bundle = await session_load(FIXTURE_ID)
    loaded_native = await session_load(NATIVE_ID)

    assert loaded_bundle["save_id"] == FIXTURE_ID
    assert loaded_native["save_id"] == NATIVE_ID


@pytest.mark.anyio
async def test_shared_explicit_slot_still_collides_as_the_backstop(_fresh_store, install_bundle):
    install_bundle(_fresh_store.game_bundles_dir)

    await session_new(FIXTURE_ID, seed=1, save_id="shared")
    await session_new(NATIVE_ID, seed=1, save_id="shared")

    with pytest.raises(ValueError, match="ambiguous"):
        await session_load("shared")


@pytest.mark.anyio
async def test_loaded_bundle_plays_end_to_end(_fresh_store, install_bundle):
    from osrlib_referee_mcp.server import prose

    install_bundle(_fresh_store.adventures_dir)

    new = await session_new(FIXTURE_ID, seed=7)
    assert new["save_id"] == FIXTURE_ID

    cold = observe()
    assert cold["location"]["kind"] == "town"
    assert "events" in cold  # a cold observe carries the recap tail
    assert prose("town")["found"] is True

    enter = await execute(EnterDungeon(dungeon_id=FIXTURE_DUNGEON_ID))
    assert enter["accepted"]
    assert observe()["area"]["id"] == "entrance"

    await _light_torch()

    opened = await execute(OpenDoor(direction=Direction.EAST))
    assert opened["accepted"]

    into_vault = await execute(MoveParty(direction=Direction.EAST))
    assert into_vault["accepted"]
    assert observe()["area"]["id"] == "vault"
    assert prose("vault")["found"] is True

    saved = await session_save()
    reloaded = await session_load(saved["save_id"])

    assert reloaded["save_id"] == FIXTURE_ID
    assert observe()["area"]["id"] == "vault"  # the reload resumes in the vault
