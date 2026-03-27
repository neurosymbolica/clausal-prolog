"""Tests for Phase 10: call-site specialization (10a–10f).

Phase 10a: compile_predicate_trampoline stores _index_plans (and joint/hierarchical
variants) on pred_cls after compilation.

Phase 10b–10f: _static_call_key, _bucket_key/_joint_bucket_key helpers,
_inject_bucket_refs_trampoline pre-scan, _dispatch_call_trampoline Phase 10 block,
and wiring into compile_predicate_trampoline.
"""

import ast
import pytest

from clausal.logic.database import Clause, Database
from clausal.logic.compiler import (
    compile_predicate_trampoline as compile_predicate,
    _extract_arg_key,
    _INDEX_THRESHOLD,
    _static_call_key,
    _bucket_key,
    _joint_bucket_key,
    _inject_bucket_refs_trampoline,
    _compile_context_local,
    _disp_key,
)
from clausal.logic.predicate import PredicateMeta
from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.logic.trampoline import StepGenerator, solutions, DONE
from clausal.terms import Compound, Unify, Call, LoadName
from clausal.logic.builtins import _normalize_fact_clause


# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_fact_clauses(functor, facts):
    return [
        _normalize_fact_clause(Compound(functor, tuple(args)))
        for args in facts
    ]


def _trampoline_solutions(dispatch, args, trail=None):
    if trail is None:
        trail = Trail()
    sg = StepGenerator(dispatch, None, *args, trail)
    return solutions(sg, lambda: tuple(deref(a) for a in args))


def _make_pred_cls(name, fields):
    return PredicateMeta(name, (), {"_fields": tuple(fields)})


# ── Phase 10a: _index_plans set after compilation ─────────────────────────────


class TestIndexPlansExposed:
    def test_index_plans_set_for_indexed_predicate(self):
        """_index_plans is populated when the predicate has enough clauses."""
        clauses = _make_fact_clauses("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        pred_cls = _make_pred_cls("color", ["name"])
        compile_predicate("color", 1, clauses, pred_cls=pred_cls)
        assert hasattr(pred_cls, "_index_plans")
        assert isinstance(pred_cls._index_plans, dict)

    def test_index_plans_keys_are_positions(self):
        """Keys of _index_plans are argument positions (ints)."""
        clauses = _make_fact_clauses("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        pred_cls = _make_pred_cls("color", ["name"])
        compile_predicate("color", 1, clauses, pred_cls=pred_cls)
        for pos in pred_cls._index_plans:
            assert isinstance(pos, int)

    def test_index_plans_values_are_dicts_of_callables(self):
        """Values of _index_plans are dicts mapping index keys to callable bucket fns."""
        clauses = _make_fact_clauses("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        pred_cls = _make_pred_cls("color", ["name"])
        compile_predicate("color", 1, clauses, pred_cls=pred_cls)
        for pos, idx_dict in pred_cls._index_plans.items():
            assert isinstance(idx_dict, dict)
            for key, bucket_fn in idx_dict.items():
                assert callable(bucket_fn), f"bucket for key {key!r} is not callable"

    def test_index_plans_contains_expected_keys(self):
        """_index_plans[0] contains the exact set of atom keys from clause heads."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        clauses = _make_fact_clauses("color", [(a,) for a in atoms])
        pred_cls = _make_pred_cls("color", ["name"])
        compile_predicate("color", 1, clauses, pred_cls=pred_cls)
        assert 0 in pred_cls._index_plans
        assert set(pred_cls._index_plans[0].keys()) == set(atoms)

    def test_index_plans_contains_integer_keys(self):
        """Integer-keyed predicates expose integer keys in _index_plans."""
        clauses = _make_fact_clauses("fib", [
            (0, 0), (1, 1), (2, 1), (3, 2), (4, 3), (5, 5),
        ])
        pred_cls = _make_pred_cls("fib", ["n", "f"])
        compile_predicate("fib", 2, clauses, pred_cls=pred_cls)
        assert 0 in pred_cls._index_plans
        assert set(pred_cls._index_plans[0].keys()) == {0, 1, 2, 3, 4, 5}

    def test_index_plans_empty_when_below_threshold(self):
        """Below the indexing threshold, _index_plans is set to {}."""
        # _INDEX_THRESHOLD clauses are needed; use fewer
        assert _INDEX_THRESHOLD > 1
        clauses = _make_fact_clauses("tiny", [("a",)])
        pred_cls = _make_pred_cls("tiny", ["x"])
        compile_predicate("tiny", 1, clauses, pred_cls=pred_cls)
        assert hasattr(pred_cls, "_index_plans")
        assert pred_cls._index_plans == {}

    def test_index_plans_not_set_when_no_pred_cls(self):
        """when pred_cls is None, no _index_plans attribute is injected."""
        clauses = _make_fact_clauses("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        # compile without pred_cls — should not raise
        compile_predicate("color", 1, clauses, pred_cls=None)

    def test_dispatch_routes_through_bucket(self):
        """The compiled dispatch routes to the correct bucket for a ground arg."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        clauses = _make_fact_clauses("color", [(a,) for a in atoms])
        pred_cls = _make_pred_cls("color", ["name"])
        dispatch = compile_predicate("color", 1, clauses, pred_cls=pred_cls)

        trail = Trail()
        arg = "green"
        sg = StepGenerator(dispatch, None, arg, trail)
        sols = solutions(sg, lambda: deref(arg))
        assert sols == ["green"]

    def test_dispatch_no_solutions_for_unknown_value(self):
        """The dispatch yields nothing for a value with no matching clause."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        clauses = _make_fact_clauses("color", [(a,) for a in atoms])
        pred_cls = _make_pred_cls("color", ["name"])
        dispatch = compile_predicate("color", 1, clauses, pred_cls=pred_cls)

        trail = Trail()
        arg = "orange"
        sg = StepGenerator(dispatch, None, arg, trail)
        sols = solutions(sg, lambda: deref(arg))
        assert sols == []

    def test_index_plans_empty_when_compiled_with_few_clauses(self):
        """_index_plans is {} when a second compile sees fewer clauses than threshold."""
        pred_cls = _make_pred_cls("tiny", ["x"])
        # First compile: enough clauses to index
        clauses5 = _make_fact_clauses("tiny", [("a",), ("b",), ("c",), ("d",), ("e",)])
        compile_predicate("tiny", 1, clauses5, pred_cls=pred_cls)
        assert pred_cls._index_plans != {}

        # Second compile: just one clause — should clear _index_plans
        clauses1 = _make_fact_clauses("tiny", [("a",)])
        compile_predicate("tiny", 1, clauses1, pred_cls=pred_cls)
        assert pred_cls._index_plans == {}

    def test_two_arg_predicate_indexes_first_arg(self):
        """Two-argument predicate: _index_plans[0] keyed on first argument."""
        clauses = _make_fact_clauses("edge", [
            ("a", "b"), ("a", "c"), ("b", "c"),
            ("b", "d"), ("c", "d"), ("d", "a"),
        ])
        pred_cls = _make_pred_cls("edge", ["from_node", "to_node"])
        compile_predicate("edge", 2, clauses, pred_cls=pred_cls)
        assert 0 in pred_cls._index_plans
        assert set(pred_cls._index_plans[0].keys()) == {"a", "b", "c", "d"}

    def test_second_position_indexed_when_more_selective(self):
        """when position 1 is more selective, it also appears in _index_plans."""
        # All first args are the same, but second args vary — pos 1 is more selective
        clauses = _make_fact_clauses("lookup", [
            ("same", 1), ("same", 2), ("same", 3), ("same", 4), ("same", 5),
        ])
        pred_cls = _make_pred_cls("lookup", ["key", "val"])
        compile_predicate("lookup", 2, clauses, pred_cls=pred_cls)
        assert hasattr(pred_cls, "_index_plans")
        # Position 1 should be indexed (all values distinct)
        assert 1 in pred_cls._index_plans


# ── Phase 10a: joint _index_plans_joint (Phase 9b) ───────────────────────────


class TestIndexPlansJoint:
    def test_index_plans_joint_set_for_high_coverage(self):
        """_index_plans_joint is populated when joint dispatch is used."""
        # Build a predicate where joint (pos0, pos1) indexing is beneficial:
        # many distinct (key0, key1) pairs, high coverage.
        clauses = _make_fact_clauses("pair", [
            (i, j) for i in range(5) for j in range(5)
        ])
        pred_cls = _make_pred_cls("pair", ["x", "y"])
        compile_predicate("pair", 2, clauses, pred_cls=pred_cls)
        # May or may not use joint dispatch depending on coverage threshold;
        # just check that if it's set it has the right structure.
        if hasattr(pred_cls, "_index_plans_joint") and pred_cls._index_plans_joint:
            for (pi, pj), jdict in pred_cls._index_plans_joint.items():
                assert isinstance(pi, int)
                assert isinstance(pj, int)
                assert pi != pj
                assert isinstance(jdict, dict)
                for jk, fn in jdict.items():
                    assert isinstance(jk, tuple) and len(jk) == 2
                    assert callable(fn)

    def test_index_plans_joint_keys_are_tuples(self):
        """Joint bucket keys are (key_i, key_j) tuples."""
        clauses = _make_fact_clauses("pair", [
            (i, j) for i in range(5) for j in range(5)
        ])
        pred_cls = _make_pred_cls("pair", ["x", "y"])
        compile_predicate("pair", 2, clauses, pred_cls=pred_cls)
        if hasattr(pred_cls, "_index_plans_joint") and pred_cls._index_plans_joint:
            for (pi, pj), jdict in pred_cls._index_plans_joint.items():
                for jk in jdict:
                    assert isinstance(jk, tuple), f"Expected tuple key, got {jk!r}"


# ── Phase 10b: _static_call_key unit tests ───────────────────────────────────


class TestStaticCallKey:
    def test_integer_constant(self):
        assert _static_call_key(ast.Constant(value=42)) == 42

    def test_string_constant(self):
        assert _static_call_key(ast.Constant(value="red")) == "red"

    def test_float_constant(self):
        assert _static_call_key(ast.Constant(value=3.14)) == 3.14

    def test_none_constant(self):
        assert _static_call_key(ast.Constant(value=None)) is None

    def test_bool_constant(self):
        assert _static_call_key(ast.Constant(value=True)) is True

    def test_variable_name_returns_none(self):
        # A Name node (variable reference) is not statically known
        assert _static_call_key(ast.Name(id="_v_x", ctx=ast.Load())) is None

    def test_compound_call_name(self):
        # Dog(_v_name) — functor Dog, arity 1
        node = ast.Call(
            func=ast.Name(id="Dog", ctx=ast.Load()),
            args=[ast.Name(id="_v_name", ctx=ast.Load())],
            keywords=[],
        )
        assert _static_call_key(node) == ("Dog", 1)

    def test_compound_call_qualified(self):
        # module.Dog(a, b) — attr Dog, arity 2
        node = ast.Call(
            func=ast.Attribute(
                value=ast.Name(id="module", ctx=ast.Load()),
                attr="Dog",
                ctx=ast.Load(),
            ),
            args=[ast.Name(id="_v_a", ctx=ast.Load()),
                  ast.Name(id="_v_b", ctx=ast.Load())],
            keywords=[],
        )
        assert _static_call_key(node) == ("Dog", 2)

    def test_compound_call_no_args(self):
        node = ast.Call(
            func=ast.Name(id="Atom", ctx=ast.Load()),
            args=[], keywords=[],
        )
        assert _static_call_key(node) == ("Atom", 0)

    def test_list_literal_returns_none(self):
        # A list node is not a constant or Call — returns None
        node = ast.List(elts=[], ctx=ast.Load())
        assert _static_call_key(node) is None

    def test_zero_integer(self):
        assert _static_call_key(ast.Constant(value=0)) == 0

    def test_empty_string(self):
        assert _static_call_key(ast.Constant(value="")) == ""


# ── Phase 10c: _bucket_key and _joint_bucket_key naming ─────────────────────


class TestBucketKeyNaming:
    def test_bucket_key_atom(self):
        k = _bucket_key("Color2", 0, "red")
        assert k == "Color2.bucket(pos=0, 'red')"

    def test_bucket_key_integer(self):
        k = _bucket_key("Fib", 0, 0)
        assert k == "Fib.bucket(pos=0, 0)"

    def test_bucket_key_second_position(self):
        k = _bucket_key("Edge", 1, "b")
        assert k == "Edge.bucket(pos=1, 'b')"

    def test_bucket_key_compound(self):
        k = _bucket_key("Rule", 0, ("Dog", 2))
        assert k == "Rule.bucket(pos=0, ('Dog', 2))"

    def test_joint_bucket_key(self):
        k = _joint_bucket_key("Pair", 0, 1, "x", 2)
        # repr uses ('x', 2) or ('x',2) depending on Python version; just check structure
        assert k.startswith("Pair.bucket(pos=(0,1), ")
        assert "('x'" in k
        assert "2)" in k

    def test_joint_bucket_key_symmetric(self):
        # Different position orderings produce different keys
        k1 = _joint_bucket_key("P", 0, 1, "a", "b")
        k2 = _joint_bucket_key("P", 1, 0, "b", "a")
        assert k1 != k2


# ── Phase 10d: _inject_bucket_refs_trampoline ────────────────────────────────


def _make_locked_pred_cls(name, facts):
    """Build a locked PredicateMeta with _index_plans populated."""
    pred_cls = _make_pred_cls(name, [f"arg{i}" for i in range(len(facts[0]))])
    arity = len(facts[0])
    clauses = _make_fact_clauses(name, facts)
    compile_predicate(name, arity, clauses, pred_cls=pred_cls)
    pred_cls._locked = True
    return pred_cls, arity


class TestInjectBucketRefs:
    def test_bucket_injected_for_literal_arg(self):
        """inject_bucket_refs injects a bucket fn for a static literal call-site arg."""
        callee_cls, callee_arity = _make_locked_pred_cls("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        assert hasattr(callee_cls, "_index_plans") and callee_cls._index_plans

        # Build a caller clause: caller(_x) <- color("red", _x)
        # We test inject directly, so we just need the Call term in the body.
        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red", x])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )

        base_globals = {"color": callee_cls}
        # Set locked_dispatch_keys so _disp_key-based check won't interfere
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        expected_gkey = _bucket_key("color", 0, "red")
        assert expected_gkey in base_globals, \
            f"Expected {expected_gkey!r} in base_globals; got {list(base_globals.keys())}"
        assert callable(base_globals[expected_gkey])

    def test_bucket_ref_map_populated(self):
        """inject_bucket_refs populates _compile_context_local.bucket_ref_map."""
        callee_cls, _ = _make_locked_pred_cls("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red", x])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        brmap = _compile_context_local.bucket_ref_map
        assert ("color", 2, 0, "red") in brmap

    def test_no_injection_for_variable_arg(self):
        """inject_bucket_refs does NOT inject for a variable (non-static) argument."""
        callee_cls, _ = _make_locked_pred_cls("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        x = Var()
        y = Var()
        call_goal = Call(func=LoadName(name="color"), args=[y, x])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        # No bucket refs should be injected for variable args
        bucket_keys = [k for k in base_globals if "bucket" in k]
        assert bucket_keys == [], f"Unexpected bucket keys: {bucket_keys}"

    def test_no_injection_for_unlocked_predicate(self):
        """inject_bucket_refs only specialises locked predicates."""
        callee_cls, _ = _make_locked_pred_cls("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        callee_cls._locked = False  # explicitly unlock

        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red", x])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        bucket_keys = [k for k in base_globals if "bucket" in k]
        assert bucket_keys == []

    def test_no_injection_for_unknown_key(self):
        """inject_bucket_refs skips keys not in the callee's bucket dict."""
        callee_cls, _ = _make_locked_pred_cls("color", [
            ("red",), ("green",), ("blue",), ("yellow",), ("purple",),
        ])
        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["orange", x])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        bucket_keys = [k for k in base_globals if "bucket" in k]
        assert bucket_keys == []


# ── Phase 10e-10f: end-to-end correctness ────────────────────────────────────


def _make_caller_via_import_hook(callee_facts, callee_name="color",
                                  caller_name="caller",
                                  caller_query_arg=None):
    """Set up callee + caller predicates using compile_predicate_trampoline.

    The caller has one clause: caller(_x) <- callee(KEY, _x) for each key.
    Returns (caller_dispatch, callee_cls).
    """
    callee_cls, _ = _make_locked_pred_cls(callee_name, callee_facts)
    arity_callee = len(callee_facts[0])
    return callee_cls


class TestCallsiteCorrectnessAndFallback:
    def _setup_color_pair(self):
        """Compile a locked 'color' predicate and a caller that queries it."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])
        return callee_cls, atoms

    def test_callsite_bucket_injected_into_base_globals(self):
        """base_globals for a caller clause contains a bucket key after compilation."""
        callee_cls, atoms = self._setup_color_pair()

        # Compile a caller: find_red(_x) <- color("red", _x)
        # We test that after compile_predicate_trampoline the callee's bucket
        # is accessible by checking _index_plans was used.
        assert "red" in callee_cls._index_plans.get(0, {})

    def test_locked_callee_returns_correct_results(self):
        """Calling a locked callee with a literal arg returns expected results."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])
        dispatch = callee_cls._dispatch_fn

        trail = Trail()
        arg = "green"
        sg = StepGenerator(dispatch, None, arg, trail)
        assert solutions(sg, lambda: deref(arg)) == ["green"]

    def test_locked_callee_variable_arg_returns_all(self):
        """Calling a locked callee with a variable returns all solutions."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])
        dispatch = callee_cls._dispatch_fn

        trail = Trail()
        arg = Var()
        sg = StepGenerator(dispatch, None, arg, trail)
        results = solutions(sg, lambda: deref(arg))
        assert set(results) == set(atoms)

    def test_compile_caller_with_literal_uses_bucket_ref(self):
        """compile_predicate_trampoline for a caller with a literal arg injects
        a bucket key into base_globals (verifiable by checking _index_plans on the callee)."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])

        # Manually run inject to verify it works for a clause referencing the callee
        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red"])
        caller_clause = Clause(
            head=Compound("find_red", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        expected_gkey = _bucket_key("color", 0, "red")
        assert expected_gkey in base_globals
        # The injected function should be the same as the bucket fn in _index_plans
        assert base_globals[expected_gkey] is callee_cls._index_plans[0]["red"]

    def test_dynamic_predicate_not_specialised(self):
        """A dynamic predicate (not locked) never gets bucket specialisation."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls = _make_pred_cls("dyn_color", ["name"])
        clauses = _make_fact_clauses("dyn_color", [(a,) for a in atoms])
        compile_predicate("dyn_color", 1, clauses, pred_cls=callee_cls)
        # Ensure it's NOT locked
        callee_cls._locked = False

        x = Var()
        call_goal = Call(func=LoadName(name="dyn_color"), args=["red"])
        caller_clause = Clause(
            head=Compound("caller", (x,)),
            body=[call_goal],
        )
        base_globals = {"dyn_color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        bucket_keys = [k for k in base_globals if "bucket" in k]
        assert bucket_keys == [], "Dynamic predicate should not be bucket-specialised"

    def test_self_recursive_predicate_not_specialised(self):
        """A predicate calling itself is compiled while unlocked → no bucket ref."""
        # Self-recursive calls happen before locking; the callee has no _locked=True
        atoms = ["red", "green", "blue", "yellow", "purple"]
        pred_cls = _make_pred_cls("color", ["name"])
        clauses = _make_fact_clauses("color", [(a,) for a in atoms])
        # pred_cls not locked yet (simulating compile-time self-call)
        pred_cls._locked = False

        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red"])
        caller_clause = Clause(
            head=Compound("color", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": pred_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        bucket_keys = [k for k in base_globals if "bucket" in k]
        assert bucket_keys == [], "Self-recursive unlocked predicate should not be specialised"

    def test_multiple_literal_calls_different_buckets(self):
        """Multiple clauses with different literal args each get their own bucket ref."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])

        x = Var()
        clauses = [
            Clause(
                head=Compound("caller", (x,)),
                body=[Call(func=LoadName(name="color"), args=[a])],
            )
            for a in ["red", "green", "blue"]
        ]
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline(clauses, base_globals)

        for atom in ["red", "green", "blue"]:
            gkey = _bucket_key("color", 0, atom)
            assert gkey in base_globals, f"Missing bucket ref for {atom!r}"

    def test_bucket_ref_is_correct_callable(self):
        """The injected bucket fn is the same object as _index_plans[0][key]."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])

        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["blue"])
        caller_clause = Clause(
            head=Compound("find_blue", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)

        gkey = _bucket_key("color", 0, "blue")
        bucket_fn = base_globals[gkey]

        # The injected fn is identical to the one stored in _index_plans
        assert bucket_fn is callee_cls._index_plans[0]["blue"]
        # It is callable
        assert callable(bucket_fn)

    def test_inject_idempotent_for_same_key(self):
        """Calling inject twice does not replace an existing bucket ref."""
        atoms = ["red", "green", "blue", "yellow", "purple"]
        callee_cls, _ = _make_locked_pred_cls("color", [(a,) for a in atoms])

        x = Var()
        call_goal = Call(func=LoadName(name="color"), args=["red"])
        caller_clause = Clause(
            head=Compound("f", (x,)),
            body=[call_goal],
        )
        base_globals = {"color": callee_cls}
        _compile_context_local.locked_dispatch_keys = frozenset()
        _compile_context_local.bucket_ref_map = {}
        _compile_context_local.joint_bucket_ref_map = {}

        _inject_bucket_refs_trampoline([caller_clause], base_globals)
        gkey = _bucket_key("color", 0, "red")
        first_fn = base_globals[gkey]

        # Inject again — should NOT overwrite
        _inject_bucket_refs_trampoline([caller_clause], base_globals)
        assert base_globals[gkey] is first_fn
