"""A07 CLP(B) & SAT — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/07-clpb-sat/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_07_clpb_sat.py -v
"""
from __future__ import annotations

import itertools
import os
import random
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from clausal.logic.variables import Var, Trail, deref, is_var, unify
from clausal.logic import clpb
from clausal.logic.clpb import (
    BDD_TRUE, BDD_FALSE, BDDNode,
    BoolEq, BoolImpl,
    enumerate_var, make_node, apply, negate, restrict,
    sat, taut, sat_count, bool_labeling,
    _expr_to_bdd, _collect_bdd_var_ids, _count_paths,
)
from clausal.pythonic_ast.nodes import BitAnd, BitOr, BitXor, Invert

try:
    from clausal.logic.clpsat import _HAS_PYSAT
except ImportError:  # pragma: no cover
    _HAS_PYSAT = False

needs_pysat = pytest.mark.skipif(not _HAS_PYSAT, reason="python-sat not installed")

REPO_ROOT = str(Path(__file__).resolve().parents[2])


# ── Brute-force truth-table oracle ───────────────────────────────────────────

def _eval_expr(e, env):
    """Independent Boolean evaluator (does not use clpb code paths)."""
    if isinstance(e, Var):
        return env[id(e)]
    if isinstance(e, (int, bool)):
        return int(e)
    n = type(e).__name__
    if n == "BitAnd":
        return _eval_expr(e.left, env) & _eval_expr(e.right, env)
    if n == "BitOr":
        return _eval_expr(e.left, env) | _eval_expr(e.right, env)
    if n == "BitXor":
        return _eval_expr(e.left, env) ^ _eval_expr(e.right, env)
    if n == "Invert":
        return 1 - _eval_expr(e.operand, env)
    if n == "BoolEq":
        return int(_eval_expr(e.left, env) == _eval_expr(e.right, env))
    if n == "BoolImpl":
        return int((not _eval_expr(e.left, env)) or _eval_expr(e.right, env))
    raise TypeError(n)


def _used_vars(e, acc):
    if isinstance(e, Var):
        acc.add(e)
        return acc
    if isinstance(e, (int, bool)):
        return acc
    if type(e).__name__ == "Invert":
        return _used_vars(e.operand, acc)
    _used_vars(e.left, acc)
    _used_vars(e.right, acc)
    return acc


def _rand_expr(rng, vars_, depth):
    if depth == 0 or rng.random() < 0.25:
        if rng.random() < 0.8:
            return rng.choice(vars_)
        return rng.choice([0, 1])
    op = rng.choice(["and", "or", "xor", "not", "eq", "impl"])
    if op == "not":
        return Invert(operand=_rand_expr(rng, vars_, depth - 1))
    l = _rand_expr(rng, vars_, depth - 1)
    r = _rand_expr(rng, vars_, depth - 1)
    if op == "and":
        return BitAnd(left=l, right=r)
    if op == "or":
        return BitOr(left=l, right=r)
    if op == "xor":
        return BitXor(left=l, right=r)
    if op == "eq":
        return BoolEq(l, r)
    return BoolImpl(l, r)


def _brute_models(e, uv):
    models = set()
    for bits in itertools.product((0, 1), repeat=len(uv)):
        env = {id(v): b for v, b in zip(uv, bits)}
        if _eval_expr(e, env):
            models.add(bits)
    return models


# ══════════════════════════════════════════════════════════════════════════════
# Regression guards — standalone-formula semantics diffed against brute force
# ══════════════════════════════════════════════════════════════════════════════


class TestTruthTableOracle:
    """sat / taut / sat_count / bool_labeling vs brute-force enumeration."""

    def test_random_formula_oracle(self):
        rng = random.Random(1234)
        for _trial in range(120):
            nv = rng.randint(1, 5)
            vs = [Var() for _ in range(nv)]
            e = _rand_expr(rng, vs, rng.randint(1, 4))
            uv = sorted(_used_vars(e, set()), key=id)
            models = _brute_models(e, uv)
            n_models = len(models)
            is_taut = n_models == 2 ** len(uv)
            is_contra = n_models == 0

            # sat_count
            tr = Trail()
            n_var = Var()
            ok = sat_count(e, n_var, tr)
            assert ok and deref(n_var) == n_models, (
                f"sat_count diverges from truth table: {deref(n_var)} != {n_models}"
            )

            # taut
            tr2 = Trail()
            t_var = Var()
            tok = taut(e, t_var, tr2)
            if is_taut:
                assert tok and deref(t_var) == 1
            elif is_contra:
                assert tok and deref(t_var) == 0
            else:
                assert not tok, "taut must fail on indeterminate formulas"

            # sat + labeling enumeration
            tr3 = Trail()
            sols = set()
            if sat(e, tr3):
                for _ in bool_labeling(list(uv), tr3):
                    sols.add(tuple(deref(v) for v in uv))
            assert sols == models, "labeling enumeration diverges from truth table"

    def test_multi_post_network_oracle(self):
        """Sequential sat() posts over shared vars = conjunction (component merge)."""
        rng = random.Random(7)
        for _trial in range(60):
            nv = rng.randint(2, 5)
            vs = [Var() for _ in range(nv)]
            exprs = [_rand_expr(rng, vs, rng.randint(1, 3))
                     for _ in range(rng.randint(1, 4))]
            expected = set()
            for bits in itertools.product((0, 1), repeat=nv):
                env = {id(v): b for v, b in zip(vs, bits)}
                if all(_eval_expr(e, env) for e in exprs):
                    expected.add(bits)
            tr = Trail()
            posted_ok = all(sat(e, tr) for e in exprs)
            got = set()
            if posted_ok:
                for _ in bool_labeling(vs, tr):
                    got.add(tuple(deref(v) for v in vs))
            assert got == expected


class TestSatCount:
    def test_docs_examples(self):
        cases = [
            (lambda x, y: BitXor(left=x, right=y), 2),
            (lambda x, y: BitAnd(left=x, right=y), 1),
            (lambda x, y: BitOr(left=x, right=y), 3),
        ]
        for build, expected in cases:
            tr = Trail()
            n = Var()
            assert sat_count(build(Var(), Var()), n, tr)
            assert deref(n) == expected

    def test_reduced_away_var_still_counted(self):
        # (X & 0) | Y reduces to a BDD over Y only, but X still contributes 2x.
        tr = Trail()
        x, y, n = Var(), Var(), Var()
        e = BitOr(left=BitAnd(left=x, right=0), right=y)
        assert sat_count(e, n, tr)
        assert deref(n) == 2

    def test_constant_formulas(self):
        tr = Trail()
        n = Var()
        assert sat_count(1, n, tr) and deref(n) == 1
        n2 = Var()
        assert sat_count(0, n2, tr) and deref(n2) == 0

    def test_test_mode_count_bound(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat_count(BitXor(left=x, right=y), 2, tr)
        tr2 = Trail()
        assert not sat_count(BitXor(left=Var(), right=Var()), 3, tr2)

    def test_big_path_or_chains_exact(self):
        """n_vars >= 63 takes the C big-int path; counts must stay exact."""
        for n in (62, 63, 70):
            tr = Trail()
            vs = [Var() for _ in range(n)]
            e = vs[0]
            for v in vs[1:]:
                e = BitOr(left=e, right=v)
            cnt = Var()
            assert sat_count(e, cnt, tr)
            assert deref(cnt) == 2 ** n - 1, f"OR-{n} count wrong"

    def test_c_count_paths_vs_local_reference(self):
        """C _count_paths on a BDD with a skipped level vs a self-contained oracle."""
        def local_count(bdd, level_map, n_vars, level=0, memo=None):
            if memo is None:
                memo = {}
            if bdd is BDD_TRUE:
                r = n_vars - level
                return 2 ** r if r > 0 else 1
            if bdd is BDD_FALSE:
                return 0
            key = (id(bdd), level)
            if key in memo:
                return memo[key]
            nl = level_map[bdd.var_id]
            mult = 2 ** max(0, nl - level)
            res = mult * (local_count(bdd.high, level_map, n_vars, nl + 1, memo)
                          + local_count(bdd.low, level_map, n_vars, nl + 1, memo))
            memo[key] = res
            return res

        vs = [Var() for _ in range(4)]
        ids = [enumerate_var(v) for v in vs]
        # BDD over vars 0 and 3 only; vars 1, 2 are skipped levels.
        inner = make_node(ids[3], BDD_TRUE, BDD_FALSE, vs[3])
        bdd = make_node(ids[0], inner, BDD_FALSE, vs[0])
        lm = {vid: i for i, vid in enumerate(sorted(ids))}
        assert _count_paths(bdd, lm, 4, {}) == local_count(bdd, lm, 4) == 4


class TestTaut:
    def test_demorgan_tautology(self):
        tr = Trail()
        x, y, t = Var(), Var(), Var()
        e = BoolEq(Invert(operand=BitAnd(left=x, right=y)),
                   BitOr(left=Invert(operand=x), right=Invert(operand=y)))
        assert taut(e, t, tr) and deref(t) == 1

    def test_contradiction(self):
        tr = Trail()
        x, t = Var(), Var()
        assert taut(BitAnd(left=x, right=Invert(operand=x)), t, tr)
        assert deref(t) == 0

    def test_indeterminate_fails(self):
        tr = Trail()
        assert not taut(BitOr(left=Var(), right=Var()), Var(), tr)

    def test_test_mode(self):
        tr = Trail()
        x = Var()
        assert taut(BitOr(left=x, right=Invert(operand=x)), 1, tr)
        tr2 = Trail()
        y = Var()
        assert not taut(BitOr(left=y, right=Invert(operand=y)), 0, tr2)


class TestPropagationAndTrail:
    def test_forcing(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat(BitAnd(left=x, right=y), tr)
        assert deref(x) == 1 and deref(y) == 1

        tr2 = Trail()
        z = Var()
        assert sat(Invert(operand=z), tr2)
        assert deref(z) == 0

    def test_contradictory_posts_fail(self):
        tr = Trail()
        x = Var()
        assert sat(x, tr)
        assert not sat(Invert(operand=x), tr)

    def test_trail_restores_constraint_store(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat(BitOr(left=x, right=y), tr)
        mark = tr.mark()
        assert sat(Invert(operand=x), tr)
        assert deref(x) == 0 and deref(y) == 1
        tr.undo(mark)
        assert is_var(deref(x)) and is_var(deref(y))
        sols = set()
        for _ in bool_labeling([x, y], tr):
            sols.add((deref(x), deref(y)))
        assert sols == {(0, 1), (1, 0), (1, 1)}

    def test_hook_rejects_out_of_domain(self):
        for bad in (2, -1, "a", 1.0):
            tr = Trail()
            x, y = Var(), Var()
            assert sat(BitOr(left=x, right=y), tr)
            assert not unify(x, bad, tr), f"CLP(B) var must reject {bad!r}"

    def test_alias_transfers_state_through_chain(self):
        # sat(X <-> Y), alias Y=Z, then Z=1 must force X=1.
        tr = Trail()
        x, y, z = Var(), Var(), Var()
        assert sat(BoolEq(x, y), tr)
        assert unify(y, z, tr)
        assert unify(z, 1, tr)
        assert deref(x) == 1

    def test_pigeonhole_unsat(self):
        tr = Trail()
        p = {(i, j): Var() for i in range(3) for j in range(2)}
        for i in range(3):
            assert sat(BitOr(left=p[(i, 0)], right=p[(i, 1)]), tr)
        posted = True
        for j in range(2):
            for a, b in itertools.combinations(range(3), 2):
                posted = posted and sat(
                    Invert(operand=BitAnd(left=p[(a, j)], right=p[(b, j)])), tr)
                if not posted:
                    break
            if not posted:
                break
        sols = 0
        if posted:
            for _ in bool_labeling(list(p.values()), tr):
                sols += 1
        assert sols == 0


class TestBDDInternals:
    def test_negate_involution_hash_consed(self):
        vs = [Var() for _ in range(3)]
        ids = [enumerate_var(v) for v in vs]
        f = make_node(ids[0],
                      make_node(ids[1], BDD_TRUE, BDD_FALSE, vs[1]),
                      make_node(ids[2], BDD_FALSE, BDD_TRUE, vs[2]),
                      vs[0])
        assert negate(negate(f)) is f

    def test_apply_terminal_table(self):
        assert apply("and", BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply("or", BDD_FALSE, BDD_FALSE) is BDD_FALSE
        assert apply("xor", BDD_TRUE, BDD_TRUE) is BDD_FALSE
        assert apply("equiv", BDD_FALSE, BDD_FALSE) is BDD_TRUE
        assert apply("impl", BDD_TRUE, BDD_FALSE) is BDD_FALSE
        assert apply("impl", BDD_FALSE, BDD_FALSE) is BDD_TRUE
        assert apply("nand", BDD_TRUE, BDD_TRUE) is BDD_FALSE

    def test_restrict_both_branches(self):
        v = Var()
        vid = enumerate_var(v)
        f = make_node(vid, BDD_TRUE, BDD_FALSE, v)
        assert restrict(f, vid, 1) is BDD_TRUE
        assert restrict(f, vid, 0) is BDD_FALSE
        # restricting a var above the root is a no-op
        assert restrict(f, vid + 10**6, 0) is f

    def test_c_refcount_stable_over_apply_loop(self, refcount_stable,
                                               getrefcount_stable):
        vs = [Var() for _ in range(3)]
        ids = [enumerate_var(v) for v in vs]
        f = make_node(ids[0], make_node(ids[1], BDD_TRUE, BDD_FALSE, vs[1]),
                      BDD_FALSE, vs[0])
        g = make_node(ids[1], BDD_TRUE,
                      make_node(ids[2], BDD_TRUE, BDD_FALSE, vs[2]), vs[1])

        def exercise():
            for op in ("and", "or", "xor", "equiv", "impl", "nand"):
                apply(op, f, g)
            restrict(f, ids[1], 0)
            negate(f)
            s = set()
            _collect_bdd_var_ids(f, s)

        getrefcount_stable(f, exercise, iterations=2000)
        refcount_stable(exercise, iterations=2000)

    def test_sat_label_undo_loop_no_growth(self, refcount_stable):
        """Re-posting over the SAME vars with backtracking must not leak."""
        tr = Trail()
        x, y = Var(), Var()

        def cycle():
            mark = tr.mark()
            sat(BitOr(left=x, right=y), tr)
            for _ in bool_labeling([x, y], tr):
                pass
            tr.undo(mark)

        refcount_stable(cycle, iterations=1500)


# ══════════════════════════════════════════════════════════════════════════════
# .clausal builtin surface
# ══════════════════════════════════════════════════════════════════════════════

CLAUSAL_FIXTURE = """
-module(a07_clpb, [xor_pair(X, Y), count_or(N), taut_dm(T), adder(X, Y, S, C), psolve(X, Y)])

xor_pair(X, Y) <- (
    sat(X ^ Y),
    bool_labeling([X, Y])
)

count_or(N) <- sat_count(X | Y, N)

taut_dm(T) <- taut(BoolEq(~(X & Y), ~X | ~Y), T)

adder(X, Y, S, C) <- (
    sat(BoolEq(S, X ^ Y)),
    sat(BoolEq(C, X & Y))
)

psolve(X, Y) <- (
    pysat.cadical([X | Y, ~X | Y]),
    pysat.solve([X, Y])
)
"""


@pytest.fixture(scope="module")
def clpb_mod(tmp_path_factory):
    from clausal.import_hook import _load_module
    p = tmp_path_factory.mktemp("a07") / "a07_clpb.clausal"
    p.write_text(CLAUSAL_FIXTURE)
    return _load_module("a07_clpb", str(p))


class TestClausalSurface:
    def test_xor_pair_labeling(self, clpb_mod, clear_query_cache):
        from clausal import solve
        x, y = Var(), Var()
        got = [(int(x), int(y)) for _ in solve(clpb_mod.xor_pair(x, y))]
        assert sorted(got) == [(0, 1), (1, 0)]

    def test_sat_count_builtin(self, clpb_mod, clear_query_cache):
        from clausal import solve
        n = Var()
        got = [int(n) for _ in solve(clpb_mod.count_or(n))]
        assert got == [3]

    def test_taut_builtin(self, clpb_mod, clear_query_cache):
        from clausal import solve
        t = Var()
        got = [int(t) for _ in solve(clpb_mod.taut_dm(t))]
        assert got == [1]

    def test_half_adder_forward(self, clpb_mod, clear_query_cache):
        from clausal import solve
        s, c = Var(), Var()
        got = [(int(s), int(c)) for _ in solve(clpb_mod.adder(1, 1, s, c))]
        assert got == [(0, 1)]

    def test_half_adder_all_rows(self, clpb_mod, clear_query_cache):
        from clausal import solve
        table = {(0, 0): (0, 0), (0, 1): (1, 0), (1, 0): (1, 0), (1, 1): (0, 1)}
        for (x, y), (es, ec) in table.items():
            s, c = Var(), Var()
            got = [(int(s), int(c)) for _ in solve(clpb_mod.adder(x, y, s, c))]
            assert got == [(es, ec)], f"adder({x},{y})"

    @needs_pysat
    def test_pysat_builtin_surface(self, clpb_mod, clear_query_cache):
        from clausal import solve
        x, y = Var(), Var()
        got = sorted((int(x), int(y)) for _ in solve(clpb_mod.psolve(x, y)))
        # (X | Y) & (~X | Y)  ⇒  Y = 1
        assert got == [(0, 1), (1, 1)]


# ══════════════════════════════════════════════════════════════════════════════
# PySAT backend (clpsat)
# ══════════════════════════════════════════════════════════════════════════════


@needs_pysat
class TestClpsat:
    def test_tseitin_oracle(self):
        from clausal.logic.clpsat import sat_constraint_block, label_sat
        tr = Trail()
        a, b, c = Var(), Var(), Var()
        expr = BitXor(left=BitAnd(left=a, right=b),
                      right=BitOr(left=b, right=Invert(operand=c)))
        sat_constraint_block((expr,), "cadical195", tr)
        got = set()
        for _ in label_sat([a, b, c], tr):
            got.add((deref(a), deref(b), deref(c)))
        expected = {bits for bits in itertools.product((0, 1), repeat=3)
                    if (bits[0] & bits[1]) ^ (bits[1] | (1 - bits[2]))}
        assert got == expected

    def test_cardinality_oracle(self):
        from clausal.logic.clpsat import sat_at_most, sat_at_least, label_sat
        tr = Trail()
        vs = [Var() for _ in range(4)]
        assert sat_at_most(vs, 2, tr)
        assert sat_at_least(vs, 1, tr)
        got = set()
        for _ in label_sat(vs, tr):
            got.add(tuple(deref(v) for v in vs))
        expected = {b for b in itertools.product((0, 1), repeat=4)
                    if 1 <= sum(b) <= 2}
        assert got == expected

    def test_exactly_with_ground_mix(self):
        from clausal.logic.clpsat import sat_exactly, label_sat
        tr = Trail()
        a, b = Var(), Var()
        assert sat_exactly([a, 1, b, 0], 2, tr)
        got = set()
        for _ in label_sat([a, b], tr):
            got.add((deref(a), deref(b)))
        assert got == {(0, 1), (1, 0)}

    def test_backtracking_retracts_block(self):
        from clausal.logic.clpsat import sat_constraint_block, sat_check
        tr = Trail()
        x = Var()
        mark = tr.mark()
        sat_constraint_block((x,), "cadical195", tr)
        sat_constraint_block((Invert(operand=x),), "cadical195", tr)
        assert not sat_check(tr)
        tr.undo(mark)
        assert sat_check(tr)

    def test_repeated_labeling_blocking_clauses_cleaned(self):
        from clausal.logic.clpsat import sat_constraint_block, label_sat
        tr = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitOr(left=x, right=y),), "cadical195", tr)
        c1 = sum(1 for _ in label_sat([x, y], tr))
        c2 = sum(1 for _ in label_sat([x, y], tr))
        assert (c1, c2) == (3, 3)

    def test_solver_mismatch_raises(self):
        from clausal.logic.clpsat import sat_constraint_block
        tr = Trail()
        x = Var()
        sat_constraint_block((x,), "cadical195", tr)
        with pytest.raises(ValueError, match="mismatch"):
            sat_constraint_block((x,), "m22", tr)


# ══════════════════════════════════════════════════════════════════════════════
# Suspected-bug tests (xfail, strict=False) — see findings ledger
# ══════════════════════════════════════════════════════════════════════════════


class TestSuspectedBugs:

    @pytest.mark.timeout(30)  # override the suite-wide 10s pytest-timeout
    def test_A07_F001_xor_chain_sat_not_exponential(self):
        # sat over a 30-var XOR chain builds a 59-node BDD; a linear
        # implementation finishes in milliseconds.  Current code needs minutes.
        script = textwrap.dedent("""
            from clausal.logic.variables import Var, Trail
            from clausal.logic.clpb import sat
            from clausal.pythonic_ast.nodes import BitXor
            vs = [Var() for _ in range(30)]
            e = vs[0]
            for v in vs[1:]:
                e = BitXor(left=e, right=v)
            assert sat(e, Trail())
            print("OK")
        """)
        env = dict(os.environ, PYTHONPATH=REPO_ROOT)
        try:
            proc = subprocess.run([sys.executable, "-c", script], env=env,
                                  capture_output=True, text=True, timeout=5)
        except subprocess.TimeoutExpired:
            pytest.fail("sat(xor-30) did not finish within 5s (exponential blowup)")
        assert proc.returncode == 0 and "OK" in proc.stdout

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F002: var-var aliasing conjoins stale per-var BDDs instead of "
        "rebuilding from sat_expr — sat(X^Y), X=Y must fail"))
    def test_A07_F002_alias_after_xor_must_fail(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat(BitXor(left=x, right=y), tr)
        assert not unify(x, y, tr), (
            "store is unsatisfiable after aliasing (labeling finds 0 solutions) "
            "but unify succeeded")

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F002: aliasing does not re-propagate — sat(X|Y), X=Y must force X=1"))
    def test_A07_F002_alias_or_propagates_forced(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat(BitOr(left=x, right=y), tr)
        assert unify(x, y, tr)
        assert deref(x) == 1, "X|X = X must be forced to 1"

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F003: taut/2 ignores posted constraints — entailed formulas fail "
        "instead of T=1 (Triska reference semantics)"))
    def test_A07_F003_taut_entailed_by_store(self):
        tr = Trail()
        x, y, t = Var(), Var(), Var()
        assert sat(BoolImpl(x, y), tr)
        ok = taut(BitOr(left=Invert(operand=x), right=y), t, tr)
        assert ok and deref(t) == 1, "~X|Y is entailed by posted X->Y"

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F004: sat_count/2 ignores posted constraints — counts the "
        "standalone formula (Triska: count admissible assignments)"))
    def test_A07_F004_sat_count_respects_store(self):
        tr = Trail()
        x, y, n = Var(), Var(), Var()
        assert sat(BoolEq(x, y), tr)
        assert sat_count(BitOr(left=x, right=y), n, tr)
        # (X|Y) ∧ (X<->Y) admits only (1,1) — Triska counts 1; Clausal says 3.
        assert deref(n) == 1

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F005: no attr hook for SAT_KEY — Clausal bindings invisible to the "
        "PySAT solver; label_sat enumerates models violating the bindings"))
    @needs_pysat
    def test_A07_F005_label_sat_respects_clausal_bindings(self):
        from clausal.logic.clpsat import sat_constraint_block, label_sat
        tr = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitOr(left=x, right=y),), "cadical195", tr)
        assert unify(x, 0, tr)
        got = set()
        for _ in label_sat([x, y], tr):
            got.add((deref(x), deref(y)))
        assert got == {(0, 1)}, f"unsound models: {got - {(0, 1)}}"

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F005: sat_check ignores Clausal bindings on registered vars"))
    @needs_pysat
    def test_A07_F005_sat_check_sees_bindings(self):
        from clausal.logic.clpsat import sat_constraint_block, sat_check
        tr = Trail()
        x, y = Var(), Var()
        sat_constraint_block((BitOr(left=x, right=y),), "cadical195", tr)
        unify(x, 0, tr)
        unify(y, 0, tr)
        assert not sat_check(tr), "X|Y with X=0, Y=0 is unsatisfiable"

    def test_A07_F006_global_tables_bounded(self):
        import gc
        before = len(clpb._id_to_var)
        for _ in range(200):
            tr = Trail()
            x, y = Var(), Var()
            sat(BitOr(left=x, right=y), tr)
        del tr, x, y
        gc.collect()
        growth = len(clpb._id_to_var) - before
        assert growth < 100, (
            f"{growth} vars pinned in module-global _id_to_var after 200 "
            "throwaway queries")

    @pytest.mark.timeout(90)  # override the suite-wide 10s pytest-timeout
    def test_A07_F007_deep_bdd_no_segfault(self):
        script = textwrap.dedent("""
            import sys
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))  # no core dumps in repo
            N = 100000
            sys.setrecursionlimit(N * 4 + 10000)
            from clausal.logic.variables import Var
            from clausal.logic.clpb import (make_node, enumerate_var, negate,
                                            BDD_TRUE, BDD_FALSE)
            vs = [Var() for _ in range(N)]
            ids = [enumerate_var(v) for v in vs]
            bdd = BDD_TRUE
            for i in range(N - 1, -1, -1):
                bdd = make_node(ids[i], bdd, BDD_FALSE, vs[i])
            negate(bdd)
            print("OK")
        """)
        env = dict(os.environ, PYTHONPATH=REPO_ROOT)
        proc = subprocess.run([sys.executable, "-c", script], env=env,
                              capture_output=True, text=True, timeout=80)
        assert proc.returncode == 0 and "OK" in proc.stdout, (
            f"deep-BDD negate crashed: returncode={proc.returncode} "
            f"(-11 = SIGSEGV), stderr={proc.stderr[-200:]}")

    @pytest.mark.xfail(strict=False, reason=(
        "A07-F008: _count_paths_py's inner recursion dispatches through the "
        "rebound module global (the C wrapper drops current_level) — the saved "
        "'Python reference' returns wrong counts while C is loaded"))
    def test_A07_F008_count_paths_py_reference_correct(self):
        from clausal.logic.clpb import _count_paths_py
        vs = [Var() for _ in range(4)]
        ids = [enumerate_var(v) for v in vs]
        # BDD over vars 0 and 3; levels 1, 2 skipped below the root.
        inner = make_node(ids[3], BDD_TRUE, BDD_FALSE, vs[3])
        bdd = make_node(ids[0], inner, BDD_FALSE, vs[0])
        lm = {vid: i for i, vid in enumerate(sorted(ids))}
        # true count: x0=1 ∧ x3=1, x1/x2 free → 4
        assert _count_paths_py(bdd, lm, 4, {}) == 4

    def test_A07_F009_bool_labeling_validates_ground_elements(self):
        tr = Trail()
        results = None
        try:
            results = list(bool_labeling([2, "a"], tr))
        except (TypeError, ValueError):
            return  # rejecting is correct
        assert results == [], (
            "bool_labeling([2, 'a']) yielded a solution for non-Boolean terms")

    def test_A07_F010_python_bool_binding(self):
        tr = Trail()
        x, y = Var(), Var()
        assert sat(BitOr(left=x, right=y), tr)
        ok = unify(x, True, tr)
        if ok:
            val = deref(x)
            assert not isinstance(val, bool) and val == 1, (
                f"CLP(B) var bound to Python bool {val!r}, not integer 1")
