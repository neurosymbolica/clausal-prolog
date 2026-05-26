"""C15 — First-arg indexing on strings.

1 bug finding. The compiler's first-arg index computes different bucket
keys for str vs char-list head clauses, so a caller with one container
type misses clauses indexed under the other. Dispatch-time analogue of
F046 (C4 head-literal mismatch); both must land together for the
strings-as-lists contract to hold at the dispatch layer.

Findings tested here:
- F095 (bug) First-arg indexing routes str vs char-list to different buckets
"""

import pytest


@pytest.mark.xfail(
    strict=True,
    reason="ledger F095: first-arg indexing routes str vs list to different buckets",
)
def test_F095_first_arg_index_coalesces_str_and_charlist():
    """The first-arg index routes str and char-list heads to different buckets.

    Under the strings-as-lists contract, str and equivalent char-list should
    unify at the dispatch layer, so:
    - A caller with unbound Var should enumerate both str and char-list clauses
    - A caller with str should reach both str-headed and char-list-headed clauses
    - A caller with char-list should reach both char-list-headed and str-headed clauses

    Currently, the indexer routes them to separate buckets:
    - str caller → str-specific bucket (which contains both str-headed and the
      list-headed default, merged for being < _INDEX_THRESHOLD callers)
    - list caller → _INDEX_VAR default bucket (which contains only list-headed)

    For facts on the same predicate with ≥4 clauses total, the indexer kicks in
    (_INDEX_THRESHOLD=4 at arg_index.py:38). We register 5 clauses on a predicate
    to cross this threshold: 3 scalar "pad" clauses (on ints) + 1 str-headed + 1
    list-headed. This makes both the str and list heads eligible for bucketing.

    Concrete effect: when called with an unbound Var, the caller enumerates both
    the str-headed AND list-headed clauses (they are merged into one bucket or
    both buckets are scanned). But when called with a ['a','b','c'] argument, the
    list caller routes to the default bucket (_INDEX_VAR), which excludes the
    str-headed clause, causing it to be silently missed.
    """
    from clausal.logic.solve import call
    from clausal.logic.variables import Var, deref
    from tests.audit_2026_05_25._helpers import load_inline_clausal

    # Register fixtures inline. We need 5+ clauses to cross _INDEX_THRESHOLD=4.
    # Three scalar pads (on ints), one str-headed, one list-headed.
    source = """\
PadHelper(1),

TestPred(1),
TestPred(2),
TestPred(3),
TestPred("abc"),
TestPred(['a', 'b', 'c']),
"""
    mod = load_inline_clausal("c15_f095_indexing", source).__dict__["$module"]

    # Test 1: Unbound Var caller should enumerate all 5 clauses.
    # (Baseline: both str and char-list clauses are reachable from Var caller.)
    x = Var()
    solutions_from_var = []
    for _ in call("TestPred", x, module=mod):
        v = deref(x)
        solutions_from_var.append((type(v).__name__, v))

    assert len(solutions_from_var) == 5, (
        f"TestPred(Var) should enumerate 5 clauses (three ints, one str, one list). "
        f"Got {len(solutions_from_var)} solutions: {solutions_from_var}. "
        f"This is the baseline for the C15 bug: if Var caller only returns "
        f"4 solutions, either the str-headed or list-headed clause is unreachable."
    )

    # Test 2: str-typed caller should find both str-headed AND list-headed clauses.
    # (Both should unify under strings-as-lists contract.)
    n_str_caller = sum(1 for _ in call("TestPred", "abc", module=mod))
    # Currently: routes to str bucket (contains str-headed clause + merged default for
    # list-headed), so returns 2.
    assert n_str_caller == 2, (
        f"TestPred('abc') should return 2 solutions: "
        f"the str-headed clause TestPred('abc') and the list-headed clause "
        f"TestPred(['a','b','c']) (via runtime unify). "
        f"Got {n_str_caller}. "
        f"If got 1, the list-headed clause is unreachable from str caller."
    )

    # Test 3: list-typed caller should find both list-headed AND str-headed clauses.
    # (This is where C15 breaks: the list caller routes to default bucket, missing str-headed.)
    n_list_caller = sum(1 for _ in call("TestPred", ["a", "b", "c"], module=mod))
    # Currently: routes to _INDEX_VAR default bucket (contains only list-headed clause),
    # so returns 1. Expected: 2 (list-headed + str-headed via runtime unify).
    assert n_list_caller == 2, (
        f"TestPred(['a','b','c']) should return 2 solutions: "
        f"the list-headed clause TestPred(['a','b','c']) and the str-headed clause "
        f"TestPred('abc') (via runtime unify, under strings-as-lists contract). "
        f"Got {n_list_caller}. "
        f"This is the C15 bug: list caller routes to _INDEX_VAR default bucket, "
        f"which does not include the str-headed clause. "
        f"Fix requires canonicalizing the dispatch-time bucket key so str and "
        f"char-list callers reach the same clauses."
    )
