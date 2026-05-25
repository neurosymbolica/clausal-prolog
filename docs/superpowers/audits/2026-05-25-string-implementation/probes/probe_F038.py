"""Probe F038: _in_iter raises on ground SegString (no __iter__ defined).

body_star_unify.py:208-217 — ``_in_iter(collection, pair_mode)``
returns ``iter(collection)`` for the non-DictTerm branch. ``SegString``
does not define ``__iter__`` (and is not a ``str`` subclass), so even a
trivially-ground ``SegString(["abc"])`` raises ``TypeError: 'SegString'
object is not iterable`` when used in a body-position ``elem in coll``
goal.

By contrast, ``SegList`` defines ``__iter__`` (terms.py:337) which
delegates to ``to_list()`` — for a ground SegList this returns the
walked list correctly. The asymmetry is the C3 SegString blind spot
again.

Severity: bug — silent TypeError on a logically-valid membership goal
against a ground SegString-bound collection. Per spec vocabulary,
"TypeError on a logically-valid call = bug".

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F038.py
"""
from clausal.logic.runtime.body_star_unify import _in_iter
from clausal.terms import SegString, SegList, ConcreteSeg


def main() -> None:
    print("Probe F038: _in_iter raises on ground SegString")

    # Ground SegList: works.
    sl = SegList([ConcreteSeg([1, 2, 3])])
    try:
        items = list(_in_iter(sl, pair_mode=False))
        print(f"  ground SegList: {items!r}")
    except Exception as e:
        print(f"  ground SegList raised {type(e).__name__}: {e}")

    # Plain str: works.
    print(f"  plain 'abc':    {list(_in_iter('abc', pair_mode=False))!r}")

    # Ground SegString: raises.
    ss = SegString(["abc"])
    print(f"  ground SegString.is_ground() = {ss.is_ground()}, "
          f"walks to {ss.__walk__()!r}")
    try:
        items = list(_in_iter(ss, pair_mode=False))
        print(f"  ground SegString: {items!r}")
    except Exception as e:
        print(f"  ground SegString raised {type(e).__name__}: {e}")

    print()
    print("  Expected: ['a', 'b', 'c'] (parallel to ground SegList).")
    print("  Actual:   TypeError — SegString has no __iter__ and is not a str.")


if __name__ == "__main__":
    main()
