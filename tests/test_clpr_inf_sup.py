"""Ruling R17 (2026-09-29): CLP(R) ``inf/2`` and ``sup/2``.

Reference: the classic CLP(R) of Holzbaur (the SICStus clpqr library):
``inf(Expr, Inf)`` / ``sup(Expr, Sup)`` compute the infimum / supremum of
``Expr`` in the current store, do not change the store, and FAIL when
``Expr`` is unbounded on that side.  Scryer has no library(clpr).

Clausal's CLP(R) is an interval solver, so the answer is the float bound
propagation has proven (sound, outward-rounded).  The CLP(Q) ``inf/2`` and
``sup/2`` (simplex) answer when no variable of ``Expr`` is a real variable.
Before this, a real variable went to CLP(Q), which knew nothing of it:
``in_real(X, 0.0, 10.0), X >= 2.5, inf(X, I)`` gave ``I = 0``.
"""
import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, call
from clausal.logic.variables import Var

SRC = """\
-private([foo(_), bar])
lower(I) <- (in_real(X, 0.0, 10.0), X >= 2.5, inf(X, I))
upper(S) <- (in_real(X, 0.0, 10.0), in_real(Y, 0.0, 5.0), X + Y == 12.0, sup(X, S))
lower_after(I) <- (in_real(X, 0.0, 10.0), in_real(Y, 0.0, 5.0), X + Y == 12.0, inf(X, I))
unbounded_below() <- (in_real(X), X <= 3.0, inf(X, _))
unbounded_above() <- (in_real(X), X >= 3.0, sup(X, _))
both(I, S) <- (in_real(X, 0.0, 1.0), X >= 0.25, inf(X, I), sup(X, S))
expression(I, S) <- (in_real(X, 1.0, 2.0), inf(2 * X + 1, I), sup(2 * X + 1, S))
nonlinear(I, S) <- (in_real(X, 1.0, 2.0), inf(X * X, I), sup(X * X, S))
store_unchanged(L, H) <- (in_real(X, 0.0, 1.0), inf(X, L), sup(X, H), X == 0.5)
check_bound() <- (in_real(X, 0.0, 1.0), inf(X, 0.0))
check_wrong_bound() <- (in_real(X, 0.0, 1.0), inf(X, 0.5))
rational_path(I) <- (rational(X), X >= 3, inf(X, I))
bad_compound(E, C) <- catch((in_real(X, 0.0, 1.0), inf(foo(X), _)), error(E, C), true)
bad_atom(E, C) <- catch((in_real(X, 0.0, 1.0), sup(X + bar, _)), error(E, C), true)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    path = tmp_path_factory.mktemp("r17") / "r17_clpr_inf_sup.clausal"
    path.write_text(SRC)
    return _load_module("r17_clpr_inf_sup", str(path))


def _answers(mod, name, arity):
    vs = [Var() for _ in range(arity)]
    return [[_deref_walk(v) for v in vs]
            for _ in call(name, *vs, module=mod.__dict__["$module"])]


@pytest.mark.parametrize("pred, arity, expected", [
    ("lower", 1, [[2.5]]),
    ("upper", 1, [[10.0]]),
    # outward rounding: a computed bound can sit one ulp outside
    ("lower_after", 1, [[pytest.approx(7.0, abs=1e-12)]]),   # from X + Y == 12
    ("both", 2, [[0.25, 1.0]]),
    ("expression", 2, [[pytest.approx(3.0, abs=1e-12),
                        pytest.approx(5.0, abs=1e-12)]]),
    ("store_unchanged", 2, [[0.0, 1.0]]),
    ("check_bound", 0, [[]]),
    ("check_wrong_bound", 0, []),
    ("rational_path", 1, [[3]]),          # no real variable: CLP(Q)
])
def test_bounds(mod, pred, arity, expected):
    assert _answers(mod, pred, arity) == expected


@pytest.mark.parametrize("pred", ["unbounded_below", "unbounded_above"])
def test_unbounded_fails(mod, pred):
    assert _answers(mod, pred, 0) == []


def test_nonlinear_bound_is_sound(mod):
    [[lo, hi]] = _answers(mod, "nonlinear", 2)
    assert lo <= 1.0 and 1.0 - lo < 1e-12
    assert hi >= 4.0 and hi - 4.0 < 1e-12


@pytest.mark.parametrize("pred, formal, culprit", [
    ("bad_compound", ("type_error", "evaluable", ("/", "foo", 1)), ("/", "inf", 2)),
    ("bad_atom", ("type_error", "evaluable", ("/", "bar", 0)), ("/", "sup", 2)),
])
def test_non_evaluable_is_a_type_error(mod, pred, formal, culprit):
    assert _answers(mod, pred, 2) == [[formal, culprit]]
