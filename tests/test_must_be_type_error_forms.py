"""must_be/2 and can_be/2 type-argument errors, as Scryer's library(error).

ISO is silent on library(error), so Scryer is the reference.  An unknown or
non-atom TYPE is ``type_error(type, Type)`` (not ``domain_error``), and it is
checked before the term, so ``must_be(foo, _)`` is a type error, not an
instantiation error.  An unbound Type is ``instantiation_error``.
"""

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.testing import load_clausal_module

_PL = """\
unk :- must_be(foo, 1).
unk_unbound_term :- must_be(foo, _).
unbound_type :- must_be(_, 1).
int_type :- must_be(1, 1).
compound_type :- must_be(between(1, 3), 5).
bad_term :- must_be(integer, a).
unbound_term :- must_be(integer, _).
cb_unk :- can_be(foo, 1).
cb_unk_unbound_term :- can_be(foo, _).
cb_int_type :- can_be(1, 1).
cb_unbound_type :- can_be(_, 1).
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("must_be_forms") / "must_be_forms.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


def _outcome(mod, goal):
    try:
        return len(list(solve(goal, mod)))
    except LogicException as e:
        return str(e).split("exception: ", 1)[-1]


@pytest.mark.parametrize("goal, expected", [
    ("unk", "error(type_error(type,foo),must_be/2)"),
    ("unk_unbound_term", "error(type_error(type,foo),must_be/2)"),
    ("unbound_type", "error(instantiation_error,must_be/2)"),
    ("int_type", "error(type_error(type,1),must_be/2)"),
    ("compound_type", "error(type_error(type,between(1,3)),must_be/2)"),
    ("bad_term", "error(type_error(integer,a),must_be/2)"),
    ("unbound_term", "error(instantiation_error,must_be/2)"),
    ("cb_unk", "error(type_error(type,foo),can_be/2)"),
    ("cb_unk_unbound_term", "error(type_error(type,foo),can_be/2)"),
    ("cb_int_type", "error(type_error(type,1),can_be/2)"),
    ("cb_unbound_type", "error(instantiation_error,can_be/2)"),
])
def test_type_argument_errors(mod, goal, expected):
    assert _outcome(mod, goal) == expected
