"""An ISO built-in predicate is static (ISO 7.5.1): a Prolog text may not
define one.  The engine against the Scryer oracle, on one Prolog text run by
both.

A clause for an ISO built-in (or a control construct) refuses the whole
file with ``permission_error(modify, static_procedure, PI)``: Scryer reports
it from ``load/1`` and loads nothing of the file, and the engine's loader
refuses the module.  A library predicate (``append/3``, ``length/2``,
``between/3``, ``forall/2`` ...) is no ISO built-in, so a file may define
it, and its own calls then run that definition, as in Scryer.

The same holds for a module-qualified head (``user:atom_length(_, 5).``)
and for a fact a ``term_expansion`` rule hands back (``term_expansion/4``
in the engine, ``term_expansion/2`` in Scryer).  ``:- dynamic(PI)`` of a
built-in is refused too, where Scryer ignores it (see
``test_dynamic_of_a_builtin_oracle``).  At run time ``assertz``/``retract``
of an ISO built-in is the same permission error, with the builtin as
context.

The set is ISO's, not Scryer's: Scryer lets a file define
``char_conversion/2`` and ``current_char_conversion/2``, which it does not
implement, while the engine refuses them, as ISO 7.5.1 says (8.14.5,
8.14.6).

The ISO set is ``clausal/tools/iso_builtins.py``; todo/done/iso-a-file-can-
redefine-a-builtin-2026-10-16.md is the record.
"""

from __future__ import annotations

import os
import re
import tempfile

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]
from clausal.import_hook import _load_module
from clausal.logic.solve import solve
from clausal.logic.variables import Trail
from tests._oracles import SCRYER, run_scryer

# (id, a clause, the refused PI as the engine's message names it, and as
# Scryer's error term writes it).  Each row's file is ``p(1).`` then the row's text then
# ``q(2).``: the refusal must take the whole file, the clause before it too.
REFUSED = [
    ("fact_atom_length_2", "atom_length(_, 5).", "atom_length/2", "atom_length/2"),
    ("rule_is_2", "X is _ :- X = 99.", "is/2", "(is)/2"),
    ("fact_atom_1", "atom(_).", "atom/1", "atom/1"),
    ("rule_write_1", "write(_) :- true.", "write/1", "write/1"),
    ("fact_keysort_2", "keysort(_, _).", "keysort/2", "keysort/2"),
    ("rule_once_1", "once(X) :- X = 1.", "once/1", "once/1"),
    ("fact_findall_3", "findall(_, _, _).", "findall/3", "findall/3"),
    ("fact_halt_0", "halt.", "halt/0", "halt/0"),
    ("fact_nl_0", "nl.", "nl/0", "nl/0"),
    ("fact_op_3", "op(_, _, _).", "op/3", "op/3"),
    ("fact_acyclic_term_1", "acyclic_term(_).", "acyclic_term/1", "acyclic_term/1"),
    ("fact_repeat_0", "repeat.", "repeat/0", "repeat/0"),
    ("fact_read_1_not_provided", "read(_).", "read/1", "read/1"),
    ("grammar_rule_atom_length", "atom_length --> [].", "atom_length/2",
     "atom_length/2"),
    # control constructs (ISO 7.8)
    ("fact_call_1", "call(_).", "call/1", "call/1"),
    ("fact_call_8", "call(_, _, _, _, _, _, _, _).", "call/8", "call/8"),
    ("fact_comma_2", "','(a, b).", ",/2", "(',')/2"),
    ("fact_true_0", "true.", "true/0", "true/0"),
    ("fact_catch_3", "catch(_, _, _).", "catch/3", "catch/3"),
    # a module-qualified head
    ("qualified_user_atom_length_2", "user:atom_length(_, 5).",
     "atom_length/2", "atom_length/2"),
    ("qualified_m_call_1", "m:call(_).", "call/1", "call/1"),
]

# A fact a term_expansion rule hands back for ``foo(zz).``: (id, the
# expansion, the refused PI as the engine names it, and as Scryer writes it).
EXPANDED = [
    ("expanded_atom_length_2", "atom_length(X, 5)", "atom_length/2",
     "atom_length/2"),
    ("expanded_call_1", "call(X)", "call/1", "call/1"),
    ("expanded_true_0", "true", "true/0", "true/0"),
]

# Library predicates, not ISO built-ins: the file loads and the goal runs
# the file's own definition.  (id, clause, goal, the answer written).
ALLOWED = [
    ("rule_append_3", "append(a, b, c) :- true.",
     "findall(X-Y-Z, append(X, Y, Z), L)", "[a-b-c]"),
    ("fact_length_2", "length(mine, 7).",
     "findall(X-N, length(X, N), L)", "[mine-7]"),
    ("fact_between_3", "between(mine, 0, 0).",
     "findall(X, between(X, 0, 0), L)", "[mine]"),
    ("fact_msort_2", "msort(mine, mine).",
     "findall(X, msort(X, mine), L)", "[mine]"),
]

# Run time (ISO 8.9): the error term of each goal.
RUNTIME = [
    ("assertz_atom_length", "assertz(atom_length(a, 1))",
     "error(permission_error(modify,static_procedure,atom_length/2),assertz/1)"),
    ("asserta_atom_length", "asserta(atom_length(a, 1))",
     "error(permission_error(modify,static_procedure,atom_length/2),asserta/1)"),
    ("retract_atom_length", "retract(atom_length(_, _))",
     "error(permission_error(modify,static_procedure,atom_length/2),retract/1)"),
    ("assertz_call_1", "assertz((call(_) :- true))",
     "error(permission_error(modify,static_procedure,call/1),assertz/1)"),
]

DYNAMIC_ROW = ":- dynamic(atom_length/2)."

_PI_IN_MESSAGE = re.compile(r"permission_error\(modify, static_procedure, (.+?)\)\)")


def _file(tmp_path, stem: str, suffix: str, text: str) -> str:
    path = tmp_path / f"{stem}{suffix}"
    path.write_text(text)
    return str(path)


def _refused_indicator(tmp_path, stem: str, suffix: str,
                       text: str) -> "str | None":
    """Load *text*; -> the PI of its static_procedure refusal, or None when
    the module loads."""
    try:
        _load_module(stem, _file(tmp_path, stem, suffix, text))
    except SyntaxError as e:
        m = _PI_IN_MESSAGE.search(str(e))
        assert m, str(e)
        return m.group(1)
    return None


def _answers(mod, goal_name: str) -> int:
    return sum(1 for _ in solve((goal_name, 1), mod, Trail()))


def _scryer_out(program: str, goal: str) -> list:
    d = tempfile.mkdtemp()
    pl = os.path.join(d, "w.pl")
    with open(pl, "w") as fh:
        fh.write(program)
    proc = run_scryer(pl, [goal], timeout=30)
    return [ln.strip() for ln in proc.stdout.strip().splitlines()]


@pytest.fixture
def oracle():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    return _scryer_out


#: The surfaces the engine rows run on: ``.pl`` through the native front end
#: (the default) and through the legacy translator, and ``.clausal``.
SURFACES = [(PL, "native"), (PL, "translator"), (CLAUSAL, "native")]
SURFACE_IDS = ["pl", "pl-translator", "clausal"]


@pytest.fixture(params=SURFACES, ids=SURFACE_IDS)
def surface(request, monkeypatch):
    suffix, frontend = request.param
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    return suffix


def _program(row: str) -> str:
    return f"p(1).\n{row}\nq(2).\n"


# --- a clause for an ISO built-in refuses the file --------------------------

def _assert_scryer_refused_the_file(out, name, scryer_indicator):
    assert out[0] == ("error(permission_error(modify,static_procedure,"
                      f"{scryer_indicator}),load/1)."), (name, out)
    # Nothing of the file loaded: not even the clause before the refused one.
    assert "existence_error(procedure,p/1)" in out[-1], (name, out)


@pytest.mark.parametrize("name, text, indicator, _scryer_indicator", REFUSED,
                         ids=[r[0] for r in REFUSED])
def test_refused_engine(tmp_path, surface, name, text, indicator,
                        _scryer_indicator):
    got = _refused_indicator(tmp_path, f"_builtin_refused_{name}", surface,
                             _program(text))
    assert got == indicator, (name, got)


@pytest.mark.parametrize("name, text, _indicator, scryer_indicator", REFUSED,
                         ids=[r[0] for r in REFUSED])
def test_refused_oracle(oracle, name, text, _indicator, scryer_indicator):
    _assert_scryer_refused_the_file(oracle(_program(text), "p(X)"), name,
                                    scryer_indicator)


# --- a fact a term_expansion rule hands back --------------------------------

@pytest.mark.parametrize("name, expansion, indicator, _scryer_indicator",
                         EXPANDED, ids=[r[0] for r in EXPANDED])
def test_expanded_fact_refused_engine(tmp_path, surface, name, expansion,
                                      indicator, _scryer_indicator):
    text = (f"p(1).\nterm_expansion(foo(X), {expansion}, S, S).\n"
            f"foo(zz).\nq(2).\n")
    try:
        _load_module(f"_builtin_expanded_{name}",
                     _file(tmp_path, f"_builtin_expanded_{name}", surface, text))
    except SyntaxError as e:
        m = _PI_IN_MESSAGE.search(str(e))
        assert m and m.group(1) == indicator, str(e)
    else:
        pytest.fail(f"{name}: the expanded fact was installed")


@pytest.mark.parametrize("name, expansion, _indicator, scryer_indicator",
                         EXPANDED, ids=[r[0] for r in EXPANDED])
def test_expanded_fact_refused_oracle(oracle, name, expansion, _indicator,
                                      scryer_indicator):
    text = (f"p(1).\nterm_expansion(foo(X), {expansion}) :- X = X.\n"
            f"foo(zz).\nq(2).\n")
    _assert_scryer_refused_the_file(oracle(text, "p(X)"), name,
                                    scryer_indicator)


# --- a library predicate is the user's to define ----------------------------

@pytest.mark.parametrize("name, text, goal, expected", ALLOWED,
                         ids=[r[0] for r in ALLOWED])
def test_allowed_engine(tmp_path, surface, name, text, goal, expected):
    src = f"{text}\nt(1) :- {goal}, L == {expected}.\n"
    stem = f"_builtin_allowed_{name}"
    mod = _load_module(stem, _file(tmp_path, stem, surface, src))
    assert _answers(mod, "t") == 1, name


@pytest.mark.parametrize("name, text, goal, expected", ALLOWED,
                         ids=[r[0] for r in ALLOWED])
def test_allowed_oracle(oracle, name, text, goal, expected):
    out = oracle(f"{text}\n", f"{goal}, write(L), nl")
    assert out[0] == expected, (name, out)


# --- dynamic/1 of an ISO built-in -------------------------------------------

@pytest.mark.parametrize("directive, indicator", [
    (":- dynamic(atom_length/2).", "atom_length/2"),
    (":- dynamic(call/1).", "call/1"),
    (":- dynamic([foo/1, atom_length/2]).", "atom_length/2"),
    (":- dynamic((foo/1, call/1)).", "call/1"),
], ids=["atom_length_2", "call_1", "in_a_list", "in_a_sequence"])
def test_dynamic_of_a_builtin_engine(tmp_path, surface, directive, indicator):
    got = _refused_indicator(tmp_path, "_builtin_dynamic", surface,
                             _program(directive))
    assert got == indicator


def test_dynamic_of_a_library_name_engine(tmp_path, surface):
    """``dynamic(append/3)`` stays the user's own procedure."""
    src = (":- dynamic(append/3).\n"
           "t(1) :- assertz(append(a, b, c)), append(a, b, c).\n")
    stem = "_builtin_dynamic_library_name"
    mod = _load_module(stem, _file(tmp_path, stem, surface, src))
    assert _answers(mod, "t") == 1


def test_dynamic_of_a_builtin_oracle(oracle):
    """Scryer DIVERGES here: it ignores ``dynamic(atom_length/2)`` without a
    word, loads the file, and the builtin stays static (an assertz of it is
    still the permission error).  The engine refuses the directive with the
    error ISO gives every other modification of a builtin, as SICStus and
    GNU Prolog document for dynamic/1 of a builtin (Trealla stops loading
    the file at the directive, without a message); this row pins what
    Scryer does so a change there is seen."""
    out = oracle(_program(DYNAMIC_ROW),
                 "p(X), catch(assertz(atom_length(a, 1)), E, true), "
                 "write(E), nl")
    assert out[0] == ("error(permission_error(modify,static_procedure,"
                      "atom_length/2),assertz/1)"), out


# --- run time: assert and retract -------------------------------------------

@pytest.mark.parametrize("name, goal, expected", RUNTIME, ids=[r[0] for r in RUNTIME])
def test_runtime_engine(tmp_path, surface, name, goal, expected):
    src = (f"t(1) :- catch({goal}, E, true), E = {expected}.\n")
    stem = f"_builtin_runtime_{name}"
    mod = _load_module(stem, _file(tmp_path, stem, surface, src))
    assert _answers(mod, "t") == 1, name


@pytest.mark.parametrize("name, goal, expected", RUNTIME, ids=[r[0] for r in RUNTIME])
def test_runtime_oracle(oracle, name, goal, expected):
    out = oracle("p(1).\n", f"catch({goal}, E, true), write(E), nl")
    assert out[0] == expected, (name, out)
