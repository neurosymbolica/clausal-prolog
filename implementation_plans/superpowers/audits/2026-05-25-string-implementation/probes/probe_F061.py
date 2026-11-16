"""Probe F061: C9 — every higher_order predicate silently fails on
ground SegList / SegString inputs (same root as [[F051]] but in
higher_order.py).

``higher_order.py`` reuses ``_as_items`` from ``lists.py`` to crack the
input collection.  ``_as_items`` accepts only ``list`` or ``str`` and
returns ``None`` for everything else (see [[F051]]).  Each higher_order
predicate gates on ``items is None`` and falls through to
``(_fail, DONE)``.

Affected predicates (every higher_order list predicate):
``maplist/2,3``, ``include/3``, ``exclude/3``, ``foldl/4``,
``partition/4``, ``take_while/3``, ``drop_while/3``, ``span/4``,
``group_by/3``, ``sort_by/3``, ``max_by/3``, ``min_by/3``,
``filter_map/3``, ``tfilter/3``, ``tpartition/4``.

This probe exercises a representative subset (maplist/2, include/3,
foldl/4, partition/4, group_by/3) and shows every Seg* call yields zero
solutions while the equivalent str / list calls succeed.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.terms import SegList, SegString, ConcreteSeg


SOURCE = """
-module(t, [is_vowel(_c), concat(_c, _a, _o), key_of(_c, _k)])
is_vowel(_c) <- in_(_c, ['a', 'e', 'i', 'o', 'u'])
concat(_c, _a, _o) <- atom_concat(_a, _c, _o)
key_of(_c, _k) <- If(in_(_c, ['a', 'e', 'i', 'o', 'u']), _k == 1, _k == 0)
"""


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
    print("Probe F061: C9 — higher_order predicates silently fail on Seg* inputs")
    mod = _load_inline_clausal(
        "probe_f061_seg_higher_order", SOURCE
    ).__dict__["$module"]

    sl = SegList([ConcreteSeg(["a", "e", "i"])])
    ss = SegString(["abc"])
    assert sl.is_ground() and sl.__walk__() == ["a", "e", "i"]
    assert ss.is_ground() and ss.__walk__() == "abc"

    is_vowel = mod.module_dict["is_vowel"]
    concat = mod.module_dict["concat"]
    key_of = mod.module_dict["key_of"]

    # Control: list/str inputs work.
    ok_list = any(True for _ in call("maplist", is_vowel, ["a", "e", "i"], module=mod))
    ok_str = any(True for _ in call("maplist", is_vowel, "aei", module=mod))
    print(f"  maplist/2(is_vowel, [a,e,i]):    {ok_list}")
    print(f"  maplist/2(is_vowel, 'aei'):      {ok_str}")

    # Seg* inputs silently fail.
    ok_sl = any(True for _ in call("maplist", is_vowel, sl, module=mod))
    ok_ss = any(True for _ in call("maplist", is_vowel, ss, module=mod))
    print(f"  maplist/2(is_vowel, SegList):    {ok_sl}   <- silent failure")
    print(f"  maplist/2(is_vowel, SegString):  {ok_ss}   <- silent failure")

    R = Var()
    n_sl_inc = sum(1 for _ in call("include", is_vowel, sl, R, module=mod))
    R = Var()
    n_ss_inc = sum(1 for _ in call("include", is_vowel, ss, R, module=mod))
    print(f"  include/3(is_vowel, SegList,   R):    {n_sl_inc} sols   <- silent failure")
    print(f"  include/3(is_vowel, SegString, R):    {n_ss_inc} sols   <- silent failure")

    R = Var()
    n_sl_fold = sum(1 for _ in call("foldl", concat, sl, "", R, module=mod))
    R = Var()
    n_ss_fold = sum(1 for _ in call("foldl", concat, ss, "", R, module=mod))
    print(f"  foldl/4(concat, SegList,   '', R):    {n_sl_fold} sols   <- silent failure")
    print(f"  foldl/4(concat, SegString, '', R):    {n_ss_fold} sols   <- silent failure")

    Y, N = Var(), Var()
    n_sl_par = sum(1 for _ in call("partition", is_vowel, sl, Y, N, module=mod))
    Y, N = Var(), Var()
    n_ss_par = sum(1 for _ in call("partition", is_vowel, ss, Y, N, module=mod))
    print(f"  partition/4(is_vowel, SegList,   Y, N): {n_sl_par} sols   <- silent failure")
    print(f"  partition/4(is_vowel, SegString, Y, N): {n_ss_par} sols   <- silent failure")

    R = Var()
    n_sl_grp = sum(1 for _ in call("group_by", key_of, sl, R, module=mod))
    R = Var()
    n_ss_grp = sum(1 for _ in call("group_by", key_of, ss, R, module=mod))
    print(f"  group_by/3(key_of, SegList,   R):     {n_sl_grp} sols   <- silent failure")
    print(f"  group_by/3(key_of, SegString, R):     {n_ss_grp} sols   <- silent failure")

    all_failed = (
        not ok_sl and not ok_ss
        and n_sl_inc == 0 and n_ss_inc == 0
        and n_sl_fold == 0 and n_ss_fold == 0
        and n_sl_par == 0 and n_ss_par == 0
        and n_sl_grp == 0 and n_ss_grp == 0
    )
    if all_failed and ok_list and ok_str:
        print("\n  Verdict: F061 CONFIRMED — every higher_order predicate "
              "silently drops Seg* inputs via _as_items.")
    else:
        print("\n  Verdict: F061 NOT confirmed; review _as_items use in higher_order.py.")


if __name__ == "__main__":
    main()
