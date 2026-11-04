"""Asserting rules: ISO 13211-1 8.9 in a ``.pl`` file, refused in Clausal
Prolog (operator ruling 2026-11-03: "assertz should work as ISO in .pl,
and in Clausal Prolog, not"; it replaces engine decision A09-F005 (b) for
``.pl``).

They were pinned (as ``xfail(strict=True)``) before the runtime rule
compiler was built (``database_ops._rule_clause``); every row passes now.
The expected answers are Scryer's (``test_oracle``) and, for
``term_instance``, the Cor.2 example DTC2 8.2.4.4.  More rows -- the
logical update view, retract during iteration, cut opacity, a call from
Clausal Prolog -- are in ``test_assert_rules_more_iso.py``.

* ``.pl``: assertz/1, asserta/1, retract/1 and clause/2 with rules,
  bodies with if-then-else and cut included (cut is ``.pl`` only, D59).
* ``.clausal``: asserting a rule stays ``permission_error(assert, rule,
  Head)``; facts are unchanged.
* the ``?-`` top-level: refused on the default Clausal Prolog surface,
  allowed with ``--prolog`` or when a ``.pl`` file is loaded (operator
  ruling 2026-10-24).
"""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .test_iso_answers_scryer import _engine_answers, _scryer_answers

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

#: (row name, body binding R, what both print)
ROWS = [
    ("assertz a rule, then call it",
     "assertz((p1(A) :- a1(A))), p1(X), R = X", ["dog"]),
    ("asserta puts the rule first",
     # (not one-letter atoms: the engine's writer prints a list of them as
     # a double-quoted string, which says nothing about the order)
     "assertz(p2(zz)), asserta((p2(X) :- X = aa)), findall(Y, p2(Y), R)",
     ["[aa,zz]"]),
    ("clause/2 gives the body",
     "assertz((p3(A) :- a1(A))), clause(p3(Q), B), R = Q-B", ["_1-a1(_1)"]),
    ("retract a rule",
     "assertz((p4(A) :- a1(A))), retract((p4(W) :- a1(W))), findall(X, p4(X), R)",
     ["[]"]),
    ("retract binds the body",
     "assertz((p5(A) :- a1(A))), retract((p5(_) :- B)), R = B", ["a1(_)"]),
    ("retract an instance of a rule",
     "assertz((p6(A) :- a1(A))), retract((p6(dog) :- a1(dog))), R = y", ["y"]),
    ("an if-then-else body",
     "assertz((p7(Z) :- (Z > 1 -> true ; fail))), ( p7(2), \\+ p7(0) -> R = y ; R = n )",
     ["y"]),
    ("a cut in the body",
     "assertz((p8(C) :- member(C, [1, 2, 3]), !)), findall(D, p8(D), R)",
     ["[1]"]),
    ("Cor.2 DTC2 8.2.4.4 term_instance",
     "assertz((term_instance(T, I) :- copy_term(T, Cp), subsumes_term(Cp, I))),"
     " ( term_instance(g(X), g(f(X))) -> R = y ; R = n )", ["y"]),
    # the errors conformed before rules could be asserted; kept
    ("a non-callable body",
     "catch(assertz((p9 :- 4)), error(F, _), R = F)", ["type_error(callable,4)"]),
    ("asserta, a non-callable body",
     "catch(asserta((p10(_) :- 1)), error(F, _), R = F)",
     ["type_error(callable,1)"]),
    ("a static predicate",
     "catch(assertz((atom(_) :- true)), error(F, _), R = F)",
     ["permission_error(modify,static_procedure,atom/1)"]),
]

PROGRAM = "a1(dog).\n" + "".join(
    f"r{i}(R) :- {body}.\n" for i, (_, body, _) in enumerate(ROWS))


@pytest.fixture(scope="module")
def pl_mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("assert_rules")
    mp = pytest.MonkeyPatch()
    mp.setenv("CLAUSAL_PL_FRONTEND", "native")
    mp.syspath_prepend(str(d))
    name = "_iso_assert_rules_1103"
    (d / f"{name}.pl").write_text(PROGRAM)
    sys.modules.pop(name, None)
    importlib.invalidate_caches()
    try:
        yield importlib.import_module(name)
    finally:
        sys.modules.pop(name, None)
        mp.undo()


def _params():
    for i, (name, _, _) in enumerate(ROWS):
        yield pytest.param(i, id=name)


@pytest.mark.parametrize("i", list(_params()))
def test_engine(pl_mod, i):
    assert _engine_answers(pl_mod, f"r{i}", 3) == ROWS[i][2]


def test_oracle(scryer):
    del scryer   # the fixture only asserts the binary is there
    got = _scryer_answers(PROGRAM, [(f"r{i}(R)", 3) for i in range(len(ROWS))])
    assert got == [r[2] for r in ROWS]


# ── Clausal Prolog keeps the refusal ────────────────────────────────────────

def _env(tmp_path):
    env = dict(os.environ)
    env.pop("CLAUSAL_PL_FRONTEND", None)
    env["PYTHONPATH"] = str(REPO_ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    env["HOME"] = str(tmp_path)
    return env


def _clausal(tmp_path, *argv, stdin=None):
    return subprocess.run(
        [sys.executable, "-m", "clausal", *argv], cwd=tmp_path,
        env=_env(tmp_path), input=stdin, capture_output=True, text=True,
        timeout=120, stdin=None if stdin is not None else subprocess.DEVNULL)


def test_a_clausal_file_still_refuses_a_rule(tmp_path):
    (tmp_path / "m.clausal").write_text(
        "t(R) :- catch(assertz((q(X) :- X = 1)), error(F, _), R = F).\n"
        "f(R) :- assertz(q(2)), q(R).\n")
    r = _clausal(tmp_path, "m.clausal", "-g", "t(R)")
    assert "permission_error(assert,rule,q(" in r.stdout, (r.stdout, r.stderr)
    facts = _clausal(tmp_path, "m.clausal", "-g", "f(R)")
    assert facts.stdout.strip() == "R = 2.", (facts.stdout, facts.stderr)


# ── the ?- top-level: by surface ────────────────────────────────────────────

_QUERY = "assertz((q(X) :- X = 1)), q(Y).\n"


def test_the_default_toplevel_refuses_a_rule(tmp_path):
    r = _clausal(tmp_path, stdin=_QUERY)
    assert "permission_error(assert,rule,q(" in r.stdout, (r.stdout, r.stderr)


def test_the_prolog_toplevel_asserts_a_rule(tmp_path):
    r = _clausal(tmp_path, "--prolog", stdin=_QUERY)
    assert "Y = 1" in r.stdout, (r.stdout, r.stderr)


def test_a_toplevel_with_a_pl_file_asserts_a_rule(tmp_path):
    (tmp_path / "p.pl").write_text("a1(dog).\n")
    r = _clausal(tmp_path, "p.pl", "--toplevel", stdin=_QUERY)
    assert "Y = 1" in r.stdout, (r.stdout, r.stderr)
