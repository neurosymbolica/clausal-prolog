"""Slice 2 of the Compound retirement: an error term is a plain cell.

Every builder in ``clausal.logic.exceptions`` builds ``('error', Formal,
Context)`` with the formal term a cell too (``('type_error', 'atom', 1)``,
``('/', 'foo', 1)``).  ``LogicException.term`` is therefore a cell, read from
Python with ``clausal.cell_functor`` / ``clausal.cell_args`` (ruling R10).

The second argument of ``error/2`` is what Scryer puts there (operator
ruling 2026-09-27, "when Scryer and SWI differ, Scryer"): the indicator of
the builtin that raised, the missing indicator for a missing procedure, an
unbound variable when there is none.  Explanatory prose stays off the term:
it is ``LogicException.message`` and follows the term in ``str()``.
"""

from __future__ import annotations

import os
import tempfile

import pytest

import clausal
import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal import cell_args, cell_functor, make_cell
from clausal.import_hook import _load_module
from clausal.logic.atoms import mint
from clausal.logic.exceptions import (
    LogicException, domain_error, error_prose, evaluation_error,
    existence_error, instantiation_error, permission_error,
    python_error_term, string_goal_error, system_error, type_error,
)
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, deref
from clausal.terms import FloorDiv


def _is_unbound(x) -> bool:
    return isinstance(deref(x), Var)


def _no_compound(t) -> bool:
    """No class-shaped compound (a ``functor``/``args`` object, the retired
    ``Compound``'s shape) anywhere in *t*: every compound is a cell."""
    if hasattr(t, "functor") and hasattr(t, "args"):
        return False
    if type(t) in (tuple, list):
        return all(_no_compound(a) for a in t)
    return True


def _msg(term) -> str:
    return str(LogicException(term)).split("\n", 1)[0]


# ── R10: the accessors are public ────────────────────────────────────────────


def test_accessors_are_exported_from_clausal():
    for name in ("cell_functor", "cell_args", "make_cell"):
        assert name in clausal.__all__
        assert callable(getattr(clausal, name))
    assert make_cell("f", 1, 2) == ("f", 1, 2)
    assert cell_functor(("f", 1, 2)) == "f"
    assert cell_args(("f", 1, 2)) == (1, 2)


# ── every builder builds a cell ──────────────────────────────────────────────


BUILDERS = {
    "type_error": lambda: type_error("atom", 1, "atom_length/2"),
    "instantiation_error": lambda: instantiation_error("atom_length/2"),
    "system_error": lambda: system_error("units_mismatch", "units/2"),
    "existence_error": lambda: existence_error(
        "procedure", ("/", mint("foo"), 1), "foo/1"),
    "permission_error": lambda: permission_error(
        "modify", "static_procedure", ("/", mint("p"), 1), "assertz/1"),
    "domain_error": lambda: domain_error("not_less_than_zero", -1,
                                         "atom_length/2"),
    "evaluation_error": lambda: evaluation_error("zero_divisor", "(/)/2"),
    "string_goal_error": lambda: string_goal_error("foo", 1, "call/2"),
    "no_context": lambda: type_error("integer", "x"),
}


@pytest.mark.parametrize("name", list(BUILDERS))
def test_builder_builds_a_cell(name):
    term = BUILDERS[name]()
    assert type(term) is tuple and cell_functor(term) == "error", term
    assert len(cell_args(term)) == 2
    formal, context = cell_args(term)
    assert type(formal) is tuple or formal == "instantiation_error"
    assert _is_unbound(context) or (
        type(context) is tuple and cell_functor(context) == "/")
    assert _no_compound(term), term


def test_formal_terms_are_the_documented_cells():
    assert type_error("atom", 1, "x/1")[1] == ("type_error", "atom", 1)
    assert instantiation_error("x/1")[1] == "instantiation_error"
    assert existence_error("procedure", ("/", "foo", 1))[1] == (
        "existence_error", "procedure", ("/", "foo", 1))
    assert evaluation_error("zero_divisor")[1] == (
        "evaluation_error", "zero_divisor")
    assert string_goal_error("", 0, "solve/1")[1] == (
        "existence_error", "procedure", ("/", mint("[]"), 0))
    assert string_goal_error("ab", 1, "call/2")[1] == (
        "existence_error", "procedure", ("/", ".", 3))


def test_python_error_term_is_a_cell():
    term = python_error_term(ValueError("bad"))
    assert term == ("ValueError", "bad")


# ── the second argument, and the prose ───────────────────────────────────────

#: (context text a raise site passes, second argument, prose) -- None for the
#: second argument = an unbound variable; None for prose = no prose.
CONTEXT_ROWS = [
    ("atom_length/2", ("/", "atom_length", 2), None),
    ("is/2", ("/", "is", 2), None),
    ("(is)/2", ("/", "is", 2), None),
    ("(/)/2", ("/", "/", 2), None),
    ("(==)/2", ("/", "==", 2), None),
    ("[]/2", ("/", mint("[]"), 2), None),
    ("{**}/1", ("/", "{**}", 1), None),
    ("py.json.parse/3", ("/", "py.json.parse", 3), None),
    ("solve/1: the goal is unbound", ("/", "solve", 1), "the goal is unbound"),
    ("throw/1: the ball is unbound (ISO 7.8.10.3)", ("/", "throw", 1),
     "the ball is unbound (ISO 7.8.10.3)"),
    ("clpfd expression", None, "clpfd expression"),
    ("py.re pattern", None, "py.re pattern"),
    ("a/b/2", None, "a/b/2"),
    ("m:p/2", None, "m:p/2"),
    ("reify(lt)/3", None, "reify(lt)/3"),
    ("", None, None),
]


@pytest.mark.parametrize("text,second,prose", CONTEXT_ROWS,
                         ids=[r[0] or "<empty>" for r in CONTEXT_ROWS])
def test_context_text_splits_into_indicator_and_prose(text, second, prose):
    term = instantiation_error(text)
    got = cell_args(term)[1]
    if second is None:
        assert _is_unbound(got), got
    else:
        assert got == second
    assert error_prose(term) == prose
    assert LogicException(term).message == prose


def test_an_indicator_given_as_the_context_is_the_second_argument():
    pi = ("/", "foo", 1)
    assert cell_args(instantiation_error(pi))[1] is pi


def test_a_missing_procedure_names_itself_as_scryer_does():
    """Scryer: ``call(nosuch, 1)`` -> ``error(existence_error(procedure,
    nosuch/1),nosuch/1)``, whichever builtin found it missing."""
    pi = ("/", "nosuch", 1)
    term = existence_error("procedure", pi, "call/2: no procedure nosuch/1")
    assert cell_args(term)[1] is pi
    assert error_prose(term) == "call/2: no procedure nosuch/1"
    term = existence_error("procedure", pi, "nosuch/1: why")
    assert error_prose(term) == "why"
    assert error_prose(existence_error("procedure", pi, "nosuch/1")) is None


def test_explicit_message_overrides_and_prose_follows_the_term():
    exc = LogicException(instantiation_error("solve/1: why"))
    assert str(exc) == "Uncaught logic exception: error(instantiation_error,solve/1): why"
    exc = LogicException(("error", "instantiation_error", ("/", "f", 1)), "given")
    assert exc.message == "given"
    assert str(exc).endswith("f/1): given")
    assert LogicException("oops").message is None


# ── the rendered message ─────────────────────────────────────────────────────

#: Built lazily: a builder records its prose for the exception about to
#: carry the term, in a bounded table, so a term built at import time and
#: raised much later is not what raise sites do.
MESSAGES = [
    (lambda: type_error("atom", 1, "atom_length/2"),
     "error(type_error(atom,1),atom_length/2)"),
    (lambda: instantiation_error("atom_length/2"),
     "error(instantiation_error,atom_length/2)"),
    (lambda: existence_error("procedure", ("/", "foo", 1), "foo/1"),
     "error(existence_error(procedure,foo/1),foo/1)"),
    (lambda: domain_error("not_less_than_zero", -1, "atom_length/2"),
     "error(domain_error(not_less_than_zero,-1),atom_length/2)"),
    (lambda: evaluation_error("zero_divisor", "(/)/2"),
     "error(evaluation_error(zero_divisor),(/)/2)"),
    (lambda: instantiation_error("solve/1: the goal is unbound"),
     "error(instantiation_error,solve/1): the goal is unbound"),
    (lambda: type_error("integer", "x"), "error(type_error(integer,x),_)"),
    (lambda: type_error("integer", "x", "clpfd expression"),
     "error(type_error(integer,x),_): clpfd expression"),
]


@pytest.mark.parametrize("build,expected", MESSAGES,
                         ids=[m[1] for m in MESSAGES])
def test_message_is_scryers_term_then_the_prose(build, expected):
    assert _msg(build()) == f"Uncaught logic exception: {expected}"


def test_message_is_deterministic():
    """A fresh variable in the second argument must not make two raises of
    the same error read differently (a consumer may dedup on the text)."""
    assert _msg(type_error("atom", 1, "x")) == _msg(type_error("atom", 1, "x"))


def test_message_names_shared_variables_and_blanks_singletons():
    x, y = Var(), Var()
    assert _msg(("f", x, y, x)) == "Uncaught logic exception: f(_1,_,_1)"


def test_hint_reads_a_cell():
    culprit = FloorDiv(left=10000, right=4)
    cell = type_error("number", culprit, "sum_list/2")
    assert "note: `10000 // 4` is an unevaluated" in str(LogicException(cell))


# ── real raises, from source ─────────────────────────────────────────────────

_SRC = r'''
-allow_singletons
-private([a, instantiation_error, nosuchtype])
sub(X) <- (L is [2025, 1, 1], X is L[0]),
splat(D) <- (L is [2025, 1, 1], D is {**L, "k": 1}),
mn(X) <- min_list([1, a, [2]], X),
mx(X) <- max_list([1, a, [2]], X),
al(N) <- atom_length(1, N),
inst(N) <- atom_length(_, N),
must(X) <- must_be(nosuchtype, 1),

c_formal(T, V) <- catch(atom_length(1, _), error(type_error(T, V), _), true),
c_pi(PI) <- catch(atom_length(1, _), error(_, PI), true),
c_pi_name(N, A) <- catch(atom_length(_, _), error(instantiation_error, '/'(N, A)), true),
'''


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_error_terms_are_cells_mod", path)
    finally:
        os.unlink(path)


def _raise(mod, name) -> LogicException:
    with pytest.raises(LogicException) as info:
        list(solve((name, Var()), mod))
    return info.value


#: The strings the downstream advice selector reads: the indicator is printed.
RAISED = [
    ("sub", "error(type_error(dict,[2025,1,1]),[]/2)"),
    ("splat", "error(type_error(dict,[2025,1,1]),'{**}'/1)"),
    ("mn", "error(type_error(orderable,[1,a,[2]]),min_list/2)"),
    ("mx", "error(type_error(orderable,[1,a,[2]]),max_list/2)"),
    ("al", "error(type_error(atom,1),atom_length/2)"),
    ("inst", "error(instantiation_error,atom_length/2)"),
    ("must", "error(domain_error(type,nosuchtype),must_be/2)"),
]


@pytest.mark.parametrize("name,expected", RAISED, ids=[r[0] for r in RAISED])
def test_engine_raise_is_a_cell_and_renders(mod, name, expected):
    exc = _raise(mod, name)
    assert type(exc.term) is tuple and _no_compound(exc.term)
    assert str(exc) == f"Uncaught logic exception: {expected}"


def _answers(mod, goal, *vs):
    return [tuple(_deref_walk(v) for v in vs) for _ in solve(goal, mod)]


def test_catch_formal_pattern_still_matches(mod):
    t, v = Var(), Var()
    assert _answers(mod, ("c_formal", t, v), t, v) == [("atom", 1)]


def test_catch_binds_the_indicator_as_the_second_argument(mod):
    pi = Var()
    assert _answers(mod, ("c_pi", pi), pi) == [(("/", "atom_length", 2),)]
    n, a = Var(), Var()
    assert _answers(mod, ("c_pi_name", n, a), n, a) == [("atom_length", 2)]


def test_a_rethrown_builder_ball_keeps_its_prose():
    """``catch(G, E, throw(E))`` rebuilds the exception from a COPY of the
    ball; the prose, which is not on the term, follows it."""
    ball = instantiation_error("throw/1: the ball is unbound (ISO 7.8.10.3)")
    from clausal.logic.compiler.globals_env import _throw_ball
    assert _throw_ball(ball).message == "the ball is unbound (ISO 7.8.10.3)"


@pytest.mark.parametrize("text", ["a/b/2", "m:p/2", "reify(lt)/3"])
def test_a_name_with_a_slash_colon_or_paren_is_prose_not_an_indicator(text):
    term = instantiation_error(text)
    assert _is_unbound(cell_args(term)[1])
    assert error_prose(term) == text


def test_a_nested_plain_writeq_inside_a_local_render_keeps_its_own_names():
    from clausal.terms import _WQ_LOCAL_VARS, term_writeq
    v = Var()
    token = _WQ_LOCAL_VARS.set({})
    try:
        inner = term_writeq(("f", v))
    finally:
        _WQ_LOCAL_VARS.reset(token)
    assert "\x00" not in inner and inner.startswith("f(_")


def test_prose_survives_catch_and_rethrow_twice():
    """``catch(catch(catch(G, E, throw(E)), E2, throw(E2)), E3, true)``: each
    throw/1 raises a copy of the ball; the prose follows every copy."""
    from clausal.logic.compiler.globals_env import _throw_ball
    first = LogicException(instantiation_error("solve/1: the goal is unbound"))
    second = _throw_ball(first.term)
    third = _throw_ball(second.term)
    assert first.message == second.message == third.message == "the goal is unbound"


def test_a_string_goal_error_without_a_context_has_no_leading_separator():
    assert not error_prose(string_goal_error("ab", 0)).startswith(":")


def test_a_ratio_is_prose_and_an_explicit_procedure_context_is_kept():
    term = instantiation_error("1/2: ratio must be reduced")
    assert _is_unbound(cell_args(term)[1])
    ctx = ("/", "call", 2)
    assert cell_args(existence_error("procedure", ("/", "f", 1), ctx))[1] is ctx
