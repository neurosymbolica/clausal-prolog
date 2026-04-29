"""The GNU Prolog session class."""
from __future__ import annotations

import re

import _gprolog_ext


def _strip_module_directive(prolog_source: str) -> str:
    """Remove :- module(...). directives.

    GNU Prolog has no module system, so these must be stripped.
    Translated .clausal files may contain them from the translation
    pipeline when using a non-gprolog dialect.
    """
    return re.sub(
        r'^:-\s*module\([^)]*\)\.\s*\n?',
        '',
        prolog_source,
        count=1,
        flags=re.MULTILINE,
    )


class GnuProlog:
    """Embedded GNU Prolog session.

    A lightweight wrapper around the GNU Prolog C engine.  GNU Prolog
    only supports one engine per process, so only one GnuProlog
    instance may exist at a time.

    The primary query interface is iteration::

        with GnuProlog() as g:
            g.consult_string("parent(tom, bob). parent(bob, ann).")
            for sol in g.query("parent(X, Y)."):
                print(sol["X"], "->", sol["Y"])

    While iterating, the machine is exclusively held by the query.
    You can break out of the loop early — the iterator cleans up on
    drop.  But you cannot start a second query or consult more code
    until the current iterator is exhausted, dropped, or closed.

    Note: Unlike Scryer, GNU Prolog has no module system.  All
    predicates live in a single global namespace.

    Examples
    --------
    >>> with GnuProlog() as g:
    ...     g.consult_string("parent(tom, bob).")
    ...     g.query_one("parent(tom, X).")
    {'X': 'bob'}

    >>> g = GnuProlog()
    >>> g.consult_string("solve(X) :- fd_domain(X, 1, 5), X #> 3, fd_labeling([X]).")
    >>> g.query_all("solve(X).")
    [{'X': 4}, {'X': 5}]
    """

    def __init__(self):
        self._machine = _gprolog_ext.RawGnuPrologMachine()

    def _check_open(self):
        if self._machine is None:
            raise RuntimeError("This GnuProlog session has been closed")

    def close(self):
        """Release the GNU Prolog engine. Idempotent.

        Warning: GNU Prolog's C runtime cannot be restarted after
        shutdown.  Once closed, no new GnuProlog instances can be
        created for the lifetime of the process.
        """
        if self._machine is not None:
            self._machine.close()
            self._machine = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()

    # ── Loading programs ──────────────────────────────────────────

    def consult_string(self, source: str) -> None:
        """Load Prolog source from a string.

        The source is written to a temporary file and consulted.
        Consult replaces earlier clauses for the same predicate.
        For accumulation, declare predicates as :- dynamic and use
        assertz/1 via query().
        """
        self._check_open()
        self._machine.consult_string(source)

    def consult_file(self, path: str) -> None:
        """Load a Prolog file into the engine.

        If the path ends with .clausal, the source is automatically
        translated to Prolog via clausal_source_to_prolog with GNU
        Prolog dialect before loading.  Module directives are stripped
        since GNU Prolog has no module system.
        """
        self._check_open()
        from pathlib import Path
        p = Path(path)
        if p.suffix == ".clausal":
            source = p.read_text(encoding="utf-8")
            from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
            from clausal.tools.prolog_dialect import Dialect
            prolog = clausal_source_to_prolog(source, dialect=Dialect.gprolog())
            prolog = _strip_module_directive(prolog)
            self._machine.consult_string(prolog)
        else:
            self._machine.consult_file(str(p))

    def consult_clausal(self, source: str) -> None:
        """Translate .clausal source to Prolog and consult it."""
        self._check_open()
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        from clausal.tools.prolog_dialect import Dialect
        prolog = clausal_source_to_prolog(source, dialect=Dialect.gprolog())
        prolog = _strip_module_directive(prolog)
        self._machine.consult_string(prolog)

    # ── Querying ──────────────────────────────────────────────────

    def query(self, goal: str):
        """Run a Prolog query. Returns an iterator over solution dicts.

        Each solution is a dict mapping variable names (str) to Python
        values (int, float, str, list, Compound).

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
