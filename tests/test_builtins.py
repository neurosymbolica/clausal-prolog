"""Tests for Step 8 — built-ins and standard library (clausal.logic.builtins).

Tests use the simple query API (clausal.logic.solve) to drive predicates and
collect solutions.  Each test follows the pattern:

    module = Module("test")
    trail = Trail()
    results = [deref(var) for _ in solve(goal, module, trail)]
"""

from __future__ import annotations

import dataclasses
import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mint
from clausal.logic.cells import chars
from clausal.logic.database import Clause, Database, Module
from clausal.logic.solve import solve
from clausal.logic.variables import Var, Trail, deref
from clausal.terms import Call, LoadName


# ── Helpers ────────────────────────────────────────────────────────────────────


def fresh_module(name: str = "test") -> Module:
    return Module(name)


def solutions(goal, mod=None, *, limit=50):
    """Return a list of trail snapshots for each solution."""
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return list(solve(goal, mod, t))


def sol_var(goal, var, *, limit=50, mod=None):
    """Return the deref'd value of var for each solution of goal."""
    if mod is None:
        mod = fresh_module()
    t = Trail()
    return [deref(var) for _ in solve(goal, mod, t)]


# ── Migration note ─────────────────────────────────────────────────────────
# TestTypeChecks / TestArithmetic / TestListPredicates / TestAssertRetract /
# TestPairHelpers have been removed — their coverage is in .clausal fixtures:
#   tests/conformity/iso_type_checking.clausal
#   tests/conformity/iso_arithmetic.clausal  (incl. Sign/Gcd/DivMod)
#   tests/conformity/iso_list_operations.clausal + builtins_lists.clausal
#   tests/conformity/iso_database.clausal + builtins_db.clausal
#   tests/fixtures/phase5_builtins.clausal  (pairs_keys_values/_keys/_values)

# ── functor/3 ─────────────────────────────────────────────────────────────────


class TestFunctor:
    def test_decompose_compound(self):
        # nv
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[("foo", 1, 2), f, a], kwargs=[])
        results = sol_var(goal, f, mod=mod)
        assert results == [mint("foo")]
        results_a = sol_var(goal, a, mod=mod)
        assert results_a == [2]

    def test_decompose_str_is_the_cons_cell_of_its_char_list(self):
        # nv — THE FLIP (spec §6.4): a ``str`` is a STRING, i.e. the LIST of
        # its char atoms, so ``functor/3`` answers it exactly as it answers
        # that list: ``F = ('.',)``, ``A = 2``.  This INVERTS the P3-1
        # str-is-its-own-atom reading (which itself had inverted the
        # original cons-cell pin -- the cons-cell answer is back).
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[chars("hello"), f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == [mint(".")]
        assert sol_var(goal, a, mod=mod) == [2]

    def test_decompose_empty_str_nil(self):
        # nv
        # F089 (audit 2026-06-13): empty str → nil atom ("[]", 0).
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[chars(""), f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == [mint("[]")]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_decompose_integer(self):
        # nv
        mod = fresh_module()
        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[42, f, a], kwargs=[])
        # A09-F027: an atomic constant is its own functor name (ISO), so
        # functor(42, F, A) gives F=42 (not the string "42"), A=0.
        assert sol_var(goal, f, mod=mod) == [42]
        assert sol_var(goal, a, mod=mod) == [0]

    def test_compose_compound(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="functor"), args=[t, mint("bar"), 2], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        r = results[0]
        # The name position CONSTRUCTS CELLS (atoms-as-cells design §6.4):
        # ``bar(_, _)`` is the cell ``("bar", _, _)``, not a Compound.
        assert type(r) is tuple
        assert r[0] == "bar"
        assert len(r) - 1 == 2

    def test_compose_atom(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="functor"), args=[t, mint("hello"), 0], kwargs=[])
        assert sol_var(goal, t, mod=mod) == [mint("hello")]

    def test_all_unbound_is_an_instantiation_error(self):
        # ISO 8.5.1.3 a (Scryer-verified); this used to fail silently
        # (todo/done/builtins-fail-silently-on-bad-arguments-2026-09-27.md).
        from clausal.logic.exceptions import LogicException
        mod = fresh_module()
        t, f, a = Var(), Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[t, f, a], kwargs=[])
        with pytest.raises(LogicException) as exc:
            sol_var(goal, t, mod=mod)
        assert cell_args(exc.value.term)[0] == mint("instantiation_error")

    def test_decompose_dataclass(self):
        # nv
        mod = fresh_module()
        db = Database()

        @dataclasses.dataclass
        class point:
            x: object
            y: object

        f, a = Var(), Var()
        goal = Call(func=LoadName(name="functor"), args=[point(x=1, y=2), f, a], kwargs=[])
        assert sol_var(goal, f, mod=mod) == [mint("point")]
        assert sol_var(goal, a, mod=mod) == [2]


# ── arg/3 ─────────────────────────────────────────────────────────────────────


class TestArg:
    def test_first_arg(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[1, ("f", 10, 20), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [10]

    def test_second_arg(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[2, ("f", 10, 20), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [20]

    def test_out_of_range(self):
        # nv
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[3, ("f", 10, 20), a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == []

    @pytest.mark.parametrize("third", ["unbound", 20])
    def test_var_n_is_an_instantiation_error(self, third):
        # D51 (ruled 2026-09-30): ISO 8.5.2.3 a and Scryer raise
        # instantiation_error for an unbound N -- ``arg(N, f(a,b), X)`` in
        # Scryer is error(instantiation_error, arg/3).  It used to ENUMERATE
        # the (N, Arg) pairs, SWI's extension, and to answer N = 2 for
        # ``arg(N, f(10, 20), 20)``.
        # nv
        from clausal.logic.exceptions import LogicException
        mod = fresh_module()
        n = Var()
        a = Var() if third == "unbound" else third
        goal = Call(func=LoadName(name="arg"),
                    args=[n, ("f", 10, 20), a], kwargs=[])
        with pytest.raises(LogicException) as ei:
            list(solve(goal, mod, Trail()))
        assert ei.value.term[1] == "instantiation_error", ei.value.term

    def test_list_arg_cons_cell_head(self):
        # nv
        # F091 (audit 2026-06-13): arg/3 on a non-empty list follows
        # ISO cons-cell — arg(1, [..], X) binds X to the head.
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[1, [10, 20, 30], a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [10]

    def test_list_arg_cons_cell_tail(self):
        # nv
        # F091 (audit 2026-06-13): arg(2, [..], X) binds X to the
        # cons-cell tail (list of rest), not the second element.
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[2, [10, 20, 30], a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == [[20, 30]]

    def test_list_arg_out_of_range(self):
        # nv
        # F091 (audit 2026-06-13): arg(N>=3, [..], _) fails because
        # cons-cell arity is 2.
        mod = fresh_module()
        a = Var()
        goal = Call(func=LoadName(name="arg"), args=[3, [10, 20, 30], a], kwargs=[])
        assert sol_var(goal, a, mod=mod) == []


# ── univ/2 ────────────────────────────────────────────────────────────────────


class TestUniv:
    def test_decompose(self):
        # nv
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[("f", 1, 2), lst], kwargs=[])
        results = sol_var(goal, lst, mod=mod)
        assert results == [[mint("f"), 1, 2]]

    def test_construct(self):
        # nv
        mod = fresh_module()
        t = Var()
        goal = Call(func=LoadName(name="unpack"), args=[t, [mint("g"), 3, 4]], kwargs=[])
        results = sol_var(goal, t, mod=mod)
        assert len(results) == 1
        # ``=..`` constructs a CELL (atoms-as-cells design §6.4).
        assert results[0] == ("g", 3, 4)

    def test_decompose_str_is_the_cons_cell_of_its_char_list(self):
        # nv — THE FLIP (spec §6.4, §5.4): a ``str`` is the LIST of its char
        # atoms, so ``=..`` decomposes it as that list does -- the head is
        # the char atom and the tail is the ``str`` SLICE (R-S2: nothing is
        # expanded).  INVERTS the P3-1 atom reading ``['hello']``.
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[chars("hello"), lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [[mint("."), mint("h"), chars("ello")]]

    def test_decompose_list_cons_cell(self):
        # nv
        # F088 (audit 2026-06-13): unpack on a non-empty list returns
        # the cons-cell decomposition [".", head, tail].
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[[1, 2, 3], lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [[mint("."), 1, [2, 3]]]

    def test_decompose_empty_list_nil(self):
        # nv
        # F088 (audit 2026-06-13): unpack on [] returns ["[]"] —
        # the nil atom (arity 0).
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[[], lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [[mint("[]")]]

    def test_decompose_empty_str_nil(self):
        # nv
        # F088/F089 (audit 2026-06-13): unpack on "" returns ["[]"].
        mod = fresh_module()
        lst = Var()
        goal = Call(func=LoadName(name="unpack"), args=[chars(""), lst], kwargs=[])
        assert sol_var(goal, lst, mod=mod) == [[mint("[]")]]






# ── assertz/retract ───────────────────────────────────────────────────────────

# ── WK-5: vary, extend, unbound_keys, signature ───────────────────────────────


class TestWK5:
    def test_vary_dataclass(self):
        @dataclasses.dataclass
        # nv
        class point:
            x: object
            y: object

        mod = fresh_module()
        p = point(x=1, y=2)
        new_p = Var()
        goal = Call(
            func=LoadName(name="vary"),
            args=[{"y": 99}, p, new_p],
            kwargs=[],
        )
        results = sol_var(goal, new_p, mod=mod)
        assert len(results) == 1
        assert results[0] == point(x=1, y=99)

    def test_vary_unknown_key_dataclass(self):
        """An override naming no field is "no variation": no solution, no
        error (the constructor's TypeError is caught)."""
        @dataclasses.dataclass
        # nv
        class point:
            x: object
            y: object

        mod = fresh_module()
        new_p = Var()
        goal = Call(
            func=LoadName(name="vary"),
            args=[{"z": 9}, point(x=1, y=2), new_p],
            kwargs=[],
        )
        assert sol_var(goal, new_p, mod=mod) == []

    def test_unbound_keys_dataclass(self):
        @dataclasses.dataclass
        # nv
        class pt:
            x: object
            y: object

        v = Var()
        t = pt(x=1, y=v)  # y is unbound
        mod = fresh_module()
        keys = Var()
        goal = Call(func=LoadName(name="unbound_keys"), args=[t, keys], kwargs=[])
        results = sol_var(goal, keys, mod=mod)
        # THE FLIP (spec §6.4): a field NAME answered to the program is an atom.
        assert results == [[mint("y")]]

    def test_signature(self):
        # nv
        from clausal.logic.database import Clause

        mod = fresh_module()
        # Register a predicate with a signature
        mod.db.register_signature("mypred", 2, ("arg0", "arg1"))
        names = Var()
        goal = Call(
            func=LoadName(name="signature"), args=[mint("mypred"), 2, names], kwargs=[]
        )
        results = sol_var(goal, names, mod=mod)
        # THE FLIP (spec §6.4): the name position speaks atoms in AND out.
        assert results == [[mint("arg0"), mint("arg1")]]

    def test_signature_unknown(self):
        # nv
        mod = fresh_module()
        names = Var()
        goal = Call(
            func=LoadName(name="signature"),
            args=[mint("unknown_pred"), 3, names],
            kwargs=[],
        )
        assert sol_var(goal, names, mod=mod) == []

    def test_signature_rejects_a_string_name(self):
        """A string in the name position is a type error, not a silent miss."""
        # nv — spec §6.4: `signature(chars("mypred"), 2, N)` asks about the LIST
        # [m,y,p,r,e,d], which is not a predicate name.
        from clausal.logic.exceptions import LogicException

        mod = fresh_module()
        mod.db.register_signature("mypred", 2, ("arg0", "arg1"))
        names = Var()
        goal = Call(
            func=LoadName(name="signature"), args=[chars("mypred"), 2, names], kwargs=[]
        )
        with pytest.raises(LogicException) as exc:
            sol_var(goal, names, mod=mod)
        formal = cell_args(exc.value.term)[0]
        assert cell_functor(formal) == "type_error"
        assert cell_args(formal)[0] == mint("atom")



# ── Builtins accessible from compiled predicate bodies ────────────────────────


class TestBuiltinsInCompiledPredicates:
    """Builtins should be accessible via _db.table_for from compiled predicates."""

    def test_between_in_compiled_body(self):
        """A compiled predicate that calls between/3 in its body."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # range_check(N) :- between(1, 10, N).
        n = Var()
        db.assertz(Clause(
            head=("range_check", n),
            body=[Call(func=LoadName(name="between"), args=[1, 5, n], kwargs=[])],
        ))
        compile_predicate_trampoline("range_check", 1, db.clauses_for("range_check", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("range_check", 1)
        results = solutions(StepGenerator(fn, None, None, None, out, t), lambda: deref(out))
        assert results == [1, 2, 3, 4, 5]

    def test_member_in_compiled_body(self):
        """A compiled predicate that calls member/2 to enumerate."""
        # nv
        from clausal.logic.compiler import compile_predicate_trampoline
        from clausal.logic.trampoline import StepGenerator, solutions

        mod = fresh_module()
        db = mod.db

        # pick(X) :- member(X, [a, b, c]).
        x = Var()
        db.assertz(Clause(
            head=("pick", x),
            body=[Call(func=LoadName(name="in_"), args=[x, ["a", "b", "c"]], kwargs=[])],
        ))
        compile_predicate_trampoline("pick", 1, db.clauses_for("pick", 1), db)

        out = Var()
        t = Trail()
        fn = db.get_dispatch("pick", 1)
        results = solutions(StepGenerator(fn, None, None, None, out, t), lambda: deref(out))
        assert results == ["a", "b", "c"]


# ── between/3 arithmetic bounds ───────────────────────────────────────────────


class TestBetweenArithmeticBounds:
    """between/3 evaluates arithmetic operator terms in its bound positions.

    todo/between3-does-not-evaluate-arithmetic-in-its-bounds.md: a bound
    written as an expression (``between(0, LENGTH - 1, X)``) used to reach the
    builtin as an unevaluated Sub term, fail the ``isinstance(int)`` guard,
    and silently yield nothing — findall then returned [] as a well-formed
    wrong answer.  The bounds now go through the same ground evaluator the
    ``==`` comparison surface uses (clpfd._eval_ground over
    ARITH_OPERATOR_TERMS); a ground bound that still is not an integer raises
    type_error(integer, ...) instead of failing silently.
    """

    def _between(self, low, high, x):
        return Call(func=LoadName(name="between"), args=[low, high, x], kwargs=[])

    def test_expression_high_bound_enumerates(self):
        """between(0, 3 - 1, X) enumerates 0..2 — the todo's core shape."""
        from clausal.terms import Sub
        x = Var()
        assert sol_var(self._between(0, Sub(left=3, right=1), x), x) == [0, 1, 2]

    def test_expression_low_bound_enumerates(self):
        """The low bound is evaluated too: between(1 + 1, 4, X) → 2..4."""
        from clausal.terms import Add
        x = Var()
        assert sol_var(self._between(Add(left=1, right=1), 4, x), x) == [2, 3, 4]

    def test_expression_bounds_check_mode(self):
        """Check mode evaluates as well: between(0, 2 * 2, 3) succeeds,
        between(0, 2 * 2, 5) fails."""
        from clausal.terms import Mult
        assert len(solutions(self._between(0, Mult(left=2, right=2), 3))) == 1
        assert solutions(self._between(0, Mult(left=2, right=2), 5)) == []

    def test_nested_expression_bound(self):
        """Nested arithmetic evaluates through: between(0, (2 * 3) - 4, X)."""
        from clausal.terms import Mult, Sub
        x = Var()
        goal = self._between(0, Sub(left=Mult(left=2, right=3), right=4), x)
        assert sol_var(goal, x) == [0, 1, 2]

    def test_integral_division_bound_accepted(self):
        """6 / 2 evaluates to the exact rational 3 (house int/int → Fraction);
        an integer-valued bound is an integer bound."""
        from clausal.terms import Div
        x = Var()
        assert sol_var(self._between(0, Div(left=6, right=2), x), x) == [0, 1, 2, 3]

    def test_non_integral_bound_raises_type_error(self):
        """A ground bound that evaluates to a non-integer (7/2) raises
        type_error(integer, ...) — not a silent []."""
        from clausal.terms import Div
        from clausal.logic.exceptions import LogicException
        x = Var()
        with pytest.raises(LogicException) as exc:
            sol_var(self._between(0, Div(left=7, right=2), x), x)
        err = exc.value.term
        assert cell_functor(err) == "error"
        assert cell_functor(cell_args(err)[0]) == "type_error"
        assert cell_args(cell_args(err)[0])[0] == mint("integer")

    def test_ground_non_numeric_expression_raises_type_error(self):
        """An arith term over non-numeric ground leaves cannot evaluate:
        typed error naming the unevaluated bound, not silence."""
        from clausal.terms import Add
        from clausal.logic.exceptions import LogicException
        x = Var()
        with pytest.raises(LogicException) as exc:
            sol_var(self._between(0, Add(left="a", right="b"), x), x)
        err = exc.value.term
        assert cell_functor(cell_args(err)[0]) == "type_error"
        assert cell_args(cell_args(err)[0])[0] == mint("integer")

    @pytest.mark.parametrize("shape", ["var_first", "garbage_first"])
    def test_unbound_var_mixed_with_garbage_still_raises(self, shape):
        """``N - "a"`` with N unbound raises, whichever side the garbage is
        on (roborev job 13): no future binding of N makes the bound legal,
        so the loud typed error beats the silent mode-failure an unbound
        Var alone gets.  Order-independence pinned by the two shapes."""
        from clausal.terms import Sub
        from clausal.logic.exceptions import LogicException
        x = Var()
        n = Var()
        bound = (Sub(left=n, right="a") if shape == "var_first"
                 else Sub(left="a", right=n))
        with pytest.raises(LogicException) as exc:
            sol_var(self._between(0, bound, x), x)
        assert cell_functor(cell_args(exc.value.term)[0]) == "type_error"

    def test_ground_zero_divisor_raises_evaluation_error(self):
        """``1 // 0`` in a bound is ISO's ``evaluation_error(zero_divisor)``
        naming the operator (Q4, 2026-09-28; it was type_error(integer,
        1 // 0) naming between/3, when the evaluator answered None)."""
        from clausal.terms import FloorDiv
        from clausal.logic.exceptions import LogicException
        x = Var()
        with pytest.raises(LogicException) as exc:
            sol_var(self._between(0, FloorDiv(left=1, right=0), x), x)
        err = exc.value.term
        assert cell_args(err)[0] == ("evaluation_error", mint("zero_divisor"))
        assert cell_args(err)[1] == ("/", "//", 2)

    def test_expression_with_unbound_leaf_is_an_instantiation_error(self):
        """A bound expression still containing an unbound Var behaves like a
        plain unbound bound -- since 2026-09-30 an instantiation error, as
        Scryer's library(between), not a silent failure."""
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Sub
        x = Var()
        with pytest.raises(LogicException) as info:
            sol_var(self._between(0, Sub(left=Var(), right=1), x), x)
        assert cell_args(info.value.term)[0] == mint("instantiation_error")

    def test_plain_unbound_bound_is_an_instantiation_error(self):
        """2026-09-30 (Scryer's library(between)): between(0, HIGH, X) with
        HIGH unbound is an instantiation error; it used to fail silently."""
        from clausal.logic.exceptions import LogicException
        x = Var()
        with pytest.raises(LogicException) as info:
            sol_var(self._between(0, Var(), x), x)
        assert cell_args(info.value.term)[0] == mint("instantiation_error")

    def test_bool_bounds_are_a_type_error(self):
        """A09-F015: a bool bound is still rejected (True is not 1) -- since
        2026-09-30 as type_error(integer, B), as Scryer, not by failing."""
        from clausal.logic.exceptions import LogicException
        x = Var()
        with pytest.raises(LogicException) as info:
            sol_var(self._between(False, True, x), x)
        assert cell_functor(cell_args(info.value.term)[0]) == "type_error"

    def test_c_and_python_paths_agree_on_expression_bounds(self):
        """The evaluation happens at the dispatch boundary, so the C and
        Python paths see identical (already-evaluated) bounds."""
        import clausal.logic.builtins.arithmetic as ar
        from clausal.terms import Sub
        x = Var()
        with_c = sol_var(self._between(0, Sub(left=3, right=1), x), x)
        saved = ar._USE_C_ARITH
        ar._USE_C_ARITH = False
        try:
            x2 = Var()
            without_c = sol_var(self._between(0, Sub(left=3, right=1), x2), x2)
        finally:
            ar._USE_C_ARITH = saved
        assert with_c == without_c == [0, 1, 2]

    def test_todo_repro_surface_level(self):
        """The exact repro from the todo: findall over between(0, LENGTH - 1, X)
        in a compiled .clausal module returns [0, 1, 2], not []."""
        import os
        import tempfile
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call
        from clausal.logic import solve as solve_mod

        src = (
            "-module(btwfix, [])\n"
            "\n"
            "btw_probe(XS) <- (\n"
            "    LENGTH == 3,\n"
            "    findall(X, between(0, LENGTH - 1, X), XS),\n"
            ")\n"
        )
        with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                         delete=False) as f:
            f.write(src)
            path = f.name
        try:
            pymod = _load_module("btwfix_between_bounds", path)
            m = pymod.__dict__["$module"]
            solve_mod._query_cache.clear()
            xs = Var()
            out = [deref(xs) for _ in call("btw_probe", xs, module=m)]
            assert out == [[0, 1, 2]]
        finally:
            os.unlink(path)
