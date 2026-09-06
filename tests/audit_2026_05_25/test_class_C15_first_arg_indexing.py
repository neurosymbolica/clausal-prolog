"""C15 — First-arg indexing on strings.

Originally 1 bug finding (F095): the compiler's first-arg index computed
a SHARED bucket key for str vs char-list head clauses ("abc" and
``['a','b','c']`` coalesced to the same key), so a str caller and a
char-list caller landed in the same bucket. That coalescing implemented
the pre-P3-1 strings-as-lists contract at the dispatch layer; P3-1 (§1b)
retired the underlying cons rule (a str and a char-list no longer unify
in general), and P3-2 Task 4 (R8) retired the now-wrong coalescing itself
(``_charlist_to_str_or_none`` in ``arg_index.py``, and the matching lift
skip in ``list_dispatch.py``). This test now pins the POST-retirement
semantics: str and char-list heads bucket separately, and each caller
gets exactly its own-type clause.

Findings tested here:
- F095 (historical bug, RETIRED — see R8): first-arg indexing routed str
  and char-list to a shared bucket under the (also since-retired)
  strings-as-lists unification contract.
"""

def test_F095_first_arg_index_coalesces_str_and_charlist():
    """The first-arg index routes str and char-list heads to separate buckets.

    Post-retirement (P3-1 §1b + P3-2 R8): "lists unify with lists, str
    unifies with str" — a str head and an equal-content char-list head are
    NOT the same term and must not share a bucket or a caller. So:
    - An unbound Var caller enumerates every clause (indexing never narrows
      an unbound caller).
    - A str caller reaches only the str-headed clause: 1 solution.
    - A char-list caller reaches only the char-list-headed clause: 1 solution.

    For facts on the same predicate with ≥4 clauses total, the indexer kicks
    in (_INDEX_THRESHOLD=4 at arg_index.py:38). We register 5 clauses on a
    predicate to cross this threshold: 3 scalar "pad" clauses (on ints) + 1
    str-headed + 1 list-headed. This makes both the str and list heads
    eligible for bucketing (the list head keys ``_INDEX_VAR`` — unindexed,
    per R8 — and rides along as a "matches anything until proven otherwise"
    default clause merged into every specific bucket; see the mechanism note
    on the assertions below for why that merge does not reopen F095).
    """
    from clausal.logic.atoms import char_atom, mint
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
    x = Var()
    solutions_from_var = []
    for _ in call("TestPred", x, module=mod):
        v = deref(x)
        solutions_from_var.append((type(v).__name__, v))

    assert len(solutions_from_var) == 5, (
        f"TestPred(Var) should enumerate 5 clauses (three ints, one str, one list). "
        f"Got {len(solutions_from_var)} solutions: {solutions_from_var}."
    )

    # P3-2 Task 4 (R8, §1b): removing the coalesce alone did NOT make this
    # symmetric — traced by driving the repro, not by reading code. The
    # list-headed clause is hoisted to Var-head + body Unify exactly like
    # the str-headed one (``_normalize_dataclass_fact`` — confirmed NOT the
    # cause, ruling out the todo's original hypothesis), keys ``_INDEX_VAR``
    # (R8: a str-content list is unindexable), and is therefore merged as a
    # "default" clause into EVERY specific bucket including the str clause's
    # own — so the str caller's bucket still contained both clauses. The
    # actual residual mechanism was one level deeper: bucket compilation
    # LIFTS a merged-in ground list literal into a head sequence PATTERN,
    # and the runtime list-pattern destructuring helper
    # (``_head_list_unify_input_py`` / its C twin) still implements the
    # pre-P3-1 "a string is a list of its chars" contract for HEAD-PATTERN
    # matching (see docs/strings_as_lists.md, "Pattern Matching") — a
    # separate code path from the ``_variables.c`` ``do_unify`` cons rule
    # P3-1 retired, and untouched by that retirement. ``_lift_clause_at_pos``
    # (list_dispatch.py) now also skips lifting a ground list literal, for
    # exactly this reason — see that function's docstring for the full
    # trace. Fixed: todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md.
    n_str_caller = sum(1 for _ in call("TestPred", mint("abc"), module=mod))
    assert n_str_caller == 1, (
        f"TestPred('abc') returned {n_str_caller} solutions; expected 1 "
        f"(same-type str-headed clause only; §1b/R8: a str no longer "
        f"reaches a list-headed clause)."
    )

    n_list_caller = sum(1 for _ in call("TestPred", [mint("a"), mint("b"), mint("c")], module=mod))
    assert n_list_caller == 1, (
        f"TestPred(['a','b','c']) returned {n_list_caller} solutions; "
        f"expected 1 (same-type list-headed clause only; §1b/R8: a list "
        f"no longer reaches a str-headed clause)."
    )
