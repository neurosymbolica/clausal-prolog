"""I/O builtins (V2-15 + Phase 2): Write/1, Writeln/1, PrintTerm/1, Nl/0,
Tab/1, WriteToString/2, TermToString/2, Listing/1, PortrayClause/1."""

from __future__ import annotations

import sys as _sys

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.terms import term_str as _term_str, term_pformat as _term_pformat
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.logic.exceptions import LogicException, type_error

from clausal.logic.builtins._registry import _builtin, BuiltinPredicate


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


# ── Clause formatting helpers ────────────────────────────────────────────────

def _format_clause_term(val):
    """Format a term value for clause head display."""
    val = deref(val)
    if isinstance(val, Var):
        return str(val)  # _N format for anonymous vars
    if isinstance(val, str):
        return repr(val)
    if isinstance(val, list):
        return "[" + ", ".join(_format_clause_term(e) for e in val) + "]"
    if is_term_instance(val):
        return _format_clause_head(val)
    return str(val)


def _format_clause_head(head):
    """Format a clause head as 'functor(arg1, arg2, ...)'."""
    if is_term_instance(head):
        name = type(head).__name__
        fields = term_field_names(head)
        if not fields:
            return name
        args = [_format_clause_term(getattr(head, f)) for f in fields]
        return f"{name}({', '.join(args)})"
    return _term_str(head)


def _format_clause(clause):
    """Format a Clause for Listing output."""
    head_str = _format_clause_head(clause.head)
    if clause.is_fact():
        return f"{head_str}."
    body_strs = [str(g) for g in clause.body]
    body = ", ".join(body_strs)
    if len(clause.body) > 1:
        return f"{head_str} <- ({body})."
    return f"{head_str} <- {body}."


# ── Listing/1 ────────────────────────────────────────────────────────────────

@_builtin("Listing", 1)
def _listing__1(pred, trail, k):
    """Listing(Pred) — print all clauses of a predicate to stdout.

    Accepts a PredicateMeta class or instance (resolves to class).
    """
    val = deref(pred)

    # Accept an instance → resolve to its class
    if is_term_instance(val):
        val = type(val)

    # Must be a PredicateMeta class
    if not isinstance(val, PredicateMeta):
        # Check if it's a BuiltinPredicate
        if isinstance(val, BuiltinPredicate):
            name = val._functor
            arity = val._arity
            print(f"% {name}/{arity} — builtin")
            yield None
            return
        raise LogicException(type_error("predicate", val, "listing/1"))

    name = val.__name__
    arity = len(val._fields)
    clauses = val._clauses

    if not clauses:
        print(f"% {name}/{arity} — no clauses")
    else:
        print(f"% {name}/{arity} — {len(clauses)} clause(s)")
        for clause in clauses:
            print(_format_clause(clause))
    yield None


# ── PortrayClause/1 ─────────────────────────────────────────────────────────

@_builtin("PortrayClause", 1)
def _portray_clause__1(term, trail, k):
    """PortrayClause(Term) — pretty-print a term with indentation."""
    from clausal.logic.solve import _deref_walk
    val = _deref_walk(term)
    print(_term_pformat(val))
    yield None
