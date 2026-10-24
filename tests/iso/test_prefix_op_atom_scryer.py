"""A prefix operator followed by a token that cannot start a term is an
atom (ISO 6.3.4.2): ``\\ .`` reads as the atom ``\\``, ``- .`` as ``-``.

Rows checked against Scryer, which reads the same text with read_term/3:

* ``- .``, ``\\ .``, ``\\+ .``, ``:- .`` are the atoms;
* ``[-]``, ``f(-)``, ``- (-)``, ``\\+ (-)`` hold the atom as an argument;
* ``- (1)`` and ``-(1)`` are both the compound -(1) (a ``(`` is not a
  number, so no negative literal is formed);
* ``X = - .`` and ``- - .`` are syntax errors: the atom is an operand
  there, and an operator atom as an operand has priority 1201 (ISO 6.3.1.3),
  above the 699 (or 200) the operator allows.

Every row is read by the reader both ``.pl`` front ends use (the native
front end's ``PrologReader``, and the translator's ``parse_term``), as a
``clausal -g`` goal where it is one, and by Scryer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from clausal.terms import term_write
from clausal.tools.prolog_parser import parse_term
from clausal.tools.prolog_reader import read_module
from tests import _oracles

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: (text, writeq of the term it reads as, or None for a syntax error).
ROWS = [
    ("- .", "-"),
    ("\\ .", "\\"),
    ("\\+ .", "\\+"),
    (":- .", ":-"),
    ("(-) .", "-"),
    ("'-' .", "-"),
    ("[-] .", "[-]"),
    ("[-,\\] .", "[-,\\]"),
    ("f(-) .", "f(-)"),
    ("- (-) .", "- (-)"),
    ("\\+ (-) .", "\\+ (-)"),
    ("\\ (\\) .", "\\ (\\)"),
    ("- (1) .", "- (1)"),
    ("-(1) .", "- (1)"),
    ("- a .", "-a"),
    ("X = - .", None),
    ("- - .", None),
]

SCRYER_READER = r"""
go :- open(File, read, S), loop(S).
loop(S) :-
    catch(read_term(S, T, []), error(syntax_error(_), _), T = '$error'),
    (   T == end_of_file -> true
    ;   T == '$error' -> write('ERROR'), nl, loop(S)
    ;   writeq(T), nl, loop(S)
    ).
"""


def _native(text):
    items = read_module(text)
    assert len(items) == 1, items
    item = items[0]
    if type(item).__name__ == "SyntaxIssue":
        return None
    return term_write(item.term, quoted=True)


def _translator(text):
    try:
        return parse_term(text)
    except Exception:                       # noqa: BLE001 -- a syntax error
        return None


@pytest.mark.parametrize("text, want", ROWS, ids=[r[0] for r in ROWS])
def test_native_reader(text, want):
    assert _native(text) == want


@pytest.mark.parametrize("text, want", ROWS, ids=[r[0] for r in ROWS])
def test_translator_parser(text, want):
    got = _translator(text)
    assert (got is None) == (want is None), got


#: The rows that are goals: what ``clausal -g`` does with each.
GOALS = [
    ("- .", "error(existence_error(procedure,(-)/0),(-)/0)"),
    ("\\ .", "error(existence_error(procedure,(\\)/0),(\\)/0)"),
    ("\\+ .", "error(existence_error(procedure,(\\+)/0),(\\+)/0)"),
    ("X = (- .)", "X = -'.'."),
    ("X = (\\ .)", "X = \\'.'."),
    ("X = [-]", "X = \"-\"."),
    ("X = f(-)", "X = f(-)."),
    ("X = - (1)", "X = - (1)."),
    ("X = -(1)", "X = - (1)."),
    ("X = - (1), X = -(1)", "X = - (1)."),
]


@pytest.mark.parametrize("goal, want", GOALS, ids=[g for g, _ in GOALS])
def test_g_goal(tmp_path, goal, want):
    (tmp_path / "prog.pl").write_text("p.\n")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    proc = subprocess.run(
        [sys.executable, "-m", "clausal", "-g", goal, "prog.pl"],
        cwd=tmp_path, env=env, capture_output=True, text=True, timeout=120)
    out = (proc.stdout + proc.stderr).strip().splitlines()[-1]
    assert out.endswith(want), out


def test_rows_match_scryer(tmp_path, scryer):
    terms = tmp_path / "terms.txt"
    terms.write_text("\n".join(t for t, _ in ROWS) + "\n")
    prog = tmp_path / "reader.pl"
    prog.write_text(SCRYER_READER.replace("File", repr(str(terms))))
    proc = subprocess.run(
        [_oracles.SCRYER, str(prog), "-g", "go", "-g", "halt"],
        stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=60)
    lines = proc.stdout.splitlines()
    assert lines == [w if w is not None else "ERROR" for _, w in ROWS], (
        proc.stdout + proc.stderr)
