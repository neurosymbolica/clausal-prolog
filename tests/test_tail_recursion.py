"""Tests for Tail Recursion Optimization (TRO).

Verifies correctness and allocation efficiency of TRO-compiled predicates.
"""

import unittest
from unittest.mock import patch

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
    In, NotIn,
    StructuralEq, StructuralNeq,
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
        self.assertTrue(_is_deterministic_goal(StructuralEq(left=1, right=1)))

    def test_structural_neq(self):
        self.assertTrue(_is_deterministic_goal(StructuralNeq(left=1, right=2)))

    def test_comparisons(self):
        self.assertTrue(_is_deterministic_goal(Gt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(Lt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(GtE(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(LtE(left=Var(), right=0)))

    def test_in_notin(self):
        self.assertTrue(_is_deterministic_goal(In(left=1, right=[1, 2])))
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
            Call(func=LoadName(name='Once'), args=[inner], kwargs=[])
        ))

    def test_findall_deterministic(self):
        self.assertTrue(_is_deterministic_goal(
            Call(func=LoadName(name='FindAll'), args=[Var(), Var(), Var()], kwargs=[])
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

    def test_star_unpack_in_tail_call_rejected(self):
        """Tail call arg with StarUnpack is rejected (TRO can't expand splats)."""
        from clausal.pythonic_ast.nodes import StarUnpack

        h = Var()
        t = Var()
        acc = Var()
        result = Var()

        class Rev(metaclass=PredicateMeta):
            _fields = ('list', 'acc', 'result')

        # AccReverse([H, *T], ACC, RESULT) <- AccReverse(T, [H, *ACC], RESULT)
        # The tail call arg [H, *ACC] contains StarUnpack — must be rejected.
        cl = Clause(
            head=Rev(Var(), acc, result),
            body=[
                Call(func=LoadName(name='Rev'),
                     args=[t, [h, StarUnpack(value=acc)], result], kwargs=[]),
            ],
        )
        self.assertFalse(_detect_tro_clause('Rev', 3, cl))

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


class TestTroAllocations(unittest.TestCase):
    """Test that TRO reduces StepGenerator allocations."""

    def setUp(self):
        self.db = Database()
        self.sg_count = 0
        self.orig_init = StepGenerator.__init__

    def _start_counting(self):
        """Start counting StepGenerator allocations."""
        self.sg_count = 0
        test = self

        def counting_init(self, func, *args):
            test.sg_count += 1
            test.orig_init(self, func, *args)

        StepGenerator.__init__ = counting_init

    def _stop_counting(self):
        """Stop counting and restore original init."""
        StepGenerator.__init__ = self.orig_init

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
        self._start_counting()
        trail = Trail()
        for _ in call(TroCount, 100, trail=trail):
            pass
        self._stop_counting()
        count_100 = self.sg_count

        # Query with depth 1000
        self.db = Database()
        self._compile(TroCount, clauses)
        self._start_counting()
        trail2 = Trail()
        for _ in call(TroCount, 1000, trail=trail2):
            pass
        self._stop_counting()
        count_1000 = self.sg_count

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

        self._start_counting()
        trail = Trail()
        for _ in call(NonTro, 10, trail=trail):
            pass
        self._stop_counting()

        # Non-TRO: should use more than 1 StepGenerator (grows with depth).
        self.assertGreater(self.sg_count, 10,
                           f"Expected >10 StepGenerators for depth 10, got {self.sg_count}")

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
        self._start_counting()
        trail2 = Trail()
        for _ in call(Acc, 500, 0, Var(), trail=trail2):
            pass
        self._stop_counting()
        self.assertEqual(self.sg_count, 1, f"Expected 1 SG, got {self.sg_count}")


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

        sg_count = [0]
        orig_init = StepGenerator.__init__

        def counting_init(self, func, *args):
            sg_count[0] += 1
            orig_init(self, func, *args)

        StepGenerator.__init__ = counting_init
        try:
            trail = Trail()
            big_list = list(range(500))
            for _ in call(AccLength, big_list, 0, Var(), trail=trail):
                pass
        finally:
            StepGenerator.__init__ = orig_init

        # AccLength uses TRO: should be O(1) StepGenerators
        self.assertEqual(sg_count[0], 1,
                         f"Expected 1 SG for TRO AccLength, got {sg_count[0]}")


if __name__ == '__main__':
    unittest.main()
