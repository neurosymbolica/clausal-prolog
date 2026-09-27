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
    DictTerm,
    SetTerm,
    KWTerm,
    And,
    Unify,
    Evaluate,
    Call,  # noqa: F401 — referenced in Evaluate/Unify patterns via type system
)
from clausal.pythonic_ast.nodes import Lambda, StarUnpack, SetLiteral as _SL, literal_value
from clausal.logic.predicate import is_term_instance, term_field_names


def _var_python_name(var: Var) -> str:
    """Return a stable Python identifier for a logic variable from its _id."""
    return f"_v{var._id}"


def _collect_vars(term: Any, seen: set[int] | None = None,
                  include_bound: bool = False) -> list[Var]:
    """Recursively collect all Var objects reachable from term, in order.

    Used to pre-scan body goals left-to-right so that body-only Vars are
    registered in ``var_context`` before right-to-left body compilation starts.
    Without this pre-pass, body-only Vars are walrus-assigned in the innermost
    (last) goal's argument list but referenced in earlier (outer) goal arguments,
    causing UnboundLocalError at runtime.

    With ``include_bound=True``, a Var that is already BOUND is collected as
    well (and its value walked for further vars).  The query compiler uses this
    so a live bound Var can be referenced by name from the compiled code when
    its value has no literal lowering (e.g. a ``datetime.date``) — see the
    bound-Var fallback at the tail of ``term_to_ast_expr``.
    """
    if seen is None:
        seen = set()

    raw = term
    term = deref(term)

    if is_var(term):
        if term._id not in seen:
            seen.add(term._id)
            return [term]
        return []

    pre: list[Var] = []
    # NB ``isinstance``, not ``is_var`` — is_var() derefs, so it is False for
    # exactly the bound Vars this branch exists to collect.
    if include_bound and isinstance(raw, Var) and raw._id not in seen:
        # *raw* was bound (deref moved past it): register the Var object
        # itself, then continue into its value below.
        seen.add(raw._id)
        pre = [raw]

    term = literal_value(term)
    if term is None or isinstance(term, (bool, int, float, str, bytes, complex)):
        return pre

    if isinstance(term, Lambda):
        # Lambda body vars are in a separate scope — don't collect them.
        return pre

    if isinstance(term, StarUnpack):
        return pre + _collect_vars(term.value, seen, include_bound)

    if isinstance(term, list):
        result: list[Var] = pre
        for e in term:
            result.extend(_collect_vars(e, seen, include_bound))
        return result

    if type(term) is tuple:
        # A CELL -- ``("point", X, Y)``.  Post-P3-2 (THE FLIP) this is how
        # every compound data term is represented, so a query goal's cell
        # argument carries the caller's Vars and the query compiler has to
        # register them: without this the template's tuple lowers with a
        # FRESH var per slot (``term_to_ast_expr``'s tuple branch, which does
        # recurse), the caller's Var is never in ``var_context``, and the
        # answer comes back unbound.  ``type(...) is tuple``, matching
        # ``cells.is_cell``'s own domain and the copy_term branch in
        # ``builtins/inspection.py``.
        result = pre
        for e in term:
            result.extend(_collect_vars(e, seen, include_bound))
        return result

    if isinstance(term, dict):
        result = pre
        for k, v in term.items():
            result.extend(_collect_vars(k, seen, include_bound))
            result.extend(_collect_vars(v, seen, include_bound))
        return result

    # DictTerm: recurse into values (keys are ground)
    if isinstance(term, DictTerm):
        result = pre
        for v in term.values():
            result.extend(_collect_vars(v, seen, include_bound))
        return result

    # SetTerm: elements must be ground, no vars to collect
    if isinstance(term, SetTerm):
        return pre

    # SetLiteral (AST node): elements may contain vars
    if isinstance(term, _SL):
        result = pre
        for e in term.elements:
            result.extend(_collect_vars(e, seen, include_bound))
        return result

    # KWTerm: recurse into field values
    if isinstance(term, KWTerm):
        result = pre
        for v in term.values():
            result.extend(_collect_vars(v, seen, include_bound))
        return result


    if is_term_instance(term):
        result = pre
        for name in term_field_names(term):
            result.extend(_collect_vars(getattr(term, name), seen, include_bound))
        return result

    # term is an operator/goal node — recurse into its fields
    try:
        fields = dataclasses.fields(term)
        result = pre
        for f in fields:
            val = getattr(term, f.name)
            if val is not None:
                result.extend(_collect_vars(val, seen, include_bound))
        return result
    except TypeError:
        return pre


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
