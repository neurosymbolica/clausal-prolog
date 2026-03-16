"""Shared helper functions for builtin predicates."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm


def _functor_name(term: Any) -> str | None:
    """Return the functor name of a ground term, or None."""
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return repr(term) if not isinstance(term, str) else term
    return None


def _arity(term: Any) -> int | None:
    """Return the arity of a ground term, or None."""
    if isinstance(term, Compound):
        return len(term.args)
    if isinstance(term, KWTerm):
        return len(term)
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return 0
    return None


def _nth_arg(term: Any, n: int) -> Any:
    """Return the n-th argument (1-based) of a compound term, or raise IndexError."""
    if isinstance(term, Compound):
        if n < 1 or n > len(term.args):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return term.args[n - 1]
    if isinstance(term, KWTerm):
        vals = list(term.values())
        if n < 1 or n > len(vals):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return vals[n - 1]
    if is_term_instance(term):
        fields = term_field_names(term)
        if n < 1 or n > len(fields):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return getattr(term, fields[n - 1])
    if isinstance(term, list) and len(term) >= n >= 1:
        return term[n - 1]
    raise IndexError(f"arg index {n} out of range for {term!r}")


def _args_list(term: Any) -> list:
    """Return the argument list of a compound term."""
    if isinstance(term, Compound):
        return list(term.args)
    if isinstance(term, KWTerm):
        return list(term.values())
    if is_term_instance(term):
        return [getattr(term, name) for name in term_field_names(term)]
    return []


def _is_compound(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or is_term_instance(term)
    )


def _is_ground(term: Any) -> bool:
    """True if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    if isinstance(term, list):
        return all(_is_ground(e) for e in term)
    if isinstance(term, Compound):
        return isinstance(term.functor, str) and all(_is_ground(a) for a in term.args)
    if isinstance(term, KWTerm):
        return all(_is_ground(v) for v in term.values())
    if is_term_instance(term):
        return all(_is_ground(getattr(term, name)) for name in term_field_names(term))
    return True
