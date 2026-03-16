"""I/O builtins (V2-15): Write/1, Writeln/1, PrintTerm/1, Nl/0, Tab/1,
WriteToString/2, TermToString/2."""

from __future__ import annotations

import sys as _sys

from clausal.logic.variables import deref, is_var, unify
from clausal.terms import term_str as _term_str

from clausal.logic.builtins._registry import _builtin


def _format_term_for_io(val):
    """Format a dereffed value for I/O output.

    Strings pass through as-is (supports f-strings naturally).
    Other values use str() which auto-derefs Vars via __str__.
    """
    if isinstance(val, str):
        return val
    return str(val)


@_builtin("Write", 1)
def _write__1(term, trail, k):
    """Write(Term) — print dereffed term to stdout (no newline).

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: Write(f"X is {X_}").
    """
    val = deref(term)
    _sys.stdout.write(_format_term_for_io(val))
    _sys.stdout.flush()
    yield None


@_builtin("Writeln", 1)
def _writeln__1(term, trail, k):
    """Writeln(Term) — print dereffed term to stdout with newline.

    Strings are printed without quotes.  Vars are auto-dereffed.
    Works naturally with f-strings: Writeln(f"X is {X_}").
    """
    val = deref(term)
    print(_format_term_for_io(val))
    yield None


@_builtin("PrintTerm", 1)
def _print_term__1(term, trail, k):
    """PrintTerm(Term) — print structured term representation with newline.

    Uses term_str() for Prolog-style output showing term structure
    (e.g., functors, lists, operators).  Vars show as Var(_N).
    """
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    print(_term_str(val))
    yield None


@_builtin("Nl", 0)
def _nl__0(trail, k):
    """Nl — print a newline."""
    print()
    yield None


@_builtin("Tab", 1)
def _tab__1(n, trail, k):
    """Tab(N) — print N spaces."""
    n_val = deref(n)
    if is_var(n_val) or not isinstance(n_val, int):
        return
    _sys.stdout.write(" " * n_val)
    _sys.stdout.flush()
    yield None


@_builtin("WriteToString", 2)
def _write_to_string__2(term, result, trail, k):
    """WriteToString(Term, Result) — unify Result with the string representation of Term.

    Vars are auto-dereffed.  Strings pass through as-is.
    """
    val = deref(term)
    s = _format_term_for_io(val)
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)


@_builtin("TermToString", 2)
def _term_to_string__2(term, result, trail, k):
    """TermToString(Term, Result) — unify Result with structured term_str representation."""
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    s = _term_str(val)
    mark = trail.mark()
    if unify(result, s, trail):
        yield None
    trail.undo(mark)
