"""Bugs the differential fuzzer (``tests/fuzz/scryer_diff.py``) found
against Scryer, one row each (operator ruling 2026-10-24: a
non-conformity is a bug).

* A partial list ``[B|A]`` is the compound ``'.'(B, A)`` (ISO 6.3.5):
  ``functor/3``, ``arg/3`` and ``=..`` failed on it, and the standard
  order put it after every other term, so ``compare(R, [B|A], [1|A])``
  gave ``>``.  A proper list against an improper one was compared element
  against tail (``[a,b]`` against ``[a|c]`` gave ``<``; ISO, by
  ``'.'(b,[])`` against ``c``, ``>``).
* A cyclic term that closes through a partial list (``B = g([B|A])``,
  ``X = [a|T], T = [X|T]``) overflowed the stack in ``writeq/1``,
  ``=..``, ``functor/3``, ``arg/3``, ``dif/2`` and ``=/2``: the walk of
  the list walked each element, and the element led back to the list.
* ``[X|C] = [A,B|C]`` failed: a partial list against a longer one ending
  in the same tail was refused as cyclic, from before the engine had
  rational trees (Scryer: ``C = [B|C]``).
* ``==/2`` and ``\\==/2`` tried their unification on a trail that ran the
  goals it woke: ``freeze(D, write(t1)), f(A,D) \\== f(A,g(B))`` printed.
* ``dif/2``'s wake-up hook tried its pair with the pair's own variables'
  dif hooks running, which met the pair with its two sides made one and
  said "violated", so the try failed and the pair was dropped as if it
  could never be violated: a copied ``dif(_A, E)`` lost.  And the answer
  printer showed a pair a binding had made true for good
  (``dif(C, [a|B]), C = 1``), missed the variables of a partial list in
  the answer (``E1 = [_A|_B]``, the dif on ``_A``) and those reached only
  through another constraint, and bracketed an operator atom argument
  (``dif(A,(=))``).

Every row runs through the real command against a ``.pl`` and a
``.clausal`` program, under the C and the pure-Python trampoline and the
pure-Python dif twin; the oracle rows run through Scryer's toplevel too
(its ``dif:`` qualifier taken off, fresh variables renamed in order).
Where Scryer orders lists against ISO, the row is checked against Trealla.
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

SCRYER_PRELUDE = (":- use_module(library(dif)).\n"
                  ":- use_module(library(freeze)).\n"
                  ":- use_module(library(when)).\n"
                  ":- use_module(library(lists)).\n")

PROGRAM = "w(X) :- write(X), nl.\n"

_CHILD = textwrap.dedent(r'''
    import sys
    if sys.argv[1] == "py":
        sys.modules["clausal.logic.runtime._trampoline"] = None
        sys.modules["clausal.logic._tabling_core"] = None
    if sys.argv[1] == "difpy":
        sys.modules["clausal.logic._constraints_dif"] = None
    import clausal.logic.trampoline as tr
    want = ("clausal.logic._trampoline_py" if sys.argv[1] == "py"
            else "clausal.logic.runtime._trampoline")
    assert tr.trampoline.__module__ == want, tr.trampoline.__module__
    if sys.argv[1] == "difpy":
        import clausal.logic.constraints as c
        assert not c._USE_C_DIF
    from clausal.cli import main
    sys.exit(main(sys.argv[2:]))
''')

#: (goal, the lines it prints: its output, then its answer).
ROWS = [
    # -- a partial list is the compound '.'/2
    ("compare(R,[B|A],[1|A])", ["R = (<)."]),
    ("compare(R,[a|A],f(a,b))", ["R = (<)."]),
    ("compare(R,[A|B],[A|1])", ["R = (<)."]),
    ("compare(R,g(x),[a|A])", ["R = (<)."]),
    ("[B|A] =.. L", ["L = ['.',B,A]."]),
    ("[B,C|A] =.. L", ["L = ['.',B,[C|A]]."]),
    ("functor([a|T],N,A)", ["N = '.', A = 2."]),
    ("arg(1,[a|T],X)", ["X = a."]),
    ("arg(2,[a,b|T],X)", ["X = [b|T]."]),
    # -- a cycle closed through a partial list
    ("X = [a|T], T = [X|T], X =.. [F|_], w(F), fail ; true", [".", "true."]),
    ("X = [a|T], T = [X|T], functor(X,N,A), w(N/A), fail ; true",
     [". /2", "true."]),
    ("B = g([B|A]), writeq(B), nl, fail ; true", ["g([...|_1])", "true."]),
    ("B = f(f(A,A),[B|A]), writeq(B), nl, fail ; true",
     ["f(f(_1,_1),[...|_1])", "true."]),
    ("B = [B|E], dif(1,B), w(ok), fail ; true", ["ok", "true."]),
    ("B = [[B|E]|g(A)], dif(1,[B|E]), w(ok), fail ; true", ["ok", "true."]),
    ("dif(A,g(B)), A = B, B = [A|B], w(ok), fail ; true", ["ok", "true."]),
    # a partial list against a longer one with the same tail: a cycle
    ("[X|C] = [A,B|C], C = [P,Q|R], w(ok), fail ; true", ["ok", "true."]),
    ("[X|C] = [A,B|C], C = [P,Q|R], P == B, Q == B, R == C, w(ok), fail ;"
     " true", ["ok", "true."]),
    ("findall(1, [[A|A]|C] = [A,B|C], L)", ["L = [1]."]),
    # ==/2 and \==/2 decide without waking a delayed goal
    ("freeze(D,w(t1)), f(A,D) \\== f(A,g(B)), fail ; true", ["true."]),
    ("when(nonvar(B),w(t1)), f(f(A,A),C) == f(B,1) ; true", ["true."]),
    # -- the dif/2 residuals an answer shows
    ("dif(C,[a|B]), C = 1", ["C = 1."]),
    ("dif(C,f(a,B)), C = 1", ["C = 1."]),
    ("dif(f(C,B),f(1,2)), C = 1", ["C = 1, dif(f(1,B),f(1,2))."]),
    ("dif(C,[C|[B|B]]), C = 1", ["C = 1."]),
    ("dif(A,E1), copy_term(E1,E2)", ["dif(A,E1), dif(_1,E2)."]),
    ("dif(A,b), copy_term([A|B],E1)",
     ["E1 = [_1|_2], dif(A,b), dif(_1,b)."]),
    ("dif(B,f(A)), dif(E1,B), copy_term(A,E2)",
     ["dif(B,f(A)), dif(E1,B), dif(_1,f(E2)), dif(_2,_1)."]),
    ("compare(E,b,b), dif(A,E)", ["E = (=), dif(A,=)."]),
    ("dif(A,-)", ["dif(A,-)."]),
]

#: Rows where Scryer orders a list against a list with another tail
#: against ISO 7.2.1 (it says ``>`` and ``<``); Trealla is the check.
TREALLA_ROWS = [
    ("compare(R,[a|A],[a])", ["R = (<)."], "<"),
    ("compare(R,[a,b],[a|c])", ["R = (>)."], ">"),
    ("compare(R,[a|T],[a,b])", ["R = (<)."], "<"),
    ("compare(R,[a|f(x,y)],[a,b])", ["R = (>)."], ">"),
    ("X = [a|X], compare(R,X,[a|B])", None, ">"),
]

_FRESH = re.compile(r"(?<![\w'])_[A-Z0-9]\w*")
_QUALIFIER = re.compile(r"\bdif:")


def _norm(line: str) -> str:
    """Take the qualifier off and rename fresh variables ``_1``, ``_2``."""
    names: dict = {}

    def sub(m):
        return names.setdefault(m.group(0), f"_{len(names) + 1}")
    return _FRESH.sub(sub, _QUALIFIER.sub("", line.strip()))


_MARKER = "write(end_of_row), nl"


def _goals(rows):
    return [g for goal, *_ in rows for g in (goal, _MARKER)]


def _by_row(stdout):
    out, cur = [], []
    lines = [ln for ln in map(_norm, stdout.splitlines()) if ln]
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
    return _by_row(proc.stdout), proc.stderr


def _wrong(rows, got):
    assert len(got) == len(rows), got
    return [(row[0], row[1], have) for row, have in zip(rows, got)
            if row[1] is not None and have != row[1]]


@pytest.mark.parametrize("mode", ["c", "py", "difpy"],
                         ids=["c_trampoline", "python_trampoline",
                              "python_dif_twin"])
@pytest.mark.parametrize("suffix", [".pl", ".clausal"],
                         ids=lambda s: s.lstrip("."))
@pytest.mark.parametrize("rows", [ROWS, TREALLA_ROWS],
                         ids=["oracle", "iso_list_order"])
def test_fuzz_findings(tmp_path, mode, suffix, rows):
    got, err = _clausal_rows(tmp_path, mode, suffix, rows)
    wrong = _wrong(rows, got)
    assert not wrong, (wrong, err)


def test_rows_match_scryers_toplevel(tmp_path):
    if not os.path.exists(_oracles.SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {_oracles.SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {_oracles.SCRYER}")
    prog = tmp_path / "prog.pl"
    prog.write_text(SCRYER_PRELUDE + PROGRAM)
    proc = _oracles.run_scryer(str(prog), _goals(ROWS), timeout=120)
    wrong = _wrong(ROWS, _by_row(proc.stdout))
    assert not wrong, (wrong, proc.stderr)


def test_list_order_rows_match_trealla(tmp_path):
    if not os.path.exists(_oracles.TREALLA):
        pytest.skip(f"trealla not built at {_oracles.TREALLA}")
    for goal, _, want in TREALLA_ROWS:
        proc = subprocess.run(
            [_oracles.TREALLA, "-q", "-g", f"{goal}, write(R), nl, halt"],
            capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL)
        assert proc.stdout.strip() == want, (goal, proc.stdout, proc.stderr)


def test_scryer_orders_these_lists_otherwise(tmp_path):
    """Recorded, not asserted for Clausal: Scryer's answers on the
    TREALLA_ROWS, so a Scryer that comes to agree is noticed."""
    if not os.path.exists(_oracles.SCRYER):
        pytest.skip(f"scryer not built at {_oracles.SCRYER}")
    prog = tmp_path / "prog.pl"
    prog.write_text(PROGRAM)
    goals = [f"{g}, write(R), nl, fail ; true" for g, _, _ in TREALLA_ROWS]
    proc = _oracles.run_scryer(str(prog), goals, timeout=60)
    said = [ln.strip() for ln in proc.stdout.splitlines()
            if ln.strip() in ("<", ">", "=")]
    assert said == [">", "<", ">", "<", "<"], proc.stdout
