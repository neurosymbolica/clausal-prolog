"""``pi`` and ``e`` are builtins only in ARITHMETIC position (ruling Q16,
narrowed 2026-09-28).

In an evaluated expression -- ``'is'(X, pi)``, ``eval_(2 * e, X)``, a
comparison operand, an evaluable functor's argument -- they need no
declaration.  In a data position (``f(e)``, ``T is e``, a fact argument) they
are ordinary atoms, which a strict module must declare.  At run time,
evaluation reads the atom as ISO does: ``T is e, 'is'(X, T)`` binds T to the
atom ``e`` and X to 2.718... (Scryer: ``T = e, X is T``), and a CLP post
refuses it as clpz does (Scryer: ``X #= pi*2`` is
domain_error(clpz_expression, pi)).
"""

from __future__ import annotations

import math
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref
from tests._suffix import SEAM

_counter = iter(range(10_000))


def _load(src):
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w",
                                     delete=False) as f:
        f.write("-allow_singletons\n" + src)
        path = f.name
    try:
        return _load_module(f"_pi_e_pos_{next(_counter)}", path)
    finally:
        os.unlink(path)


def _first(mod, name, n=1):
    vs = [Var() for _ in range(n)]
    try:
        for _ in solve((name, *vs), mod):
            got = tuple(deref(v) for v in vs)
            return got[0] if n == 1 else got
    except LogicException as exc:
        return render_error_term(exc.term)
    return "fails"


@pytest.fixture(scope="module")
def arith():
    # a STRICT module with no declaration of pi or e
    return _load(
        "is_pi(X) <- 'is'(X, pi)\n"
        "eval_e(X) <- eval_(2 * e, X)\n"
        "nested(X) <- 'is'(X, sin(pi / 2))\n"
        "compare(X) <- ('<'(3, pi), X is 1)\n"
        "power(X) <- 'is'(X, '**'(e, 2))\n"
        "clp(X) <- (X == pi * 2)\n")


@pytest.mark.parametrize("name, want", [
    ("is_pi", math.pi), ("eval_e", 2 * math.e), ("nested", 1.0),
    ("compare", 1), ("power", 7.3890560989306495),
])
def test_arithmetic_position_needs_no_declaration(arith, name, want):
    assert _first(arith, name) == want


def test_a_clp_post_refuses_the_constant_as_clpz_does(arith):
    assert _first(arith, "clp").startswith(
        "error(domain_error(clpz_expression,pi),")


@pytest.mark.parametrize("src", [
    "d(X) <- (X is f(e))\n-private([f(_)])\n",
    "d(X) <- (X is e)\n",
    "d(pi),\n",
])
def test_a_data_position_needs_a_declaration(src):
    with pytest.raises(NameError, match="undeclared atom"):
        _load(src)


def test_declared_data_stays_the_atom_and_evaluates_as_iso():
    mod = _load("-private([e, f(_)])\n"
                "d(X) <- (X is f(e))\n"
                "t(T, X) <- (T is e, 'is'(X, T))\n")
    assert _first(mod, "d") == ("f", "e")
    assert _first(mod, "t", 2) == ("e", math.e)
