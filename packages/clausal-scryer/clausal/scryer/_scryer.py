"""The Scryer session class."""
from __future__ import annotations

import re

import _scryer_ext


def _strip_module_directive(prolog_source: str) -> str:
    """Remove :- module(...). directives so predicates land in user module.

    Translated .clausal files may contain :- module(name, [exports]).
    when loading into the embedded Scryer session we want everything in
    the default 'user' module so queries work without module prefixes.
    """
    # Match :- module(...). spanning potentially multiple lines
    return re.sub(
        r'^:-\s*module\([^)]*\)\.\s*\n?',
        '',
        prolog_source,
        count=1,
        flags=re.MULTILINE,
    )


class Scryer:
    """Embedded Scryer Prolog session.

    A heavyweight object (~200ms to create). Create once, reuse across
    many queries. Supports context manager protocol for explicit lifecycle.

    The primary query interface is iteration::

        with Scryer() as s:
            s.load_string("parent(tom, bob). parent(bob, ann).")
            for sol in s.query("parent(X, Y)."):
                print(sol["X"], "->", sol["Y"])

    While iterating, the machine is exclusively held by the query.
    You can break out of the loop early — the iterator cleans up on
    drop.  But you cannot start a second query or load more code
    until the current iterator is exhausted, dropped, or closed.

    Examples
    --------
    >>> with Scryer() as s:
    ...     s.load_string("parent(tom, bob).")
    ...     s.query_one("parent(tom, X).")
    {'X': 'bob'}

    >>> s = Scryer()
    >>> s.consult_file("clausal/examples/graph.seam")
    >>> s.query_all("reachable(1, X).")
    [{'X': 2}, {'X': 3}, {'X': 4}, {'X': 5}, {'X': 6}]
    """

    def __init__(self):
        self._machine = _scryer_ext.RawScryerMachine()

    def _check_open(self):
        if self._machine is None:
            raise RuntimeError("This Scryer session has been closed")

    def close(self):
        """Release the Scryer machine. Idempotent."""
        self._machine = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()

    # ── Loading programs ──────────────────────────────────────────

    def consult_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source via consult (full module system).

        Warning: consult *replaces* earlier clauses for the same predicate
        within the same module. If you want to accumulate facts across
        multiple calls, use load_string() instead.
        """
        self._check_open()
        self._machine.consult_module_string(module, source)

    def load_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source via file_load.

        Like consult_string, this replaces earlier clauses for the same
        predicate.  For true accumulation, declare predicates as
        :- dynamic and use assertz/1 via query().
        """
        self._check_open()
        self._machine.load_module_string(module, source)

    def consult_file(self, path: str, module: str = "user") -> None:
        """Load a file into the machine.

        If the path ends with .clausal, the source is automatically
        translated to Prolog via clausal_source_to_prolog with Scryer
        dialect before loading.  The :- module(...) directive is stripped
        so predicates land in the target module (default: user).
        """
        self._check_open()
        from pathlib import Path
        p = Path(path)
        source = p.read_text(encoding="utf-8")
        if p.suffix == ".clausal":
            from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
            from clausal.tools.prolog_dialect import Dialect
            source = clausal_source_to_prolog(source, dialect=Dialect.scryer())
            source = _strip_module_directive(source)
        self.consult_string(source, module)

    def consult_clausal(self, source: str, module: str = "user") -> None:
        """Translate .clausal source to Prolog and consult it."""
        self._check_open()
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        from clausal.tools.prolog_dialect import Dialect
        prolog = clausal_source_to_prolog(source, dialect=Dialect.scryer())
        prolog = _strip_module_directive(prolog)
        self.consult_string(prolog, module)

    # ── Querying ──────────────────────────────────────────────────

    def query(self, goal: str):
        """Run a Prolog query. Returns an iterator over solution dicts.

        Each solution is a dict mapping variable names (str) to Python
        values (int, float, str, list, cell).

        Iteration is lazy — each call to next() resumes Prolog
        backtracking for one more solution.  Breaking out of the loop
        early is fine; the iterator cleans up on drop.

        While the iterator is alive, the machine is locked — you cannot
        load code or start another query until this one finishes.

        Parameters
        ----------
        goal : str
            Prolog query text, including the trailing period.
            E.g. "parent(tom, X)."
        """
        self._check_open()
        return self._machine.query(goal)

    def query_all(self, goal: str) -> list[dict]:
        """Run a query and collect all solutions into a list of dicts."""
        return list(self.query(goal))

    def query_one(self, goal: str) -> dict | None:
        """Return the first solution, or None if the query fails.

        Only evaluates one solution — does not backtrack further.
        """
        self._check_open()
        it = self._machine.query(goal)
        try:
            return next(it)
        except StopIteration:
            return None

    def query_bool(self, goal: str) -> bool:
        """Return True if the query succeeds at least once.

        Only evaluates one solution — does not backtrack further.
        """
        return self.query_one(goal) is not None
