"""The session store: one live `GameSession`, a lock, and durable saves.

osrlib does zero file I/O and assigns no save ids — persistence is pure dict-in/
dict-out (`osrlib.persistence`). Durable disk saves, the `save_id`, and adventure
resolution are entirely this server's to invent. `GameSession` is not thread-safe by
contract (no locking exists inside osrlib itself), so every mutation here runs under
one `asyncio.Lock` — safety insurance for a single-client stdio server, not a
concurrency necessity.
"""

import json
import random

from osrlib.core.character import party_from_document
from osrlib.crawl.adventure import Adventure
from osrlib.crawl.party import Party
from osrlib.crawl.session import GameSession
from osrlib.persistence import load_game, save_game

from osrlib_referee_mcp.content import ADVENTURE_REGISTRY, default_party_document
from osrlib_referee_mcp.gamedir import find_save, resolve_game_root, save_path


class SessionStore:
    """Holds the single live session a stdio server serves, plus its save identity."""

    def __init__(self) -> None:
        """Create an empty store: no active session until `new` or `load` runs."""
        self.game_root = resolve_game_root()
        self._session: GameSession | None = None
        self._adventure_id: str | None = None
        self._save_id: str | None = None
        self.needs_recap = False

    @property
    def session(self) -> GameSession:
        """The active session.

        Raises:
            ValueError: No session is active yet — call `session_new` or `session_load`.
        """
        if self._session is None:
            raise ValueError("no active session; call session_new or session_load first")
        return self._session

    def _resolve_adventure(self, adventure_id: str) -> Adventure:
        builder = ADVENTURE_REGISTRY.get(adventure_id)
        if builder is None:
            raise ValueError(f"unknown adventure_id {adventure_id!r}; known: {sorted(ADVENTURE_REGISTRY)}")
        return builder()

    def new(
        self,
        adventure_id: str,
        *,
        seed: int | None,
        party_document: dict[str, object] | None,
        save_id: str,
    ) -> dict[str, object]:
        """Start a fresh session and persist it immediately.

        Args:
            adventure_id: A key in the server's native adventure registry.
            seed: The master seed; a fresh, unpredictable seed is drawn if omitted.
            party_document: A `party_to_document` document; the frozen pregen roster
                if omitted.
            save_id: The save slot stem this session will persist under.

        Returns:
            `{schema_version, engine_version, save_id}` — never the seed.

        Raises:
            ValueError: `adventure_id` is not in the registry.
            ContentValidationError: The adventure or party document is malformed.
        """
        adventure = self._resolve_adventure(adventure_id)
        document = party_document if party_document is not None else default_party_document()
        members = party_from_document(document)
        resolved_seed = seed if seed is not None else _fresh_seed()
        session = GameSession.new(Party(members=members), adventure, seed=resolved_seed)
        self._session = session
        self._adventure_id = adventure_id
        self._save_id = save_id
        self.needs_recap = True
        self._persist()
        return {**session.metadata, "save_id": save_id}

    def load(self, save_id: str) -> dict[str, object]:
        """Load a save by id and make it the active session.

        A save document embeds its own adventure spec, so no `adventure_id` is
        needed. Listeners and action policies never survive a save round-trip by
        osrlib's own contract — Phase 1 registers none, so there is nothing to
        re-attach; a future phase that adds either must re-register them here.

        Args:
            save_id: The save slot stem to load.

        Returns:
            `{schema_version, engine_version, save_id}`.

        Raises:
            ValueError: No save (or more than one) matches `save_id`.
            ContentValidationError: The save document is malformed.
            SaveVersionError: The save is from a newer engine.
        """
        path = find_save(self.game_root, save_id)
        document = json.loads(path.read_text())
        session = load_game(document)
        self._session = session
        self._adventure_id = path.parent.name
        self._save_id = save_id
        self.needs_recap = True
        return {**session.metadata, "save_id": save_id}

    def save(self) -> dict[str, object]:
        """Persist the active session to its current save slot.

        Returns:
            `{schema_version, engine_version, save_id}`.
        """
        self._persist()
        return {**self.session.metadata, "save_id": self._save_id}

    def _persist(self) -> None:
        session = self.session
        if self._adventure_id is None or self._save_id is None:
            raise ValueError("no active session; call session_new or session_load first")
        document = save_game(session)
        path = save_path(self.game_root, self._adventure_id, self._save_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(document))


def _fresh_seed() -> int:
    return random.SystemRandom().getrandbits(63)
