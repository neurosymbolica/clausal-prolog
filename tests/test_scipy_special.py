"""Tests for clausal.modules.py.scipy_special — scipy.special predicates.

Tests are organised per function family and cover:
- correct result for typical inputs (scalar and/or array)
- multi-arity variants (optional args)
- unification succeeds when RESULT is unbound
- unification fails when RESULT is bound to a wrong value
"""

import math
import pytest

pytest.importorskip("scipy", reason="scipy not installed")

import numpy as np
import scipy.special as sc

from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import DONE
from clausal.modules.py.scipy_special import (
    Gamma, GammaLog, GammaSign, BetaLog, Digamma, Polygamma,
    Factorial, Comb, Perm,
    Erf, ErfComplement,
    NormalCdf,
    BesselJ, BesselY, BesselJReal, BesselYReal, BesselK, BesselI,
    BesselJZeros, SphericalBesselJ,
    EllipticK, EllipticE, EllipticKIncomplete, EllipticEIncomplete,
    Hypergeometric1F1, Hypergeometric2F1, Hypergeometric0F1,
    Entr, KlDivergence, LogSumExp,
    AssocLegendre, LegendrePoly, ChebyshevT, ChebyshevU,
    HermiteH, GeneralizedLaguerre,
    CubeRoot, Exp10, Exp2, Logit, LambertW, XLogY, XLog1pY,
)


# ── Test driver ───────────────────────────────────────────────────────────

def _drive(pred, *args):
    """Call predicate with a fresh Var as RESULT; return first solution value."""
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, *args, result, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def _drive_bwd(pred, *args):
    """Call predicate in backward direction: first arg is unbound Var, rest are ground.

    For a bidirectional predicate Pred(X, Y): binds X (result) given Y (ground).
    """
    result = Var()
    dispatch = pred._get_dispatch()
    trail = Trail()
    gen = dispatch(None, None, result, *args, trail)
    for parent, sentinel in gen:
        if sentinel is DONE:
            return None
        if sentinel is None:
            return deref(result)
    return None


def approx(a, b, rel=1e-9):
    """True when a ≈ b (handles numpy scalars and Python floats)."""
    a, b = float(np.real(a)), float(np.real(b))
    if b == 0:
        return abs(a) < 1e-14
    return abs(a - b) / max(abs(b), 1e-300) < rel


# ── Gamma and related ─────────────────────────────────────────────────────

class TestGamma:
    def test_positive_integer(self):
        # nv
        r = _drive(Gamma, 5.0)
        assert approx(r, sc.gamma(5.0))

    def test_half(self):
        # nv
        r = _drive(Gamma, 0.5)
        assert approx(r, sc.gamma(0.5))

    def test_unification_fails_wrong_value(self):
        # nv
        trail = Trail()
        result = 999.0  # ground value, won't unify with gamma(5)
        dispatch = Gamma._get_dispatch()
        solutions = list(dispatch(None, None, 5.0, result, trail))
        assert len([s for s in solutions if s[1] is None]) == 0


class TestGammaLog:
    def test_basic(self):
        # nv
        r = _drive(GammaLog, 10.0)
        assert approx(r, sc.gammaln(10.0))


class TestGammaSign:
    def test_positive(self):
        # nv
        r = _drive(GammaSign, 0.5)
        assert r == sc.gammasgn(0.5)

    def test_negative(self):
        # nv
        r = _drive(GammaSign, -0.5)
        assert r == sc.gammasgn(-0.5)


class TestBetaLog:
    def test_basic(self):
        # nv
        r = _drive(BetaLog, 2.0, 3.0)
        assert approx(r, sc.betaln(2.0, 3.0))


class TestDigamma:
    def test_basic(self):
        # nv
        r = _drive(Digamma, 1.0)
        assert approx(r, sc.digamma(1.0))


class TestPolygamma:
    def test_order_0_is_digamma(self):
        # nv
        r = _drive(Polygamma, 0, 1.0)
        assert approx(r, sc.polygamma(0, 1.0))

    def test_order_1(self):
        # nv
        r = _drive(Polygamma, 1, 2.0)
        assert approx(r, sc.polygamma(1, 2.0))


class TestFactorial:
    def test_arity2_exact_false(self):
        # nv
        r = _drive(Factorial, 5)
        assert approx(r, sc.factorial(5, exact=False))

    def test_arity3_exact_true(self):
        # nv
        r = _drive(Factorial, 5, True)
        assert r == 120

    def test_zero(self):
        # nv
        r = _drive(Factorial, 0)
        assert approx(r, 1.0)


class TestComb:
    def test_arity3(self):
        # nv
        r = _drive(Comb, 5, 2)
        assert approx(r, sc.comb(5, 2, exact=False))

    def test_arity4_exact(self):
        # nv
        r = _drive(Comb, 5, 2, True)
        assert r == 10

    def test_arity5_repetition(self):
        # nv
        r = _drive(Comb, 5, 2, False, True)
        assert approx(r, sc.comb(5, 2, exact=False, repetition=True))


class TestPerm:
    def test_arity3(self):
        # nv
        r = _drive(Perm, 5, 2)
        assert approx(r, sc.perm(5, 2, exact=False))

    def test_arity4_exact(self):
        # nv
        r = _drive(Perm, 5, 2, True)
        assert r == 20


# ── Error functions ───────────────────────────────────────────────────────

class TestErf:
    def test_zero(self):
        # nv
        r = _drive(Erf, 0.0)
        assert approx(r, 0.0)

    def test_one(self):
        # nv
        r = _drive(Erf, 1.0)
        assert approx(r, sc.erf(1.0))


class TestErfComplement:
    def test_one(self):
        # nv
        r = _drive(ErfComplement, 1.0)
        assert approx(r, sc.erfc(1.0))

    def test_sums_to_one(self):
        # nv
        erf_val = _drive(Erf, 1.0)
        erfc_val = _drive(ErfComplement, 1.0)
        assert approx(erf_val + erfc_val, 1.0)


class TestErfInverse:
    def test_round_trip(self):
        # nv
        x = 0.5
        erf_x = _drive(Erf, x)
        # Backward direction of Erf: Erf(result_var, erf_x) → result_var = erfinv(erf_x)
        inv = _drive_bwd(Erf, erf_x)
        assert approx(inv, x)


class TestErfComplementInverse:
    def test_basic(self):
        # Backward direction of ErfComplement: ErfComplement(result_var, 0.5) → result_var = erfcinv(0.5)
        # nv
        r = _drive_bwd(ErfComplement, 0.5)
        assert approx(r, sc.erfcinv(0.5))


class TestNormalCdf:
    def test_zero(self):
        # nv
        r = _drive(NormalCdf, 0.0)
        assert approx(r, 0.5)

    def test_one(self):
        # nv
        r = _drive(NormalCdf, 1.0)
        assert approx(r, sc.ndtr(1.0))


class TestNormalCdfInverse:
    def test_half(self):
        # Backward direction of NormalCdf: NormalCdf(result_var, 0.5) → result_var = ndtri(0.5)
        # nv
        r = _drive_bwd(NormalCdf, 0.5)
        assert approx(r, 0.0)

    def test_round_trip(self):
        # nv
        p = 0.975
        x = _drive_bwd(NormalCdf, p)
        back = _drive(NormalCdf, x)
        assert approx(back, p)


# ── Bessel functions ───────────────────────────────────────────────────────

class TestBesselJ:
    def test_order0(self):
        # nv
        r = _drive(BesselJ, 0, 1.0)
        assert approx(r, sc.jn(0, 1.0))

    def test_order1(self):
        # nv
        r = _drive(BesselJ, 1, 2.0)
        assert approx(r, sc.jn(1, 2.0))


class TestBesselY:
    def test_order0(self):
        # nv
        r = _drive(BesselY, 0, 1.0)
        assert approx(r, sc.yn(0, 1.0))


class TestBesselJReal:
    def test_half_order(self):
        # nv
        r = _drive(BesselJReal, 0.5, 2.0)
        assert approx(r, sc.jv(0.5, 2.0))


class TestBesselYReal:
    def test_half_order(self):
        # nv
        r = _drive(BesselYReal, 0.5, 2.0)
        assert approx(r, sc.yv(0.5, 2.0))


class TestBesselK:
    def test_order0(self):
        # nv
        r = _drive(BesselK, 0, 1.0)
        assert approx(r, sc.kn(0, 1.0))


class TestBesselI:
    def test_order0(self):
        # nv
        r = _drive(BesselI, 0, 1.0)
        assert approx(r, sc.iv(0, 1.0))


class TestBesselJZeros:
    def test_first_five_zeros_of_j0(self):
        # nv
        r = _drive(BesselJZeros, 0, 5)
        expected = sc.jn_zeros(0, 5)
        assert np.allclose(r, expected)


class TestSphericalBesselJ:
    def test_arity3_no_derivative(self):
        # nv
        r = _drive(SphericalBesselJ, 0, 1.0)
        assert approx(r, sc.spherical_jn(0, 1.0))

    def test_arity4_with_derivative(self):
        # nv
        r = _drive(SphericalBesselJ, 0, 1.0, True)
        assert approx(r, sc.spherical_jn(0, 1.0, derivative=True))


# ── Elliptic integrals ────────────────────────────────────────────────────

class TestEllipticK:
    def test_zero_modulus(self):
        # nv
        r = _drive(EllipticK, 0.0)
        assert approx(r, math.pi / 2)


class TestEllipticE:
    def test_zero_modulus(self):
        # nv
        r = _drive(EllipticE, 0.0)
        assert approx(r, math.pi / 2)


class TestEllipticKIncomplete:
    def test_basic(self):
        # nv
        r = _drive(EllipticKIncomplete, 0.5, 0.3)
        assert approx(r, sc.ellipkinc(0.5, 0.3))


class TestEllipticEIncomplete:
    def test_basic(self):
        # nv
        r = _drive(EllipticEIncomplete, 0.5, 0.3)
        assert approx(r, sc.ellipeinc(0.5, 0.3))


# ── Hypergeometric ────────────────────────────────────────────────────────

class TestHypergeometric1F1:
    def test_basic(self):
        # nv
        r = _drive(Hypergeometric1F1, 1.0, 2.0, 0.5)
        assert approx(r, sc.hyp1f1(1.0, 2.0, 0.5))


class TestHypergeometric2F1:
    def test_basic(self):
        # nv
        r = _drive(Hypergeometric2F1, 0.5, 0.5, 1.5, 0.25)
        assert approx(r, sc.hyp2f1(0.5, 0.5, 1.5, 0.25))


class TestHypergeometric0F1:
    def test_basic(self):
        # nv
        r = _drive(Hypergeometric0F1, 2.0, 0.5)
        assert approx(r, sc.hyp0f1(2.0, 0.5))


# ── Information theory ────────────────────────────────────────────────────

class TestEntr:
    def test_half(self):
        # nv
        r = _drive(Entr, 0.5)
        assert approx(r, sc.entr(0.5))

    def test_zero(self):
        # nv
        r = _drive(Entr, 0.0)
        assert approx(r, 0.0)


class TestKlDivergence:
    def test_equal_inputs(self):
        # nv
        r = _drive(KlDivergence, 0.5, 0.5)
        assert approx(r, 0.0)

    def test_basic(self):
        # nv
        r = _drive(KlDivergence, 0.25, 0.5)
        assert approx(r, sc.kl_div(0.25, 0.5))


class TestLogSumExp:
    def test_arity2(self):
        # nv
        a = np.array([1.0, 2.0, 3.0])
        r = _drive(LogSumExp, a)
        assert approx(r, sc.logsumexp(a))

    def test_arity5_with_axis(self):
        # nv
        a = np.array([[1.0, 2.0], [3.0, 4.0]])
        r = _drive(LogSumExp, a, 0, None, False)
        expected = sc.logsumexp(a, axis=0, b=None, keepdims=False)
        assert np.allclose(r, expected)


# ── Orthogonal polynomials ─────────────────────────────────────────────────

class TestAssocLegendre:
    def test_basic(self):
        # nv
        r = _drive(AssocLegendre, 0, 1, 0.5)
        assert approx(r, sc.lpmv(0, 1, 0.5))


class TestLegendrePoly:
    def test_p0_is_one(self):
        # nv
        r = _drive(LegendrePoly, 0, 0.5)
        assert approx(r, 1.0)

    def test_p1_is_x(self):
        # nv
        r = _drive(LegendrePoly, 1, 0.5)
        assert approx(r, 0.5)

    def test_p2(self):
        # nv
        r = _drive(LegendrePoly, 2, 0.5)
        assert approx(r, sc.eval_legendre(2, 0.5))


class TestChebyshevT:
    def test_t0_is_one(self):
        # nv
        r = _drive(ChebyshevT, 0, 0.5)
        assert approx(r, 1.0)

    def test_t1_is_x(self):
        # nv
        r = _drive(ChebyshevT, 1, 0.5)
        assert approx(r, 0.5)


class TestChebyshevU:
    def test_u0_is_one(self):
        # nv
        r = _drive(ChebyshevU, 0, 0.5)
        assert approx(r, 1.0)


class TestHermiteH:
    def test_h0_is_one(self):
        # nv
        r = _drive(HermiteH, 0, 1.0)
        assert approx(r, 1.0)

    def test_h1_is_2x(self):
        # nv
        r = _drive(HermiteH, 1, 1.0)
        assert approx(r, 2.0)


class TestGeneralizedLaguerre:
    def test_l0_is_one(self):
        # nv
        r = _drive(GeneralizedLaguerre, 0, 1.0, 0.5)
        assert approx(r, 1.0)


# ── Convenience / misc ────────────────────────────────────────────────────

class TestCubeRoot:
    def test_eight(self):
        # nv
        r = _drive(CubeRoot, 8.0)
        assert approx(r, 2.0)

    def test_negative(self):
        # nv
        r = _drive(CubeRoot, -8.0)
        assert approx(r, sc.cbrt(-8.0))


class TestExp10:
    def test_two(self):
        # nv
        r = _drive(Exp10, 2.0)
        assert approx(r, 100.0)


class TestExp2:
    def test_three(self):
        # nv
        r = _drive(Exp2, 3.0)
        assert approx(r, 8.0)


class TestSigmoid:
    def test_zero_input(self):
        # Backward direction of Logit: Logit(result_var, 0.0) → result_var = expit(0.0)
        # nv
        r = _drive_bwd(Logit, 0.0)
        assert approx(r, 0.5)

    def test_large_input(self):
        # Backward direction of Logit: expit(100.0) ≈ 1.0
        # nv
        r = _drive_bwd(Logit, 100.0)
        assert approx(r, 1.0)

    def test_round_trip_with_logit(self):
        # nv
        x = 0.3
        # expit(x) via backward Logit, then logit(sig) via forward Logit should give back x
        sig = _drive_bwd(Logit, x)
        back = _drive(Logit, sig)
        assert approx(back, x)


class TestLogit:
    def test_half(self):
        # nv
        r = _drive(Logit, 0.5)
        assert approx(r, 0.0)


class TestLambertW:
    def test_arity2(self):
        # nv
        r = _drive(LambertW, 1.0)
        expected = sc.lambertw(1.0, k=0, tol=1e-8)
        assert approx(float(np.real(r)), float(np.real(expected)))

    def test_arity4_k0(self):
        # nv
        r = _drive(LambertW, 1.0, 0, 1e-8)
        expected = sc.lambertw(1.0, k=0, tol=1e-8)
        assert approx(float(np.real(r)), float(np.real(expected)))

    def test_arity4_k_minus1(self):
        # nv
        r = _drive(LambertW, -0.1, -1, 1e-8)
        expected = sc.lambertw(-0.1, k=-1, tol=1e-8)
        assert approx(float(np.real(r)), float(np.real(expected)))


class TestXLogY:
    def test_basic(self):
        # nv
        r = _drive(XLogY, 2.0, 3.0)
        assert approx(r, sc.xlogy(2.0, 3.0))

    def test_zero_x_gives_zero(self):
        # nv
        r = _drive(XLogY, 0.0, 0.0)
        assert approx(r, 0.0)


class TestXLog1pY:
    def test_basic(self):
        # nv
        r = _drive(XLog1pY, 2.0, 3.0)
        assert approx(r, sc.xlog1py(2.0, 3.0))

    def test_zero_x_gives_zero(self):
        # nv
        r = _drive(XLog1pY, 0.0, 0.0)
        assert approx(r, 0.0)


# ── Predicate metadata ─────────────────────────────────────────────────────

class TestPredicateMeta:
    def test_repr(self):
        # nv
        assert "Gamma" in repr(Gamma)

    def test_get_dispatch_callable(self):
        # nv
        assert callable(Gamma._get_dispatch())

    def test_multi_arity_dispatch_is_callable(self):
        # nv
        assert callable(Factorial._get_dispatch())

    def test_unknown_arity_fails(self):
        """Calling Factorial with 4 positional args (arity 4, unregistered) fails."""
        # nv
        trail = Trail()
        result = Var()
        dispatch = Factorial._get_dispatch()
        gen = dispatch(None, None, 5, True, "extra", result, trail)
        items = list(gen)
        assert any(s[1] is DONE for s in items)


# ── Fixture integration ─────────────────────────────────────────────────────

import os
from clausal.logic.solve import call
from clausal.import_hook import _load_module

_FIXTURE_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name):
    path = os.path.join(_FIXTURE_DIR, f"{name}.clausal")
    mod = _load_module(name, path)
    return mod.__dict__["$module"]


def _succeeds(functor, *args, module):
    for _ in call(functor, *args, module=module):
        return True
    return False


class TestScipySpecialFixture:
    """Run Test predicates from tests/fixtures/scipy_special.clausal."""

    @pytest.fixture(autouse=True, scope="class")
    def _setup(self, request):
        request.cls.mod = _load_fixture("scipy_special_tests")

    @pytest.mark.parametrize("name", [
        # Gamma family
        "gamma 5",
        "gamma 0.5 sqrt pi",
        "gammalog 10",
        "gammasign positive",
        "gammasign negative",
        "betalog 2 3",
        "betalog 1 1 is zero",
        "digamma 1",
        "digamma 2",
        "polygamma 0 1",
        "polygamma 1 1",
        # Factorial / Comb / Perm
        "factorial 5 inexact",
        "factorial 5 exact",
        "factorial 0",
        "comb 5 2 inexact",
        "comb 5 2 exact",
        "comb 6 3",
        "perm 5 2",
        "perm 4 4",
        # Error functions
        "erf 0",
        "erf 1",
        "erfc 1",
        "erfc 0 is 1",
        "erfinv 0.5",
        "erfcinv 0.5",
        # Normal CDF
        "normal cdf 0 is 0.5",
        "normal cdf 1",
        "normal cdf inverse 0.5 is 0",
        "normal cdf inverse 0.84",
        # Bessel
        "besselj 0 0",
        "besselj 1 1",
        "bessely 0 1",
        "bessely 1 1",
        "besseljreal 0.5 1",
        "besseljreal 1.5 2",
        "besselk 0 1",
        "besselk 1 1",
        "besseli 0 1",
        "besseli 1 1",
        "besseljzeros 0 first zero",
        "besseljzeros 0 three zeros",
        "spherical besselj 0 at 0 is 1",
        "spherical besselj 1 at 0 is 0",
        # Elliptic
        "elliptic k 0 is pi/2",
        "elliptic k 0.5",
        "elliptic e 0 is pi/2",
        "elliptic e 0.5",
        "elliptic k incomplete",
        "elliptic e incomplete",
        # Hypergeometric
        "hyp1f1 1 2 0.5",
        "hyp1f1 identity at 0",
        "hyp2f1 0.5 0.5 1.5 0.25",
        "hyp2f1 at 0 is 1",
        "hyp0f1 2 0.5",
        "hyp0f1 at 0 is 1",
        # Information theory
        "entr 0.5",
        "entr 1 is 0",
        "kl divergence equal",
        "kl divergence positive",
        "log sum exp scalar 1",
        "log sum exp scalar 0",
        # Orthogonal polynomials
        "assoc legendre m0 v0 x0.5",
        "assoc legendre m0 v1 x0.5",
        "legendre poly 0",
        "legendre poly 1",
        "chebyshev t 0",
        "chebyshev t 1",
        "chebyshev u 0",
        "chebyshev u 1",
        "hermite h 0",
        "hermite h 1",
        "generalized laguerre 0 1 0.5",
        "generalized laguerre 1 1 0",
        # Misc
        "cube root 8",
        "cube root negative",
        "exp10 2",
        "exp10 0 is 1",
        "exp2 3",
        "exp2 0 is 1",
        "sigmoid 0 is 0.5",
        "sigmoid large is 1",
        "logit 0.5 is 0",
        "logit 0.75 positive",
        "lambert w 1",
        "lambert w 0 is 0",
        "xlogy 2 3",
        "xlogy 0 anything is 0",
        "xlog1py 2 3",
        "xlog1py 0 anything is 0",
        "besselyreal 0.5 1",
        "besselyreal 1.5 2",
    ])
    def test_fixture(self, name):
        # nv
        assert _succeeds("Test", name, module=self.mod)
