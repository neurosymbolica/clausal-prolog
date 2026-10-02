"""Prolog flags (ISO 13211-1 7.11, 8.17) and the ``assert_creates_dynamic``
flag -- the 2026-09-28 "API and flags" ruling.

ISO decides the error terms; Scryer is the oracle for behaviour where the
two agree, and each row where Scryer differs says so and pins Scryer's
answer beside ours (``test_scryer_oracle``).  Scryer, measured on the local
build with no flags touched::

    current_prolog_flag(bounded, X).        X = false.
    current_prolog_flag(max_integer, X).    false.        (unbounded)
    current_prolog_flag(max_arity, X).      X = 255.
    current_prolog_flag(unknown, X).        X = error.
    current_prolog_flag(double_quotes, X).  X = chars.
    set_prolog_flag(X, 1).                  instantiation_error
    set_prolog_flag(1, a).                  type_error(atom,1)
    set_prolog_flag(nosuch, 1).             domain_error(prolog_flag,nosuch)
    set_prolog_flag(double_quotes, bogus).  domain_error(flag_value,double_quotes+bogus)
    set_prolog_flag(max_arity, 5).          domain_error(prolog_flag,max_arity)   <- ISO: permission_error
    set_prolog_flag(unknown, bogus).        domain_error(prolog_flag,unknown)     <- ISO: domain_error(flag_value,...)
    current_prolog_flag(debug, X).          domain_error(prolog_flag,debug)       <- Scryer lacks debug
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap

import pytest

from clausal import cell_args, cell_functor
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var

from .conftest import SCRYER, run_scryer
from tests._suffix import SEAM


@pytest.fixture(autouse=True)
def _tree_under_test():
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__


@pytest.fixture(autouse=True)
def _restore_process_flags():
    """``debug`` is process-wide: put it back after every test."""
    from clausal.logic.builtins import flags
    saved = dict(flags._PROCESS)
    yield
    flags._PROCESS.clear()
    flags._PROCESS.update(saved)


def _load(tmp_path, monkeypatch, name, src, ext=SEAM.lstrip(".")):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / f"{name}.{ext}"
    path.write_text(textwrap.dedent(src))
    sys.modules.pop(name, None)
    if ext == "pl":
        return _load_prolog_module(name, str(path))
    return _load_module(name, str(path))


def _lm(mod):
    return mod.__dict__["$module"]


def _answers(goal, lm, *slots):
    return [tuple(_deref_walk(s) for s in slots) for _ in solve(goal, lm, Trail())]


def _formal(goal, lm):
    with pytest.raises(LogicException) as info:
        list(solve(goal, lm, Trail()))
    term = _deref_walk(info.value.term)
    assert cell_functor(term) == "error", term
    return cell_args(term)[0], cell_args(term)[1]


@pytest.fixture
def plain(tmp_path, monkeypatch):
    return _lm(_load(tmp_path, monkeypatch, "flags_plain", "x(1),\n"))


# ── current_prolog_flag/2: the values ────────────────────────────────────────


@pytest.mark.parametrize("flag, value", [
    ("bounded", False),                       # Scryer: false
    ("integer_rounding_function", "toward_zero"),
    ("char_conversion", "off"),
    ("debug", "off"),
    ("max_arity", "unbounded"),               # Scryer: 255
    ("unknown", "error"),                     # Scryer: error
    ("double_quotes", "chars"),               # Scryer: chars
    ("assert_creates_dynamic", False),
])
def test_the_value_of_each_flag(plain, flag, value):
    V = Var()
    assert _answers(("current_prolog_flag", flag, V), plain, V) == [(value,)]


@pytest.mark.parametrize("flag", ["max_integer", "min_integer"])
def test_max_and_min_integer_have_no_value(plain, flag):
    # Integers are unbounded; Scryer: current_prolog_flag(max_integer, X) fails.
    assert _answers(("current_prolog_flag", flag, Var()), plain) == []


def test_an_unbound_flag_enumerates_every_flag_with_a_value(plain):
    F, V = Var(), Var()
    got = dict(_answers(("current_prolog_flag", F, V), plain, F, V))
    assert set(got) == {"bounded", "integer_rounding_function",
                        "char_conversion", "debug", "max_arity", "unknown",
                        "double_quotes", "assert_creates_dynamic",
                        "require_end_module"}


# ── the ISO errors (8.17.1.3, 8.17.2.3) ──────────────────────────────────────


SET_ERRORS = [
    # (Flag, Value, ISO formal)
    (Var(), 1, "instantiation_error"),
    ("unknown", Var(), "instantiation_error"),
    (1, "a", ("type_error", "atom", 1)),
    ("nosuch", 1, ("domain_error", "prolog_flag", "nosuch")),
    ("double_quotes", "bogus", ("domain_error", "flag_value", ("+", "double_quotes", "bogus"))),
    ("unknown", "bogus", ("domain_error", "flag_value", ("+", "unknown", "bogus"))),
    ("debug", "bogus", ("domain_error", "flag_value", ("+", "debug", "bogus"))),
    ("bounded", 7, ("domain_error", "flag_value", ("+", "bounded", 7))),
    ("assert_creates_dynamic", "yes",
     ("domain_error", "flag_value", ("+", "assert_creates_dynamic", "yes"))),
    # read-only flags, an admissible value
    ("bounded", True, ("permission_error", "modify", "flag", "bounded")),
    ("max_arity", 5, ("permission_error", "modify", "flag", "max_arity")),
    ("max_integer", 5, ("permission_error", "modify", "flag", "max_integer")),
    ("integer_rounding_function", "down",
     ("permission_error", "modify", "flag", "integer_rounding_function")),
    # an ISO value this engine does not implement
    ("unknown", "fail", ("permission_error", "modify", "flag", "unknown")),
    ("unknown", "warning", ("permission_error", "modify", "flag", "unknown")),
    ("char_conversion", "on", ("permission_error", "modify", "flag", "char_conversion")),
    # double_quotes is fixed when the module is compiled: never as a goal
    ("double_quotes", "atom", ("permission_error", "modify", "flag", "double_quotes")),
    ("double_quotes", "codes", ("permission_error", "modify", "flag", "double_quotes")),
]


@pytest.mark.parametrize("flag, value, formal", SET_ERRORS,
                         ids=[f"{f}={v}" for f, v, _ in SET_ERRORS])
def test_set_prolog_flag_errors(plain, flag, value, formal):
    got, context = _formal(("set_prolog_flag", flag, value), plain)
    assert got == formal
    assert context == ("/", "set_prolog_flag", 2)


@pytest.mark.parametrize("flag, formal", [
    (1, ("type_error", "atom", 1)),
    ("nosuch", ("domain_error", "prolog_flag", "nosuch")),
])
def test_current_prolog_flag_errors(plain, flag, formal):
    got, context = _formal(("current_prolog_flag", flag, Var()), plain)
    assert got == formal
    assert context == ("/", "current_prolog_flag", 2)


@pytest.mark.parametrize("flag, value", [
    ("unknown", "error"), ("char_conversion", "off"), ("debug", "on"),
    ("debug", "off"),
])
def test_the_settable_values_are_accepted(plain, flag, value):
    V = Var()
    assert _answers(("set_prolog_flag", flag, value), plain) == [()]
    assert _answers(("current_prolog_flag", flag, V), plain, V) == [(value,)]


# ── module scoping ──────────────────────────────────────────────────────────


def test_a_runtime_set_affects_only_the_calling_module(tmp_path, monkeypatch):
    a = _lm(_load(tmp_path, monkeypatch, "flags_mod_a", "x(1),\n"))
    b = _lm(_load(tmp_path, monkeypatch, "flags_mod_b", "x(1),\n"))
    assert _answers(("set_prolog_flag", "assert_creates_dynamic", True), a) == [()]
    V = Var()
    assert _answers(("current_prolog_flag", "assert_creates_dynamic", V), a, V) == [(True,)]
    assert _answers(("current_prolog_flag", "assert_creates_dynamic", V), b, V) == [(False,)]
    # and it governs asserts in THAT module only
    assert _answers(("assertz", ("flags_new_a", 1)), a) == [()]
    got, _ = _formal(("assertz", ("flags_new_b", 1)), b)
    assert got == ("permission_error", "modify", "static_procedure",
                   ("/", "flags_new_b", 1))


def test_a_goal_in_source_sets_the_flag_of_its_own_module(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "flags_goal", """
        on() <- set_prolog_flag('assert_creates_dynamic', true)
        add(X) <- assertz(flags_goal_new(X))
    """)
    lm = _lm(mod)
    with pytest.raises(LogicException):
        list(solve(("add", 1), lm, Trail()))
    assert _answers("on", lm) == [()]
    assert _answers(("add", 2), lm) == [()]
    X = Var()
    assert _answers(("flags_goal_new", X), lm, X) == [(2,)]


def test_the_directive_sets_the_flag_for_its_module(tmp_path, monkeypatch):
    lm = _lm(_load(tmp_path, monkeypatch, "flags_dir", """
        -set_prolog_flag(assert_creates_dynamic, true)
        x(1),
    """))
    V = Var()
    assert _answers(("current_prolog_flag", "assert_creates_dynamic", V), lm, V) == [(True,)]


@pytest.mark.parametrize("directive, formal", [
    ("-set_prolog_flag(unknown, fail)", "permission_error(modify,flag,unknown)"),
    ("-set_prolog_flag(unknown, bogus)", "domain_error(flag_value,unknown+bogus)"),
    ("-set_prolog_flag(bounded, true)", "permission_error(modify,flag,bounded)"),
    ("-set_prolog_flag(nosuch, 1)", "domain_error(prolog_flag,nosuch)"),
    ("-set_prolog_flag(double_quotes, codes)", "permission_error(modify,flag,double_quotes)"),
])
def test_a_refused_directive_is_a_load_error_with_the_iso_term(
        tmp_path, monkeypatch, directive, formal):
    with pytest.raises(SyntaxError) as info:
        _load(tmp_path, monkeypatch, "flags_bad_dir", f"{directive}\nx(1),\n")
    assert f"error({formal},set_prolog_flag/2)" in str(info.value)


# ── double_quotes is the module's -double_quotes mode ───────────────────────


@pytest.mark.parametrize("header, mode, literal", [
    ("", "chars", ("$chars", "ab")),
    ("-double_quotes(atom)\n", "atom", "ab"),
    ("-set_prolog_flag(double_quotes, atom)\n", "atom", "ab"),
    ("-set_prolog_flag(double_quotes, chars)\n", "chars", ("$chars", "ab")),
])
def test_double_quotes_reports_and_governs_the_module_mode(
        tmp_path, monkeypatch, header, mode, literal):
    lm = _lm(_load(tmp_path, monkeypatch, "flags_dq",
                   header + 'lit(X) <- (X is "ab")\n'))
    V, X = Var(), Var()
    assert _answers(("current_prolog_flag", "double_quotes", V), lm, V) == [(mode,)]
    assert _answers(("lit", X), lm, X) == [(literal,)]


# ── assert: flag off / on x every kind of target ─────────────────────────────


ASSERT_SRC = """
    -private([data(_)])
    -dynamic(dyn/1)
    st(1),
    data_user(X) <- (X is data(1))
"""


def _assert_module(tmp_path, monkeypatch, name, flag_on):
    header = "-set_prolog_flag(assert_creates_dynamic, true)\n" if flag_on else ""
    return _lm(_load(tmp_path, monkeypatch, name,
                     header + textwrap.dedent(ASSERT_SRC)))


@pytest.mark.parametrize("builtin", ["assertz", "asserta"])
@pytest.mark.parametrize("flag_on", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("target, outcome", [
    (("nd", 1), "created"),            # does not exist
    (("st", 2), "static"),             # a static predicate with clauses
    (("atom_length", "a", 1), "static"),   # a builtin
    (("data", 2), "static"),           # a declared data functor
    (("dyn", 3), "added"),             # declared -dynamic
])
def test_assert(tmp_path, monkeypatch, builtin, flag_on, target, outcome):
    name = f"flags_assert_{builtin}_{int(flag_on)}_{target[0]}"
    lm = _assert_module(tmp_path, monkeypatch, name, flag_on)
    functor, arity = target[0], len(target) - 1
    if outcome == "created" and not flag_on:
        outcome = "static"
    if outcome == "static":
        got, context = _formal((builtin, target), lm)
        assert got == ("permission_error", "modify", "static_procedure",
                       ("/", functor, arity))
        assert context == ("/", builtin, 1)
        return
    assert _answers((builtin, target), lm) == [()]
    X = Var()
    assert (target[1],) in _answers((functor, X), lm, X)
    # a created procedure is DYNAMIC: it can be retracted and asserted again
    assert _answers(("retract", target), lm) == [()]
    assert _answers((builtin, target), lm) == [()]


def test_the_refusal_is_still_a_name_error_for_python_callers(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "flags_nameerr", """
        add(X) <- assertz(flags_nameerr_new(X))
    """)
    with pytest.raises(NameError):
        list(solve(("add", 1), _lm(mod), Trail()))


# ── the .pl importer sets assert_creates_dynamic ─────────────────────────────


def test_an_imported_pl_module_gets_iso_assert(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "flags_pl_on", """
        add(X) :- assertz(counter(X)).
        get(X) :- counter(X).
        st(1).
        addst(X) :- assertz(st(X)).
    """, ext="pl")
    lm = _lm(mod)
    V, X = Var(), Var()
    assert _answers(("current_prolog_flag", "assert_creates_dynamic", V), lm, V) == [(True,)]
    assert _answers(("add", 7), lm) == [()]
    assert _answers(("get", X), lm, X) == [(7,)]
    got, _ = _formal(("addst", 2), lm)
    assert got == ("permission_error", "modify", "static_procedure", ("/", "st", 1))


def test_a_pl_module_can_turn_it_off(tmp_path, monkeypatch):
    mod = _load(tmp_path, monkeypatch, "flags_pl_off", """
        :- set_prolog_flag(assert_creates_dynamic, false).
        add(X) :- assertz(counter(X)).
    """, ext="pl")
    got, _ = _formal(("add", 1), _lm(mod))
    assert got == ("permission_error", "modify", "static_procedure",
                   ("/", "counter", 1))


def test_the_translator_carries_set_prolog_flag_across():
    from clausal.tools.prolog_to_clausal import prolog_to_clausal
    out = prolog_to_clausal(":- set_prolog_flag(unknown, error).\n"
                            ":- set_prolog_flag(debug, on).\n")
    assert "-set_prolog_flag(unknown, 'error')" in out
    assert "-set_prolog_flag(debug, 'on')" in out
    # the default is a loader item, not translated text
    assert "assert_creates_dynamic" not in prolog_to_clausal("p(1).\n")


# ── the Scryer oracle ───────────────────────────────────────────────────────


ORACLE = [
    # (goal, Scryer's answer, agrees with this engine?)
    ("current_prolog_flag(bounded, X).", "X = false.", True),
    ("current_prolog_flag(max_integer, X).", "false.", True),
    ("current_prolog_flag(unknown, X).", "X = error.", True),
    ("current_prolog_flag(double_quotes, X).", "X = chars.", True),
    ("current_prolog_flag(max_arity, X).", "X = 255.", False),   # ours: unbounded
    ("set_prolog_flag(X, 1).", "error(instantiation_error,set_prolog_flag/2).", True),
    ("set_prolog_flag(1, a).", "error(type_error(atom,1),set_prolog_flag/2).", True),
    ("set_prolog_flag(nosuch, 1).",
     "error(domain_error(prolog_flag,nosuch),set_prolog_flag/2).", True),
    ("current_prolog_flag(nosuch, X).",
     "error(domain_error(prolog_flag,nosuch),current_prolog_flag/2).", True),
    ("set_prolog_flag(double_quotes, bogus).",
     "error(domain_error(flag_value,double_quotes+bogus),set_prolog_flag/2).", True),
    # Scryer departs from ISO 8.17.1.3 e/f on these two; ISO decides here
    ("set_prolog_flag(max_arity, 5).",
     "error(domain_error(prolog_flag,max_arity),set_prolog_flag/2).", False),
    ("set_prolog_flag(unknown, bogus).",
     "error(domain_error(prolog_flag,unknown),set_prolog_flag/2).", False),
    # ISO assert (7.5.2(2)): what assert_creates_dynamic=true gives
    ("assertz(nd(1)), nd(X).", "X = 1.", True),
    ("asserta(nd(1)), nd(X).", "X = 1.", True),
    ("assertz(st(2)).",
     "error(permission_error(modify,static_procedure,st/1),assertz/1).", True),
    ("assertz(atom_length(a,1)).",
     "error(permission_error(modify,static_procedure,atom_length/2),assertz/1).", True),
    ("assertz(dyn(3)), dyn(X).", "X = 3.", True),
]


def _scryer(goal: str) -> str:
    d = tempfile.mkdtemp()
    pl = os.path.join(d, "w.pl")
    with open(pl, "w") as fh:
        fh.write(":- dynamic(dyn/1).\nst(1).\n")
    proc = run_scryer(pl, [goal], timeout=30)
    lines = [ln.strip() for ln in proc.stdout.splitlines()
             if ln.strip() and "put_attr TRACE" not in ln]
    return lines[0] if lines else ""


@pytest.mark.parametrize("goal, answer, agrees", ORACLE, ids=[g for g, _, _ in ORACLE])
def test_scryer_oracle(scryer, goal, answer, agrees):
    assert _scryer(goal) == answer


@pytest.mark.parametrize("flag_on", [False, True], ids=["off", "on"])
@pytest.mark.parametrize("goal", ["add_nested_dyn", "add_nested_new"])
def test_a_nested_undeclared_functor_is_still_refused(
        tmp_path, monkeypatch, flag_on, goal):
    """Only the clause's OUTERMOST functor is the procedure the flag is
    about.  An undeclared functor inside it is refused at construction, with
    the flag off or on, and nothing is stored (roborev job 291)."""
    header = "-set_prolog_flag(assert_creates_dynamic, true)\n" if flag_on else ""
    lm = _lm(_load(tmp_path, monkeypatch, f"flags_nested_{int(flag_on)}_{goal}",
                   header + textwrap.dedent("""
        -dynamic(dyn/1)
        add_nested_dyn(X) <- assertz(dyn(nested_undeclared(X)))
        add_nested_new(X) <- assertz(flags_nested_new(nested_undeclared(X)))
    """)))
    with pytest.raises(NameError) as info:
        list(solve((goal, 1), lm, Trail()))
    formal = cell_args(_deref_walk(info.value.term))[0]
    assert formal == ("permission_error", "modify", "static_procedure",
                      ("/", "nested_undeclared", 1))
    assert _answers(("dyn", Var()), lm) == []
