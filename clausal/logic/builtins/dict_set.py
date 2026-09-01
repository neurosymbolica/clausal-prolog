"""Dict and Set builtins (Phase 3 + Phase 4).

Dict builtins:
  is_dict/1         — type check
  dict_size/2       — number of keys
  dict_keys/2       — extract key list (sorted for determinism)
  dict_values/2     — extract value list (in key order)
  dict_pairs/2      — DictTerm ↔ list of (Key: Value) pairs
  dict_get/3        — dict_get(Key, Dict, Value) — semidet lookup
  tri_get/3         — tri_get(Dict, Key, Value) — Kleene read (absent → Undefined)
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
from clausal.logic.exceptions import (
    LogicException, type_error, existence_error, instantiation_error,
)

# ── Destructive-reuse: CPython refcount availability ────────────────────────

import platform as _platform
import sys as _sys

_HAS_REFCOUNT: bool = (
    _platform.python_implementation() == "CPython"
    and hasattr(_sys, "getrefcount")
)


def _is_hashable(x) -> bool:
    try:
        hash(x)
        return True
    except TypeError:
        return False

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


def _dict_input(v):
    """The underlying mapping of a dict-valued term, or ``None``.

    Accepts a plain Python ``dict`` wherever ``DictTerm`` is accepted:
    subscript, ``DictTerm.__unify__``, structural ``==`` and the profile API
    (`get/3` family) already treat the two as the same term, so a KEY-first
    builtin that fails SOFTLY on the plain flavor hands a Python caller a
    partly working dict and a silent wrong answer (the get/3 precedent —
    todo/done/get3-rejects-a-plain-dict-that-subscript-accepts.md, swept by
    todo/dictterm-only-builtins-sweep.md).  Callers must NOT mutate the
    returned mapping: for a plain dict it IS the caller's object.
    """
    if isinstance(v, DictTerm):
        return v.data
    if isinstance(v, dict):
        return v
    return None


def _set_input(v):
    """The underlying element set of a set-valued term, or ``None`` — the
    ``SetTerm``/plain-``set`` twin of ``_dict_input`` (structural ``==`` and
    unify already accept plain sets).  Same no-mutation rule."""
    if isinstance(v, SetTerm):
        return v.elements
    if isinstance(v, (set, frozenset)):
        return v
    return None


# ── Dict builtins ─────────────────────────────────────────────────────────────


@_builtin("is_dict", 1)
def _is_dict__1(term, trail, k):
    """is_dict(Term) — succeeds if Term is a DictTerm or a plain dict."""
    if _dict_input(deref(term)) is not None:
        yield None


@_trampoline_builtin("dict_size", 2)
def _dict_size__2(this_generator, _proceed, _fail, _catcher, d, n, trail):
    """dict_size(Dict, N) — N is the number of keys in Dict."""
    data = _dict_input(deref(d))
    if data is not None:
        mark = trail.mark()
        if unify(n, len(data), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_keys", 2)
def _dict_keys__2(this_generator, _proceed, _fail, _catcher, d, keys, trail):
    """dict_keys(Dict, Keys) — Keys is the sorted list of keys in Dict."""
    data = _dict_input(deref(d))
    if data is not None:
        sorted_keys = sorted(data.keys(), key=repr)
        mark = trail.mark()
        if unify(keys, sorted_keys, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_values", 2)
def _dict_values__2(this_generator, _proceed, _fail, _catcher, d, values, trail):
    """dict_values(Dict, Values) — Values is the list of values in key-sorted order."""
    data = _dict_input(deref(d))
    if data is not None:
        sorted_keys = sorted(data.keys(), key=repr)
        vals = [data[k] for k in sorted_keys]
        mark = trail.mark()
        if unify(values, vals, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_pairs", 2)
def _dict_pairs__2(this_generator, _proceed, _fail, _catcher, d, pairs, trail):
    """dict_pairs(Dict, Pairs) — Dict ↔ list of [Key, Value] 2-element lists.

    Modes:
      dict_pairs(+DictTerm, -Pairs) — decompose dict into pair list
      dict_pairs(-DictTerm, +Pairs) — construct dict from pair list
    """
    d_val = deref(d)
    pairs_val = deref(pairs)

    data = _dict_input(d_val)
    if data is not None:
        # Dict → Pairs
        sorted_keys = sorted(data.keys(), key=repr)
        pair_list = [[k, data[k]] for k in sorted_keys]
        mark = trail.mark()
        if unify(pairs, pair_list, trail):
            yield (_proceed, None)
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
                try:
                    data[k] = v
                except TypeError:
                    # A09-F012: an unhashable key (e.g. a list) escaped as a
                    # raw TypeError, uncatchable by catch/3. Raise a typed
                    # error instead (A09-D002).
                    raise LogicException(
                        type_error("hashable", k, "dict_pairs/2"))
            else:
                ok = False
                break
        if ok:
            mark = trail.mark()
            if unify(d, DictTerm(data), trail):
                yield (_proceed, None)
            trail.undo(mark)

    yield (_fail, DONE)


@_trampoline_builtin("dict_get", 3)
def _dict_get__3(this_generator, _proceed, _fail, _catcher, key, d, value, trail):
    """dict_get(Key, Dict, Value) — semidet: Value is Dict[Key]."""
    key_val = deref(key)
    data = _dict_input(deref(d))
    if not is_var(key_val) and data is not None and key_val in data:
        mark = trail.mark()
        if unify(value, data[key_val], trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _dict_put_dr__4(this_generator, _proceed, _fail, _catcher, key, value, old_dict, new_dict, trail):
    """Destructive-reuse variant of dict_put/4.

    When the old DictTerm has a low reference count (not shared), mutate its
    internal ``_data`` dict in-place.  Falls back to the standard (copying)
    implementation otherwise.
    """
    key_val = deref(key)
    old_val = deref(old_dict)
    if (_HAS_REFCOUNT and not is_var(key_val) and isinstance(old_val, DictTerm)
            and _sys.getrefcount(old_val) <= 3):
        old_val._data[key_val] = deref(value)
        mark = trail.mark()
        if unify(new_dict, old_val, trail):
            yield (_proceed, None)
        trail.undo(mark)
        yield (_fail, DONE)
        return
    # Fallback to standard dict_put
    yield from _dict_put__4(this_generator, _proceed, _fail, _catcher, key, value, old_dict, new_dict, trail)


@_trampoline_builtin("dict_put", 4)
def _dict_put__4(this_generator, _proceed, _fail, _catcher, key, value, old_dict, new_dict, trail):
    """dict_put(Key, Value, OldDict, NewDict) — NewDict is OldDict with Key→Value."""
    key_val = deref(key)
    old_data = _dict_input(deref(old_dict))
    if not is_var(key_val) and old_data is not None:
        new_data = dict(old_data)
        new_data[key_val] = deref(value)
        mark = trail.mark()
        if unify(new_dict, DictTerm(new_data), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_put_pairs", 3)
def _dict_put_pairs__3(this_generator, _proceed, _fail, _catcher, pairs, old_dict, new_dict, trail):
    """dict_put(Pairs, OldDict, NewDict) — bulk update from [[Key, Value], ...] list."""
    pairs_val = deref(pairs)
    old_data = _dict_input(deref(old_dict))
    if isinstance(pairs_val, list) and old_data is not None:
        new_data = dict(old_data)
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
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_remove", 3)
def _dict_remove__3(this_generator, _proceed, _fail, _catcher, key, old_dict, new_dict, trail):
    """dict_remove(Key, OldDict, NewDict) — NewDict is OldDict without Key."""
    key_val = deref(key)
    old_data = _dict_input(deref(old_dict))
    if not is_var(key_val) and old_data is not None and key_val in old_data:
        new_data = {k: v for k, v in old_data.items() if k != key_val}
        mark = trail.mark()
        if unify(new_dict, DictTerm(new_data), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("dict_merge", 3)
def _dict_merge__3(this_generator, _proceed, _fail, _catcher, d1, d2, merged, trail):
    """dict_merge(D1, D2, Merged) — Merged is D1 updated with D2's key-value pairs."""
    d1_data = _dict_input(deref(d1))
    d2_data = _dict_input(deref(d2))
    if d1_data is not None and d2_data is not None:
        new_data = dict(d1_data)
        new_data.update(d2_data)
        mark = trail.mark()
        if unify(merged, DictTerm(new_data), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("gen_dict", 3)
def _gen_dict__3(this_generator, _proceed, _fail, _catcher, key, d, value, trail):
    """gen_dict(Key, Dict, Value) — enumerate all key-value pairs on backtracking."""
    data = _dict_input(deref(d))
    if data is not None:
        for k, v in data.items():
            mark = trail.mark()
            if unify(key, k, trail) and unify(value, v, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


# ── sub_dict: partial dict matching ───────────────────────────────────────────


@_trampoline_builtin("sub_dict", 2)
def _sub_dict__2(this_generator, _proceed, _fail, _catcher, pattern, full_dict, trail):
    """sub_dict(Pattern, Dict) — Pattern's keys are a subset of Dict's keys.

    Values for Pattern's keys unify pairwise with corresponding values in Dict.
    Dict may have extra keys (they are ignored).

    Example:
        get_name(PERSON, NAME) <- sub_dict({name: NAME}, PERSON),
    """
    pat_data = _dict_input(deref(pattern))
    full_data = _dict_input(deref(full_dict))
    if pat_data is not None and full_data is not None:
        mark = trail.mark()
        ok = True
        for k in pat_data.keys():
            if k not in full_data:
                ok = False
                break
            if not unify(pat_data[k], full_data[k], trail):
                ok = False
                break
        if ok:
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── Dict-native profile API: Python dict-surface reads/removal ────────────────
# The pinned surface (todo/dict-native-profile-api.md): DICT-first arg order,
# Python-familiar names.  Distinct from the older dict_get/dict_remove family
# above (which are KEY-first).  Strict reads/removal throw; soft ones fail.


@_trampoline_builtin("get", 3)
def _get__3(this_generator, _proceed, _fail, _catcher, d, key, value, trail):
    """get(Dict, Key, Value) — soft read (Python ``dict.get``).

    Binds ``Value`` to ``Dict[Key]`` if present; **fails** the clause if the
    key is absent (the logic analogue of ``d.get(k)`` returning ``None`` — never
    binds a sentinel).  A non-ground key or non-dict object fails (soft: this
    predicate never throws — use ``V is P[K]`` for the strict, throwing read).

    Accepts a plain Python ``dict`` as well as a ``DictTerm``, matching the
    subscript read — a Python caller's ``{'k': v}`` profile must not be
    half-accepted (subscript reads working, every ``get`` guard silently
    failing).
    """
    key_val = deref(key)
    d_val = deref(d)
    if (not is_var(key_val) and _is_hashable(key_val)
            and isinstance(d_val, (DictTerm, dict)) and key_val in d_val):
        mark = trail.mark()
        if unify(value, d_val[key_val], trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("get", 4)
def _get__4(this_generator, _proceed, _fail, _catcher, d, key, value, default, trail):
    """get(Dict, Key, Value, Default) — defaulted read (Python ``dict.get(k, default)``).

    Binds ``Value`` to ``Dict[Key]`` if present, else to ``Default``.  Always
    succeeds when ``Dict`` is a dict (``DictTerm`` or plain ``dict``) and
    ``Key`` is a ground hashable key.
    """
    key_val = deref(key)
    d_val = deref(d)
    if (not is_var(key_val) and _is_hashable(key_val)
            and isinstance(d_val, (DictTerm, dict))):
        result = d_val[key_val] if key_val in d_val else default
        mark = trail.mark()
        if unify(value, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("tri_get", 3)
def _tri_get__3(this_generator, _proceed, _fail, _catcher, d, key, value, trail):
    """tri_get(Dict, Key, Value) — three-valued (Kleene) profile read.

    Binds ``Value`` to ``Dict[Key]`` if the key is present, else to the Kleene
    ``Undefined`` builtin (the third truth value).  This replaces the pervasive
    ``tri_<key>(Profile, T)`` reader boilerplate — 2 clauses per key — in the
    deontic corpus domains (absent profile key → ``unknown``).

    Edge cases mirror ``get/3`` exactly: soft (never throws) — a non-ground key,
    a non-hashable key, or a non-dict ``Dict`` simply **fails**.  The ONLY
    behavioural difference from ``get/3`` is the absent-key branch: ``get/3``
    fails, ``tri_get/3`` binds ``Undefined``.  Deterministic (one solution when it
    succeeds).
    """
    from clausal.terms import Undefined  # noqa: PLC0415
    key_val = deref(key)
    d_val = deref(d)
    if (not is_var(key_val) and _is_hashable(key_val)
            and isinstance(d_val, (DictTerm, dict))):
        result = d_val[key_val] if key_val in d_val else Undefined
        mark = trail.mark()
        if unify(value, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("delete", 3)
def _delete__3(this_generator, _proceed, _fail, _catcher, d, key, new_dict, trail):
    """delete(Dict, Key, NewDict) — functional key removal (Python ``del d[k]``).

    Binds ``NewDict`` to a fresh ``DictTerm`` equal to ``Dict`` without ``Key``.
    **Throws** ``existence_error`` if ``Key`` is absent (strict, mirroring
    ``del d[missing]`` raising ``KeyError``); ``instantiation_error`` for a
    non-ground key; ``type_error`` for a non-dict object.  ``Dict`` is never
    mutated (the residual is constructed fresh).
    """
    key_val = deref(key)
    d_val = deref(d)
    if is_var(key_val):
        raise LogicException(instantiation_error("delete/3"))
    if not _is_hashable(key_val):
        raise LogicException(type_error("dict_key", key_val, "delete/3"))
    if not isinstance(d_val, (DictTerm, dict)):
        raise LogicException(type_error("dict", d_val, "delete/3"))
    if key_val not in d_val:
        raise LogicException(existence_error("dict_key", key_val, "delete/3"))
    new_data = {k: v for k, v in d_val.items() if k != key_val}
    mark = trail.mark()
    if unify(new_dict, DictTerm(new_data), trail):
        yield (_proceed, None)
    trail.undo(mark)
    yield (_fail, DONE)


# ── Set builtins ─────────────────────────────────────────────────────────────


@_builtin("is_set", 1)
def _is_set__1(term, trail, k):
    """is_set(Term) — succeeds if Term is a SetTerm or a plain set."""
    if _set_input(deref(term)) is not None:
        yield None


@_trampoline_builtin("set_size", 2)
def _set_size__2(this_generator, _proceed, _fail, _catcher, s, n, trail):
    """set_size(Set, N) — N is the cardinality of Set."""
    elems = _set_input(deref(s))
    if elems is not None:
        mark = trail.mark()
        if unify(n, len(elems), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("set_list", 2)
def _set_list__2(this_generator, _proceed, _fail, _catcher, s, lst, trail):
    """set_list(Set, List) — Set ↔ sorted list of elements.

    Modes:
      set_list(+SetTerm, -List) — decompose set to sorted list
      set_list(-SetTerm, +List) — construct set from list
    """
    s_val = deref(s)
    lst_val = deref(lst)

    s_elems = _set_input(s_val)
    if s_elems is not None:
        sorted_elems = sorted(s_elems, key=repr)
        mark = trail.mark()
        if unify(lst, sorted_elems, trail):
            yield (_proceed, None)
        trail.undo(mark)

    elif isinstance(lst_val, list):
        elems = [deref(e) for e in lst_val]
        if all(not is_var(e) for e in elems):
            try:
                set_term = SetTerm(elems)
            except TypeError:
                # A09-F012: an unhashable element escaped as a raw TypeError.
                bad = next((e for e in elems if not _is_hashable(e)), elems)
                raise LogicException(type_error("hashable", bad, "set_list/2"))
            mark = trail.mark()
            if unify(s, set_term, trail):
                yield (_proceed, None)
            trail.undo(mark)

    yield (_fail, DONE)


def _set_union_dr__3(this_generator, _proceed, _fail, _catcher, s1, s2, union, trail):
    """Destructive-reuse variant of set_union/3.

    When the first SetTerm has a low reference count (not shared), replace its
    internal ``_elements`` frozenset in-place.  Falls back to the standard
    (copying) implementation otherwise.
    """
    s1_val = deref(s1)
    s2_val = deref(s2)
    if (_HAS_REFCOUNT and isinstance(s1_val, SetTerm)
            and isinstance(s2_val, SetTerm)
            and _sys.getrefcount(s1_val) <= 3):
        # Replace _elements on the reused wrapper (avoids new SetTerm alloc).
        # Still allocates a new frozenset — true in-place set mutation would
        # require changing SetTerm internals from frozenset to set.
        s1_val._elements = s1_val._elements | s2_val._elements
        mark = trail.mark()
        if unify(union, s1_val, trail):
            yield (_proceed, None)
        trail.undo(mark)
        yield (_fail, DONE)
        return
    # Fallback to standard set_union
    yield from _set_union__3(this_generator, _proceed, _fail, _catcher, s1, s2, union, trail)


@_trampoline_builtin("set_union", 3)
def _set_union__3(this_generator, _proceed, _fail, _catcher, s1, s2, union, trail):
    """set_union(S1, S2, union) — union is the union of S1 and S2."""
    e1 = _set_input(deref(s1))
    e2 = _set_input(deref(s2))
    if e1 is not None and e2 is not None:
        mark = trail.mark()
        if unify(union, SetTerm(frozenset(e1) | frozenset(e2)), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("set_intersection", 3)
def _set_intersection__3(this_generator, _proceed, _fail, _catcher, s1, s2, inter, trail):
    """set_intersection(S1, S2, Inter) — Inter is the intersection of S1 and S2."""
    e1 = _set_input(deref(s1))
    e2 = _set_input(deref(s2))
    if e1 is not None and e2 is not None:
        mark = trail.mark()
        if unify(inter, SetTerm(frozenset(e1) & frozenset(e2)), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("set_subtract", 3)
def _set_subtract__3(this_generator, _proceed, _fail, _catcher, s1, s2, diff, trail):
    """set_subtract(S1, S2, Diff) — Diff is S1 minus S2."""
    e1 = _set_input(deref(s1))
    e2 = _set_input(deref(s2))
    if e1 is not None and e2 is not None:
        mark = trail.mark()
        if unify(diff, SetTerm(frozenset(e1) - frozenset(e2)), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("set_sym_diff", 3)
def _set_symdiff__3(this_generator, _proceed, _fail, _catcher, s1, s2, sym, trail):
    """set_symdiff(S1, S2, Sym) — Sym is the symmetric difference of S1 and S2."""
    e1 = _set_input(deref(s1))
    e2 = _set_input(deref(s2))
    if e1 is not None and e2 is not None:
        mark = trail.mark()
        if unify(sym, SetTerm(frozenset(e1) ^ frozenset(e2)), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_builtin("set_subset", 2)
def _set_subset__2(sub, sup, trail, k):
    """set_subset(Sub, Super) — Sub is a subset of Super."""
    sub_elems = _set_input(deref(sub))
    sup_elems = _set_input(deref(sup))
    if sub_elems is not None and sup_elems is not None:
        if frozenset(sub_elems) <= frozenset(sup_elems):
            yield None


@_builtin("set_disjoint", 2)
def _set_disjoint__2(s1, s2, trail, k):
    """set_disjoint(S1, S2) — S1 and S2 have no elements in common."""
    e1 = _set_input(deref(s1))
    e2 = _set_input(deref(s2))
    if e1 is not None and e2 is not None:
        if frozenset(e1).isdisjoint(e2):
            yield None


@_trampoline_builtin("set_add", 3)
def _set_add__3(this_generator, _proceed, _fail, _catcher, elem, old_set, new_set, trail):
    """set_add(Elem, OldSet, NewSet) — NewSet is OldSet with Elem added."""
    elem_val = deref(elem)
    old_elems = _set_input(deref(old_set))
    if not is_var(elem_val) and old_elems is not None:
        if not _is_hashable(elem_val):
            # A09-F012: an unhashable element escaped as a raw TypeError.
            raise LogicException(type_error("hashable", elem_val, "set_add/3"))
        mark = trail.mark()
        if unify(new_set, SetTerm(frozenset(old_elems) | {elem_val}), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("set_remove", 3)
def _set_remove__3(this_generator, _proceed, _fail, _catcher, elem, old_set, new_set, trail):
    """set_remove(Elem, OldSet, NewSet) — NewSet is OldSet without Elem."""
    elem_val = deref(elem)
    old_elems = _set_input(deref(old_set))
    if not is_var(elem_val) and old_elems is not None:
        if not _is_hashable(elem_val):
            # A09-F012: an unhashable element escaped as a raw TypeError.
            raise LogicException(
                type_error("hashable", elem_val, "set_remove/3"))
        mark = trail.mark()
        if unify(new_set, SetTerm(frozenset(old_elems) - {elem_val}), trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("gen_set", 2)
def _gen_set__2(this_generator, _proceed, _fail, _catcher, elem, s, trail):
    """gen_set(Elem, Set) — enumerate all elements of Set on backtracking."""
    elems = _set_input(deref(s))
    if elems is not None:
        for e in sorted(elems, key=repr):
            mark = trail.mark()
            if unify(elem, e, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)

