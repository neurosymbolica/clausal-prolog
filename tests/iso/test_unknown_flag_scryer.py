"""The ``unknown`` flag (ISO 13211-1 7.11.2.4): what a call to a procedure
that does not exist does.

* ``error`` (the default): ``existence_error(procedure, PI)``;
* ``fail``: the call fails;
* ``warning``: an implementation-dependent warning, then the call fails.

The flag is process-wide, as ISO has it (a flag is global).  Each ROW is
one goal written in a clause body of the same ``.pl`` program, run under
each value of the flag by the engine and (ORACLE half) by Scryer.  The
driver clause sets the flag, runs the row's clause, reports ``true``,
``false`` or ``caught(E)``, and puts the flag back to ``error``.

Scryer prints its warning (``% Warning: predicate nosuch/0 is undefined``)
on standard output; the engine prints the same line on standard error (the
``user_error`` stream ISO names for diagnostics).
"""

from __future__ import annotations

import os
import sys
import tempfile
import textwrap

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var
from clausal.terms import term_writeq

from .conftest import SCRYER, run_scryer


@pytest.fixture(autouse=True)
def _tree_under_test():
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__


@pytest.fixture(autouse=True)
def _restore_process_flags():
    """``unknown`` is process-wide: put it back after every test."""
    from clausal.logic.builtins import flags
    saved = dict(flags._PROCESS)
    yield
    flags._PROCESS.clear()
    flags._PROCESS.update(saved)


def _ex(pi):
    return f"caught(error(existence_error(procedure,{pi}),{pi}))"


#: (goal, answer under error, answer under fail / warning, the indicator
#:  the warning names -- written unquoted, as Scryer writes it -- or None)
ROWS = [
    # a direct call in a clause body
    ("nosuch", _ex("nosuch/0"), "false", "nosuch/0"),
    ("nosuch(1)", _ex("nosuch/1"), "false", "nosuch/1"),
    # meta-calls
    ("call(nosuch)", _ex("nosuch/0"), "false", "nosuch/0"),
    ("call(nosuch, 1)", _ex("nosuch/1"), "false", "nosuch/1"),
    ("G = nosuch(1), call(G)", _ex("nosuch/1"), "false", "nosuch/1"),
    ("call((true, nosuch))", _ex("nosuch/0"), "false", "nosuch/0"),
    ("once(nosuch)", _ex("nosuch/0"), "false", "nosuch/0"),
    ("maplist(nosuch, [1])", _ex("nosuch/1"), "false", "nosuch/1"),
    ("phrase(nosuch, [])", _ex("nosuch/2"), "false", "nosuch/2"),
    # call/N's fold makes ','/3, a procedure that does not exist
    ("call((true, true), x)", _ex("(',')/3"), "false", ",/3"),
    # negation and the all-solutions builtins see the failure
    ("\\+ nosuch", _ex("nosuch/0"), "true", "nosuch/0"),
    ("findall(X, nosuch(X), L), L == []", _ex("nosuch/1"), "true",
     "nosuch/1"),
    ("(nosuch ; true)", _ex("nosuch/0"), "true", "nosuch/0"),
    # a failure is not an error: catch/3 has nothing to catch
    ("catch(nosuch, _, true)", "true", "false", "nosuch/0"),
    # a predicate exists at another arity only: pk/2 does not exist
    ("pk(1, 2)", _ex("pk/2"), "false", "pk/2"),
    ("call(pk, 1, 2)", _ex("pk/2"), "false", "pk/2"),
    # a qualified call into a module that does not exist
    ("nomod:nosuch(1)", _ex("nosuch/1"), "false", "nosuch/1"),
    ("call(nomod:nosuch, 1)", _ex("nosuch/1"), "false", "nosuch/1"),
    # the flag leaves a procedure that exists alone
    ("pk(1)", "true", "true", None),
    ("call(pk, 1)", "true", "true", None),
    ("phrase(nt, [a])", "true", "true", None),
]

MODES = ("error", "fail", "warning")

PROGRAM = """\
pk(1).
nt --> [a].
"""


def _program() -> str:
    lines = [PROGRAM]
    for i, (goal, _, _, _) in enumerate(ROWS):
        lines.append(f"g{i} :- {goal}.\n")
        lines.append(
            f"r{i}(Mode, R) :- set_prolog_flag(unknown, Mode), "
            f"catch((g{i} -> R = true ; R = false), E, R = caught(E)), "
            f"set_prolog_flag(unknown, error).\n")
    return "".join(lines)


def _expected(mode, row):
    _, on_error, on_fail, _ = row
    return on_error if mode == "error" else on_fail


@pytest.fixture(scope="module")
def unknown_module(tmp_path_factory):
    d = tmp_path_factory.mktemp("unknown_flag")
    path = d / "unknown_flag_rows.pl"
    path.write_text(_program())
    sys.path.insert(0, str(d))
    try:
        yield _load_prolog_module("unknown_flag_rows", str(path))
    finally:
        sys.path.remove(str(d))


def _engine(mod, i, mode) -> str:
    R = Var()
    answers = [term_writeq(_deref_walk(R))
               for _ in solve((f"r{i}", mode, R), mod, Trail())]
    assert len(answers) == 1, answers
    return answers[0]


@pytest.mark.parametrize("mode", MODES)
@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(unknown_module, capfd, i, mode):
    row = ROWS[i]
    assert _engine(unknown_module, i, mode) == _expected(mode, row)
    err = capfd.readouterr().err
    warning = f"% Warning: predicate {row[3]} is undefined"
    if mode == "warning" and row[3] is not None:
        assert warning in err, err
    else:
        assert "Warning: predicate" not in err, err


def test_scryer_oracle(scryer):
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "rows.pl")
        with open(pl, "w") as fh:
            fh.write(":- use_module(library(lists)).\n"
                     ":- use_module(library(dcgs)).\n" + _program())
        queries = [f"r{i}({mode}, R), write('A '), writeq(R), nl, fail ; true."
                   for i in range(len(ROWS)) for mode in MODES]
        got = []
        for q in queries:
            proc = run_scryer(pl, [q], timeout=30)
            answer = [ln[2:].strip() for ln in proc.stdout.splitlines()
                      if ln.startswith("A ")]
            warned = [ln.strip() for ln in proc.stdout.splitlines()
                      if "Warning: predicate" in ln]
            got.append((answer, warned))
    bad = []
    k = 0
    for row in ROWS:
        for mode in MODES:
            answer, warned = got[k]
            k += 1
            want = ([f"% Warning: predicate {row[3]} is undefined"]
                    if mode == "warning" and row[3] is not None else [])
            if answer != [_expected(mode, row)] or warned != want:
                bad.append((row[0], mode, answer, warned))
    assert bad == []


# ── the flag itself ─────────────────────────────────────────────────────────


def _lm(mod):
    return mod.__dict__["$module"]


def _answers(goal, lm, *slots):
    return [tuple(_deref_walk(s) for s in slots)
            for _ in solve(goal, lm, Trail())]


@pytest.fixture
def two_modules(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    mods = []
    for name in ("unknown_flag_a", "unknown_flag_b"):
        path = tmp_path / f"{name}.pl"
        path.write_text("t(R) :- catch((nosuch -> R = true ; R = false), "
                        "E, R = caught(E)).\n")
        sys.modules.pop(name, None)
        mods.append(_lm(_load_prolog_module(name, str(path))))
    return mods


@pytest.mark.parametrize("value", MODES)
def test_every_iso_value_can_be_set_and_read_back(two_modules, value):
    a, _ = two_modules
    V = Var()
    assert _answers(("set_prolog_flag", "unknown", value), a) == [()]
    assert _answers(("current_prolog_flag", "unknown", V), a, V) == [(value,)]


def test_the_flag_is_process_wide(two_modules):
    # ISO 7.11: a flag is global.  Set in one module, it governs the calls
    # of another.
    a, b = two_modules
    R, V = Var(), Var()
    assert _answers(("set_prolog_flag", "unknown", "fail"), a) == [()]
    assert _answers(("current_prolog_flag", "unknown", V), b, V) == [("fail",)]
    assert _answers(("t", R), b, R) == [(False,)]


def test_a_load_time_directive_sets_it(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "unknown_flag_dir.pl"
    path.write_text(":- set_prolog_flag(unknown, fail).\n"
                    "t(R) :- (nosuch -> R = true ; R = false).\n")
    lm = _lm(_load_prolog_module("unknown_flag_dir", str(path)))
    R = Var()
    assert _answers(("t", R), lm, R) == [(False,)]


def test_a_query_of_an_unknown_procedure_fails(two_modules):
    a, _ = two_modules
    assert _answers(("set_prolog_flag", "unknown", "fail"), a) == [()]
    assert _answers(("nosuch", 1), a) == []


def test_clausal_prolog_honours_it(tmp_path, monkeypatch):
    # The same flag on the Clausal Prolog surface.
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "unknown_flag_cl.clausal"
    path.write_text(textwrap.dedent("""\
        :- module(unknown_flag_cl, [t/1]).
        t(R) :- catch((call(nosuch, 1), R = yes), E, R = caught(E)).
        u(R) :- findall(X, nosuch(X), R).
        :- end_module(unknown_flag_cl).
    """))
    lm = _lm(_load_module("unknown_flag_cl", str(path)))
    R = Var()
    assert _answers(("set_prolog_flag", "unknown", "fail"), lm) == [()]
    assert _answers(("t", R), lm, R) == []
    assert _answers(("u", R), lm, R) == [([],)]
    assert _answers(("set_prolog_flag", "unknown", "error"), lm) == [()]
    [(got,)] = _answers(("t", R), lm, R)
    assert got[0] == "caught"


def test_the_refusals_of_committed_choice_stay_errors(two_modules, tmp_path,
                                                      monkeypatch):
    # ``*->`` is refused on every surface (Clausal is cut-free): it reports
    # existence_error(procedure, '*->'/2), but it is a refusal, not a
    # missing procedure, so the flag does not turn it into a failure.
    a, _ = two_modules
    assert _answers(("set_prolog_flag", "unknown", "fail"), a) == [()]
    with pytest.raises(LogicException) as info:
        list(solve(("call", ("*->", "true", "true")), a, Trail()))
    assert "*->" in str(_deref_walk(info.value.term))
