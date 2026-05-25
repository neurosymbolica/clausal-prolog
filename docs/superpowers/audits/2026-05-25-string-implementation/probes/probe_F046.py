"""Probe F046: C4 — head string literal vs char-list caller (and vice versa).

The compiler's ``head_to_match_pattern`` (head_match.py:253-254) emits a
raw ``ast.MatchValue(ast.Constant(value=term))`` when a clause head arg
is a Python ``str``.  Python's ``match`` statement compares
``MatchValue`` patterns using ``==``.

Under the strings-as-lists contract — exercised by Phase 1 unification
in ``tests/test_string_list_unification.py`` (``"abc" == ['a','b','c']``
at the runtime ``unify`` layer) — a clause ``Foo("abc")`` *should* match
a caller ``Foo(['a','b','c'])`` because the two are unifiable.  But
``"abc" == ['a','b','c']`` is ``False`` in plain Python, so the
``match`` arm rejects the caller and the clause silently does not
match.

This probe is the largest-blast-radius candidate in the audit.  If it
confirms, the fix scope is potentially compiler-wide — every clause
whose head pins a string literal would need either:
- a wrapping unify guard instead of a raw MatchValue, or
- an outer wildcard capture + post-match unify guard equivalent to the
  list-pattern path that already exists (lines 258-448).

This probe writes an inline .clausal source to a tempfile, loads it
via the import hook, calls each predicate, and counts solutions.

Usage:
    python docs/superpowers/audits/2026-05-25-string-implementation/probes/probe_F046.py
"""
from __future__ import annotations

import os
import tempfile

from clausal.import_hook import _load_module
from clausal.logic.solve import call


SOURCE = """
# Probe F046 fixtures — clause heads pinning string vs char-list literals.

Foo("abc"),
Bar(['a', 'b', 'c']),
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
    print("Probe F046: C4 — head literal mismatch (str vs char-list)")

    mod = _load_inline_clausal("probe_f046_c4", SOURCE).__dict__["$module"]

    # Call Foo(['a','b','c']) — should match clause Foo("abc") under
    # strings-as-lists.
    n_foo = sum(1 for _ in call("Foo", ["a", "b", "c"], module=mod))

    # Call Bar("abc") — should match clause Bar(['a','b','c']) under
    # strings-as-lists.
    n_bar = sum(1 for _ in call("Bar", "abc", module=mod))

    # Sanity controls: same-type calls should always succeed.
    n_foo_ctrl = sum(1 for _ in call("Foo", "abc", module=mod))
    n_bar_ctrl = sum(1 for _ in call("Bar", ["a", "b", "c"], module=mod))

    print(f"  Foo(\"abc\") called with ['a','b','c']: {n_foo} solutions")
    print(f"  Bar(['a','b','c']) called with \"abc\":  {n_bar} solutions")
    print(f"  Control Foo(\"abc\") called with \"abc\":           {n_foo_ctrl} solutions")
    print(f"  Control Bar(['a','b','c']) called with list:     {n_bar_ctrl} solutions")
    print(f"  Expected (strings-as-lists contract): 1 and 1")
    if n_foo == 1 and n_bar == 1:
        print(f"  Verdict: C4 not present")
    else:
        print(f"  Verdict: C4 CONFIRMED — STOP and notify user")


if __name__ == "__main__":
    main()
