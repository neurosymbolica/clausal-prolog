"""A clause head qualified with a module other than the file's own
(operator ruling 2026-11-03; the own-module case is
``tests/test_module_qualified_clause_head.py``).

- ``user:`` in a file with no module/2 names the file itself, for heads
  (clauses and grammar rules) and for calls, at load and when a goal runs:
  ``user:bar(2).`` defines ``bar/1``, and ``user:p(X)`` reaches the file's
  ``p/1``, as in Scryer, where such a file IS module ``user``.
- ``M:H`` with ``M`` a variable or not an atom refuses the whole file with
  Scryer's ``permission_error(modify, static_procedure, (:)/2)``; Scryer
  checks it before the ISO built-in check (``M:atom(1).`` is (:)/2 there).
- Any other atom module is refused ("a clause for another module is not
  supported").  Here Scryer adds the clause to that module; one file is one
  module in Clausal, and nothing adds clauses to another module at load.
  The oracle rows below record what Scryer does for those texts.

Every engine row runs on ``.pl`` through both front ends (native and the
translator) and on ``.clausal``.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.import_hook import _load_module
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var
from tests._oracles import SCRYER, run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]
REPO_ROOT = Path(__file__).resolve().parent.parent.parent

SURFACES = [(PL, "native"), (PL, "translator"), (CLAUSAL, "native")]
SURFACE_IDS = ["pl", "pl-translator", "clausal"]


@pytest.fixture(params=SURFACES, ids=SURFACE_IDS)
def surface(request, monkeypatch):
    suffix, frontend = request.param
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    return suffix


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
        return [ln.strip() for ln in proc.stdout.strip().splitlines()]
    return run


def _load(tmp_path, stem, suffix, text):
    path = tmp_path / f"{stem}{suffix}"
    path.write_text(text)
    sys.modules.pop(stem, None)
    return _load_module(stem, str(path))


def _answers(mod, name, n):
    args = tuple(Var() for _ in range(n))
    return [tuple(_deref_walk(a) for a in args)
            for _ in solve((name, *args), mod)]


# ── user: in a file with no module/2 ────────────────────────────────────────

USER_TEXT = """\
p(1).
user:bar(2).
user:user:deep(3).
q(X) :- user:p(X).
r(X) :- G = user:p(X), call(G).
user:g --> [a].
s(ok) :- phrase(user:g, [a]).
t(L) :- findall(X, user:bar(X), L).
user:rule(X) :- p(X).
"""

#: (goal name, arity, answers) -- the same in Scryer (test_user_oracle),
#: except ``deep/1``: Scryer strips one ``user:`` from ``user:user:deep(3).``
#: and defines ``(:)/2`` in ``user``; the engine strips every own qualifier,
#: as it does for ``m:m:H`` in module ``m``
#: (tests/test_module_qualified_clause_head.py).
USER_GOALS = [
    ("bar", 1, [(2,)]),
    ("deep", 1, [(3,)]),
    ("q", 1, [(1,)]),
    ("r", 1, [(1,)]),
    ("s", 1, [("ok",)]),
    ("t", 1, [([2],)]),
    ("rule", 1, [(1,)]),
]


def test_user_heads_and_calls_name_the_file(tmp_path, surface):
    stem = f"_mqh_user_{surface[1:]}_{os.environ['CLAUSAL_PL_FRONTEND']}"
    try:
        mod = _load(tmp_path, stem, surface, USER_TEXT)
        db = mod.__dict__["$module"]
        got = {name: _answers(db, name, n) for name, n, _ in USER_GOALS}
        assert got == {name: ans for name, _n, ans in USER_GOALS}
        assert ":" not in {k if type(k) is str else k[0]
                           for k in db.db._clauses}
    finally:
        sys.modules.pop(stem, None)


@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_user_goal_from_the_command_line(tmp_path, frontend):
    """A ``-g user:G`` runs in the file loaded, as Scryer's toplevel runs
    it in ``user``."""
    path = tmp_path / "w.pl"
    path.write_text(USER_TEXT)
    env = dict(os.environ, CLAUSAL_PL_FRONTEND=frontend,
               PYTHONPATH=str(REPO_ROOT))
    out = subprocess.run(
        [sys.executable, "-m", "clausal", str(path), "-g", "user:bar(X)"],
        capture_output=True, text=True, env=env, timeout=120, cwd=tmp_path)
    assert out.stdout.strip() == "X = 2.", (out.stdout, out.stderr)


@pytest.mark.parametrize("goal, expected", [
    ("bar(X)", "X = 2."), ("q(X)", "X = 1."),
    ("r(X)", "X = 1."), ("s(X)", "X = ok."), ("t(X)", "X = [2]."),
    ("rule(X)", "X = 1."), ("user:bar(X)", "X = 2."),
])
def test_user_oracle(oracle, goal, expected):
    assert oracle(USER_TEXT, goal) == [expected]


def test_user_in_a_module_file_is_not_the_file(tmp_path, surface):
    """With module/2, ``user:`` is another module: a goal through it does
    not reach the file's own predicates."""
    stem = f"mqh_userm_{surface[1:]}_{os.environ['CLAUSAL_PL_FRONTEND']}"
    text = f":- module({stem}, [t/1]).\np(1).\nt(X) :- G = user:p(X), call(G).\n"
    if surface == CLAUSAL:
        text += f":- end_module({stem}).\n"
    try:
        mod = _load(tmp_path, stem, surface, text)
        from clausal.logic.exceptions import LogicException
        with pytest.raises(LogicException):
            _answers(mod.__dict__["$module"], "t", 1)
    finally:
        sys.modules.pop(stem, None)


# ── refused heads ───────────────────────────────────────────────────────────

_COLON_2 = "permission_error(modify, static_procedure, (:)/2)"
_ANOTHER = "a clause for another module is not supported"

#: (id, module/2 name or None, the clause, what the refusal says).
REFUSED = [
    ("var_module", None, "M:foo(1).", _COLON_2),
    ("int_module", None, "7:foo(1).", _COLON_2),
    ("var_module_rule", None, "M:foo(X) :- X = 1.", _COLON_2),
    ("var_module_builtin", None, "M:atom(1).", _COLON_2),
    ("user_then_var", None, "user:M:foo(1).", _COLON_2),
    ("var_module_in_a_module", "a", "M:foo(1).", _COLON_2),
    ("other_atom_no_module2", None, "m:foo(1).", "m:foo/1 -- " + _ANOTHER),
    ("other_atom_rule", None, "m:foo(X) :- X = 1.", "m:foo/1 -- " + _ANOTHER),
    ("user_then_other", None, "user:m:h(3).", "m:h/1 -- " + _ANOTHER),
    ("other_atom_in_a_module", "a", "b:qux(8).", "b:qux/1 -- " + _ANOTHER),
    ("user_in_a_module", "a", "user:zed(9).", "user:zed/1 -- " + _ANOTHER),
    ("builtin_other_module", None, "b:atom(1).",
     "permission_error(modify, static_procedure, atom/1)"),
]


def _refused_program(module, clause, stem, surface):
    head = f":- module({stem}, [p/1]).\n" if module else ""
    tail = f":- end_module({stem}).\n" if module and surface == CLAUSAL else ""
    return f"{head}p(1).\n{clause}\nq(2).\n{tail}"


@pytest.mark.parametrize("name, module, clause, says", REFUSED,
                         ids=[r[0] for r in REFUSED])
def test_refused_engine(tmp_path, surface, name, module, clause, says):
    stem = f"mqh_ref_{name}"
    try:
        with pytest.raises(SyntaxError) as e:
            _load(tmp_path, stem, surface,
                  _refused_program(module, clause, stem, surface))
        assert says in str(e.value), str(e.value)
    finally:
        sys.modules.pop(stem, None)


#: What Scryer does with the same texts (file ``w.pl``, module ``a`` when
#: the row has one): (id, goal, Scryer's output lines).
ORACLE_REFUSED = {
    "var_module": ["error(permission_error(modify,static_procedure,(:)/2),load/1)."],
    "int_module": ["error(permission_error(modify,static_procedure,(:)/2),load/1)."],
    "var_module_builtin": ["error(permission_error(modify,static_procedure,(:)/2),load/1)."],
    "builtin_other_module": ["error(permission_error(modify,static_procedure,atom/1),load/1)."],
}


@pytest.mark.parametrize("name", sorted(ORACLE_REFUSED))
def test_refused_oracle(oracle, name):
    _id, module, clause, _says = next(r for r in REFUSED if r[0] == name)
    out = [ln for ln in oracle(_refused_program(module, clause, "a", PL),
                                "q(X)") if not ln.startswith("% Warning")]
    assert out[:-1] == ORACLE_REFUSED[name], out
    # The whole file is refused: q/1 after the clause did not load.
    assert "existence_error(procedure,q/1)" in out[-1], out


def test_another_module_oracle(oracle):
    """Scryer adds ``m:foo(1).`` to module ``m`` (the case refused here by
    the ruling): recorded so a change in the oracle is seen."""
    assert oracle("p(1).\nm:foo(1).\n", "m:foo(X)") == ["X = 1."]
    out = oracle("p(1).\nm:foo(1).\n", "foo(X)")
    assert "existence_error(procedure,foo/1)" in out[-1], out


# ── the Trealla prelude (user: heads, no module/2) still loads ──────────────

@pytest.mark.parametrize("frontend", ["native", "translator"])
def test_trealla_prelude_loads(tmp_path, monkeypatch, frontend):
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    src = (REPO_ROOT / "clausal" / "tools" / "prolog_preludes"
           / "clausal_constants_trealla.pl").read_text()
    stem = f"_mqh_trealla_{frontend}"
    try:
        mod = _load(tmp_path, stem, PL, src)
        clauses = mod.__dict__["$module"].db._clauses
        names = {k if type(k) is str else k[0] for k in clauses}
        assert "term_expansion" in names and ":" not in names, names
    finally:
        sys.modules.pop(stem, None)
