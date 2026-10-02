"""Rule heads with imported-compound functors must destructure correctly.

Companion to todo/rule_head_imported_compound_falls_through_to_wildcard.md
in clausal-thai_imm_rules.

The todo described the bug as a wildcard fall-through (rule fires on
every input).  The actual current symptom is the inverse: because
``Call`` is a dataclass, ``head_to_match_pattern`` routes through the
``is_term_instance`` branch and emits a ``MatchClass(Call, ...)``
pattern that requires the runtime arg to *be* a ``Call`` AST instance —
which it never is.  Result: rule clauses with imported-compound heads
never fire.

Same root cause (no ``Call(func=LoadName, args=...)`` case in
``head_to_match_pattern``), opposite manifestation.  The fix is to
resolve the ``LoadName`` at compile time against the module's globals
and emit the pattern the reference compiles to.

P3-2 Task 2 (THE FLIP, R6): ``wrap``/``Item``/``Met`` are DATA functors, so
they compile to cells and their names bind interned spellings rather than
classes -- ``mod.wrap`` is the str ``"wrap"``, not a constructor.  Every term
this file used to build with ``wrap(...)`` is now built as the cell literal
``("wrap", ...)``, and the shape assertions read slot 0 instead of
``type(x).__name__``.  The dispatch questions being asked are unchanged; only
the representation the caller hands in is.
"""

from __future__ import annotations

import os

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_importer() -> object:
    # Load the owner first so its declarations are in place; the
    # importer's -import_from(...) will then resolve cleanly.
    _load_module(
        "tests.fixtures.head_compound_owner",
        _fixture_path("head_compound_owner.seam"),
    )
    return _load_module(
        "tests.fixtures.head_compound_importer",
        _fixture_path("head_compound_importer.seam"),
    )


def _results(mod: object, pred: str, *args) -> list:
    logic_mod = mod.__dict__["$module"]
    out_var = Var()
    found = []
    for _ in call(pred, *args, out_var, module=logic_mod):
        found.append(deref(out_var))
    return found


def test_rule_with_imported_compound_head_skips_non_matching_term():
    """Rule head check(wrap(_), _) MUST NOT fire on 'not_a_wrap'."""
    mod = _load_importer()
    results = _results(mod, "check", "not_a_wrap")
    # Expected: only the catch-all fires.
    assert results == [mint("fallback")], (
        f"Rule head compiled to wildcard — fired for non-Wrap input. "
        f"Got {results!r}, expected ['fallback']."
    )


def test_fact_with_imported_compound_head_skips_non_matching_term():
    """Parity baseline: fact form already routes correctly today."""
    mod = _load_importer()
    results = _results(mod, "check_fact", "not_a_wrap")
    assert results == [mint("fallback")], (
        f"Fact-form head misrouted. Got {results!r}, expected ['fallback']."
    )


def test_rule_with_imported_compound_head_fires_on_matching_term():
    """When the caller passes a wrap term, the rule must match."""
    mod = _load_importer()
    wrap_term = ("wrap", "anything")
    results = _results(mod, "check", wrap_term)
    # Both clauses match a Wrap term: the rule yields "matched", the
    # catch-all yields "fallback".
    assert results == [mint("matched"), mint("fallback")], (
        f"Expected rule + catchall to both fire on Wrap input. Got {results!r}."
    )


def test_rule_with_imported_compound_head_binds_inner_var():
    """SUB inside wrap(SUB) in the head must bind to the caller's sub-term."""
    mod = _load_importer()
    wrap_term = ("wrap", "payload")
    results = _results(mod, "check_mixed", wrap_term)
    assert results == ["payload", mint("fallback")], (
        f"Expected SUB to be bound to 'payload'. Got {results!r}."
    )


def test_fact_and_rule_forms_agree_for_non_matching_input():
    """Fact-form and rule-form must produce identical results.

    This is the structural invariant from the todo: a fact `H,` and a
    rule `H <- true` MUST dispatch identically.
    """
    mod = _load_importer()
    rule_results = _results(mod, "check", "not_a_wrap")
    fact_results = _results(mod, "check_fact", "not_a_wrap")
    assert rule_results == fact_results, (
        f"Fact/rule head divergence: rule={rule_results!r} "
        f"fact={fact_results!r}"
    )


def test_fact_and_rule_forms_agree_for_matching_input():
    mod = _load_importer()
    wrap_term = ("wrap", "x")
    rule_results = _results(mod, "check", wrap_term)
    fact_results = _results(mod, "check_fact", wrap_term)
    assert rule_results == fact_results, (
        f"Fact/rule head divergence on matching input: "
        f"rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_imported_compound_head_destructures():
    """The original ``item(REQ_ID, met(S), _, _)`` case from the todo.

    Both the outer ``item`` and inner ``met`` are imported compound
    functors; the head pattern compiles to a nested ``MatchClass``.
    """
    mod = _load_importer()
    direct = getattr(mod, "direct")
    # Matching shape: Item(REQ_ID, Met(SUB), DETAIL)
    item_term = ("item", "req-42", ("met", direct), "some-detail")
    results = _results(mod, "check_nested", item_term)
    # Rule binds RESULT to REQ_ID ("req-42") and yields; catchall yields "fallback".
    assert results == ["req-42", mint("fallback")], (
        f"Nested imported-compound head failed to destructure. Got {results!r}."
    )


def test_nested_imported_compound_head_rejects_outer_class_mismatch():
    """A wrap term must NOT match a head expecting item — different classes."""
    mod = _load_importer()
    results = _results(mod, "check_nested", ("wrap", "x"))
    assert results == [mint("fallback")], (
        f"Nested head matched a Wrap term when expecting Item. Got {results!r}."
    )


def test_nested_imported_compound_head_rejects_inner_class_mismatch():
    """An Item whose second arg is NOT a Met must fall through to catchall."""
    mod = _load_importer()
    # Item present but second arg is a plain string, not Met(_):
    results = _results(mod, "check_nested", ("item", "r", "not-a-met", "d"))
    assert results == [mint("fallback")], (
        f"Nested head matched on inner-class mismatch. Got {results!r}."
    )


# ── First-argument indexer + imported compounds ────────────────────────


def test_indexed_wrap_rule_fires_under_first_arg_index():
    """5 clauses → first-arg indexer engages.  Bucketing must reach
    the wrap-keyed clauses when the caller passes a wrap term."""
    mod = _load_importer()
    results = _results(mod, "check_indexed", ("wrap", "x"))
    assert results == [mint("first"), mint("second"), mint("fallback")], (
        f"Indexer bucketing dropped Wrap-keyed rule clauses. Got {results!r}."
    )


def test_indexed_item_rule_fires_under_first_arg_index():
    mod = _load_importer()
    direct = getattr(mod, "direct")
    item_with_met = ("item", "r", ("met", direct), "d")
    results = _results(mod, "check_indexed", item_with_met)
    # Both Item-keyed rule clauses match (the second one further
    # destructures Met(_) which the input satisfies).
    assert results == [mint("item"), mint("item-met"), mint("fallback")], (
        f"Indexer bucketing dropped Item-keyed rule clauses. "
        f"Got {results!r}."
    )


def test_indexed_non_matching_term_only_hits_fallback():
    mod = _load_importer()
    results = _results(mod, "check_indexed", "not_a_known_shape")
    assert results == [mint("fallback")], (
        f"Non-matching input fired an indexed rule clause. Got {results!r}."
    )


# ── Fact-form vs rule-form parity for Call(LoadName) head shapes ──────
#
# These are the dispatch-equivalence assertions for the specific head
# shapes the immediate fix addresses.  The wider structural pin
# (every head shape, including scalars / lists / locals) is out of
# scope and tracked separately — see the todo's "Structural" section.


def test_nested_fact_and_rule_agree_on_matching_input():
    mod = _load_importer()
    direct = getattr(mod, "direct")
    item_term = ("item", "req", ("met", direct), "d")
    rule_results = _results(mod, "check_nested", item_term)
    fact_results = _results(mod, "check_nested_fact", item_term)
    # Rule binds RESULT to REQ_ID ("req"); fact binds RESULT to "matched".
    # They disagree on the *value* (different head shape conventions in
    # the fixture), but they must agree on solution count.
    assert len(rule_results) == len(fact_results), (
        f"Rule fired {len(rule_results)}x but fact fired {len(fact_results)}x "
        f"on matching nested input. rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_fact_and_rule_agree_on_outer_mismatch():
    mod = _load_importer()
    rule_results = _results(mod, "check_nested", ("wrap", "x"))
    fact_results = _results(mod, "check_nested_fact", ("wrap", "x"))
    assert rule_results == fact_results, (
        f"Fact/rule divergence on outer mismatch: "
        f"rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_fact_and_rule_agree_on_inner_mismatch():
    mod = _load_importer()
    rule_results = _results(mod, "check_nested", ("item", "r", "no-met", "d"))
    fact_results = _results(mod, "check_nested_fact", ("item", "r", "no-met", "d"))
    assert rule_results == fact_results, (
        f"Fact/rule divergence on inner mismatch: "
        f"rule={rule_results!r} fact={fact_results!r}"
    )


def _bind_first(mod, pred, second):
    """Output mode: query pred(X, second) with X unbound; return derefs of X."""
    logic_mod = mod.__dict__["$module"]
    X = Var()
    found = []
    for _ in call(pred, X, second, module=logic_mod):
        found.append(deref(X))
    return found


def test_rule_structural_head_binds_unbound_caller():
    """check(wrap(SUB), RESULT) <- RESULT is "matched":
    check(X, "matched") with X unbound must bind X = wrap(_)."""
    mod = _load_importer()
    got = _bind_first(mod, "check", mint("matched"))
    assert len(got) == 1
    # R6: the constructed answer is a cell -- slot 0 IS the functor.
    assert got[0][0] == "wrap"


def test_rule_matches_fact_in_output_mode():
    """rule (check) and fact (check_fact) must agree in output mode."""
    mod = _load_importer()
    rule_got = _bind_first(mod, "check", mint("matched"))
    fact_got = _bind_first(mod, "check_fact", mint("matched"))
    assert len(rule_got) == len(fact_got) == 1
    assert rule_got[0][0] == fact_got[0][0] == "wrap"   # R6: cells


def test_indexed_imported_compound_at_second_position_enumerates_all_rows():
    """arg0 UNBOUND + arg1 = an imported compound must route onto the arg1
    index and enumerate every row for that functor.

    Regression: with >=4 fact clauses the indexer engages; the Phase-8 lift
    put an unresolved ``Call(LoadName wrap)`` into the bucket head whose
    bucket globals lacked the imported class, so ``head_to_match_pattern``
    emitted ``MatchClass(Call)`` and the wrap/Item buckets returned nothing."""
    mod = _load_importer()
    wrap_rows = _bind_first(mod, "tagged", ("wrap", Var()))
    assert sorted(wrap_rows) == [mint("r1"), mint("r3")], (
        f"arg1-indexed Wrap bucket dropped rows. Got {wrap_rows!r}, "
        f"expected [('r1',), ('r3',)]."
    )
    item_rows = _bind_first(mod, "tagged", ("item", Var(), Var(), Var()))
    assert sorted(item_rows) == [mint("r2"), mint("r4")], (
        f"arg1-indexed Item bucket dropped rows. Got {item_rows!r}, "
        f"expected [('r2',), ('r4',)]."
    )


def test_indexed_imported_compound_at_second_position_fully_unbound_arg():
    """Control: fully-unbound arg1 (no functor to index on) already works —
    every row must enumerate regardless of the indexing bug."""
    mod = _load_importer()
    all_rows = _bind_first(mod, "tagged", Var())
    assert sorted(all_rows) == [mint("r1"), mint("r2"), mint("r3"),
                                mint("r4")], (
        f"Fully-unbound arg1 dropped rows. Got {all_rows!r}."
    )


def test_nested_compound_head_binds_unbound_caller():
    """check_nested(item(REQ_ID, met(SUB), _), RESULT) <- RESULT is REQ_ID:
    output mode must construct AND correctly shape the nested term. There are
    two solutions (the rule + the "fallback" catch-all); pin the rule's."""
    mod = _load_importer()
    logic_mod = mod.__dict__["$module"]
    X = Var()
    found = []
    for _ in call("check_nested", X, Var(), module=logic_mod):
        found.append(deref(X))
    item_solutions = [
        f for f in found if isinstance(f, tuple) and f and f[0] == "item"
    ]
    assert len(item_solutions) == 1
    item = item_solutions[0]
    # The structural head Item(REQ_ID, Met(SUB), _) must be reconstructed with
    # its STATUS slot bound to a Met-shaped sub-term (not a free var /
    # garbage).  R6: STATUS is slot 2 of the cell, not an attribute.
    assert deref(item[2])[0] == "met"
