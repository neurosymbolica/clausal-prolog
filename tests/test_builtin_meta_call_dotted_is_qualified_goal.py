"""A dotted ``lib.p(...)`` passed to a BUILTIN meta-caller runs ``p`` in lib.

``call(lib.mp(X))`` compiled the argument in TERM position, where ruling (a)
makes a dotted call the plain cell ``("mp", X)``, so call/1 looked ``mp/1`` up
in the CALLING module: ``existence_error(procedure, mp/1)`` -- or, worse, the
caller's own ``mp/1`` ran, silently.  The same dotted call in goal position
(``lib.mp(X)``) and inside an inlined control construct (findall/3, once/1,
``not``, forall/2, catch/3, bagof/3) always ran lib's.  The builtin callers
that reached the argument as a TERM -- call/1..8, aggregate_all/3,
time_goal/1,2, phrase/2,3 and maplist & co. -- now receive the qualified goal
``lib:mp(X)`` (``(":", lib, ("mp", X))``), as a user ``-meta_predicate``
callee already did (operator ruling 2026-09-25).

Scryer, the ``.pl`` spelling (``call(sqpm:mp(X))``, ``T = sqpm:mp(X),
call(T)``) answers ``[1, 2]`` for both; so does Clausal's native .pl front end.

Data is untouched: ``T is lib.mp(1)`` is still the plain cell ``("mp", 1)``
(ruling (a)), and a dotted Python attribute is still its value.
"""
from __future__ import annotations

import sys
import textwrap

import pytest

from clausal import cell_args, cell_functor
from clausal.logic.atoms import mint
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk

_LIB = """
    -module(bmqlib, [mp(X), q(A, B), decide(B, V), g(N, L, R)])
    -private([lib_version])
    mp(1),
    mp(2),
    q(A, B) <- (B is A)
    decide(_B_UNUSED, lib_version),
    g(N) >> ([N])
"""

_USER = """
    -module(bmquser, [])
    -import_module(bmqlib)
    -private([caller_version])
    import math
    decide(_B_UNUSED, caller_version),
    same(A, A),
    call1(X) <- call(bmqlib.mp(X))
    call2(B) <- call(bmqlib.q(1), B)
    call2_bare(X) <- call(bmqlib.mp, X)
    call_own(V) <- call(decide(1, V))
    call_lib(V) <- call(bmqlib.decide(1, V))
    agg(N) <- aggregate_all('count', bmqlib.mp(_), N)
    timed(X) <- time_goal(bmqlib.mp(X))
    maplist_partial() <- maplist(bmqlib.q(1), [1, 1])
    phrase_args(L) <- phrase(bmqlib.g(7), L)
    builtin_fallback(L) <- call(bmqlib.numlist(3, L))
    missing() <- call(bmqlib.nosuch(1))
    direct(X) <- bmqlib.mp(X)
    via_findall(L) <- findall(X, bmqlib.mp(X), L)
    via_once(X) <- once(bmqlib.mp(X))
    via_not() <- (not bmqlib.mp(3))
    via_forall() <- forall(bmqlib.mp(X), X > 0)
    data(T) <- (T is bmqlib.mp(1))
    py_attr(X) <- call(same, X, math.pi)
"""


@pytest.fixture(scope="module")
def user(tmp_path_factory):
    from clausal.import_hook import _load_module
    d = tmp_path_factory.mktemp("bmq")
    sys.path.insert(0, str(d))
    mods = {}
    try:
        for name, body in (("bmqlib", _LIB), ("bmquser", _USER)):
            p = d / f"{name}.clausal"
            p.write_text(textwrap.dedent(body).lstrip())
            mods[name] = _load_module(name, str(p))
        yield mods["bmquser"].__dict__["$module"]
    finally:
        sys.path.remove(str(d))
        for name in ("bmqlib", "bmquser"):
            sys.modules.pop(name, None)


def _answers(module, goal, arity=1):
    args = [Var() for _ in range(arity)]
    return [[walk(a) for a in args] for _ in call(goal, *args, module=module)]


@pytest.mark.parametrize("goal, expected", [
    ("call1", [[1], [2]]),
    ("call2", [[1]]),
    ("agg", [[2]]),
    ("timed", [[1], [2]]),
    ("builtin_fallback", [[[1, 2, 3]]]),
])
def test_a_dotted_goal_argument_of_a_builtin_meta_caller_runs_in_its_module(
        user, goal, expected):
    """Each raised existence_error(procedure, ...) in the calling module."""
    assert _answers(user, goal) == expected


def test_maplist_with_a_dotted_partial_closure(user):
    assert _answers(user, "maplist_partial", 0) == [[]]


def test_phrase_with_a_dotted_nonterminal_with_arguments(user):
    assert _answers(user, "phrase_args") == [[[7]]]


def test_the_dotted_name_beats_the_callers_own_predicate(user):
    """Before the fix ``call(bmqlib.decide(1, V))`` SILENTLY ran the caller's
    decide/2; the undotted spelling still does."""
    assert _answers(user, "call_lib") == [["lib_version"]]
    assert _answers(user, "call_own") == [["caller_version"]]


def test_a_missing_owner_predicate_raises_existence_error(user):
    with pytest.raises(LogicException) as exc:
        list(call("missing", module=user))
    formal = cell_args(exc.value.term)[0]
    assert cell_functor(formal) == "existence_error"
    assert cell_args(formal) == (mint("procedure"), ("/", mint("nosuch"), 1))


@pytest.mark.parametrize("goal, arity, expected", [
    ("call2_bare", 1, [[1], [2]]),
    ("direct", 1, [[1], [2]]),
    ("via_findall", 1, [[[1, 2]]]),
    ("via_once", 1, [[1]]),
    ("via_not", 0, [[]]),
    ("via_forall", 0, [[]]),
])
def test_controls_that_already_ran_in_the_owner(user, goal, arity, expected):
    assert _answers(user, goal, arity) == expected


def test_a_dotted_call_in_data_position_is_still_the_plain_cell(user):
    """Ruling (a): unchanged by the fix."""
    assert _answers(user, "data") == [[("mp", 1)]]


def test_a_dotted_python_attribute_is_still_its_value(user):
    import math
    assert _answers(user, "py_attr") == [[math.pi]]
