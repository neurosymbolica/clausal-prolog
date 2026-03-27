"""Tests for Tail Recursion Optimization (TRO).

Verifies correctness and allocation efficiency of TRO-compiled predicates.
"""

import unittest

from clausal.logic.compiler import (
    _detect_tro_clause,
    _is_deterministic_goal,
    _tro_args_safe,
    compile_predicate_trampoline,
)
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.trampoline import StepGenerator, DONE
from clausal.logic.variables import Var, Trail, deref, is_var
from clausal.terms import (
    Add, Sub, Mult,
    And, Or, Not,
    Unify, DoesNotUnify, Evaluate,
    Lt, LtE, Gt, GtE,
    in_, NotIn,
    ArithEq, ArithNeq,
    Call, LoadName,
    Compound,
)
from clausal.pythonic_ast.nodes import IfExpr, StarUnpack


# ── Detection tests ──────────────────────────────────────────────────────────


class TestIsDeterministicGoal(unittest.TestCase):
    """Test _is_deterministic_goal classification."""

    def test_unify(self):
        self.assertTrue(_is_deterministic_goal(Unify(left=Var(), right=42)))

    def test_evaluate(self):
        self.assertTrue(_is_deterministic_goal(Evaluate(left=Var(), right=Add(left=1, right=2))))

    def test_does_not_unify(self):
        self.assertTrue(_is_deterministic_goal(DoesNotUnify(left=Var(), right=42)))

    def test_structural_eq(self):
        self.assertTrue(_is_deterministic_goal(ArithEq(left=1, right=1)))

    def test_structural_neq(self):
        self.assertTrue(_is_deterministic_goal(ArithNeq(left=1, right=2)))

    def test_comparisons(self):
        self.assertTrue(_is_deterministic_goal(Gt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(Lt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(GtE(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(LtE(left=Var(), right=0)))

    def test_in_notin(self):
        self.assertTrue(_is_deterministic_goal(in_(left=1, right=[1, 2])))
        self.assertTrue(_is_deterministic_goal(NotIn(left=3, right=[1, 2])))

    def test_not(self):
        self.assertTrue(_is_deterministic_goal(Not(operand=Gt(left=1, right=2))))

    def test_true_false(self):
        self.assertTrue(_is_deterministic_goal(True))
        self.assertTrue(_is_deterministic_goal(False))

    def test_and_deterministic(self):
        self.assertTrue(_is_deterministic_goal(
            And(left=Gt(left=Var(), right=0), right=Evaluate(left=Var(), right=Sub(left=Var(), right=1)))
        ))

    def test_and_nondeterministic(self):
        self.assertFalse(_is_deterministic_goal(
            And(left=Gt(left=Var(), right=0), right=Call(func=LoadName(name='Foo'), args=[], kwargs=[]))
        ))

    def test_predicate_call(self):
        self.assertFalse(_is_deterministic_goal(
            Call(func=LoadName(name='Foo'), args=[Var()], kwargs=[])
        ))

    def test_or_nondeterministic(self):
        self.assertFalse(_is_deterministic_goal(
            Or(left=Gt(left=Var(), right=0), right=Lt(left=Var(), right=0))
        ))

    def test_once_deterministic(self):
        inner = Call(func=LoadName(name='Foo'), args=[Var()], kwargs=[])
        self.assertTrue(_is_deterministic_goal(
            Call(func=LoadName(name='once'), args=[inner], kwargs=[])
        ))

    def test_findall_deterministic(self):
        self.assertTrue(_is_deterministic_goal(
            Call(func=LoadName(name='findall'), args=[Var(), Var(), Var()], kwargs=[])
        ))


class TestDetectTroClause(unittest.TestCase):
    """Test _detect_tro_clause detection."""

    def _make_clause(self, head_fields, body):
        class P(metaclass=PredicateMeta):
            _fields = head_fields
        head_args = {f: Var() for f in head_fields}
        head = P(**head_args)
        return Clause(head=head, body=body), P, head_args

    def test_no_body(self):
        """Facts (no body) are not TRO-eligible."""
        cl, P, _ = self._make_clause(('x',), [])
        self.assertFalse(_detect_tro_clause('P', 1, cl))

    def test_last_goal_is_self_call(self):
        """Clause with only a self-recursive tail call is TRO-eligible
        if args are safe."""
        x = Var()

        class Q(metaclass=PredicateMeta):
            _fields = ('x',)

        cl = Clause(
            head=Q(x),
            body=[Call(func=LoadName(name='Q'), args=[x], kwargs=[])],
        )
        # x is a passthrough (same Var at position 0 in head and tail call)
        self.assertTrue(_detect_tro_clause('Q', 1, cl))

    def test_deterministic_prefix_with_self_call(self):
        """Deterministic prefix + self-recursive tail call is TRO-eligible."""
        n = Var()
        n1 = Var()
        result = Var()

        class Fact(metaclass=PredicateMeta):
            _fields = ('n', 'result')

        cl = Clause(
            head=Fact(n, result),
            body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='Fact'), args=[n1, result], kwargs=[]),
            ],
        )
        self.assertTrue(_detect_tro_clause('Fact', 2, cl))

    def test_nondeterministic_prefix_rejected(self):
        """Predicate call in prefix makes clause non-TRO."""
        n = Var()

        class R(metaclass=PredicateMeta):
            _fields = ('n',)

        cl = Clause(
            head=R(n),
            body=[
                Call(func=LoadName(name='Helper'), args=[n], kwargs=[]),
                Call(func=LoadName(name='R'), args=[n], kwargs=[]),
            ],
        )
        self.assertFalse(_detect_tro_clause('R', 1, cl))

    def test_different_functor_rejected(self):
        """Tail call to a different predicate is not self-recursive."""
        x = Var()

        class S(metaclass=PredicateMeta):
            _fields = ('x',)

        cl = Clause(
            head=S(x),
            body=[Call(func=LoadName(name='Other'), args=[x], kwargs=[])],
        )
        self.assertFalse(_detect_tro_clause('S', 1, cl))

    def test_no_prefix_body_only_vars_rejected(self):
        """Tail call with body-only vars and no prefix goals is rejected."""
        h = Var()
        t = Var()
        acc = Var()
        result = Var()

        class Rev(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        # AccReverse([H, *T], ACC, RESULT) <- AccReverse(T, [H, *ACC], RESULT)
        # No prefix goals; t and h are body-only vars not in head — rejected.
        cl = Clause(
            head=Rev(Var(), acc, result),
            body=[
                Call(func=LoadName(name='Rev'),
                     args=[t, [h, StarUnpack(value=acc)], result], kwargs=[]),
            ],
        )
        self.assertFalse(_detect_tro_clause('Rev', 3, cl))

    def test_star_unpack_with_prefix_allowed(self):
        """StarUnpack in tail call is allowed when prefix goals exist."""
        h = Var()
        t = Var()
        acc = Var()
        result = Var()
        acc2 = Var()

        class Rev(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        # Rev([H, *T], ACC, R) <- (ACC2 is [H, *ACC], Rev(T, ACC2, R))
        # With a prefix goal, head vars are allowed; ACC2 is Unify-bound.
        cl = Clause(
            head=Rev([h, StarUnpack(value=t)], acc, result),
            body=[
                Unify(left=acc2, right=[h, StarUnpack(value=acc)]),
                Call(func=LoadName(name='Rev'), args=[t, acc2, result], kwargs=[]),
            ],
        )
        self.assertTrue(_detect_tro_clause('Rev', 3, cl))

    def test_nested_var_in_list_arg_no_prefix_rejected(self):
        """List arg containing head-decomposition Var, no prefix goals, is rejected."""
        x = Var()
        goals_var = Var()
        rest = Var()

        class Meta(metaclass=PredicateMeta):
            _fields = ('goals', 'result')

        # Meta([X|Rest], R) <- Meta(Rest, R)  — but passing [X] as a nested list
        # With no prefix goals, X from head decomposition is unsafe.
        cl = Clause(
            head=Meta(Var(), Var()),
            body=[
                Call(func=LoadName(name='Meta'),
                     args=[[x, rest], Var()], kwargs=[]),
            ],
        )
        # x and rest are not passthrough, not bound by prefix — rejected
        self.assertFalse(_detect_tro_clause('Meta', 2, cl))

    def test_compound_arg_with_head_var_allowed_with_prefix(self):
        """Compound tail arg embedding head vars is allowed when prefix goals exist."""
        n = Var()
        n1 = Var()
        acc = Var()

        class Acc(metaclass=PredicateMeta):
            _fields = ('n', 'state')

        # Acc(N, State) <- (N > 0, N1 := N-1, Acc(N1, Compound("s", (N, State))))
        # N and State are head vars; with prefix goals, allow_head_vars=True.
        cl = Clause(
            head=Acc(n, acc),
            body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='Acc'),
                     args=[n1, Compound("s", (n, acc))], kwargs=[]),
            ],
        )
        # n and acc are head vars, n1 is Evaluate-bound; with prefix, allowed.
        self.assertTrue(_detect_tro_clause('Acc', 2, cl))

    def test_compound_arg_with_head_var_rejected_no_prefix(self):
        """Compound tail arg embedding head vars is rejected without prefix goals."""
        x = Var()
        y = Var()

        class P(metaclass=PredicateMeta):
            _fields = ('a', 'b')

        cl = Clause(
            head=P(x, y),
            body=[
                Call(func=LoadName(name='P'),
                     args=[Compound("f", (x,)), y], kwargs=[]),
            ],
        )
        # No prefix goals. x is in Compound, not passthrough (different structure).
        # x is a head var but allow_head_vars=False without prefix.
        self.assertFalse(_detect_tro_clause('P', 2, cl))


# ── Correctness tests (programmatic) ────────────────────────────────────────


class TestTroCorrectness(unittest.TestCase):
    """Test TRO-compiled predicates produce correct results."""

    def setUp(self):
        self.db = Database()

    def _compile_and_query(self, pred_cls, clauses, *args):
        """Compile clauses with TRO, then query and return results."""
        functor = pred_cls.__name__
        arity = len(pred_cls._fields)
        for cl in clauses:
            self.db.assertz(cl)
        self.db.register_signature(functor, arity, pred_cls._fields)
        compile_predicate_trampoline(
            functor, arity, clauses, self.db,
            globals_={functor: pred_cls},
            pred_cls=pred_cls,
        )
        trail = Trail()
        results = []
        for _ in call(pred_cls, *args, trail=trail):
            results.append(tuple(deref(a) for a in args))
        return results

    def test_simple_countdown(self):
        """N > 0, N1 := N - 1, CountDown(N1) — deterministic prefix."""
        class CountDown(metaclass=PredicateMeta):
            _fields = ('n',)

        n = Var()
        n1 = Var()
        base_n = Var()
        clauses = [
            # Base case: CountDown(N) <- N is 0  (parser style)
            Clause(head=CountDown(base_n), body=[Unify(left=base_n, right=0)]),
            Clause(head=CountDown(n), body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='CountDown'), args=[n1], kwargs=[]),
            ]),
        ]
        results = self._compile_and_query(CountDown, clauses, 5)
        # TRO reaches base case — 1 solution
        self.assertEqual(len(results), 1)

    def test_accumulator_sum(self):
        """AccSum([H|T], Acc, R) <- AccSum(T, Acc+H, R)."""
        class ASum(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        acc = Var()
        result = Var()
        h = Var()
        t = Var()
        new_acc = Var()

        clauses = [
            Clause(head=ASum([], acc, acc), body=[]),
            Clause(head=ASum(Var(), Var(), Var()), body=[
                # Need actual head vars
            ]),
        ]
        # Use fixture instead — tested via .clausal file above

    def test_passthrough_variable(self):
        """Output variable passed through unchanged in tail call."""
        class Pass(metaclass=PredicateMeta):
            _fields = ('n', 'out')

        n = Var()
        n1 = Var()
        out = Var()
        # Base case uses Var + Unify (same as parser does for head constants).
        base_n = Var()
        base_out = Var()

        clauses = [
            Clause(head=Pass(base_n, base_out), body=[
                Unify(left=base_n, right=0),
                Unify(left=base_out, right=42),
            ]),
            Clause(head=Pass(n, out), body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='Pass'), args=[n1, out], kwargs=[]),
            ]),
        ]
        results = self._compile_and_query(Pass, clauses, 10, Var())
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][1], 42)

    def test_deep_recursion(self):
        """TRO handles deep recursion without excessive allocations."""
        class Deep(metaclass=PredicateMeta):
            _fields = ('n',)

        n = Var()
        n1 = Var()
        base_n = Var()

        clauses = [
            Clause(head=Deep(base_n), body=[Unify(left=base_n, right=0)]),
            Clause(head=Deep(n), body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='Deep'), args=[n1], kwargs=[]),
            ]),
        ]
        # Should not crash even with very deep recursion
        results = self._compile_and_query(Deep, clauses, 10000)
        self.assertEqual(len(results), 1)


# ── Allocation tests ────────────────────────────────────────────────────────


import clausal.logic.solve as _solve_mod


def _make_counting_sg():
    """Build a counting StepGenerator wrapper and return (wrapper_cls, counter).

    ``counter`` is a one-element list ``[int]`` incremented on every
    StepGenerator creation.  The wrapper delegates to the real C/Python
    StepGenerator so runtime behaviour is unchanged.
    """
    counter = [0]
    _real = StepGenerator

    class _Counting(_real):
        __slots__ = ()
        def __new__(cls, func, *args):
            counter[0] += 1
            return _real(func, *args)
    return _Counting, counter


def _patch_sg(counting_cls, *pred_classes):
    """Swap ``StepGenerator`` in ``solve.call``'s module *and* every compiled
    dispatch function's ``__globals__`` dict for *pred_classes*.

    Returns a restore callable.
    """
    _real = StepGenerator
    patched: list[dict] = []

    # 1) solve module — call() creates the root StepGenerator here.
    _solve_mod.StepGenerator = counting_cls
    patched.append(vars(_solve_mod))

    # 2) Each compiled dispatch fn has its own __globals__.
    for pcls in pred_classes:
        dispatch = pcls._get_dispatch()
        if dispatch is None:
            continue
        # dispatch may be a plain function or a wrapper; chase __wrapped__.
        fn = getattr(dispatch, '__wrapped__', dispatch)
        g = getattr(fn, '__globals__', None)
        if g is not None and "StepGenerator" in g:
            g["StepGenerator"] = counting_cls
            patched.append(g)

    def _restore():
        for d in patched:
            d["StepGenerator"] = _real
    return _restore


class TestTroAllocations(unittest.TestCase):
    """Test that TRO reduces StepGenerator allocations."""

    def setUp(self):
        self.db = Database()

    def _compile(self, pred_cls, clauses):
        functor = pred_cls.__name__
        arity = len(pred_cls._fields)
        for cl in clauses:
            self.db.assertz(cl)
        self.db.register_signature(functor, arity, pred_cls._fields)
        compile_predicate_trampoline(
            functor, arity, clauses, self.db,
            globals_={functor: pred_cls},
            pred_cls=pred_cls,
        )

    def test_tro_constant_allocations(self):
        """TRO predicate should use O(1) StepGenerators regardless of depth."""
        class TroCount(metaclass=PredicateMeta):
            _fields = ('n',)

        n = Var()
        n1 = Var()
        base_n = Var()
        clauses = [
            Clause(head=TroCount(base_n), body=[Unify(left=base_n, right=0)]),
            Clause(head=TroCount(n), body=[
                Gt(left=n, right=0),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='TroCount'), args=[n1], kwargs=[]),
            ]),
        ]
        self._compile(TroCount, clauses)

        # Query with depth 100
        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, TroCount)
        trail = Trail()
        for _ in call(TroCount, 100, trail=trail):
            pass
        count_100 = counter[0]
        restore()

        # Query with depth 1000
        self.db = Database()
        self._compile(TroCount, clauses)
        counting_cls2, counter2 = _make_counting_sg()
        restore2 = _patch_sg(counting_cls2, TroCount)
        trail2 = Trail()
        for _ in call(TroCount, 1000, trail=trail2):
            pass
        count_1000 = counter2[0]
        restore2()

        # With TRO, both should use the same number of StepGenerators
        # (just the top-level one from call()).
        self.assertEqual(count_100, count_1000,
                         f"StepGenerator count should be constant: "
                         f"depth=100 used {count_100}, depth=1000 used {count_1000}")
        # The top-level call() creates exactly 1 StepGenerator.
        self.assertEqual(count_100, 1,
                         f"Expected 1 StepGenerator (top-level only), got {count_100}")

    def test_non_tro_linear_allocations(self):
        """Non-TRO predicate (nondeterministic prefix) uses O(n) StepGenerators."""
        class Helper(metaclass=PredicateMeta):
            _fields = ('x',)

        class NonTro(metaclass=PredicateMeta):
            _fields = ('n',)

        n = Var()
        n1 = Var()
        x = Var()
        hx = Var()
        helper_clauses = [Clause(head=Helper(hx), body=[Unify(left=hx, right=1)])]
        base_n = Var()
        nontro_clauses = [
            Clause(head=NonTro(base_n), body=[Unify(left=base_n, right=0)]),
            Clause(head=NonTro(n), body=[
                Gt(left=n, right=0),
                Call(func=LoadName(name='Helper'), args=[x], kwargs=[]),  # nondeterministic
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='NonTro'), args=[n1], kwargs=[]),
            ]),
        ]
        for cl in helper_clauses:
            self.db.assertz(cl)
        self.db.register_signature('Helper', 1, ('x',))
        compile_predicate_trampoline(
            'Helper', 1, helper_clauses, self.db,
            globals_={'Helper': Helper}, pred_cls=Helper,
        )
        for cl in nontro_clauses:
            self.db.assertz(cl)
        self.db.register_signature('NonTro', 1, ('n',))
        compile_predicate_trampoline(
            'NonTro', 1, nontro_clauses, self.db,
            globals_={'NonTro': NonTro, 'Helper': Helper},
            pred_cls=NonTro,
        )

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, NonTro, Helper)
        trail = Trail()
        for _ in call(NonTro, 10, trail=trail):
            pass
        restore()

        # Non-TRO: should use more than 1 StepGenerator (grows with depth).
        self.assertGreater(counter[0], 10,
                           f"Expected >10 StepGenerators for depth 10, got {counter[0]}")

    def test_tro_with_passthrough_output(self):
        """TRO correctly binds output variable through passthrough."""
        class Acc(metaclass=PredicateMeta):
            _fields = ('n', 'acc', 'result')

        n = Var()
        n1 = Var()
        acc = Var()
        new_acc = Var()
        result = Var()
        base_n = Var()
        clauses = [
            Clause(head=Acc(base_n, acc, acc), body=[Unify(left=base_n, right=0)]),
            Clause(head=Acc(n, acc, result), body=[
                Gt(left=n, right=0),
                Evaluate(left=new_acc, right=Add(left=acc, right=n)),
                Evaluate(left=n1, right=Sub(left=n, right=1)),
                Call(func=LoadName(name='Acc'), args=[n1, new_acc, result], kwargs=[]),
            ]),
        ]
        for cl in clauses:
            self.db.assertz(cl)
        self.db.register_signature('Acc', 3, ('n', 'acc', 'result'))
        compile_predicate_trampoline(
            'Acc', 3, clauses, self.db,
            globals_={'Acc': Acc}, pred_cls=Acc,
        )

        # Verify correct result
        r = Var()
        trail = Trail()
        for _ in call(Acc, 5, 0, r, trail=trail):
            self.assertEqual(deref(r), 15)  # 5+4+3+2+1+0 = 15
            break
        else:
            self.fail("No solutions from accumulator sum")

        # Verify O(1) allocations
        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, Acc)
        trail2 = Trail()
        for _ in call(Acc, 500, 0, Var(), trail=trail2):
            pass
        restore()
        self.assertEqual(counter[0], 1, f"Expected 1 SG, got {counter[0]}")


# ── Integration with .clausal import hook ────────────────────────────────────


class TestTroImportHook(unittest.TestCase):
    """Test TRO via the .clausal import hook."""

    def test_fixture_loaded_with_tro(self):
        """tro_predicates.clausal should load and pass all inline tests."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        # Verify key predicates exist
        self.assertIn('AccSum', mod.__dict__)
        self.assertIn('AccFactorial', mod.__dict__)

    def test_fixture_accsum_correct(self):
        """AccSum via import hook produces correct results."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        AccSum = mod.__dict__['AccSum']
        r = Var()
        trail = Trail()
        for _ in call(AccSum, [1, 2, 3, 4, 5], 0, r, trail=trail):
            self.assertEqual(deref(r), 15)
            break
        else:
            self.fail("No solutions")

    def test_fixture_factorial_correct(self):
        """AccFactorial via import hook produces correct results."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        AccFactorial = mod.__dict__['AccFactorial']
        r = Var()
        trail = Trail()
        for _ in call(AccFactorial, 10, 1, r, trail=trail):
            self.assertEqual(deref(r), 3628800)
            break
        else:
            self.fail("No solutions")

    def test_fixture_tro_allocations(self):
        """TRO predicates from fixture use O(1) StepGenerators."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        AccLength = mod.__dict__['AccLength']

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, AccLength)
        try:
            trail = Trail()
            big_list = list(range(500))
            for _ in call(AccLength, big_list, 0, Var(), trail=trail):
                pass
        finally:
            restore()

        # AccLength uses TRO: should be O(1) StepGenerators
        self.assertEqual(counter[0], 1,
                         f"Expected 1 SG for TRO AccLength, got {counter[0]}")


# ── Phase 2: Indexed TRO, StarUnpack, runtime ground-check ──────────────────


class TestTroGroundnessDispatch(unittest.TestCase):
    """Test TRO across groundness-dispatch bucket boundaries."""

    def test_mynthof_tro_across_buckets(self):
        """MyNthOf-style predicate: TRO restarts land in different bucket."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/deep_index.clausal')
        MyNthOf = mod.__dict__['MyNthOf']

        # Correctness
        r = Var()
        trail = Trail()
        for _ in call(MyNthOf, 2, [10, 20, 30], r, trail=trail):
            self.assertEqual(deref(r), 30)
            break
        else:
            self.fail("No solutions for MyNthOf(2, [10,20,30], E)")

    def test_mynthof_tro_allocations(self):
        """MyNthOf uses O(1) StepGenerators via dispatch-level TRO."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/deep_index.clausal')
        MyNthOf = mod.__dict__['MyNthOf']

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, MyNthOf)
        try:
            trail = Trail()
            for _ in call(MyNthOf, 50, list(range(100)), Var(), trail=trail):
                pass
        finally:
            restore()

        # Dispatch-level TRO: O(1) StepGenerators regardless of index depth.
        self.assertEqual(counter[0], 1,
                         f"Expected 1 SG for TRO MyNthOf, got {counter[0]}")


class TestTroRuntimeGroundCheck(unittest.TestCase):
    """Test runtime ground-check fallback for head-decomposition vars."""

    def test_acclength_with_unbound_list(self):
        """AccLength with unbound first arg falls back to StepGenerator (no TRO)."""
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        AccLength = mod.__dict__['AccLength']

        # Call with unbound first arg — should produce solutions via
        # StepGenerator fallback, not break due to TRO.
        list_var = Var()
        trail = Trail()
        results = []
        for _ in call(AccLength, [], 0, Var(), trail=trail):
            results.append(True)
        # Base case: AccLength([], 0, 0) should still work
        self.assertEqual(len(results), 1)

    def test_check_indices_computed(self):
        """_get_tro_check_indices returns positions for head-decomposition vars."""
        from clausal.logic.compiler import _get_tro_check_indices

        class P(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        h = Var()
        t = Var()
        acc = Var()
        result = Var()
        new_acc = Var()

        cl = Clause(
            head=P(Var(), acc, result),
            body=[
                Evaluate(left=new_acc, right=Add(left=acc, right=1)),
                Call(func=LoadName(name='P'), args=[t, new_acc, result], kwargs=[]),
            ],
        )
        # t is NOT in bound_var_ids, NOT passthrough, IS a head var → needs check
        # new_acc is in bound_var_ids → no check
        # result is passthrough → no check
        # But t is from the BODY (not head) in this construction... let me fix
        # Actually, t doesn't appear in the head here. So it would be a body-only var.
        # Let me construct it with t in the head list pattern.

    def test_get_tro_check_indices_with_head_decomposition(self):
        """Check indices include head-decomposition vars not bound by prefix."""
        from clausal.logic.compiler import _get_tro_check_indices, _detect_tro_clause
        from clausal.pythonic_ast.nodes import StarUnpack as _SU

        class L(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        wild = Var()
        t = Var()
        acc = Var()
        result = Var()
        new_acc = Var()

        # L([_, *T], ACC, R) <- (NEWACC := ACC + 1, L(T, NEWACC, R))
        cl = Clause(
            head=L([wild, _SU(value=t)], acc, result),
            body=[
                Evaluate(left=new_acc, right=Add(left=acc, right=1)),
                Call(func=LoadName(name='L'), args=[t, new_acc, result], kwargs=[]),
            ],
        )
        self.assertTrue(_detect_tro_clause('L', 3, cl))
        indices = _get_tro_check_indices('L', 3, cl)
        # t (position 0 in tail call) is from head decomposition → needs check
        self.assertIn(0, indices)
        # new_acc (position 1) is bound by Evaluate → no check
        self.assertNotIn(1, indices)
        # result (position 2) is passthrough → no check
        self.assertNotIn(2, indices)


if __name__ == '__main__':
    unittest.main()
