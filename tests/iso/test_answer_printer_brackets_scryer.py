"""The ``clausal FILE -g GOAL`` answer printer writes each binding as
``writeq/1`` writes the right-hand operand of ``=`` (priority 699), as
Scryer's toplevel does.

An answer ``X = V`` is read back as the term ``X = V``, so ``V`` is an
operand of the infix ``=`` (xfx 700): an operator term of priority above
699 is bracketed (``T = (a,b)``, ``X = (a:-b)``, ``X = (a=b)``), and so is
a bare operator atom (``X = (-)``, ``X = (:-)``), exactly as ``writeq``
brackets them as operands (ISO 7.10.5).  The printer wrote the value at
priority 1200 and printed ``T = a,b``, which reads back as ``(T = a), b``.

The full stop that ends an answer is set off by a space when the answer
ends in a graphic character (``X = $ .``), or the two would read as one
token.

Every row runs the same goal through the real command against a ``.pl``
program (both front ends) and through Scryer's own toplevel printer.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests import _oracles

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: (goal, the answer Scryer's toplevel prints for it).
ROWS = [
    # Operator terms above 699 are bracketed.
    ("T = (a,b)", "T = (a,b)."),
    ("X = ((a,b),c)", "X = ((a,b),c)."),
    ("X = (a:-b)", "X = (a:-b)."),
    ("X = (a:-b,c)", "X = (a:-b,c)."),
    ("X = ((a:-b):-c)", "X = ((a:-b):-c)."),
    ("X = (a;b)", "X = (a;b)."),
    ("X = (a->b)", "X = (a->b)."),
    ("X = (a=b)", "X = (a=b)."),
    ("X = (1 = 2)", "X = (1=2)."),
    ("X = ((a=b)=c)", "X = ((a=b)=c)."),
    ("X = (\\+a)", "X = (\\+a)."),
    ("X = (\\+ \\+ a)", "X = (\\+ \\+a)."),
    ("X = (\\+ (a,b))", "X = (\\+ (a,b))."),
    ("X = (\\+ .)", "X = (\\+'.')."),
    # A bare operator atom is bracketed, whatever its priority.
    ("X = (-)", "X = (-)."),
    ("X = (+)", "X = (+)."),
    ("X = (\\)", "X = (\\)."),
    ("X = (\\+)", "X = (\\+)."),
    ("X = (:-)", "X = (:-)."),
    ("X = (?-)", "X = (?-)."),
    ("X = (-->)", "X = (-->)."),
    ("X = (->)", "X = (->)."),
    ("X = (;)", "X = (;)."),
    ("X = (',')", "X = (',')."),
    ("X = (=)", "X = (=)."),
    ("X = (is)", "X = (is)."),
    ("X = (mod)", "X = (mod)."),
    ("X = (rem)", "X = (rem)."),
    ("X = (^)", "X = (^)."),
    ("X = (**)", "X = (**)."),
    ("X = (//)", "X = (//)."),
    # At or below 699, or not an operator: unchanged.
    ("F = '.'", "F = '.'."),
    ("X = []", "X = []."),
    ("X = {}", "X = {}."),
    ("X = (a:b)", "X = a:b."),
    ("X = (1-2)", "X = 1-2."),
    ("X = - (1)", "X = - (1)."),
    ("X = -(-(1))", "X = - - (1)."),
    ("X = - (-)", "X = - (-)."),
    ("X = - (:-)", "X = - (:-)."),
    ("X = (- a)", "X = -a."),
    ("X = - - a", "X = - -a."),
    ("X = -(1)^2", "X = (- (1))^2."),
    ("X = (a- (-1))", "X = a- -1."),
    ("X = (- .)", "X = -'.'."),
    ("X = f(-)", "X = f(-)."),
    ("X = f(:-)", "X = f(:-)."),
    ("X = f((a:-b))", "X = f((a:-b))."),
    ("X = [(a,b)]", "X = [(a,b)]."),
    ("X = {a:-b}", "X = {a:-b}."),
    ("X = {a,b}", "X = {a,b}."),
    ("X = a*(b+c)", "X = a*(b+c)."),
    ("X = '|'", "X = '|'."),
    # The full stop after a graphic-character atom is set off by a space.
    ("X = $", "X = $ ."),
    ("X = @", "X = @ ."),
    # Several bindings, each bracketed on its own.
    ("X = (a,b), Y = (-), Z = 1", "X = (a,b), Y = (-), Z = 1."),
]

#: The operators in force when the answer is printed: the program's own
#: op/3 directives, and op/3 run by the goal itself (ISO 8.14.3: one table).
OPS_PROGRAM = ":- op(200, xfx, foo).\np.\n"
OPS_ROWS = [
    ("X = (foo)", "X = (foo)."),
    ("X = f(foo)", "X = f(foo)."),
    ("op(100, xfx, '.'), F = '.'", "F = ('.')."),
    ("op(9, fy, fy), X = (fy)", "X = (fy)."),
    ("op(9, fy, fz), X = - fz", "X = - (fz)."),
    ("op(0, xfx, foo), X = (foo)", "X = foo."),
]

FRONT_ENDS = ["translator", "native"]


def _clausal(tmp_path, frontend, goals, program="p.\n"):
    (tmp_path / "prog.pl").write_text(program)
    env = dict(os.environ)
    env["CLAUSAL_PL_FRONTEND"] = frontend
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    argv = [a for g in goals for a in ("-g", g)]
    proc = subprocess.run(
        [sys.executable, "-m", "clausal", *argv, "prog.pl"], cwd=tmp_path,
        env=env, capture_output=True, text=True, timeout=300)
    return proc.stdout.splitlines(), proc.stderr


@pytest.mark.parametrize("frontend", FRONT_ENDS)
def test_answer_bindings_are_written_as_operands_of_equals(tmp_path, frontend):
    lines, err = _clausal(tmp_path, frontend, [g for g, _ in ROWS])
    assert len(lines) == len(ROWS), err
    wrong = [(g, want, got) for (g, want), got in zip(ROWS, lines)
             if got != want]
    assert not wrong, wrong


def test_rows_match_scryers_toplevel(tmp_path, scryer):
    prog = tmp_path / "prog.pl"
    prog.write_text("p.\n")
    proc = _oracles.run_scryer(str(prog), [g for g, _ in ROWS], timeout=120)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert len(lines) == len(ROWS), proc.stdout + proc.stderr
    wrong = [(g, want, got) for (g, want), got in zip(ROWS, lines)
             if got != want]
    assert not wrong, wrong


# Native front end only: the translator does not apply a file's op/3
# directives to the run-time table, so writeq/1 there misses them as well
# (todo/translator-pl-op-directives-miss-the-run-time-table-2026-10-24.md).
@pytest.mark.parametrize("goal, want", OPS_ROWS, ids=[g for g, _ in OPS_ROWS])
def test_answer_uses_the_operators_in_force(tmp_path, goal, want):
    lines, err = _clausal(tmp_path, "native", [goal], OPS_PROGRAM)
    assert lines == [want], err


@pytest.mark.parametrize("goal, want", OPS_ROWS, ids=[g for g, _ in OPS_ROWS])
def test_operator_rows_match_scryers_toplevel(tmp_path, scryer, goal, want):
    prog = tmp_path / "prog.pl"
    prog.write_text(OPS_PROGRAM)
    proc = _oracles.run_scryer(str(prog), [goal], timeout=60)
    lines = [ln.strip() for ln in proc.stdout.splitlines() if ln.strip()]
    assert lines == [want], proc.stdout + proc.stderr
