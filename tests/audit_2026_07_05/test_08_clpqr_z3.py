"""A08 CLP(Q/R), Z3 & ortools — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/08-clpqr-z3/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    PYTHONPATH=/workspace/clausal-bug-fix \
    /home/node/.pyenv/versions/3.13.3/bin/python -m pytest \
        tests/audit_2026_07_05/test_08_clpqr_z3.py -v -p no:cacheprovider

Notes:
- These tests exercise the subsystem at its Python API surface (the builtins
  in builtins/z3_constraints.py etc. are thin generator wrappers over the
  same functions).
- Two CLP(R) repros (F010) HANG the interpreter on current code; they are run
  in a subprocess with a 6 s timeout (the repo's pytest-timeout budget is 10 s
  per test, thread method — subprocess timeouts must stay below it).
- z3-solver and ortools were both installed for the audit interpreter; tests
  skip cleanly if they are absent.
"""
import gc
import subprocess
import sys
import math
from fractions import Fraction as F

import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, unify, get_attr

# ── availability flags ────────────────────────────────────────────────────────

try:
    import z3 as _z3_direct  # noqa: F401
    HAS_Z3 = True
except ImportError:  # pragma: no cover
    HAS_Z3 = False

try:
    from ortools.sat.python import cp_model as _cpm  # noqa: F401
    HAS_ORTOOLS = True
except ImportError:  # pragma: no cover
    HAS_ORTOOLS = False

needs_z3 = pytest.mark.skipif(not HAS_Z3, reason="z3-solver not installed")
needs_ortools = pytest.mark.skipif(not HAS_ORTOOLS, reason="ortools not installed")

PY = sys.executable


def _run_sub(code: str, timeout: float = 6.0):
    """Run *code* in a subprocess (guards against hangs). Returns CompletedProcess
    or None on timeout."""
    try:
        return subprocess.run(
            [PY, "-c", code], capture_output=True, text=True, timeout=timeout,
            env={"PYTHONPATH": "/workspace/clausal-bug-fix"},
        )
    except subprocess.TimeoutExpired:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# CLP(Q) — clausal/logic/clpq.py
# ══════════════════════════════════════════════════════════════════════════════

from clausal.logic.clpq import (  # noqa: E402
    in_q, q_eq, q_ne, q_le, q_lt, q_ge, q_gt,
    maximize, minimize, sup, inf, entailed, bb_inf, dump_q,
    clpq_constraint_block, Q_KEY, _tableaux,
)
from clausal.terms import Add, Sub, Mult, Mod  # noqa: E402


class TestClpqSoundness:
    """Confirmed soundness bugs: unsatisfiable stores accepted."""

    def test_qle_bound_then_unify_outside_fails(self):
        t = Trail()
        x = Var()
        assert in_q(x, 0, 100, t)
        assert q_le(x, 5, t)          # X <= 5 (tableau-only bound)
        assert not unify(x, 50, t)    # 50 > 5 must fail — currently succeeds

    @pytest.mark.xfail(strict=False,
                       reason="A08-F002: Gaussian pivot bounds never re-checked; "
                              "X,Y in [0,10] with X+Y=100 accepted")
    def test_parametric_bounds_infeasible_eq_fails(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q(x, 0, 10, t)
        assert in_q(y, 0, 10, t)
        assert not q_eq(Add(left=x, right=y), 100, t)

    def test_in_q_empty_interval_fails(self):
        t = Trail()
        x = Var()
        assert not in_q(x, 10, 0, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F004: strict < is <= + passive diseq; "
                              "cycle X<Y, Y<X accepted")
    def test_strict_cycle_fails(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q(x, None, None, t)
        assert in_q(y, None, None, t)
        r1 = q_lt(x, y, t)
        r2 = q_lt(y, x, t)
        assert not (r1 and r2)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F004: {X<Y}, X is Y accepted (aliased diseq "
                              "invisible to _check_diseqs)")
    def test_strict_then_alias_unify_fails(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q(x, None, None, t)
        assert in_q(y, None, None, t)
        assert q_lt(x, y, t)
        assert not unify(x, y, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F004: {X!=Y}, X is Y accepted")
    def test_ne_then_alias_unify_fails(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q(x, None, None, t)
        assert in_q(y, None, None, t)
        assert q_ne(x, y, t)
        assert not unify(x, y, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F006: bb_inf branches on a Gaussian-eliminated "
                              "(parametric) int var — set_bound is a no-op, "
                              "B&B exhausts depth and fails")
    def test_bb_inf_parametric_int_var(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q(x, 0, None, t)
        assert in_q(y, 0, None, t)
        # Y + X == 3/2 makes Y the elimination pivot (parametric)
        assert q_eq(Add(left=y, right=x), F(3, 2), t)
        rv = Var()
        assert bb_inf([y], x, rv, t)          # min X with Y integer: Y=1, X=1/2
        assert deref(rv) == F(1, 2)

    def test_no_stale_tableau_on_recycled_trail_id(self):
        gc.collect()
        t = Trail()
        x = Var()
        in_q(x, 0, 5, t)
        tid = id(t)
        assert tid in _tableaux
        del t, x
        gc.collect()
        # Deterministic leak evidence: the entry is removed only by a
        # trail-undo callback that never fires when the trail is dropped,
        # so it survives GC of the Trail. A future Trail() allocated at the
        # same address (observed in probing: 200 queries piled 200 vars into
        # one recycled tableau) then inherits these stale constraints.
        assert tid not in _tableaux, (
            "tableau entry survives Trail GC — recycled trail ids inherit "
            "stale constraint stores"
        )


class TestClpqSemanticsVsReference:
    """Divergences from SICStus/Holzbaur semantics and from docs/clpq.md."""

    @pytest.mark.xfail(strict=False,
                       reason="A08-F008: entailed ignores stored disequalities "
                              "(SICStus: entailed(A=\\=5) after {A=\\=5} is true)")
    def test_entailed_diseq_after_ne(self):
        t = Trail()
        a = Var()
        assert in_q(a, 0, 10, t)
        assert q_ne(a, 5, t)
        assert entailed('\\=', a, 5, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F004/F008: entailed('<') false after q_lt "
                              "store (strict stored as non-strict)")
    def test_entailed_strict_after_strict(self):
        t = Trail()
        x = Var()
        assert in_q(x, None, None, t)
        assert q_lt(x, 5, t)
        assert entailed('<', x, 5, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F007: docs promise TypeError on Q/float mixing; "
                              "q_eq silently converts float to binary Fraction")
    def test_q_eq_float_raises_typeerror(self):
        t = Trail()
        x = Var()
        assert in_q(x, None, None, t)
        with pytest.raises(TypeError):
            q_eq(x, 0.1, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F007: docs table says in_q on an in_real var "
                              "raises TypeError; it silently succeeds")
    def test_in_q_after_in_real_raises(self):
        from clausal.logic.clpr import in_real
        t = Trail()
        x = Var()
        assert in_real(x, 0.0, 10.0, t)
        with pytest.raises(TypeError):
            in_q(x, 0, 10, t)


class TestClpqRegressionGuards:
    """Behaviour confirmed correct during the audit."""

    def test_gaussian_three_var_exactness(self):
        # docs/clpq.md worked example: X+Y+Z=6, X-Y=2, Y-Z=1
        t = Trail()
        x, y, z = Var(), Var(), Var()
        assert in_q([x, y, z], None, None, t)
        assert q_eq(Add(left=Add(left=x, right=y), right=z), 6, t)
        assert q_eq(Sub(left=x, right=y), 2, t)
        assert q_eq(Sub(left=y, right=z), 1, t)
        assert deref(x) == F(11, 3)
        assert deref(y) == F(5, 3)
        assert deref(z) == F(2, 3)

    def test_classic_lp_maximize_310(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q([x, y], 0, 1000, t)
        assert q_le(Add(left=Mult(left=2, right=x), right=y), 16, t)
        assert q_le(Add(left=x, right=Mult(left=2, right=y)), 11, t)
        assert q_le(Add(left=x, right=Mult(left=3, right=y)), 15, t)
        rv = Var()
        assert maximize(Add(left=Mult(left=30, right=x),
                            right=Mult(left=50, right=y)), rv, t)
        assert deref(rv) == 310
        assert deref(x) == 7 and deref(y) == 2

    def test_sup_inf_do_not_bind(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_q([x, y], 0, 10, t)
        assert q_le(Add(left=x, right=y), 8, t)
        s, i = Var(), Var()
        assert sup(Add(left=x, right=y), s, t)
        assert inf(Add(left=x, right=y), i, t)
        assert deref(s) == 8 and deref(i) == 0
        assert is_var(deref(x)) and is_var(deref(y))

    def test_entailed_basics(self):
        t = Trail()
        x = Var()
        assert in_q(x, 0, 10, t)
        assert entailed('=<', x, 10, t)
        assert not entailed('=<', x, 7, t)

    def test_backtracking_restores_tableau_bound(self):
        t = Trail()
        w = Var()
        assert in_q(w, 0, 100, t)
        st = get_attr(w, Q_KEY)
        mark = t.mark()
        assert q_le(w, 5, t)
        assert _tableaux[id(t)].hi[st.tab_id] == 5
        t.undo(mark)
        assert _tableaux[id(t)].hi[st.tab_id] == 100

    def test_q_ne_fires_on_grounding(self):
        t = Trail()
        x = Var()
        assert in_q(x, 0, 10, t)
        assert q_ne(x, 5, t)
        assert not unify(x, 5, t)

    def test_maximize_fails_on_strict_supremum(self):
        # SICStus maximize also fails when the supremum is not attained.
        t = Trail()
        x = Var()
        assert in_q(x, 0, None, t)
        assert q_lt(x, 5, t)
        rv = Var()
        assert not maximize(x, rv, t)

    def test_constraint_block_and_maximize(self):
        from clausal.pythonic_ast.nodes import LtE, ArithEq, CompareChain
        from clausal.pythonic_ast.nodes import Add as NAdd
        t = Trail()
        x, y = Var(), Var()
        assert clpq_constraint_block((
            CompareChain(comparisons=[LtE(left=0, right=x), LtE(left=x, right=1)]),
            CompareChain(comparisons=[LtE(left=0, right=y), LtE(left=y, right=1)]),
            ArithEq(left=NAdd(left=x, right=y), right=F(3, 4)),
        ), t)
        v = Var()
        assert maximize(x, v, t)
        assert deref(v) == F(3, 4)

    def test_dump_q_no_slack_leakage(self):
        t = Trail()
        p, q = Var(), Var()
        assert in_q([p, q], 0, None, t)
        assert q_le(Add(left=Mult(left=2, right=p), right=q), 16, t)
        out = dump_q([p, q], t)
        names = {str(deref(p)), str(deref(q))}
        for line in out:
            body = line.strip('{}')
            # every symbol in the projection must be a target variable
            for tok in body.replace('*', ' ').replace('+', ' ').replace(
                    '-', ' ').replace('=<', ' ').replace('=', ' ').split():
                if tok.startswith('_'):
                    assert tok in names, f"internal var {tok} leaked into {line}"


# ══════════════════════════════════════════════════════════════════════════════
# CLP(R) — clausal/logic/clpr.py + _clpr_core.c
# ══════════════════════════════════════════════════════════════════════════════

from clausal.logic.clpr import (  # noqa: E402
    in_real, real_eq, real_ne, real_lt, real_le, label_real,
    REAL_KEY, _imod, _imod_py, _imul, _imul_py, _iadd,
)


class TestClprModInterval:
    def test_imod_contains_true_value_real_numerator(self):
        lo, hi = _imod(1.5, 1.5, 2.0, 2.0)
        assert lo <= 1.5 <= hi, f"true value 1.5 outside [{lo}, {hi}]"

    def test_imod_fractional_divisor_nonempty(self):
        lo, hi = _imod(0.0, 10.0, 0.5, 0.5)
        assert lo <= hi, f"empty interval [{lo}, {hi}] for satisfiable X % 0.5"

    def test_mod_constraint_true_value_accepted(self):
        t = Trail()
        y = Var()
        assert in_real(y, -100.0, 100.0, t)
        assert real_eq(Mod(left=1.5, right=2.0), y, t)
        assert unify(y, 1.5, t)   # 1.5 % 2.0 == 1.5

    def test_mod_constraint_fractional_divisor_posts(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_real(x, 0.0, 10.0, t)
        assert in_real(y, -100.0, 100.0, t)
        assert real_eq(Mod(left=x, right=0.5), y, t)


class TestClprAliasing:
    def test_real_ne_alias_fails(self):
        t = Trail()
        x, y = Var(), Var()
        assert in_real(x, 0.0, 10.0, t)
        assert in_real(y, 0.0, 10.0, t)
        assert real_ne(x, y, t)
        assert not unify(x, y, t)

    def test_real_lt_alias_unify_fails_promptly(self):
        code = (
            "from clausal.logic.variables import Var, Trail, unify\n"
            "from clausal.logic.clpr import in_real, real_lt\n"
            "t = Trail(); x = Var(); y = Var()\n"
            "in_real(x, 0.0, 10.0, t); in_real(y, 0.0, 10.0, t)\n"
            "real_lt(x, y, t)\n"
            "print('RESULT', unify(x, y, t))\n"
        )
        cp = _run_sub(code, timeout=6.0)
        assert cp is not None, "non-termination: unify after X<Y hung >6s"
        assert "RESULT False" in cp.stdout

    def test_real_strict_cycle_fails_promptly(self):
        code = (
            "from clausal.logic.variables import Var, Trail\n"
            "from clausal.logic.clpr import in_real, real_lt\n"
            "t = Trail(); x = Var(); y = Var()\n"
            "in_real(x, 0.0, 10.0, t); in_real(y, 0.0, 10.0, t)\n"
            "r1 = real_lt(x, y, t)\n"
            "r2 = real_lt(y, x, t)\n"
            "print('RESULT', r1 and r2)\n"
        )
        cp = _run_sub(code, timeout=6.0)
        assert cp is not None, "non-termination: X<Y, Y<X hung >6s"
        assert "RESULT False" in cp.stdout


class TestClprPythonCParity:
    def test_imul_py_nan_corner_matches_c(self):
        py_lo, py_hi = _imul_py(0.0, 1.0, -math.inf, 2.0)
        assert not math.isnan(py_lo) and not math.isnan(py_hi)
        c_lo, c_hi = _imul(0.0, 1.0, -math.inf, 2.0)
        assert (py_lo, py_hi) == (c_lo, c_hi)


class TestClprRegressionGuards:
    def test_outward_rounding_addition_contains_true_value(self):
        lo, hi = _iadd(0.1, 0.1, 0.2, 0.2)
        assert lo <= 0.3 <= hi

    def test_sqrt2_labeling(self):
        t = Trail()
        x = Var()
        assert in_real(x, 0.0, 2.0, t)
        assert real_eq(Mult(left=x, right=x), 2.0, t)
        found = False
        for _ in label_real([x], t, eps=1e-9):
            s = get_attr(deref(x), REAL_KEY)
            mid = (s.lo + s.hi) / 2.0
            assert abs(mid - math.sqrt(2)) < 1e-8
            found = True
            break
        assert found

    def test_in_real_intersection_failure(self):
        t = Trail()
        x = Var()
        assert in_real(x, 0.0, 5.0, t)
        assert not in_real(x, 6.0, 10.0, t)

    def test_backtracking_restores_interval(self):
        t = Trail()
        x = Var()
        assert in_real(x, 0.0, 10.0, t)
        mark = t.mark()
        assert real_le(x, 5.0, t)
        assert get_attr(x, REAL_KEY).hi == 5.0
        t.undo(mark)
        assert get_attr(x, REAL_KEY).hi == 10.0

    def test_unify_out_of_interval_fails(self):
        t = Trail()
        x = Var()
        assert in_real(x, 0.0, 5.0, t)
        assert not unify(x, 7.0, t)


# ══════════════════════════════════════════════════════════════════════════════
# CLP(Z3) — clausal/logic/clpz3.py
# ══════════════════════════════════════════════════════════════════════════════


@needs_z3
class TestZ3StoreSync:
    @pytest.mark.xfail(strict=False,
                       reason="A08-F013: no attr hook for Z3_KEY — binding a "
                              "Z3-registered var outside its domain succeeds")
    def test_binding_out_of_domain_fails(self):
        from clausal.logic.clpz3 import in_z3
        t = Trail()
        x = Var()
        assert in_z3(x, 1, 10, t)
        assert not unify(x, 99, t)

    @pytest.mark.xfail(strict=False,
                       reason="A08-F013: label_z3 ignores Clausal-side bindings "
                              "— B enumerates 1..10 after A==B, A=3")
    def test_label_respects_bindings(self):
        from clausal.logic.clpz3 import in_z3, z3_eq, label_z3
        t = Trail()
        a, b = Var(), Var()
        assert in_z3(a, 1, 10, t)
        assert in_z3(b, 1, 10, t)
        assert z3_eq(a, b, t)
        assert unify(a, 3, t)
        sols = sorted({deref(b) for _ in label_z3([b], t)})
        assert sols == [3], f"solutions inconsistent with A=3: {sols}"


@needs_z3
class TestZ3TranslationFidelity:
    @pytest.mark.xfail(strict=False,
                       reason="A08-F014: Int FloorDiv → SMT Euclidean div "
                              "(7 // -2 gives -3, Python gives -4)")
    def test_floordiv_negative_divisor(self):
        from clausal.logic.clpz3 import in_z3, z3_eq, label_z3
        from clausal.pythonic_ast.nodes import FloorDiv
        t = Trail()
        x = Var()
        assert in_z3(x, -100, 100, t)
        assert z3_eq(FloorDiv(left=7, right=-2), x, t)
        sols = [deref(x) for _ in label_z3([x], t)]
        assert sols == [7 // -2]  # -4

    @pytest.mark.xfail(strict=False,
                       reason="A08-F014: Int Mod → SMT mod (7 % -2 gives 1, "
                              "Python gives -1)")
    def test_mod_negative_divisor(self):
        from clausal.logic.clpz3 import in_z3, z3_eq, label_z3
        from clausal.pythonic_ast.nodes import Mod as NMod
        t = Trail()
        x = Var()
        assert in_z3(x, -100, 100, t)
        assert z3_eq(NMod(left=7, right=-2), x, t)
        sols = [deref(x) for _ in label_z3([x], t)]
        assert sols == [7 % -2]  # -1

    @pytest.mark.xfail(strict=False,
                       reason="A08-F014: FloorDiv under RealSort becomes true "
                              "division (7 // 2 gives 7/2)")
    def test_floordiv_real_sort(self):
        from clausal.logic.clpz3 import in_z3_real, z3_real_eq, label_z3_real
        from clausal.pythonic_ast.nodes import FloorDiv
        t = Trail()
        x = Var()
        assert in_z3_real(x, None, None, t)
        assert z3_real_eq(FloorDiv(left=7, right=2), x, t)
        for _ in label_z3_real([x], t):
            assert deref(x) == 3  # Python 7 // 2
            return
        pytest.fail("no solution")


@needs_z3
class TestZ3RegressionGuards:
    def test_linear_system(self):
        from clausal.logic.clpz3 import in_z3, z3_eq, label_z3
        from clausal.pythonic_ast.nodes import Add as NAdd, Sub as NSub
        t = Trail()
        x, y = Var(), Var()
        assert in_z3([x, y], 0, 100, t)
        assert z3_eq(NAdd(left=x, right=y), 10, t)
        assert z3_eq(NSub(left=x, right=y), 2, t)
        sols = {(deref(x), deref(y)) for _ in label_z3([x, y], t)}
        assert sols == {(6, 4)}

    def test_rational_model_extraction_is_exact_fraction(self):
        from clausal.logic.clpz3 import in_z3_real, z3_real_eq, label_z3_real
        from clausal.pythonic_ast.nodes import Mult as NMult
        t = Trail()
        r = Var()
        assert in_z3_real(r, None, None, t)
        assert z3_real_eq(NMult(left=3, right=r), 1, t)
        got = [deref(r) for _ in label_z3_real([r], t)]
        assert got == [F(1, 3)]
        assert isinstance(got[0], F)

    def test_backtracking_pops_solver_scope(self):
        from clausal.logic.clpz3 import in_z3, z3_eq, z3_ne, z3_check
        t = Trail()
        x = Var()
        assert in_z3(x, 1, 5, t)
        mark = t.mark()
        assert z3_eq(x, 3, t)
        assert z3_check(t)
        assert z3_ne(x, 3, t)
        assert not z3_check(t)
        t.undo(mark)
        assert z3_check(t)

    def test_taut_and_sat_count(self):
        from clausal.logic.clpz3 import taut_z3, sat_count_z3
        from clausal.pythonic_ast.nodes import BitOr, Invert
        t = Trail()
        a, b = Var(), Var()
        tv = Var()
        assert taut_z3(BitOr(left=a, right=Invert(operand=a)), tv, t)
        assert deref(tv) == 1
        cv = Var()
        assert sat_count_z3(BitOr(left=a, right=b), cv, t)
        assert deref(cv) == 3

    def test_label_enumerates_full_domain(self):
        from clausal.logic.clpz3 import in_z3, label_z3
        t = Trail()
        x = Var()
        assert in_z3(x, 1, 4, t)
        sols = sorted(deref(x) for _ in label_z3([x], t))
        assert sols == [1, 2, 3, 4]


# ══════════════════════════════════════════════════════════════════════════════
# ortools — clportools*.py
# ══════════════════════════════════════════════════════════════════════════════


@needs_ortools
class TestCpsatTranslationFidelity:
    @pytest.mark.xfail(strict=False,
                       reason="A08-F015: CP-SAT division truncates toward zero "
                              "(-7 // 2 gives -3, Python gives -4)")
    def test_floordiv_negative_numerator(self):
        from clausal.logic import clportools as O
        from clausal.pythonic_ast.nodes import ArithEq, FloorDiv
        t = Trail()
        x = Var()
        O.or_in(x, -100, 100, trail=t)
        ct = O.clausal_to_cpsat_constraint(
            ArithEq(left=FloorDiv(left=-7, right=2), right=x), t)
        O.or_add_constraint(ct, t)
        sols = [deref(x) for _ in O.label_or([x], t)]
        assert sols == [-7 // 2]  # -4

    @pytest.mark.xfail(strict=False,
                       reason="A08-F015: Mod result var domain [0,1e9] + CP-SAT "
                              "sign semantics make -7 % 3 infeasible "
                              "(Python: 2)")
    def test_mod_negative_numerator(self):
        from clausal.logic import clportools as O
        from clausal.pythonic_ast.nodes import ArithEq, Mod as NMod
        t = Trail()
        x = Var()
        O.or_in(x, -100, 100, trail=t)
        ct = O.clausal_to_cpsat_constraint(
            ArithEq(left=NMod(left=-7, right=3), right=x), t)
        O.or_add_constraint(ct, t)
        sols = [deref(x) for _ in O.label_or([x], t)]
        assert sols == [-7 % 3]  # 2

    def test_or_minimize_unify_failure_not_ignored(self):
        from clausal.logic import clportools as O
        t = Trail()
        x, y = Var(), Var()
        O.or_in(x, 1, 3, trail=t)
        O.or_in(y, 1, 3, trail=t)
        unify(y, 99, t)   # (F013-class desync: succeeds — no OR hook)
        v = Var()
        n = sum(1 for _ in O.or_minimize(x, v, t))
        assert n == 0, "yielded an optimum despite Y=99 contradicting the model"


@needs_ortools
class TestOrtoolsRegressionGuards:
    def test_cpsat_linear_system(self):
        from clausal.logic import clportools as O
        from clausal.pythonic_ast.nodes import ArithEq, Add as NAdd, Sub as NSub
        t = Trail()
        x, y = Var(), Var()
        O.or_in(x, 0, 100, trail=t)
        O.or_in(y, 0, 100, trail=t)
        O.or_add_constraint(O.clausal_to_cpsat_constraint(
            ArithEq(left=NAdd(left=x, right=y), right=10), t), t)
        O.or_add_constraint(O.clausal_to_cpsat_constraint(
            ArithEq(left=NSub(left=x, right=y), right=2), t), t)
        sols = {(deref(x), deref(y)) for _ in O.label_or([x, y], t)}
        assert sols == {(6, 4)}

    def test_or_count_respects_scoped_constraints(self):
        from clausal.logic import clportools as O
        from clausal.pythonic_ast.nodes import ArithEq
        t = Trail()
        x = Var()
        O.or_in(x, 1, 3, trail=t)
        assert O.or_count([x], t) == 3
        O.or_push(t)
        O.or_add_constraint(O.clausal_to_cpsat_constraint(
            ArithEq(left=x, right=2), t), t)
        assert O.or_count([x], t) == 1

    def test_or_count_stable_after_labeling(self):
        from clausal.logic import clportools as O
        t = Trail()
        x = Var()
        O.or_in(x, 1, 3, trail=t)
        assert sum(1 for _ in O.label_or([x], t)) == 3
        # blocking clauses must be retracted when labeling completes
        assert O.or_count([x], t) == 3

    def test_lp_maximize_classic(self):
        from clausal.logic import clportools_lp as L
        from clausal.pythonic_ast.nodes import LtE, Add as NAdd, Mult as NMult
        t = Trail()
        x, y = Var(), Var()
        L.lp_var(x, 0.0, 1000.0, t, 'glop')
        L.lp_var(y, 0.0, 1000.0, t, 'glop')
        assert L.lp_constraint_block((
            LtE(left=NAdd(left=NMult(left=2, right=x), right=y), right=16),
            LtE(left=NAdd(left=x, right=NMult(left=2, right=y)), right=11),
            LtE(left=NAdd(left=x, right=NMult(left=3, right=y)), right=15),
        ), 'glop', t)
        v = Var()
        seen = False
        for _ in L.lp_maximize(NAdd(left=NMult(left=30, right=x),
                                    right=NMult(left=50, right=y)), v, t):
            assert abs(deref(v) - 310.0) < 1e-6
            seen = True
        assert seen

    def test_graph_max_flow_and_knapsack(self):
        from clausal.logic import clportools_graph as G
        t = Trail()
        flow, _ = G.or_max_flow([[0, 1, 3], [0, 2, 2], [1, 3, 2], [2, 3, 3]],
                                0, 3, t)
        assert flow == 4
        total, sel = G.or_knapsack([60, 100, 120], [[10, 20, 30]], [50], t)
        assert total == 220 and sel == [0, 1, 1]

    def test_routing_tsp_small(self):
        from clausal.logic import clportools_routing as R
        t = Trail()
        d = [[0, 10, 15, 20], [10, 0, 35, 25], [15, 35, 0, 30], [20, 25, 30, 0]]
        res = R.or_tsp(d, 0, t)
        assert res is not None
        tour, dist = res
        assert tour[0] == 0 and tour[-1] == 0 and dist == 80


# ══════════════════════════════════════════════════════════════════════════════
# C toolkit — _clpr_core leak checks
# ══════════════════════════════════════════════════════════════════════════════


class TestClprCoreMemory:
    def test_interval_ops_no_leak(self, refcount_stable):
        def thunk():
            _imul(0.5, 1.5, -2.0, 2.0)
            _iadd(0.1, 0.1, 0.2, 0.2)
            _imod(1.0, 6.0, 2.0, 2.0)
        refcount_stable(thunk, iterations=3000)

    def test_clpq_post_solve_loop_no_leak(self, refcount_stable):
        def thunk():
            t = Trail()
            x = Var()
            in_q(x, 0, 10, t)
            q_le(x, 5, t)
            unify(x, 3, t)
        refcount_stable(thunk, iterations=300, tol=256, alloc_tol=1 << 18)
