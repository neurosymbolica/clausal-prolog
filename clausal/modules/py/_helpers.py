"""Shared dispatch helpers for Clausal Python-library wrappers.

Extracted from ``torch.py`` so that all wrappers (torch, scipy, etc.) share
the same implementations — in particular ``_deep_deref`` which recursively
unwraps ``Var`` / ``DictTerm`` objects inside lists and dicts.
"""

from __future__ import annotations

from typing import Callable

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py import ModulePredicate


# ── Core helpers ────────────────────────────────────────────────────────────

def _pred(name: str, *arity_fns) -> ModulePredicate:
    p = ModulePredicate(name)
    for arity, fn in arity_fns:
        p._register(arity, fn)
    return p


def _deep_deref(val):
    """Deref a value, recursively deref-ing list, tuple, and dict elements.

    Handles both plain dicts and DictTerm (Clausal's unification-aware dict).
    Tuples are preserved as tuples (not converted to lists) — library code
    that distinguishes tuple-of-ints from list-of-ints relies on this, e.g.
    ``a.at[(1, 2)]`` vs ``a.at[[1, 2]]`` in JAX have different semantics.
    """
    from clausal.terms import DictTerm
    val = deref(val)
    if isinstance(val, list):
        return [_deep_deref(x) for x in val]
    if isinstance(val, tuple):
        return tuple(_deep_deref(x) for x in val)
    if isinstance(val, DictTerm):
        return {k: _deep_deref(v) for k, v in val.items()}
    if isinstance(val, dict):
        return {k: _deep_deref(v) for k, v in val.items()}
    return val


def _pure(fn: Callable) -> Callable:
    """Wrap a pure function: deep-deref all inputs, call fn(*inputs), unify RESULT."""
    def dispatch(this_generator, _proceed, _fail, _catcher, *args):
        trail = args[-1]
        result_var = args[-2]
        inputs = [_deep_deref(x) for x in args[:-2]]
        try:
            out = fn(*inputs)
        except Exception:
            yield (_fail, DONE)
            return
        if unify(result_var, out, trail):
            yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _property_2(getter):
    """Multi-mode property predicate: query (+X,-V) or check (+X,+V).

    ``getter(x)`` returns the property value. In query mode (V is a var),
    unify V with the value. In check mode (V is bound), succeed iff
    ``getter(x) == V``.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_var, value_var, trail):
        x = deref(x_var)
        v = deref(value_var)
        try:
            actual = getter(x)
        except Exception:
            yield (_fail, DONE)
            return
        if is_var(v):
            if unify(value_var, actual, trail):
                yield (_proceed, None)
        else:
            if actual == v:
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch


def _values_equal(a, b):
    """Equality check that tolerates array-like operands.

    Python `==` on numpy / JAX / torch arrays returns an element-wise
    bool array rather than a scalar, and `bool(array)` of a multi-
    element array raises. This helper:

    - returns True on object identity;
    - returns the result directly if `==` yields a plain bool;
    - otherwise reduces via `.all()` (numpy / JAX / torch share this).

    Any exception during comparison is treated as inequality — this
    covers unhashable or type-mismatched operands without surprises.
    """
    if a is b:
        return True
    try:
        r = (a == b)
    except Exception:
        return False
    if isinstance(r, bool):
        return r
    try:
        return bool(r.all())
    except (AttributeError, TypeError):
        try:
            return bool(r)
        except Exception:
            return False


def _bidir_2(forward, backward):
    """Bidirectional predicate: (+X,-Y) forward, (-X,+Y) backward, (+X,+Y) check.

    In check mode `unify` is tried first so structured Y terms with
    embedded Vars (e.g. ``tensor_list(X, [V1, V2])``) still work.
    ``unify`` can raise on array-typed operands (JAX / numpy /
    multi-element torch tensors — `==` yields element-wise bool), in
    which case `_values_equal` is used as a fallback.
    """
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, y_raw, trail):
        x = deref(x_raw)
        y = deref(y_raw)

        if not is_var(x) and is_var(y):
            try:
                out = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(y_raw, out, trail):
                yield (_proceed, None)

        elif is_var(x) and not is_var(y):
            try:
                out = backward(y)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(x_raw, out, trail):
                yield (_proceed, None)

        elif not is_var(x) and not is_var(y):
            try:
                out = forward(x)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = unify(y_raw, out, trail)
            except Exception:
                trail.undo(mark)
                unified = _values_equal(out, y)
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _bidir_3_mid(forward, backward):
    """Bidirectional with a middle arg: (+X,+M,-Y) forward, (-X,+M,+Y) backward."""
    def dispatch(this_generator, _proceed, _fail, _catcher, x_raw, mid_raw, y_raw, trail):
        x = deref(x_raw)
        m = _deep_deref(mid_raw)
        y = deref(y_raw)

        if not is_var(x) and is_var(y):
            try:
                out = forward(x, m)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(y_raw, out, trail):
                yield (_proceed, None)

        elif is_var(x) and not is_var(y):
            try:
                out = backward(y, m)
            except Exception:
                yield (_fail, DONE)
                return
            if unify(x_raw, out, trail):
                yield (_proceed, None)

        elif not is_var(x) and not is_var(y):
            try:
                out = forward(x, m)
            except Exception:
                yield (_fail, DONE)
                return
            mark = trail.mark()
            unified = False
            try:
                unified = unify(y_raw, out, trail)
            except Exception:
                trail.undo(mark)
                unified = _values_equal(out, y)
            if unified:
                yield (_proceed, None)

        yield (_fail, DONE)
    return dispatch


def _fact_table_2(get_facts):
    """Nondeterministic fact table: enumerate (name, value) pairs.

    Supports modes: (+name, -value), (-name, +value), (-name, -value), (+name, +value).
    get_facts() is called lazily to build the list on first use.
    """
    cache = {}

    def dispatch(this_generator, _proceed, _fail, _catcher, name_var, value_var, trail):
        if not cache:
            facts = get_facts()
            cache["facts"] = facts
            cache["by_name"] = {n: v for n, v in facts}
            cache["by_value"] = {id(v): n for n, v in facts}
        n = deref(name_var)
        v = deref(value_var)

        if not is_var(n) and is_var(v):
            cls = cache["by_name"].get(n)
            if cls is not None and unify(value_var, cls, trail):
                yield (_proceed, None)
        elif is_var(n) and not is_var(v):
            key = cache["by_value"].get(id(v))
            if key is not None and unify(name_var, key, trail):
                yield (_proceed, None)
        elif is_var(n) and is_var(v):
            for name, value in cache["facts"]:
                mark = trail.mark()
                if unify(name_var, name, trail) and unify(value_var, value, trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            cls = cache["by_name"].get(n)
            if cls is not None and cls is v:
                yield (_proceed, None)
        yield (_fail, DONE)
    return dispatch
