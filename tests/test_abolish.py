"""ISO 8.9.4 abolish/1: a DYNAMIC procedure goes -- its clauses and the
procedure itself, so a later call is existence_error(procedure, F/N), as in
ISO and Scryer (a dynamic procedure emptied by retract/1 FAILS instead).  A
static procedure, user-defined or builtin, is permission_error(modify,
static_procedure, F/N); a procedure that does not exist is no error.  Errors
on the indicator in ISO 8.9.4.3's order.  abolish/1 did not exist
(existence_error(procedure, abolish/1)).

Scryer (the clean clpq build) gives the same answers for the .pl program
in ``SCRYER_PROGRAM``, measured 2026-09-30, except that it qualifies a
non-indicator with the module (type_error(predicate_indicator, user:foo));
ISO's term, unqualified, is the one kept here.
"""
from __future__ import annotations

import itertools
import os
import subprocess
import warnings

import pytest

from clausal.import_hook import _load_module
from clausal.logic.exceptions import LogicException
from clausal.logic.solve import call
from clausal.logic.variables import Var, walk
from clausal.terms import term_str

SCRYER = "/workspace/scryer-prolog-clpq/target/release/scryer-prolog"

_N = itertools.count()


def _module(tmp_path, body: str, exports: list[str]):
    name = f"_abolish_{next(_N)}"
    src = (f"-module({name}, [{', '.join(exports)}])\n-allow_singletons\n"
           f"{body}\n")
    p = tmp_path / f"{name}.clausal"
    p.write_text(src)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return _load_module(name, str(p)).__dict__["$module"]


def _run(mod, pred, *args):
    """The walked answers of pred(*args, Out), or the ISO error term."""
    out = Var()
    try:
        return [walk(out) for _ in call(pred, *args, out, module=mod)]
    except LogicException as e:
        return term_str(e.term)


SEAM = """\
-private([ok, nope])
-dynamic(d/1)
-dynamic(e/2)
d(1)
d(2)
s(1)
t(X) <- d(X)
ab(ok) <- abolish(d/1)
ab_s(ok) <- abolish(s/1)
ab_none(ok) <- abolish(nope/2)
ab_builtin(ok) <- abolish(atom_length/2)
ab_self(ok) <- abolish(abolish/1)
emptied(X) <- (retract(d(1)), retract(d(2)), findall(Y, d(Y), X))
called(X) <- call(d, X)
count(N) <- (findall(X, d(X), L), length(L, N))
e_twice(ok) <- (abolish(e/2), abolish(e/2))
"""
EXPORTS = ["t/1", "ab/1", "ab_s/1", "ab_none/1", "ab_builtin/1",
           "ab_self/1", "emptied/1", "called/1", "count/1", "e_twice/1",
           "s/1"]


@pytest.fixture
def mod(tmp_path):
    return _module(tmp_path, SEAM, EXPORTS)


def test_abolish_removes_the_procedure(mod):
    assert _run(mod, "t") == [1, 2]
    assert _run(mod, "ab") == ["ok"]
    err = "error(existence_error(procedure, /(d, 1)), /(d, 1))"
    assert _run(mod, "t") == err
    assert _run(mod, "called") == err
    assert _run(mod, "count") == err


def test_emptying_by_retract_fails_instead(mod):
    """The positive control: retract leaves the procedure, so it fails."""
    assert _run(mod, "emptied") == [[]]
    assert _run(mod, "t") == []


def test_abolish_twice_and_of_nothing_succeeds(mod):
    assert _run(mod, "e_twice") == ["ok"]
    assert _run(mod, "ab_none") == ["ok"]


def test_static_procedures_are_refused(mod):
    for pred, pi in (("ab_s", "/(s, 1)"), ("ab_builtin", "/(atom_length, 2)"),
                     ("ab_self", "/(abolish, 1)")):
        got = _run(mod, pred)
        assert isinstance(got, str), (pred, got)
        assert got.startswith(
            f"error(permission_error(modify, static_procedure, {pi})"), got
    assert _run(mod, "s") == [1]            # untouched


@pytest.mark.parametrize("pi, formal", [
    (Var(), "instantiation_error"),
    (("/", Var(), 1), "instantiation_error"),
    (("/", "foo", Var()), "instantiation_error"),
    ("foo", "type_error(predicate_indicator, foo)"),
    (1.5, "type_error(predicate_indicator, 1.5)"),
    (("/", 1, 1), "type_error(atom, 1)"),
    (("/", ("foo", "a"), 1), "type_error(atom, foo(a))"),
    (("/", "foo", "a"), "type_error(integer, a)"),
    (("/", "foo", -1), "domain_error(not_less_than_zero, -1)"),
])
def test_indicator_errors(mod, pi, formal):
    with pytest.raises(LogicException) as ei:
        list(call("abolish", pi, module=mod))
    assert term_str(ei.value.term).startswith(f"error({formal}"), \
        term_str(ei.value.term)


SCRYER_PROGRAM = """\
:- dynamic(d/1).
d(1). d(2).
s(1).
e(G) :- catch((findall(x, G, L), (L = [], writeq(fail) ; L = [_|_], writeq(ok))),
         error(E, _), writeq(E)), nl.
t :- e(abolish(d/1)), e(d(_)), e(abolish(s/1)), e(abolish(nope/2)),
     e(abolish(d/1)), e(abolish(atom_length/2)), e(abolish(foo/(-1))),
     e(abolish(foo(a)/1)), e(abolish(_)).
"""
SCRYER_OUT = ["ok", "existence_error(procedure,d/1)",
              "permission_error(modify,static_procedure,s/1)", "ok", "ok",
              "permission_error(modify,static_procedure,atom_length/2)",
              "domain_error(not_less_than_zero,-1)",
              "type_error(atom,foo(a))", "instantiation_error"]


def test_native_pl_matches_scryer(tmp_path, monkeypatch):
    """The same program under the native .pl front end answers Scryer's
    lines, and Scryer itself prints them (the oracle)."""
    import importlib
    import sys
    from clausal import import_hook as ih
    from clausal.logic.solve import call as _call
    import io
    import contextlib
    (tmp_path / "abolish_native.pl").write_text(SCRYER_PROGRAM)
    monkeypatch.setenv("CLAUSAL_PL_FRONTEND", "native")
    monkeypatch.syspath_prepend(str(tmp_path))
    sys.modules.pop("abolish_native", None)
    importlib.invalidate_caches()
    try:
        m = importlib.import_module("abolish_native")
        assert type(m.__loader__) is ih.NativePrologLoader
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            assert len(list(_call("t", module=m))) == 1
        got = buf.getvalue().split()
    finally:
        sys.modules.pop("abolish_native", None)
    assert got == SCRYER_OUT
    if not os.path.exists(SCRYER):
        if os.environ.get("CLAUSAL_ISO_ALLOW_NO_SCRYER"):
            pytest.skip(f"scryer not built at {SCRYER}")
        pytest.fail(f"the Scryer oracle is not built at {SCRYER}")
    f = tmp_path / "oracle.pl"
    f.write_text(SCRYER_PROGRAM)
    proc = subprocess.run([SCRYER, str(f), "-g", "t", "-g", "halt"],
                          cwd=tmp_path, capture_output=True, text=True,
                          timeout=120, stdin=subprocess.DEVNULL)
    lines = [ln for ln in proc.stdout.split() if ln]
    assert lines == SCRYER_OUT, (proc.stdout, proc.stderr)
