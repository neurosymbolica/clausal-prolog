"""The Trealla Prolog session class."""

from __future__ import annotations

import re

from clausal.trealla._engine import TreallaMachine


def _strip_module_directive(prolog_source: str) -> str:
    """Remove :- module(...). directives so predicates land in user module."""
    return re.sub(
        r'^:-\s*module\([^)]*\)\.\s*\n?',
        '',
        prolog_source,
        count=1,
        flags=re.MULTILINE,
    )


def _parse_binding_value(text: str):
    """Parse a Prolog term text into a Python value.

    Handles integers, floats, atoms, lists, and compound terms.
    """
    text = text.strip()
    if not text:
        return text

    # Integer
    try:
        return int(text)
    except ValueError:
        pass

    # Float
    try:
        return float(text)
    except ValueError:
        pass

    # List: [...]
    if text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return _parse_list_elements(inner)

    # Compound: functor(args)
    m = re.match(r"^([a-z_][a-zA-Z0-9_]*)\((.+)\)$", text, re.DOTALL)
    if m:
        functor = m.group(1)
        args_text = m.group(2)
        args = _parse_list_elements(args_text)
        return (functor, *args)

    # Quoted atom: 'something'
    if text.startswith("'") and text.endswith("'"):
        return text[1:-1].replace("\\'", "'").replace("\\\\", "\\")

    # Plain atom
    return text


def _parse_list_elements(text: str) -> list:
    """Parse comma-separated Prolog terms, respecting nesting."""
    elements = []
    depth = 0
    current = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in ("(", "["):
            depth += 1
            current.append(ch)
        elif ch in (")", "]"):
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            elements.append(_parse_binding_value("".join(current)))
            current = []
        elif ch == "'" :
            # Quoted atom — scan to closing quote
            current.append(ch)
            i += 1
            while i < len(text):
                c2 = text[i]
                current.append(c2)
                if c2 == "\\" and i + 1 < len(text):
                    i += 1
                    current.append(text[i])
                elif c2 == "'":
                    break
                i += 1
        else:
            current.append(ch)
        i += 1
    if current:
        val = "".join(current).strip()
        if val:
            elements.append(_parse_binding_value(val))
    return elements


def _parse_binding_line(line: str) -> dict:
    """Parse a tab-separated line of Name=Value bindings into a dict.

    Each binding is ``Name=Value`` separated by tabs.
    """
    bindings = {}
    parts = line.split("\t")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        eq = part.find("=")
        if eq < 0:
            continue
        name = part[:eq]
        value_text = part[eq + 1:]
        bindings[name] = _parse_binding_value(value_text)
    return bindings


# ── Query wrapper templates ─────────────────────────────────────

# Single-solution wrapper: output bindings for the current solution,
# used with pl_query/pl_redo for lazy iteration.
_QUERY_ONE_SOL = (
    "read_term_from_atom('{query}', __Goal__, [variable_names(__VNs__)]), "
    "call(__Goal__), "
    "write('__SOL__'), "
    "forall(member(__Name__=__Val__, __VNs__), "
    "(write(__Name__), write('='), writeq(__Val__), write('\\t'))), "
    "nl."
)

_QUERY_BOOL_WRAPPER = (
    "read_term_from_atom('{query}', __Goal__, []), "
    "( call(__Goal__) -> write('__TRUE__') ; write('__FALSE__') ), nl."
)


class TreallaError(Exception):
    """Exception raised for Prolog errors from the Trealla engine."""
    pass


def _check_error(output: str) -> None:
    """Raise TreallaError if output contains a Prolog error."""
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("error(") or line.startswith("throw("):
            raise TreallaError(f"Prolog error: {line}")
        # Trealla prefixes errors with spaces
        stripped = line.lstrip()
        if stripped.startswith("error(") or stripped.startswith("throw("):
            raise TreallaError(f"Prolog error: {stripped}")


class Trealla:
    """Embedded Trealla Prolog session.

    A lightweight object (instant creation, ~5MB memory). Trealla is a
    fast, ISO-conformant Prolog interpreter written in C.

    The primary query interface is iteration::

        with Trealla() as t:
            t.load_string("parent(tom, bob). parent(bob, ann).")
            for sol in t.query("parent(X, Y)."):
                print(sol["X"], "->", sol["Y"])

    Examples
    --------
    >>> with Trealla() as t:
    ...     t.load_string("parent(tom, bob).")
    ...     t.query_one("parent(tom, X).")
    {'X': 'bob'}
    """

    def __init__(self):
        self._machine = TreallaMachine()

    def _check_open(self):
        if self._machine is None:
            raise RuntimeError("This Trealla session has been closed")

    def close(self):
        """Release the Trealla machine. Idempotent."""
        if self._machine is not None:
            self._machine.destroy()
            self._machine = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def __del__(self):
        self.close()

    # ── Loading programs ──────────────────────────────────────────

    def consult_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source (replaces earlier clauses for same predicate).

        The *module* parameter is accepted for API compatibility with
        :class:`clausal.scryer.Scryer` but is ignored — Trealla's C API
        does not support module-scoped loading.
        """
        self._check_open()
        if not self._machine.consult_string(source):
            raise RuntimeError("Failed to consult Prolog source")

    def load_string(self, source: str, module: str = "user") -> None:
        """Load Prolog source. Alias for consult_string."""
        self.consult_string(source, module)

    def consult_file(self, path: str, module: str = "user") -> None:
        """Load a file into the machine, by its surface (its extension):

        * seam (``.seam``): translated to Prolog via
          clausal_source_to_prolog with the Trealla dialect, its
          ``:- module(...)`` directive stripped;
        * Clausal Prolog (``.clausal``): already Prolog, consulted as
          written except that ``:- end_module(...)`` is commented out;
        * anything else (``.pl``): Trealla consults the file itself.

        The *module* parameter is accepted for API compatibility with
        :class:`clausal.scryer.Scryer` but is ignored.
        """
        self._check_open()
        from pathlib import Path
        from clausal.end_module import (
            SURFACE_CLAUSAL_PROLOG, SURFACE_SEAM, strip_end_module,
            surface_of)
        p = Path(path)
        surface = surface_of(p)
        if surface == SURFACE_SEAM:
            source = p.read_text(encoding="utf-8")
            from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
            from clausal.tools.prolog_dialect import Dialect
            prolog = clausal_source_to_prolog(source, dialect=Dialect.trealla())
            prolog = _strip_module_directive(prolog)
            self.consult_string(prolog)
        elif surface == SURFACE_CLAUSAL_PROLOG:
            self.consult_string(strip_end_module(p.read_text(encoding="utf-8")))
        else:
            if not self._machine.consult_file(str(p)):
                raise RuntimeError(f"Failed to consult file: {path}")

    def consult_clausal(self, source: str, module: str = "user") -> None:
        """Translate seam (``.seam``) source text to Prolog and consult it.

        The *module* parameter is accepted for API compatibility with
        :class:`clausal.scryer.Scryer` but is ignored.
        """
        self._check_open()
        from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
        from clausal.tools.prolog_dialect import Dialect
        prolog = clausal_source_to_prolog(source, dialect=Dialect.trealla())
        prolog = _strip_module_directive(prolog)
        self.consult_string(prolog)

    # ── Querying ──────────────────────────────────────────────────

    def _escape_query(self, goal: str) -> str:
        """Escape a query string for embedding in an atom."""
        goal = goal.strip().rstrip(".")
        return goal.replace("\\", "\\\\").replace("'", "\\'")

    def query(self, goal: str):
        """Run a Prolog query. Returns an iterator over solution dicts.

        Each solution is a dict mapping variable names (str) to Python
        values (int, float, str, list, cell).

        Iteration is lazy — each call to next() resumes Prolog
        backtracking for one more solution.

        Parameters
        ----------
        goal : str
            Prolog query text, including the trailing period.
            E.g. "parent(tom, X)."
        """
        self._check_open()
        escaped = self._escape_query(goal)
        wrapper = _QUERY_ONE_SOL.format(query=escaped)

        for ok, output in self._machine.query_iter(wrapper):
            _check_error(output)
            if not ok:
                return
            for line in output.splitlines():
                line = line.strip()
                if line.startswith("__SOL__"):
                    rest = line[len("__SOL__"):]
                    if rest.strip():
                        yield _parse_binding_line(rest)
                    else:
                        yield {}  # ground goal — no variable bindings

    def query_all(self, goal: str) -> list[dict]:
        """Run a query and collect all solutions into a list of dicts."""
        return list(self.query(goal))

    def query_one(self, goal: str) -> dict | None:
        """Return the first solution, or None if the query fails."""
        for sol in self.query(goal):
            return sol
        return None

    def query_bool(self, goal: str) -> bool:
        """Return True if the query succeeds at least once."""
        self._check_open()
        escaped = self._escape_query(goal)
        wrapper = _QUERY_BOOL_WRAPPER.format(query=escaped)
        _status, output = self._machine.eval_capture(wrapper)
        _check_error(output)
        return "__TRUE__" in output
