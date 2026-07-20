"""Round-trip tests for clausal.reflection render_ast/render_source — the
inverse of reify_ast. Invariant: reify(render_source(clause)) is structurally
identical to clause (positions ignored)."""

import dataclasses

import pytest

from clausal.reflection import (
    Clause,
    ReifyError,
    RenderError,
    reify_source,
    render_ast,
    render_source,
)


def strip_positions(term):
    """Recursively null every ``position`` field so structural == ignores
    source location. Reified terms carry ``_fields``; simple_ast operator
    nodes are dataclasses (their position is compare=False, but we normalise
    anyway to reach nested position-bearing terms)."""
    if isinstance(term, list):
        return [strip_positions(x) for x in term]
    if isinstance(term, tuple):
        return tuple(strip_positions(x) for x in term)
    if isinstance(term, dict):
        return {k: strip_positions(v) for k, v in term.items()}
    if dataclasses.is_dataclass(term) and not isinstance(term, type):
        return dataclasses.replace(term, **{
            f.name: (None if f.name == "position" else strip_positions(getattr(term, f.name)))
            for f in dataclasses.fields(term)
        })
    fields = getattr(type(term), "_fields", None)
    if fields is not None:
        return type(term)(*[
            None if name == "position" else strip_positions(getattr(term, name))
            for name in fields
        ])
    return term


def only_clause(src):
    clauses = [i for i in reify_source(src) if isinstance(i, Clause)]
    assert len(clauses) == 1, f"expected one clause, got {len(clauses)}"
    return clauses[0]


def assert_round_trips(src):
    """render_source then re-reify equals the original clause (ignoring positions)."""
    original = only_clause(src)
    rendered_text = render_source(original)
    reparsed = only_clause(rendered_text + "\n")
    assert strip_positions(reparsed) == strip_positions(original), (
        f"round-trip mismatch for {src!r}\n  rendered: {rendered_text!r}"
    )


class TestFacts:
    @pytest.mark.parametrize("src", [
        "Edge(1, 2),\n",
        "Item('widget', 2.5),\n",
        "Status(ok, 1),\n",
        "Temp(-40),\n",
        "Rule(X, Y),\n",
    ])
    def test_fact_round_trips(self, src):
        assert_round_trips(src)


class TestRules:
    @pytest.mark.parametrize("src", [
        "Connected(X, Y) <- Edge(X, Y)\n",
        "Grandparent(X, Z) <- (Parent(X, Y), Parent(Y, Z))\n",
        "Reachable(X) <- Edge(_, _)\n",
        "Three(A) <- (Pa(A), Qa(A), Ra(A))\n",
    ])
    def test_rule_round_trips(self, src):
        assert_round_trips(src)


class TestOperators:
    @pytest.mark.parametrize("src", [
        "Positive(N) <- (N > 0)\n",
        "AtLeast(N) <- (N >= 10)\n",
        "Eq(N) <- (N == 0)\n",
        "Neq(N) <- (N != 0)\n",
        "Sum(X, Y, Z) <- (Z is X + Y)\n",
        "Prod(X, Y, Z) <- (Z is X * Y)\n",
        "Diff(X, Y, Z) <- (Z is X - Y)\n",
        "Unify2(X, Y) <- (X is Y)\n",
        "Dif2(X, Y) <- (X is not Y)\n",
        "Free(A) <- (not Busy(A))\n",
        "Either(A) <- (Pa(A) or Qa(A))\n",
        "Both(A) <- (Pa(A) and Qa(A))\n",
        "Neg(X, Y) <- (Y is -X)\n",
        "ConsTail(T) <- Head([a, b | T])\n",
        "StarTail(T) <- Head([a, b, *T])\n",
    ])
    def test_operator_round_trips(self, src):
        assert_round_trips(src)
