"""Posting a CYCLIC expression to CLP(Z), row by row against Scryer's clpz.

There is no occurs check, so ``X = X+1`` (the seam's ``X is X + 1``) builds
a rational tree.  Posting it used to loop forever (the seam: the walk in
``clpfd._fd_int_term`` went round the cycle) or overflow the stack (``.pl``:
``resource_error(stack)``).  Scryer's clpz refuses it, and so does the engine
now (operator ruling 2026-11-04, "type_error if Scryer gives one": Scryer
gives a domain_error here, so the engine follows Scryer).

Scryer's rule, read off the rows below:

* a comparison (``#=``, ``#\\=``, ``#<``, ...): a cyclic SIDE is
  ``domain_error(clpz_expression, Side)`` -- the whole side as posted, not
  the subterm the cycle closes on (``Y #= X*2`` names ``X*2``).  The left
  side is checked first, and a cycle in either side comes before a bad leaf
  in either side (``a #= X`` names X's cycle, not ``a``);
* a reified connective (``#<==>``, ``#==>``, ``#\\/``, ``#\\``, ``#=/3`` ...):
  a cyclic OPERAND is ``domain_error(clpz_reifiable_expression, Operand)``,
  operands checked left to right, each before it is descended into (a bad
  leaf in an earlier operand comes first);
* ``in/2``, ``labeling/2``, ``sum/3``, ``zcompare/3``: a cyclic term where an
  integer or variable belongs is ``type_error(integer, Term)``, as for any
  compound there; a ``labeling/2`` objective is a clpz expression.

The culprit is compared with Scryer's text.  The context is the engine's,
as for every other clpz expression error: the builtin's indicator on
``.pl``/``.clausal``, an unbound variable on the seam (Scryer's is
``unknown(Culprit)-1``).

Every row runs under a hard time limit (SIGALRM), so a regression fails
instead of hanging the suite.
"""
from __future__ import annotations

import os
import re
import signal

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from clausal.terms import term_writeq

from tests._oracles import run_scryer
from tests._suffix import SEAM

_CE = "clpz_expression"
_CR = "clpz_reifiable_expression"

# The engine's context as it prints: the builtin's indicator (``#\/`` and
# ``#/\`` print an unbound one, as for their other errors today).
_EQ, _LT, _NE = " #= /2", " #< /2", " #\\= /2"
_IFF, _IMP, _NOT, _OR, _AND = " #<==> /2", " #==> /2", " #\\ /1", "_", "_"

# (row, goal, error kind, Scryer's culprit, the engine's context, the
#  engine's culprit text where its writer prints the same term differently:
#  canonical #=(A,B) for clpz's operators, a different depth for a cycle)
ROWS = [
    # -- comparisons: the cyclic side --
    ("p1", "X = X+1, X #= 1", _CE, "... +1", _EQ),
    ("p2", "X = 1+X, X #< 3", _CE, "1+ ... +1", _LT, "1+ ..."),
    ("p3", "X = f(X), X #= 1", _CE, "f(...)", _EQ),
    ("p4", "X = X+1, 1 #= X", _CE, "... +1", _EQ),
    ("p5", "X = X+1, X #\\= 1", _CE, "... +1", _NE),
    ("p6", "X = X*_, X #= 1", _CE, "... *_", _EQ),
    ("p9", "X = X+1, _ #= X*2", _CE, "(... +1)*2", _EQ),
    ("p10", "X = 1+X, _ #= 3 + X", _CE, "3+(1+ ...)", _EQ),
    ("p11", "X = X+1, X #>= _", _CE, "... +1", " #>= /2"),
    ("p11b", "X = X+1, X #> _", _CE, "... +1", " #> /2"),
    ("p11c", "X = X+1, X #=< _", _CE, "... +1", " #=< /2"),
    ("p12", "X = abs(X), X #= 1", _CE, "abs(...)", _EQ),
    ("p13", "X = X*X, X #= 1", _CE, "... * ...", _EQ),
    ("p14", "X = Y+1, Y = X*2, X #= 1", _CE, "... *2+1", _EQ),
    ("p15", "X = f(X)+1, X #= 1", _CE, "f(...)+1", _EQ),
    ("p20", "X = max(X,1), X #= 1", _CE, "max(...,1)", _EQ),
    ("p21", "X = X // 2, _ #= X", _CE, "... //2", _EQ),
    ("p22", "X = 2^X, _ #= X", _CE, "2^ ...", _EQ),
    ("p23", "X = X+1, Y #= 1, Y #= X", _CE, "... +1", _EQ),
    ("p24", "X = _+X, X #= 1", _CE, "_+ ...", _EQ),
    # a cycle comes before a bad leaf, in either side
    ("p25", "X = a+X, X #= 1", _CE, "a+ ...", _EQ),
    ("c5", "X = X+1, X #= a", _CE, "... +1", _EQ),
    ("c6", "X = X+1, a #= X", _CE, "... +1", _EQ),
    ("c10", "X = X+1, X #= X", _CE, "... +1", _EQ),
    ("c11", "X = X+1, Z = Z*2, Z #= X", _CE, "... *2", _EQ),
    ("c12", "X = X + 1.5, X #= 1", _CE, "... +1.5", _EQ),
    ("a12", "X = X+1, Y in 1..3, Y #= X", _CE, "... +1", _EQ),
    # -- reified: the cyclic operand of a connective --
    ("p7", "X = X+1, _ #<==> (X #= 1)", _CR, "... +1#=1", _IFF, "#=(... +1,1)"),
    ("p8", "X = X+1, (X #= 1) #==> _", _CR, "... +1#=1", _IMP, "#=(... +1,1)"),
    ("p18", "X = X+1, #\\ (X #= 1)", _CR, "... +1#=1", _NOT, "#=(... +1,1)"),
    ("p19", "X = X+1, (X #= 1) #\\/ (_ #= 1)", _CR, "... +1#=1", _OR,
     "#=(... +1,1)"),
    ("a6", "X = X+1, _ #<==> (_ #= 1 + X)", _CR, "_#=1+(... +1)", _IFF,
     "#=(_,1+(... +1))"),
    ("a7", "X = X+1, _ #<==> (1 #< X)", _CR, "1#< ... +1", _IFF, "#<(1,... +1)"),
    ("a8", "X = X+1, _ #<==> X", _CR, "... +1", _IFF),
    ("a9", "X = (X #= 1), _ #<==> X", _CR, "... #=1", _IFF, "#=(...,1)"),
    ("a10", "X = (X #/\\ _), X", _CR, "... #/\\_", _AND, "#/\\(...,_)"),
    # the OUTERMOST cyclic operand
    ("c1", "X = X+1, _ #<==> (_ #/\\ (_ #= X))", _CR, "_#/\\_#= ... +1", _IFF,
     "#/\\(_,#=(_,... +1))"),
    ("c2", "X = X+1, (_ #= X) #\\/ (_ #= a)", _CR, "_#= ... +1", _OR,
     "#=(_,... +1)"),
    # an earlier operand's bad leaf comes first
    ("c3", "X = X+1, (_ #= a) #\\/ (_ #= X)", _CE, "a", _OR),
    ("c4", "X = X+1, #\\ (_ #= X)", _CR, "_#= ... +1", _NOT, "#=(_,... +1)"),
    ("c9", "X = X+1, _ #<==> (X #= a)", _CR, "... +1#=a", _IFF, "#=(... +1,a)"),
    ("c13", "X = X+1, B #<==> (_ #= 1), B #<==> (_ #= X)", _CR, "_#= ... +1",
     _IFF, "#=(_,... +1)"),
    # reif's #=/3 and #</3, and if_/3 over them
    ("i1", "X = X+1, if_(X #= 1, true, true)", _CR, "... +1#=1", _IFF,
     "#=(... +1,1)"),
    ("i2", "X = X+1, if_(X #< 1, true, true)", _CR, "... +1#<1", _IFF,
     "#<(... +1,1)"),
    ("i3", "X = X+1, #=(X, 1, _)", _CR, "... +1#=1", _IFF, "#=(... +1,1)"),
    ("i4", "X = X+1, if_(1 #= X, true, true)", _CR, "1#= ... +1", _IFF,
     "#=(1,... +1)"),
    # -- an integer or variable expected: type_error(integer, _) --
    ("p16", "X = X+1, labeling([], [X])", "type_integer", "... +1", "labeling/2"),
    ("p17", "X = X+1, X in 1..3", "type_integer", "... +1", "in/2"),
    ("a11", "X = X+1, sum([X], #=, 1)", "type_integer", "... +1", "sum/3"),
    ("a14", "X = X+1, zcompare(_, X, 1)", "type_integer", "... +1", "zcompare/3"),
    # a labeling objective is a clpz expression
    ("i6", "Y in 1..3, X = X+1, labeling([min(X)], [Y])", _CE, "... +1",
     "labeling/2"),
]


def _norm(text: str) -> str:
    """Variable names differ between systems: each becomes ``_``."""
    return re.sub(r"\b_[0-9A-Z]\w*", "_", text)


def _error(kind, culprit) -> str:
    if kind == "type_integer":
        return f"type_error(integer,{culprit})"
    return f"domain_error({kind},{culprit})"


_PRELUDE = (":- use_module(library(clpz)).\n:- use_module(library(reif)).\n"
            "ev(G, R) :- catch((G, R = yes), error(E, C), R = E-C).\n")
_PROGRAM = _PRELUDE + "".join(f"{n}(R) :- ev(({g}), R).\n"
                              for n, g, *_ in ROWS)
_IDS = [r[0] for r in ROWS]
_ROW = {r[0]: r for r in ROWS}


class _Hung(BaseException):
    pass


def _within_seconds(call, seconds=10):
    """*call*'s result, or a failure when it takes longer than *seconds*:
    a cyclic post that loops must fail the row, not hang the suite."""
    def ring(*_):
        raise _Hung(f"no answer within {seconds} s: the post loops")
    old = signal.signal(signal.SIGALRM, ring)
    signal.alarm(seconds)
    try:
        return call()
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def _load(tmp_path_factory, suffix, text, frontend=None):
    path = tmp_path_factory.mktemp("clpz_cyclic") / f"clpz_cyclic_rows{suffix}"
    path.write_text(text, encoding="utf-8")
    saved = os.environ.get("CLAUSAL_PL_FRONTEND")
    if frontend:
        os.environ["CLAUSAL_PL_FRONTEND"] = frontend
    try:
        return _load_module(f"_clpz_cyclic_rows_{suffix.lstrip('.')}", str(path))
    finally:
        if saved is None:
            os.environ.pop("CLAUSAL_PL_FRONTEND", None)
        else:
            os.environ["CLAUSAL_PL_FRONTEND"] = saved


def _answer(mod, name) -> str:
    def run():
        r = Var()
        try:
            return [term_writeq(_deref_walk(r)) for _ in solve((name, r), mod)]
        except LogicException as exc:
            pytest.fail(f"{name}: uncaught {exc}")
    try:
        answers = _within_seconds(run)
    except _Hung as exc:
        pytest.fail(f"{name}: {exc}")
    assert len(answers) == 1, (name, answers)
    return _norm(answers[0])


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".pl", _PROGRAM, frontend="native")


@pytest.fixture(scope="module")
def clausal_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".clausal", _PROGRAM)


def _expected(name) -> str:
    _n, _g, kind, culprit, ctx, *engine = _ROW[name]
    return f"{_error(kind, engine[0] if engine else culprit)}-{ctx}"


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_post_pl(pl_mod, name):
    assert _answer(pl_mod, name) == _expected(name)


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_post_clausal(clausal_mod, name):
    assert _answer(clausal_mod, name) == _expected(name)


@pytest.fixture(scope="module")
def scryer_answers(tmp_path_factory):
    path = tmp_path_factory.mktemp("clpz_cyclic_scryer") / "rows.pl"
    path.write_text(_PROGRAM + "row_in(X, [X|_]).\nrow_in(X, [_|T]) :- row_in(X, T).\n",
                    encoding="utf-8")
    names = ", ".join(_IDS)
    goal = (f"( row_in(N, [{names}]), call(N, R), writeq(N = R), nl, fail "
            "; true ), halt.")
    proc = run_scryer(str(path), [goal], timeout=120)
    out = {}
    for line in proc.stdout.splitlines():
        m = re.match(r"\s*(\w+)\s*=\s*(.*)$", line)
        if m and m.group(1) in _ROW:
            out[m.group(1)] = _norm(m.group(2))
    assert out, (proc.stdout[-500:], proc.stderr[-500:])
    return out


@pytest.mark.parametrize("name", _IDS)
def test_cyclic_post_scryer(scryer, scryer_answers, name):
    """Scryer's own error and culprit (its context is its own), so a Scryer
    change shows up as a failing row."""
    del scryer
    _n, _g, kind, culprit, *_ = _ROW[name]
    got = scryer_answers.get(name, "")
    assert got.startswith(_error(kind, culprit) + "-"), got


# ── deep and shared ACYCLIC posts are not mistaken for cycles ───────────────

_ACYCLIC_PROGRAM = _PRELUDE + """\
sum(0, T, T).
sum(N, T, S) :- N > 0, N1 is N-1, sum(N1, T+1, S).
dag(0, T, T).
dag(N, T, R+R) :- N > 0, N1 is N-1, dag(N1, T, R).
deep(R) :- sum(200, 0, S), ev(X #= S, R0), R = X-R0.
shared(R) :- dag(12, Y, S), ev(S #= 8192, R0), R = Y-R0.
shared_var(R) :- Y = A+1, X = Y+Y, ev(X #= 8, R0), R = A-R0.
reified_shared(R) :- Y = A+1, ev(B #<==> (Y*Y #= 9), R0), A = 2, R = B-R0.
"""


@pytest.fixture(scope="module")
def acyclic_mod(tmp_path_factory):
    return _load(tmp_path_factory, ".pl", _ACYCLIC_PROGRAM, frontend="native")


@pytest.mark.parametrize("name,expected", [
    ("deep", "200-yes"), ("shared", "2-yes"),
    ("shared_var", "3-yes"), ("reified_shared", "1-yes"),
])
def test_acyclic_posts_still_post(acyclic_mod, name, expected):
    assert _answer(acyclic_mod, name) == expected


# ── the seam: its arithmetic comparisons post to CLP(Z) ─────────────────────
#
# The seam's ``is`` unifies, so ``X is X + 1`` builds the cycle; ``==``, ``!=``,
# ``<``, ``<=``, ``>``, ``>=`` are CLP(Z) comparisons, reified inside if_/3.
# The culprit is the cyclic side; the context is unbound, as for every other
# clpz expression error the seam's posts raise.

_SEAM_ROWS = [
    ("s1", "X is X + 1, X == 1", "... +1"),
    ("s2", "X is X + 1, X < 1", "... +1"),
    ("s3", "X is X + 1, Y_U == X", "... +1"),
    ("s4", "X is X + 1, X != 1", "... +1"),
    ("s5", "X is X + 1, if_(X == 1, Y_U is 1, Y_U is 2)", "... +1"),
    ("s6", "X is X + 1, if_(X < 1, Y_U is 1, Y_U is 2)", "... +1"),
    ("s7", "X is X * Y_U, X == 1", "... *_"),
    ("s9", "X is X + 1, Y_U == X * 2", "(... +1)*2"),
    ("s10", "X is X + 1, X >= 1", "... +1"),
    ("s11", "X is X + 1, X > 1", "... +1"),
    ("s12", "X is X + 1, X <= 1", "... +1"),
    ("s13", "X is X + 1, 1 == X", "... +1"),
    ("s14", "X is X + 1.5, X == 1", "... +1.5"),
    ("s15", "X is 'a' + X, X == 1", "a+ ..."),
    ("s16", "X is X + 1, Z is Z * 2, Z == X", "... *2"),
    ("s17", "X is X + 1, if_(1 < X, Y_U is 1, Y_U is 2)", "... +1"),
    ("s18", "X is X + 1, if_(Y_U != X, Z_U is 1, Z_U is 2)", "... +1"),
    ("s19", "X is Y + 1, Y is X * 2, X == 1", "... *2+1"),
]

_SEAM_PROGRAM = "-allow_singletons\n" + "".join(
    f"{n}(R) <- catch(({g}, R is 'yes'), error(E, C), R is E - C)\n"
    for n, g, _c in _SEAM_ROWS)


@pytest.fixture(scope="module")
def seam_mod(tmp_path_factory):
    return _load(tmp_path_factory, SEAM, _SEAM_PROGRAM)


@pytest.mark.parametrize("name,culprit", [(r[0], r[2]) for r in _SEAM_ROWS],
                         ids=[r[0] for r in _SEAM_ROWS])
def test_cyclic_post_seam(seam_mod, name, culprit):
    assert _answer(seam_mod, name) == f"domain_error(clpz_expression,{culprit})-_"


# ── with the units side channel on ──────────────────────────────────────────
#
# Once any Quantity exists the posts run the units side channel first, and it
# walks the sides too.  The flag is process-wide and never turns off, so this
# runs in a child process, under a hard timeout.

_UNITS_CHILD = r"""
import sys
from clausal.logic import _units_flag
_units_flag.touch()
import tests.iso.test_clpz_cyclic_scryer as T
import pathlib, tempfile

class Factory:
    def mktemp(self, name):
        return pathlib.Path(tempfile.mkdtemp(prefix=name))

bad = []
pl = T._load(Factory(), ".pl", T._PROGRAM, frontend="native")
for n in T._IDS:
    got = T._answer(pl, n)
    if got != T._expected(n):
        bad.append((n, got))
seam = T._load(Factory(), T.SEAM, T._SEAM_PROGRAM)
for n, _g, c in T._SEAM_ROWS:
    got = T._answer(seam, n)
    if got != f"domain_error(clpz_expression,{c})-_":
        bad.append((n, got))
print("BAD", bad)
"""


def test_cyclic_posts_with_units_active():
    import subprocess
    import sys
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    proc = subprocess.run(
        [sys.executable, "-c", _UNITS_CHILD], cwd=root, capture_output=True,
        text=True, timeout=300,
        env={**os.environ, "PYTHONPATH": root + os.pathsep + os.environ.get("PYTHONPATH", "")})
    assert "BAD []" in proc.stdout, (proc.stdout[-2000:], proc.stderr[-2000:])
