"""Read-only access to the shelf-of-holding page index — where a module's text comes from.

The compiler skill's first problem is not in this repo: before it can split boxed text
from referee notes it has to *have* the module's text. Reading a scanned PDF page by
page is the expensive way to get it. `shelf-of-holding` (`~/repos/shelf-of-holding`)
has already solved it for the whole shelf: it converts every page of every PDF under
`~/rpgbook` to Markdown and stores the results in a SQLite index whose `page_text` view
returns one Markdown text per page, picked from the best converter that covered it.
This module reads that view. Nothing here writes.

Three deliberate constraints:

- **Read-only, always.** The index is opened through a `file:…?mode=ro` URI, so a bug
  that tries to write fails loudly instead of touching a store a bulk conversion run may
  be writing to at the same time. WAL readers do not block that writer. This module
  never shells out to the `shelf` CLI, whose `scan`, `triage`, `convert`, and `gold`
  subcommands all write.
- **Optional.** The index is one person's local corpus, not a dependency. Every entry
  point raises [`ShelfUnavailableError`][osrlib_referee_mcp.shelf.ShelfUnavailableError]
  when it is absent, and the compiler falls back to whatever text the user supplies.
  Nothing in the play path imports this module.
- **`SHELF_DB` points wherever you like.** It defaults to the live store, but a snapshot
  is the better read while a bulk conversion is running: `shelf-of-holding`'s batch loop
  writes a verified copy after every batch and keeps dated copies of it, and pointing at
  one of those gives a stable file that no other process is rewriting under you.

The index stores **PDF page indexes**, not the page numbers printed on the page. A
module whose printed page 2 is PDF page 6 needs that offset established once, by eye,
before any range here means what the module's key says it means.
"""

import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DB = "~/.shelf-of-holding/shelf.db"
"""The live shelf-of-holding store, used when `SHELF_DB` is unset."""

BUSY_TIMEOUT_MS = 5000
"""How long to wait behind a writer's lock before giving up on a read."""

MAX_PAGES = 400
"""Most pages one `page_texts` call will return, so a fat range can't dump the shelf."""

_SHA_PREFIX = re.compile(r"^[0-9a-f]{6,64}$")


class ShelfUnavailableError(RuntimeError):
    """Raised when the shelf index is missing, unreadable, or not a shelf database."""


@dataclass(frozen=True)
class Book:
    """One PDF in the index, with its text coverage.

    Attributes:
        sha: The content hash the index keys every page on.
        path: The book's path relative to the shelf root (`~/rpgbook`).
        pages: The PDF's page count, or `None` if the index could not open it.
        pages_with_text: How many of those pages have Markdown in `page_text`.
        title: The PDF's embedded title, often absent or wrong.
    """

    sha: str
    path: str
    pages: int | None
    pages_with_text: int
    title: str | None


@dataclass(frozen=True)
class Page:
    """One page's converted Markdown.

    Attributes:
        page: The PDF page index, one-based, as the index stores it.
        converter: Which converter produced this text (`mineru`, `textlayer`, …).
        markdown: The page's Markdown.
    """

    page: int
    converter: str
    markdown: str


def resolve_db_path() -> Path:
    """Resolve the shelf index path from the environment, or the default.

    Returns:
        The expanded path from `SHELF_DB`, else [`DEFAULT_DB`][osrlib_referee_mcp.shelf.DEFAULT_DB].
        Not guaranteed to exist.
    """
    return Path(os.environ.get("SHELF_DB", DEFAULT_DB)).expanduser()


def _open(uri: str) -> sqlite3.Connection:
    """Open one read-only URI and configure the connection.

    `sqlite3.connect` is lazy, so the first statement is what actually opens the file
    and what raises when it cannot. The connection object is closed on that failure
    rather than left to the garbage collector.
    """
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    except sqlite3.Error:
        conn.close()
        raise
    return conn


def connect(db_path: Path | None = None) -> sqlite3.Connection:
    """Open the shelf index read-only.

    Args:
        db_path: The index to open. Defaults to
            [`resolve_db_path`][osrlib_referee_mcp.shelf.resolve_db_path].

    Returns:
        A read-only connection with `sqlite3.Row` rows.

    Raises:
        ShelfUnavailableError: If the file is missing, unreadable, or has no `page_text` view.
    """
    path = (db_path or resolve_db_path()).expanduser()
    if not path.is_file():
        raise ShelfUnavailableError(
            f"no shelf index at {path}. Set SHELF_DB to one, or compile from text you supply instead."
        )
    uri = path.resolve().as_uri()
    try:
        try:
            conn = _open(f"{uri}?mode=ro")
        except sqlite3.OperationalError:
            # A WAL database needs its `-shm` sidecar, and a read-only connection cannot
            # create one — so a snapshot copied away from its store (no `-wal`, no `-shm`)
            # fails to open at all. `immutable=1` skips the locking protocol and reads the
            # file directly, which is exactly right here and only here: a live store being
            # written right now *has* its `-shm`, so that open succeeds and never reaches
            # this fallback. Reaching it means no writer holds the file.
            conn = _open(f"{uri}?mode=ro&immutable=1")
    except sqlite3.Error as exc:
        raise ShelfUnavailableError(f"could not read the shelf index at {path}: {exc}") from exc
    try:
        has_view = conn.execute("SELECT 1 FROM sqlite_master WHERE type = 'view' AND name = 'page_text'").fetchone()
    except sqlite3.Error as exc:
        conn.close()
        raise ShelfUnavailableError(f"could not read the shelf index at {path}: {exc}") from exc
    if has_view is None:
        conn.close()
        raise ShelfUnavailableError(f"{path} is a database, but not a shelf index (no page_text view)")
    return conn


def _normalized(column: str) -> str:
    """SQL that lowercases `column` and flattens every separator to a space."""
    expr = f"lower({column})"
    for separator in ("-", "_", ".", "/"):
        expr = f"replace({expr}, '{separator}', ' ')"
    return expr


def find_books(conn: sqlite3.Connection, query: str, limit: int = 20) -> list[Book]:
    """Find indexed books whose path or title contains every word of `query`.

    Filenames on the shelf spell a title with whatever separator the publisher used
    (`x01-isle-of-dread.pdf`, `The_Tomb_of_Armansquagulat.pdf`), so a search for the
    title as a person writes it has to ignore separators. The query is split into words
    and each must appear, in the path or in the embedded title, with `-`, `_`, `.`, and
    `/` all read as spaces.

    Args:
        conn: An open index connection.
        query: Words to match, in any order and any case.
        limit: Most rows to return.

    Returns:
        Matching books, ordered by path. Books whose file has gone missing are skipped.
    """
    words = [w for w in re.split(r"[\s\-_./]+", query.lower()) if w]
    if not words:
        return []
    path_expr, title_expr = _normalized("p.path"), _normalized("coalesce(d.title, '')")
    clause = " AND ".join(f"({path_expr} LIKE ? OR {title_expr} LIKE ?)" for _ in words)
    params: list[object] = []
    for word in words:
        params.extend([f"%{word}%", f"%{word}%"])
    rows = conn.execute(
        f"""
        SELECT d.sha AS sha, p.path AS path, d.pages AS pages, d.title AS title,
               (SELECT count(*) FROM page_text t WHERE t.sha = d.sha) AS pages_with_text
        FROM pdf_path p JOIN pdf d ON d.sha = p.sha
        WHERE p.missing = 0 AND {clause}
        ORDER BY p.path
        LIMIT ?
        """,
        (*params, limit),
    ).fetchall()
    return [Book(r["sha"], r["path"], r["pages"], r["pages_with_text"], r["title"]) for r in rows]


def resolve_book(conn: sqlite3.Connection, ref: str) -> Book:
    """Resolve one book from a sha prefix or a path fragment.

    Args:
        conn: An open index connection.
        ref: A hex sha prefix of six characters or more, or a substring of the path.

    Returns:
        The single matching book.

    Raises:
        ValueError: If nothing matches, or if the reference matches more than one book.
    """
    if _SHA_PREFIX.match(ref.lower()):
        rows = conn.execute(
            """
            SELECT d.sha AS sha, p.path AS path, d.pages AS pages, d.title AS title,
                   (SELECT count(*) FROM page_text t WHERE t.sha = d.sha) AS pages_with_text
            FROM pdf_path p JOIN pdf d ON d.sha = p.sha
            WHERE p.missing = 0 AND d.sha LIKE ?
            ORDER BY p.path
            LIMIT 20
            """,
            (f"{ref.lower()}%",),
        ).fetchall()
        matches = [Book(r["sha"], r["path"], r["pages"], r["pages_with_text"], r["title"]) for r in rows]
    else:
        matches = find_books(conn, ref)
    if not matches:
        raise ValueError(f"no book in the shelf index matches {ref!r}")
    # One book copied to two paths is still one book: the sha is what pages key on.
    shas = {book.sha for book in matches}
    if len(shas) > 1:
        listed = "\n".join(f"  {b.sha[:8]}  {b.path}" for b in matches[:10])
        raise ValueError(f"{ref!r} matches {len(shas)} books; use a sha prefix:\n{listed}")
    return matches[0]


def page_texts(conn: sqlite3.Connection, sha: str, pages: list[int]) -> list[Page]:
    """Read the converted Markdown for specific pages of one book.

    Args:
        conn: An open index connection.
        sha: The book's content hash.
        pages: PDF page indexes to read, one-based.

    Returns:
        One [`Page`][osrlib_referee_mcp.shelf.Page] per requested page that has text,
        ordered by page. A page the index has not converted is simply absent — compare
        against `pages` to see the gaps.

    Raises:
        ValueError: If more than [`MAX_PAGES`][osrlib_referee_mcp.shelf.MAX_PAGES] pages are requested.
    """
    if len(pages) > MAX_PAGES:
        raise ValueError(f"{len(pages)} pages requested; ask for at most {MAX_PAGES} at a time")
    if not pages:
        return []
    placeholders = ",".join("?" * len(pages))
    rows = conn.execute(
        f"""
        SELECT t.page AS page, t.converter AS converter, t.markdown AS markdown
        FROM page_text t
        WHERE t.sha = ? AND t.page IN ({placeholders})
        ORDER BY t.page
        """,
        (sha, *pages),
    ).fetchall()
    return [Page(r["page"], r["converter"], r["markdown"]) for r in rows]


def parse_page_range(spec: str) -> list[int]:
    """Parse a page specification like `"4-12,20,25-27"` into page numbers.

    Args:
        spec: Comma-separated single pages and inclusive `start-end` ranges.

    Returns:
        The pages, sorted and deduplicated.

    Raises:
        ValueError: If the specification is empty, malformed, or names a page below 1.
    """
    pages: set[int] = set()
    for part in (p.strip() for p in spec.split(",")):
        if not part:
            continue
        if "-" in part:
            start_text, _, end_text = part.partition("-")
            try:
                start, end = int(start_text), int(end_text)
            except ValueError as exc:
                raise ValueError(f"{part!r} is not a page range like '4-12'") from exc
            if start < 1 or end < start:
                raise ValueError(f"{part!r} is not a page range like '4-12'")
            pages.update(range(start, end + 1))
        else:
            try:
                page = int(part)
            except ValueError as exc:
                raise ValueError(f"{part!r} is not a page number") from exc
            if page < 1:
                raise ValueError(f"{part!r} is not a page number")
            pages.add(page)
    if not pages:
        raise ValueError(f"{spec!r} names no pages")
    return sorted(pages)


def format_pages(book: Book, requested: list[int], texts: list[Page]) -> str:
    """Render pages as one Markdown document with page provenance on every page.

    Each page is preceded by an HTML comment naming its PDF page index and the converter
    that produced it, so the compiler can cite a keyed area back to a page — and so a
    page the index never converted shows up as a stated gap rather than as silence.

    Args:
        book: The book the pages came from.
        requested: The pages asked for.
        texts: The pages that had text, from [`page_texts`][osrlib_referee_mcp.shelf.page_texts].

    Returns:
        The assembled Markdown.
    """
    by_page = {page.page: page for page in texts}
    out = [f"<!-- shelf: {book.path} -->", f"<!-- sha: {book.sha} -->", ""]
    for number in requested:
        page = by_page.get(number)
        if page is None:
            out.append(f"<!-- page {number}: no text in the index -->")
        else:
            out.append(f"<!-- page {number} ({page.converter}) -->")
            out.append("")
            out.append(page.markdown.strip())
        out.append("")
    return "\n".join(out)
