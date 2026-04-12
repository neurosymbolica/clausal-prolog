"""Variable-inspection helpers used throughout the compiler.

Pure traversal utilities over term trees: naming a logic variable,
collecting reachable Vars / Var IDs, and collecting the IDs of Vars
bound by Evaluate/Unify goals.  No compiler-internal dependencies
beyond ``clausal.terms`` / ``clausal.logic.variables`` /
``clausal.logic.predicate`` / ``clausal.pythonic_ast.nodes``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from clausal.logic.variables import Var, is_var, deref
from clausal.terms import (
    Compound,
    DictTerm,
    SetTerm,
    KWTerm,
    And,
    Unify,
    Evaluate,
    Call,  # noqa: F401 — referenced in Evaluate/Unify patterns via type system
)
from clausal.pythonic_ast.nodes import Lambda, StarUnpack, SetLiteral as _SL
from clausal.logic.predicate import is_term_instance, term_field_names


def _var_python_name(var: Var) -> str:
    """Return a stable Python identifier for a logic variable from its _id."""
    return f"_v{var._id}"


def _collect_vars(term: Any, seen: set[int] | None = None) -> list[Var]:
    """Recursively collect all Var objects reachable from term, in order.

    Used to pre-scan body goals left-to-right so that body-only Vars are
    registered in ``var_context`` before right-to-left body compilation starts.
    Without this pre-pass, body-only Vars are walrus-assigned in the innermost
    (last) goal's argument list but referenced in earlier (outer) goal arguments,
    causing UnboundLocalError at runtime.
    """
    if seen is None:
        seen = set()

    term = deref(term)

    if is_var(term):
        if term._id not in seen:
            seen.add(term._id)
            return [term]
        return []

    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return []

    if isinstance(term, Lambda):
        # Lambda body vars are in a separate scope — don't collect them.
        return []

    if isinstance(term, StarUnpack):
        return _collect_vars(term.value, seen)

    if isinstance(term, list):
        result: list[Var] = []
        for e in term:
            result.extend(_collect_vars(e, seen))
        return result

    if isinstance(term, dict):
        result = []
        for k, v in term.items():
            result.extend(_collect_vars(k, seen))
            result.extend(_collect_vars(v, seen))
        return result

    # DictTerm: recurse into values (keys are ground)
    if isinstance(term, DictTerm):
        result = []
        for v in term.values():
            result.extend(_collect_vars(v, seen))
        return result

    # SetTerm: elements must be ground, no vars to collect
    if isinstance(term, SetTerm):
        return []

    # SetLiteral (AST node): elements may contain vars
    if isinstance(term, _SL):
        result = []
        for e in term.elements:
            result.extend(_collect_vars(e, seen))
        return result

    # KWTerm: recurse into field values
    if isinstance(term, KWTerm):
        result = []
        for v in term.values():
            result.extend(_collect_vars(v, seen))
        return result

    if isinstance(term, Compound):
        result = _collect_vars(term.functor, seen)
        for a in term.args:
            result.extend(_collect_vars(a, seen))
        return result

    if is_term_instance(term):
        result = []
        for name in term_field_names(term):
            result.extend(_collect_vars(getattr(term, name), seen))
        return result

    # term is an operator/goal node — recurse into its fields
    try:
        fields = dataclasses.fields(term)
        result = []
        for f in fields:
            val = getattr(term, f.name)
            if val is not None:
                result.extend(_collect_vars(val, seen))
        return result
    except TypeError:
        return []


def _collect_var_ids(term: Any, ids: set[int]) -> None:
    """Recursively collect all Var IDs from a term."""

    term = deref(term)
    if is_var(term):
        ids.add(term._id)
    elif isinstance(term, (list, tuple)):
        for item in term:
            _collect_var_ids(item, ids)
    elif isinstance(term, DictTerm):
        for v in term._data.values():
            _collect_var_ids(v, ids)
    elif is_term_instance(term):
        for fname in term_field_names(term):
            _collect_var_ids(getattr(term, fname), ids)
    elif isinstance(term, Compound):
        for a in term.args:
            _collect_var_ids(a, ids)
    # StarUnpack and other single-child wrappers
    elif hasattr(term, 'value'):
        _collect_var_ids(term.value, ids)


def _collect_bound_vars(goal: Any, bound_ids: set[int]) -> None:
    """Collect Var IDs bound by Evaluate/Unify in *goal* (recursive for And)."""
    goal = deref(goal)
    match goal:
        case Evaluate(left=lhs):
            if is_var(lhs):
                bound_ids.add(lhs._id)
        case Unify(left=lhs, right=rhs):
            if is_var(lhs):
                bound_ids.add(lhs._id)
            if is_var(rhs):
                bound_ids.add(rhs._id)
        case And(left=l, right=r):
            _collect_bound_vars(l, bound_ids)
            _collect_bound_vars(r, bound_ids)
