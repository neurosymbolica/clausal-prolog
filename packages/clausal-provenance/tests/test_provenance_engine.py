"""Engine invariants for `clausal-provenance` under the boolean semiring.

These tests construct predicates and rules at the Python level (no .clausal
parsing needed) so they exercise the engine in isolation.
"""

from __future__ import annotations

import pytest

from clausal.logic.predicate import make_predicate
from clausal.logic.database import Module, Clause
from clausal.logic.variables import Var
from clausal.pythonic_ast.nodes import Call, LoadName, Not

from clausal.modules.provenance import (
    boolean,
    evaluate,
    query,
    Provenance,
    PurityError,
    NonGroundTupleError,
    StratificationError,
)
from clausal.modules.provenance._registration import (
    BOTTOM_UP_FLAG,
    PURE_FLAG,
)


# ── Helpers ─────────────────────────────────────────────────────────────


def _setup_program(*pred_specs):
    """Build (module, classes-dict) for predicates declared by name+fields.

    Each pred_spec is a tuple ``(name, fields, bottom_up=True)``.
    """
    classes: dict = {}
    module_dict: dict = {}
    for spec in pred_specs:
        if len(spec) == 2:
            name, fields = spec
            bu = True
        else:
            name, fields, bu = spec
        cls = make_predicate(name, fields)
        cls.__module__ = "test_engine"
        if bu:
            setattr(cls, BOTTOM_UP_FLAG, True)
        classes[name] = cls
        module_dict[name] = cls
    mod = Module("test_engine", module_dict=module_dict)
    return mod, classes


def _ast_call(name, *args):
    return Call(func=LoadName(name=name), args=list(args), kwargs=[])


# ── Boolean semiring algebra ────────────────────────────────────────────


def test_boolean_zero_one():
    assert boolean.zero() is False
    assert boolean.one() is True


def test_boolean_add_is_or():
    assert boolean.add(False, False) is False
    assert boolean.add(False, True) is True
    assert boolean.add(True, False) is True
    assert boolean.add(True, True) is True


def test_boolean_mult_is_and():
    assert boolean.mult(False, False) is False
    assert boolean.mult(False, True) is False
    assert boolean.mult(True, False) is False
    assert boolean.mult(True, True) is True


def test_boolean_negate():
    assert boolean.negate(True) is False
    assert boolean.negate(False) is True


def test_boolean_saturated_default():
    assert boolean.saturated(True, True) is True
    assert boolean.saturated(False, True) is False


# ── End-to-end reachability is dogfooded in
#    tests/fixtures/provenance_reach.clausal and mutual_recursion.clausal.
#    These Python tests retain only the cases that need pytest infra:
#    error paths, custom Python semirings, and engine-internal probes.


# ── Single empty-relation corner case (kept in Python — fits Python)
#    better than a dedicated .clausal fixture for this one shape) ────────


def test_facts_only_no_rules_for_query_predicate():
    """Path is registered -bottom_up but has no clauses; querying yields []."""
    mod, c = _setup_program(("edge", ["a", "b"]), ("path", ["a", "b"]))
    Edge, Path = c["edge"], c["path"]
    facts = [(Edge("a", "b"), True)]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    assert out == []


# ── Purity errors ───────────────────────────────────────────────────────


def test_purity_error_on_unmarked_callee():
    mod, c = _setup_program(("path", ["a", "b"]),)
    Path = c["path"]
    A, B = Var(), Var()
    # Body calls "MystePred" which is neither -bottom_up, -pure, nor default-pure.
    Path._assertz(Clause(
        head=Path(A, B),
        body=[_ast_call("MysteryPred", A, B)],
    ))
    with pytest.raises(PurityError) as exc:
        evaluate(boolean, [], Path(Var(), Var()), module=mod)
    assert "MysteryPred/2" in str(exc.value)
    # Message points at docs/purity.md
    assert "purity" in str(exc.value).lower()


def test_default_pure_builtins_accepted():
    """`is`/2 (Unify) is on the default-pure whitelist."""
    mod, c = _setup_program(("edge", ["a", "b"]), ("path", ["a", "b"]))
    Edge, Path = c["edge"], c["path"]
    # Path(A, B) :- Edge(A, B), length([A, B], 2)
    # length/2 is on the default-pure whitelist.
    A, B = Var(), Var()
    Path._assertz(Clause(
        head=Path(A, B),
        body=[
            _ast_call("edge", A, B),
            _ast_call("length", [A, B], 2),
        ],
    ))
    facts = [(Edge("a", "b"), True)]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    assert len(out) == 1


def test_pure_marked_callee_accepted():
    """A user predicate marked via `pure_/1` is callable from -bottom_up bodies."""
    mod, c = _setup_program(
        ("edge", ["a", "b"]),
        ("path", ["a", "b"]),
        ("MyHelper", ["x"], False),  # not -bottom_up
    )
    Edge, Path, MyHelper = c["edge"], c["path"], c["MyHelper"]
    setattr(MyHelper, PURE_FLAG, True)
    # MyHelper has no clauses; it'll fail when called. That's fine — the
    # purity check only validates the *call site*, not whether the call
    # would succeed.
    A, B = Var(), Var()
    Path._assertz(Clause(
        head=Path(A, B),
        body=[_ast_call("edge", A, B), _ast_call("MyHelper", A)],
    ))
    facts = [(Edge("a", "b"), True)]
    # Should not raise PurityError — the validate step accepts it.
    # The body might fail at runtime (MyHelper has no clauses) which yields
    # no Path tuples, but validate_purity should not have errored.
    try:
        out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    except PurityError:
        pytest.fail("pure_/1-marked predicate should not trigger PurityError")
    # MyHelper has no clauses and no dispatch — so the body fails for every
    # candidate, yielding zero answers.
    assert out == []


# ── Attributed-variable / constraint-posting rejection ─────────────────
#
# Risks §1 in the plan: -bottom_up rules must reject bodies that post
# attributed-var constraints. Bottom-up evaluation operates on ground
# tuples; attributed-var propagation is non-monotonic w.r.t. the
# fixpoint and breaks the semiring discipline. The purity gate is what
# enforces this — none of dif/2, CLP(FD) labelling, CLP(B) sat are on
# the default-pure whitelist, and they cannot be marked pure_/1
# truthfully.


@pytest.mark.parametrize("constraint,arity,call_args", [
    ("dif", 2, lambda a, b: (a, b)),
    ("label", 1, lambda a, b: ([a, b],)),
    ("sat", 1, lambda a, b: (a,)),
    ("#=", 2, lambda a, b: (a, b)),
])
def test_attributed_var_constraint_rejected(constraint, arity, call_args):
    """An unmarked attributed-var poster in a -bottom_up body raises PurityError."""
    mod, c = _setup_program(("edge", ["a", "b"]), ("path", ["a", "b"]))
    Edge, Path = c["edge"], c["path"]
    A, B = Var(), Var()
    Path._assertz(Clause(
        head=Path(A, B),
        body=[
            _ast_call("edge", A, B),
            _ast_call(constraint, *call_args(A, B)),
        ],
    ))
    facts = [(Edge("a", "b"), True)]
    with pytest.raises(PurityError) as exc:
        evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    assert f"{constraint}/{arity}" in str(exc.value)


# ── Non-ground tuple errors ─────────────────────────────────────────────


def test_non_ground_head_raises():
    """A head variable not bound by the body should raise NonGroundTupleError."""
    mod, c = _setup_program(("edge", ["a", "b"]), ("path", ["a", "b"]))
    Edge, Path = c["edge"], c["path"]
    A, B, C = Var(), Var(), Var()
    # Path(A, C) :- Edge(A, B)   -- C is free!
    Path._assertz(Clause(
        head=Path(A, C),
        body=[_ast_call("edge", A, B)],
    ))
    facts = [(Edge("a", "b"), True)]
    with pytest.raises(NonGroundTupleError):
        evaluate(boolean, facts, Path(Var(), Var()), module=mod)


def test_non_ground_input_fact_raises():
    mod, c = _setup_program(("edge", ["a", "b"]),)
    Edge = c["edge"]
    # Provide a fact with an unbound Var — illegal for a ground-tuple engine.
    bad_fact = (Edge("a", Var()), True)
    with pytest.raises(NonGroundTupleError):
        evaluate(boolean, [bad_fact], Edge(Var(), Var()), module=mod)


# ── Stratification ──────────────────────────────────────────────────────


def test_stratify_simple_chain():
    """SCCs returned in topological order."""
    from clausal.modules.provenance.stratify import stratify
    # A depends on B, B depends on C
    A_clauses = [Clause(head=None, body=[_ast_call("B", Var())])]
    B_clauses = [Clause(head=None, body=[_ast_call("C", Var())])]
    C_clauses = []
    program = {("A", 1): A_clauses, ("B", 1): B_clauses, ("C", 1): C_clauses}
    sccs = stratify(program)
    flat = [s[0] for s in sccs]
    # Dependencies first: C, then B, then A
    assert flat.index(("C", 1)) < flat.index(("B", 1)) < flat.index(("A", 1))


def test_stratify_recursive_scc():
    """Mutually-recursive predicates land in one SCC."""
    from clausal.modules.provenance.stratify import stratify
    A_clauses = [Clause(head=None, body=[_ast_call("B", Var())])]
    B_clauses = [Clause(head=None, body=[_ast_call("A", Var())])]
    program = {("A", 1): A_clauses, ("B", 1): B_clauses}
    sccs = stratify(program)
    assert len(sccs) == 1
    assert set(sccs[0]) == {("A", 1), ("B", 1)}


def test_stratify_rejects_cyclic_negation():
    """SCC containing a Not edge is unstratifiable."""
    from clausal.modules.provenance.stratify import stratify
    # P(X) :- not Q(X);   Q(X) :- not P(X)
    P_clauses = [Clause(head=None, body=[Not(operand=_ast_call("Q", Var()))])]
    Q_clauses = [Clause(head=None, body=[Not(operand=_ast_call("P", Var()))])]
    program = {("P", 1): P_clauses, ("Q", 1): Q_clauses}
    with pytest.raises(StratificationError) as exc:
        stratify(program)
    assert "Cyclic negation" in str(exc.value)


def test_stratify_negation_across_strata_ok():
    """Negation between distinct strata is fine."""
    from clausal.modules.provenance.stratify import stratify
    # A :- not B;   B :- nothing  -- two strata, B below A.
    A_clauses = [Clause(head=None, body=[Not(operand=_ast_call("B", Var()))])]
    B_clauses = []
    program = {("A", 1): A_clauses, ("B", 1): B_clauses}
    sccs = stratify(program)  # should succeed
    assert len(sccs) == 2


# ── Goal predicate validation ───────────────────────────────────────────


def test_goal_must_be_bottom_up_predicate():
    mod, c = _setup_program(("NotBU", ["x"], False),)
    NotBU = c["NotBU"]
    with pytest.raises(ValueError) as exc:
        evaluate(boolean, [], NotBU(Var()), module=mod)
    msg = str(exc.value)
    assert "NotBU" in msg or "bottom_up" in msg


def test_fact_must_match_registered_predicate():
    mod, c = _setup_program(("edge", ["a", "b"]), ("Other", ["x"], False))
    Edge, Other = c["edge"], c["Other"]
    with pytest.raises(ValueError):
        evaluate(boolean, [(Other(1), True)], Edge(Var(), Var()), module=mod)


# ── Python query() helper ───────────────────────────────────────────────


def test_python_query_helper():
    mod, c = _setup_program(("edge", ["a", "b"]), ("path", ["a", "b"]))
    Edge, Path = c["edge"], c["path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("edge", A, B)]))
    facts = [(Edge("a", "b"), True)]
    out = query(Path(Var(), Var()), facts=facts, semiring=boolean, module=mod)
    assert len(out) == 1


# In-source provenance.solve/4 and recover/3 are dogfooded in the
# .clausal fixtures; same for transitive-closure correctness on dense
# graphs (top_k_engine.clausal exercises a 4-edge diamond, and
# provenance_reach.clausal covers the disjoint-component case).


# ── Custom semiring contract ────────────────────────────────────────────


class _CountSemiring(Provenance):
    """Counting semiring (N, +, ·, 0, 1) — bag semantics for test purposes."""

    name = "_count"

    def zero(self): return 0
    def one(self): return 1
    def add(self, a, b): return a + b
    def mult(self, a, b): return a * b


def test_custom_semiring_count_facts():
    """Engine is generic: a count semiring runs through cleanly on input facts."""
    mod, c = _setup_program(("edge", ["a", "b"]),)
    Edge = c["edge"]
    sr = _CountSemiring()
    facts = [(Edge("a", "b"), 1), (Edge("a", "b"), 1)]
    out = evaluate(sr, facts, Edge(Var(), Var()), module=mod)
    # Two duplicate facts — counts add.
    assert len(out) == 1
    assert out[0][1] == 2
