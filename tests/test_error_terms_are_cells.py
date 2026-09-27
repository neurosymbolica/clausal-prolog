"""Slice 2 of the Compound retirement: an error term is a plain cell.

Every builder in ``clausal.logic.exceptions`` builds ``('error', Formal,
Context)`` with the formal term a cell too (``('type_error', 'atom', 1)``,
``('/', 'foo', 1)``).  ``LogicException.term`` is therefore a cell, read from
Python with ``clausal.cell_functor`` / ``clausal.cell_args`` (ruling R10).

Ruling R11: the second argument of ``error/2`` is ISO ``context(Culprit,
Message)``.  ``Culprit`` is the predicate indicator of the builtin that
raised, ``Message`` the free text; either is a fresh variable when there is
none.  The indicator stays PRINTED in the rendered message.
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
    LogicException, domain_error, error_context, evaluation_error,
    existence_error, instantiation_error, permission_error,
    python_error_term, string_goal_error, system_error, type_error,
)
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, deref
from clausal.terms import Compound, FloorDiv


def _is_unbound(x) -> bool:
    return isinstance(deref(x), Var)


def _no_compound(t) -> bool:
    if isinstance(t, Compound):
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
def test_builder_builds_a_cell_with_an_iso_context(name):
    term = BUILDERS[name]()
    assert type(term) is tuple and cell_functor(term) == "error", term
    assert len(cell_args(term)) == 2
    formal, context = cell_args(term)
    assert type(formal) is tuple or formal == "instantiation_error"
    assert type(context) is tuple and cell_functor(context) == "context"
    assert len(cell_args(context)) == 2
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


# ── R11: the context ─────────────────────────────────────────────────────────

#: (context text a raise site passes, Culprit, Message) -- None = unbound.
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
    ("", None, None),
]


@pytest.mark.parametrize("text,culprit,message", CONTEXT_ROWS,
                         ids=[r[0] or "<empty>" for r in CONTEXT_ROWS])
def test_context_text_becomes_context_culprit_message(text, culprit, message):
    context = instantiation_error(text)[2]
    assert cell_functor(context) == "context"
    got_culprit, got_message = cell_args(context)
    if culprit is None:
        assert _is_unbound(got_culprit), got_culprit
    else:
        assert got_culprit == culprit
    if message is None:
        assert _is_unbound(got_message), got_message
    else:
        assert got_message == message


def test_an_indicator_given_as_the_context_is_the_culprit():
    for pi in (("/", "foo", 1), Compound("/", ("foo", 1))):
        context = instantiation_error(pi)[2]
        assert cell_args(context)[0] is pi
        assert _is_unbound(cell_args(context)[1])


def test_a_built_context_passes_through():
    ctx = error_context(("/", "foo", 1), "why")
    assert ctx == ("context", ("/", "foo", 1), "why")
    assert type_error("atom", 1, ctx)[2] is ctx
    blank = error_context()
    assert _is_unbound(blank[1]) and _is_unbound(blank[2])
    assert deref(blank[1]) is not deref(blank[2])


# ── the rendered message ─────────────────────────────────────────────────────

MESSAGES = [
    (type_error("atom", 1, "atom_length/2"),
     "error(type_error(atom,1),context(atom_length/2,_))"),
    (instantiation_error("atom_length/2"),
     "error(instantiation_error,context(atom_length/2,_))"),
    (existence_error("procedure", ("/", "foo", 1), "foo/1"),
     "error(existence_error(procedure,foo/1),context(foo/1,_))"),
    (domain_error("not_less_than_zero", -1, "atom_length/2"),
     "error(domain_error(not_less_than_zero,-1),context(atom_length/2,_))"),
    (evaluation_error("zero_divisor", "(/)/2"),
     "error(evaluation_error(zero_divisor),context((/)/2,_))"),
    (instantiation_error("solve/1: the goal is unbound"),
     "error(instantiation_error,context(solve/1,'the goal is unbound'))"),
    (type_error("integer", "x"),
     "error(type_error(integer,x),context(_,_))"),
]


@pytest.mark.parametrize("term,expected", MESSAGES,
                         ids=[m[1] for m in MESSAGES])
def test_message_renders_the_context_and_prints_the_indicator(term, expected):
    assert _msg(term) == f"Uncaught logic exception: {expected}"


def test_message_is_deterministic():
    """A fresh variable in every context must not make two raises of the same
    error read differently (a consumer may dedup on the text)."""
    assert _msg(type_error("atom", 1, "atom_length/2")) == _msg(
        type_error("atom", 1, "atom_length/2"))


def test_message_names_shared_variables_and_blanks_singletons():
    x, y = Var(), Var()
    assert _msg(("f", x, y, x)) == "Uncaught logic exception: f(_1,_,_1)"


def test_hint_reads_a_cell_and_a_compound_alike():
    culprit = FloorDiv(left=10000, right=4)
    cell = type_error("number", culprit, "sum_list/2")
    legacy = Compound("error", (Compound("type_error", ("number", culprit)),
                                "sum_list/2"))
    for term in (cell, legacy):
        assert "note: `10000 // 4` is an unevaluated" in str(LogicException(term))


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
c_pi(PI) <- catch(atom_length(1, _), error(_, context(PI, _)), true),
c_pi_name(N, A) <- catch(atom_length(_, _), error(instantiation_error, context('/'(N, A), _)), true),
c_msg(M) <- catch(throw(_), error(instantiation_error, context(_, M)), true),
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
    ("sub", "error(type_error(dict,[2025,1,1]),context([]/2,_))"),
    ("splat", "error(type_error(dict,[2025,1,1]),context('{**}'/1,_))"),
    ("mn", "error(type_error(orderable,[1,a,[2]]),context(min_list/2,_))"),
    ("mx", "error(type_error(orderable,[1,a,[2]]),context(max_list/2,_))"),
    ("al", "error(type_error(atom,1),context(atom_length/2,_))"),
    ("inst", "error(instantiation_error,context(atom_length/2,_))"),
    ("must", "error(domain_error(type,nosuchtype),context(must_be/2,_))"),
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


def test_catch_context_pattern_binds_the_indicator(mod):
    pi = Var()
    assert _answers(mod, ("c_pi", pi), pi) == [(("/", "atom_length", 2),)]
    n, a = Var(), Var()
    assert _answers(mod, ("c_pi_name", n, a), n, a) == [("atom_length", 2)]


def test_catch_context_pattern_binds_the_message(mod):
    m = Var()
    assert _answers(mod, ("c_msg", m), m) == [
        ("the ball is unbound (ISO 7.8.10.3)",)]


@pytest.mark.parametrize("text,expected", [
    ("atom_length/2", "atom_length/2"),
    ("solve/1: the goal is unbound", "solve/1: the goal is unbound"),
    ("clpfd expression", "clpfd expression"),
    ("is/2", "(is)/2"),
    ("", ""),
])
def test_error_context_text_reads_the_context_back(text, expected):
    from clausal.logic.exceptions import error_context_text
    assert error_context_text(type_error("atom", 1, text)) == expected
    assert error_context_text("not an error term") == ""


def test_error_context_text_renders_a_string_message_as_its_text():
    from clausal.logic.cells import chars
    from clausal.logic.exceptions import error_context_message, error_context_text
    term = ("error", "instantiation_error",
            ("context", ("/", "foo", 1), chars("why")))
    assert error_context_text(term) == "foo/1: why"
    assert error_context_message(term) == chars("why")
    assert error_context_message(type_error("atom", 1, "x/1: m")) == "m"
    assert error_context_message(("not", "error")) is None


@pytest.mark.parametrize("text", ["a/b/2", "m:p/2", "reify(lt)/3"])
def test_a_name_with_a_slash_colon_or_paren_is_prose_not_an_indicator(text):
    culprit, message = cell_args(instantiation_error(text)[2])
    assert _is_unbound(culprit)
    assert message == text


def test_a_nested_plain_writeq_inside_a_local_render_keeps_its_own_names():
    from clausal.terms import _WQ_LOCAL_VARS, term_writeq
    v = Var()
    token = _WQ_LOCAL_VARS.set({})
    try:
        inner = term_writeq(("f", v))
    finally:
        _WQ_LOCAL_VARS.reset(token)
    assert "\x00" not in inner and inner.startswith("f(_")
