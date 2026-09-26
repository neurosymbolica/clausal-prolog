"""A bare logic variable in goal position is rejected with a clean,
located compile-time error (todo/attvar-in-goal-position.md).

All Clausal logic variables are ``att_var`` instances (``Var = att_var``),
so a bare variable used as a goal reaches ``terms_to_goalop`` as an
``att_var``.  Before the fix it fell through to the generic
``NotImplementedError: terms_to_goalop: goal shape not yet supported
(att_var): att_var(_0)`` internal-shape crash.  The author-facing
behaviour is now a clear, located error naming the predicate and
pointing at ``call/1`` for an intended meta-call.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var
from clausal.logic.compiler.terms_to_goalop import (
    terms_to_goalop,
    BareGoalVariableError,
)


def test_bare_var_goal_raises_dedicated_error_not_notimplemented():
    """A bare ``Var`` in goal position raises ``BareGoalVariableError``."""
    v = Var()
    with pytest.raises(BareGoalVariableError):
        terms_to_goalop([v], db=None)


def test_bare_var_goal_error_is_actionable():
    """The message names 'callable goal' and points at ``call/1``."""
    v = Var()
    with pytest.raises(BareGoalVariableError) as exc:
        terms_to_goalop([v], db=None)
    msg = str(exc.value)
    assert "callable goal" in msg
    assert "call/1" in msg


def test_bare_var_goal_load_error_is_located(tmp_path):
    """Loading a clause that ends in a bare variable goal fails with a
    located error naming the predicate (``go/1``) rather than the
    cryptic internal ``goal shape not yet supported (AttVar)`` crash."""
    from clausal.testing import load_clausal_module

    src = tmp_path / "attvar_min.clausal"
    src.write_text(
        "-double_quotes(atom)\ngo(R) <- (\n"
        "    X == 5,\n"
        "    R == X - 2,\n"
        "    R\n"
        ")\n"
        'test("attvar in goal position") <- (go(R), R == 3)\n'
    )
    with pytest.raises(Exception) as exc:
        load_clausal_module(str(src))
    msg = str(exc.value)
    assert "goal shape not yet supported" not in msg
    assert "callable goal" in msg
    assert "go/1" in msg
