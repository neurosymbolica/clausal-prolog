"""The second argument of ``error/2`` is what Scryer puts there.

Operator ruling 2026-09-27 (when Scryer and SWI-Prolog differ, Scryer): a
builtin's error names the builtin's indicator, a missing procedure names
itself, and there is no ``context/2`` wrapper.  Each row runs the same goal
in the engine and (ORACLE half) in Scryer, and the error term must print the
same.  The engine's explanatory prose follows the term after ``": "`` and is
not part of the comparison.
"""

from __future__ import annotations

import os
import subprocess
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException, render_error_term
from clausal.logic.solve import solve
from clausal.logic.variables import Var

from .conftest import SCRYER

#: (engine clause body, Scryer goal, the error term both print)
ROWS = [
    ("atom_length(_, _)", "atom_length(_, _)",
     "error(instantiation_error,atom_length/2)"),
    ("atom_length(1, _)", "atom_length(1, _)",
     "error(type_error(atom,1),atom_length/2)"),
    ("atom_codes(_, _)", "atom_codes(_, _)",
     "error(instantiation_error,atom_codes/2)"),
    ("call(esa_missing, 1)", "call(esa_missing, 1)",
     "error(existence_error(procedure,esa_missing/1),esa_missing/1)"),
    ("call(esa_missing)", "call(esa_missing)",
     "error(existence_error(procedure,esa_missing/0),esa_missing/0)"),
    ("call(_)", "call(_)", "error(instantiation_error,call/1)"),
    ("(G is 1, call(G))", "G = 1, call(G)",
     "error(type_error(callable,1),call/1)"),
    ("must_be(integer, a)", "must_be(integer, a)",
     "error(type_error(integer,a),must_be/2)"),
    ("must_be(integer, _)", "must_be(integer, _)",
     "error(instantiation_error,must_be/2)"),
    ("throw(_)", "throw(_)", "error(instantiation_error,throw/1)"),
    ("'=:='(1, 1 + a)", "1 =:= 1 + a",
     "error(type_error(evaluable,a/0),(is)/2)"),
]

_SRC = "-allow_singletons\n-private([esa_missing, a, integer])\n" + "".join(
    f"g{i}(X) <- {body},\n" for i, (body, _, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def mod():
    with tempfile.NamedTemporaryFile(suffix=".clausal", mode="w",
                                     delete=False) as f:
        f.write(_SRC)
        path = f.name
    try:
        return _load_module("_error_second_argument_scryer", path)
    finally:
        os.unlink(path)


@pytest.mark.parametrize("i", range(len(ROWS)), ids=[r[1] for r in ROWS])
def test_engine_error_term_prints_as_scryers(mod, i):
    with pytest.raises(LogicException) as info:
        list(solve((f"g{i}", Var()), mod))
    assert render_error_term(info.value.term) == ROWS[i][2]
    assert str(info.value).startswith(f"Uncaught logic exception: {ROWS[i][2]}")


def test_oracle_prints_the_expected_column(scryer):
    del scryer   # the fixture only asserts the binary is there
    with tempfile.NamedTemporaryFile(suffix=".pl", mode="w",
                                     delete=False) as f:
        f.write(":- use_module(library(error)).\n")
        prelude = f.name
    try:
        stdin = "".join(f"catch(({goal}), E, true), writeq(E), nl.\n"
                        for _, goal, _ in ROWS)
        out = subprocess.run([SCRYER, prelude], input=stdin,
                             capture_output=True, text=True,
                             timeout=60).stdout.splitlines()
    finally:
        os.unlink(prelude)
    got = [line for line in (l.strip() for l in out) if line.startswith("error(")]
    want = [r[2] for r in ROWS]
    assert len(got) == len(want) == len(ROWS) > 0
    assert got == want
