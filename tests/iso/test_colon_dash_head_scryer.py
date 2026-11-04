"""A clause head named ``:-`` (operator ruling 2026-11-03, following
Scryer).

- ``(:-)/0`` is an ordinary atom head: a file may hold ``:- .`` (read as the
  atom ``:-``, ISO 6.3.4.2), which defines the fact ``(:-)/0``, and
  ``assertz((:-))`` does the same; ``call((:-))`` then succeeds.
- ``(:-)/1`` and ``(:-)/2`` -- a directive or a clause as a head -- are
  refused with ``permission_error(modify, static_procedure, (:-)/N)``: at
  load (the whole file), and by assertz/1, asserta/1, retract/1 and
  retractall/1 (whose context Scryer writes as retract/1).

Every row is checked against Scryer.  Loading runs on ``.pl`` (the native
front end) and ``.clausal``.  The translator front end writes seam text,
whose predicate names are Python identifiers, so it cannot define any
``:-`` procedure and refuses all three arities (its own message).
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from tests._oracles import SCRYER, run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def oracle():
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")

    def run(program: str, goal: str) -> list:
        d = tempfile.mkdtemp()
        pl = os.path.join(d, "w.pl")
        with open(pl, "w") as fh:
            fh.write(program)
        proc = run_scryer(pl, [goal], timeout=30)
        return [ln.strip() for ln in proc.stdout.strip().splitlines()
                if not ln.startswith("% Warning")]
    return run


def _clausal(tmp_path, suffix, program, goal, frontend="native"):
    path = tmp_path / f"w{suffix}"
    path.write_text(program)
    env = dict(os.environ, CLAUSAL_PL_FRONTEND=frontend,
               PYTHONPATH=str(REPO_ROOT))
    out = subprocess.run(
        [sys.executable, "-m", "clausal", str(path), "-g", goal],
        capture_output=True, text=True, env=env, timeout=120, cwd=tmp_path)
    return (out.stdout + out.stderr).strip()


_PROGRAM_0 = "p(1).\n:- .\nq(2).\n"


@pytest.mark.parametrize("suffix", [PL, CLAUSAL], ids=["pl", "clausal"])
def test_file_defines_colon_dash_0(tmp_path, suffix):
    assert _clausal(tmp_path, suffix, _PROGRAM_0, "call((:-)), q(X)") \
        == "X = 2."


def test_file_defines_colon_dash_0_oracle(oracle):
    assert oracle(_PROGRAM_0, "call((:-)), q(X)") == ["X = 2."]


#: (id, the clause, N of the refused (:-)/N).
LOAD_REFUSED = [
    ("directive_head", "((:- a) :- true).", 1),
    ("clause_head", "((a :- b) :- true).", 2),
    ("clause_head_rule", "((a :- b) :- c).", 2),
]


@pytest.mark.parametrize("suffix", [PL, CLAUSAL], ids=["pl", "clausal"])
@pytest.mark.parametrize("name, clause, n", LOAD_REFUSED,
                         ids=[r[0] for r in LOAD_REFUSED])
def test_load_refused(tmp_path, suffix, name, clause, n):
    out = _clausal(tmp_path, suffix, f"p(1).\n{clause}\nq(2).\n", "q(X)")
    assert "did not load" in out, out
    assert (f"permission_error(modify, static_procedure, (:-)/{n})"
            in out), out


@pytest.mark.parametrize("name, clause, n", LOAD_REFUSED,
                         ids=[r[0] for r in LOAD_REFUSED])
def test_load_refused_oracle(oracle, name, clause, n):
    out = oracle(f"p(1).\n{clause}\nq(2).\n", "q(X)")
    assert out[0] == (f"error(permission_error(modify,static_procedure,"
                      f"(:-)/{n}),load/1)."), out


@pytest.mark.parametrize("text", [":- .", "((:- a) :- true).",
                                  "((a :- b) :- true)."])
def test_translator_refuses_every_colon_dash_head(tmp_path, text):
    out = _clausal(tmp_path, PL, f"p(1).\n{text}\n", "p(X)",
                   frontend="translator")
    assert "did not load" in out, out


#: (goal, the answer Clausal and Scryer print).
RUNTIME = [
    ("assertz((:-)), call((:-))", "true."),
    ("asserta((:-)), call((:-))", "true."),
    ("retractall((:-))", "true."),
    ("assertz(((a:-b):-true))",
     "error(permission_error(modify,static_procedure,(:-)/2),assertz/1)"),
    ("asserta(((a:-b):-true))",
     "error(permission_error(modify,static_procedure,(:-)/2),asserta/1)"),
    ("assertz(((:-a):-true))",
     "error(permission_error(modify,static_procedure,(:-)/1),assertz/1)"),
    ("assertz((:-a))",
     "error(permission_error(modify,static_procedure,(:-)/1),assertz/1)"),
    ("asserta((:-a))",
     "error(permission_error(modify,static_procedure,(:-)/1),asserta/1)"),
    ("retract(((a:-b):-true))",
     "error(permission_error(modify,static_procedure,(:-)/2),retract/1)"),
    ("retract((:-a))",
     "error(permission_error(modify,static_procedure,(:-)/1),retract/1)"),
    ("retract(((:-a):-true))",
     "error(permission_error(modify,static_procedure,(:-)/1),retract/1)"),
    ("retractall((a:-b))",
     "error(permission_error(modify,static_procedure,(:-)/2),retract/1)"),
    ("retractall((:-a))",
     "error(permission_error(modify,static_procedure,(:-)/1),retract/1)"),
]


def _wrapped(goal):
    # No if-then-else: ``.clausal`` refuses ``->``.
    return f"catch(({goal}), E, true), (var(E), R = true ; nonvar(E), R = E)"


@pytest.mark.parametrize("suffix", [PL, CLAUSAL], ids=["pl", "clausal"])
@pytest.mark.parametrize("goal, expected", RUNTIME,
                         ids=[r[0] for r in RUNTIME])
def test_runtime(tmp_path, suffix, goal, expected):
    out = _clausal(tmp_path, suffix, "z.\n", _wrapped(goal) + ", writeq(R), nl")
    assert out.splitlines()[0] == expected.removesuffix("."), out


@pytest.mark.parametrize("goal, expected", RUNTIME,
                         ids=[r[0] for r in RUNTIME])
def test_runtime_oracle(oracle, goal, expected):
    out = oracle("z.\n", _wrapped(goal) + ", writeq(R), nl, false")
    assert out[0] == expected.removesuffix("."), out
