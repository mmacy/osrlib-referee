"""The bundle format, its loader, and the `validate_bundle` compile gate.

The committed fixture bundle round-trips (`Adventure.model_validate` reconstructs it,
`validate_bundle` passes); the deliberately-broken cases prove `validate_bundle` catches
what `validate_adventure` alone skips — dead edge keys and unresolved wandering-table
ids — plus the keyed-monster resolution it inherits from `validate_adventure`.
"""

import copy
import json
from pathlib import Path

import pytest
from osrlib.crawl.adventure import Adventure
from osrlib.crawl.dungeon import Direction, edge_key
from osrlib.errors import ContentValidationError

from osrlib_referee_mcp.bundle import (
    edge_key_integrity_errors,
    load_bundle,
    render_map,
    validate_bundle,
)

FIXTURES = Path(__file__).parent / "fixtures" / "bundles" / "fixture_crypt"


def _fixture_dict(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text())


def _make_bundle(dest: Path, mutate=None) -> Path:
    """Write a bundle into `dest`, optionally mutating the adventure dict first."""
    dest.mkdir(parents=True, exist_ok=True)
    adventure = copy.deepcopy(_fixture_dict("adventure.json"))
    if mutate is not None:
        mutate(adventure)
    (dest / "adventure.json").write_text(json.dumps(adventure))
    (dest / "prose.json").write_text(json.dumps(_fixture_dict("prose.json")))
    (dest / "manifest.json").write_text(json.dumps(_fixture_dict("manifest.json")))
    return dest


def test_committed_fixture_round_trips_and_validates():
    bundle = load_bundle(FIXTURES)

    assert bundle.bundle_id == "fixture_crypt"
    assert isinstance(bundle.adventure, Adventure)
    assert bundle.adventure.name == "The Redhollow Vault"
    assert bundle.prose["town"]["read_aloud"]
    assert bundle.manifest["approximations"] == {"reskins": [], "geometry": [], "escape_hatch": []}
    validate_bundle(FIXTURES)  # does not raise


def test_validate_bundle_catches_out_of_bounds_edge_key(tmp_path):
    def add_boundary_edge(adventure):
        # "0,0:west" separates (0,0) and (-1,0); the neighbour is off-grid, so the
        # engine never reads it — the exact dead entry validate_adventure ignores.
        adventure["dungeons"][0]["levels"][0]["edges"]["0,0:west"] = {"kind": "open"}

    bundle_dir = _make_bundle(tmp_path / "boundary", add_boundary_edge)

    with pytest.raises(ContentValidationError, match="boundary edge"):
        validate_bundle(bundle_dir)


def test_validate_bundle_catches_non_canonical_edge_key(tmp_path):
    def add_south_edge(adventure):
        adventure["dungeons"][0]["levels"][0]["edges"]["1,0:east"] = {"kind": "open"}

    bundle_dir = _make_bundle(tmp_path / "south", add_south_edge)

    with pytest.raises(ContentValidationError, match="not a canonical"):
        validate_bundle(bundle_dir)


def test_validate_bundle_catches_unresolved_wandering_table_id(tmp_path):
    def break_wandering(adventure):
        rows = adventure["dungeons"][0]["levels"][0]["wandering"]["table"]["rows"]
        rows[0]["entry"]["monster_ids"] = ["not_a_real_monster"]

    bundle_dir = _make_bundle(tmp_path / "wander", break_wandering)

    with pytest.raises(ContentValidationError, match="wandering table row 1 references unknown monster"):
        validate_bundle(bundle_dir)


def test_validate_bundle_catches_unknown_keyed_monster(tmp_path):
    def break_keyed(adventure):
        den = next(a for a in adventure["dungeons"][0]["levels"][0]["areas"] if a["id"] == "den")
        den["encounter"]["monsters"][0]["template_id"] = "not_a_real_monster"

    bundle_dir = _make_bundle(tmp_path / "keyed", break_keyed)

    with pytest.raises(ContentValidationError, match="unknown monster 'not_a_real_monster'"):
        validate_bundle(bundle_dir)


def test_validate_bundle_catches_bad_prose_key(tmp_path):
    bundle_dir = _make_bundle(tmp_path / "prose")
    prose = json.loads((bundle_dir / "prose.json").read_text())
    prose["nowhere"] = {"read_aloud": "x", "referee_notes": "y"}
    (bundle_dir / "prose.json").write_text(json.dumps(prose))

    with pytest.raises(ContentValidationError, match="prose.json key 'nowhere'"):
        validate_bundle(bundle_dir)


def test_validate_bundle_rejects_bad_bundle_id(tmp_path):
    bundle_dir = _make_bundle(tmp_path / "slug")
    manifest = json.loads((bundle_dir / "manifest.json").read_text())
    manifest["bundle_id"] = "Not A Slug!"
    (bundle_dir / "manifest.json").write_text(json.dumps(manifest))

    with pytest.raises(ContentValidationError, match="must be a slug"):
        validate_bundle(bundle_dir)


def test_validate_bundle_reports_every_problem_at_once(tmp_path):
    # The whole point of validate_bundle over a fail-fast check: one pass surfaces a
    # keyed-monster miss (via validate_adventure), a dead edge key, and a wandering-id
    # miss together, so a compiler fixes them in one round rather than one at a time.
    def break_everything(adventure):
        level = adventure["dungeons"][0]["levels"][0]
        level["edges"]["0,0:west"] = {"kind": "open"}  # boundary dead key
        den = next(a for a in level["areas"] if a["id"] == "den")
        den["encounter"]["monsters"][0]["template_id"] = "no_such_keyed"  # validate_adventure miss
        level["wandering"]["table"]["rows"][0]["entry"]["monster_ids"] = ["no_such_wander"]  # wandering miss

    bundle_dir = _make_bundle(tmp_path / "everything", break_everything)

    with pytest.raises(ContentValidationError) as excinfo:
        validate_bundle(bundle_dir)
    message = str(excinfo.value)
    assert "no_such_keyed" in message
    assert "boundary edge" in message
    assert "no_such_wander" in message


def test_load_bundle_missing_file_raises_content_validation_error(tmp_path):
    (tmp_path / "empty").mkdir()

    with pytest.raises(ContentValidationError, match="is missing"):
        load_bundle(tmp_path / "empty")


def test_edge_key_integrity_passes_on_a_live_map():
    adventure = load_bundle(FIXTURES).adventure

    assert edge_key_integrity_errors(adventure) == []


def test_render_map_marks_entrance_area_and_door():
    level = load_bundle(FIXTURES).adventure.dungeons[0].levels[0]

    rendered = render_map(level)

    assert "@" in rendered  # the entrance cell
    assert "D" in rendered  # the door east of the entrance
    assert "= vault" in rendered  # the legend names the keyed areas


def test_edge_key_helper_matches_osrlib():
    # The CLI's edge-key wrapper must be the engine's own canonicalization, not a copy.
    assert edge_key((1, 0), Direction.EAST) == "2,0:west"
