"""must_be(list, _) and can_be(list, _) on a partial list, as ISO and Scryer.

A partial list (``[a|_]``) is not yet known not to be a list:
``must_be(list, [a|_])`` raises ``instantiation_error`` and
``can_be(list, [a|_])`` succeeds.  ``type_error(list, _)`` is for a term
that can never become a list (``[a|b]``, ``foo``).  ``is_list/1`` stays a
plain failure.  Every expected answer below is Scryer's.
"""

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.testing import load_clausal_module

_PL = """\
mb_partial :- must_be(list, [a|_]).
mb_improper :- must_be(list, [a|b]).
mb_proper :- must_be(list, [a, b]).
mb_atom :- must_be(list, foo).
cb_partial :- can_be(list, [a|_]).
cb_improper :- can_be(list, [a|b]).
il_partial :- is_list([a|_]).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("must_be") / "must_be.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


def _outcome(mod, goal):
    try:
        return len(list(solve(goal, mod)))
    except LogicException as e:
        return str(e).split("exception: ", 1)[-1]


@pytest.mark.parametrize("goal, expected", [
    ("mb_partial", "error(instantiation_error,must_be/2)"),
    ("mb_improper", "error(type_error(list,[a|b]),must_be/2)"),
    ("mb_proper", 1),
    ("mb_atom", "error(type_error(list,foo),must_be/2)"),
    ("cb_partial", 1),
    ("cb_improper", "error(type_error(list,[a|b]),can_be/2)"),
    ("il_partial", 0),
])
def test_partial_list(mod, goal, expected):
    assert _outcome(mod, goal) == expected
