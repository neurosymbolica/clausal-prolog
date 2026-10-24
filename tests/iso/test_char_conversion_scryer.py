"""ISO character conversion (13211-1 8.14.5, 8.14.6, flag 7.11.2.1).

``char_conversion(In, Out)`` adds the pair ``(In, Out)`` to the character
conversion table when ``In \\== Out``, and removes any pair ``(In, _)``
when ``In == Out``.  ``current_char_conversion(In, Out)`` is true iff
``In \\== Out`` and the pair is in the table.  Errors (context the
builtin's indicator):

* char_conversion/2: ``In`` or ``Out`` unbound -- ``instantiation_error``;
  either bound to anything but a one-char atom --
  ``representation_error(character)``;
* current_char_conversion/2: either bound to anything but a one-char atom
  -- ``representation_error(character)``.

The table is process-wide, as ISO makes it.  The ``char_conversion`` flag
is ``off``; ``on`` is refused (``permission_error(modify, flag,
char_conversion)``) because no reader here applies the table: there is no
``read_term/2``, and the source front ends read a file before its
directives run.

Scryer (the oracle elsewhere in this suite) has neither builtin and no
``char_conversion`` flag: the ORACLE half pins that, so the day Scryer
grows them the rows below are what to compare against.  ISO decides.
"""

from __future__ import annotations

import os
import sys
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module, _load_prolog_module
from clausal.logic.exceptions import render_error_term, LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Trail, Var
from clausal.terms import term_writeq

from .conftest import SCRYER, run_scryer


@pytest.fixture(autouse=True)
def _tree_under_test():
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__


@pytest.fixture(autouse=True)
def _empty_table():
    """The table is process-wide: every test starts and ends with it
    empty."""
    from clausal.logic.builtins import flags
    flags._CHAR_CONVERSION.clear()
    yield
    flags._CHAR_CONVERSION.clear()


def _rep(pi):
    return f"error(representation_error(character),{pi})"


CC, CUR = "char_conversion/2", "current_char_conversion/2"

#: (goal binding R, the answers R takes -- writeq'd, one per line -- or
#:  the error term the goal raises)
ROWS = [
    # the table: add, overwrite, remove, enumerate
    ("char_conversion(a, b), current_char_conversion(a, R)", ["b"]),
    ("char_conversion(a, b), current_char_conversion(R, b)", ["a"]),
    ("char_conversion(a, b), char_conversion(a, c), "
     "current_char_conversion(a, R)", ["c"]),
    ("char_conversion(a, b), char_conversion(a, a), "
     "findall(X-Y, current_char_conversion(X, Y), R)", ["[]"]),
    ("char_conversion(b, x), char_conversion(a, y), "
     "findall(X-Y, current_char_conversion(X, Y), R0), msort(R0, R)",
     ["[a-y,b-x]"]),
    # an identity pair is never in the table
    ("char_conversion(a, a), findall(X-Y, current_char_conversion(X, Y), R)",
     ["[]"]),
    ("current_char_conversion(a, R)", []),
    ("findall(X-Y, current_char_conversion(X, Y), R)", ["[]"]),
    ("char_conversion(a, b), current_char_conversion(a, b), R = yes",
     ["yes"]),
    ("char_conversion(a, b), current_char_conversion(a, c), R = yes", []),
    # any one-char atom, quoted ones included
    ("char_conversion(' ', '_'), current_char_conversion(' ', R)", ["'_'"]),
    ("char_conversion('A', é), current_char_conversion('A', R)", ["é"]),
    # 8.14.5.3
    ("char_conversion(_, a), R = no", ["error(instantiation_error,char_conversion/2)"]),
    ("char_conversion(a, _), R = no", ["error(instantiation_error,char_conversion/2)"]),
    ("char_conversion(ab, a), R = no", [_rep(CC)]),
    ("char_conversion(a, ab), R = no", [_rep(CC)]),
    ("char_conversion(1, a), R = no", [_rep(CC)]),
    ("char_conversion(a, f(x)), R = no", [_rep(CC)]),
    ("char_conversion('', a), R = no", [_rep(CC)]),
    # 8.14.6.3
    ("current_char_conversion(ab, R)", [_rep(CUR)]),
    ("current_char_conversion(1, R)", [_rep(CUR)]),
    ("current_char_conversion(R, f(x))", [_rep(CUR)]),
    ("current_char_conversion(R, [])", [_rep(CUR)]),
    # the flag (7.11.2.1)
    ("current_prolog_flag(char_conversion, R)", ["off"]),
    ("set_prolog_flag(char_conversion, off), R = yes", ["yes"]),
    ("set_prolog_flag(char_conversion, on), R = no",
     ["error(permission_error(modify,flag,char_conversion),set_prolog_flag/2)"]),
]


def _program() -> str:
    return "".join(f"r{i}(R) :- {goal}.\n" for i, (goal, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def rows_module(tmp_path_factory):
    d = tmp_path_factory.mktemp("char_conversion")
    path = d / "char_conversion_rows.pl"
    path.write_text(_program(), encoding="utf-8")
    sys.path.insert(0, str(d))
    try:
        yield _load_prolog_module("char_conversion_rows", str(path))
    finally:
        sys.path.remove(str(d))


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(rows_module, i):
    from clausal.logic.builtins import flags
    flags._CHAR_CONVERSION.clear()
    R = Var()
    out = []
    try:
        for _ in solve((f"r{i}", R), rows_module, Trail()):
            out.append(term_writeq(_deref_walk(R)))
    except LogicException as exc:
        out.append(render_error_term(exc.term))
    assert out == ROWS[i][1]


def test_the_table_is_process_wide(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    mods = []
    for name in ("char_conv_a", "char_conv_b"):
        path = tmp_path / f"{name}.pl"
        path.write_text("x.\n")
        mods.append(_load_prolog_module(name, str(path)))
    a, b = (m.__dict__["$module"] for m in mods)
    R = Var()
    assert len(list(solve(("char_conversion", "a", "b"), a, Trail()))) == 1
    assert [_deref_walk(R) for _ in solve(
        ("current_char_conversion", "a", R), b, Trail())] == ["b"]


def test_clausal_prolog_has_them(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "char_conv_cl.clausal"
    path.write_text(
        ":- module(char_conv_cl, [t/1]).\n"
        "t(R) :- char_conversion(p, q), current_char_conversion(p, R).\n"
        ":- end_module(char_conv_cl).\n")
    lm = _load_module("char_conv_cl", str(path)).__dict__["$module"]
    R = Var()
    assert [_deref_walk(R) for _ in solve(("t", R), lm, Trail())] == ["q"]


def test_the_directive_sets_the_table_and_reading_ignores_it(tmp_path,
                                                             monkeypatch):
    # ISO 7.4.2.5: char_conversion/2 is also a directive.  With the flag
    # off (it cannot be on here) the text after it is read as written.
    from clausal.logic.builtins import flags
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "char_conv_read.pl"
    path.write_text(":- char_conversion(a, b).\nt(a).\n")
    lm = _load_prolog_module("char_conv_read", str(path)).__dict__["$module"]
    R = Var()
    assert [_deref_walk(R) for _ in solve(("t", R), lm, Trail())] == ["a"]
    assert flags._CHAR_CONVERSION == {"a": "b"}


@pytest.mark.parametrize("directive, formal", [
    (":- char_conversion(_, a).", "instantiation_error"),
    (":- char_conversion(ab, a).", "representation_error(character)"),
    (":- char_conversion(a, 1).", "representation_error(character)"),
    (":- set_prolog_flag(char_conversion, on).",
     "permission_error(modify,flag,char_conversion)"),
])
def test_a_bad_directive_is_a_load_error(tmp_path, monkeypatch, directive,
                                         formal):
    monkeypatch.syspath_prepend(str(tmp_path))
    path = tmp_path / "char_conv_bad.pl"
    path.write_text(directive + "\nt.\n")
    sys.modules.pop("char_conv_bad", None)
    with pytest.raises(SyntaxError) as info:
        _load_prolog_module("char_conv_bad", str(path))
    assert formal in str(info.value)


SCRYER_ROWS = [
    ("char_conversion(a, b).",
     "error(existence_error(procedure,char_conversion/2),char_conversion/2)"),
    ("current_char_conversion(X, Y).",
     "error(existence_error(procedure,current_char_conversion/2),"
     "current_char_conversion/2)"),
    ("current_prolog_flag(char_conversion, X).",
     "error(domain_error(prolog_flag,char_conversion),current_prolog_flag/2)"),
]


@pytest.mark.parametrize("goal, answer", SCRYER_ROWS)
def test_scryer_has_none_of_it(scryer, goal, answer):
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "w.pl")
        with open(pl, "w") as fh:
            fh.write("x.\n")
        proc = run_scryer(pl, [f"catch({goal[:-1]}, E, (writeq(E), nl))."],
                          timeout=30)
    assert answer in proc.stdout, proc.stdout
