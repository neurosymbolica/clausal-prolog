"""C4 — Head-pattern literal mismatch (rule heads with str literals).

1 bug finding. Quux("abc") <- (real_body) compiles to MatchValue(Constant("abc"))
at head_match.py:253-254. Python's match uses == for MatchValue, so a caller
Quux(['a','b','c']) silently fails despite the strings-as-lists contract.

Asymmetry: only str-literal heads in rules with non-True bodies hit this
bug. Facts (including <- (True) rules) dodge it via the
_normalize_dataclass_fact elaborator at database.py:332-361. List-literal
heads work because they go through the wildcard-capture + runtime-unify
path at head_match.py:258.

This single test guards the highest-blast-radius fix in the audit. Per
the Phase 2 ordering, C4 lands last and requires F095 (first-arg indexing
canonicalisation) to land first.

Findings tested here:
- F046 (bug) — Rules with str-literal heads silently fail char-list callers
"""

import pytest


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ledger F046: Rules with string-literal heads fail to match "
        "char-list callers"
    ),
)
def test_F046_rule_str_head_matches_charlist_caller():
    """All 8 cross-call combinations (fact/rule × str-head/list-head ×
    str-caller/list-caller) should return exactly 1 solution each.

    Currently the Quux(['a','b','c']) call returns 0 solutions, which makes
    the assertion fail and the xfail fire.

    The probe registers four clauses via inline .clausal source:
    - Fact `Foo("abc")` — handled correctly by elaborator dodge
    - Fact `Bar(['a', 'b', 'c'])` — handled correctly
    - Rule `Quux("abc") <- (Helper(1))` — currently broken (F046 bug)
    - Rule `Zorp(['a','b','c']) <- (Helper(1))` — currently works
    - Plus `Helper(1)` so the rule bodies succeed

    Under the strings-as-lists contract, all 8 calls should work:
    1. Foo("abc") — control (fact, str-head, str-caller)
    2. Foo(['a','b','c']) — strings-as-lists test (fact, str-head, list-caller)
    3. Bar("abc") — strings-as-lists test (fact, list-head, str-caller)
    4. Bar(['a','b','c']) — control (fact, list-head, list-caller)
    5. Quux("abc") — control (rule, str-head, str-caller)
    6. Quux(['a','b','c']) — strings-as-lists test (rule, str-head, list-caller) [CURRENTLY FAILS]
    7. Zorp("abc") — strings-as-lists test (rule, list-head, str-caller)
    8. Zorp(['a','b','c']) — control (rule, list-head, list-caller)

    The bug surface is call #6: Quux(['a','b','c']) returns 0 solutions
    instead of 1.
    """
    from clausal.logic.solve import call
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    # Register fixtures inline.
    source = """\
Foo("abc"),
Bar(['a', 'b', 'c']),

Helper(1),

Quux("abc") <- (Helper(1))
Zorp(['a', 'b', 'c']) <- (Helper(1))
"""
    mod = load_inline_clausal("c04_f046_heads", source).__dict__["$module"]

    # Collect all 8 solution counts.
    n_foo_str = sum(1 for _ in call("Foo", "abc", module=mod))
    n_foo_list = sum(1 for _ in call("Foo", ["a", "b", "c"], module=mod))
    n_bar_str = sum(1 for _ in call("Bar", "abc", module=mod))
    n_bar_list = sum(1 for _ in call("Bar", ["a", "b", "c"], module=mod))
    n_quux_str = sum(1 for _ in call("Quux", "abc", module=mod))
    n_quux_list = sum(1 for _ in call("Quux", ["a", "b", "c"], module=mod))
    n_zorp_str = sum(1 for _ in call("Zorp", "abc", module=mod))
    n_zorp_list = sum(1 for _ in call("Zorp", ["a", "b", "c"], module=mod))

    # Assert all 8 return exactly 1 solution.
    assert n_foo_str == 1, (
        f"Fact Foo(\"abc\") called with \"abc\" returned {n_foo_str} "
        f"solutions; expected 1 (control)"
    )
    assert n_foo_list == 1, (
        f"Fact Foo(\"abc\") called with ['a','b','c'] returned "
        f"{n_foo_list} solutions; expected 1 (strings-as-lists test, "
        f"handled by elaborator dodge)"
    )
    assert n_bar_str == 1, (
        f"Fact Bar(['a','b','c']) called with \"abc\" returned {n_bar_str} "
        f"solutions; expected 1 (strings-as-lists test)"
    )
    assert n_bar_list == 1, (
        f"Fact Bar(['a','b','c']) called with ['a','b','c'] returned "
        f"{n_bar_list} solutions; expected 1 (control)"
    )
    assert n_quux_str == 1, (
        f"Rule Quux(\"abc\") <- Helper(1) called with \"abc\" returned "
        f"{n_quux_str} solutions; expected 1 (control)"
    )
    assert n_quux_list == 1, (
        f"Rule Quux(\"abc\") <- Helper(1) called with ['a','b','c'] "
        f"returned {n_quux_list} solutions; expected 1 (strings-as-lists "
        f"test, currently broken — F046 bug: head_match.py:253-254 emits "
        f"MatchValue(Constant(\"abc\")) which fails == comparison with "
        f"['a','b','c'])"
    )
    assert n_zorp_str == 1, (
        f"Rule Zorp(['a','b','c']) <- Helper(1) called with \"abc\" "
        f"returned {n_zorp_str} solutions; expected 1 (strings-as-lists "
        f"test, list-literal heads work via wildcard+runtime-unify)"
    )
    assert n_zorp_list == 1, (
        f"Rule Zorp(['a','b','c']) <- Helper(1) called with "
        f"['a','b','c'] returned {n_zorp_list} solutions; expected 1 "
        f"(control)"
    )
