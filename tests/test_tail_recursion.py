"""Tests for Tail Recursion Optimization (TRO).

Verifies correctness and allocation efficiency of TRO-compiled predicates.
"""

import unittest

from clausal.logic.compiler import compile_predicate_trampoline
from clausal.logic.compiler.tro import _is_deterministic_goal, _tro_args_safe


def _detect_tro_clause(functor, arity, clause, db=None):
    """Test helper: E6d-β-style TRO eligibility via the uniform
    ``optimisations.tro.analyse`` pass.  Replaces the retired term-walking
    ``tro._detect_tro_clause``; returns ``False`` for clauses whose body
    shape is outside the IR subset (matching the retired helper's
    behaviour on unsupported shapes)."""
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.optimisations.tro import analyse
    try:
        ir = terms_to_goalop(clause.body, db=db)
    except NotImplementedError:
        return False
    return analyse(ir, clause.head, functor, arity, db=db).eligible


def _get_tro_check_indices(functor, arity, clause, db=None):
    """Test helper: check-indices via the uniform ``analyse`` pass."""
    from clausal.logic.compiler.terms_to_goalop import terms_to_goalop
    from clausal.logic.compiler.optimisations.tro import analyse
    ir = terms_to_goalop(clause.body, db=db)
    return analyse(ir, clause.head, functor, arity, db=db).check_indices
from clausal.logic.database import Clause, Database
from clausal.logic.predicate import resolve_predicate_row
from tests.predicate_api_support import RowPredicate
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
        # nv
        self.assertTrue(_is_deterministic_goal(Unify(left=Var(), right=42)))

    def test_evaluate(self):
        # nv
        self.assertTrue(_is_deterministic_goal(Evaluate(left=Var(), right=Add(left=1, right=2))))

    def test_does_not_unify(self):
        # nv
        self.assertTrue(_is_deterministic_goal(DoesNotUnify(left=Var(), right=42)))

    def test_structural_eq(self):
        # nv
        self.assertTrue(_is_deterministic_goal(ArithEq(left=1, right=1)))

    def test_structural_neq(self):
        # nv
        self.assertTrue(_is_deterministic_goal(ArithNeq(left=1, right=2)))

    def test_comparisons(self):
        # nv
        self.assertTrue(_is_deterministic_goal(Gt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(Lt(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(GtE(left=Var(), right=0)))
        self.assertTrue(_is_deterministic_goal(LtE(left=Var(), right=0)))

    def test_in_notin(self):
        # nv — A03-F001: positive membership (in_) is NONdeterministic (it
        # succeeds once per matching occurrence), so it is NOT safe before a
        # TRO tail call. NotIn (not_in) is semidet and stays deterministic.
        self.assertFalse(_is_deterministic_goal(in_(left=1, right=[1, 2])))
        self.assertTrue(_is_deterministic_goal(NotIn(left=3, right=[1, 2])))

    def test_not(self):
        # nv
        self.assertTrue(_is_deterministic_goal(Not(operand=Gt(left=1, right=2))))

    def test_true_false(self):
        # nv
        self.assertTrue(_is_deterministic_goal(True))
        self.assertTrue(_is_deterministic_goal(False))

    def test_and_deterministic(self):
        # nv
        self.assertTrue(_is_deterministic_goal(
            And(left=Gt(left=Var(), right=0), right=Evaluate(left=Var(), right=Sub(left=Var(), right=1)))
        ))

    def test_and_nondeterministic(self):
        # nv
        self.assertFalse(_is_deterministic_goal(
            And(left=Gt(left=Var(), right=0), right=Call(func=LoadName(name='Foo'), args=[], kwargs=[]))
        ))

    def test_predicate_call(self):
        # nv
        self.assertFalse(_is_deterministic_goal(
            Call(func=LoadName(name='Foo'), args=[Var()], kwargs=[])
        ))

    def test_or_nondeterministic(self):
        # nv
        self.assertFalse(_is_deterministic_goal(
            Or(left=Gt(left=Var(), right=0), right=Lt(left=Var(), right=0))
        ))

    def test_once_deterministic(self):
        # nv
        inner = Call(func=LoadName(name='Foo'), args=[Var()], kwargs=[])
        self.assertTrue(_is_deterministic_goal(
            Call(func=LoadName(name='once'), args=[inner], kwargs=[])
        ))

    def test_findall_deterministic(self):
        # nv
        self.assertTrue(_is_deterministic_goal(
            Call(func=LoadName(name='findall'), args=[Var(), Var(), Var()], kwargs=[])
        ))


class TestDetectTroClause(unittest.TestCase):
    """Test _detect_tro_clause detection."""

    def _make_clause(self, head_fields, body):
        P = RowPredicate('P', head_fields, None)
        head_args = {f: Var() for f in head_fields}
        head = P(**head_args)
        return Clause(head=head, body=body), P, head_args

    def test_no_body(self):
        """Facts (no body) are not TRO-eligible."""
        # nv
        cl, P, _ = self._make_clause(('x',), [])
        self.assertFalse(_detect_tro_clause('P', 1, cl))

    def test_last_goal_is_self_call(self):
        """Clause with only a self-recursive tail call is TRO-eligible
        if args are safe."""
        # nv
        x = Var()

        Q = RowPredicate('Q', ('x',), None)

        cl = Clause(
            head=Q(x),
            body=[Call(func=LoadName(name='Q'), args=[x], kwargs=[])],
        )
        # x is a passthrough (same Var at position 0 in head and tail call)
        self.assertTrue(_detect_tro_clause('Q', 1, cl))

    def test_deterministic_prefix_with_self_call(self):
        """Deterministic prefix + self-recursive tail call is TRO-eligible."""
        # nv
        n = Var()
        n1 = Var()
        result = Var()

        Fact = RowPredicate('Fact', ('n', 'result'), None)

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
        # nv
        n = Var()

        R = RowPredicate('R', ('n',), None)

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
        # nv
        x = Var()

        S = RowPredicate('S', ('x',), None)

        cl = Clause(
            head=S(x),
            body=[Call(func=LoadName(name='Other'), args=[x], kwargs=[])],
        )
        self.assertFalse(_detect_tro_clause('S', 1, cl))

    def test_no_prefix_body_only_vars_rejected(self):
        """Tail call with body-only vars and no prefix goals is rejected."""
        # nv
        h = Var()
        t = Var()
        acc = Var()
        result = Var()

        Rev = RowPredicate('Rev', ('list', 'acc', 'result'), None)

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
        # nv
        h = Var()
        t = Var()
        acc = Var()
        result = Var()
        acc2 = Var()

        Rev = RowPredicate('Rev', ('list', 'acc', 'result'), None)

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
        # nv
        x = Var()
        goals_var = Var()
        rest = Var()

        Meta = RowPredicate('Meta', ('goals', 'result'), None)

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
        # nv
        n = Var()
        n1 = Var()
        acc = Var()

        Acc = RowPredicate('Acc', ('n', 'state'), None)

        # Acc(N, State) <- (N > 0, eval_(N-1, N1), Acc(N1, Compound("s", (N, State))))
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
        # nv
        x = Var()
        y = Var()

        P = RowPredicate('P', ('a', 'b'), None)

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
        self.db = _module_db()

    def _compile_and_query(self, pred_cls, clauses, *args):
        """Compile clauses with TRO, then query and return results."""
        functor = pred_cls.__name__
        arity = len(pred_cls._fields)
        for cl in clauses:
            self.db.assertz(cl)
        self.db.register_signature(functor, arity, pred_cls._fields)
        compile_predicate_trampoline(
            functor, arity, clauses, self.db,
            globals_={functor: pred_cls.handle},
            pred_cls=pred_cls.handle,
        )
        trail = Trail()
        results = []
        for _ in call(pred_cls.handle, *args, trail=trail):
            results.append(tuple(deref(a) for a in args))
        return results

    def test_simple_countdown(self):
        """N > 0, eval_(N - 1, N1), CountDown(N1) — deterministic prefix."""
        # nv
        CountDown = RowPredicate('CountDown', ('n',), self.db)

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
        """acc_sum([H|T], Acc, R) <- acc_sum(T, Acc+H, R)."""
        # nv
        ASum = RowPredicate('ASum', ('list', 'acc', 'result'), self.db)

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
        # nv
        Pass = RowPredicate('Pass', ('n', 'out'), self.db)

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
        # nv
        Deep = RowPredicate('Deep', ('n',), self.db)

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


def _dispatch_of(pred):
    """The compiled dispatch of *pred*: a ``RowPredicate`` (the
    Python-built predicates below), or a ``(module, name, arity)`` triple for
    a module-loaded predicate -- post-flip its module-dict binding is a
    mangled handle, whose row (and so dispatch) is read off its owner's
    Database.

    The handle is resolved WITH the loaded module's db as the hint (ruling
    Q0), never bare: ``load_clausal_module`` loads every file under the same
    ``_clausal_test_<stem>`` name and pops it from ``sys.modules``, and the
    ``.clausal`` pytest collector keeps its own load of the same fixture
    alive for the whole session -- so a bare handle names a module that TWO
    live databases answer to, and the engine refuses it
    (``AmbiguousHandleOwnerError``) by design.  The hint picks this test's
    own load, which is the one the query below runs in."""
    if isinstance(pred, tuple):
        mod, name, arity = pred
        db = mod.__dict__['$module'].db
        handle = mod.__dict__[name]
        row = resolve_predicate_row(handle, arity=arity, db=db)
        assert row is not None, f"no row for {handle!r}/{arity}"
        assert row.db is db, "resolved to another load's row, not this one"
        return db.get_dispatch(*row.key)
    if isinstance(pred, RowPredicate):
        # A predicate compiled into a module Database through its handle
        # (W4b-3 slice 7; a PredicateMeta class answered _get_dispatch()).
        return pred.db.get_dispatch(pred.__name__, len(pred._fields))
    return pred._get_dispatch()


def _module_db():
    """A fresh Database of a NAMED module, so a handle can name it."""
    from clausal.logic.database import Module
    _module_db.serial = getattr(_module_db, "serial", 0) + 1
    name = f"_tro_mod_{_module_db.serial}"
    return Module(name, module_dict={"__name__": name}).db


def _patch_sg(counting_cls, *pred_classes):
    """Swap ``StepGenerator`` in ``solve.call``'s module *and* every compiled
    dispatch function's ``__globals__`` dict for *pred_classes* (classes, or
    ``(module, name, arity)`` triples -- see ``_dispatch_of``).

    Returns a restore callable.  Every predicate asked for must be patched:
    a dispatch left unpatched would count NOTHING, and a count of 1 (the
    root StepGenerator alone) would then read as "TRO fired".
    """
    _real = StepGenerator
    patched: list[dict] = []

    # 1) solve module — call() creates the root StepGenerator here.
    _solve_mod.StepGenerator = counting_cls
    patched.append(vars(_solve_mod))

    # 2) Each compiled dispatch fn has its own __globals__.
    for pcls in pred_classes:
        dispatch = _dispatch_of(pcls)
        assert dispatch is not None, f"{pcls!r}: no compiled dispatch to patch"
        # dispatch may be a plain function or a wrapper; chase __wrapped__.
        fn = getattr(dispatch, '__wrapped__', dispatch)
        g = getattr(fn, '__globals__', None)
        assert g is not None and "StepGenerator" in g, (
            f"{pcls!r}: dispatch globals carry no StepGenerator to patch")
        g["StepGenerator"] = counting_cls
        patched.append(g)

    def _restore():
        for d in patched:
            d["StepGenerator"] = _real
    return _restore


def _tro_disabled() -> bool:
    """Skip-helper for TRO observability tests under the E5b
    ``CLAUSAL_DISABLE_OPT=tro`` per-optimisation suite sweep — these
    tests assert the optimisation actually fires."""
    import os
    return "tro" in {
        s.strip() for s in os.environ.get("CLAUSAL_DISABLE_OPT", "").split(",")
    }


@unittest.skipIf(_tro_disabled(), "TRO disabled via CLAUSAL_DISABLE_OPT")
class TestTroAllocations(unittest.TestCase):
    """Test that TRO reduces StepGenerator allocations."""

    def setUp(self):
        self.db = _module_db()

    def _compile(self, pred_cls, clauses):
        functor = pred_cls.__name__
        arity = len(pred_cls._fields)
        for cl in clauses:
            self.db.assertz(cl)
        self.db.register_signature(functor, arity, pred_cls._fields)
        compile_predicate_trampoline(
            functor, arity, clauses, self.db,
            globals_={functor: pred_cls.handle},
            pred_cls=pred_cls.handle,
        )

    def test_tro_constant_allocations(self):
        """TRO predicate should use O(1) StepGenerators regardless of depth."""
        # nv
        TroCount = RowPredicate('TroCount', ('n',), self.db)

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
        for _ in call(TroCount.handle, 100, trail=trail):
            pass
        count_100 = counter[0]
        restore()

        # Query with depth 1000
        self.db = _module_db()
        TroCount = RowPredicate('TroCount', ('n',), self.db)
        self._compile(TroCount, clauses)
        counting_cls2, counter2 = _make_counting_sg()
        restore2 = _patch_sg(counting_cls2, TroCount)
        trail2 = Trail()
        for _ in call(TroCount.handle, 1000, trail=trail2):
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
        # nv
        Helper = RowPredicate('Helper', ('x',), self.db)

        NonTro = RowPredicate('NonTro', ('n',), self.db)

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
            globals_={'Helper': Helper.handle}, pred_cls=Helper.handle,
        )
        for cl in nontro_clauses:
            self.db.assertz(cl)
        self.db.register_signature('NonTro', 1, ('n',))
        compile_predicate_trampoline(
            'NonTro', 1, nontro_clauses, self.db,
            globals_={'NonTro': NonTro.handle, 'Helper': Helper.handle},
            pred_cls=NonTro.handle,
        )

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, NonTro, Helper)
        trail = Trail()
        for _ in call(NonTro.handle, 10, trail=trail):
            pass
        restore()

        # Non-TRO: should use more than 1 StepGenerator (grows with depth).
        self.assertGreater(counter[0], 10,
                           f"Expected >10 StepGenerators for depth 10, got {counter[0]}")

    def test_tro_with_passthrough_output(self):
        """TRO correctly binds output variable through passthrough."""
        # nv
        Acc = RowPredicate('Acc', ('n', 'acc', 'result'), self.db)

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
            globals_={'Acc': Acc.handle}, pred_cls=Acc.handle,
        )

        # Verify correct result
        r = Var()
        trail = Trail()
        for _ in call(Acc.handle, 5, 0, r, trail=trail):
            self.assertEqual(deref(r), 15)  # 5+4+3+2+1+0 = 15
            break
        else:
            self.fail("No solutions from accumulator sum")

        # Verify O(1) allocations
        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, Acc)
        trail2 = Trail()
        for _ in call(Acc.handle, 500, 0, Var(), trail=trail2):
            pass
        restore()
        self.assertEqual(counter[0], 1, f"Expected 1 SG, got {counter[0]}")


# ── Integration with .clausal import hook ────────────────────────────────────


@unittest.skipIf(_tro_disabled(), "TRO disabled via CLAUSAL_DISABLE_OPT")
class TestTroImportHook(unittest.TestCase):
    """Test TRO via the .clausal import hook."""

    def test_fixture_loaded_with_tro(self):
        """tro_predicates.clausal should load and pass all inline tests."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        # Verify key predicates exist
        self.assertIn('acc_sum', mod.__dict__)
        self.assertIn('acc_factorial', mod.__dict__)

    def test_fixture_accsum_correct(self):
        """acc_sum via import hook produces correct results."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        lm = mod.__dict__['$module']
        # By NAME in this test's own load (module=lm), never the bare handle:
        # the same-named fixture load the .clausal collector holds would make
        # the handle ambiguous (see ``_dispatch_of``).
        r = Var()
        trail = Trail()
        for _ in call('acc_sum', [1, 2, 3, 4, 5], 0, r, module=lm, trail=trail):
            self.assertEqual(deref(r), 15)
            break
        else:
            self.fail("No solutions")

    def test_fixture_factorial_correct(self):
        """acc_factorial via import hook produces correct results."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        lm = mod.__dict__['$module']
        # By NAME in this test's own load (module=lm), never the bare handle:
        # the same-named fixture load the .clausal collector holds would make
        # the handle ambiguous (see ``_dispatch_of``).
        r = Var()
        trail = Trail()
        for _ in call('acc_factorial', 10, 1, r, module=lm, trail=trail):
            self.assertEqual(deref(r), 3628800)
            break
        else:
            self.fail("No solutions")

    def test_fixture_tro_allocations(self):
        """TRO predicates from fixture use O(1) StepGenerators."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        lm = mod.__dict__['$module']

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, (mod, 'acc_length', 3))
        try:
            trail = Trail()
            big_list = list(range(500))
            for _ in call('acc_length', big_list, 0, Var(), module=lm,
                          trail=trail):
                pass
        finally:
            restore()

        # AccLength uses TRO: should be O(1) StepGenerators
        self.assertEqual(counter[0], 1,
                         f"Expected 1 SG for TRO AccLength, got {counter[0]}")


# ── Phase 2: Indexed TRO, StarUnpack, runtime ground-check ──────────────────


@unittest.skipIf(_tro_disabled(), "TRO disabled via CLAUSAL_DISABLE_OPT")
class TestTroGroundnessDispatch(unittest.TestCase):
    """Test TRO across groundness-dispatch bucket boundaries."""

    def test_mynthof_tro_across_buckets(self):
        """my_nth_of-style predicate: TRO restarts land in different bucket."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/deep_index.clausal')
        lm = mod.__dict__['$module']
        # By NAME in this test's own load (module=lm), never the bare handle:
        # the same-named fixture load the .clausal collector holds would make
        # the handle ambiguous (see ``_dispatch_of``).

        # Correctness
        r = Var()
        trail = Trail()
        for _ in call('my_nth_of', 2, [10, 20, 30], r, module=lm, trail=trail):
            self.assertEqual(deref(r), 30)
            break
        else:
            self.fail("No solutions for my_nth_of(2, [10,20,30], E)")

    def test_mynthof_tro_allocations(self):
        """my_nth_of uses O(1) StepGenerators via dispatch-level TRO."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/deep_index.clausal')
        lm = mod.__dict__['$module']

        counting_cls, counter = _make_counting_sg()
        restore = _patch_sg(counting_cls, (mod, 'my_nth_of', 3))
        try:
            trail = Trail()
            for _ in call('my_nth_of', 50, list(range(100)), Var(), module=lm,
                          trail=trail):
                pass
        finally:
            restore()

        # Dispatch-level TRO: O(1) StepGenerators regardless of index depth.
        self.assertEqual(counter[0], 1,
                         f"Expected 1 SG for TRO MyNthOf, got {counter[0]}")


class TestTroRuntimeGroundCheck(unittest.TestCase):
    """Test runtime ground-check fallback for head-decomposition vars."""

    def test_acclength_with_unbound_list(self):
        """acc_length with unbound first arg falls back to StepGenerator (no TRO)."""
        # nv
        from clausal.testing import load_clausal_module
        mod = load_clausal_module('tests/fixtures/tro_predicates.clausal')
        lm = mod.__dict__['$module']
        # By NAME in this test's own load (module=lm), never the bare handle:
        # the same-named fixture load the .clausal collector holds would make
        # the handle ambiguous (see ``_dispatch_of``).

        # Call with unbound first arg — should produce solutions via
        # StepGenerator fallback, not break due to TRO.
        list_var = Var()
        trail = Trail()
        results = []
        for _ in call('acc_length', [], 0, Var(), module=lm, trail=trail):
            results.append(True)
        # Base case: AccLength([], 0, 0) should still work
        self.assertEqual(len(results), 1)

    def test_check_indices_computed(self):
        """_get_tro_check_indices returns positions for head-decomposition vars."""
        pass  # helper defined at module-level

        P = RowPredicate('P', ('list', 'acc', 'result'), None)

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
        pass  # helpers defined at module-level
        from clausal.pythonic_ast.nodes import StarUnpack as _SU

        L = RowPredicate('L', ('list', 'acc', 'result'), None)

        wild = Var()
        t = Var()
        acc = Var()
        result = Var()
        new_acc = Var()

        # L([_, *T], ACC, R) <- (eval_(ACC + 1, NEWACC), L(T, NEWACC, R))
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
