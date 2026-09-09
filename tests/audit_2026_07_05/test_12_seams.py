"""A12 seams & synthesis — adversarial cross-subsystem boundary tests (2026-07-06).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/12-seams/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
seam behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_12_seams.py -v

Seams under test (boundaries the partition split apart):
- tabling (A04) x dif (A05) x CLP(FD) (A06): constraint survival through
  table answer storage/replay, propagation wake-up across hook families
- compiler-emits (A03) x runtime-consumes (A04): TRO-shaped tail calls under
  -table, directive-target validation, ==-goal lowering into CLP(Z)
- terms/dunders (A01) x head matcher/dispatch (A02): attributed-var and
  strings-as-lists queries through indexed dispatch
- import hook (A10) x compiler (A03) x runtime (A04/A09): module-namespace
  engine-name leakage, -dynamic forward declarations, assertz reindexing

Fixture discipline: every module is loaded exactly ONCE under a unique module
name (atoms/functors and table state are module-scoped).
"""
import pytest

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import solve, call, _query_cache
from clausal.logic.variables import (
    Var,
    Trail,
    deref,
    is_var,
    unify,
    get_attr,
)
from clausal.logic.constraints import dif, DIF_KEY
from clausal.logic.clpfd import in_domain, label, fd_eq, fd_ne, FD_KEY


# ── Fixture loader ────────────────────────────────────────────────────────────

_loaded = {}


@pytest.fixture(scope="session")
def load(tmp_path_factory):
    def _load(name, source):
        if name not in _loaded:
            d = tmp_path_factory.mktemp("a12fix")
            p = d / f"{name}.clausal"
            p.write_text(source)
            _loaded[name] = _load_module(f"a12_{name}", str(p))
        return _loaded[name]
    yield _load
    _loaded.clear()


@pytest.fixture(autouse=True)
def _clear_query_cache():
    _query_cache.clear()
    yield
    _query_cache.clear()


DIAMOND = """\
step(1, 2),
step(1, 3),
step(2, 4),
step(3, 4),
"""


# ══════════════════════════════════════════════════════════════════════════════
# A12-F001 — tabled answer replay discards attributed-var constraints
# (tabling A04 x dif A05 x CLP(FD) A06). First evaluation yields an answer var
# carrying the dif/FD attribute; the SECOND identical query replays the stored
# answer with the constraint gone, so td(X), X is 1 succeeds against td's
# body constraint X is not 1.
# ══════════════════════════════════════════════════════════════════════════════

class TestF001TablingReplayDropsConstraints:
    TD_SRC = """\
-table(td/1)

td(X) <- (X is not 1)
"""
    TF_SRC = """\
-table(tf/1)

tf(X) <- in_domain(X, 1, 3)
"""

    def test_first_evaluation_answer_carries_dif(self, load):
        m = load("f001_dif", self.TD_SRC)
        x = Var()
        seen = []
        for _ in solve(m.td(x)):
            xv = deref(x)
            seen.append(is_var(xv) and get_attr(xv, DIF_KEY) is not None)
        assert seen == [True]

    @pytest.mark.xfail(strict=False,
                       reason="A12-F001: table replay drops the dif constraint "
                              "— replayed answer var has no dif attr and "
                              "unifies with the excluded value")
    def test_replayed_answer_still_carries_dif(self, load):
        m = load("f001_dif", self.TD_SRC)
        x = Var()
        list(solve(m.td(x)))            # fill the table
        _query_cache.clear()
        y = Var()
        for _ in solve(m.td(y)):
            yv = deref(y)
            assert is_var(yv) and get_attr(yv, DIF_KEY) is not None
            t = Trail()
            assert not unify(y, 1, t), (
                "td(Y) then Y=1 must fail (body posts Y is not 1)"
            )

    @pytest.mark.xfail(strict=False,
                       reason="A12-F001: table replay drops the FD domain")
    def test_replayed_answer_still_carries_fd_domain(self, load):
        m = load("f001_fd", self.TF_SRC)
        x = Var()
        list(solve(m.tf(x)))            # fill the table
        _query_cache.clear()
        y = Var()
        for _ in solve(m.tf(y)):
            yv = deref(y)
            assert is_var(yv), "answer should be an unbound domain var"
            st = get_attr(yv, FD_KEY)
            assert st is not None, "FD domain lost in table replay"

    def test_first_evaluation_answer_carries_fd_domain(self, load):
        m = load("f001_fd_first", self.TF_SRC)
        x = Var()
        seen = []
        for _ in solve(m.tf(x)):
            xv = deref(x)
            seen.append(is_var(xv) and get_attr(xv, FD_KEY) is not None)
        assert seen == [True]


# ══════════════════════════════════════════════════════════════════════════════
# A12-F002 — `X == <non-numeric term>` (atom / str) succeeds vacuously,
# posting an unbounded CLP(Z) constraint on X (== goal lowering A03 x CLP(Z)
# entry A06 x atoms A01). The resulting var then unifies with 42 but NOT with
# the named atom — inverted semantics. Cheat-sheet documents this trap as the
# "broken FD var"; the standing contract says == is *arithmetic* equality, so
# a non-numeric ground operand must raise a type error or fail, never succeed.
# ══════════════════════════════════════════════════════════════════════════════

class TestF002EqNonNumericOperand:
    SRC = """\
-private([myatom])

badeq(X) <- (X == myatom)

badeqs(X) <- (X == "somestr")
"""

    def test_eq_atom_operand_rejected(self, load):
        m = load("f002", self.SRC)
        x = Var()
        try:
            sols = list(solve(m.badeq(x)))
        except Exception:
            return  # a (catchable) type error is acceptable
        assert sols == [], "X == myatom must not succeed"

    def test_eq_str_operand_rejected(self, load):
        m = load("f002", self.SRC)
        x = Var()
        try:
            sols = list(solve(m.badeqs(x)))
        except Exception:
            return
        assert sols == [], 'X == "somestr" must not succeed'

    def test_eq_atom_raises_catchable_type_error(self, load):
        # A12-F002 fixed: X == myatom now raises a catchable LogicException
        # (type error) instead of leaving X an inverted-semantics FD var.
        from clausal.logic.exceptions import LogicException
        m = load("f002", self.SRC)
        x = Var()
        with pytest.raises(LogicException):
            list(solve(m.badeq(x)))

    # A12-F002 gap: a ground COMPOUND == operand kept the inverted semantics
    # (after X == point4(1,2): unify(X, 42) → True, unify(X, point4(1,2)) →
    # False). Ground data terms — PredicateMeta term instances and runtime
    # Compounds — must raise the same catchable type_error, while arithmetic
    # expression trees stay legal.
    CMP_SRC = """\
-private([point4(PPA, PPB)])

badeqc(CX) <- (CX == point4(1, 2))

okadd(AX) <- (AX == 3 + 4)

oklin(LX, LY) <- (LX == LY * 2, LY == 3)
"""

    def test_eq_ground_compound_operand_raises_catchable_type_error(self, load):
        from clausal.logic.exceptions import LogicException
        m = load("f002_cmp", self.CMP_SRC)
        x = Var()
        with pytest.raises(LogicException):
            list(solve(m.badeqc(x)))

    def test_eq_runtime_compound_operand_raises_catchable_type_error(self):
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Compound
        tr = Trail()
        x = Var()
        with pytest.raises(LogicException):
            fd_eq(x, Compound("pt", (1, 2)), tr)

    def test_eq_arith_expression_operands_still_legal(self, load):
        # controls: expression trees must NOT be caught by the compound guard
        m = load("f002_cmp", self.CMP_SRC)
        x = Var()
        assert [deref(x) for _ in solve(m.okadd(x))] == [7]
        _query_cache.clear()
        x, y = Var(), Var()
        assert [deref(x) for _ in solve(m.oklin(x, y))] == [6]
        # ground non-linear expr node reaching the guard (Pow bypasses both
        # the linearise arm and _both_ground) must also stay legal
        from clausal.terms import Pow
        tr = Trail()
        z = Var()
        assert fd_eq(z, Pow(left=2, right=3), tr) is True
        assert deref(z) == 8


class TestF002EqNonRealOperand:
    """Extension of the A12-F002 guard: its original blocklist (atoms,
    strings, collections, ground compounds) let dates, Quantities, Decimals,
    None, … through — and the posted EqConstraint's unification hook accepts
    integers only, so the var then rejected EVERY later binding including the
    equal one (``fd_eq(X, date(...)); unify(X, same_date)`` → False).  The
    guard is now the same exactly-one-var + ``numbers.Real`` allowlist the
    ordering comparators use, keeping the ``evaluable`` error shape.
    Fixed: todo/eq-comparison-with-date-or-quantity-operand-posts-broken-var.md
    """

    def _assert_evaluable_error(self, exc_info, culprit):
        term = exc_info.value.term
        assert term.functor == "error"
        inner = term.args[0]
        assert inner.functor == "type_error"
        assert inner.args[0] == mint("evaluable")
        assert inner.args[1] == culprit
        assert term.args[1] == "(==)/2"

    def test_eq_date_operand_raises_catchable_type_error(self):
        import datetime as dt
        from clausal.logic.exceptions import LogicException
        target = dt.date(2026, 6, 1)
        with pytest.raises(LogicException) as ei:
            fd_eq(Var(), target, Trail())
        self._assert_evaluable_error(ei, target)

    def test_eq_datetime_operand_raises_catchable_type_error(self):
        import datetime as dt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(Var(), dt.datetime(2026, 6, 1, 12, 0), Trail())

    def test_eq_quantity_operand_raises_catchable_type_error(self):
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        with pytest.raises(LogicException) as ei:
            fd_eq(Var(), Quantity(5, {metre: 1}), Trail())
        self._assert_evaluable_error(ei, Quantity(5, {metre: 1}))

    def test_eq_decimal_operand_raises_catchable_type_error(self):
        from decimal import Decimal
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(Var(), Decimal("2.5"), Trail())

    def test_eq_none_operand_raises_catchable_type_error(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(Var(), None, Trail())

    def test_eq_ground_side_may_be_left_operand(self):
        import datetime as dt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(dt.date(2026, 6, 1), Var(), Trail())

    # ── controls: numeric and both-ground == unchanged ───────────────────

    def test_eq_int_still_posts_and_binds(self):
        tr = Trail()
        x = Var()
        assert fd_eq(x, 5, tr) is True
        assert deref(x) == 5

    def test_eq_float_still_dispatches_and_binds(self):
        tr = Trail()
        x = Var()
        assert fd_eq(x, 2.5, tr) is True
        assert deref(x) == 2.5

    def test_eq_fraction_still_dispatches(self):
        from fractions import Fraction
        tr = Trail()
        x = Var()
        assert fd_eq(x, Fraction(1, 2), tr) is True

    def test_eq_real_attr_var_vs_str_raises_not_posts(self):
        # A var already carrying a CLP(R) attribute triggers the real
        # dispatch on its own; the guard must fire before that dispatch in
        # the Python build too (same divergence roborev job 266 found in the
        # ordering comparators).
        from clausal.logic.exceptions import LogicException
        tr = Trail()
        x = Var()
        from clausal.logic.clpr import real_le
        assert real_le(x, 9.5, tr)  # gives x a REAL attribute
        with pytest.raises(LogicException):
            fd_eq(x, "somestr", tr)

    def test_eq_both_ground_dates_still_python_equality(self):
        import datetime as dt
        tr = Trail()
        assert fd_eq(dt.date(2026, 6, 1), dt.date(2026, 6, 1), tr) is True
        assert fd_eq(dt.date(2026, 6, 1), dt.date(2026, 6, 2), tr) is False

    def test_eq_both_ground_quantities_still_python_equality(self):
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        tr = Trail()
        assert fd_eq(Quantity(5, {metre: 1}), Quantity(5, {metre: 1}), tr) is True
        assert fd_eq(Quantity(5, {metre: 1}), Quantity(3, {metre: 1}), tr) is False


class TestF002NeNonRealOperand:
    """Third member of the A12-F002 defect family: ``!=`` (arithmetic
    disequality, ``nodes.ArithNeq`` → ``fd_ne``) never got any guard, so
    ``X != "banana"`` posted a NeConstraint whose unification hook accepts
    integers only — every later non-integer binding of X was rejected and
    ``X != "banana", X is "apple"`` silently lost its solution.  Same
    exactly-one-var + ``numbers.Real`` allowlist as ``==``/the ordering
    comparators, with the ``evaluable`` kind (``!=`` is ``==``'s arithmetic
    sibling; ``dif/2`` remains the structural disequality) and context
    ``"(!=)/2"`` (the clausal surface operator, matching ``"(==)/2"``).
    Fixed: todo/arith-disequality-on-unbound-var-rejects-all-later-bindings.md
    """

    def _assert_evaluable_error(self, exc_info, culprit):
        term = exc_info.value.term
        assert term.functor == "error"
        inner = term.args[0]
        assert inner.functor == "type_error"
        assert inner.args[0] == mint("evaluable")
        assert inner.args[1] == culprit
        assert term.args[1] == "(!=)/2"

    def test_ne_str_operand_raises_catchable_type_error(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_ne(Var(), "banana", Trail())
        self._assert_evaluable_error(ei, "banana")

    def test_ne_ground_side_may_be_left_operand(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_ne("banana", Var(), Trail())
        self._assert_evaluable_error(ei, "banana")

    def test_ne_date_operand_raises_catchable_type_error(self):
        import datetime as dt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_ne(Var(), dt.date(2026, 6, 1), Trail())

    def test_ne_quantity_operand_raises_catchable_type_error(self):
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        with pytest.raises(LogicException):
            fd_ne(Var(), Quantity(5, {metre: 1}), Trail())

    def test_ne_compiled_repro_raises_instead_of_losing_solution(self, load):
        # The silent-loss shape: X != "banana", X is "apple" had 0 solutions.
        from clausal.logic.exceptions import LogicException
        m = load("f002_ne", """\
badne(X) <- ( X != "banana", X is "apple" )
""")
        with pytest.raises(LogicException):
            list(solve(m.badne(Var())))

    # ── controls: numeric, residual and both-ground != unchanged ─────────

    def test_ne_int_residual_still_works(self):
        tr = Trail()
        x = Var()
        assert fd_ne(x, 5, tr) is True
        assert unify(x, 4, tr) is True

    def test_ne_int_residual_still_excludes_operand(self):
        tr = Trail()
        x = Var()
        assert fd_ne(x, 5, tr) is True
        assert unify(x, 5, tr) is False

    def test_ne_float_still_dispatches_clpr(self):
        tr = Trail()
        x = Var()
        assert fd_ne(x, 2.5, tr) is True

    def test_ne_fraction_still_dispatches_clpq(self):
        from fractions import Fraction
        tr = Trail()
        x = Var()
        assert fd_ne(x, Fraction(1, 2), tr) is True

    def test_ne_var_var_still_legal(self):
        assert fd_ne(Var(), Var(), Trail()) is True

    def test_ne_expr_tree_still_legal(self):
        from clausal.terms import Add
        tr = Trail()
        x, y = Var(), Var()
        assert fd_ne(x, Add(left=y, right=1), tr) is True

    def test_ne_both_ground_mixed_types_still_python_ne(self):
        # Python != between mismatched types falls back to identity and
        # never raises — no TypeError conversion needed on the ground path.
        tr = Trail()
        assert fd_ne("a", 5, tr) is True
        import datetime as dt
        assert fd_ne(dt.date(2026, 1, 1), "x", tr) is True

    def test_ne_both_ground_strings_still_python_ne(self):
        tr = Trail()
        assert fd_ne("a", "b", tr) is True
        assert fd_ne("a", "a", tr) is False


class TestF002ExprTreeVsNonNumericOperand:
    """The guards checked only the exactly-one-bare-Var case, so with the var
    one level down in an arithmetic expression tree both sides deref to
    non-Vars and the guard returned early: ``X + 1 == "banana"`` posted an
    EqConstraint whose ``_expr_domain`` catch-all treats the string as an
    unconstrained integer — it then accepted ``X = 5`` (silently wrong
    answers, worse than the bare-var case which at least rejected
    everything).  A tree *containing* a var now counts as the var side; a
    fully-ground tree still counts as ground (``2 + 3 == "banana"`` keeps
    falling back to Python ``==`` → False after _resolve).
    Fixed: todo/nonnumeric-operand-vs-var-inside-expr-tree-unguarded.md
    """

    def _add(self, l, r):
        from clausal.terms import Add
        return Add(left=l, right=r)

    def test_eq_var_tree_vs_str_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_eq(self._add(Var(), 1), "banana", Trail())
        term = ei.value.term
        assert term.args[0].functor == "type_error"
        assert term.args[0].args[0] == mint("evaluable")
        assert term.args[0].args[1] == "banana"
        assert term.args[1] == "(==)/2"

    def test_eq_str_vs_var_tree_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq("banana", self._add(Var(), 1), Trail())

    def test_eq_var_tree_vs_date_raises(self):
        import datetime as dt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(self._add(Var(), 1), dt.date(2026, 6, 1), Trail())

    def test_ne_var_tree_vs_str_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_ne(self._add(Var(), 1), "banana", Trail())
        assert ei.value.term.args[1] == "(!=)/2"

    def test_eq_compiled_repro_raises_instead_of_wrong_answer(self, load):
        # The reported repro: X + 1 == "banana" posted, then accepted X is 4.
        from clausal.logic.exceptions import LogicException
        m = load("f002_exprtree", """\
badexpr(X) <- ( X + 1 == "banana", X is 4 )
""")
        with pytest.raises(LogicException):
            list(solve(m.badexpr(Var())))

    # ── controls ─────────────────────────────────────────────────────────

    def test_eq_var_tree_vs_int_still_propagates(self):
        tr = Trail()
        x = Var()
        assert fd_eq(self._add(x, 1), 5, tr) is True
        assert deref(x) == 4

    def test_eq_var_tree_vs_var_tree_still_legal(self):
        tr = Trail()
        assert fd_eq(self._add(Var(), 1), self._add(Var(), 2), tr) is True

    def test_eq_var_vs_var_tree_still_legal(self):
        tr = Trail()
        assert fd_eq(Var(), self._add(Var(), 1), tr) is True

    def test_eq_ground_tree_vs_str_still_python_equality(self):
        # _resolve (Python) / the C impl evaluate a fully-ground tree to a
        # scalar, and ground == ground falls back to Python == → False. The
        # guard must NOT reclassify a ground tree as the var side.
        tr = Trail()
        assert fd_eq(self._add(2, 3), "banana", tr) is False

    def test_ne_ground_tree_vs_str_still_python_ne(self):
        tr = Trail()
        assert fd_ne(self._add(2, 3), "banana", tr) is True

    def test_eq_var_tree_vs_ground_tree_still_legal(self):
        tr = Trail()
        x = Var()
        assert fd_eq(self._add(x, 1), self._add(2, 3), tr) is True
        assert deref(x) == 4


class TestNonNumericLeafInsideExprTree:
    """Residue of TestF002ExprTreeVsNonNumericOperand: garbage as a LEAF of
    the expression tree itself (``X + "a" == 5``) still posted silently.
    ``_linearise`` fails on the string leaf, the EqConstraint is posted, and
    ``_expr_domain``'s catch-all treated the leaf as an unconstrained
    integer — X stayed unconstrained, silently wrong verdicts (worse under
    ``not`` / indeterminate routes).  ``!=`` shared the defect one walker
    over: ``_eval_ground`` returned ``None`` for the garbage leaf, which
    NeConstraint reads as "still has unbound vars", keeping the constraint
    pending forever — ``2 + "a" == 5`` and ``X + "a" != 5`` both succeeded.
    Both leaf fall-throughs now raise the house-style catchable
    ``type_error(integer, Leaf, "clpfd expression")``.  Recognized arithmetic
    NODES (Div/FloorDiv/Mod/Pow, ground or not) and int/Var leaves keep
    their previous behaviour exactly, and Fraction leaves in trees keep
    dispatching to CLP(Q) before any FD walker runs.
    Fixed: todo/nonnumeric-leaf-inside-expr-tree-unguarded.md
    """

    def _add(self, l, r):
        from clausal.terms import Add
        return Add(left=l, right=r)

    def _assert_integer_leaf_error(self, exc_info, culprit):
        term = exc_info.value.term
        assert term.functor == "error"
        inner = term.args[0]
        assert inner.functor == "type_error"
        assert inner.args[0] == mint("integer")
        # The culprit is the operand AS THE CALLER PASSED IT: a Python
        # ``str`` operand stays a STRING (THE FLIP), while an operand
        # written as ``"a"`` in .clausal source is an ATOM — see
        # ``test_compiled_leaf_error_is_catchable``, which expects one.
        assert inner.args[1] == culprit
        assert term.args[1] == "clpfd expression"

    # ── the repro: eq / ne / orderings with a garbage leaf ───────────────

    def test_eq_str_leaf_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_eq(self._add(Var(), mint("a")), 5, Trail())
        self._assert_integer_leaf_error(ei, mint("a"))

    def test_eq_str_leaf_on_rhs_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(5, self._add(Var(), mint("a")), Trail())

    def test_ne_str_leaf_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_ne(self._add(Var(), mint("a")), 5, Trail())
        self._assert_integer_leaf_error(ei, mint("a"))

    def test_lt_str_leaf_raises(self):
        from clausal.logic.clpfd import fd_lt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_lt(self._add(Var(), mint("a")), 5, Trail())
        self._assert_integer_leaf_error(ei, mint("a"))

    def test_le_str_leaf_raises(self):
        from clausal.logic.clpfd import fd_le
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_le(self._add(Var(), mint("a")), 5, Trail())

    def test_gt_str_leaf_raises(self):
        from clausal.logic.clpfd import fd_gt
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_gt(self._add(Var(), mint("a")), 5, Trail())

    # ── other garbage leaf kinds (same allowlist as the operand guards) ──

    def test_none_leaf_raises(self):
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_eq(self._add(Var(), None), 5, Trail())
        self._assert_integer_leaf_error(ei, None)

    def test_quantity_leaf_raises(self):
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Quantity
        from clausal.modules.units import metre
        q = Quantity(2, {metre: 1})
        with pytest.raises(LogicException) as ei:
            fd_eq(self._add(Var(), q), 5, Trail())
        self._assert_integer_leaf_error(ei, q)

    def test_ground_quantity_tree_vs_var_raises(self):
        # X == Quantity(2, m) * 2: the tree is fully ground but not
        # FD-evaluable.  Before the fix it posted, left X unconstrained, and
        # then accepted unify(X, 42) — silently wrong.  Units arithmetic in
        # constraint position is not (and was not) supported; the typed
        # error points users at ``is``, where Quantity.__mul__ works.
        from clausal.logic.exceptions import LogicException
        from clausal.terms import Mult, Quantity
        from clausal.modules.units import metre
        q = Quantity(2, {metre: 1})
        with pytest.raises(LogicException):
            fd_eq(Var(), Mult(left=q, right=2), Trail())

    def test_float_leaf_raises(self):
        # A bare float leaf inside a var-containing FD tree never dispatched
        # to CLP(R) (_is_real_arg does not walk trees) and was treated as an
        # unconstrained integer.  CLP(Z) semantics: type_error(integer, 0.5).
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            fd_eq(self._add(Var(), 0.5), 5, Trail())
        self._assert_integer_leaf_error(ei, 0.5)

    def test_fully_ground_float_tree_folds_to_clpr(self):
        # The float raise above is the VAR-adjacent case only.  A fully
        # ground tree with a float leaf folds numerically in _eval_ground
        # and dispatches to CLP(R) — the pre-existing FD/R boundary, which
        # the leaf guard must not move (roborev job 14): 2 + 0.5 is real
        # arithmetic, not garbage.
        assert fd_eq(self._add(2, 0.5), 2.5, Trail()) is True
        assert fd_eq(self._add(2, 0.5), 5, Trail()) is False

    def test_ground_tree_with_str_leaf_raises(self):
        # 2 + "a" == 5 previously succeeded outright (no vars: EqConstraint
        # posted, default domain ∩ {5} non-empty → True).
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            fd_eq(self._add(2, mint("a")), 5, Trail())

    # ── the sibling walkers: reification and _expr_domain itself ─────────

    def test_reify_str_leaf_raises(self):
        from clausal.logic.clpfd import reify_fd
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            reify_fd("eq", self._add(Var(), mint("a")), 5, Trail())

    def test_expr_domain_unknown_leaf_raises(self):
        # The enforcement point named by the todo: the catch-all must never
        # hand back the default domain for a leaf it cannot type as integer
        # (this is the path element/3 items and sum totals also take, and
        # the C slow path delegates trees here).
        from clausal.logic.clpfd import _expr_domain
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException) as ei:
            _expr_domain("a", Trail())
        self._assert_integer_leaf_error(ei, "a")

    # ── compiled routes: raise instead of wrong answer; catchable ────────

    def test_compiled_repro_raises_instead_of_wrong_answer(self, load):
        from clausal.logic.exceptions import LogicException
        m = load("leafguard", """\
badleaf(X) <- ( X + "a" == 5, X is 4 )
""")
        with pytest.raises(LogicException):
            list(solve(m.badleaf(Var())))

    def test_compiled_repro_catchable_via_catch3(self, load):
        # catch/3 must catch it, and the error term must be a proper ground
        # term that round-trips through unification with the catcher var.
        m = load("leafguard_catch", """\
safeleaf(SX, SE) <- catch((SX + "a" == 5), SE, 1 == 1)
""")
        e = Var()
        caught = [deref(e) for _ in solve(m.safeleaf(Var(), e))]
        assert len(caught) == 1
        term = caught[0]
        assert term.functor == "error"
        assert term.args[0].functor == "type_error"
        assert term.args[0].args[0] == mint("integer")
        assert term.args[0].args[1] == mint("a")
        assert term.args[1] == "clpfd expression"

    # ── controls: legitimate leaves and nodes keep working ───────────────

    def test_int_leaf_still_propagates(self):
        tr = Trail()
        x = Var()
        assert fd_eq(self._add(x, 1), 5, tr) is True
        assert deref(x) == 4

    def test_nested_arith_still_legal(self):
        from clausal.terms import Mult
        tr = Trail()
        x = Var()
        assert fd_eq(self._add(x, Mult(left=2, right=3)), 7, tr) is True
        assert deref(x) == 1

    def test_nonground_floordiv_node_still_posts(self):
        # A recognized arithmetic NODE containing vars must keep its default
        # (unbounded) domain — that over-approximation is deliberate.
        from clausal.terms import FloorDiv
        tr = Trail()
        assert fd_eq(self._add(Var(), FloorDiv(left=Var(), right=2)), 5, tr) is True

    def test_ground_pow_node_still_evaluates(self):
        from clausal.terms import Pow
        tr = Trail()
        z = Var()
        assert fd_eq(z, Pow(left=2, right=3), tr) is True
        assert deref(z) == 8

    def test_fraction_leaf_still_dispatches_clpq(self):
        from fractions import Fraction
        tr = Trail()
        x = Var()
        assert fd_eq(self._add(x, Fraction(1, 2)), 5, tr) is True
        assert deref(x) == Fraction(9, 2)

    def test_ne_var_tree_still_posts_and_enforces(self):
        tr = Trail()
        x = Var()
        assert fd_ne(self._add(x, 1), 5, tr) is True
        assert unify(x, 4, tr) is False  # 4 + 1 == 5 violates X + 1 != 5
        assert unify(x, 7, tr) is True

    def test_ne_both_ground_tree_still_python_ne(self):
        tr = Trail()
        assert fd_ne(self._add(2, 3), 5, tr) is False
        assert fd_ne(self._add(2, 3), 6, tr) is True


# ══════════════════════════════════════════════════════════════════════════════
# A12-F003 — directive targets are not validated: -table naming an undefined
# predicate, or a defined predicate with the wrong arity, is silently accepted
# and the predicate runs UNtabled (import hook A10 x tabling A04). A typo in a
# -table directive silently loses termination/dedup guarantees. Family of
# A10-F012 (malformed directive silent no-op), distinct: these directives are
# well-formed, their TARGET is dangling.
# ══════════════════════════════════════════════════════════════════════════════

class TestF003DirectiveTargetValidation:

    def test_table_of_undefined_predicate_errors_at_load(self, load):
        with pytest.raises(Exception):
            load("f003_ghost", """\
-table(zzz_no_such_pred/2)

q(1),
""")

    def test_table_with_wrong_arity(self, load):
        # -table(reach/3) but reach/2 is defined: load should error, or at
        # minimum reach/2 must not silently lose tabling (diamond dedup).
        try:
            m = load("f003_arity", DIAMOND + """\

-table(reach/3)

reach(X, Y) <- (X is Y)
reach(X, Y) <- (
    step(X, Z),
    reach(Z, Y)
)
""")
        except Exception:
            return  # load error is the preferred behaviour
        y = Var()
        got = sorted(deref(y) for _ in solve(m.reach(1, y)))
        assert got == [1, 2, 3, 4], f"untabled: duplicate answers {got}"


# ══════════════════════════════════════════════════════════════════════════════
# A12-F004 — engine helpers leak into every .clausal module namespace
# (import hook A10 x term layer A01/runtime A04): walk, deref, unify, Var,
# Trail, Compound are in scope in user modules, so a user predicate named
# walk/deref/unify fails at LOAD with a cryptic "takes no keyword arguments"
# TypeError. The docs reserve only *Python builtins*; these are engine
# internals. Related: A10-F013 (builtin call/N shadows clausal.call API).
# ══════════════════════════════════════════════════════════════════════════════

class TestF004EngineNamespaceLeak:

    @pytest.mark.parametrize("name", ["walk", "deref", "unify"])
    def test_user_predicate_named_after_engine_helper(self, load, name):
        # A12-F004 fixed: walk/deref/unify are injected $-prefixed only, so
        # a user predicate can use those public names.
        m = load(f"f004_{name}", f'{name}("a", "b"),\n')
        x = Var()
        got = [deref(x) for _ in solve(getattr(m, name)(mint("a"), x))]
        assert got == [mint("b")]

    def test_leak_is_observable_in_module_dict(self, load):
        m = load("f004_obs", "q(1),\n")
        import clausal.logic.variables as V
        leaked = {k for k in m.__dict__
                  if not k.startswith("_")
                  and getattr(V, k, None) is m.__dict__[k]}
        # A12-F004: walk/deref/unify are no longer leaked under public names
        # (generated bodies use the reserved $-prefix). The user-facing types
        # Var/Trail are intentionally still injected for embedded Python.
        assert not ({"walk", "deref", "unify"} & leaked)
        assert {"Var", "Trail"} <= leaked

    def test_solve_named_predicate_currently_works(self, load):
        # control: 'solve' is NOT leaked, so a solve/2 user predicate is fine
        m = load("f004_solve", 'solve("a", "b"),\n')
        x = Var()
        assert [deref(x) for _ in solve(m.solve(mint("a"), x))] == [mint("b")]

    def test_headlit_guard_immune_to_user_unify_predicate(self, load):
        # A12-F004 follow-up: the opaque head-literal guard (A02-F003) must
        # call the reserved $unify helper like its scalar/atom siblings. It
        # emitted _name("unify"), which a user predicate named unify/3
        # (loadable since A12-F004) shadows in the module dict — the guard
        # then "succeeds" on ANY caller value (a PredicateMeta __call__
        # returns a truthy term), so a non-matching exotic literal matched.
        import datetime
        m = load("f004_headlit", """\
unify(1, 2, 3),

-dynamic(hl_date/2)
hl_date("seed", 0),
""")
        logic_mod = m.__dict__["$module"]
        list(call("assertz", m.hl_date(datetime.date(2026, 1, 1), 1),
                  module=logic_mod))
        _query_cache.clear()
        r = Var()
        got = [deref(r) for _ in
               call("hl_date", datetime.date(1999, 9, 9), r, module=logic_mod)]
        assert got == [], "non-matching date head literal must NOT match"
        _query_cache.clear()
        r = Var()
        got = [deref(r) for _ in
               call("hl_date", datetime.date(2026, 1, 1), r, module=logic_mod)]
        assert got == [1], "matching date head literal must still match"


# ══════════════════════════════════════════════════════════════════════════════
# A12-F005 — -dynamic forward declaration without an initial clause does not
# mint the predicate's term class (import hook A10 x compiler globals_env A03
# x database ops A09): assertz(ghost(...)) in the SAME module raises
# NameError "Predicate 'ghost/1' is not in scope as a term class", so the
# declare-then-assertz workflow requires a dummy seed fact.
# ══════════════════════════════════════════════════════════════════════════════

class TestF005DynamicForwardDeclaration:
    SRC = """\
-dynamic(ghost/1)

seed <- assertz(ghost("x"))
"""

    def test_assertz_into_clauseless_dynamic_predicate(self, load):
        m = load("f005", self.SRC)
        logic_mod = m.__dict__["$module"]
        list(call("seed", module=logic_mod))
        x = Var()
        got = [deref(x) for _ in call("ghost", x, module=logic_mod)]
        assert got == [mint("x")]

    def test_declared_but_empty_dynamic_predicate_fails_cleanly(self, load):
        # A12-F005 spec acceptance: querying a declared-but-empty dynamic
        # predicate fails cleanly (0 solutions). It raised
        # NotImplementedError ("no compiled dispatch function") because
        # compile_module's pending map was built only from predicate_nodes,
        # so a clause-less minted class never got the always-fail dispatch.
        m = load("f005_empty", """\
-dynamic(ghost2/1)

probe(PX) <- ghost2(PX)
""")
        logic_mod = m.__dict__["$module"]
        x = Var()
        assert list(call("ghost2", x, module=logic_mod)) == []
        _query_cache.clear()
        x = Var()
        assert list(solve(m.ghost2(x))) == []
        _query_cache.clear()
        x = Var()
        assert list(solve(m.probe(x))) == []
        # assertz after the empty queries still works (dynamic stays open)
        _query_cache.clear()
        list(call("assertz", m.ghost2(mint("y")), module=logic_mod))
        _query_cache.clear()
        x = Var()
        assert [deref(x) for _ in solve(m.ghost2(x))] == [mint("y")]

    def test_directive_then_clause_keeps_named_fields(self, load):
        # A12-F005 regression: the -dynamic(pers/2) handler pre-registered
        # placeholder arg_0/arg_1 field names, so a later real clause could no
        # longer derive named fields from its head vars — pers._fields became
        # ('arg_0','arg_1') and m.pers(name=..., age=...) raised TypeError.
        # The first real clause's derived head-var names must win.
        m = load("f005_fields", """\
-dynamic(pers/2)

likes("bob", 42),

pers(NAME, AGE) <- likes(NAME, AGE)
""")
        assert m.pers._fields == ("name", "age")
        x = Var()
        got = [deref(x) for _ in solve(m.pers(name=mint("bob"), age=x))]
        assert got == [42]

    def test_dynamic_with_seed_fact_works(self, load):
        # control: with one initial fact the same workflow is fine
        m = load("f005_ctrl", """\
-dynamic(ghost/1)

ghost("init"),

seed <- assertz(ghost("x"))
""")
        logic_mod = m.__dict__["$module"]
        list(call("seed", module=logic_mod))
        x = Var()
        got = sorted(deref(x) for _ in solve(m.ghost(x)))
        assert got == [mint("init"), mint("x")]


# ══════════════════════════════════════════════════════════════════════════════
# Known-family seam confirmations (cited, not re-owned by A12)
# ══════════════════════════════════════════════════════════════════════════════

class TestKnownFamilySeams:

    @pytest.mark.xfail(strict=False,
                       reason="A06-F005 x A03 catch/3 seam: element/3's raw "
                              "ValueError bypasses catch/3 (family "
                              "A09-F012/A09-D002/A11-D001)")
    def test_catch_over_fd_builtin_raw_valueerror(self, load):
        m = load("kf_catch", """\
guarded(R) <- catch(bad_elem(R), _, R is "caught")

bad_elem(R) <- (
    element(I, [10, 20, 30], V),
    R is "no"
)
""")
        r = Var()
        got = [deref(r) for _ in solve(m.guarded(r))]
        assert got == [mint("caught")]

    def test_tabled_list_answer_via_liskov_char_list(self, load):
        # A04-F005 seam consequence, fixed by commit 5f0a5088 (tabled
        # answers hashable + type-distinguishing keys): a tabled predicate
        # whose answer contains a list used to crash (unhashable) when
        # queried with the char-list form of a str key.
        m = load("kf_unhash", """\
-table(sl/2)

sl(["a", "b"], R) <- (R is "matched")
""")
        r = Var()
        got = [deref(r) for _ in solve(m.sl([mint("a"), mint("b")], r))]
        assert got == [mint("matched")]


# ══════════════════════════════════════════════════════════════════════════════
# Seam regression guards — boundaries probed and found CORRECT (pin them)
# ══════════════════════════════════════════════════════════════════════════════

class TestDifClpfdComposition:
    """dif hook (A05) is woken by CLP(FD) narrowing/binding paths (A06)."""

    def test_singleton_domain_binding_wakes_dif(self):
        t = Trail()
        x, y = Var(), Var()
        assert dif(x, y, t)
        assert in_domain(x, 1, 1, t)        # binds x=1
        assert deref(x) == 1
        assert not in_domain(y, 1, 1, t)    # would bind y=1 -> dif fails it

    def test_fd_eq_narrow_to_bound_wakes_dif(self):
        t = Trail()
        x, y = Var(), Var()
        assert dif(x, y, t)
        assert in_domain(x, 5, 5, t)
        assert in_domain(y, 4, 5, t)
        assert not fd_eq(y, 5, t)

    def test_labeling_excludes_dif_violations(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 2, t)
        assert in_domain(y, 1, 2, t)
        assert dif(x, y, t)
        sols = set()
        for _ in label([x, y], t):
            sols.add((deref(x), deref(y)))
        assert sols == {(1, 2), (2, 1)}


class TestDispatchWithConstrainedVars:
    """Indexed first-arg dispatch (A02) filters through attr hooks (A05/A06)."""

    SRC = """\
p(1, "one"),
p(2, "two"),
p(3, "three"),
p(4, "four"),
p(5, "five"),
"""

    def test_fd_constrained_query_var(self, load):
        m = load("disp", self.SRC)
        t = Trail()
        x, r = Var(), Var()
        in_domain(x, 2, 3, t)
        got = [(deref(x), deref(r)) for _ in solve(m.p(x, r))]
        assert got == [(2, mint("two")), (3, mint("three"))]

    def test_dif_constrained_query_var(self, load):
        m = load("disp", self.SRC)
        t = Trail()
        x, r = Var(), Var()
        dif(x, 2, t)
        got = [(deref(x), deref(r)) for _ in solve(m.p(x, r))]
        assert got == [(1, mint("one")), (3, mint("three")), (4, mint("four")), (5, mint("five"))]


class TestControlConstraintScoping:
    """once/1 and not/1 (A03) interact correctly with the constraint trail
    (A05): constraints posted inside once survive; constraints posted inside
    a failed NAF goal are fully unwound."""

    def test_once_preserves_posted_dif(self, load):
        m = load("oncep", 'oncep(X) <- once(X is not 1)\n')
        x = Var()
        n = 0
        for _ in solve(m.oncep(x)):
            n += 1
            xv = deref(x)
            assert is_var(xv) and get_attr(xv, DIF_KEY) is not None
            t = Trail()
            assert not unify(x, 1, t)
        assert n == 1

    def test_naf_unwinds_constraints_of_failed_goal(self, load):
        m = load("nafp", """\
nafp(X) <- (not fail_after_dif(X))

fail_after_dif(X) <- (
    X is not 1,
    1 == 2
)
""")
        x = Var()
        n = 0
        for _ in solve(m.nafp(x)):
            n += 1
            xv = deref(x)
            assert not (is_var(xv) and get_attr(xv, DIF_KEY) is not None), (
                "dif attr leaked out of a failed NAF goal"
            )
            t = Trail()
            assert unify(x, 1, t)
        assert n == 1


class TestTablingReplayRespectsCallerConstraints:
    """Table answer replay (A04) unifies through the caller's attr hooks
    (A05/A06) — a constrained caller var filters stored answers."""

    SRC = """\
-table(td/1)

td(1),
td(2),
td(3),
"""

    def test_dif_constrained_caller(self, load):
        m = load("treplay", self.SRC)
        x = Var()
        assert sorted(deref(x) for _ in solve(m.td(x))) == [1, 2, 3]
        _query_cache.clear()
        t = Trail()
        y = Var()
        dif(y, 2, t)
        assert sorted(deref(y) for _ in solve(m.td(y))) == [1, 3]

    def test_fd_constrained_caller(self, load):
        m = load("treplay", self.SRC)
        _query_cache.clear()
        t = Trail()
        z = Var()
        in_domain(z, 2, 3, t)
        assert sorted(deref(z) for _ in solve(m.td(z))) == [2, 3]


class TestCompilerRuntimeTablingSeam:
    """Compiler-emitted recursion shapes (A03) drive the tabling runtime
    (A04) correctly: tail-position self-calls (TRO-eligible) and diamond
    graphs (multiple derivations of one answer) dedup and terminate."""

    def test_tail_recursive_tabled_diamond_dedups(self, load):
        m = load("ttail", DIAMOND + """\

-table(reach/2)

reach(X, Y) <- (X is Y)
reach(X, Y) <- (
    step(X, Z),
    reach(Z, Y)
)
""")
        y = Var()
        got = sorted(deref(y) for _ in solve(m.reach(1, y)))
        assert got == [1, 2, 3, 4]

    def test_left_recursive_tabled_diamond_dedups(self, load):
        m = load("tleft", DIAMOND + """\

-table(reach/2)

reach(X, Y) <- (X is Y)
reach(X, Y) <- (
    reach(X, Z),
    step(Z, Y)
)
""")
        y = Var()
        got = sorted(deref(y) for _ in solve(m.reach(1, y)))
        assert got == [1, 2, 3, 4]

    def test_deterministic_tail_recursion_under_table(self, load):
        m = load("tcnt", """\
-table(cnt/2)

cnt(0, R) <- (R is "done")
cnt(N, R) <- (
    N > 0,
    M == N - 1,
    cnt(M, R)
)
""")
        r = Var()
        assert [deref(r) for _ in solve(m.cnt(3, r))] == [mint("done")]


class TestStringsAsListsDispatchParity:
    """A str and its equivalent char-list take the same path through guard-
    and head-pattern dispatch (A01 Liskov contract x A02 list dispatch)."""

    GUARD_SRC = """\
r(L, R) <- (
    L is [],
    R is "empty"
)
r(L, R) <- (
    L is [_],
    R is "one"
)
r(L, R) <- (
    L is [_, _],
    R is "two"
)
r(L, R) <- (
    L is [_, _, _, *_],
    R is "many"
)
"""
    HEAD_SRC = """\
h([], R) <- (R is "empty")
h([_], R) <- (R is "one")
h([_, _], R) <- (R is "two")
h([_, _, _, *_], R) <- (R is "many")
"""

    # THE FLIP (2026-09-06-atoms-as-cells-strings §6.2) UNDID P3-1 Task 5's
    # retirement of the str~char-list cons rule, and this class's parity
    # claim — "a str and its char list take the same path" — holds again in
    # BOTH forms.  A body ``Is``-goal against a star-free list literal
    # compiles to a plain ``unify(L, [...], trail)``, and ``do_unify`` now
    # has the str↔list arm back, so the str probe reaches the same clause
    # its char-list twin does.  ``""`` and ``[]`` are one term.
    @pytest.mark.parametrize("probe,expected", [
        ([mint("a"), mint("b")], [mint("two")]),
        ("ab", [mint("two")]),
        ([], [mint("empty")]),
        ("", [mint("empty")]),
        ("abc", [mint("many")]),
    ])
    def test_guard_form_parity(self, load, probe, expected):
        m = load("liskov_guard", self.GUARD_SRC)
        _query_cache.clear()
        r = Var()
        assert [deref(r) for _ in solve(m.r(probe, r))] == expected

    @pytest.mark.parametrize("probe,expected", [
        ([mint("a"), mint("b")], [mint("two")]),
        ("ab", [mint("two")]),
        ([], [mint("empty")]),
        ("", [mint("empty")]),
        ("abcd", [mint("many")]),
    ])
    def test_head_pattern_parity(self, load, probe, expected):
        m = load("liskov_head", self.HEAD_SRC)
        _query_cache.clear()
        r = Var()
        assert [deref(r) for _ in solve(m.h(probe, r))] == expected

    def test_tabled_str_query_against_list_head(self, load):
        m = load("liskov_tabled", """\
-table(sl/2)

sl(["a", "b"], R) <- (R is "matched")
""")
        r = Var()
        # The head list ["a", "b"] is a list of char ATOMS — that IS the
        # string "ab" (THE FLIP §6.2) — so a str probe matches it.
        assert [deref(r) for _ in solve(m.sl("ab", r))] == [mint("matched")]


class TestAssertzReindexSeam:
    """assertz (A09) into an indexed -dynamic predicate (A02) is visible to
    findall (A03) and to new-key/unbound queries — the cheat-sheet §8 caveat
    about stale dispatch after assertz did NOT reproduce on this build."""

    SRC = """\
-dynamic(f/2)

f("a", 1),
f("b", 2),
f("c", 3),
f("d", 4),

keys(L) <- findall(K, f(K, _), L)

addone <- assertz(f("e", 5))
"""

    def test_assertz_reaches_findall_and_dispatch(self, load):
        m = load("reindex", self.SRC)
        logic_mod = m.__dict__["$module"]
        L = Var()
        for _ in solve(m.keys(L)):
            assert deref(L) == [mint("a"), mint("b"), mint("c"), mint("d")]
        list(call("addone", module=logic_mod))
        _query_cache.clear()
        L2 = Var()
        for _ in solve(m.keys(L2)):
            assert deref(L2) == [mint("a"), mint("b"), mint("c"),
                                 mint("d"), mint("e")]
        _query_cache.clear()
        v = Var()
        assert [deref(v) for _ in solve(m.f(mint("e"), v))] == [5]
        _query_cache.clear()
        k, v2 = Var(), Var()
        got = [(deref(k), deref(v2)) for _ in solve(m.f(k, v2))]
        assert got == [(mint("a"), 1), (mint("b"), 2), (mint("c"), 3),
                       (mint("d"), 4), (mint("e"), 5)]
