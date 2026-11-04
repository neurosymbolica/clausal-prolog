"""copy_term/3 and call_residue_vars/2 against Scryer.

``copy_term(Term, Copy, Gs)``: Copy is Term with fresh variables that carry
no attributes, and Gs the goals that put back the constraints of Term's
variables on Copy's.  ``call_residue_vars(Goal, Vars)``: the variables
that got an attribute during Goal, also those no argument reaches.

Each row is a goal, the answer Clausal prints for it (from a ``.pl`` and a
``.clausal`` program, under the C and the pure-Python trampoline), the
answer Scryer's own toplevel printer gives (the build in
``tests/_oracles.py``, with library(clpq)), and why the two differ, or None
where they are the same once Scryer's module qualifiers are taken off
(Clausal prints residual goals plain: operator rulings 2026-10-24 and
2026-10-26).  The goals are the ones the answer printers show for the same
constraints, so Clausal's CLP(Z) forms (``X #< Y``, ``scalar_product/4``)
stay its own.
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

PROGRAM = """\
:- use_module(library(dif)).
:- use_module(library(freeze)).
:- use_module(library(when)).
:- use_module(library(clpz)).
:- use_module(library(clpq)).
:- use_module(library(lists)).
:- use_module(library(iso_ext)).
p :- q(_).
q(X) :- dif(X, a).
"""

#: Clausal has no library(clpb) to load: sat/1 is a builtin.
SCRYER_PROGRAM = PROGRAM + ":- use_module(library(clpb)).\n"

_ORDER = "Clausal lists dif/2 goals, then CLP(Z), then freeze/when"
_CLPZ_FORM = "Clausal's CLP(Z) goal, as its printer writes it"
_CLPB_FORM = "a formula of the BDD, not Scryer's algebraic normal form"
_CLPQ_BRACES = ("a callable {}/1 goal; Scryer's clpq hook gives the bare "
                "relation, which is no CLP(Q) goal")

#: (goal, Clausal's answer, Scryer's answer, why they differ or None)
ROWS = [
    ("dif(X,a), copy_term(X,Y,Gs)",
     "Gs = [dif(Y,a)], dif(X,a).",
     "Gs = [dif:dif(Y,a)], dif:dif(X,a).", None),
    ("dif(X,Z), copy_term(X,Y,Gs)",
     "Gs = [dif(Y,_A)], dif(X,Z).",
     "Gs = [dif:dif(Y,_A)], dif:dif(X,Z).", None),
    ("dif(f(X,Z),f(a,b)), copy_term(X,Y,Gs)",
     "Gs = [dif(f(Y,_A),f(a,b))], dif(f(X,Z),f(a,b)).",
     "Gs = [dif:dif(f(Y,_A),f(a,b))], dif:dif(f(X,Z),f(a,b)).", None),
    ("dif(X,Z), copy_term(f(X,Z,X),Y,Gs)",
     "Y = f(_A,_B,_A), Gs = [dif(_A,_B)], dif(X,Z).",
     "Y = f(_A,_B,_A), Gs = [dif:dif(_A,_B)], dif:dif(X,Z).", None),
    ("freeze(X,write(hi)), copy_term(X,Y,Gs)",
     "Gs = [freeze(Y,write(hi))], freeze(X,write(hi)).",
     "Gs = [freeze:freeze(Y,write(hi))], freeze:freeze(X,write(hi)).", None),
    ("freeze(X,g), freeze(X,h), copy_term(X,Y,Gs)",
     "Gs = [freeze(Y,(g,h))], freeze(X,(g,h)).",
     "Gs = [freeze:freeze(Y,(user:g,user:h))], "
     "freeze:freeze(X,(user:g,user:h)).", None),
    ("when(ground(f(X,Z)),g(X)), copy_term(X,Y,Gs)",
     "Gs = [when(ground(f(Y,_A)),g(Y))], when(ground(f(X,Z)),g(X)).",
     "Gs = [when:when(ground(f(Y,_A)),user:g(Y))], "
     "when:when(ground(f(X,Z)),user:g(X)).", None),
    ("when((nonvar(X);ground(Z)),g), copy_term(X-Z,Y,Gs)",
     "Y = _A-_B, Gs = [when((nonvar(_A);ground(_B)),g)], "
     "when((nonvar(X);ground(Z)),g).",
     "Y = _A-_B, Gs = [when:when((nonvar(_A);ground(_B)),user:g)], "
     "when:when((nonvar(X);ground(Z)),user:g).", None),
    ("X in 1..3, copy_term(X,Y,Gs)",
     "Gs = [Y in 1..3], X in 1..3.",
     "Gs = [clpz:(Y in 1..3)], clpz:(X in 1..3).", None),
    ("X in 1..3\\/5..7, copy_term(X,Y,Gs)",
     "Gs = [Y in 1..3\\/5..7], X in 1..3\\/5..7.",
     "Gs = [clpz:(Y in 1..3\\/5..7)], clpz:(X in 1..3\\/5..7).", None),
    ("X #> 3, copy_term(X,Y,Gs)",
     "Gs = [Y in 4..sup], X in 4..sup.",
     "Gs = [clpz:(Y in 4..sup)], clpz:(X in 4..sup).", None),
    ("X #= A+B, copy_term(X,Y,Gs)",
     "Gs = [scalar_product([1,-1,-1],[Y,_A,_B],#=,0)], "
     "scalar_product([1,-1,-1],[X,A,B],#=,0).",
     "Gs = [clpz:(_A+_B#=Y)], clpz:(A+B#=X).", _CLPZ_FORM),
    ("X #< Z, copy_term(X-Z,Y,Gs)",
     "Y = _A-_B, Gs = [_A#<_B], X #< Z.",
     "Y = _A-_B, Gs = [clpz:(_A#=<_B+ -1)], clpz:(X#=<Z+ -1).", _CLPZ_FORM),
    ("X #< Z, copy_term(X,Y,Gs)",
     "Gs = [Y#<_A], X #< Z.",
     "Gs = [clpz:(Y#=<_A+ -1)], clpz:(X#=<Z+ -1).", _CLPZ_FORM),
    ("all_different([X,Z,W]), copy_term([X,Z,W],Y,Gs)",
     "Y = [_A,_B,_C], Gs = [all_different([_A,_B,_C])], "
     "all_different([X,Z,W]).",
     "Y = [_A,_B,_C], Gs = [clpz:all_different([_A,_B,_C])], "
     "clpz:all_different([X,Z,W]).", None),
    ("X in 0..1, all_different([X,Z]), copy_term([X,Z],Y,Gs)",
     "Y = [_A,_B], Gs = [_A in 0..1,all_different([_A,_B])], "
     "X in 0..1, all_different([X,Z]).",
     "Y = [_A,_B], Gs = [clpz:(_A in 0..1),clpz:all_different([_A,_B])], "
     "clpz:(X in 0..1), clpz:all_different([X,Z]).", None),
    ("sat(X+Z), copy_term([X,Z],Y,Gs)",
     "Y = [_A,_B], Gs = [sat(_A+_B)], sat(X+Z).",
     "Y = [_A,_B], Gs = [clpb:sat(_A=\\=_A*_B#_B)], clpb:sat(X=\\=X*Z#Z).",
     _CLPB_FORM),
    ("sat(X*Z), copy_term([X,Z],Y,Gs)",
     "X = 1, Z = 1, Y = [1,1], Gs = [].",
     "X = 1, Z = 1, Y = [1,1], Gs = [].", None),
    ("sat(X=\\=Z), copy_term(X-Z,Y,Gs)",
     "Y = _A-_B, Gs = [sat(_A* ~(_B)+ ~(_A)*_B)], sat(X* ~(Z)+ ~(X)*Z).",
     "Y = _A-_B, Gs = [clpb:sat(_A=\\=_B)], clpb:sat(X=\\=Z).", _CLPB_FORM),
    ("{X >= 2}, copy_term(X,Y,Gs)",
     "Gs = [{Y>=2}], {X >= 2}.",
     "Gs = [Y>=2], X>=2.", _CLPQ_BRACES),
    ("{X + Z = 3}, copy_term(X-Z,Y,Gs)",
     "Y = _A-_B, Gs = [{_A+_B=3}], {X + Z = 3}.",
     None,       # Scryer: Gs = [], and the toplevel prints a stray binding
     "Scryer's clpq copy_term/3 loses the equation (Gs = [])"),
    ("dif(X,a), X in 0..5, freeze(X,g), copy_term(X,Y,Gs)",
     "Gs = [dif(Y,a),Y in 0..5,freeze(Y,g)], dif(X,a), X in 0..5, "
     "freeze(X,g).",
     "Gs = [clpz:(Y in 0..5),dif:dif(Y,a),freeze:freeze(Y,user:g)], "
     "clpz:(X in 0..5), dif:dif(X,a), freeze:freeze(X,user:g).", _ORDER),
    ("X = f(X,V), dif(V,a), copy_term(X,Y,Gs)",
     "X = f(...,V), Y = f(...,_A), Gs = [dif(_A,a)], dif(V,a).",
     "X = f(X,V), Y = f(Y,_A), Gs = [dif:dif(_A,a)], dif:dif(V,a).",
     "the printers write a cycle differently; the copy is the same"),
    ("dif(V,a), copy_term(f(W),Y,Gs)",
     "Y = f(_A), Gs = [], dif(V,a).",
     "Y = f(_A), Gs = [], dif:dif(V,a).", None),
    ("copy_term(f(X,a),Y,Gs)",
     "Y = f(_A,a), Gs = [].",
     "Y = f(_A,a), Gs = [].", None),
    ("dif(X,a), copy_term(X,Y,Gs), Y = a",
     "Y = a, Gs = [dif(a,a)], dif(X,a).",
     "Y = a, Gs = [dif:dif(a,a)], dif:dif(X,a).", None),
    ("X #> 3, copy_term(X,Y,Gs), Y = 1",
     "Y = 1, Gs = [1 in 4..sup], X in 4..sup.",
     "Y = 1, Gs = [clpz:(1 in 4..sup)], clpz:(X in 4..sup).", None),
    ("call_residue_vars(dif(X,a), Vs)",
     "Vs = [X], dif(X,a).",
     "Vs = [X], dif:dif(X,a).", None),
    ("call_residue_vars((dif(Z,a), X = 1), Vs)",
     "X = 1, Vs = [Z], dif(Z,a).",
     "X = 1, Vs = [Z], dif:dif(Z,a).", None),
    ("call_residue_vars(X #> 3, Vs)",
     "Vs = [X], X in 4..sup.",
     "Vs = [X], clpz:(X in 4..sup).", None),
    ("call_residue_vars((X #> 3, X = 4), Vs)",
     "X = 4, Vs = [].",
     "X = 4, Vs = [].", None),
    ("call_residue_vars(freeze(X,g), Vs)",
     "Vs = [X], freeze(X,g).",
     "Vs = [X], freeze:freeze(X,user:g).", None),
    ("call_residue_vars(true, Vs)",
     "Vs = [].",
     "Vs = [].", None),
    ("call_residue_vars((X in 1..2, Y #> X), Vs)",
     "Vs = [X,Y], X in 1..2, Y in 2..sup, X #< Y.",
     "Vs = [X,Y], clpz:(X in 1..2), clpz:(X#=<Y+ -1), clpz:(Y in 2..sup).",
     _CLPZ_FORM),
    ("call_residue_vars(sat(A+B), Vs)",
     "Vs = [A,B], sat(A+B).",
     "Vs = [A,B,_A], clpb:sat(A=\\=A*B#B).",
     "Scryer's clpb keeps an internal attributed variable"),
    ("call_residue_vars({A >= 2}, Vs)",
     "Vs = [A], {A >= 2}.",
     "Vs = [A,_A], A>=2.",
     "Scryer's clpq keeps an internal attributed variable"),
    ("call_residue_vars(p, Vs)",
     "Vs = [_A], dif(_A,a).",
     "Vs = [_A], dif:dif(_A,a).", None),
]

#: (goal, Clausal's error, Scryer's): only the context differs.
ERROR_ROWS = [
    ("copy_term(X,Y,foo)",
     "error(type_error(list,foo),copy_term/3)",
     "error(type_error(list,foo),can_be/2)."),
    ("call_residue_vars(true, foo)",
     "error(type_error(list,foo),call_residue_vars/2)",
     "error(type_error(list,foo),can_be/2)."),
]

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
        env=env, capture_output=True, text=True, timeout=600)
    return proc.stdout.splitlines(), proc.stderr


def _unqualified(text: str) -> str:
    """Scryer's answer with its module qualifiers taken off:
    ``dif:dif(X,a)`` is ``dif(X,a)``, ``clpz:(X in 1..3)`` is
    ``X in 1..3``."""
    text = re.sub(r"\b(?:dif|freeze|when|user|clpb):", "", text)
    while "clpz:(" in text:
        start = text.index("clpz:(")
        depth, i = 0, start + len("clpz:")
        while True:
            depth += {"(": 1, ")": -1}.get(text[i], 0)
            if depth == 0:
                break
            i += 1
        text = text[:start] + text[start + len("clpz:(") : i] + text[i + 1 :]
    return text.replace("clpz:", "")


@pytest.mark.parametrize("mode", ["c", "py"],
                         ids=["c_trampoline", "python_trampoline"])
@pytest.mark.parametrize("suffix", [".pl", ".clausal"],
                         ids=lambda s: s.lstrip("."))
def test_clausal_answers(tmp_path, mode, suffix):
    lines, err = _clausal(tmp_path, mode, suffix, [g for g, *_ in ROWS])
    assert len(lines) == len(ROWS), (lines, err)
    wrong = [(g, want, got) for (g, want, *_), got in zip(ROWS, lines)
             if got != want]
    assert not wrong, wrong


@pytest.mark.parametrize("suffix", [".pl", ".clausal"],
                         ids=lambda s: s.lstrip("."))
def test_clausal_errors(tmp_path, suffix):
    wrong = []
    for goal, want, _ in ERROR_ROWS:
        _, err = _clausal(tmp_path, "c", suffix, [goal])
        if want not in err:
            wrong.append((goal, want, err))
    assert not wrong, wrong


def _scryer(tmp_path, goal):
    prog = tmp_path / "prog.pl"
    prog.write_text(SCRYER_PROGRAM)
    proc = _oracles.run_scryer(prog, [goal], timeout=120)
    return " ".join(line.strip() for line in proc.stdout.splitlines())


def test_scryer_answers(tmp_path):
    """Scryer still answers as the table records, and the rows marked the
    same are the same once its qualifiers are off."""
    if not os.path.exists(_oracles.SCRYER):
        pytest.skip(f"no Scryer at {_oracles.SCRYER}")
    wrong = []
    for goal, clausal, scryer, why in ROWS:
        got = _scryer(tmp_path, goal)
        if scryer is not None and got != scryer:
            wrong.append(("scryer moved", goal, scryer, got))
        if why is None and _unqualified(got) != clausal:
            wrong.append(("differs", goal, clausal, _unqualified(got)))
    for goal, _, scryer in ERROR_ROWS:
        got = _scryer(tmp_path, goal)
        if got != scryer:
            wrong.append(("scryer moved", goal, scryer, got))
    assert not wrong, wrong
