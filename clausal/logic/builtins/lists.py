"""List builtins: In/2, InCheck/2, Append/3, Length/2, Last/2, Reverse/2,
GetItem/3, Flatten/2, MergeSort/2, Sort/2, Permutation/2, Select/3,
Subtract/3, Intersection/3, Union/3, ToSet/2, SumList/2, MaxList/2, MinList/2."""

from __future__ import annotations

from typing import Any

from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE

from clausal.logic.builtins._registry import _trampoline_builtin


@_trampoline_builtin("In", 2)
def _member__2(this_generator, parent, elem, lst, trail):
    """member(Elem, List) — Elem is a member of List; enumerates on backtrack."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for item in lst_val:
            mark = trail.mark()
            if unify(elem, item, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("InCheck", 2)
def _memberchk__2(this_generator, parent, elem, lst, trail):
    """memberchk(Elem, List) — like member/2 but commits to the first match."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for item in lst_val:
            mark = trail.mark()
            if unify(elem, item, trail):
                yield (parent, None)
                yield (parent, DONE)
                return
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Append", 3)
def _append__3(this_generator, parent, l1, l2, l3, trail):
    """append(L1, L2, L3) — L3 is the concatenation of L1 and L2.

    Modes:
      append(+, +, -) — deterministic concatenation
      append(+, -, +) — split L3 starting from L1
      append(-, -, +) — enumerate all splits of L3
    """
    l1_val = deref(l1)
    l2_val = deref(l2)
    l3_val = deref(l3)

    if isinstance(l1_val, list) and isinstance(l2_val, list):
        # Both known: concatenate
        mark = trail.mark()
        if unify(l3, l1_val + l2_val, trail):
            yield (parent, None)
        trail.undo(mark)
    elif isinstance(l1_val, list) and isinstance(l3_val, list):
        # L1 and L3 known: compute L2
        n = len(l1_val)
        if len(l3_val) >= n and l3_val[:n] == l1_val:
            mark = trail.mark()
            if unify(l2, l3_val[n:], trail):
                yield (parent, None)
            trail.undo(mark)
    elif isinstance(l3_val, list):
        # Only L3 known: enumerate all splits
        for i in range(len(l3_val) + 1):
            mark = trail.mark()
            if unify(l1, l3_val[:i], trail) and unify(l2, l3_val[i:], trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Length", 2)
def _length__2(this_generator, parent, lst, n, trail):
    """length(List, N) — N is the length of List."""
    lst_val = deref(lst)
    n_val = deref(n)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(n, len(lst_val), trail):
            yield (parent, None)
        trail.undo(mark)
    elif not is_var(n_val) and isinstance(n_val, int) and n_val >= 0:
        result = [Var() for _ in range(n_val)]
        mark = trail.mark()
        if unify(lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Last", 2)
def _last__2(this_generator, parent, lst, elem, trail):
    """last(List, Elem) — Elem is the last element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        mark = trail.mark()
        if unify(elem, lst_val[-1], trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Reverse", 2)
def _reverse__2(this_generator, parent, lst, rev, trail):
    """reverse(List, Rev) — Rev is the reverse of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        mark = trail.mark()
        if unify(rev, list(reversed(lst_val)), trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("GetItem", 3)
def _nth0__3(this_generator, parent, n, lst, elem, trail):
    """nth0(N, List, Elem) — Elem is the N-th element of List (0-based)."""
    n_val = deref(n)
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        if not is_var(n_val):
            if isinstance(n_val, int) and 0 <= n_val < len(lst_val):
                mark = trail.mark()
                if unify(elem, lst_val[n_val], trail):
                    yield (parent, None)
                trail.undo(mark)
        else:
            for i, item in enumerate(lst_val):
                mark = trail.mark()
                if unify(n, i, trail) and unify(elem, item, trail):
                    yield (parent, None)
                trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Flatten", 2)
def _flatten__2(this_generator, parent, lst, flat, trail):
    """flatten(List, Flat) — Flat is the flat list of all atoms in List."""
    lst_val = deref(lst)
    if not is_var(lst_val):
        result: list = []

        def _do_flat(x: Any) -> None:
            x = deref(x)
            if isinstance(x, list):
                for item in x:
                    _do_flat(item)
            else:
                result.append(x)

        _do_flat(lst_val)
        mark = trail.mark()
        if unify(flat, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MergeSort", 2)
def _msort__2(this_generator, parent, lst, sorted_lst, trail):
    """msort(List, Sorted) — Sorted is List sorted, preserving duplicates."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        try:
            result = sorted(lst_val)
        except TypeError:
            result = sorted(lst_val, key=lambda x: (type(x).__name__, repr(x)))
        mark = trail.mark()
        if unify(sorted_lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Sort", 2)
def _sort__2(this_generator, parent, lst, sorted_lst, trail):
    """sort(List, Sorted) — Sorted is List sorted with duplicates removed."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        seen: list = []
        for x in lst_val:
            if x not in seen:
                seen.append(x)
        try:
            result = sorted(seen)
        except TypeError:
            result = sorted(seen, key=lambda x: (type(x).__name__, repr(x)))
        mark = trail.mark()
        if unify(sorted_lst, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Permutation", 2)
def _permutation__2(this_generator, parent, lst, perm, trail):
    """permutation(List, Perm) — Perm is a permutation of List."""
    import itertools
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for p in itertools.permutations(lst_val):
            mark = trail.mark()
            if unify(perm, list(p), trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Select", 3)
def _select__3(this_generator, parent, elem, lst, rest, trail):
    """select(Elem, List, Rest) — Elem is in List, Rest is List without one occurrence."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        for i, item in enumerate(lst_val):
            mark = trail.mark()
            remainder = lst_val[:i] + lst_val[i + 1:]
            if unify(elem, item, trail) and unify(rest, remainder, trail):
                yield (parent, None)
            trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Subtract", 3)
def _subtract__3(this_generator, parent, set1, set2, diff, trail):
    """subtract(Set1, Set2, Diff) — Diff is Set1 minus elements in Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = [x for x in s1 if x not in s2]
        mark = trail.mark()
        if unify(diff, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Intersection", 3)
def _intersection__3(this_generator, parent, set1, set2, inter, trail):
    """intersection(Set1, Set2, Inter) — Inter is the intersection of Set1 and Set2."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = [x for x in s1 if x in s2]
        mark = trail.mark()
        if unify(inter, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("Union", 3)
def _union__3(this_generator, parent, set1, set2, uni, trail):
    """union(Set1, Set2, Union) — Union is Set1 ∪ Set2 (no duplicates)."""
    s1 = deref(set1)
    s2 = deref(set2)
    if isinstance(s1, list) and isinstance(s2, list):
        result = list(s1)
        for x in s2:
            if x not in result:
                result.append(x)
        mark = trail.mark()
        if unify(uni, result, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("ToSet", 2)
def _list_to_set__2(this_generator, parent, lst, set_out, trail):
    """list_to_set(List, Set) — Set is List with duplicates removed (order preserved)."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        seen: list = []
        for x in lst_val:
            if x not in seen:
                seen.append(x)
        mark = trail.mark()
        if unify(set_out, seen, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("SumList", 2)
def _sum_list__2(this_generator, parent, lst, total, trail):
    """sum_list(List, Total) — Total is the sum of all numbers in List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list):
        try:
            s = sum(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(total, s, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MaxList", 2)
def _max_list__2(this_generator, parent, lst, maximum, trail):
    """max_list(List, Max) — Max is the maximum element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        try:
            m = max(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(maximum, m, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)


@_trampoline_builtin("MinList", 2)
def _min_list__2(this_generator, parent, lst, minimum, trail):
    """min_list(List, Min) — Min is the minimum element of List."""
    lst_val = deref(lst)
    if isinstance(lst_val, list) and len(lst_val) > 0:
        try:
            m = min(deref(x) for x in lst_val)
        except TypeError:
            yield (parent, DONE)
            return
        mark = trail.mark()
        if unify(minimum, m, trail):
            yield (parent, None)
        trail.undo(mark)
    yield (parent, DONE)
