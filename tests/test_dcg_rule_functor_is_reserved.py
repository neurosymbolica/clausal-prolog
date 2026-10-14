"""``(-->)/2`` is reserved: the database builtins refuse it.

Ulrich Neumerkel's phrase/2,3 conformity table
(https://www.complang.tuwien.ac.at/ulrich/iso-prolog/phrase, rows 24-26,
expectations from the WG17 DCG draft 8.18.1.3)::

    asserta((a-->b)).    permission_error(modify,static_procedure,(-->)/2)
    clause((a-->b),B).   permission_error(access,private_procedure,(-->)/2)
    (X-->Y).             existence_error(procedure,(-->)/2)

A ``-->`` term is a grammar rule, not a clause: asserting it untranslated
stored a fact of ``(-->)/2`` (with ``assert_creates_dynamic`` on, as in every
``.pl`` file), which ``clause/2`` and a bare ``(X-->Y)`` goal then answered.
retract/1 and retractall/1 share assert's refusal (they used to remove that
fact).  Calling ``(-->)/2`` as a goal is untouched: no such procedure.

No row on the page covers retract/1 or retractall/1 of ``(-->)/2`` directly
-- this follows from row 24 (asserta's refusal) plus ISO 8.9.3.3 c (a
static procedure cannot be retracted), the same way ``_refuse_control_construct``
already covers ``retract((a,b))``.  The local clean Scryer build (not a
WG17-measured row) differs here: its ``retract/1`` just fails on
``(-->)/2`` rather than raising, and its ``retractall/1`` succeeds
silently -- the same divergence it has for an ordinary control construct
like ``,``/2 (see ``_refuse_control_construct``'s docstring).
"""
import pytest

from clausal.logic.database import Module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import solve
from clausal.logic.variables import Var

DCG = "-->"
PI = ("/", DCG, 2)


@pytest.fixture(params=["flag_on", "flag_off"])
def mod(request):
    m = Module(f"dcg_reserved_{request.param}")
    if request.param == "flag_on":
        list(solve(("set_prolog_flag", "assert_creates_dynamic", "true"), m))
    return m


def _err(mod, goal):
    with pytest.raises(LogicException) as info:
        list(solve(goal, mod))
    return info.value.term[1]


@pytest.mark.parametrize("name", ["asserta", "assertz"])
def test_assert_of_a_grammar_rule_is_a_permission_error(mod, name):
    assert _err(mod, (name, (DCG, "a", "b"))) == (
        "permission_error", "modify", "static_procedure", PI)


@pytest.mark.parametrize("name", ["asserta", "assertz"])
def test_assert_of_a_grammar_rule_with_a_neck_is_refused_too(mod, name):
    assert _err(mod, (name, (":-", (DCG, "a", "b"), "true"))) == (
        "permission_error", "modify", "static_procedure", PI)


@pytest.mark.parametrize("name", ["retract", "retractall"])
def test_retract_of_a_grammar_rule_is_a_permission_error(mod, name):
    assert _err(mod, (name, (DCG, "a", "b"))) == (
        "permission_error", "modify", "static_procedure", PI)


def test_clause_of_a_grammar_rule_is_a_permission_error(mod):
    assert _err(mod, ("clause", (DCG, "a", "b"), Var())) == (
        "permission_error", "access", "private_procedure", PI)


def test_a_refused_assert_leaves_nothing_to_call(mod):
    with pytest.raises(LogicException):
        list(solve(("asserta", (DCG, "a", "b")), mod))
    assert _err(mod, (DCG, Var(), Var())) == ("existence_error", "procedure", PI)


def test_a_bare_grammar_rule_goal_is_still_an_existence_error(mod):
    """Must-not-regress (row 26): the refusal is the database builtins',
    not call/1's."""
    assert _err(mod, (DCG, Var(), Var())) == ("existence_error", "procedure", PI)


def test_an_ordinary_fact_still_asserts_with_the_flag_on():
    """Control: the reservation is (-->)/2 only."""
    m = Module("dcg_reserved_control")
    list(solve(("set_prolog_flag", "assert_creates_dynamic", "true"), m))
    list(solve(("asserta", ("arrow", "a", "b")), m))
    assert len(list(solve(("clause", ("arrow", "a", "b"), "true"), m))) == 1
