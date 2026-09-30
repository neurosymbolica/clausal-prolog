"""``m:Builtin(...)`` in a compiled body runs the builtin (Scryer: a
qualified call to a builtin runs it, in module m's context).

D60: the native .pl front end auto-declares a module name the file also
writes as DATA -- ``call(m:G)``, ``findall(X, m:p(X), L)`` -- as an atom, and
that atom binding then shadowed the imported module when the compiler
resolved every OTHER qualified call ``m:atom_length(...)``,
``m:assertz(...)``, ... in the file: each raised existence_error(procedure,
_).  Without the meta-call the same file worked.  Expected answers are
Scryer's for the same programs (2026-09-30).
"""
from __future__ import annotations

import pytest

from clausal.predicate_diagnostics import PredicateNotFoundError

OWNER = """\
:- module(qb_owner, [mp/1]).
:- dynamic(mp/1).
mp(1). mp(2).
"""

BODY = """\
b(R) :- qb_owner:atom_length(abc, R).
a(L) :- qb_owner:assertz(mp(9)), findall(X, qb_owner:mp(X), L).
r(L) :- qb_owner:retract(mp(1)), findall(X, qb_owner:mp(X), L).
"""

META = """\
c(L) :- findall(X, call(qb_owner:mp(X)), L).
"""


def _user(name, meta):
    return (f":- module({name}, [b/1, a/1, r/1, c/1]).\n"
            ":- use_module(qb_owner).\n" + BODY + (META if meta else ""))


@pytest.mark.parametrize("meta", [False, True], ids=["plain", "with_meta"])
def test_qualified_builtins_in_a_pl_module(native, ans, meta):
    native.load("qb_owner", OWNER)
    name = f"qb_user_{int(meta)}"
    mod = native.load(name, _user(name, meta))
    assert ans(mod, "b") == [3]
    assert ans(mod, "a") == [[1, 2, 9]]
    assert ans(mod, "r") == [[2, 9]]
    if meta:
        assert ans(mod, "c") == [[2, 9]]


@pytest.mark.parametrize("meta", [False, True], ids=["plain", "with_meta"])
def test_self_qualified_builtin_in_a_pl_file_without_a_module(native, ans,
                                                              meta):
    """A file with no module/2 qualifying by its own name; Scryer answers
    b(R) with R = 3 either way."""
    name = f"qb_self_{int(meta)}"
    src = f"b(R) :- {name}:atom_length(abc, R).\n"
    if meta:
        src += f"c(R) :- call({name}:atom_length(ab, R)).\n"
    mod = native.load(name, src)
    assert ans(mod, "b") == [3]
    if meta:
        assert ans(mod, "c") == [2]


def test_a_db_free_builtin_qualified_by_an_unloaded_module(native, ans):
    """Scryer: ``zz:atom_length(abc, R)`` answers R = 3 with no module zz;
    ``zz:foo(X)`` is existence_error(procedure, foo/1)."""
    mod = native.load("qb_unloaded", ":- module(qb_unloaded, [b/1, c/1]).\n"
                      "b(R) :- zz:atom_length(abc, R).\n"
                      "c(X) :- zz:foo(X).\n")
    assert ans(mod, "b") == [3]
    with pytest.raises(PredicateNotFoundError):
        ans(mod, "c")


SEAM_OWNER = """\
-module(qbs_owner, [mp/1])
-dynamic(mp/1)
mp(1)
mp(2)
"""


@pytest.mark.parametrize("meta", [False, True], ids=["plain", "with_meta"])
def test_qualified_builtins_in_a_seam_module(native, ans, meta):
    """The seam's ``m.assertz(...)`` walked to the ``assertz`` AST node class
    the loader injects into every module namespace (type_error(callable,
    <class assertz>)); it now resolves in m, like ``m.atom_length``."""
    native.load("qbs_owner", SEAM_OWNER, suffix=".seam")
    name = f"qbs_user_{int(meta)}"
    src = (f"-module({name}, [b/1, a/1, c/1])\n"
           "-import_module(qbs_owner)\n"
           "-private([abc])\n"
           "b(R) <- qbs_owner.atom_length(abc, R)\n"
           "a(L) <- (qbs_owner.assertz(qbs_owner.mp(9)),"
           " findall(X, qbs_owner.mp(X), L))\n")
    if meta:
        src += "c(L) <- findall(X, qbs_owner.mp(X), L)\n"
    mod = native.load(name, src, suffix=".seam")
    assert ans(mod, "b") == [3]
    assert ans(mod, "a") == [[1, 2, 9]]
    if meta:
        assert ans(mod, "c") == [[1, 2, 9]]
