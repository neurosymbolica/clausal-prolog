"""A pending ``freeze/2`` or ``when/2`` is printed as the GOAL, as Scryer
prints it (operator ruling 2026-10-26): ``freeze(X,write(hi))``, a goal that
reads back and re-posts the delay.  Before, ``clausal FILE -g GOAL`` and the
``?-`` top level printed ``true.`` and hid it.

Scryer qualifies each residual with its library and each user goal with
``user:`` (``freeze:freeze(X,user:g)``); Clausal prints residuals in the
PLAIN form, as it prints ``dif(X,a)`` and ``X in 4..5`` (operator ruling
2026-10-24), so the Scryer oracle row compares with those qualifiers taken
off.  Otherwise the text is Scryer's, byte for byte: several freezes on one
variable are ONE ``freeze/2`` of their conjunction, left-nested in posting
order; a ``when/2`` keeps its whole condition, with what has been bound
since shown bound; ``when/2`` goals on one variable come newest first.

Every row runs the same goal through the real command against a ``.pl``
and a ``.clausal`` program, under the C and the pure-Python trampoline, and
through Scryer's own toplevel printer.  ``frozen/2`` (SWI's spelling;
Scryer has none) reads the same goals back as a term.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from tests import _oracles

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

PROGRAM = "g.\nh.\ni.\ng(_).\n"
SCRYER_PRELUDE = (":- use_module(library(freeze)).\n"
                  ":- use_module(library(when)).\n"
                  ":- use_module(library(dif)).\n")

#: (goal, the answer Scryer's toplevel prints, its qualifiers taken off).
ROWS = [
    ("freeze(X,true)", "freeze(X,true)."),
    ("freeze(X,write(hi))", "freeze(X,write(hi))."),
    ("freeze(X,g), freeze(X,h)", "freeze(X,(g,h))."),
    ("freeze(X,g), freeze(X,h), freeze(X,i)", "freeze(X,((g,h),i))."),
    ("freeze(X,g), freeze(Y,h)", "freeze(X,g), freeze(Y,h)."),
    ("when(nonvar(X), g(X))", "when(nonvar(X),g(X))."),
    ("when((nonvar(X);ground(Y)), g)", "when((nonvar(X);ground(Y)),g)."),
    ("when(ground(f(X,Y)), g)", "when(ground(f(X,Y)),g)."),
    ("when(ground(f(X,Y)), g), X = 1", "X = 1, when(ground(f(1,Y)),g)."),
    ("when((nonvar(X),nonvar(Y)), g)", "when((nonvar(X),nonvar(Y)),g)."),
    ("when((nonvar(X),nonvar(Y)), g), X = 1",
     "X = 1, when((nonvar(1),nonvar(Y)),g)."),
    ("when((nonvar(X);nonvar(Y)), g), X = 1", "X = 1."),
    ("when(ground(X), g)", "when(ground(X),g)."),
    ("dif(X,a), freeze(X,g)", "dif(X,a), freeze(X,g)."),
    ("freeze(X,g), Y = f(X)", "Y = f(X), freeze(X,g)."),
    ("freeze(X,true), X = 1", "X = 1."),
    ("freeze(X,(g;h))", "freeze(X,(g;h))."),
    ("freeze(X,(g,h))", "freeze(X,(g,h))."),
    ("freeze(X,Y = 1)", "freeze(X,Y=1)."),
    ("freeze(X,\\+ g)", "freeze(X,\\+g)."),
    ("L = [X,Y], freeze(X,true), freeze(Y,write(Y))",
     "L = [X,Y], freeze(X,true), freeze(Y,write(Y))."),
    ("freeze(X,g), when(nonvar(X),h)", "freeze(X,g), when(nonvar(X),h)."),
    ("when(nonvar(X),g), when(nonvar(X),h)",
     "when(nonvar(X),h), when(nonvar(X),g)."),
    ("freeze(X, call(g))", "freeze(X,call(g))."),
    ("G = g, freeze(X, G)", "G = g, freeze(X,g)."),
    ("freeze(X, findall(Z, g(Z), L))", "freeze(X,findall(Z,g(Z),L))."),
]

#: frozen/2 (Clausal and SWI; Scryer has no frozen/2): the same goals as a
#: term, ``true`` for none.
FROZEN_ROWS = [
    ("frozen(X, G)", "G = true."),
    ("frozen(1, G)", "G = true."),
    ("freeze(X,g), frozen(X,G)", "G = freeze(X,g), freeze(X,g)."),
    ("freeze(X,g), freeze(X,h), frozen(X,G)",
     "G = freeze(X,(g,h)), freeze(X,(g,h))."),
    ("freeze(X,g), freeze(Y,h), frozen(f(X,Y),G)",
     "G = (freeze(X,g),freeze(Y,h)), freeze(X,g), freeze(Y,h)."),
    ("when(nonvar(X),g), frozen(X,G)",
     "G = when(nonvar(X),g), when(nonvar(X),g)."),
    ("freeze(X,g), frozen(X,G), X = 1", "X = 1, G = freeze(1,g)."),
    ("freeze(X,g), frozen(X,G), X = 1, frozen(X, H)",
     "X = 1, G = freeze(1,g), H = true."),
    ("freeze(X, write(hi)), frozen(X, freeze(_, W))",
     "W = write(hi), freeze(X,write(hi))."),
]

_QUALIFIER = re.compile(r"\b(?:freeze|when|dif|user):")

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


def _clausal(tmp_path, mode, suffix, goals):
    prog = tmp_path / f"prog{suffix}"
    prog.write_text(PROGRAM)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = "native"
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    argv = [a for g in goals for a in ("-g", g)]
    proc = subprocess.run(
        [sys.executable, "-c", _CHILD, mode, *argv, prog.name], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=300)
    return proc.stdout.splitlines(), proc.stderr


@pytest.mark.parametrize("mode", ["c", "py"],
                         ids=["c_trampoline", "python_trampoline"])
@pytest.mark.parametrize("suffix", [".pl", ".clausal"],
                         ids=lambda s: s.lstrip("."))
@pytest.mark.parametrize("rows", [ROWS, FROZEN_ROWS], ids=["residual", "frozen"])
def test_pending_goals_print_as_goals(tmp_path, mode, suffix, rows):
    lines, err = _clausal(tmp_path, mode, suffix, [g for g, _ in rows])
    assert len(lines) == len(rows), (lines, err)
    wrong = [(g, want, got) for (g, want), got in zip(rows, lines)
             if got != want]
    assert not wrong, wrong


@pytest.mark.parametrize("mode", ["c", "py"],
                         ids=["c_trampoline", "python_trampoline"])
def test_backtracking_undoes_the_goal(tmp_path, mode):
    """The goal term is kept with the delay, on the trail: an answer after
    backtracking past the freeze has none, and a later freeze on a fresh
    branch shows only its own goal."""
    lines, err = _clausal(tmp_path, mode, ".pl", [
        "(freeze(X,g) ; true)",
        "(freeze(X,g) ; freeze(X,h))",
        "freeze(X,g), (freeze(X,h) ; true)",
        "(when(ground(f(X,Y)),g) ; true)",
    ])
    assert lines == [
        "freeze(X,g).", "true.",
        "freeze(X,g).", "freeze(X,h).",
        "freeze(X,(g,h)).", "freeze(X,g).",
        "when(ground(f(X,Y)),g).", "true.",
    ], err


def test_rows_match_scryers_toplevel(tmp_path, scryer):
    prog = tmp_path / "prog.pl"
    prog.write_text(SCRYER_PRELUDE + PROGRAM)
    proc = _oracles.run_scryer(str(prog), [g for g, _ in ROWS], timeout=120)
    lines = [_QUALIFIER.sub("", ln.strip())
             for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == len(ROWS), proc.stdout + proc.stderr
    wrong = [(g, want, got) for (g, want), got in zip(ROWS, lines)
             if got != want]
    assert not wrong, wrong
