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
    """Deref a value, recursively deref-ing list elements and dict values.

    Handles both plain dicts and DictTerm (Clausal's unification-aware dict).
    """
    from clausal.terms import DictTerm
    val = deref(val)
    if isinstance(val, list):
        return [_deep_deref(x) for x in val]
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
