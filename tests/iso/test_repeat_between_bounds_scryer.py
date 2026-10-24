"""repeat/0 (ISO 8.15.3) and between/3's upper bound, row by row against
Scryer and Trealla.

repeat/0 succeeds, and succeeds again on every backtrack, forever.  It is
monotone nondeterminism, not committed choice, so it is a builtin on the
``.pl`` surface and on ``.clausal`` alike (operator ruling 2026-10-24: an
ISO non-conformity is a bug).  It used to be
``existence_error(procedure, repeat/0)`` everywhere, although
``clausal/tools/iso_builtins.py`` lists it.

between/3's upper bound is an integer.  SWI-Prolog also takes the atoms
``inf`` and ``infinite`` there; Scryer and Trealla take neither (each raises
``type_error(integer, inf)``, checking the upper bound before X), and the
operator ruled (2026-10-24) to behave as Scryer and Trealla do, so the rows
pin the refusal.

Each ROW is one goal binding ``R``; every row is bounded (an unbounded goal
under the driver's failure loop would never end).  The ENGINE half loads the
rows as a ``.pl`` module and as a ``.clausal`` module; the ORACLE halves run
the same text in Scryer and in Trealla.  The two agree on every row.

An error answer is its formal term only, because the three engines name
different contexts and ISO leaves the context implementation defined:

======================  =================  ===============  ============
error                   Scryer             Trealla          Clausal
======================  =================  ===============  ============
type_error(integer, _)  ``must_be/2``      ``between/3``    ``between/3``
instantiation_error     ``must_be/2``      ``integer``      ``between/3``
======================  =================  ===============  ============

Scryer's ``must_be/2`` is its library(between) implementation showing
through; Clausal keeps the predicate indicator, as its other errors do.
"""

from __future__ import annotations

import contextlib
import io
import os
import resource
import subprocess
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal._suffixes import PROLOG_SUFFIX
from clausal.import_hook import _load_module
from clausal.logic.solve import solve

from tests._oracles import TREALLA

from .conftest import run_scryer

CLAUSAL_PROLOG = ".clausal"

#: ``row(I)`` prints ``ROW I`` then ``A <answer>`` per answer, or
#: ``A <formal>`` for an error.
DRIVER = """\
:- dynamic(tick/1).
run_row(I, G, R) :-
    write('ROW '), write(I), nl,
    catch(( call(G), write('A '), writeq(R), nl, fail ; true ),
          error(F, _), ( write('A '), writeq(F), nl )).
"""

#: (id, goal, expected answers) -- the same text in both engines.
ROWS = [
    # ── repeat/0 ────────────────────────────────────────────────────────
    ("repeat_once", "once(repeat), R = yes", ["yes"]),
    ("repeat_once_per_outer_answer",
     "findall(x, (between(1, 3, _), once(repeat)), R)", ["[x,x,x]"]),
    ("repeat_inside_member",
     "findall(X, (member(X, [a, b]), once(repeat)), R)", ["[a,b]"]),
    ("repeat_succeeds_again_on_backtrack",
     "retractall(tick(_)), assertz(tick(0)), "
     "once((repeat, retract(tick(K)), K1 is K + 1, assertz(tick(K1)), "
     "K1 >= 4)), R = K1", ["4"]),
    ("repeat_nth_solution", "call_nth(repeat, 1000), R = yes", ["yes"]),
    ("repeat_then_bounded_generator",
     "once((repeat, between(1, 3, I), I >= 2)), R = I", ["2"]),
    ("repeat_double_negation", "\\+ \\+ repeat, R = yes", ["yes"]),
    ("repeat_negation_fails", "( \\+ repeat, R = no ; R = yes )", ["yes"]),
    ("repeat_through_call", "once(call(repeat)), R = yes", ["yes"]),
    ("repeat_inside_catch", "once(catch(repeat, E, R = E)), R = yes", ["yes"]),
    ("repeat_is_callable", "G = repeat, once(G), R = yes", ["yes"]),
    # ── between/3: the upper bound is an integer ────────────────────────
    ("between_inf_check", "between(1, inf, 5), R = yes",
     ["type_error(integer,inf)"]),
    ("between_inf_generate", "between(1, inf, X), R = X",
     ["type_error(integer,inf)"]),
    ("between_infinite", "between(1, infinite, X), R = X",
     ["type_error(integer,infinite)"]),
    ("between_inf_upper_checked_before_x", "between(1, inf, a), R = yes",
     ["type_error(integer,inf)"]),
    ("between_low_not_integer", "between(a, inf, X), R = X",
     ["type_error(integer,a)"]),
    ("between_upper_not_integer", "between(1, foo, X), R = X",
     ["type_error(integer,foo)"]),
    ("between_x_not_integer", "between(1, 3, a), R = yes",
     ["type_error(integer,a)"]),
    ("between_low_unbound", "between(_, inf, X), R = X",
     ["instantiation_error"]),
    ("between_bounded_enumerates", "findall(X, between(1, 3, X), R)",
     ["[1,2,3]"]),
    ("between_empty_range", "between(3, 1, X), R = X", []),
]


def _program(goals: list[str]) -> str:
    return DRIVER + "".join(
        f"row({i}) :- run_row({i}, ({g}), R).\n" for i, g in enumerate(goals))


def _parse(stdout: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in stdout.splitlines():
        if line.startswith("ROW "):
            rows.append([])
        elif rows and line.startswith("A "):
            rows[-1].append(line[2:].strip())
    return rows


@pytest.fixture(scope="module", params=[PROLOG_SUFFIX, CLAUSAL_PROLOG])
def engine_rows(request, tmp_path_factory):
    import clausal
    assert os.getcwd() in clausal.__file__, clausal.__file__
    suffix = request.param
    name = "repeat_between" + suffix.replace(".", "_")
    src = _program([r[1] for r in ROWS])
    if suffix == CLAUSAL_PROLOG:
        src = f":- module({name}, []).\n" + src + f":- end_module({name}).\n"
    path = tmp_path_factory.mktemp("repeat") / f"{name}{suffix}"
    path.write_text(src)
    mod = _load_module(name, str(path))
    out = []
    for i in range(len(ROWS)):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            n = sum(1 for _ in solve(("row", i), mod))
        assert n == 1, (ROWS[i][0], n)
        parsed = _parse(buf.getvalue())
        assert len(parsed) == 1, (ROWS[i][0], buf.getvalue())
        out.append(parsed[0])
    return out


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[0] for r in ROWS])
def test_engine(engine_rows, i):
    assert engine_rows[i] == ROWS[i][2], (ROWS[i][1], engine_rows[i])


_ORACLE_PRELUDE = (":- use_module(library(lists)).\n"
                   ":- use_module(library(between)).\n"
                   ":- use_module(library(iso_ext)).\n")


def test_oracle(scryer):
    del scryer      # the fixture only asserts the binary is there
    prelude = _ORACLE_PRELUDE
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "oracle.pl")
        with open(pl, "w") as fh:
            fh.write(prelude + _program([r[1] for r in ROWS]))
        proc = run_scryer(pl, [f"row({i})." for i in range(len(ROWS))],
                          timeout=120)
    got = _parse(proc.stdout)
    assert len(got) == len(ROWS), proc.stdout[-2000:] + proc.stderr[-2000:]
    bad = [(r[0], g, r[2]) for r, g in zip(ROWS, got) if g != r[2]]
    assert not bad, bad


@pytest.mark.skipif(not os.path.exists(TREALLA), reason="Trealla not built here")
def test_oracle_trealla():
    main = "main :- " + ", ".join(f"row({i})" for i in range(len(ROWS))) + ".\n"
    with tempfile.TemporaryDirectory() as d:
        pl = os.path.join(d, "oracle.pl")
        with open(pl, "w") as fh:
            fh.write(_ORACLE_PRELUDE + _program([r[1] for r in ROWS]) + main)
        proc = subprocess.run([TREALLA, "-q", pl, "-g", "main, halt"],
                              capture_output=True, text=True, timeout=120)
    got = _parse(proc.stdout)
    assert len(got) == len(ROWS), proc.stdout[-2000:] + proc.stderr[-2000:]
    bad = [(r[0], g, r[2]) for r, g in zip(ROWS, got) if g != r[2]]
    assert not bad, bad


# ── repeat/0 resumes in constant space ─────────────────────────────────────

_BOUNDED = """\
nth(N) :- call_nth(repeat, N).
counted(N, L) :- findall(x, (between(1, N, _), once(repeat)), Xs), length(Xs, L).
"""


@pytest.fixture(scope="module", params=[PROLOG_SUFFIX, CLAUSAL_PROLOG])
def bounded_module(request, tmp_path_factory):
    suffix = request.param
    name = "repeat_bounded" + suffix.replace(".", "_")
    src = _BOUNDED
    if suffix == CLAUSAL_PROLOG:
        src = f":- module({name}, []).\n" + src + f":- end_module({name}).\n"
    path = tmp_path_factory.mktemp("repeat_bounded") / f"{name}{suffix}"
    path.write_text(src)
    return _load_module(name, str(path))


def _rss_kb() -> int:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def test_repeat_200000_retries_bounded(bounded_module):
    """The 200000th solution of repeat/0: each retry is a resume of the
    same generator, so neither the Python stack (the run would hit the
    recursion limit) nor the trail (repeat binds nothing) grows with the
    count, and the peak RSS stays put between 20000 and 200000 retries."""
    from clausal.logic.variables import Trail
    lengths = []
    trail = Trail()
    for _ in solve(("nth", 20000), bounded_module, trail):
        lengths.append(len(trail))
    before = _rss_kb()
    trail = Trail()
    for _ in solve(("nth", 200000), bounded_module, trail):
        lengths.append(len(trail))
    assert len(lengths) == 2 and lengths[0] == lengths[1], lengths
    assert _rss_kb() - before < 20_000, (before, _rss_kb())


def test_repeat_200000_outer_solutions_bounded(bounded_module):
    """200000 ``once(repeat)`` calls under findall: each one's choicepoint
    is dropped by once/1, so the run is linear and flat."""
    from clausal.logic.variables import Var, deref
    length = Var()
    got = [deref(length) for _ in solve(("counted", 200000, length),
                                        bounded_module)]
    assert got == [200000]
