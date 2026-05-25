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

Fact-side dodge.  ``_normalize_dataclass_fact`` (database.py:332-361,
gated by ``body_goals == [True]`` at database.py:274) rewrites ground
literal head fields into a fresh Var + ``Unify(var, value)`` body goal
before the clause is asserted.  This sidesteps the MatchValue branch
entirely because the head now contains only a Var.

Rule trap.  The ``body_goals == [True]`` gate covers rules whose body
is literally ``True`` as well as facts — those rules ALSO get
normalized.  Only rules with a real body goal (anything that flattens
to something other than ``[True]``) survive with the literal still
embedded in the head, exposing the MatchValue branch.

This probe writes an inline .clausal source to a tempfile, loads it
via the import hook, calls each predicate, and counts solutions.  The
rule fixtures use ``Helper(1)`` as the body to ensure the elaborator
dodge does NOT fire and the literal head is the one being matched.

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

# Facts (covered by _normalize_dataclass_fact elaborator dodge at
# clausal/logic/database.py:332-361, invoked from database.py:275):
Foo("abc"),
Bar(['a', 'b', 'c']),

# Helper used as a non-trivial rule body so the elaborator's body == [True]
# guard at database.py:274 does NOT fire, leaving any literal head args in
# the head where head_match.py:253-254 emits MatchValue(Constant(...)).
Helper(1),

# Rules with literal head args and a NON-True body (so the
# _normalize_dataclass_fact dodge does not apply).  Under strings-as-lists,
# both should be reachable by either argument shape.
Quux("abc") <- (Helper(1))
Zorp(['a', 'b', 'c']) <- (Helper(1))
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

    # C4 probe for rules-with-literal-head:
    n_quux = sum(1 for _ in call("Quux", ["a", "b", "c"], module=mod))
    n_zorp = sum(1 for _ in call("Zorp", "abc", module=mod))

    # Sanity controls for rules:
    n_quux_ctrl = sum(1 for _ in call("Quux", "abc", module=mod))
    n_zorp_ctrl = sum(1 for _ in call("Zorp", ["a", "b", "c"], module=mod))

    print(f"  FACT Foo(\"abc\") called with ['a','b','c']: {n_foo} solutions")
    print(f"  FACT Bar(['a','b','c']) called with \"abc\":  {n_bar} solutions")
    print(f"  Control FACT Foo(\"abc\") called with \"abc\":           {n_foo_ctrl} solutions")
    print(f"  Control FACT Bar(['a','b','c']) called with list:     {n_bar_ctrl} solutions")
    print(f"  RULE Quux(\"abc\"):- called with ['a','b','c']: {n_quux} solutions")
    print(f"  RULE Zorp(['a','b','c']):- called with \"abc\":  {n_zorp} solutions")
    print(f"  Control RULE Quux(\"abc\"):- called with \"abc\":          {n_quux_ctrl} solutions")
    print(f"  Control RULE Zorp(['a','b','c']):- called with list:    {n_zorp_ctrl} solutions")
    print(f"  Expected (strings-as-lists contract): 1 for every line above")

    all_pass = (n_foo == 1 and n_bar == 1 and n_quux == 1 and n_zorp == 1)
    if all_pass:
        print(f"  Verdict: C4 not present (for facts AND rules)")
    elif n_foo == 1 and n_bar == 1 and (n_quux == 0 or n_zorp == 0):
        print(f"  Verdict: C4 CONFIRMED FOR RULES (facts dodged by elaborator; rules not) — STOP and notify user")
    else:
        print(f"  Verdict: C4 partially present — review carefully")


if __name__ == "__main__":
    main()
