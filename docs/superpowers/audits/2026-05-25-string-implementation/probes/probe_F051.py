"""Probe F051: C9 — every polymorphic list builtin silently fails on
ground SegList / SegString inputs.

The helper ``_as_items`` (lists.py:48-57) accepts only ``list`` or
``str`` and returns ``None`` otherwise.  Every polymorphic predicate
gates its work on ``items is not None`` and falls through to ``(_fail,
DONE)`` when the input is anything else.

Ground ``SegList(ConcreteSeg(...))`` and ``SegString([...])`` are
*logically* equivalent to a list/str under the strings-as-lists +
SegList contracts.  They walk to a concrete list / str via
``__walk__``.  But ``_as_items`` doesn't try ``__walk__``, so each of
the following builtins silently yields zero solutions on a Seg* input:
append, length, member (``in_``), reverse, nth (``get_item``), take,
drop, split_at, msort, sort, last, select, permutation, flatten,
subtract, intersection, union, list_to_set, sum_list, max_list,
min_list, zip_, split_with, same_length.

This probe demonstrates the silent-failure on a representative subset
(append, length, member, reverse, take, msort, select, get_item).
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import SegList, SegString, ConcreteSeg


def _load_inline_clausal(name: str, source: str):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def main() -> None:
    print("Probe F051: C9 — polymorphic builtins silently fail on Seg* inputs")
    mod = _load_inline_clausal(
        "probe_f051_seg_builtins", "-module(t, [])\n"
    ).__dict__["$module"]

    sl = SegList([ConcreteSeg(["a", "b", "c"])])
    ss = SegString(["abc"])
    assert sl.is_ground() and sl.__walk__() == ["a", "b", "c"]
    assert ss.is_ground() and ss.__walk__() == "abc"

    # Controls: same logical values as list / str succeed.
    R = Var()
    n_list_append = sum(1 for _ in call("append", ["a", "b", "c"], "d", R, module=mod))
    R = Var()
    n_str_append = sum(1 for _ in call("append", "abc", "d", R, module=mod))

    R = Var()
    n_sl_append = sum(1 for _ in call("append", sl, "d", R, module=mod))
    R = Var()
    n_ss_append = sum(1 for _ in call("append", ss, "d", R, module=mod))

    print(f"  append([a,b,c], d, R):        {n_list_append} solutions")
    print(f"  append('abc',   d, R):        {n_str_append} solutions")
    print(f"  append(SegList, d, R):        {n_sl_append} solutions   ← silent failure")
    print(f"  append(SegString, d, R):      {n_ss_append} solutions   ← silent failure")

    V = Var()
    n_list_in = sum(1 for _ in call("in_", V, ["a", "b", "c"], module=mod))
    V = Var()
    n_sl_in = sum(1 for _ in call("in_", V, sl, module=mod))
    V = Var()
    n_ss_in = sum(1 for _ in call("in_", V, ss, module=mod))
    print(f"  in_(V, [a,b,c]):              {n_list_in} solutions")
    print(f"  in_(V, SegList):              {n_sl_in} solutions   ← silent failure")
    print(f"  in_(V, SegString):            {n_ss_in} solutions   ← silent failure")

    N = Var()
    n_sl_len = sum(1 for _ in call("length", sl, N, module=mod))
    N = Var()
    n_ss_len = sum(1 for _ in call("length", ss, N, module=mod))
    print(f"  length(SegList,   N):         {n_sl_len} solutions   ← silent failure")
    print(f"  length(SegString, N):         {n_ss_len} solutions   ← silent failure")

    R = Var()
    n_sl_rev = sum(1 for _ in call("reverse", sl, R, module=mod))
    R = Var()
    n_ss_rev = sum(1 for _ in call("reverse", ss, R, module=mod))
    print(f"  reverse(SegList,   R):        {n_sl_rev} solutions   ← silent failure")
    print(f"  reverse(SegString, R):        {n_ss_rev} solutions   ← silent failure")

    T = Var()
    n_sl_take = sum(1 for _ in call("take", 2, sl, T, module=mod))
    T = Var()
    n_ss_take = sum(1 for _ in call("take", 2, ss, T, module=mod))
    print(f"  take(2, SegList,   T):        {n_sl_take} solutions   ← silent failure")
    print(f"  take(2, SegString, T):        {n_ss_take} solutions   ← silent failure")

    M = Var()
    n_sl_msort = sum(1 for _ in call("msort", sl, M, module=mod))
    print(f"  msort(SegList, M):            {n_sl_msort} solutions   ← silent failure")

    E, S = Var(), Var()
    n_sl_select = sum(1 for _ in call("select", E, sl, S, module=mod))
    print(f"  select(E, SegList, S):        {n_sl_select} solutions   ← silent failure")

    E = Var()
    n_sl_get = sum(1 for _ in call("get_item", 1, sl, E, module=mod))
    print(f"  get_item(1, SegList, E):      {n_sl_get} solutions   ← silent failure")

    all_failed = (n_sl_append == 0 and n_ss_append == 0
                  and n_sl_in == 0 and n_ss_in == 0
                  and n_sl_len == 0 and n_ss_len == 0)
    if all_failed and n_list_append > 0 and n_str_append > 0:
        print("\n  Verdict: F051 CONFIRMED — Seg* inputs are silently dropped "
              "by every _as_items-gated builtin.")
    else:
        print("\n  Verdict: F051 NOT confirmed; review _as_items.")


if __name__ == "__main__":
    main()
