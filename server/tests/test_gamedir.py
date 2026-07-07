"""Game-directory and adventures-directory resolution."""

from pathlib import Path

from osrlib_referee_mcp.gamedir import game_bundles_dir, repo_adventures_dir


def test_repo_adventures_dir_uses_a_clean_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("OSRLIB_REFEREE_ADVENTURES_DIR", str(tmp_path / "elsewhere"))

    assert repo_adventures_dir() == tmp_path / "elsewhere"


def test_repo_adventures_dir_ignores_an_unexpanded_env_value(monkeypatch):
    # A launcher that failed to substitute ${CLAUDE_PLUGIN_ROOT} must not shadow the
    # working fallback with a literal "${...}/adventures" path.
    monkeypatch.setenv("OSRLIB_REFEREE_ADVENTURES_DIR", "${CLAUDE_PLUGIN_ROOT}/adventures")

    resolved = repo_adventures_dir()

    assert "${" not in str(resolved)
    assert resolved.name == "adventures"


def test_repo_adventures_dir_fallback_points_at_the_committed_demo(monkeypatch):
    # The parents[3] fallback (used by the local uv run / --plugin-dir launch) must
    # actually resolve to the in-repo adventures/ holding the committed demo bundle.
    monkeypatch.delenv("OSRLIB_REFEREE_ADVENTURES_DIR", raising=False)

    fallback = repo_adventures_dir()

    assert (fallback / "sunken_chapel" / "manifest.json").is_file()


def test_game_bundles_dir_is_separate_from_saves():
    root = Path("/tmp/game")

    assert game_bundles_dir(root) == root / "bundles"
    assert game_bundles_dir(root) != root / "adventures"  # never the saves subtree
