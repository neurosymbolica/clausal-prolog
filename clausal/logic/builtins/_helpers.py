"""Shared helper functions for builtin predicates.

The heavy-lifting functions (_functor_name, _arity, _nth_arg, _args_list,
_is_compound, _is_ground) are implemented in C in _variables.c for performance.
Python reference implementations are kept here as fallbacks.
"""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
from clausal.terms import Compound, KWTerm, SegList, SegString, VarSeg, ConcreteSeg


# ── Python reference implementations ─────────────────────────────────────────


def _functor_name_py(term: Any) -> str | None:
    """Return the functor name of a ground term, or None.

    Lists and strings follow ISO cons-cell semantics:
      - non-empty list / str → ``"."`` (the cons-cell functor)
      - empty list / empty str → ``"[]"`` (the nil atom)

    User decision 2026-06-13: ISO-named inspection predicates
    (``functor/3``, ``arg/3``, ``unpack/2`` / ``=..``) follow ISO
    Prolog semantics; strings-as-lists Liskov symmetry applies so str
    inputs decompose the same shape as list inputs.
    """
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, str):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float, bytes)) or term is None:
        return repr(term)
    if isinstance(term, PredicateMeta) and not term._fields:
        return term
    return None


def _arity_py(term: Any) -> int | None:
    """Return the arity of a ground term, or None.

    Lists and strings follow ISO cons-cell semantics: non-empty has
    arity 2 (head + tail), empty has arity 0 (the nil atom).
    """
    if isinstance(term, Compound):
        return len(term.args)
    if isinstance(term, KWTerm):
        return len(term)
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if isinstance(term, str):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float, bytes)) or term is None:
        return 0
    if isinstance(term, PredicateMeta) and not term._fields:
        return 0
    return None


def _nth_arg_py(term: Any, n: int) -> Any:
    """Return the n-th argument (1-based) of a compound term, or raise IndexError.

    For lists and strings, ISO cons-cell semantics apply:
      - n=1 → head (first element / 1-char str)
      - n=2 → tail (rest of list / substring)
      - n>=3 → IndexError (arity is 2)

    Str preserves str type for both head (1-char str via ``term[0]``)
    and tail (substring via ``term[1:]``) — Liskov symmetry with the
    list branch.
    """
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
    if isinstance(term, list) and len(term) > 0:
        if n == 1:
            return term[0]
        if n == 2:
            return term[1:]
        raise IndexError(f"arg index {n} out of range for {term!r}")
    if isinstance(term, str) and len(term) > 0:
        if n == 1:
            return term[0]
        if n == 2:
            return term[1:]
        raise IndexError(f"arg index {n} out of range for {term!r}")
    raise IndexError(f"arg index {n} out of range for {term!r}")


def _args_list_py(term: Any) -> list:
    """Return the argument list of a compound term.

    For lists and strings, ISO cons-cell semantics: non-empty returns
    ``[head, tail]``; empty returns ``[]`` (the nil atom has no args).
    """
    if isinstance(term, Compound):
        return list(term.args)
    if isinstance(term, KWTerm):
        return list(term.values())
    if is_term_instance(term):
        return [getattr(term, name) for name in term_field_names(term)]
    if isinstance(term, list):
        if len(term) == 0:
            return []
        return [term[0], term[1:]]
    if isinstance(term, str):
        if len(term) == 0:
            return []
        return [term[0], term[1:]]
    return []


def _is_compound_py(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or is_term_instance(term)
    )


def _is_ground_py(term: Any) -> bool:
    """True if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    if isinstance(term, type) and isinstance(term, PredicateMeta) and not term._fields:
        return True
    if isinstance(term, list):
        return all(_is_ground_py(e) for e in term)
    if isinstance(term, Compound):
        return isinstance(term.functor, str) and all(_is_ground_py(a) for a in term.args)
    if isinstance(term, KWTerm):
        return all(_is_ground_py(v) for v in term.values())
    # F083 (audit 2026-05-25): recurse into Seg* containers so that
    # ``ground/1`` returns False for any SegList/SegString that still
    # holds an unbound ``VarSeg``. Both the Python fallback and the C
    # ``c_is_ground`` historically fell through to "True" for Seg* —
    # see [[F083]] in the 2026-05-25 string audit findings ledger.
    if isinstance(term, SegList):
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                if not all(_is_ground_py(e) for e in seg.elements):
                    return False
            elif isinstance(seg, VarSeg):
                if not _is_ground_py(seg.var):
                    return False
            else:
                # Unknown segment type — be conservative and walk it.
                if not _is_ground_py(seg):
                    return False
        return True
    if isinstance(term, SegString):
        for seg in term.segments:
            if isinstance(seg, str):
                continue
            if isinstance(seg, VarSeg):
                if not _is_ground_py(seg.var):
                    return False
            else:
                if not _is_ground_py(seg):
                    return False
        return True
    if is_term_instance(term):
        return all(_is_ground_py(getattr(term, name)) for name in term_field_names(term))
    return True


# ── C-accelerated versions (with Python fallback) ────────────────────────────

_functor_name = _functor_name_py
_arity = _arity_py
_nth_arg = _nth_arg_py
_args_list = _args_list_py
_is_compound = _is_compound_py
_is_ground = _is_ground_py

try:
    from clausal.logic.variables._variables import (
        _functor_name,
        _arity,
        _nth_arg,
        _args_list,
        _is_compound,
        _is_ground as _c_is_ground,
        _register_term_types,
    )
    # Register Compound and KWTerm types with the C extension
    _register_term_types(Compound, KWTerm)

    # F083 (audit 2026-05-25): the C ``_is_ground`` does not know about
    # SegList / SegString and falls through to "True" for any unknown
    # container. Short-circuit the Seg* shapes in Python so a SegList
    # / SegString that still holds an unbound ``VarSeg`` reports
    # *not* ground. Other shapes still go through the fast C path.
    def _is_ground(term: Any) -> bool:
        t = deref(term)
        if isinstance(t, (SegList, SegString)):
            return _is_ground_py(t)
        return _c_is_ground(t)
except ImportError:
    pass
