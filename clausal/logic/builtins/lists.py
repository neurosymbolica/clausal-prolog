"""List builtins: in_/2, in_check/2, append/3, length/2, last/2, reverse/2,
list_item/3, flatten/2, msort/2, sort/2, permutation/2, select/3,
subtract/3, intersection/3, union/3, list_to_set/2, sum_list/2, max_list/2, min_list/2,
take/3, drop/3, split_at/4, zip_/3, replicate/3, split_with/3,
numlist/2,3, same_length/2, transpose/2."""

from __future__ import annotations

from typing import Any

from clausal.logic.atoms import char_atom, is_char_atom, spelling
from clausal.logic.variables import Var, deref, is_var, unify
from clausal.logic.trampoline import DONE

from clausal.logic.builtins._registry import _trampoline_builtin, _builtin
from clausal.logic.builtins._helpers import _standard_order_key, _standard_order_sorted

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

def _is_int(v) -> bool:
    """A09-F015 / A01-D001(c): a genuine int used as an index/count/length —
    a bool is NOT accepted (True is not 1) so length(L, True), list_item(True,
    …), take(True, …) etc. fail instead of silently treating True as 1."""
    return isinstance(v, int) and not isinstance(v, bool)


def _as_items(val):
    """Return list of elements if *val* is a sequence (list or str), else None.

    For strings, returns a list of CHARS (``char_atom``).

    F051/F061 (C9 audit): a *ground* ``SegList`` / ``SegString`` is
    walked to the concrete ``list`` / ``str`` it represents and then
    re-entered, so every gated builtin treats the Seg* like the
    sequence it walks to. A non-ground Seg* still returns ``None`` so
    the caller takes its usual "not a sequence" branch.
    """
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        return [char_atom(c) for c in val]
    if isinstance(val, bytes):
        # Codes model: a bytes is a list of int codes (list(b"abc") == [97,98,99]).
        return list(val)
    # Late import to avoid an import cycle (clausal.terms → clausal.logic
    # via Seg*.__walk__).
    from clausal.terms import SegList, SegString, SegBytes
    if isinstance(val, (SegList, SegString, SegBytes)) and val.is_ground():
        return _as_items(val.__walk__())
    return None


def _as_membership_items(val):
    """Membership domain for the dict/set collections the ``in`` OPERATOR
    already iterates (``_in_iter``'s ``iter()`` fallback): DictTerm / plain
    dict → keys, SetTerm / set / frozenset → elements, both in iteration
    order so ``in_/2`` enumerates exactly what ``X in C`` does. Returns None
    for anything else so ``in_/2``'s member/2 alias keeps its list-only
    contract for the remaining types."""
    from clausal.terms import DictTerm, SetTerm
    if isinstance(val, (DictTerm, dict, SetTerm, set, frozenset)):
        return list(val)
    return None


def _was_string(val):
    """Return True if *val* should be treated as str-shaped for output
    purposes.

    Used by every ``_seq_result``-consuming predicate to decide whether
    to promote a result of chars back to a ``str``. Recognises a
    plain ``str`` and a ground ``SegString`` that walks to one. Lists —
    including lists of chars — are *not* str-shaped under
    option A (input-type wins): list input keeps list output.
    """
    if isinstance(val, str):
        return True
    from clausal.terms import SegString
    if isinstance(val, SegString) and val.is_ground():
        return isinstance(val.__walk__(), str)
    return False


def _was_bytes(val):
    """Codes-model analog of :func:`_was_string`: True if *val* should be
    treated as bytes-shaped for output, so a result of int codes promotes back
    to a ``bytes`` object (input-type-wins). Recognises a plain ``bytes`` and a
    ground ``SegBytes`` that walks to one."""
    if isinstance(val, bytes):
        return True
    from clausal.terms import SegBytes
    if isinstance(val, SegBytes) and val.is_ground():
        return isinstance(val.__walk__(), bytes)
    return False


def _seq_result(items, was_string, was_bytes=False):
    """Reconstruct the input container type from a result of elements.

    When the input was a ``str`` and every result element is a CHAR,
    promote to ``str`` (joining the chars' spellings). When the input was a
    ``bytes`` and every result element is an int in ``[0, 255]`` (excluding
    ``bool``), promote to ``bytes`` (the codes model). Otherwise return the
    plain list (input-type-wins; a list input keeps a list output)."""
    if was_string and all(is_char_atom(c) for c in items):
        return "".join(spelling(c) for c in items)
    if was_bytes and all(
        isinstance(c, int) and not isinstance(c, bool) and 0 <= c <= 255
        for c in items
    ):
        return bytes(items)
    return items


@_trampoline_builtin("in_", 2)
def _member__2(this_generator, _proceed, _fail, _catcher, elem, lst, trail):
    """member(Elem, List) — Elem is a member of List; enumerates on backtrack.

    Also accepts the collections the ``in`` operator iterates (DictTerm/dict
    keys, SetTerm/set elements) so the predicate and operator spellings of
    membership agree."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is None:
        items = _as_membership_items(lst_val)
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
    """memberchk(Elem, List) — like member/2 but commits to the first match.

    Accepts the same dict/set collections as ``in_/2`` (see _member__2)."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is None:
        items = _as_membership_items(lst_val)
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
    # Track the result container type. str output when a str is present and no
    # list/bytes; bytes output (codes model) when a bytes is present and no
    # list/str. A list anywhere keeps a list (input-type-wins).
    _any_str = isinstance(l1_val, str) or isinstance(l2_val, str) or isinstance(l3_val, str)
    _any_bytes = isinstance(l1_val, bytes) or isinstance(l2_val, bytes) or isinstance(l3_val, bytes)
    _any_list = isinstance(l1_val, list) or isinstance(l2_val, list) or isinstance(l3_val, list)
    _out_str = _any_str and not _any_list and not _any_bytes
    _out_bytes = _any_bytes and not _any_list and not _any_str

    if l1_items is not None and l2_items is not None:
        # Both known: concatenate
        result = _seq_result(l1_items + l2_items, _out_str, _out_bytes)
        mark = trail.mark()
        if unify(l3, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif l1_items is not None and l3_items is not None:
        # L1 and L3 known: compute L2
        n = len(l1_items)
        if len(l3_items) >= n and l3_items[:n] == l1_items:
            remainder = _seq_result(l3_items[n:], _out_str, _out_bytes)
            mark = trail.mark()
            if unify(l2, remainder, trail):
                yield (_proceed, None)
            trail.undo(mark)
    elif l3_items is not None:
        # Only L3 known: enumerate all splits. The C accelerator only knows the
        # str promotion flag, so bytes output routes through the Python path.
        if _c_append_split_find is not None and not _out_bytes:
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
                prefix = _seq_result(l3_items[:i], _out_str, _out_bytes)
                suffix = _seq_result(l3_items[i:], _out_str, _out_bytes)
                mark = trail.mark()
                if unify(l1, prefix, trail) and unify(l2, suffix, trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("length", 2)
def _length__2(this_generator, _proceed, _fail, _catcher, lst, n, trail):
    """length(List, N) — N is the length of List.

    F051 (C9 audit): accepts ground SegList/SegString via ``_as_items``
    so a Seg* term reports the length of the sequence it walks to.
    """
    lst_val = deref(lst)
    n_val = deref(n)
    items = _as_items(lst_val)
    if items is not None:
        mark = trail.mark()
        if unify(n, len(items), trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif not is_var(n_val) and _is_int(n_val) and n_val >= 0:
        result = [Var() for _ in range(n_val)]
        mark = trail.mark()
        if unify(lst, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("last", 2)
def _last__2(this_generator, _proceed, _fail, _catcher, lst, elem, trail):
    """last(List, Elem) — Elem is the last element of List.

    F051 (C9 audit): accepts ground SegList/SegString via ``_as_items``.
    """
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None and len(items) > 0:
        mark = trail.mark()
        if unify(elem, items[-1], trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


def _reverse_dr__2(this_generator, _proceed, _fail, _catcher, lst, rev, trail):
    """Destructive-reuse variant of reverse/2.

    Forward mode over an unshared plain list: reverse it in place
    (``list.reverse``), no allocation.  Every other shape — shared list,
    str/bytes (immutable; the copying path preserves the sequence type),
    Seg*, backward mode — falls back to the standard implementation.
    Selected by the compiler's destructive-reuse analysis only when the
    source var is dead after the goal, unaliased with head vars, and the
    prefix is deterministic (see compiler/destructive_reuse.py); the
    refcount gate guards object-level sharing at run time, exactly as in
    ``_append_dr__3``.
    """
    lst_val = deref(lst)
    # Belt-and-braces beyond the compile-time analysis: mutate only in the
    # true forward OUTPUT mode (second arg an unbound var). A bound second
    # arg — the self-aliased reverse(L, L) palindrome idiom included — takes
    # the copying path, where unification gives the correct answer instead
    # of a vacuous self-unify against the mutated list (roborev job 18).
    if (_HAS_REFCOUNT and isinstance(lst_val, list)
            and is_var(deref(rev))
            and _sys.getrefcount(lst_val) <= 3):
        lst_val.reverse()
        mark = trail.mark()
        if unify(rev, lst_val, trail):
            yield (_proceed, None)
        trail.undo(mark)
        yield (_fail, DONE)
        return
    # Fallback to standard reverse
    yield from _reverse__2(this_generator, _proceed, _fail, _catcher, lst, rev, trail)


@_trampoline_builtin("reverse", 2)
def _reverse__2(this_generator, _proceed, _fail, _catcher, lst, rev, trail):
    """reverse(List, Rev) — Rev is the reverse of List.

    Bidirectional: if the first arg is a usable sequence we reverse it into the
    second (forward mode); otherwise, if the second arg is a usable sequence we
    reverse it into the first (backward mode, e.g. ``reverse(L, [3,2,1])``).
    Both-ground calls verify via the forward branch. Both-unbound is not
    enumerated (yields no solution).

    F051 (C9 audit): accepts ground SegList/SegString via ``_as_items``.
    """
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        result = _seq_result(list(reversed(items)), was_str, was_bytes)
        mark = trail.mark()
        if unify(rev, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    else:
        # Backward mode: first arg not a usable sequence (e.g. unbound Var);
        # reverse the second arg into it. Mirrors the forward branch, preserving
        # the str/bytes seq-result contract from the *second* arg's shape.
        rev_val = deref(rev)
        rev_items = _as_items(rev_val)
        if rev_items is not None:
            was_str = _was_string(rev_val)
            was_bytes = _was_bytes(rev_val)
            result = _seq_result(list(reversed(rev_items)), was_str, was_bytes)
            mark = trail.mark()
            if unify(lst, result, trail):
                yield (_proceed, None)
            trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("list_item", 3)
def _nth0__3(this_generator, _proceed, _fail, _catcher, n, lst, elem, trail):
    """list_item(N, List, Elem) — Elem is the N-th element of List (0-based).

    Renamed from ``get_item/3`` per user decision 2026-06-13: the old
    name was deemed too procedural. ``list_item`` is the Pythonic /
    Clausal-named 0-based positional accessor; it is distinct from
    ISO-named ``arg/3`` which follows cons-cell head/tail semantics.
    """
    n_val = deref(n)
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        if not is_var(n_val):
            if _is_int(n_val) and 0 <= n_val < len(items):
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

    F056 (C9 audit): under the strings-as-lists contract, ``['ab']``
    and ``[['a','b']]`` are equivalent values, so ``flatten`` must
    treat a nested ``str`` (or ground ``SegString``) like a list of
    1-char strs and recurse through it. The top-level container is
    *not* recursed into — flattening ``'abc'`` returns ``['abc']`` for
    the same reason a 1-element atom flattens to its 1-element
    wrapper.
    """
    lst_val = deref(lst)
    if not is_var(lst_val):
        result: list = []
        outer = True

        def _do_flat(x: Any) -> None:
            nonlocal outer
            x = deref(x)
            if isinstance(x, list):
                for item in x:
                    outer = False
                    _do_flat(item)
            elif not outer and isinstance(x, str):
                # F056: nested str is recursed-into per the
                # strings-as-lists equivalence; the top-level str case
                # is handled by the early-return below the recursion.
                # Its elements are CHARS, like every other str→list split.
                for ch in x:
                    result.append(char_atom(ch))
            else:
                # Ground Seg* walk to their concrete shape; reuse the
                # _as_items helper for the Seg* recurse-or-atom decision.
                items = _as_items(x) if not outer else None
                if items is not None:
                    for item in items:
                        _do_flat(item)
                else:
                    result.append(x)

        # Top-level: if the whole input is a non-list (str, atom, Seg*),
        # the canonical flatten result is a single-element list
        # containing the input (matching Prolog's flatten/2 contract).
        if isinstance(lst_val, list):
            outer = False
            _do_flat(lst_val)
        else:
            result.append(lst_val)
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
        items = [deref(x) for x in items]
        result = _standard_order_sorted(items)
        out = _seq_result(result, _was_string(lst_val), _was_bytes(lst_val))
        mark = trail.mark()
        if unify(sorted_lst, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("sort", 2)
def _sort__2(this_generator, _proceed, _fail, _catcher, lst, sorted_lst, trail):
    """sort(List, Sorted) — Sorted is List sorted with duplicates removed.

    THE FLIP (spec §6.5): duplicates are decided by STANDARD-ORDER KEY
    equality, not by Python ``==``.  A string and the list of its char atoms
    are the same term (``"ab"`` and ``[a, b]``) but are not ``==``, so a
    ``==``-based dedup would leave both in a sorted set that is supposed to
    hold each term once.  The FIRST occurrence survives, as it did before.
    ``msort/2`` keeps every element and is unaffected.

    The seen-set is a SET of keys, not a list: a standard-order key is a
    tuple of hashables in every band but ``_ORD_OTHER``, so ``sort/2`` is
    linear rather than the quadratic scan a list of keys costs (2000
    distinct elements is 2 million tuple comparisons).  The one exception is
    ``_helpers._OpaqueOrder`` — it defines ``__eq__`` and no ``__hash__``, so
    a key holding one is unhashable; those keys, and only those, fall back to
    the list.  The two pools never have to be compared against each other:
    ``_OpaqueOrder`` answers ``NotImplemented`` to anything that is not an
    ``_OpaqueOrder``, and its band tag differs from every other band's, so an
    unhashable key can only ever equal another unhashable key.
    """
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        items = [deref(x) for x in items]
        seen: list = []
        hashable_keys: set = set()
        opaque_keys: list = []
        for x in items:
            key = _standard_order_key(x)
            try:
                duplicate = key in hashable_keys
                if not duplicate:
                    hashable_keys.add(key)
            except TypeError:
                duplicate = key in opaque_keys
                if not duplicate:
                    opaque_keys.append(key)
            if not duplicate:
                seen.append(x)
        result = _standard_order_sorted(seen)
        out = _seq_result(result, _was_string(lst_val), _was_bytes(lst_val))
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
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        if _c_permutation_find is not None and not was_bytes:
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
                if unify(perm, _seq_result(list(p), was_str, was_bytes), trail):
                    yield (_proceed, None)
                trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("select", 3)
def _select__3(this_generator, _proceed, _fail, _catcher, elem, lst, rest, trail):
    """select(Elem, List, Rest) — Elem is in List, Rest is List without one occurrence."""
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        if _c_select_find is not None and not was_bytes:
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
                remainder = _seq_result(items[:i] + items[i + 1:], was_str, was_bytes)
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
        _out_bytes = isinstance(s1, bytes) and isinstance(s2, bytes)
        result = _seq_result([x for x in s1_items if x not in s2_items], _out_str, _out_bytes)
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
        _out_bytes = isinstance(s1, bytes) and isinstance(s2, bytes)
        result = _seq_result([x for x in s1_items if x in s2_items], _out_str, _out_bytes)
        mark = trail.mark()
        if unify(inter, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("union", 3)
def _union__3(this_generator, _proceed, _fail, _catcher, set1, set2, uni, trail):
    """union(Set1, Set2, Union) — Union is Set1 followed by the elements of
    Set2 not already in Set1 (SWI-consistent). Set1's OWN duplicates are
    preserved (``union([1,1],[],U)`` = ``[1,1]``); only elements of Set2 that
    already occur in Set1 are dropped. Use list_to_set/2 first for a true set.
    """
    s1 = deref(set1)
    s2 = deref(set2)
    s1_items = _as_items(s1)
    s2_items = _as_items(s2)
    if s1_items is not None and s2_items is not None:
        _out_str = isinstance(s1, str) and isinstance(s2, str)
        _out_bytes = isinstance(s1, bytes) and isinstance(s2, bytes)
        result = list(s1_items)
        for x in s2_items:
            if x not in result:
                result.append(x)
        out = _seq_result(result, _out_str, _out_bytes)
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
        items = [deref(x) for x in items]
        seen: list = []
        for x in items:
            if x not in seen:
                seen.append(x)
        out = _seq_result(seen, _was_string(lst_val), _was_bytes(lst_val))
        mark = trail.mark()
        if unify(set_out, out, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("sum_list", 2)
def _sum_list__2(this_generator, _proceed, _fail, _catcher, lst, total, trail):
    """sum_list(List, Total) — Total is the sum of all numbers in List.

    F052 (C9 audit): a TypeError from ``sum(...)`` (e.g. ``sum_list("abc",
    S)`` where the elements are not summable) is raised as a typed
    ``type_error(number, …)`` clausal exception rather than silently
    converted to ``(_fail, DONE)`` — silent failure is
    indistinguishable from the legitimate "the list is empty" result.
    """
    from clausal.logic.exceptions import LogicException, type_error
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None:
        from clausal.terms import Quantity                    # noqa: PLC0415

        def _summable(v):
            return (isinstance(v, Quantity)
                    or (isinstance(v, (int, float))
                        and not isinstance(v, bool)))

        values = [deref(x) for x in items]
        offender = next((v for v in values if not _summable(v)), None)
        if offender is not None:
            raise LogicException(
                type_error("number", offender, "sum_list/2"))
        try:
            # Seeded from the FIRST element, not from a bare 0: `sum()` starts
            # at 0, and `0 + Quantity` is a plain number meeting a dimensioned
            # one, so a list of money used to raise rather than total. The
            # empty list still gives 0, every plain list is unchanged, and a
            # list mixing currencies — or mixing money with a bare number —
            # still raises UnitsMismatch, which is the property that makes
            # uniting an invoice's totals worth doing.
            s = 0
            if values:
                s = values[0]
                for v in values[1:]:
                    s = s + v
        except TypeError as exc:
            raise LogicException(
                type_error("number", values[0] if values else None,
                           "sum_list/2")
            ) from exc
        mark = trail.mark()
        if unify(total, s, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("max_list", 2)
def _max_list__2(this_generator, _proceed, _fail, _catcher, lst, maximum, trail):
    """max_list(List, max_) — max_ is the maximum element of List.

    F052 (C9 audit): a TypeError from ``max(...)`` (e.g. mixed
    incomparable types) is raised as a typed clausal exception rather
    than silently converted to ``(_fail, DONE)``.
    """
    from clausal.logic.exceptions import LogicException, type_error
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None and len(items) > 0:
        try:
            m = max(deref(x) for x in items)
        except TypeError as exc:
            raise LogicException(
                type_error("orderable", lst_val, "max_list/2")
            ) from exc
        mark = trail.mark()
        if unify(maximum, m, trail):
            yield (_proceed, None)
        trail.undo(mark)
    yield (_fail, DONE)


@_trampoline_builtin("min_list", 2)
def _min_list__2(this_generator, _proceed, _fail, _catcher, lst, minimum, trail):
    """min_list(List, min_) — min_ is the minimum element of List.

    F052 (C9 audit): a TypeError from ``min(...)`` is raised as a typed
    clausal exception rather than silently converted to ``(_fail,
    DONE)``.
    """
    from clausal.logic.exceptions import LogicException, type_error
    lst_val = deref(lst)
    items = _as_items(lst_val)
    if items is not None and len(items) > 0:
        try:
            m = min(deref(x) for x in items)
        except TypeError as exc:
            raise LogicException(
                type_error("orderable", lst_val, "min_list/2")
            ) from exc
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
    if _is_int(n_val) and items is not None:
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        result = _seq_result(items[:n_val] if n_val >= 0 else [], was_str, was_bytes)
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
    if _is_int(n_val) and items is not None:
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        result = _seq_result(items[n_val:] if n_val >= 0 else items, was_str, was_bytes)
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
    if _is_int(n_val) and items is not None:
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        idx = max(0, min(n_val, len(items)))
        l_out = _seq_result(items[:idx], was_str, was_bytes)
        r_out = _seq_result(items[idx:], was_str, was_bytes)
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
    """replicate(N, Elem, List) — List is N copies of Elem.

    F053 (C9 audit, option A — input-type wins): when ``Elem`` is a
    CHAR, build the result as a ``str`` (e.g. ``replicate(5,
    'a', R)`` → ``R = 'aaaaa'``). The char element gives the
    builder the type hint it needs to pick the str shape, matching the
    string-preserving contract followed by the rest of the family.
    """
    n_val = deref(n)
    elem_val = deref(elem)
    if isinstance(n_val, int) and n_val >= 0:
        if is_char_atom(elem_val):
            result = spelling(elem_val) * n_val
        else:
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
        was_str = _was_string(lst_val)
        was_bytes = _was_bytes(lst_val)
        # Split mode
        result: list = [[]]
        for item in items:
            if deref(item) == sep_val:
                result.append([])
            else:
                result[-1].append(deref(item))
        if was_str:
            result = [_seq_result(part, True) for part in result]
        elif was_bytes:
            result = [_seq_result(part, False, True) for part in result]
        mark = trail.mark()
        if unify(parts, result, trail):
            yield (_proceed, None)
        trail.undo(mark)
    elif isinstance(parts_val, list):
        # Join mode: interleave parts with separator.
        # F050 (C9 audit): str parts are the natural inverse of the
        # split direction (which emits str parts when the input was a
        # str). Widen the recurse-into-part test to ``_as_items`` so
        # str / list / ground Seg* parts all contribute their elements
        # to the joined output, rather than the bug-shape "only
        # separators survive".
        joined: list = []
        for i, part in enumerate(parts_val):
            p = deref(part)
            p_items = _as_items(p)
            if p_items is not None:
                joined.extend(p_items)
            else:
                # Non-sequence part — treat as a single element.
                joined.append(p)
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
    if not _is_int(low_val) or not _is_int(high_val):
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
    if not _is_int(high_val):
        return
    if high_val < 1:
        return
    result = list(range(1, high_val + 1))
    if unify(lst, result, trail):
        yield None


def _fresh_same_shape(seq_val):
    """Return a fresh sequence of N elements matching ``seq_val``'s shape.

    F053 (C9 audit, option A — input-type wins): when the sibling value
    is a ``str`` (or a ground ``SegString``), build a fresh
    ``SegString`` of N ``VarSeg`` holes so the generated placeholder is
    *str-shaped* rather than a Python list. Otherwise generate the
    classic list of fresh ``Var`` objects.
    """
    from clausal.terms import SegString, SegBytes, VarSeg
    if isinstance(seq_val, str):
        return SegString([VarSeg(Var()) for _ in seq_val])
    if isinstance(seq_val, SegString) and seq_val.is_ground():
        return SegString([VarSeg(Var()) for _ in seq_val.__walk__()])
    if isinstance(seq_val, bytes):
        return SegBytes([VarSeg(Var()) for _ in seq_val])
    if isinstance(seq_val, SegBytes) and seq_val.is_ground():
        return SegBytes([VarSeg(Var()) for _ in seq_val.__walk__()])
    return [Var() for _ in seq_val]


@_builtin("same_length", 2)
def _same_length__2(l1, l2, trail, k):
    """same_length(L1, L2) — true if L1 and L2 have the same length.

    F053 (C9 audit, option A — input-type wins): if one side is a
    ``str`` (or ground ``SegString``) and the other is unbound, the
    generated placeholder is a ``SegString`` of fresh ``VarSeg`` holes
    (str-shaped); a ``bytes`` (or ground ``SegBytes``) sibling yields a
    ``SegBytes`` of fresh holes (bytes-shaped, codes model); for a
    ``list`` sibling the placeholder is the classic list of fresh
    ``Var`` objects.
    """
    from clausal.logic.runtime._seg_helpers import normalize_seg_input
    # F019: walk ground SegList / SegString / SegBytes to their concrete
    # shape so the seq/placeholder arms below (and _fresh_same_shape's Seg*
    # branches) fire — the raw isinstance check rejected ground Seg* even
    # though the docstring and _fresh_same_shape promise support.
    l1_val = normalize_seg_input(deref(l1))
    l2_val = normalize_seg_input(deref(l2))
    l1_is_seq = isinstance(l1_val, (list, str, bytes))
    l2_is_seq = isinstance(l2_val, (list, str, bytes))
    if l1_is_seq and l2_is_seq:
        if len(l1_val) == len(l2_val):
            yield None
    elif l1_is_seq and is_var(l2_val):
        if unify(l2, _fresh_same_shape(l1_val), trail):
            yield None
    elif l2_is_seq and is_var(l1_val):
        if unify(l1, _fresh_same_shape(l2_val), trail):
            yield None


@_builtin("transpose", 2)
def _transpose__2(matrix, transposed, trail, k):
    """transpose(Matrix, Transposed) — column-wise transposition of a list of lists.

    F055 (C9 audit): the outer matrix may be a ``list``, a ``str`` (read
    as a 1-row matrix of 1-char-str cells via ``_as_items``), or a
    ground Seg* that walks to either. Inner rows continue to go through
    ``_as_items`` so list-of-str matrices still transpose correctly.
    """
    mat = deref(matrix)
    outer_items = _as_items(mat)
    if outer_items is None:
        return
    if len(outer_items) == 0:
        if unify(transposed, [], trail):
            yield None
        return
    # Verify all rows are lists (or strings) of the same length
    rows = []
    for row in outer_items:
        r = deref(row)
        items = _as_items(r)
        if items is None:
            # A non-sequence row (e.g. an int) is treated as a single-cell
            # row. This does NOT fire for str rows: _as_items("a") is ['a'],
            # so transpose("ab") reads two 1-char rows and yields the single
            # column [['a', 'b']] (F024: not [['a'], ['b']]).
            items = [r]
        rows.append(items)
    if len(set(len(r) for r in rows)) != 1:
        return
    result = [list(col) for col in zip(*rows)]
    if unify(transposed, result, trail):
        yield None
