"""Dict and Set builtins (Phase 3 + Phase 4).

Dict builtins:
  is_dict/1         — type check
  dict_size/2       — number of keys
  dict_keys/2       — extract key list (sorted for determinism)
  dict_values/2     — extract value list (in key order)
  dict_pairs/2      — DictTerm ↔ list of (Key: Value) pairs
  dict_get/3        — dict_get(Key, Dict, Value) — semidet lookup
  dict_put/4        — dict_put(Key, Value, Old, New) — functional update
  dict_put_pairs/3   — dict_put(Pairs, Old, New) — bulk update from pair list
  dict_remove/3     — dict_remove(Key, Old, New) — remove key
  dict_merge/3      — dict_merge(D1, D2, Merged) — D2 overrides D1
  gen_dict/3        — gen_dict(Key, Dict, Value) — nondeterministic enumeration

Set builtins:
  is_set/1          — type check
  set_size/2        — cardinality
  set_list/2        — SetTerm ↔ sorted list
  set_union/3       — set union
  set_intersection/3 — set intersection
  set_subtract/3    — S1 - S2
  set_sym_diff/3     — symmetric difference
  set_subset/2      — subset test
  set_disjoint/2    — disjoint test
  set_add/3         — add element → new SetTerm
  set_remove/3      — remove element → new SetTerm
  gen_set/2         — enumerate elements on backtracking

The ``<<`` (partial match / DictSelect) operator is handled directly in
compile_goal via the ``_dict_select`` function defined here.
"""

from __future__ import annotations

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.trampoline import DONE
from clausal.terms import DictTerm, SetTerm

from clausal.logic.builtins._registry import _builtin, _trampoline_builtin


# ── helpers ──────────────────────────────────────────────────────────────────


def _pair_key(pair):
    """Extract key from a (Key: Value) pair represented as a 2-tuple or Compound."""
    # Pairs are represented as Python 2-tuples (key, value) in list context.
    # We use Python tuples: (key, value).
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return pair[0]
    raise TypeError(f"Expected 2-tuple pair, got {pair!r}")


def _pair_value(pair):
    if isinstance(pair, (list, tuple)) and len(pair) == 2:
        return pair[1]
    raise TypeError(f"Expected 2-tuple pair, got {pair!r}")


# ── Dict builtins ─────────────────────────────────────────────────────────────


@_builtin("is_dict", 1)
def _is_dict__1(term, trail, k):
    """is_dict(Term) — succeeds if Term is a DictTerm."""
    if isinstance(deref(term), DictTerm):
        yield None


@_trampoline_builtin("dict_size", 2)
def _dict_size__2(this_generator, parent, d, n, trail):
    """dict_size(Dict, N) — N is the number of keys in Dict."""
    d_val = deref(d)
    if isinstance(d_val, DictTerm):
        mark = trail.mark()
        if unify(n, len(d_val), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_keys", 2)
def _dict_keys__2(this_generator, parent, d, keys, trail):
    """dict_keys(Dict, Keys) — Keys is the sorted list of keys in Dict."""
    d_val = deref(d)
    if isinstance(d_val, DictTerm):
        sorted_keys = sorted(d_val.keys(), key=repr)
        mark = trail.mark()
        if unify(keys, sorted_keys, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_values", 2)
def _dict_values__2(this_generator, parent, d, values, trail):
    """dict_values(Dict, Values) — Values is the list of values in key-sorted order."""
    d_val = deref(d)
    if isinstance(d_val, DictTerm):
        sorted_keys = sorted(d_val.keys(), key=repr)
        vals = [d_val[k] for k in sorted_keys]
        mark = trail.mark()
        if unify(values, vals, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_pairs", 2)
def _dict_pairs__2(this_generator, parent, d, pairs, trail):
    """dict_pairs(Dict, Pairs) — Dict ↔ list of [Key, Value] 2-element lists.

    Modes:
      dict_pairs(+DictTerm, -Pairs) — decompose dict into pair list
      dict_pairs(-DictTerm, +Pairs) — construct dict from pair list
    """
    d_val = deref(d)
    pairs_val = deref(pairs)

    if isinstance(d_val, DictTerm):
        # Dict → Pairs
        sorted_keys = sorted(d_val.keys(), key=repr)
        pair_list = [[k, d_val[k]] for k in sorted_keys]
        mark = trail.mark()
        if unify(pairs, pair_list, trail):
            yield (parent, None)
        trail.undo(mark)

    elif isinstance(pairs_val, list):
        # Pairs → Dict
        data = {}
        ok = True
        for pair in pairs_val:
            pair = deref(pair)
            if isinstance(pair, list) and len(pair) == 2:
                k = deref(pair[0])
                v = deref(pair[1])
                if is_var(k):
                    ok = False
                    break
                data[k] = v
            else:
                ok = False
                break
        if ok:
            mark = trail.mark()
            if unify(d, DictTerm(data), trail):
                yield (parent, None)
            trail.undo(mark)

    yield (parent, DONE)


@_trampoline_builtin("dict_get", 3)
def _dict_get__3(this_generator, parent, key, d, value, trail):
    """dict_get(Key, Dict, Value) — semidet: Value is Dict[Key]."""
    key_val = deref(key)
    d_val = deref(d)
    if not is_var(key_val) and isinstance(d_val, DictTerm) and key_val in d_val:
        mark = trail.mark()
        if unify(value, d_val[key_val], trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


def _dict_put_dr__4(this_generator, parent, key, value, old_dict, new_dict, trail):
    """Destructive-reuse variant of dict_put/4.

    When the old DictTerm has a low reference count (not shared), mutate its
    internal ``_data`` dict in-place.  Falls back to the standard (copying)
    implementation otherwise.
    """
    import sys  # noqa: PLC0415

    key_val = deref(key)
    old_val = deref(old_dict)
    if (not is_var(key_val) and isinstance(old_val, DictTerm)
            and sys.getrefcount(old_val) <= 3):
        old_val._data[key_val] = deref(value)
        mark = trail.mark()
        if unify(new_dict, old_val, trail):
            yield (parent, None)
        trail.undo(mark)
        yield (parent, DONE)
        return
    # Fallback to standard dict_put
    yield from _dict_put__4(this_generator, parent, key, value, old_dict, new_dict, trail)


@_trampoline_builtin("dict_put", 4)
def _dict_put__4(this_generator, parent, key, value, old_dict, new_dict, trail):
    """dict_put(Key, Value, OldDict, NewDict) — NewDict is OldDict with Key→Value."""
    key_val = deref(key)
    old_val = deref(old_dict)
    if not is_var(key_val) and isinstance(old_val, DictTerm):
        new_data = dict(old_val.data)
        new_data[key_val] = deref(value)
        mark = trail.mark()
        if unify(new_dict, DictTerm(new_data), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_put_pairs", 3)
def _dict_put_pairs__3(this_generator, parent, pairs, old_dict, new_dict, trail):
    """dict_put(Pairs, OldDict, NewDict) — bulk update from [[Key, Value], ...] list."""
    pairs_val = deref(pairs)
    old_val = deref(old_dict)
    if isinstance(pairs_val, list) and isinstance(old_val, DictTerm):
        new_data = dict(old_val.data)
        ok = True
        for pair in pairs_val:
            pair = deref(pair)
            if isinstance(pair, list) and len(pair) == 2:
                k = deref(pair[0])
                v = deref(pair[1])
                if is_var(k):
                    ok = False
                    break
                new_data[k] = v
            else:
                ok = False
                break
        if ok:
            mark = trail.mark()
            if unify(new_dict, DictTerm(new_data), trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_remove", 3)
def _dict_remove__3(this_generator, parent, key, old_dict, new_dict, trail):
    """dict_remove(Key, OldDict, NewDict) — NewDict is OldDict without Key."""
    key_val = deref(key)
    old_val = deref(old_dict)
    if not is_var(key_val) and isinstance(old_val, DictTerm) and key_val in old_val:
        new_data = {k: v for k, v in old_val.items() if k != key_val}
        mark = trail.mark()
        if unify(new_dict, DictTerm(new_data), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("dict_merge", 3)
def _dict_merge__3(this_generator, parent, d1, d2, merged, trail):
    """dict_merge(D1, D2, Merged) — Merged is D1 updated with D2's key-value pairs."""
    d1_val = deref(d1)
    d2_val = deref(d2)
    if isinstance(d1_val, DictTerm) and isinstance(d2_val, DictTerm):
        new_data = dict(d1_val.data)
        new_data.update(d2_val.data)
        mark = trail.mark()
        if unify(merged, DictTerm(new_data), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("gen_dict", 3)
def _gen_dict__3(this_generator, parent, key, d, value, trail):
    """gen_dict(Key, Dict, Value) — enumerate all key-value pairs on backtracking."""
    d_val = deref(d)
    if isinstance(d_val, DictTerm):
        for k, v in d_val.items():
            mark = trail.mark()
            if unify(key, k, trail) and unify(value, v, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


# ── sub_dict: partial dict matching ───────────────────────────────────────────


@_trampoline_builtin("sub_dict", 2)
def _sub_dict__2(this_generator, parent, pattern, full_dict, trail):
    """sub_dict(Pattern, Dict) — Pattern's keys are a subset of Dict's keys.

    Values for Pattern's keys unify pairwise with corresponding values in Dict.
    Dict may have extra keys (they are ignored).

    Example:
        get_name(PERSON, NAME) <- sub_dict({name: NAME}, PERSON),
    """
    pat_val = deref(pattern)
    full_val = deref(full_dict)
    if isinstance(pat_val, DictTerm) and isinstance(full_val, DictTerm):
        mark = trail.mark()
        ok = True
        for k in pat_val.keys():
            if k not in full_val:
                ok = False
                break
            if not unify(pat_val[k], full_val[k], trail):
                ok = False
                break
        if ok:
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


# ── Set builtins ─────────────────────────────────────────────────────────────


@_builtin("is_set", 1)
def _is_set__1(term, trail, k):
    """is_set(Term) — succeeds if Term is a SetTerm."""
    if isinstance(deref(term), SetTerm):
        yield None


@_trampoline_builtin("set_size", 2)
def _set_size__2(this_generator, parent, s, n, trail):
    """set_size(Set, N) — N is the cardinality of Set."""
    s_val = deref(s)
    if isinstance(s_val, SetTerm):
        mark = trail.mark()
        if unify(n, len(s_val), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("set_list", 2)
def _set_list__2(this_generator, parent, s, lst, trail):
    """set_list(Set, List) — Set ↔ sorted list of elements.

    Modes:
      set_list(+SetTerm, -List) — decompose set to sorted list
      set_list(-SetTerm, +List) — construct set from list
    """
    s_val = deref(s)
    lst_val = deref(lst)

    if isinstance(s_val, SetTerm):
        sorted_elems = sorted(s_val.elements, key=repr)
        mark = trail.mark()
        if unify(lst, sorted_elems, trail):
            yield (parent, None)
        trail.undo(mark)

    elif isinstance(lst_val, list):
        elems = [deref(e) for e in lst_val]
        if all(not is_var(e) for e in elems):
            mark = trail.mark()
            if unify(s, SetTerm(elems), trail):
                yield (parent, None)
            trail.undo(mark)

    yield (parent, DONE)


def _set_union_dr__3(this_generator, parent, s1, s2, union, trail):
    """Destructive-reuse variant of set_union/3.

    When the first SetTerm has a low reference count (not shared), replace its
    internal ``_elements`` frozenset in-place.  Falls back to the standard
    (copying) implementation otherwise.
    """
    import sys  # noqa: PLC0415

    s1_val = deref(s1)
    s2_val = deref(s2)
    if (isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm)
            and sys.getrefcount(s1_val) <= 3):
        s1_val._elements = s1_val._elements | s2_val._elements
        mark = trail.mark()
        if unify(union, s1_val, trail):
            yield (parent, None)
        trail.undo(mark)
        yield (parent, DONE)
        return
    # Fallback to standard set_union
    yield from _set_union__3(this_generator, parent, s1, s2, union, trail)


@_trampoline_builtin("set_union", 3)
def _set_union__3(this_generator, parent, s1, s2, union, trail):
    """set_union(S1, S2, union) — union is the union of S1 and S2."""
    s1_val = deref(s1)
    s2_val = deref(s2)
    if isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm):
        mark = trail.mark()
        if unify(union, SetTerm(s1_val.elements | s2_val.elements), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("set_intersection", 3)
def _set_intersection__3(this_generator, parent, s1, s2, inter, trail):
    """set_intersection(S1, S2, Inter) — Inter is the intersection of S1 and S2."""
    s1_val = deref(s1)
    s2_val = deref(s2)
    if isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm):
        mark = trail.mark()
        if unify(inter, SetTerm(s1_val.elements & s2_val.elements), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("set_subtract", 3)
def _set_subtract__3(this_generator, parent, s1, s2, diff, trail):
    """set_subtract(S1, S2, Diff) — Diff is S1 minus S2."""
    s1_val = deref(s1)
    s2_val = deref(s2)
    if isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm):
        mark = trail.mark()
        if unify(diff, SetTerm(s1_val.elements - s2_val.elements), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("set_sym_diff", 3)
def _set_symdiff__3(this_generator, parent, s1, s2, sym, trail):
    """set_symdiff(S1, S2, Sym) — Sym is the symmetric difference of S1 and S2."""
    s1_val = deref(s1)
    s2_val = deref(s2)
    if isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm):
        mark = trail.mark()
        if unify(sym, SetTerm(s1_val.elements ^ s2_val.elements), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_builtin("set_subset", 2)
def _set_subset__2(sub, sup, trail, k):
    """set_subset(Sub, Super) — Sub is a subset of Super."""
    sub_val = deref(sub)
    sup_val = deref(sup)
    if isinstance(sub_val, SetTerm) and isinstance(sup_val, SetTerm):
        if sub_val.elements <= sup_val.elements:
            yield None


@_builtin("set_disjoint", 2)
def _set_disjoint__2(s1, s2, trail, k):
    """set_disjoint(S1, S2) — S1 and S2 have no elements in common."""
    s1_val = deref(s1)
    s2_val = deref(s2)
    if isinstance(s1_val, SetTerm) and isinstance(s2_val, SetTerm):
        if s1_val.elements.isdisjoint(s2_val.elements):
            yield None


@_trampoline_builtin("set_add", 3)
def _set_add__3(this_generator, parent, elem, old_set, new_set, trail):
    """set_add(Elem, OldSet, NewSet) — NewSet is OldSet with Elem added."""
    elem_val = deref(elem)
    old_val = deref(old_set)
    if not is_var(elem_val) and isinstance(old_val, SetTerm):
        mark = trail.mark()
        if unify(new_set, SetTerm(old_val.elements | {elem_val}), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("set_remove", 3)
def _set_remove__3(this_generator, parent, elem, old_set, new_set, trail):
    """set_remove(Elem, OldSet, NewSet) — NewSet is OldSet without Elem."""
    elem_val = deref(elem)
    old_val = deref(old_set)
    if not is_var(elem_val) and isinstance(old_val, SetTerm):
        mark = trail.mark()
        if unify(new_set, SetTerm(old_val.elements - {elem_val}), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("gen_set", 2)
def _gen_set__2(this_generator, parent, elem, s, trail):
    """gen_set(Elem, Set) — enumerate all elements of Set on backtracking."""
    s_val = deref(s)
    if isinstance(s_val, SetTerm):
        for e in sorted(s_val.elements, key=repr):
            mark = trail.mark()
            if unify(elem, e, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)

