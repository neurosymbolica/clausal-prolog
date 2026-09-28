"""A lambda called with the wrong number of arguments is an ISO error term.

``maplist((S) <- (S > 0), [1, 2], R)`` calls a one-parameter lambda with two
arguments.  It used to escape as Python's ``TypeError: ... takes 3
positional arguments but 4 were given``.  Scryer's library(lambda) is the
model (``\\X^Body``):

* too MANY arguments: call/N adds the surplus to the body goal, so the error
  names the body's principal goal at the extended arity --
  ``maplist(\\S^(S > 0), [1, 2], _)`` is
  ``error(existence_error(procedure, (>)/3), (>)/3)``;
* too FEW: ``existence_error(lambda_parameter, Lambda)``, as Scryer's
  ``call(\\X^Y^true, 1)``.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var

_SRC = """\
-allow_singletons
too_many(R) <- maplist((S) <- (S > 0), [1, 2], R)
too_many_conj(R) <- maplist((S) <- (S > 0, S < 5), [1, 2], R)
too_many_call(R) <- call((S) <- p(S), 1, 2)
too_few(R) <- maplist((S, T, U) <- (S > 0), [1, 2], R)
right(R) <- maplist((S, T) <- (T == S), [1, 2], R)
p(1),
"""


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_lambda_arity_error", path)
    finally:
        os.unlink(path)


def _run(mod, name):
    x = Var()
    try:
        for _ in solve((name, x), mod):
            return "succeeds"
        return "fails"
    except LogicException as exc:
        return render_error_term(exc.term)


@pytest.mark.parametrize("name, want", [
    ("too_many", "error(existence_error(procedure,(>)/3),(>)/3)"),
    ("too_many_conj", "error(existence_error(procedure,(',')/3),(',')/3)"),
    ("too_many_call", "error(existence_error(procedure,p/2),p/2)"),
])
def test_too_many_arguments_extend_the_body_goal(mod, name, want):
    assert _run(mod, name) == want


def test_too_few_arguments_is_a_lambda_parameter_error(mod):
    got = _run(mod, "too_few")
    assert got.startswith("error(existence_error(lambda_parameter,"), got


def test_the_right_arity_still_runs(mod):
    assert _run(mod, "right") == "succeeds"
