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


# ── Single rule, no recursion ───────────────────────────────────────────


def test_direct_edge_reachability():
    mod, c = _setup_program(("Edge", ["s", "t"]), ("Path", ["s", "t"]))
    Edge, Path = c["Edge"], c["Path"]
    s, t = Var(), Var()
    Path._assertz(Clause(head=Path(s, t), body=[_ast_call("Edge", s, t)]))
    facts = [(Edge("a", "b"), True), (Edge("b", "c"), True)]
    out = evaluate(boolean, facts, Path("a", Var()), module=mod)
    assert len(out) == 1
    (term, tag), = out
    assert (term.s, term.t) == ("a", "b")
    assert tag is True


# ── Recursive transitive closure ────────────────────────────────────────


def test_transitive_closure_three_hop():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [(Edge("a", "b"), True), (Edge("b", "c"), True), (Edge("c", "d"), True)]
    out = evaluate(boolean, facts, Path("a", Var()), module=mod)
    targets = sorted(p.b for p, _ in out)
    assert targets == ["b", "c", "d"]
    assert all(tag is True for _, tag in out)


def test_transitive_closure_with_cycle():
    """A cycle should not blow up the fixpoint — set semantics."""
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [
        (Edge("a", "b"), True),
        (Edge("b", "a"), True),  # cycle a-b-a
    ]
    out = evaluate(boolean, facts, Path("a", Var()), module=mod)
    targets = sorted(p.b for p, _ in out)
    assert targets == ["a", "b"]


def test_no_path_when_disconnected():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [(Edge("a", "b"), True), (Edge("c", "d"), True)]
    out = evaluate(boolean, facts, Path("a", "d"), module=mod)
    assert out == []


def test_multiple_starts():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [(Edge(0, 1), True), (Edge(1, 2), True), (Edge(10, 11), True)]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    pairs = sorted((p.a, p.b) for p, _ in out)
    assert pairs == [(0, 1), (0, 2), (1, 2), (10, 11)]


# ── Mutual recursion across two predicates ──────────────────────────────


def test_mutual_recursion_even_odd():
    """Even/Odd over Pred (predecessor) — mutual recursion across two SCC members."""
    mod, c = _setup_program(
        ("Pred", ["a", "b"]),
        ("Even", ["x"]),
        ("Odd", ["x"]),
        ("Zero", ["x"]),
    )
    Pred, Even, Odd, Zero = c["Pred"], c["Even"], c["Odd"], c["Zero"]
    # Zero(0)
    X = Var()
    Even._assertz(Clause(head=Even(X), body=[_ast_call("Zero", X)]))
    # Odd(N)  :- Pred(N, M), Even(M)
    N, M = Var(), Var()
    Odd._assertz(Clause(head=Odd(N), body=[_ast_call("Pred", N, M), _ast_call("Even", M)]))
    # Even(N) :- Pred(N, M), Odd(M)
    N2, M2 = Var(), Var()
    Even._assertz(Clause(head=Even(N2), body=[_ast_call("Pred", N2, M2), _ast_call("Odd", M2)]))
    facts = [
        (Zero(0), True),
        (Pred(1, 0), True), (Pred(2, 1), True), (Pred(3, 2), True),
        (Pred(4, 3), True), (Pred(5, 4), True),
    ]
    even_out = evaluate(boolean, facts, Even(Var()), module=mod)
    odd_out = evaluate(boolean, facts, Odd(Var()), module=mod)
    even_vals = sorted(t.x for t, _ in even_out)
    odd_vals = sorted(t.x for t, _ in odd_out)
    assert even_vals == [0, 2, 4]
    assert odd_vals == [1, 3, 5]


# ── Empty input handling ────────────────────────────────────────────────


def test_no_facts_no_answers():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    out = evaluate(boolean, [], Path(Var(), Var()), module=mod)
    assert out == []


def test_facts_only_no_rules_for_query_predicate():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    # Path has no rules. Query against Path will yield empty.
    facts = [(Edge("a", "b"), True)]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    assert out == []


def test_facts_only_with_query_on_input_predicate():
    mod, c = _setup_program(("Edge", ["a", "b"]),)
    Edge = c["Edge"]
    facts = [(Edge("a", "b"), True), (Edge("b", "c"), True)]
    out = evaluate(boolean, facts, Edge(Var(), Var()), module=mod)
    pairs = sorted((t.a, t.b) for t, _ in out)
    assert pairs == [("a", "b"), ("b", "c")]


# ── Goal binding modes ──────────────────────────────────────────────────


def test_goal_with_specific_target():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [(Edge(0, 1), True), (Edge(1, 2), True)]
    # Query with both args bound — single-tuple match
    out = evaluate(boolean, facts, Path(0, 2), module=mod)
    assert len(out) == 1
    out_neg = evaluate(boolean, facts, Path(0, 99), module=mod)
    assert out_neg == []


# ── Tag merging via semiring.add ────────────────────────────────────────


def test_duplicate_facts_merge_via_add():
    mod, c = _setup_program(("Edge", ["a", "b"]),)
    Edge = c["Edge"]
    facts = [(Edge("a", "b"), True), (Edge("a", "b"), True), (Edge("a", "b"), True)]
    out = evaluate(boolean, facts, Edge(Var(), Var()), module=mod)
    # Boolean: True ∨ True = True, single tuple
    assert len(out) == 1
    assert out[0][1] is True


# ── Purity errors ───────────────────────────────────────────────────────


def test_purity_error_on_unmarked_callee():
    mod, c = _setup_program(("Path", ["a", "b"]),)
    Path = c["Path"]
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
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    # Path(A, B) :- Edge(A, B), length([A, B], 2)
    # length/2 is on the default-pure whitelist.
    A, B = Var(), Var()
    Path._assertz(Clause(
        head=Path(A, B),
        body=[
            _ast_call("Edge", A, B),
            _ast_call("length", [A, B], 2),
        ],
    ))
    facts = [(Edge("a", "b"), True)]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    assert len(out) == 1


def test_pure_marked_callee_accepted():
    """A user predicate marked via `pure_/1` is callable from -bottom_up bodies."""
    mod, c = _setup_program(
        ("Edge", ["a", "b"]),
        ("Path", ["a", "b"]),
        ("MyHelper", ["x"], False),  # not -bottom_up
    )
    Edge, Path, MyHelper = c["Edge"], c["Path"], c["MyHelper"]
    setattr(MyHelper, PURE_FLAG, True)
    # MyHelper has no clauses; it'll fail when called. That's fine — the
    # purity check only validates the *call site*, not whether the call
    # would succeed.
    A, B = Var(), Var()
    Path._assertz(Clause(
        head=Path(A, B),
        body=[_ast_call("Edge", A, B), _ast_call("MyHelper", A)],
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


# ── Non-ground tuple errors ─────────────────────────────────────────────


def test_non_ground_head_raises():
    """A head variable not bound by the body should raise NonGroundTupleError."""
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B, C = Var(), Var(), Var()
    # Path(A, C) :- Edge(A, B)   -- C is free!
    Path._assertz(Clause(
        head=Path(A, C),
        body=[_ast_call("Edge", A, B)],
    ))
    facts = [(Edge("a", "b"), True)]
    with pytest.raises(NonGroundTupleError):
        evaluate(boolean, facts, Path(Var(), Var()), module=mod)


def test_non_ground_input_fact_raises():
    mod, c = _setup_program(("Edge", ["a", "b"]),)
    Edge = c["Edge"]
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
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Other", ["x"], False))
    Edge, Other = c["Edge"], c["Other"]
    with pytest.raises(ValueError):
        evaluate(boolean, [(Other(1), True)], Edge(Var(), Var()), module=mod)


# ── Python query() helper ───────────────────────────────────────────────


def test_python_query_helper():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    facts = [(Edge("a", "b"), True)]
    out = query(Path(Var(), Var()), facts=facts, semiring=boolean, module=mod)
    assert len(out) == 1


# ── In-source provenance.solve/4 builtin ────────────────────────────────


def test_solve_4_builtin_reach(tmp_path):
    """Use provenance.solve/4 from .clausal source."""
    src = (
        '-import_from(provenance, [bottom_up_, solve, boolean])\n'
        '-module(test_solve_4, [Edge(A, B), Path(A, B)])\n'
        'bottom_up_(Edge)\n'
        'bottom_up_(Path)\n'
        'Path(A, B) <- Edge(A, B)\n'
        'Path(A, C) <- (Edge(A, B), Path(B, C))\n'
    )
    p = tmp_path / "test_solve_4.clausal"
    p.write_text(src)
    from clausal.import_hook import _load_module
    from clausal.logic.solve import call as logic_call
    from clausal.logic.variables import Var, deref
    mod = _load_module("test_solve_4", str(p))
    cm = mod.__dict__["$module"]
    Edge = mod.Edge
    Path = mod.Path

    # provenance.solve(boolean, FACTS, Path("a", _), R)
    from clausal.modules.provenance import solve as prov_solve, boolean as bool_sr
    facts = [
        (Edge("a", "b"), True),
        (Edge("b", "c"), True),
    ]
    R = Var()
    success = False
    for _ in logic_call(prov_solve, bool_sr, facts, Path("a", Var()), R, module=cm):
        success = True
        result = deref(R)
    assert success
    assert isinstance(result, list)
    targets = sorted(t.B for (t, _) in result)
    assert targets == ["b", "c"]


# ── Recover/3 ───────────────────────────────────────────────────────────


def test_recover_3_identity_for_boolean():
    from clausal.modules.provenance import recover, boolean as bool_sr
    from clausal.logic.solve import call as logic_call
    from clausal.logic.variables import Var, deref
    Out = Var()
    success = False
    for _ in logic_call(recover, bool_sr, True, Out):
        success = True
        result = deref(Out)
    assert success
    assert result is True


# ── Semi-naive correctness: all derivable tuples appear ─────────────────


def test_dense_graph_all_pairs_reachable():
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    # Complete graph on {0, 1, 2}
    facts = [
        (Edge(i, j), True)
        for i in range(3)
        for j in range(3)
        if i != j
    ]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    pairs = sorted((p.a, p.b) for p, _ in out)
    # All ordered pairs (i, j) with i ≠ j: 6 of them, plus self-loops via cycle
    expected = sorted({(i, j) for i in range(3) for j in range(3)})
    assert pairs == expected


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
    mod, c = _setup_program(("Edge", ["a", "b"]),)
    Edge = c["Edge"]
    sr = _CountSemiring()
    facts = [(Edge("a", "b"), 1), (Edge("a", "b"), 1)]
    out = evaluate(sr, facts, Edge(Var(), Var()), module=mod)
    # Two duplicate facts — counts add.
    assert len(out) == 1
    assert out[0][1] == 2


# ── Saturation checks the relation reaches fixpoint ─────────────────────


def test_fixpoint_terminates_on_complete_graph():
    """Even on a strongly-connected graph the engine must terminate."""
    mod, c = _setup_program(("Edge", ["a", "b"]), ("Path", ["a", "b"]))
    Edge, Path = c["Edge"], c["Path"]
    A, B = Var(), Var()
    Path._assertz(Clause(head=Path(A, B), body=[_ast_call("Edge", A, B)]))
    A2, M, B2 = Var(), Var(), Var()
    Path._assertz(Clause(
        head=Path(A2, B2),
        body=[_ast_call("Edge", A2, M), _ast_call("Path", M, B2)],
    ))
    facts = [
        (Edge(0, 1), True), (Edge(1, 0), True),
        (Edge(1, 2), True), (Edge(2, 1), True),
    ]
    out = evaluate(boolean, facts, Path(Var(), Var()), module=mod)
    pairs = sorted((p.a, p.b) for p, _ in out)
    # All combinations among {0, 1, 2}
    assert (0, 0) in pairs
    assert (0, 2) in pairs
    assert (2, 0) in pairs
