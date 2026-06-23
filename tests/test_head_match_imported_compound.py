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
and emit a ``MatchClass`` on the resolved ``PredicateMeta`` class.
"""

from __future__ import annotations

import os

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
        _fixture_path("head_compound_owner.clausal"),
    )
    return _load_module(
        "tests.fixtures.head_compound_importer",
        _fixture_path("head_compound_importer.clausal"),
    )


def _results(mod: object, pred: str, *args) -> list:
    logic_mod = mod.__dict__["$module"]
    out_var = Var()
    found = []
    for _ in call(pred, *args, out_var, module=logic_mod):
        found.append(deref(out_var))
    return found


def test_rule_with_imported_compound_head_skips_non_matching_term():
    """Rule head Check(Wrap(_), _) MUST NOT fire on 'not_a_wrap'."""
    mod = _load_importer()
    results = _results(mod, "Check", "not_a_wrap")
    # Expected: only the catch-all fires.
    assert results == ["fallback"], (
        f"Rule head compiled to wildcard — fired for non-Wrap input. "
        f"Got {results!r}, expected ['fallback']."
    )


def test_fact_with_imported_compound_head_skips_non_matching_term():
    """Parity baseline: fact form already routes correctly today."""
    mod = _load_importer()
    results = _results(mod, "CheckFact", "not_a_wrap")
    assert results == ["fallback"], (
        f"Fact-form head misrouted. Got {results!r}, expected ['fallback']."
    )


def test_rule_with_imported_compound_head_fires_on_matching_term():
    """When the caller passes a Wrap term, the rule must match."""
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    wrap_term = Wrap("anything")
    results = _results(mod, "Check", wrap_term)
    # Both clauses match a Wrap term: the rule yields "matched", the
    # catch-all yields "fallback".
    assert results == ["matched", "fallback"], (
        f"Expected rule + catchall to both fire on Wrap input. Got {results!r}."
    )


def test_rule_with_imported_compound_head_binds_inner_var():
    """SUB inside Wrap(SUB) in the head must bind to the caller's sub-term."""
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    wrap_term = Wrap("payload")
    results = _results(mod, "CheckMixed", wrap_term)
    assert results == ["payload", "fallback"], (
        f"Expected SUB to be bound to 'payload'. Got {results!r}."
    )


def test_fact_and_rule_forms_agree_for_non_matching_input():
    """Fact-form and rule-form must produce identical results.

    This is the structural invariant from the todo: a fact `H,` and a
    rule `H <- true` MUST dispatch identically.
    """
    mod = _load_importer()
    rule_results = _results(mod, "Check", "not_a_wrap")
    fact_results = _results(mod, "CheckFact", "not_a_wrap")
    assert rule_results == fact_results, (
        f"Fact/rule head divergence: rule={rule_results!r} "
        f"fact={fact_results!r}"
    )


def test_fact_and_rule_forms_agree_for_matching_input():
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    wrap_term = Wrap("x")
    rule_results = _results(mod, "Check", wrap_term)
    fact_results = _results(mod, "CheckFact", wrap_term)
    assert rule_results == fact_results, (
        f"Fact/rule head divergence on matching input: "
        f"rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_imported_compound_head_destructures():
    """The original ``Item(REQ_ID, Met(S), _, _)`` case from the todo.

    Both the outer ``Item`` and inner ``Met`` are imported compound
    functors; the head pattern compiles to a nested ``MatchClass``.
    """
    mod = _load_importer()
    Item = getattr(mod, "Item")
    Met = getattr(mod, "Met")
    direct = getattr(mod, "direct")
    # Matching shape: Item(REQ_ID, Met(SUB), DETAIL)
    item_term = Item("req-42", Met(direct), "some-detail")
    results = _results(mod, "CheckNested", item_term)
    # Rule binds RESULT to REQ_ID ("req-42") and yields; catchall yields "fallback".
    assert results == ["req-42", "fallback"], (
        f"Nested imported-compound head failed to destructure. Got {results!r}."
    )


def test_nested_imported_compound_head_rejects_outer_class_mismatch():
    """A Wrap term must NOT match a head expecting Item — different classes."""
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    results = _results(mod, "CheckNested", Wrap("x"))
    assert results == ["fallback"], (
        f"Nested head matched a Wrap term when expecting Item. Got {results!r}."
    )


def test_nested_imported_compound_head_rejects_inner_class_mismatch():
    """An Item whose second arg is NOT a Met must fall through to catchall."""
    mod = _load_importer()
    Item = getattr(mod, "Item")
    # Item present but second arg is a plain string, not Met(_):
    results = _results(mod, "CheckNested", Item("r", "not-a-met", "d"))
    assert results == ["fallback"], (
        f"Nested head matched on inner-class mismatch. Got {results!r}."
    )


# ── First-argument indexer + imported compounds ────────────────────────


def test_indexed_wrap_rule_fires_under_first_arg_index():
    """5 clauses → first-arg indexer engages.  Bucketing must reach
    the Wrap-keyed clauses when the caller passes a Wrap term."""
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    results = _results(mod, "CheckIndexed", Wrap("x"))
    assert results == ["first", "second", "fallback"], (
        f"Indexer bucketing dropped Wrap-keyed rule clauses. Got {results!r}."
    )


def test_indexed_item_rule_fires_under_first_arg_index():
    mod = _load_importer()
    Item = getattr(mod, "Item")
    Met = getattr(mod, "Met")
    direct = getattr(mod, "direct")
    item_with_met = Item("r", Met(direct), "d")
    results = _results(mod, "CheckIndexed", item_with_met)
    # Both Item-keyed rule clauses match (the second one further
    # destructures Met(_) which the input satisfies).
    assert results == ["item", "item-met", "fallback"], (
        f"Indexer bucketing dropped Item-keyed rule clauses. "
        f"Got {results!r}."
    )


def test_indexed_non_matching_term_only_hits_fallback():
    mod = _load_importer()
    results = _results(mod, "CheckIndexed", "not_a_known_shape")
    assert results == ["fallback"], (
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
    Item = getattr(mod, "Item")
    Met = getattr(mod, "Met")
    direct = getattr(mod, "direct")
    item_term = Item("req", Met(direct), "d")
    rule_results = _results(mod, "CheckNested", item_term)
    fact_results = _results(mod, "CheckNestedFact", item_term)
    # Rule binds RESULT to REQ_ID ("req"); fact binds RESULT to "matched".
    # They disagree on the *value* (different head shape conventions in
    # the fixture), but they must agree on solution count.
    assert len(rule_results) == len(fact_results), (
        f"Rule fired {len(rule_results)}x but fact fired {len(fact_results)}x "
        f"on matching nested input. rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_fact_and_rule_agree_on_outer_mismatch():
    mod = _load_importer()
    Wrap = getattr(mod, "Wrap")
    rule_results = _results(mod, "CheckNested", Wrap("x"))
    fact_results = _results(mod, "CheckNestedFact", Wrap("x"))
    assert rule_results == fact_results, (
        f"Fact/rule divergence on outer mismatch: "
        f"rule={rule_results!r} fact={fact_results!r}"
    )


def test_nested_fact_and_rule_agree_on_inner_mismatch():
    mod = _load_importer()
    Item = getattr(mod, "Item")
    rule_results = _results(mod, "CheckNested", Item("r", "no-met", "d"))
    fact_results = _results(mod, "CheckNestedFact", Item("r", "no-met", "d"))
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
    """Check(Wrap(SUB), RESULT) <- RESULT is "matched":
    Check(X, "matched") with X unbound must bind X = Wrap(_)."""
    mod = _load_importer()
    got = _bind_first(mod, "Check", "matched")
    assert len(got) == 1
    assert type(got[0]).__name__ == "Wrap"


def test_rule_matches_fact_in_output_mode():
    """Rule (Check) and fact (CheckFact) must agree in output mode."""
    mod = _load_importer()
    rule_got = _bind_first(mod, "Check", "matched")
    fact_got = _bind_first(mod, "CheckFact", "matched")
    assert len(rule_got) == len(fact_got) == 1
    assert type(rule_got[0]).__name__ == type(fact_got[0]).__name__ == "Wrap"


def test_nested_compound_head_binds_unbound_caller():
    """CheckNested(Item(REQ_ID, Met(SUB), _), RESULT) <- RESULT is REQ_ID:
    output mode constructs the nested term and binds the caller Var.

    Note: the catch-all clause CheckNested(ANY, "fallback") also fires in
    output mode (ANY unifies with the unbound X and "fallback" unifies with
    the second Var()), so len(found) == 2.  The pin is that at least one
    solution has X bound to an Item.
    """
    mod = _load_importer()
    logic_mod = mod.__dict__["$module"]
    X = Var()
    found = []
    for _ in call("CheckNested", X, Var(), module=logic_mod):
        found.append(deref(X))
    assert any(type(f).__name__ == "Item" for f in found)
