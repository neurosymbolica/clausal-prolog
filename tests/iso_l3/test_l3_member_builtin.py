"""member/2 and memberchk/2 are engine builtins under their ISO names.

They were registered only as ``in_/2`` and ``in_check/2``; the old ``.pl``
translator renamed the ISO spellings, so a ``.pl`` file read by the native
front end, and a goal handed to the Python query API, found no procedure.
A module's own member/2 still answers first, as a row outranks any builtin."""
from __future__ import annotations

import pytest

from clausal.logic.variables import Var, deref, walk

FRONT_ENDS = pytest.mark.parametrize("frontend", ["native", None])


@FRONT_ENDS
def test_member_and_memberchk_in_a_pl_file(native, ans, frontend):
    mod = native.load(f"mem_pl_{frontend}",
                      "all(L) :- findall(X, member(X, [a, b, c]), L).\n"
                      "first(X) :- memberchk(X, [p, q]).\n"
                      "open(L) :- memberchk(z, L).\n"
                      "gen(X) :- member(X, [1, 2]).\n",
                      frontend=frontend)
    assert ans(mod, "all") == [["a", "b", "c"]]
    assert ans(mod, "first") == ["p"]
    assert ans(mod, "gen") == [1, 2]
    [row] = ans(mod, "open")
    assert row[0] == "z"


@FRONT_ENDS
def test_a_modules_own_member_2_wins_over_the_builtin(native, ans, frontend):
    # A first-element-only member/2: the builtin would answer b too.
    mod = native.load(f"mem_own_{frontend}",
                      "member(X, [X|_]).\n"
                      "memberchk(only, _).\n"
                      "all(L) :- findall(X, member(X, [a, b]), L).\n"
                      "chk(X) :- memberchk(X, [a]).\n",
                      frontend=frontend)
    assert ans(mod, "all") == [["a"]]
    assert ans(mod, "chk") == ["only"]


def test_member_from_the_python_query_api(native):
    from clausal import solve
    mod = native.load("mem_q", "p(1).\n")
    x = Var()
    got = [walk(deref(x)) for _ in solve(("member", x, [3, 4]), module=mod)]
    assert got == [3, 4]
    y = Var()
    got = [walk(deref(y)) for _ in solve(("memberchk", y, [3, 4]), module=mod)]
    assert got == [3]


def test_member_in_a_seam_module(native, ans):
    mod = native.load("mem_seam",
                      "all(L) <- findall(X, member(X, [1, 2]), L)\n"
                      "chk(X) <- memberchk(X, [7, 8])\n",
                      suffix=".seam", frontend=None)
    assert ans(mod, "all") == [[1, 2]]
    assert ans(mod, "chk") == [7]


@FRONT_ENDS
def test_member_is_still_an_ordinary_atom_as_data_in_a_pl_file(
        native, ans, frontend):
    mod = native.load(f"mem_atom_{frontend}",
                      "role(member).\nrole(guest).\n"
                      "is_member(X) :- role(X), X == member.\n",
                      frontend=frontend)
    assert ans(mod, "role") == ["member", "guest"]
    assert ans(mod, "is_member") == ["member"]


def test_member_is_still_an_ordinary_atom_as_data_in_a_seam_module(
        native, ans):
    mod = native.load("mem_atom_seam",
                      "-private([member, guest])\n"
                      "role(member),\nrole(guest),\n"
                      "is_member(X) <- (role(X), X == member)\n",
                      suffix=".seam", frontend=None)
    assert ans(mod, "role") == ["member", "guest"]
    assert ans(mod, "is_member") == ["member"]


@FRONT_ENDS
def test_an_imported_member_2_wins_over_the_builtin(native, ans, frontend):
    native.load(f"mem_lib_{frontend}",
                f":- module(mem_lib_{frontend}, [member/2]).\n"
                "member(X, [X|_]).\n", frontend=frontend)
    mod = native.load(f"mem_user_{frontend}",
                      f":- use_module(mem_lib_{frontend}).\n"
                      "all(L) :- findall(X, member(X, [a, b]), L).\n",
                      frontend=frontend)
    assert ans(mod, "all") == [["a"]]
