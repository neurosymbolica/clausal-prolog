"""Pair helper builtins: Unzip/3, PairKeys/2, PairValues/2, GroupPairsByKey/2."""

from __future__ import annotations

from clausal.logic.variables import deref, unify
from clausal.logic.trampoline import DONE

from clausal.logic.builtins._registry import _trampoline_builtin


@_trampoline_builtin("Unzip", 3)
def _pairs_keys_values__3(this_generator, parent, pairs, keys, values, trail):
    """pairs_keys_values(Pairs, Keys, Values) — Pairs is a list of [K, V] lists."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
        vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(keys, ks, trail) and unify(values, vs, trail):
            yield (parent, None)
        trail.undo(mark)
    else:
        ks_val = deref(keys)
        vs_val = deref(values)
        if isinstance(ks_val, list) and isinstance(vs_val, list) and len(ks_val) == len(vs_val):
            result = [[k, v] for k, v in zip(ks_val, vs_val)]
            mark = trail.mark()
            if unify(pairs, result, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("PairKeys", 2)
def _pairs_keys__2(this_generator, parent, pairs, keys, trail):
    """pairs_keys(Pairs, Keys) — Keys are the first elements of each pair."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        ks = [deref(p)[0] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(keys, ks, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("PairValues", 2)
def _pairs_values__2(this_generator, parent, pairs, values, trail):
    """pairs_values(Pairs, Values) — Values are the second elements of each pair."""
    pairs_val = deref(pairs)
    if isinstance(pairs_val, list):
        vs = [deref(p)[1] for p in pairs_val if isinstance(deref(p), list)]
        mark = trail.mark()
        if unify(values, vs, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("GroupPairsByKey", 2)
def _group_pairs_by_key__2(this_generator, parent, pairs, groups, trail):
    """GroupPairsByKey(Pairs, Groups) — group [Key, Value] pairs by key.

    Groups is a list of [Key, Values] where Values collects all values for that key.
    Order preserved: first occurrence of key determines group order.
    """
    pairs_val = deref(pairs)
    if not isinstance(pairs_val, list):
        yield (parent, DONE)
        return
    grouped: dict = {}
    order: list = []
    for pair in pairs_val:
        p = deref(pair)
        if not isinstance(p, list) or len(p) < 2:
            yield (parent, DONE)
            return
        key = deref(p[0])
        value = deref(p[1])
        try:
            hash(key)
            k = key
        except TypeError:
            k = id(key)
        if k not in grouped:
            grouped[k] = (key, [])
            order.append(k)
        grouped[k][1].append(value)
    result = [[grouped[k][0], grouped[k][1]] for k in order]
    mark = trail.mark()
    if unify(groups, result, trail):
        yield (parent, None)
    trail.undo(mark)
    yield (parent, DONE)
