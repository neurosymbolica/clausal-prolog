"""A06 CLP(FD) / CLP(Z) — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/06-clpfd/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_06_clpfd.py -v

Scope: clausal/logic/clpfd.py, _clpfd_core.c, _clpfd_propagate.c,
_arithmetic_core.c.  Known prior art cited, not re-reported:
todo/cross_cutting_issues.md issue 3 (Cumulative stale snapshots) and
issue 8 (int64 ceilings), implementation_plans/clpfd/todo/*.
"""
import itertools
import json
import os
import random
import subprocess
import sys
from fractions import Fraction

import pytest

from clausal.logic.solve import solve   # P2: a cell goal is driven, never iterated
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.variables import Var, Trail, deref, is_var, unify, get_attr, put_attr
from clausal.logic import clpfd
from clausal.logic.clpfd import (
    FD_KEY,
    all_different,
    chain,
    cumulative,
    domain_contains,
    domain_from_range,
    domain_max,
    domain_min,
    domain_remove,
    domain_remove_above,
    domain_remove_below,
    domain_size,
    fd_element,
    fd_circuit,
    fd_eq,
    fd_ge,
    fd_gt,
    fd_le,
    fd_lt,
    fd_ne,
    fd_scalar_product,
    fd_sum,
    global_cardinality,
    in_domain,
    label,
    reify_fd,
    tuples_in,
    zcompare,
)
from clausal.terms import Add, Div, Mult, Negate, Sub


# ── helpers ───────────────────────────────────────────────────────────────────


def dom(v):
    """Current domain of v, or its value if bound."""
    v = deref(v)
    if not is_var(v):
        return v
    s = get_attr(v, FD_KEY)
    return s.domain if s is not None else None


def label_set(vs, trail):
    out = set()
    for _ in label(vs, trail):
        out.add(tuple(deref(v) for v in vs))
    return out


_loaded = {}


@pytest.fixture(scope="session")
def load(tmp_path_factory):
    """Load each fixture exactly once per session (atoms are module-scoped)."""

    def _load(name, source=None, path=None):
        if name not in _loaded:
            if path is None:
                d = tmp_path_factory.mktemp("a06fix")
                p = d / f"{name}.clausal"
                p.write_text(source)
                path = str(p)
            _loaded[name] = _load_module(f"a06_{name}", path)
        return _loaded[name]

    yield _load
    _loaded.clear()


# ── Oracles: classic instances with known solution counts ────────────────────


class TestOracles:
    def test_queens6_count(self, load):
        m = load("queens", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "clpfd_queens.clausal"))
        qs = [Var() for _ in range(6)]
        assert sum(1 for _ in solve(("safe_queens", 6, qs), m)) == 4

    def test_queens8_count(self, load):
        m = load("queens", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "clpfd_queens.clausal"))
        qs = [Var() for _ in range(8)]
        assert sum(1 for _ in solve(("safe_queens", 8, qs), m)) == 92

    def test_sendmore_unique(self, load):
        m = load("sendmore", path=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "clpfd_sendmore.clausal"))
        vs = [Var() for _ in range(8)]
        sols = [tuple(deref(v) for v in vs) for _ in solve(("sendmoney", *vs), m)]
        assert sols == [(9, 5, 6, 7, 1, 0, 8, 2)]


# ── Differential oracle: brute force vs propagate+label ─────────────────────


OPS = {
    "eq": (fd_eq, lambda a, b: a == b),
    "ne": (fd_ne, lambda a, b: a != b),
    "lt": (fd_lt, lambda a, b: a < b),
    "le": (fd_le, lambda a, b: a <= b),
    "gt": (fd_gt, lambda a, b: a > b),
    "ge": (fd_ge, lambda a, b: a >= b),
}


class TestDifferential:
    def test_binary_networks_match_bruteforce(self):
        random.seed(42)
        for _ in range(120):
            n = random.randint(2, 4)
            lo, hi = random.randint(-3, 1), random.randint(1, 4)
            cons = [
                (random.choice(list(OPS)), random.randrange(n), random.randrange(n))
                for _ in range(random.randint(1, 5))
            ]
            expected = {
                tup
                for tup in itertools.product(range(lo, hi + 1), repeat=n)
                if all(OPS[o][1](tup[i], tup[j]) for o, i, j in cons)
            }
            t = Trail()
            vs = [Var() for _ in range(n)]
            ok = in_domain(vs, lo, hi, t)
            for o, i, j in cons:
                if not ok:
                    break
                ok = OPS[o][0](vs[i], vs[j], t)
            got = label_set(vs, t) if ok else set()
            assert got == expected, (cons, lo, hi)

    def test_linear_expr_eq_lt_le_match_bruteforce(self):
        # a*X + b*Y + c OP Z over small domains (ne excluded: A06-F001)
        random.seed(7)
        for _ in range(80):
            a, b, c = random.randint(-3, 3), random.randint(-3, 3), random.randint(-4, 4)
            op = random.choice(["eq", "lt", "le"])
            expected = {
                tup
                for tup in itertools.product(range(-2, 4), repeat=3)
                if OPS[op][1](a * tup[0] + b * tup[1] + c, tup[2])
            }
            t = Trail()
            vs = [Var() for _ in range(3)]
            in_domain(vs, -2, 3, t)
            expr = Add(
                left=Add(left=Mult(left=a, right=vs[0]), right=Mult(left=b, right=vs[1])),
                right=c,
            )
            ok = OPS[op][0](expr, vs[2], t)
            got = label_set(vs, t) if ok else set()
            assert got == expected, (op, a, b, c)


# ── A06-F001: != never evaluates expression operands (UNSOUND) ───────────────


class TestNeExpressionBlindness:
    def test_ne_with_expr_fails_when_equal(self):
        t = Trail()
        x, y = Var(), Var()
        assert fd_ne(Add(left=x, right=1), y, t)
        r2 = unify(x, 1, t)
        r3 = unify(y, 2, t)
        assert not (r2 and r3), "1+1 != 2 must fail"

    def test_ne_with_expr_label_excludes_violators(self):
        t = Trail()
        x, y = Var(), Var()
        in_domain([x, y], 1, 3, t)
        assert fd_ne(Add(left=x, right=1), y, t)
        sols = label_set([x, y], t)
        assert all(a + 1 != b for a, b in sols), sorted(sols)
        assert len(sols) == 7

    def test_compiled_ne_expr(self, load):
        m = load("ne_expr", source="""
bad(X, Y) <- (X + 1 != Y, X is 1, Y is 2)

good(X, Y) <- (X + 1 != Y, X is 1, Y is 5)
""")
        x, y = Var(), Var()
        assert sum(1 for _ in solve(("bad", x, y), m)) == 0
        x, y = Var(), Var()
        assert sum(1 for _ in solve(("good", x, y), m)) == 1

    def test_ne_ground_expr_at_post_ok(self):
        # _resolve evaluates ground expressions before posting — correct today.
        t = Trail()
        assert fd_ne(Add(left=1, right=1), 2, t) is False
        assert fd_ne(Add(left=1, right=1), 3, t) is True


# ── A06-F002: output-mode linear == never grounds unbounded vars ─────────────


class TestOutputModeLinearEq:
    def test_negate_output_mode(self):
        t = Trail()
        x, y = Var(), Var()
        assert fd_eq(x, Negate(operand=y), t)
        assert unify(y, 3, t)
        assert deref(x) == -3

    def test_mult_output_mode(self):
        t = Trail()
        x, y = Var(), Var()
        assert fd_eq(x, Mult(left=2, right=y), t)
        assert unify(y, 5, t)
        assert deref(x) == 10

    def test_compiled_reverse_double(self, load):
        m = load("dbl", source="""
double(X, Y) <- (Y == 2 * X)
""")
        x = Var()
        got = [deref(x) for _ in solve(("double", x, 8), m)]
        assert got == [4]

    def test_bounded_output_mode_works(self):
        # Regression guard: with a finite domain the same equation grounds.
        t = Trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, -100, 100, t)
        assert fd_eq(x, Add(left=y, right=z), t)
        assert unify(y, 1, t)
        assert unify(z, 2, t)
        assert deref(x) == 3

    def test_input_mode_works(self, load):
        m = load("dbl", source="""
double(X, Y) <- (Y == 2 * X)
""")
        y = Var()
        assert [deref(y) for _ in solve(("double", 3, y), m)] == [6]


# ── A06-F003 / A06-F004: double-precision over-pruning (UNSOUND) ─────────────


class TestDoublePrecisionRounding:
    def test_sum_near_2_53(self):
        P = 2 ** 53
        t = Trail()
        y = Var()
        in_domain(y, P, P + 2, t)
        # -(2^53) + Y == 1  →  Y = 2^53 + 1 (valid, in domain)
        assert fd_eq(Add(left=-P, right=y), 1, t)
        assert deref(y) == P + 1

    def test_scalar_bignum_exact_division(self):
        t = Trail()
        x = Var()
        in_domain(x, 0, 2 ** 62, t)
        total = 3 * (2 ** 60 + 1)
        assert fd_eq(Mult(left=3, right=x), total, t)
        assert deref(x) == 2 ** 60 + 1

    def test_scalar_small_values_exact(self):
        # Regression guard: normal ranges divide exactly.
        t = Trail()
        x = Var()
        in_domain(x, 0, 10 ** 6, t)
        assert fd_eq(Mult(left=3, right=x), 3 * 12345, t)
        assert deref(x) == 12345


# ── A06-F005: element/3 with unconstrained index crashes ─────────────────────


class TestElement:
    def test_element_unconstrained_index(self):
        t = Trail()
        i, v = Var(), Var()
        got = [(deref(i), deref(v)) for _ in fd_element(i, [10, 20, 30, 20], v, t)]
        assert got == [(1, 10), (2, 20), (3, 30), (4, 20)]

    def test_element_bounded_index_enumeration(self):
        t = Trail()
        i, v = Var(), Var()
        in_domain(i, 1, 4, t)
        got = [(deref(i), deref(v)) for _ in fd_element(i, [10, 20, 30, 20], v, t)]
        assert got == [(1, 10), (2, 20), (3, 30), (4, 20)]

    def test_element_value_fixed(self):
        t = Trail()
        i = Var()
        in_domain(i, 1, 4, t)
        assert [deref(i) for _ in fd_element(i, [10, 20, 30, 20], 20, t)] == [2, 4]

    def test_element_var_list_element(self):
        t = Trail()
        i, x = Var(), Var()
        in_domain(i, 1, 2, t)
        got = [(deref(i), deref(x)) for _ in fd_element(i, [x, 5], 7, t)]
        assert got == [(1, 7)]

    def test_element_ground_index(self):
        t = Trail()
        v = Var()
        assert [deref(v) for _ in fd_element(2, [10, 20, 30], v, t)] == [20]
        t = Trail()
        assert list(fd_element(5, [10, 20, 30], Var(), t)) == []


# ── A06-F006: rational subexpression → TypeError from C domain ops ───────────


class TestRationalSubexpression:
    def test_rational_subexpr_no_crash(self):
        t = Trail()
        x, y = Var(), Var()
        assert fd_eq(x, Add(left=y, right=Div(left=1, right=2)), t)
        try:
            r = unify(y, 1, t)
        except TypeError as e:  # pragma: no cover - the bug
            pytest.fail(f"TypeError escaped from unify: {e}")
        # Correct behaviour: CLP(Q) semantics X = 3/2
        assert r
        assert deref(x) == Fraction(3, 2)

    def test_rational_literal_dispatches_to_clpq(self):
        # Regression guard: a directly rational RHS goes to CLP(Q) today.
        t = Trail()
        x = Var()
        assert fd_eq(x, Div(left=7, right=2), t)
        assert deref(x) == Fraction(7, 2)


# ── A06-F007: int64 boundary bounds silently become ±inf ─────────────────────


class TestInt64BoundarySentinel:
    def test_exact_int64_max_bound_is_finite(self):
        t = Trail()
        x = Var()
        assert in_domain(x, 0, 2 ** 63 - 1, t)
        # 2**100 is outside the declared domain — must be rejected
        assert not fd_eq(x, 2 ** 100, t)

    def test_exact_int64_max_domain_size_finite(self):
        d = domain_from_range(0, 2 ** 63 - 1)
        assert domain_size(d) == 2 ** 63
        assert not domain_contains(d, 2 ** 100)

    def test_near_boundary_bounds_exact(self):
        # Regression guard: INT64_MAX - 1 stays finite.
        d = domain_from_range(0, 2 ** 63 - 2)
        assert domain_size(d) == 2 ** 63 - 1
        assert not domain_contains(d, 2 ** 63 - 1)
        # And true bignum bounds round-trip via the Python fallback.
        d2 = domain_from_range(0, 2 ** 64)
        assert domain_contains(d2, 2 ** 64)
        assert not domain_contains(d2, 2 ** 64 + 1)


# ── A06-F007 follow-up: sentinel collision in value/limit ARGUMENTS ──────────
# 7fad78d6 fixed domain *construction* at the int64 boundary; the same
# collision existed for the value/limit arguments of domain_remove{,_above,
# _below} and for the ne/lt/le propagators' int operands.


_I64MAX = 2 ** 63 - 1
_I64MIN = -(2 ** 63)
_INF = float("inf")


class TestInt64SentinelValueArgs:
    def test_remove_above_at_int64_max_keeps_cap(self):
        d = domain_remove_above(domain_from_range(0, _INF), _I64MAX)
        assert domain_contains(d, _I64MAX)
        assert not domain_contains(d, 2 ** 63)
        assert not domain_contains(d, 2 ** 100)

    def test_remove_below_at_int64_min_keeps_cap(self):
        d = domain_remove_below(domain_from_range(-_INF, 0), _I64MIN)
        assert domain_contains(d, _I64MIN)
        assert not domain_contains(d, _I64MIN - 1)
        assert not domain_contains(d, -(2 ** 100))

    def test_remove_at_int64_max_removes_only_that_value(self):
        d = domain_remove(domain_from_range(-_INF, _INF), _I64MAX)
        assert not domain_contains(d, _I64MAX)
        assert domain_contains(d, _I64MAX - 1)
        assert domain_contains(d, 2 ** 63)

    def test_remove_at_int64_min_removes_only_that_value(self):
        d = domain_remove(domain_from_range(-_INF, _INF), _I64MIN)
        assert not domain_contains(d, _I64MIN)
        assert domain_contains(d, _I64MIN + 1)
        assert domain_contains(d, _I64MIN - 1)

    def test_fd_ne_at_int64_max_allows_neighbour(self):
        t = Trail()
        z = Var()
        assert fd_ne(z, _I64MAX, t)
        assert unify(z, 2 ** 63, t)  # 2**63 != 2**63-1 — must succeed

    def test_fd_ne_at_int64_max_still_excludes_value(self):
        t = Trail()
        z = Var()
        assert fd_ne(z, _I64MAX, t)
        assert not unify(z, _I64MAX, t)

    def test_fd_ne_at_int64_min_allows_neighbour(self):
        t = Trail()
        u = Var()
        assert fd_ne(u, _I64MIN, t)
        assert unify(u, _I64MIN - 1, t)  # -(2**63)-1 != -(2**63) — must succeed

    def test_fd_ne_at_int64_min_still_excludes_value(self):
        t = Trail()
        u = Var()
        assert fd_ne(u, _I64MIN, t)
        assert not unify(u, _I64MIN, t)

    def test_fd_le_at_int64_max_bounds_domain(self):
        # Reflection: the cap must land in X's domain, not be silently dropped.
        t = Trail()
        x = Var()
        assert fd_le(x, _I64MAX, t)
        s = get_attr(x, FD_KEY)
        assert s is not None
        assert domain_max(s.domain) == _I64MAX
        assert not domain_contains(s.domain, 2 ** 63)

    def test_fd_ge_at_int64_min_bounds_domain(self):
        t = Trail()
        x = Var()
        assert fd_ge(x, _I64MIN, t)
        s = get_attr(x, FD_KEY)
        assert s is not None
        assert domain_min(s.domain) == _I64MIN
        assert not domain_contains(s.domain, _I64MIN - 1)

    def test_c_and_python_domain_ops_agree_at_boundaries(self):
        unbounded = clpfd._py_domain_from_range(-_INF, _INF)
        cases = [
            (clpfd.domain_remove_above, clpfd._py_domain_remove_above, _I64MAX),
            (clpfd.domain_remove_above, clpfd._py_domain_remove_above, _I64MAX - 1),
            (clpfd.domain_remove_below, clpfd._py_domain_remove_below, _I64MIN),
            (clpfd.domain_remove_below, clpfd._py_domain_remove_below, _I64MIN + 1),
            (clpfd.domain_remove, clpfd._py_domain_remove, _I64MAX),
            (clpfd.domain_remove, clpfd._py_domain_remove, _I64MIN),
            (clpfd.domain_contains, clpfd._py_domain_contains, _I64MAX),
            (clpfd.domain_contains, clpfd._py_domain_contains, _I64MIN),
        ]
        for c_op, py_op, arg in cases:
            assert c_op(unbounded, arg) == py_op(unbounded, arg), (py_op, arg)

    def test_domain_size_wide_fast_path_no_overflow(self):
        # Widest fast-path domain: width 2^64 - 2 overflows a signed
        # 64-bit accumulator; must match the Python reference.
        d = domain_from_range(-(2 ** 63) + 1, 2 ** 63 - 2)
        assert domain_size(d) == 2 ** 64 - 2
        assert domain_size(d) == clpfd._py_domain_size(d)

    def test_near_boundary_and_bignum_limits_regression(self):
        # Just inside the boundary stays on the fast path and is exact.
        d = domain_remove_above(domain_from_range(0, _INF), _I64MAX - 1)
        assert domain_contains(d, _I64MAX - 1)
        assert not domain_contains(d, _I64MAX)
        # True bignum limits keep working via the Python fallback.
        d2 = domain_remove_above(domain_from_range(0, _INF), 2 ** 64)
        assert domain_contains(d2, 2 ** 64)
        assert not domain_contains(d2, 2 ** 64 + 1)
        # ne just inside the boundary: neighbour above is the sentinel value.
        t = Trail()
        z = Var()
        assert fd_ne(z, _I64MAX - 1, t)
        assert unify(z, _I64MAX, t)


# ── A06-F007 sibling: alldiff ground members at the int64 sentinels ──────────
# alldiff_propagate did an ungated PyLong_AsLongLong on a ground member before
# domain_remove_c on the peers: a member at exactly 2**63-1 / -(2**63) read
# back as ±inf (truncating the peer domains), and a true bignum member raised
# OverflowError.  C path only — the pure-Python propagator was correct.


def _open_fd_var(t):
    """Fresh var with an unbounded FD domain (minus a marker hole)."""
    v = Var()
    assert fd_ne(v, 12345, t)
    return v


_ALLDIFF_AGREEMENT_SCRIPT = r"""
import json, sys
if sys.argv[1] == "py":
    sys.modules['clausal.logic._clpfd_propagate'] = None
    sys.modules['clausal.logic._clpfd_core'] = None
from clausal.logic.variables import Var, Trail
from clausal.logic import clpfd
from clausal.logic.clpfd import all_different, fd_ne, domain_contains, FD_KEY
from clausal.logic.variables import get_attr

assert clpfd._USE_C_PROPAGATE == (sys.argv[1] == "c")
assert clpfd._USE_C_DOMAINS == (sys.argv[1] == "c")

I64MAX = 2 ** 63 - 1
I64MIN = -(2 ** 63)
out = []
for g in (I64MAX, I64MIN, 2 ** 64, -(2 ** 64), I64MAX - 1, I64MIN + 1, 7):
    t = Trail()
    x = Var()
    assert fd_ne(x, 12345, t)
    assert all_different([x, g], t)
    d = get_attr(x, FD_KEY).domain
    out.append([bool(domain_contains(d, p))
                for p in (g - 1, g, g + 1, 0, 2 ** 100, -(2 ** 100))])
print(json.dumps(out))
"""


class TestAllDiffInt64Sentinel:
    def test_ground_member_at_int64_max_removes_only_that_value(self):
        t = Trail()
        x = _open_fd_var(t)
        assert all_different([x, _I64MAX], t)
        d = dom(x)
        assert not domain_contains(d, _I64MAX)
        assert domain_contains(d, _I64MAX - 1)
        assert domain_contains(d, 2 ** 63)   # was wrongly removed (truncation)
        assert domain_contains(d, 2 ** 100)  # was wrongly removed (truncation)

    def test_ground_member_at_int64_min_removes_only_that_value(self):
        t = Trail()
        x = _open_fd_var(t)
        assert all_different([x, _I64MIN], t)
        d = dom(x)
        assert not domain_contains(d, _I64MIN)
        assert domain_contains(d, _I64MIN + 1)
        assert domain_contains(d, _I64MIN - 1)   # was wrongly removed
        assert domain_contains(d, -(2 ** 100))   # was wrongly removed

    def test_ground_member_true_bignum_no_overflow(self):
        t = Trail()
        x = _open_fd_var(t)
        assert all_different([x, 2 ** 64], t)  # raised OverflowError before
        d = dom(x)
        assert not domain_contains(d, 2 ** 64)
        assert domain_contains(d, 2 ** 64 - 1)
        assert domain_contains(d, 2 ** 64 + 1)

    def test_peer_domain_with_bignum_bound_small_ground_member(self):
        # Same call site, mirrored shape: the PEER's domain carries a bignum
        # bound, which domain_remove_c cannot unpack (raised OverflowError).
        t = Trail()
        x = Var()
        assert fd_le(x, 2 ** 64, t)
        assert all_different([x, 5], t)
        d = dom(x)
        assert not domain_contains(d, 5)
        assert domain_contains(d, 4)
        assert domain_contains(d, 2 ** 64)

    def test_member_bound_to_sentinel_after_posting(self):
        # Grounding a member AFTER posting re-fires the propagator through
        # the unification hook — same guarded removal path.
        t = Trail()
        x = _open_fd_var(t)
        y = _open_fd_var(t)
        assert all_different([x, y], t)
        assert unify(y, _I64MAX, t)
        d = dom(x)
        assert not domain_contains(d, _I64MAX)
        assert domain_contains(d, 2 ** 63)

    def test_c_and_python_alldiff_agree_at_boundaries(self):
        if not clpfd._USE_C_PROPAGATE:
            pytest.skip("C propagate extension not in use")
        # _USE_C_PROPAGATE is read at import time, so the pure-Python leg
        # runs in a subprocess with the C extensions import-blocked.
        repo_root = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))))
        env = {**os.environ, "PYTHONPATH": repo_root}

        def leg(which):
            p = subprocess.run(
                [sys.executable, "-c", _ALLDIFF_AGREEMENT_SCRIPT, which],
                capture_output=True, text=True, env=env)
            assert p.returncode == 0, p.stderr
            return json.loads(p.stdout)

        assert leg("c") == leg("py")

    def test_ground_member_just_inside_fast_range_regression(self):
        # 2**63-2 is the largest int on the C fast path — must stay there
        # and remove exactly itself.
        t = Trail()
        x = _open_fd_var(t)
        assert all_different([x, _I64MAX - 1], t)
        d = dom(x)
        assert not domain_contains(d, _I64MAX - 1)
        assert domain_contains(d, _I64MAX - 2)
        assert domain_contains(d, _I64MAX)

    def test_small_int_alldiff_regression(self):
        t = Trail()
        x, y, z = Var(), Var(), Var()
        assert in_domain([x, y, z], 1, 3, t)
        assert all_different([x, y, z], t)
        assert unify(x, 1, t)
        assert unify(y, 2, t)
        assert deref(z) == 3  # propagation forces the last value


# ── A06-F008: in_domain doesn't re-propagate existing constraints ────────────


class TestInDomainPropagation:
    def test_in_domain_propagates_through_eq(self):
        t = Trail()
        x, y = Var(), Var()
        assert fd_eq(x, y, t)
        assert in_domain(x, 1, 5, t)
        assert [deref(y) for _ in label([y], t)] == [1, 2, 3, 4, 5]

    def test_in_domain_before_constraint_propagates(self):
        # Regression guard: posting order in_domain-then-== works.
        t = Trail()
        x, y = Var(), Var()
        assert in_domain(x, 1, 3, t)
        assert fd_eq(x, y, t)
        assert label_set([x, y], t) == {(1, 1), (2, 2), (3, 3)}


# ── A06-F009: booleans — C hook accepts, Python hook rejects, docs say reject ─


class TestBooleanHandling:
    @pytest.mark.xfail(strict=False, reason="A06-F009: C _fd_hook accepts bool via the "
                       ".denominator sniff; docs say booleans are rejected by CLP(Z)")
    def test_binding_fd_var_to_bool_fails(self):
        t = Trail()
        x = Var()
        assert in_domain(x, 1, 5, t)
        assert not unify(x, True, t)

    @pytest.mark.xfail(strict=False, reason="A06-F009: ground comparison paths treat "
                       "True as 1 (docs: booleans are not numbers in CLP(Z))")
    def test_ground_bool_comparison_rejected(self):
        t = Trail()
        assert not fd_eq(1, True, t)

    def test_binding_fd_var_to_float_or_string_fails(self):
        # Regression guard: non-integer bindings are rejected by the hook.
        for bad in (3.0, "a", [1]):
            t = Trail()
            x = Var()
            assert in_domain(x, 1, 5, t)
            assert not unify(x, bad, t)

    def test_binding_fd_var_to_integer_fraction_ok(self):
        t = Trail()
        x = Var()
        assert in_domain(x, 1, 5, t)
        assert unify(x, Fraction(3), t)
        assert deref(x) == 3


# ── A06-F010: X != X accepted at post time ────────────────────────────────────


class TestNeReflexivity:
    def test_ne_same_var_fails_at_post(self):
        t = Trail()
        x = Var()
        assert fd_ne(x, x, t) is False

    def test_ne_same_var_yields_no_labelled_solutions(self):
        # Regression guard: at least no unsound labelled answers escape.
        t = Trail()
        x = Var()
        in_domain(x, 1, 3, t)
        fd_ne(x, x, t)
        assert sum(1 for _ in label([x], t)) == 0


# ── A06-F011: sum_/scalar_product operator-atom vocabulary ───────────────────
# Renamed from TestSumOpStrings by Task 12b: the Op is an ATOM (spec §6.4),
# and a plain str in that position is now refused, not read as the spelling.


class TestSumOpAtoms:
    def test_prolog_style_ops_post(self):
        for op in ["#=", "=", "#<", "#>", "#=<", "#>=", "#\\="]:
            t = Trail()
            x, y = Var(), Var()
            in_domain([x, y], 1, 5, t)
            assert sum(1 for _ in fd_sum([x, y], mint(op), 6, t)) == 1, op

    @pytest.mark.xfail(strict=False, reason="A06-F011: Python-style op strings "
                       "('<=', '==', '!=') — the language's own operator spelling — "
                       "silently post nothing instead of working or raising")
    def test_python_style_ops_post(self):
        for op in ["<=", "==", "!="]:
            t = Trail()
            x, y = Var(), Var()
            in_domain([x, y], 1, 5, t)
            assert sum(1 for _ in fd_sum([x, y], mint(op), 6, t)) == 1, op

    def test_sum_eq_narrows_and_labels(self):
        t = Trail()
        x, y = Var(), Var()
        in_domain(x, 8, 9, t)
        in_domain(y, 1, 9, t)
        assert sum(1 for _ in fd_sum([x, y], mint("#="), 10, t)) == 1
        assert dom(y) == ((1, 2),)

    def test_scalar_product_solutions(self):
        t = Trail()
        x, y = Var(), Var()
        in_domain([x, y], 0, 10, t)
        n = sum(1 for _ in fd_scalar_product([2, 3], [x, y], mint("#="), 6, t))
        assert n == 1
        assert label_set([x, y], t) == {(0, 2), (3, 0)}


# ── A06-F012: zcompare weak propagation ──────────────────────────────────────


class TestZcompare:
    def test_order_determined_by_binding(self):
        t = Trail()
        o, x, y = Var(), Var(), Var()
        in_domain([x, y], 1, 5, t)
        assert zcompare(o, x, y, t)
        assert unify(x, 2, t)
        assert unify(y, 4, t)
        assert deref(o) == mint("<")

    def test_ground_order_constrains(self):
        t = Trail()
        x, y = Var(), Var()
        in_domain([x, y], 1, 5, t)
        assert zcompare(mint("<"), x, y, t)
        assert dom(x) == ((1, 4),)
        assert dom(y) == ((2, 5),)

    def test_binding_order_var_propagates(self):
        t = Trail()
        o, x, y = Var(), Var(), Var()
        in_domain([x, y], 1, 5, t)
        assert zcompare(o, x, y, t)
        assert unify(o, mint("<"), t)
        assert dom(x) == ((1, 4),)

    def test_binding_order_var_sound_after_labeling(self):
        # Regression guard: even though propagation is delayed, labeling is sound.
        t = Trail()
        o, x, y = Var(), Var(), Var()
        in_domain([x, y], 1, 5, t)
        zcompare(o, x, y, t)
        assert unify(o, mint("<"), t)
        sols = label_set([x, y], t)
        assert sols == {(a, b) for a in range(1, 6) for b in range(1, 6) if a < b}

    def test_same_var_is_eq(self):
        t = Trail()
        o, x = Var(), Var()
        in_domain(x, 1, 5, t)
        assert zcompare(o, x, x, t)
        assert deref(o) == mint("=")


# ── A06-F013: global_cardinality var counts never propagate ──────────────────


class TestGlobalCardinality:
    def test_ground_counts(self):
        t = Trail()
        vs = [Var() for _ in range(3)]
        in_domain(vs, 1, 2, t)
        assert global_cardinality(vs, [(1, 2), (2, 1)], t)
        assert label_set(vs, t) == {(1, 1, 2), (1, 2, 1), (2, 1, 1)}

    def test_var_count_bound_when_ground(self):
        t = Trail()
        vs = [Var() for _ in range(3)]
        cnt = Var()
        for v in vs:
            assert unify(v, 1, t)
        assert global_cardinality(vs, [(1, cnt)], t)
        assert deref(cnt) == 3

    def test_values_outside_pairs_allowed_today(self):
        # Current behaviour (parked design question A06-D003): values not
        # listed in Pairs are unconstrained; SWI restricts Vars to the keys.
        t = Trail()
        vs = [Var() for _ in range(2)]
        in_domain(vs, 1, 3, t)
        assert global_cardinality(vs, [(1, 1), (2, 1)], t)
        assert label_set(vs, t) == {(1, 2), (2, 1)}


# ── A06-F014 / F015: type-check holes ─────────────────────────────────────────


class TestTypeHoles:
    def test_sum_over_strings_rejected(self):
        t = Trail()
        assert sum(1 for _ in fd_sum(["a", "b"], mint("#="), 5, t)) == 0

    def test_plus_strings_rejected(self):
        from clausal.logic._arithmetic_core import arith_plus

        t = Trail()
        z = Var()
        r = arith_plus("a", "b", z, t)
        assert r is None  # no solution — correct behaviour for non-numeric args

    def test_plus_string_inverse_no_crash(self):
        from clausal.logic._arithmetic_core import arith_plus

        t = Trail()
        y = Var()
        try:
            r = arith_plus("a", y, "ab", t)
        except TypeError as e:
            pytest.fail(f"TypeError escaped: {e}")
        assert r is None

    def test_all_different_type_edges(self):
        t = Trail()
        assert all_different([1, 1], t) is False
        t = Trail()
        assert all_different([1, 2], t) is True
        t = Trail()
        assert all_different(["a", "b"], t) is False  # non-integers fail (silently)


# ── A06-F016: non-FDVar "fd" attribute must not be struct-cast (UB) ───────────


class TestFdVarDuckTypingUB:
    def test_non_fdvar_fd_attr_no_crash(self):
        # A user-supplied "fd" attribute that merely *looks* like an FDVar
        # (has .domain / .constraints) was cast to FDVarObject* and read at
        # fixed struct offsets — undefined behaviour, one refactor from a
        # segfault.  It must now fail cleanly (TypeError), never crash.
        import types as _types

        t = Trail()
        x = Var()
        put_attr(x, "fd", _types.SimpleNamespace(domain=((1, 2),), constraints=()), t)
        with pytest.raises(TypeError):
            fd_ne(x, 1, t)

    def test_real_fdvar_still_works(self):
        # Control: a genuine FD var (real C FDVar under "fd") is unaffected.
        t = Trail()
        x = Var()
        in_domain(x, 1, 5, t)
        assert fd_ne(x, 3, t)
        assert not domain_contains(dom(x), 3)


# ── Global constraints: regression guards ────────────────────────────────────


class TestGlobalConstraintGuards:
    def test_circuit_counts(self):
        t = Trail()
        assert sum(1 for _ in fd_circuit([Var() for _ in range(3)], t)) == 2
        t = Trail()
        assert sum(1 for _ in fd_circuit([Var() for _ in range(4)], t)) == 6

    def test_circuit_degenerate_current_behaviour(self):
        # Parked design question A06-D004: circuit([]) and circuit([X]) both
        # yield 0 solutions today (SWI: circuit([]) succeeds, circuit([X]) X=1).
        t = Trail()
        assert sum(1 for _ in fd_circuit([], t)) == 0
        t = Trail()
        assert sum(1 for _ in fd_circuit([Var()], t)) == 0

    def test_tuples_in(self):
        t = Trail()
        x, y = Var(), Var()
        assert tuples_in([[x, y]], [(1, 2), (2, 3), (3, 3)], t)
        assert label_set([x, y], t) == {(1, 2), (2, 3), (3, 3)}

    def test_tuples_in_empty_relation_fails(self):
        t = Trail()
        assert tuples_in([[Var(), Var()]], [], t) is False

    def test_chain_lt(self):
        t = Trail()
        vs = [Var() for _ in range(3)]
        in_domain(vs, 1, 3, t)
        assert chain(vs, "lt", t)
        assert label_set(vs, t) == {(1, 2, 3)}

    def test_cumulative_disjunctive(self):
        # Known prior art (cite, not re-report): cross_cutting_issues.md issue 3 —
        # stale domain snapshots make filtering weaker but not unsound.
        t = Trail()
        s1, s2 = Var(), Var()
        in_domain([s1, s2], 0, 2, t)
        assert cumulative([(s1, 2, 1), (s2, 2, 1)], 1, t)
        assert label_set([s1, s2], t) == {(0, 2), (2, 0)}

    def test_cumulative_overload_fails(self):
        t = Trail()
        s1, s2 = Var(), Var()
        in_domain([s1, s2], 0, 0, t)
        assert cumulative([(s1, 1, 1), (s2, 1, 1)], 1, t) is False

    def test_reify_fd_three_valued(self):
        t = Trail()
        x = Var()
        assert reify_fd("lt", 1, 2, t) is True
        assert reify_fd("lt", 2, 1, t) is False
        assert reify_fd("lt", x, 2, t) is None


# ── Labeling: completeness, determinism, backtracking ────────────────────────


class TestLabeling:
    def test_holes_enumerated_in_order_no_dups(self):
        t = Trail()
        x = Var()
        in_domain(x, 1, 5, t)
        fd_ne(x, 3, t)
        assert [deref(x) for _ in label([x], t)] == [1, 2, 4, 5]

    def test_single_var_non_list_arg(self):
        t = Trail()
        x = Var()
        in_domain(x, 1, 2, t)
        assert [deref(x) for _ in label(x, t)] == [1, 2]

    def test_ground_list_yields_once(self):
        t = Trail()
        assert sum(1 for _ in label([1, 2], t)) == 1

    def test_unbounded_domain_raises(self):
        t = Trail()
        x, y = Var(), Var()
        fd_lt(x, y, t)  # auto-domains, still unbounded
        with pytest.raises(ValueError):
            list(label([x], t))

    def test_domainless_var_current_behaviour(self):
        # Parked design question A06-D001: a var with NO fd attr silently
        # yields one "solution" with the var left unbound, while an
        # unbounded fd attr raises ValueError.  Guard current behaviour.
        t = Trail()
        x = Var()
        n = 0
        for _ in label([x], t):
            n += 1
            assert is_var(deref(x))
        assert n == 1

    def test_backtracking_restores_domain_and_constraints(self):
        t = Trail()
        x, y = Var(), Var()
        in_domain([x, y], 1, 10, t)
        d0 = get_attr(x, FD_KEY).domain
        mark = t.mark()
        fd_lt(x, y, t)
        assert get_attr(x, FD_KEY).domain == ((1, 9),)
        t.undo(mark)
        assert get_attr(x, FD_KEY).domain == d0
        assert len(get_attr(x, FD_KEY).constraints) == 0

    def test_label_backtrack_reusable(self):
        t = Trail()
        x = Var()
        in_domain(x, 1, 3, t)
        assert [deref(x) for _ in label([x], t)] == [1, 2, 3]
        # After exhaustion the domain is restored — labeling again re-enumerates.
        assert [deref(x) for _ in label([x], t)] == [1, 2, 3]


# ── Propagation fixpoint & hook guards ────────────────────────────────────────


class TestPropagation:
    def test_lt_chain_cascade(self):
        t = Trail()
        x, y, z = Var(), Var(), Var()
        in_domain([x, y, z], 1, 10, t)
        fd_lt(x, y, t)
        fd_lt(y, z, t)
        assert unify(z, 3, t)
        assert deref(x) == 1 and deref(y) == 2

    def test_var_var_merge_intersects_and_keeps_constraints(self):
        t = Trail()
        x, y, z = Var(), Var(), Var()
        in_domain(x, 1, 5, t)
        in_domain(y, 3, 8, t)
        in_domain(z, 1, 10, t)
        fd_lt(x, z, t)
        assert unify(x, y, t)
        assert dom(x) == ((3, 5),)
        assert unify(z, 4, t)
        assert deref(x) == 3  # x < 4 with dom 3..5 → singleton 3

    def test_eq_identity_and_contradiction(self):
        t = Trail()
        x = Var()
        assert fd_eq(x, x, t) is True
        t = Trail()
        x = Var()
        assert fd_eq(x, Add(left=x, right=1), t) is False  # X == X+1

    def test_binding_outside_domain_fails(self):
        t = Trail()
        x = Var()
        in_domain(x, 1, 5, t)
        assert not unify(x, 7, t)

    def test_gt_ge_delegate_with_expr(self):
        t = Trail()
        x = Var()
        in_domain(x, 0, 10, t)
        assert fd_gt(x, Add(left=2, right=3), t)
        assert dom(x) == ((6, 10),)
        t = Trail()
        x = Var()
        in_domain(x, 0, 10, t)
        assert fd_ge(x, 7, t)
        assert dom(x) == ((7, 10),)

    def test_in_domain_singleton_binds(self):
        t = Trail()
        x = Var()
        assert in_domain(x, 5, 5, t)
        assert deref(x) == 5

    def test_in_domain_empty_fails(self):
        t = Trail()
        assert in_domain(Var(), 5, 4, t) is False


# ── _arithmetic_core guards ───────────────────────────────────────────────────


class TestArithmeticCore:
    def test_succ_both_modes(self):
        from clausal.logic._arithmetic_core import arith_succ

        t = Trail()
        y = Var()
        r = arith_succ(3, y, t)
        assert isinstance(r, int) and deref(y) == 4
        t = Trail()
        x = Var()
        r = arith_succ(x, 1, t)
        assert isinstance(r, int) and deref(x) == 0
        t = Trail()
        assert arith_succ(Var(), 0, t) is None  # succ(X, 0) has no solution
        t = Trail()
        assert arith_succ(-1, Var(), t) is None  # negative rejected

    def test_between_modes(self):
        from clausal.logic._arithmetic_core import arith_between

        t = Trail()
        assert arith_between(1, 3, 2, t) is True
        assert arith_between(1, 3, 5, t) is None
        assert arith_between(1, 3, True, t) is None  # bool is not an int
        assert arith_between(1, 3, Var(), t) == (1, 3)  # generate mode

    def test_plus_numeric_modes(self):
        from clausal.logic._arithmetic_core import arith_plus

        t = Trail()
        z = Var()
        assert isinstance(arith_plus(1, 2, z, t), int) and deref(z) == 3
        t = Trail()
        y = Var()
        assert isinstance(arith_plus(1, y, 5, t), int) and deref(y) == 4
        t = Trail()
        assert arith_plus(Var(), Var(), 5, t) is None  # two unknowns

    def test_trail_type_checked(self):
        # cross_cutting_issues.md issue 1 claims _arithmetic_core casts the
        # trail unchecked — it now Trail_Check()s (doc drift, A06-F017).
        from clausal.logic._arithmetic_core import arith_succ

        with pytest.raises(TypeError):
            arith_succ(1, Var(), "not a trail")


# ── C leak checks ─────────────────────────────────────────────────────────────


class TestCLeaks:
    def test_post_label_undo_cycle_no_leak(self, refcount_stable):
        def cycle():
            t = Trail()
            vs = [Var() for _ in range(4)]
            in_domain(vs, 1, 4, t)
            all_different(vs, t)
            fd_lt(vs[0], vs[1], t)
            fd_ne(vs[2], 3, t)
            for _ in label(vs, t):
                pass
            t.undo(0)

        refcount_stable(cycle, iterations=300, tol=64)

    def test_domain_value_refcounts_stable(self, getrefcount_stable):
        val = 123456789

        def exercise():
            t = Trail()
            x = Var()
            in_domain(x, val, val + 3, t)
            fd_ne(x, val + 1, t)
            for _ in label([x], t):
                pass

        getrefcount_stable(val, exercise, iterations=1000)
