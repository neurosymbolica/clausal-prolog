"""List builtins: in_/2, in_check/2, append/3, length/2, last/2, reverse/2,
get_item/3, flatten/2, msort/2, sort/2, permutation/2, select/3,
subtract/3, intersection/3, union/3, list_to_set/2, sum_list/2, max_list/2, min_list/2,
take/3, drop/3, split_at/4, zip_/3, replicate/3, split_with/3,
numlist/2,3, same_length/2, transpose/2."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE

from clausal.logic.builtins._registry import _trampoline_builtin, _builtin

# ── Destructive-reuse: CPython refcount availability ────────────────────────

import platform as _platform
import sys as _sys

_HAS_REFCOUNT: bool = (
    _platform.python_implementation() == "CPython"
    and hasattr(_sys, "getrefcount")
)

# ── C-accelerated inner loops (Option B: C helpers from Python generators) ───

try:
    from clausal.logic._lists_core import (
        member_find as _c_member_find,
        memberchk_find as _c_memberchk_find,
        append_split_find as _c_append_split_find,
        select_find as _c_select_find,
        permutation_find as _c_permutation_find,
        nth0_find as _c_nth0_find,
    )
except ImportError:
    _c_member_find = None
    _c_memberchk_find = None
    _c_append_split_find = None
    _c_select_find = None
    _c_permutation_find = None
    _c_nth0_find = None


# ── String-as-list helpers ───────────────────────────────────────────────────

def _as_items(val):
    """Return list of elements if *val* is a sequence (list or str), else None.

    For strings, returns list of single-char strings.
    """
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return list(val)
    return None


def _seq_result(items, was_string):
    """Reconstruct a string when the original input was a string and the
    result consists entirely of single-character strings."""
    if was_string and all(isinstance(c, str) and len(c) == 1 for c in items):
        return "".join(items)
    return items


@_trampoline_builtin("in_", 2)
def _member__2(this_generator, _proceed, _fail, _catcher, elem, lst, trail):
    """member(Elem, List) — Elem is a member of List; enumerates on backtrack."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        if _c_member_find is not None:
            idx = 0
            while True:
                result = _c_member_find(items, idx, elem, trail)
                if result is None:
                    break
                idx, mark = result
                yield (_proceed, None)
                trail.undo(mark)
        else:
            for item in items:
                mark = trail.mark()
                if unify(elem, item, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("in_check", 2)
def _memberchk__2(this_generator, _proceed, _fail, _catcher, elem, lst, trail):
    """memberchk(Elem, List) — like member/2 but commits to the first match."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        if _c_memberchk_find is not None:
            if _c_memberchk_find(items, elem, trail):
                yield (_proceed, None)
                yield (_fail, DONE)
                return
        else:
            for item in items:
                mark = trail.mark()
                if unify(elem, item, trail):
                    yield (_proceed, None)
                    yield (_fail, DONE)
                    return
                trail.undo(mark)
    yield (_fail, DONE)


def _append_dr__3(this_generator, _proceed, _fail, _catcher, l1, l2, l3, trail):
    """Destructive-reuse variant of append/3.

    When the first list (l1) has a reference count low enough to prove it is
    not shared, extend it in-place instead of allocating a new list.  Falls
    back to the standard (copying) implementation otherwise.
    """
    l1_val = deref(l1)
    # Only attempt destructive reuse for the deterministic (+,+,-) mode
    # with an actual Python list (not string) and a low reference count.
    if (_HAS_REFCOUNT and isinstance(l1_val, list)
            and _sys.getrefcount(l1_val) <= 3):
        l2_val = deref(l2)
        l2_items = _as_items(l2_val)
        if l2_items is not None:
            l1_val.extend(l2_items)
            mark = trail.mark()
            if unify(l3, l1_val, trail):
                yield (_proceed, None)
            trail.undo(mark)
            yield (_fail, DONE)
            return
    # Fallback to standard append
    yield from _append__3(this_generator, _proceed, _fail, _catcher, l1, l2, l3, trail)


@_trampoline_builtin("append", 3)
def _append__3(this_generator, _proceed, _fail, _catcher, l1, l2, l3, trail):
    """append(L1, L2, L3) — L3 is the concatenation of L1 and L2.

    Modes:
      append(+, +, -) — deterministic concatenation
      append(+, -, +) — split L3 starting from L1
      append(-, -, +) — enumerate all splits of L3
    """
    l1_val = deref(l1)
    l2_val = deref(l2)
    l3_val = deref(l3)

    l1_items = _as_items(l1_val)
    l2_items = _as_items(l2_val)
    l3_items = _as_items(l3_val)
    # Track whether all bound sequence inputs are strings for result type
    _all_str = isinstance(l1_val, str) or isinstance(l2_val, str) or isinstance(l3_val, str)
    _any_list = isinstance(l1_val, list) or isinstance(l2_val, list) or isinstance(l3_val, list)
    _out_str = _all_str and not _any_list

    if l1_items is not None and l2_items is not None:
        # Both known: concatenate
        result = _seq_result(l1_items + l2_items, _out_str)
        mark = trail.mark()
        if unify(l3, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif l1_items is not None and l3_items is not None:
        # L1 and L3 known: compute L2
        n = len(l1_items)
        if len(l3_items) >= n and l3_items[:n] == l1_items:
            remainder = _seq_result(l3_items[n:], _out_str)
            mark = trail.mark()
            if unify(l2, remainder, trail):
                yield (_proceed, None)
            trail.undo(mark)
    elif l3_items is not None:
        # Only L3 known: enumerate all splits
        if _c_append_split_find is not None:
            idx = 0
            while True:
                result = _c_append_split_find(
                    l3_items, idx, l1, l2, _out_str, trail)
                if result is None:
                    break
                idx, mark = result
                yield (_proceed, None)
                trail.undo(mark)
        else:
            for i in range(len(l3_items) + 1):
                prefix = _seq_result(l3_items[:i], _out_str)
                suffix = _seq_result(l3_items[i:], _out_str)
                mark = trail.mark()
                if unify(l1, prefix, trail) and unify(l2, suffix, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("length", 2)
def _length__2(this_generator, _proceed, _fail, _catcher, lst, n, trail):
    """length(List, N) — N is the length of List."""
    lst_val = deref(lst)
    n_val = deref(n)
    if isinstance(lst_val, (list, str)):
        mark = trail.mark()
        if unify(n, len(lst_val), trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif not is_var(n_val) and isinstance(n_val, int) and n_val >= 0:
        result = [Var() for _ in range(n_val)]
        mark = trail.mark()
        if unify(lst, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("last", 2)
def _last__2(this_generator, _proceed, _fail, _catcher, lst, elem, trail):
    """last(List, Elem) — Elem is the last element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, (list, str)) and len(lst_val) > 0:
        mark = trail.mark()
        if unify(elem, lst_val[-1], trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("reverse", 2)
def _reverse__2(this_generator, _proceed, _fail, _catcher, lst, rev, trail):
    """reverse(List, Rev) — Rev is the reverse of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, (list, str)):
        was_str = isinstance(lst_val, str)
        result = _seq_result(list(reversed(lst_val)), was_str)
        mark = trail.mark()
        if unify(rev, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("get_item", 3)
def _nth0__3(this_generator, _proceed, _fail, _catcher, n, lst, elem, trail):
    """nth0(N, List, Elem) — Elem is the N-th element of List (0-based)."""
    n_val = deref(n)
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        if not is_var(n_val):
            if isinstance(n_val, int) and 0 <= n_val < len(items):
                mark = trail.mark()
                if unify(elem, items[n_val], trail):
                    yield (_proceed, None)
                trail.undo(mark)
        else:
            if _c_nth0_find is not None:
                idx = 0
                while True:
                    result = _c_nth0_find(items, idx, n, elem, trail)
                    if result is None:
                        break
                    idx, mark = result
                    yield (_proceed, None)
                    trail.undo(mark)
            else:
                for i, item in enumerate(items):
                    mark = trail.mark()
                    if unify(n, i, trail) and unify(elem, item, trail):
                        yield (_proceed, None)
                    trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("flatten", 2)
def _flatten__2(this_generator, _proceed, _fail, _catcher, lst, flat, trail):
    """flatten(List, Flat) — Flat is the flat list of all atoms in List.

    Strings are treated as atoms (not flattened into characters).
    """
    lst_val = deref(lst)
    if not is_var(lst_val):
        result: list = []

        def _do_flat(x: Any) -> None:
            x = deref(x)
            if isinstance(x, list):
                for item in x:
                    _do_flat(item)
            else:
                # Strings are atoms, not recursed into
                result.append(x)

        _do_flat(lst_val)
        mark = trail.mark()
        if unify(flat, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("msort", 2)
def _msort__2(this_generator, _proceed, _fail, _catcher, lst, sorted_lst, trail):
    """msort(List, Sorted) — Sorted is List sorted, preserving duplicates."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        try:
            result = sorted(items)
        except TypeError:
            result = sorted(items, key=lambda x: (type(x).__name__, repr(x)))
        out = _seq_result(result, isinstance(lst_val, str))
        mark = trail.mark()
        if unify(sorted_lst, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("sort", 2)
def _sort__2(this_generator, _proceed, _fail, _catcher, lst, sorted_lst, trail):
    """sort(List, Sorted) — Sorted is List sorted with duplicates removed."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        seen: list = []
        for x in items:
            if x not in seen:
                seen.append(x)
        try:
            result = sorted(seen)
        except TypeError:
            result = sorted(seen, key=lambda x: (type(x).__name__, repr(x)))
        out = _seq_result(result, isinstance(lst_val, str))
        mark = trail.mark()
        if unify(sorted_lst, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("permutation", 2)
def _permutation__2(this_generator, _proceed, _fail, _catcher, lst, perm, trail):
    """permutation(List, Perm) — Perm is a permutation of List."""
    import itertools
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        was_str = isinstance(lst_val, str)
        if _c_permutation_find is not None:
            perm_iter = itertools.permutations(items)
            while True:
                mark = _c_permutation_find(perm_iter, perm, was_str, trail)
                if mark is None:
                    break
                yield (_proceed, None)
                trail.undo(mark)
        else:
            for p in itertools.permutations(items):
                mark = trail.mark()
                if unify(perm, _seq_result(list(p), was_str), trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("select", 3)
def _select__3(this_generator, _proceed, _fail, _catcher, elem, lst, rest, trail):
    """select(Elem, List, Rest) — Elem is in List, Rest is List without one occurrence."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        was_str = isinstance(lst_val, str)
        if _c_select_find is not None:
            idx = 0
            while True:
                result = _c_select_find(
                    items, idx, elem, rest, was_str, trail)
                if result is None:
                    break
                idx, mark = result
                yield (_proceed, None)
                trail.undo(mark)
        else:
            for i, item in enumerate(items):
                mark = trail.mark()
                remainder = _seq_result(items[:i] + items[i + 1:], was_str)
                if unify(elem, item, trail) and unify(rest, remainder, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("subtract", 3)
def _subtract__3(this_generator, _proceed, _fail, _catcher, set1, set2, diff, trail):
    """subtract(Set1, Set2, Diff) — Diff is Set1 minus elements in Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    s1_items = _as_items(s1)
    s2_items = _as_items(s2)
    if s1_items is not None and s2_items is not None:
        _out_str = isinstance(s1, str) and isinstance(s2, str)
        result = _seq_result([x for x in s1_items if x not in s2_items], _out_str)
        mark = trail.mark()
        if unify(diff, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("intersection", 3)
def _intersection__3(this_generator, _proceed, _fail, _catcher, set1, set2, inter, trail):
    """intersection(Set1, Set2, Inter) — Inter is the intersection of Set1 and Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    s1_items = _as_items(s1)
    s2_items = _as_items(s2)
    if s1_items is not None and s2_items is not None:
        _out_str = isinstance(s1, str) and isinstance(s2, str)
        result = _seq_result([x for x in s1_items if x in s2_items], _out_str)
        mark = trail.mark()
        if unify(inter, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("union", 3)
def _union__3(this_generator, _proceed, _fail, _catcher, set1, set2, uni, trail):
    """union(Set1, Set2, union) — union is Set1 ∪ Set2 (no duplicates)."""
    s1 = deref(set1)
    s2 = deref(set2)
    s1_items = _as_items(s1)
    s2_items = _as_items(s2)
    if s1_items is not None and s2_items is not None:
        _out_str = isinstance(s1, str) and isinstance(s2, str)
        result = list(s1_items)
        for x in s2_items:
            if x not in result:
                result.append(x)
        out = _seq_result(result, _out_str)
        mark = trail.mark()
        if unify(uni, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("list_to_set", 2)
def _list_to_set__2(this_generator, _proceed, _fail, _catcher, lst, set_out, trail):
    """list_to_set(List, Set) — Set is List with duplicates removed (order preserved)."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        seen: list = []
        for x in items:
            if x not in seen:
                seen.append(x)
        out = _seq_result(seen, isinstance(lst_val, str))
        mark = trail.mark()
        if unify(set_out, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("sum_list", 2)
def _sum_list__2(this_generator, _proceed, _fail, _catcher, lst, total, trail):
    """sum_list(List, Total) — Total is the sum of all numbers in List."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        try:
            s = sum(deref(x) for x in items)
        except TypeError:
            yield (_fail, DONE)
            return
        mark = trail.mark()
        if unify(total, s, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("max_list", 2)
def _max_list__2(this_generator, _proceed, _fail, _catcher, lst, maximum, trail):
    """max_list(List, max_) — max_ is the maximum element of List."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None and len(items) > 0:
        try:
            m = max(deref(x) for x in items)
        except TypeError:
            yield (_fail, DONE)
            return
        mark = trail.mark()
        if unify(maximum, m, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("min_list", 2)
def _min_list__2(this_generator, _proceed, _fail, _catcher, lst, minimum, trail):
    """min_list(List, min_) — min_ is the minimum element of List."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None and len(items) > 0:
        try:
            m = min(deref(x) for x in items)
        except TypeError:
            yield (_fail, DONE)
            return
        mark = trail.mark()
        if unify(minimum, m, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


# ── V3-5: Extended list predicates ────────────────────────────────────────────


@_trampoline_builtin("take", 3)
def _take__3(this_generator, _proceed, _fail, _catcher, n, lst, taken, trail):
    """take(N, List, Taken) — Taken is the first N elements of List."""
    n_val, lst_val = deref(n), deref(lst)
    items = _as_items(lst_val)
    if isinstance(n_val, int) and items is not None:
        was_str = isinstance(lst_val, str)
        result = _seq_result(items[:n_val] if n_val >= 0 else [], was_str)
        mark = trail.mark()
        if unify(taken, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("drop", 3)
def _drop__3(this_generator, _proceed, _fail, _catcher, n, lst, rest, trail):
    """drop(N, List, Rest) — Rest is List after dropping the first N elements."""
    n_val, lst_val = deref(n), deref(lst)
    items = _as_items(lst_val)
    if isinstance(n_val, int) and items is not None:
        was_str = isinstance(lst_val, str)
        result = _seq_result(items[n_val:] if n_val >= 0 else items, was_str)
        mark = trail.mark()
        if unify(rest, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("split_at", 4)
def _split_at__4(this_generator, _proceed, _fail, _catcher, n, lst, left, right, trail):
    """split_at(N, List, Left, Right) — split List at index N."""
    n_val, lst_val = deref(n), deref(lst)
    items = _as_items(lst_val)
    if isinstance(n_val, int) and items is not None:
        was_str = isinstance(lst_val, str)
        idx = max(0, min(n_val, len(items)))
        l_out = _seq_result(items[:idx], was_str)
        r_out = _seq_result(items[idx:], was_str)
        mark = trail.mark()
        if unify(left, l_out, trail) and unify(right, r_out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("zip_", 3)
def _zip__3(this_generator, _proceed, _fail, _catcher, l1, l2, pairs, trail):
    """zip_(L1, L2, Pairs) — Pairs is a list of [X, Y] from L1 and L2."""
    l1_val, l2_val = deref(l1), deref(l2)
    l1_items = _as_items(l1_val)
    l2_items = _as_items(l2_val)
    if l1_items is not None and l2_items is not None:
        result = [[a, b] for a, b in zip(l1_items, l2_items)]
        mark = trail.mark()
        if unify(pairs, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("replicate", 3)
def _replicate__3(this_generator, _proceed, _fail, _catcher, n, elem, lst, trail):
    """replicate(N, Elem, List) — List is N copies of Elem."""
    n_val = deref(n)
    elem_val = deref(elem)
    if isinstance(n_val, int) and n_val >= 0:
        result = [elem_val] * n_val
        mark = trail.mark()
        if unify(lst, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("split_with", 3)
def _split_with__3(this_generator, _proceed, _fail, _catcher, sep, lst, parts, trail):
    """split_with(Sep, List, Parts) — split List by separator Sep into sublists.

    Modes:
      split_with(+Sep, +List, -Parts) — split
      split_with(+Sep, -List, +Parts) — join (flatten Parts interleaved with Sep)
    """
    sep_val = deref(sep)
    lst_val = deref(lst)
    parts_val = deref(parts)

    items = _as_items(lst_val)
    if items is not None:
        was_str = isinstance(lst_val, str)
        # Split mode
        result: list = [[]]
        for item in items:
            if deref(item) == sep_val:
                result.append([])
            else:
                result[-1].append(deref(item))
        if was_str:
            result = [_seq_result(part, True) for part in result]
        mark = trail.mark()
        if unify(parts, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif isinstance(parts_val, list):
        # Join mode: interleave parts with separator
        joined: list = []
        for i, part in enumerate(parts_val):
            p = deref(part)
            if isinstance(p, list):
                joined.extend(p)
            if i < len(parts_val) - 1:
                joined.append(sep_val)
        mark = trail.mark()
        if unify(lst, joined, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_builtin("numlist", 3)
def _numlist__3(low, high, lst, trail, k):
    """numlist(Low, High, List) — List is integers from Low to High inclusive."""
    low_val = deref(low)
    high_val = deref(high)
    if is_var(low_val) or is_var(high_val):
        return
    if not isinstance(low_val, int) or not isinstance(high_val, int):
        return
    if low_val > high_val:
        return
    result = list(range(low_val, high_val + 1))
    if unify(lst, result, trail):
        yield None


@_builtin("numlist", 2)
def _numlist__2(high, lst, trail, k):
    """numlist(High, List) — shorthand for numlist(1, High, List)."""
    high_val = deref(high)
    if is_var(high_val):
        return
    if not isinstance(high_val, int):
        return
    if high_val < 1:
        return
    result = list(range(1, high_val + 1))
    if unify(lst, result, trail):
        yield None


@_builtin("same_length", 2)
def _same_length__2(l1, l2, trail, k):
    """same_length(L1, L2) — true if L1 and L2 have the same length.

    If one is ground and the other unbound, generates a list of fresh Vars.
    """
    l1_val = deref(l1)
    l2_val = deref(l2)
    l1_is_seq = isinstance(l1_val, (list, str))
    l2_is_seq = isinstance(l2_val, (list, str))
    if l1_is_seq and l2_is_seq:
        if len(l1_val) == len(l2_val):
            yield None
    elif l1_is_seq and is_var(l2_val):
        generated = [Var() for _ in l1_val]
        if unify(l2, generated, trail):
            yield None
    elif l2_is_seq and is_var(l1_val):
        generated = [Var() for _ in l2_val]
        if unify(l1, generated, trail):
            yield None


@_builtin("transpose", 2)
def _transpose__2(matrix, transposed, trail, k):
    """transpose(Matrix, Transposed) — column-wise transposition of a list of lists."""
    mat = deref(matrix)
    if is_var(mat) or not isinstance(mat, list):
        return
    if len(mat) == 0:
        if unify(transposed, [], trail):
            yield None
        return
    # Verify all rows are lists (or strings) of the same length
    rows = []
    for row in mat:
        r = deref(row)
        items = _as_items(r)
        if items is None:
            return
        rows.append(items)
    if len(set(len(r) for r in rows)) != 1:
        return
    result = [list(col) for col in zip(*rows)]
    if unify(transposed, result, trail):
        yield None
