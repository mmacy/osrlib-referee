"""Read-only access to the shelf-of-holding page index."""

import sqlite3
from contextlib import closing

import pytest

from osrlib_referee_mcp import shelf

# Copied verbatim from a real shelf.db (`sqlite3 shelf.db .schema`) so the fixture's
# converter precedence is the index's own, not a restatement of it.
PAGE_TEXT_VIEW = """
CREATE VIEW page_text AS
  SELECT c.* FROM conversion c
  WHERE c.status = 'ok' AND length(c.markdown) > 0 AND c.id = (
    SELECT c2.id FROM conversion c2
    WHERE c2.sha = c.sha AND c2.page = c.page AND c2.status = 'ok' AND length(c2.markdown) > 0
    ORDER BY CASE c2.converter WHEN 'mineru' THEN 0 WHEN 'chandra' THEN 1 WHEN 'qwen' THEN 2 ELSE 3 END,
             c2.created_at DESC, c2.id DESC
    LIMIT 1)
"""

SCHEMA = """
CREATE TABLE pdf (sha TEXT PRIMARY KEY, bytes INTEGER NOT NULL, pages INTEGER, title TEXT,
                  first_seen TEXT NOT NULL, last_seen TEXT NOT NULL);
CREATE TABLE pdf_path (path TEXT PRIMARY KEY, sha TEXT NOT NULL REFERENCES pdf(sha),
                       bytes INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                       seen_at TEXT NOT NULL, missing INTEGER NOT NULL DEFAULT 0);
CREATE TABLE conversion (id INTEGER PRIMARY KEY, sha TEXT NOT NULL, page INTEGER NOT NULL,
                         converter TEXT NOT NULL, version TEXT NOT NULL, status TEXT NOT NULL,
                         markdown TEXT, created_at TEXT NOT NULL);
"""

SHA_KEEP = "aa11bb22cc33dd44"
SHA_TOMB = "ff99ee88dd77cc66"


def build_index(path, wal: bool = False) -> None:
    """Write a small shelf-shaped index: two books, one of them stored at two paths."""
    with closing(sqlite3.connect(path)) as conn:
        if wal:
            conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA + PAGE_TEXT_VIEW)
        conn.executemany(
            "INSERT INTO pdf (sha, bytes, pages, title, first_seen, last_seen) VALUES (?, ?, ?, ?, 't', 't')",
            [(SHA_KEEP, 100, 3, "Keep on the Borderlands"), (SHA_TOMB, 200, 2, None)],
        )
        conn.executemany(
            "INSERT INTO pdf_path (path, sha, bytes, mtime_ns, seen_at, missing) VALUES (?, ?, 1, 1, 't', ?)",
            [
                ("bx/keep.pdf", SHA_KEEP, 0),
                ("backup/keep-copy.pdf", SHA_KEEP, 0),  # same book, second path
                ("ose/tomb.pdf", SHA_TOMB, 0),
                ("gone/deleted.pdf", SHA_TOMB, 1),  # missing: never listed
            ],
        )
        conn.executemany(
            "INSERT INTO conversion (sha, page, converter, version, status, markdown, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 't')",
            [
                (SHA_KEEP, 1, "textlayer", "1", "ok", "layer text for page 1"),
                (SHA_KEEP, 1, "mineru", "2", "ok", "mineru text for page 1"),
                (SHA_KEEP, 2, "textlayer", "1", "ok", "layer text for page 2"),
                (SHA_KEEP, 3, "mineru", "2", "error", None),  # page 3 has no usable text
                (SHA_TOMB, 1, "mineru", "2", "ok", "tomb page 1"),
            ],
        )
        conn.commit()


@pytest.fixture
def index(tmp_path, monkeypatch):
    path = tmp_path / "shelf.db"
    build_index(path)
    monkeypatch.setenv("SHELF_DB", str(path))
    return path


def test_resolve_db_path_prefers_the_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("SHELF_DB", str(tmp_path / "snapshot.db"))

    assert shelf.resolve_db_path() == tmp_path / "snapshot.db"


def test_resolve_db_path_defaults_to_the_live_store(monkeypatch):
    monkeypatch.delenv("SHELF_DB", raising=False)

    assert shelf.resolve_db_path().name == "shelf.db"


def test_connect_reports_a_missing_index_as_unavailable(monkeypatch, tmp_path):
    monkeypatch.setenv("SHELF_DB", str(tmp_path / "nothing.db"))

    with pytest.raises(shelf.ShelfUnavailableError, match="no shelf index"):
        shelf.connect()


def test_connect_rejects_a_database_that_is_not_a_shelf_index(monkeypatch, tmp_path):
    other = tmp_path / "other.db"
    with closing(sqlite3.connect(other)) as conn:
        conn.execute("CREATE TABLE unrelated (x INTEGER)")
    monkeypatch.setenv("SHELF_DB", str(other))

    with pytest.raises(shelf.ShelfUnavailableError, match="not a shelf index"):
        shelf.connect()


def test_the_connection_cannot_write(index):
    # The whole safety story: a bulk conversion run may own this file. Read-only mode
    # has to be in force, not merely intended.
    with closing(shelf.connect()) as conn, pytest.raises(sqlite3.OperationalError, match="readonly"):
        conn.execute("DELETE FROM conversion")


def test_connect_opens_a_wal_snapshot_with_no_sidecars(tmp_path, monkeypatch):
    # A snapshot copied away from its store is a WAL database with no -wal or -shm
    # beside it, which a plain read-only open cannot touch. This is the shape of every
    # backup-host copy, so it must open.
    path = tmp_path / "snapshot.db"
    build_index(path, wal=True)
    assert not (tmp_path / "snapshot.db-shm").exists()
    monkeypatch.setenv("SHELF_DB", str(path))

    with closing(shelf.connect()) as conn:
        assert shelf.find_books(conn, "keep")


def test_find_books_matches_path_or_title_and_skips_missing_files(index):
    with closing(shelf.connect()) as conn:
        by_path = shelf.find_books(conn, "tomb")
        by_title = shelf.find_books(conn, "borderlands")
        every = shelf.find_books(conn, ".pdf")

    assert [b.path for b in by_path] == ["ose/tomb.pdf"]
    assert {b.sha for b in by_title} == {SHA_KEEP}
    assert "gone/deleted.pdf" not in [b.path for b in every]


def test_find_books_ignores_separators(index):
    # Filenames spell a title with whatever separator the publisher used, so searching
    # for it the way a person writes it has to match: x01-isle-of-dread.pdf for
    # "isle of dread".
    with closing(shelf.connect()) as conn:
        spaced = shelf.find_books(conn, "keep copy")
        hyphenated = shelf.find_books(conn, "keep-copy")

    assert [b.path for b in spaced] == ["backup/keep-copy.pdf"]
    assert [b.path for b in hyphenated] == ["backup/keep-copy.pdf"]


def test_find_books_requires_every_word(index):
    with closing(shelf.connect()) as conn:
        both = shelf.find_books(conn, "tomb ose")
        unmatched = shelf.find_books(conn, "tomb borderlands")

    assert [b.path for b in both] == ["ose/tomb.pdf"]
    assert unmatched == []


def test_find_books_matches_nothing_on_a_query_of_only_separators(index):
    with closing(shelf.connect()) as conn:
        assert shelf.find_books(conn, " -_/ ") == []


def test_find_books_counts_pages_with_text(index):
    with closing(shelf.connect()) as conn:
        (book,) = shelf.find_books(conn, "ose/tomb")

    assert book.pages == 2  # the PDF has two pages
    assert book.pages_with_text == 1  # only one is converted


def test_resolve_book_accepts_a_sha_prefix(index):
    with closing(shelf.connect()) as conn:
        book = shelf.resolve_book(conn, SHA_KEEP[:8])

    assert book.sha == SHA_KEEP


def test_resolve_book_treats_one_book_at_two_paths_as_unambiguous(index):
    with closing(shelf.connect()) as conn:
        book = shelf.resolve_book(conn, "keep")

    assert book.sha == SHA_KEEP


def test_resolve_book_rejects_a_reference_matching_two_books(index):
    with closing(shelf.connect()) as conn, pytest.raises(ValueError, match="matches 2 books"):
        shelf.resolve_book(conn, ".pdf")


def test_resolve_book_rejects_a_reference_matching_nothing(index):
    with closing(shelf.connect()) as conn, pytest.raises(ValueError, match="no book"):
        shelf.resolve_book(conn, "no-such-module")


def test_page_texts_takes_the_views_best_converter(index):
    with closing(shelf.connect()) as conn:
        pages = shelf.page_texts(conn, SHA_KEEP, [1, 2, 3])

    # Page 1 has both converters; the view prefers mineru. Page 3 stored an error row.
    assert [(p.page, p.converter) for p in pages] == [(1, "mineru"), (2, "textlayer")]
    assert pages[0].markdown == "mineru text for page 1"


def test_page_texts_refuses_an_oversized_range(index):
    with closing(shelf.connect()) as conn, pytest.raises(ValueError, match="at most"):
        shelf.page_texts(conn, SHA_KEEP, list(range(1, shelf.MAX_PAGES + 2)))


@pytest.mark.parametrize(
    ("spec", "expected"),
    [("5", [5]), ("4-6", [4, 5, 6]), ("3,1", [1, 3]), ("1-2,2-3", [1, 2, 3]), (" 7 , 9 ", [7, 9])],
)
def test_parse_page_range_reads_pages_and_ranges(spec, expected):
    assert shelf.parse_page_range(spec) == expected


@pytest.mark.parametrize("spec", ["", "0", "6-4", "x", "1-", "-3", "1.5"])
def test_parse_page_range_rejects_nonsense(spec):
    with pytest.raises(ValueError):
        shelf.parse_page_range(spec)


def test_format_pages_marks_a_page_the_index_never_converted(index):
    with closing(shelf.connect()) as conn:
        book = shelf.resolve_book(conn, SHA_KEEP[:8])
        rendered = shelf.format_pages(book, [1, 3], shelf.page_texts(conn, SHA_KEEP, [1, 3]))

    assert "<!-- page 1 (mineru) -->" in rendered
    assert "<!-- page 3: no text in the index -->" in rendered
    assert book.sha in rendered  # provenance travels with the text
