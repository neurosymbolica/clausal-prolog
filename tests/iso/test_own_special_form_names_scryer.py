"""A module's OWN definition of a special form's name runs in its own bodies.

The compiler lowers its special forms (``clausal/logic/special_forms.py``:
``forall/2``, ``call_cleanup/2``, ``freeze/2``, ``findall/4`` ...) inline,
by name.  A ``.pl`` or ``.clausal`` file may not define an ISO built-in
(``tests/iso/test_builtin_redefinition_scryer.py``), but every special form
that is NOT one is a library name the file may define (operator ruling
2026-10-24), and Scryer then runs the file's definition.  The engine ran the
special form instead, in the file's own bodies and through ``call/N``, and
ignored the definition: ``forall(X, _) :- X = mine.`` then
``findall(X, forall(X, true), L)`` raised ``instantiation_error``, where
Scryer answers ``L = [mine]``.

Each row defines one such name with the probe argument bound to ``mine``
and asks for it on four routes: the body goal, ``call/N`` of the name,
``call/1`` of the cell, and ``call/N`` of a closure.  The definition is
placed after the uses and before them.  ``:- dynamic(forall/2).`` makes
the name the file's own procedure too.  Another module that does not define
the name keeps the special form, and so does a seam module that defines it
(the seam is not ISO text).

Scryer differs on one row: it refuses ``findall/4`` (its own builtin, no
ISO one) with ``permission_error(modify, static_procedure, findall/4)``;
the engine's refusal is ISO's set, so the file loads and its definition
runs.  ``test_oracle`` pins both.

Record: todo/done/a-module-own-forall-definition-is-ignored-in-its-bodies-
2026-10-24.md.
"""

from __future__ import annotations

import importlib
import os
import shutil
import sys
import tempfile
import textwrap

import pytest

from clausal._suffixes import CLAUSAL_PROLOG_SUFFIXES
from clausal._suffixes import PROLOG_SUFFIX as PL
from clausal.logic.solve import solve
from clausal.logic.special_forms import GOAL_CONTROLS, SPECIAL_FORMS
from clausal.logic.variables import Trail
from clausal.tools.iso_builtins import is_iso_builtin
from tests._oracles import SCRYER, run_scryer

CLAUSAL = CLAUSAL_PROLOG_SUFFIXES[0]

#: Every special form, and every goal control, a file may define: those
#: that are no ISO built-in.
DEFINABLE = sorted(
    key for key in list(SPECIAL_FORMS) + list(GOAL_CONTROLS)
    if not is_iso_builtin(*key))

#: Scryer refuses these (its own builtins), where the engine loads them.
SCRYER_REFUSES = {("findall", 4)}


def test_the_definable_set():
    """The rows below are every definable special form; a new special form
    is a new row."""
    assert DEFINABLE == [
        ("call_cleanup", 2), ("call_nth", 2), ("catch_error", 2),
        ("catch_recover", 3), ("count_all", 2), ("eval_", 2),
        ("findall", 4), ("forall", 2), ("freeze", 2), ("ignore", 1),
        ("not", 1), ("setup_call_cleanup", 3), ("when", 2)]


def _args(first: str, arity: int) -> str:
    return ", ".join([first] + ["_"] * (arity - 1))


def _program(name: str, arity: int, definition_first: bool) -> str:
    """The definition binds its first argument to ``mine``; q1..q4 collect
    that argument through the four routes."""
    definition = f"{name}({_args('X', arity)}) :- X = mine.\n"
    closure = ", ".join(["_"] * (arity - 1))
    uses = (
        f"q1(L) :- findall(Y, {name}({_args('Y', arity)}), L).\n"
        f"q2(L) :- findall(Y, call({name}, {_args('Y', arity)}), L).\n"
        f"q3(L) :- findall(Y, (G = {name}({_args('Y', arity)}), call(G)), L).\n"
        + (f"q4(L) :- findall(Y, call({name}(Y), {closure}), L).\n"
           if arity > 1 else
           f"q4(L) :- findall(Y, call({name}, Y), L).\n"))
    return definition + uses if definition_first else uses + definition


def _ids(keys):
    return [f"{n}_{a}" for n, a in keys]


_COUNTER = iter(range(10 ** 6))


def _load(tmp_path, suffix: str, text: str, stem: str):
    stem = f"{stem}_{next(_COUNTER)}"
    path = tmp_path / f"{stem}{suffix}"
    path.write_text(text)
    from clausal.import_hook import _load_module  # noqa: PLC0415
    return _load_module(stem, str(path))


def _collected(mod, pred: str):
    from clausal import Var  # noqa: PLC0415
    from clausal.logic.solve import _deref_walk  # noqa: PLC0415
    L = Var()
    out = []
    for _ in solve((pred, L), mod, Trail()):
        out.append(_deref_walk(L))
    return out


#: ``.pl`` through the native front end (the default) and the translator,
#: and ``.clausal``.
SURFACES = [(PL, "native"), (PL, "translator"), (CLAUSAL, "native")]
SURFACE_IDS = ["pl", "pl-translator", "clausal"]


@pytest.fixture(params=SURFACES, ids=SURFACE_IDS)
def surface(request, monkeypatch):
    suffix, frontend = request.param
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", frontend)
    return suffix


@pytest.mark.parametrize("definition_first", [False, True],
                         ids=["defined_after", "defined_before"])
def test_engine(tmp_path, surface, definition_first):
    """Every row, every route: the file's definition runs.  All failures
    are collected and named together."""
    failures = []
    for name, arity in DEFINABLE:
        if (name, arity) == ("not", 1) and os.environ.get(
                "CLAUSAL_PL_FRONTEND") == "translator":
            # The legacy translator spells ``\\+`` as the seam's ``not``, and
            # its call/N of a defined not/1 is existence_error: an older
            # translator gap, the same before this change
            # (todo/pl-translator-call-n-of-a-defined-not-1-2026-11-03.md).
            continue
        text = _program(name, arity, definition_first)
        try:
            mod = _load(tmp_path, surface, text, f"_own_sf_{name}")
        except Exception as e:  # noqa: BLE001 -- named below
            failures.append(f"{name}/{arity}: load: {type(e).__name__}: {e}")
            continue
        for q in ("q1", "q2", "q3", "q4"):
            try:
                got = _collected(mod, q)
            except Exception as e:  # noqa: BLE001 -- named below
                failures.append(f"{name}/{arity} {q}: {type(e).__name__}: {e}")
                continue
            if got != [["mine"]]:
                failures.append(f"{name}/{arity} {q}: {got!r}")
    assert not failures, "\n".join(failures)


def test_other_module_keeps_the_special_form(tmp_path, surface,
                                             monkeypatch):
    """The definition is local: a module that imports the definer's q1/1
    but not its forall/2 still runs the special form."""
    monkeypatch.syspath_prepend(str(tmp_path))
    names = ["own_sf_definer", "own_sf_user"]
    for n in names:
        sys.modules.pop(n, None)
    (tmp_path / f"own_sf_definer{surface}").write_text(textwrap.dedent("""\
        :- module(own_sf_definer, [q1/1]).
        forall(X, _) :- X = mine.
        q1(L) :- findall(Y, forall(Y, true), L).
        """) + (":- end_module(own_sf_definer).\n"
                if surface == CLAUSAL else ""))
    (tmp_path / f"own_sf_user{surface}").write_text(textwrap.dedent("""\
        :- module(own_sf_user, [t/1]).
        :- use_module(own_sf_definer).
        t(L) :- q1(L), forall(member(X, [1, 2]), integer(X)).
        """) + (":- end_module(own_sf_user).\n"
                if surface == CLAUSAL else ""))
    try:
        importlib.invalidate_caches()
        mod = importlib.import_module("own_sf_user")
        assert _collected(mod, "t") == [["mine"]]
    finally:
        for n in names:
            sys.modules.pop(n, None)
        for p in tmp_path.rglob("__pycache__"):
            shutil.rmtree(p, ignore_errors=True)


DYNAMIC_PROGRAM = (":- dynamic(forall/2).\n"
                   "q1(L) :- findall(Y, forall(Y, _), L).\n"
                   "t(L) :- q1([]), assertz(forall(a, b)), q1(L).\n")


def test_dynamic_engine(tmp_path, surface):
    """``dynamic(forall/2)`` makes the name the file's own procedure too."""
    mod = _load(tmp_path, surface, DYNAMIC_PROGRAM, "_own_sf_dynamic")
    assert _collected(mod, "t") == [["a"]]


def test_dynamic_oracle(oracle):
    out = oracle(DYNAMIC_PROGRAM, "t(L), write(L), nl")
    assert out[0] == "[a]", out


def test_seam_keeps_the_special_form(tmp_path):
    """The seam is not ISO text: a seam module that defines forall/2 still
    runs the special form in its own bodies (unchanged)."""
    path = tmp_path / "own_sf_seam.seam"
    path.write_text(textwrap.dedent("""\
        -module(own_sf_seam, [mine])

        forall(X, _) <- (X is mine)
        q1(L) <- findall(Y, forall(member(Y, [1, 2]), Y > 0), L)
        """))
    from clausal.import_hook import _load_module  # noqa: PLC0415
    from clausal.logic.variables import is_var  # noqa: PLC0415
    sys.modules.pop("own_sf_seam", None)
    try:
        mod = _load_module("own_sf_seam", str(path))
        got = _collected(mod, "q1")
    finally:
        sys.modules.pop("own_sf_seam", None)
    assert len(got) == 1 and len(got[0]) == 1 and is_var(got[0][0]), got


# --- the oracle --------------------------------------------------------------

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


def test_oracle(oracle):
    """Scryer runs the file's definition on every route, for every row but
    the ones it refuses as its own builtins."""
    failures = []
    goal = ("q1(A), q2(B), q3(C), q4(D), write([A, B, C, D]), nl")
    for name, arity in DEFINABLE:
        out = oracle(_program(name, arity, False), goal)
        if (name, arity) in SCRYER_REFUSES:
            want = ("error(permission_error(modify,static_procedure,"
                    f"{name}/{arity}),load/1).")
            if not out or out[0] != want:
                failures.append(f"{name}/{arity}: {out!r}")
        elif not out or out[0] != "[[mine],[mine],[mine],[mine]]":
            failures.append(f"{name}/{arity}: {out!r}")
    assert not failures, "\n".join(failures)
