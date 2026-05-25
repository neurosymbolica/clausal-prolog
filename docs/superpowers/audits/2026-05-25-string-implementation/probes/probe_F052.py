"""Probe F052: C9 — sum_list/max_list/min_list silently fail on
non-numeric str input.

``sum_list/max_list/min_list`` accept any sequence via ``_as_items``,
but the inner ``sum/max/min(deref(x) for x in items)`` raises TypeError
when items are str chars (str + str works but ``sum(str, 0)`` does not;
``max/min`` work).  The TypeError is caught and converted to
``(_fail, DONE)`` — the goal yields zero solutions silently.

For ``sum_list``, this masks the type error: ``sum_list("abc", S)``
appears to fail logically when actually the predicate is undefined on
str chars.  ``max_list("abc", S)`` succeeds because str supports
ordering.

The expected behaviour depends on the contract: either (a) the
predicate should be undefined for str input and raise an error rather
than silently fail, or (b) sum should mean "string concatenation" for
str input — but currently neither holds.
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


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
    print("Probe F052: C9 — sum_list silently fails on str input")
    mod = _load_inline_clausal(
        "probe_f052_sum_list", "-module(t, [])\n"
    ).__dict__["$module"]

    # sum_list on numeric list — works.
    S = Var()
    results = []
    for _ in call("sum_list", [1, 2, 3], S, module=mod):
        results.append(deref(S))
    print(f"  sum_list([1,2,3], S):    {results} (control, expected [6])")

    # sum_list on str — silently fails.
    S = Var()
    n_str = sum(1 for _ in call("sum_list", "abc", S, module=mod))
    print(f"  sum_list('abc',  S):     {n_str} solutions  ← silent failure")

    # sum_list on list of chars — also silently fails (same TypeError path).
    S = Var()
    n_chars = sum(1 for _ in call("sum_list", ["a", "b", "c"], S, module=mod))
    print(f"  sum_list(['a','b','c'], S):  {n_chars} solutions  ← silent failure")

    # max_list / min_list on str — succeeds (chars are orderable).
    M = Var()
    for _ in call("max_list", "abc", M, module=mod):
        print(f"  max_list('abc', M):      M = {deref(M)!r}  (works)")
        break
    M = Var()
    for _ in call("min_list", "abc", M, module=mod):
        print(f"  min_list('abc', M):      M = {deref(M)!r}  (works)")
        break

    # max_list on a mixed list (int + str) — TypeError swallowed.
    M = Var()
    n_mixed = sum(1 for _ in call("max_list", [1, "a"], M, module=mod))
    print(f"  max_list([1, 'a'], M):   {n_mixed} solutions  ← TypeError swallowed")

    if n_str == 0 and n_chars == 0:
        print("\n  Verdict: F052 CONFIRMED — sum_list silently swallows "
              "the TypeError from summing str chars; logical-failure indistinguishable "
              "from type-error.")


if __name__ == "__main__":
    main()
