"""Unifying two variables that both carry ``freeze/2`` or ``when/2`` goals
merges the delays (operator ruling 2026-10-24: a non-conformity is a bug).

``X = Y`` with both unbound satisfies no condition a delay waits for
(``nonvar/1``, ``ground/1``), so nothing runs: the goals of the variable
that is bound move onto the one that survives, after its own, and they all
run once it gets a non-variable value -- as Scryer's ``verify_attributes``
for ``freeze`` and ``when`` does.  Before, the bound side's goals ran at the
alias with the variable still unbound (``woke2(_37)``), and a goal that
binds its variable then produced answers that do not exist.

Every row runs the same goals through the real command against a ``.pl``
and a ``.clausal`` program, under the C and the pure-Python trampoline;
the oracle rows run through Scryer's toplevel too (its library qualifiers
taken off, and a ``V = W`` alias written with the names sorted: Scryer and
Clausal name the surviving variable of an alias differently).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

import pytest

import textwrap
from pathlib import Path

from tests import _oracles

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SCRYER_PRELUDE = (":- use_module(library(freeze)).\n"
                  ":- use_module(library(when)).\n"
                  ":- use_module(library(dif)).\n"
                  ":- use_module(library(lists)).\n")

_QUALIFIER = re.compile(r"\b(?:freeze|when|dif|user):")

# The command, under the C or the pure-Python trampoline (as in
# test_freeze_when_residuals_scryer.py).
_CHILD = textwrap.dedent(r'''
    import sys
    if sys.argv[1] == "py":
        sys.modules["clausal.logic.runtime._trampoline"] = None
        sys.modules["clausal.logic._tabling_core"] = None
    import clausal.logic.trampoline as tr
    want = ("clausal.logic._trampoline_py" if sys.argv[1] == "py"
            else "clausal.logic.runtime._trampoline")
    assert tr.trampoline.__module__ == want, tr.trampoline.__module__
    from clausal.cli import main
    sys.exit(main(sys.argv[2:]))
''')

PROGRAM = (
    "w(X) :- write(X), nl.\n"
    "g6 :- freeze(X4, (write(woke(X4)), nl)),"
    " freeze(X2, (write(woke2(X2)), nl)),"
    " X4 = X2, write(aliased), nl, X2 = 7.\n"
)

#: (goal, the lines it prints: its output, then its answer).
ROWS = [
    # the fuzzer's case: nothing runs at the alias, both run at the binding
    ("g6", ["aliased", "woke(7)", "woke2(7)", "true."]),
    # aliasing alone: one merged delay, older variable's goals first
    ("freeze(X, w(a)), freeze(Y, w(b)), X = Y",
     ["X = Y, freeze(X,(w(a),w(b)))."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), Y = X",
     ["X = Y, freeze(X,(w(a),w(b)))."]),
    # aliasing, then binding
    ("freeze(X, w(a)), freeze(Y, w(b)), X = Y, Y = 1",
     ["a", "b", "X = 1, Y = 1."]),
    # one side frozen, the survivor not (the other direction too)
    ("X = X, freeze(Y, w(a)), X = Y", ["X = Y, freeze(X,w(a))."]),
    ("X = X, freeze(Y, w(a)), X = Y, X = 1", ["a", "X = 1, Y = 1."]),
    # aliasing, then backtracking past it: the merge is undone
    ("freeze(X, w(a)), freeze(Y, w(b)), (X = Y, fail ; true)",
     ["freeze(X,w(a)), freeze(Y,w(b))."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), (X = Y, fail ; true), X = 1",
     ["a", "X = 1, freeze(Y,w(b))."]),
    # a freeze on one side, a when on the other
    ("freeze(X, w(a)), when(nonvar(Y), w(b)), X = Y",
     ["X = Y, freeze(X,w(a)), when(nonvar(X),w(b))."]),
    ("freeze(X, w(a)), when(nonvar(Y), w(b)), X = Y, Y = 1",
     ["a", "b", "X = 1, Y = 1."]),
    # three-way aliasing, either way round
    ("freeze(X, w(a)), freeze(Y, w(b)), freeze(Z, w(c)), X = Y, Y = Z, Z = 1",
     ["a", "b", "c", "X = 1, Y = 1, Z = 1."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), freeze(Z, w(c)), Z = Y, Y = X, X = 1",
     ["a", "b", "c", "X = 1, Y = 1, Z = 1."]),
    # a dif on one side: it survives the alias, and still decides the binding
    ("dif(X, 1), freeze(X, w(a)), freeze(Y, w(b)), X = Y",
     ["X = Y, dif(X,1), freeze(X,(w(a),w(b)))."]),
    # (a failing row says so: the command stops at a goal that fails)
    ("(dif(X, 1), freeze(X, w(a)), freeze(Y, w(b)), X = Y, Y = 1 ; w(no))",
     ["no", "true."]),
    ("(dif(Y, 1), freeze(X, w(a)), freeze(Y, w(b)), X = Y, Y = 1 ; w(no))",
     ["no", "true."]),
    ("dif(X, 1), freeze(X, w(a)), freeze(Y, w(b)), X = Y, Y = 2",
     ["a", "b", "X = 2, Y = 2."]),
    # the answer-set shape: a goal that binds its own variable must not run
    # at the alias (it gave X1 = 1, X3 = 1 and lost the other answers)
    ("findall(R, (freeze(X4, X4 = f(X1,1)), freeze(X2, X2 = f(1,X3)),"
     " X4 = X2, (X1 = 2, R = 1 ; X3 = 5, R = 2 ; R = 3)), L)",
     ["L = [1,2,3]."]),
    ("freeze(X4, X4 = f(X1,1)), freeze(X2, X2 = f(1,X3)), X4 = X2,"
     " X2 = f(A,B)",
     ["X4 = f(1,1), X1 = 1, X2 = f(1,1), X3 = 1, A = 1, B = 1."]),
    ("(freeze(X4, X4 = f(X1,1)), freeze(X2, X2 = f(1,X3)), X4 = X2,"
     " X1 = 2, X2 = f(A,B) ; w(no))", ["no", "true."]),
    # an alias made inside one unification of compound terms
    ("f(X,Y) = f(Y,Z), freeze(X, w(a)), freeze(Z, w(b)), Z = 1",
     ["a", "b", "X = 1, Y = 1, Z = 1."]),
]

#: Rows Scryer answers differently; Clausal's answer is the one asserted.
#: * a when/2 waiting on both variables of an alias is ONE delay: its goal
#:   runs once (SWI-Prolog, SICStus), where Scryer keeps a copy per variable,
#:   prints it twice and runs it twice;
#: * the goals of three aliased variables print as one conjunction nested to
#:   the left in order, where Scryer's nesting follows the order of the
#:   aliases (``(a,(b,c))`` for ``Z = Y, Y = X``); the goals are the same and
#:   run in the same order.
CLAUSAL_ONLY_ROWS = [
    ("when(ground(f(X,Y)), w(g)), X = Y",
     ["X = Y, when(ground(f(X,X)),w(g))."]),
    ("when(ground(f(X,Y)), w(g)), X = Y, X = 1", ["g", "X = 1, Y = 1."]),
    ("when((nonvar(X);nonvar(Y)), w(g)), X = Y",
     ["X = Y, when((nonvar(X);nonvar(X)),w(g))."]),
    ("when((nonvar(X);nonvar(Y)), w(g)), X = Y, X = 1",
     ["g", "X = 1, Y = 1."]),
    # (Scryer agrees on this one: a re-check of ground/1 no longer
    # re-installs itself where it already waits, which ran g twice)
    ("when(ground(f(X,Y)), w(g)), X = 1, Y = 2", ["g", "X = 1, Y = 2."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), freeze(Z, w(c)), Z = Y, Y = X",
     ["X = Y, X = Z, freeze(X,((w(a),w(b)),w(c)))."]),
]

#: frozen/2 (Scryer has none) reads the merged goals back.
FROZEN_ROWS = [
    ("freeze(X, w(a)), freeze(Y, w(b)), X = Y, frozen(X, G)",
     ["X = Y, G = freeze(X,(w(a),w(b))), freeze(X,(w(a),w(b)))."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), X = Y, frozen(Y, G)",
     ["X = Y, G = freeze(X,(w(a),w(b))), freeze(X,(w(a),w(b)))."]),
    ("freeze(X, w(a)), freeze(Y, w(b)), (X = Y, fail ; true), frozen(X, G)",
     ["G = freeze(X,w(a)), freeze(X,w(a)), freeze(Y,w(b))."]),
]

_ALIAS = re.compile(r"\b([A-Z_]\w*) = ([A-Z_]\w*)(?=,|\.$)")

#: A goal put after each row, so the output splits back into rows.
_MARKER = "write(end_of_row), nl"


def _norm(line: str) -> str:
    """Take the library qualifiers off, and write each ``V = W`` alias
    with the two names sorted."""
    def sort(m):
        a, b = sorted((m.group(1), m.group(2)))
        return f"{a} = {b}"
    return _ALIAS.sub(sort, _QUALIFIER.sub("", line.strip()))


def _goals(rows):
    return [g for goal, _ in rows for g in (goal, _MARKER)]


def _by_row(rows, stdout):
    """The lines each row printed, normalised (:func:`_norm`)."""
    out, cur, lines = [], [], [ln for ln in map(_norm, stdout.splitlines())
                                if ln]
    i = 0
    while i < len(lines):
        if lines[i] == "end_of_row" and lines[i + 1:i + 2] == ["true."]:
            out.append(cur)
            cur = []
            i += 2
            continue
        cur.append(lines[i])
        i += 1
    if cur:
        out.append(cur)
    return out


def _clausal_rows(tmp_path, mode, suffix, rows):
    prog = tmp_path / f"prog{suffix}"
    prog.write_text(PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = "native"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    argv = [a for g in _goals(rows) for a in ("-g", g)]
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, mode, *argv, prog.name], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=300)
    return _by_row(rows, proc.stdout), proc.stderr


def _wrong(rows, got):
    assert len(got) == len(rows), got
    return [(g, want, have) for (g, want), have in zip(rows, got)
            if have != want]


@pytest.mark.parametrize("mode", ["c", "py"],
                         ids=["c_trampoline", "python_trampoline"])
@pytest.mark.parametrize("suffix", [".pl", ".clausal"],
                         ids=lambda s: s.lstrip("."))
@pytest.mark.parametrize("rows", [ROWS, CLAUSAL_ONLY_ROWS, FROZEN_ROWS],
                         ids=["oracle", "clausal_only", "frozen"])
def test_aliased_delays_merge(tmp_path, mode, suffix, rows):
    got, err = _clausal_rows(tmp_path, mode, suffix, rows)
    wrong = _wrong(rows, got)
    assert not wrong, (wrong, err)


def test_rows_match_scryers_toplevel(tmp_path):
    # The oracle's absence fails, as tests/iso/conftest.py's ``scryer``
    # fixture has it (checked here: that fixture is not always found when
    # this file is collected after files outside tests/iso).
    if not os.path.exists(_oracles.SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {_oracles.SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {_oracles.SCRYER}")
    prog = tmp_path / "prog.pl"
    prog.write_text(SCRYER_PRELUDE + PROGRAM)
    proc = _oracles.run_scryer(str(prog), _goals(ROWS), timeout=120)
    wrong = _wrong(ROWS, _by_row(ROWS, proc.stdout))
    assert not wrong, (wrong, proc.stderr)
