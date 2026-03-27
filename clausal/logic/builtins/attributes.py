"""Attributed variable builtins: put_attr/3, get_attr/3, del_attr/2,
get_attrs/2, put_attrs/2, attvar/1, term_attvars/2."""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify, put_attr, get_attr, del_attr
from clausal.logic.predicate import is_term_instance, term_field_names
from clausal.terms import Compound, DictTerm

from clausal.logic.builtins._registry import _builtin


# ── Per-key operations ─────────────────────────────────────────────────────


@_builtin("put_attr", 3)
def _put_attr__3(var, key, value, trail, k):
    """put_attr(Var, Key, Value) — attach attribute under Key to Var.

    Var must be an unbound variable. Key must be a ground string. Trailed.
    """
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return
    if is_var(key_d) or not isinstance(key_d, str):
        return
    put_attr(var_d, key_d, deref(value), trail)
    yield None


@_builtin("get_attr", 3)
def _get_attr__3(var, key, value, trail, k):
    """get_attr(Var, Key, Value) — retrieve attribute under Key.

    Fails if Var has no attribute for Key, or if Var is not an unbound variable.
    """
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return
    if is_var(key_d) or not isinstance(key_d, str):
        return
    attr = get_attr(var_d, key_d)
    if attr is None:
        return
    if unify(value, attr, trail):
        yield None


@_builtin("del_attr", 2)
def _del_attr__2(var, key, trail, k):
    """del_attr(Var, Key) — remove attribute under Key from Var.

    Succeeds even if no attribute existed (no-op). Trailed.
    """
    var_d = deref(var)
    key_d = deref(key)
    if not is_var(var_d):
        return
    if is_var(key_d) or not isinstance(key_d, str):
        return
    del_attr(var_d, key_d, trail)
    yield None


# ── Bulk operations (DictTerm) ─────────────────────────────────────────────


@_builtin("get_attrs", 2)
def _get_attrs__2(var, attrs, trail, k):
    """get_attrs(Var, Attrs) — unify Attrs with a DictTerm of all attributes on Var."""
    var_d = deref(var)
    if not is_var(var_d):
        return
    raw = var_d.attrs if hasattr(var_d, 'attrs') and var_d.attrs else {}
    result = DictTerm(dict(raw))
    if unify(attrs, result, trail):
        yield None


@_builtin("put_attrs", 2)
def _put_attrs__2(var, attrs, trail, k):
    """put_attrs(Var, Attrs) — set multiple attributes from a DictTerm."""
    var_d = deref(var)
    attrs_d = deref(attrs)
    if not is_var(var_d):
        return
    if isinstance(attrs_d, DictTerm):
        data = attrs_d.data
    elif isinstance(attrs_d, dict):
        data = attrs_d
    else:
        return
    for key, value in data.items():
        if not isinstance(key, str):
            return
        put_attr(var_d, key, deref(value), trail)
    yield None


# ── Inspection ─────────────────────────────────────────────────────────────


@_builtin("attvar", 1)
def _is_att_var__1(var, trail, k):
    """attvar(Var) — succeeds if Var is an unbound variable with attributes."""
    var_d = deref(var)
    if is_var(var_d):
        raw = var_d.attrs if hasattr(var_d, 'attrs') else None
        if raw:
            yield None


@_builtin("term_attvars", 2)
def _term_attributed_variables__2(term, vars_list, trail, k):
    """term_attvars(Term, Vars) — collect all attributed variables in Term."""
    seen = set()
    result = []
    _collect_attvars(deref(term), seen, result)
    if unify(vars_list, result, trail):
        yield None


def _collect_attvars(term, seen, result):
    """Recursively collect attributed variables from a term."""
    if is_var(term):
        vid = id(term)
        if vid not in seen:
            seen.add(vid)
            raw = term.attrs if hasattr(term, 'attrs') else None
            if raw:
                result.append(term)
        return
    if isinstance(term, list):
        for item in term:
            _collect_attvars(deref(item), seen, result)
    elif isinstance(term, Compound):
        for arg in term.args:
            _collect_attvars(deref(arg), seen, result)
    elif is_term_instance(term):
        for f in term_field_names(term):
            _collect_attvars(deref(getattr(term, f)), seen, result)
    elif isinstance(term, DictTerm):
        for v in term.data.values():
            _collect_attvars(deref(v), seen, result)
