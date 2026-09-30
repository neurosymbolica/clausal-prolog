"""D52: findall/4 in a findall/3 goal raised "findall/3 not found" -- in a
native ``.pl`` file and in the seam alike.  The clause set's call targets
held both ``findall/3`` (the special form: no builtin at that arity, so it
got an arity-fixed ``_DbDispatchAdapter`` under the name) and ``findall/4``;
when the set iterated ``/3`` first, the adapter was accepted as the call
target for ``/4`` too, and the findall/4 goal dispatched findall/3.
Expected answers are Scryer's (``:- use_module(library(lists))``, plus
``library(iso_ext)`` for forall/2)."""
from __future__ import annotations

SRC = """\
p1(L) :- findall(X, (member(Y, [1,2]), findall(Z, member(Z, [Y]), X, [])), L).
p2(L) :- findall(X-T, (member(Y, [1,2]), findall(Z, member(Z, [Y]), X), T=[]), L0, [end]), L = L0.
p3(L) :- findall(X, (member(Y, [1,2]), bagof(Z, member(Z, [Y,Y]), X)), L).
p4(L) :- findall(X, (member(Y, [2,1]), setof(Z, member(Z, [Y,0]), X)), L).
p5(L) :- findall(Y, (member(Y, [1,2,3]), forall(member(Z, [1,2]), Z =< Y)), L).
p6(L) :- findall(X, (member(Y,[1,2]), findall(W, (member(W,[Y]), findall(V, member(V,[W]), _, [])), X, [])), L).
p8(L) :- findall(X, (member(Y,[1,2]), findall(W, (member(W,[Y]), findall(V, member(V,[W]), _)), X)), L).
p9(L) :- findall(A, (member(Y,[1,2]), findall(Z, (member(Z,[Y]), findall(Q, member(Q,[Z]), [_], [])), A, [tail])), L).
b2(L) :- bagof(X, Y^Z^(member(Y, [1,2]), findall(Z, member(Z, [Y]), X)), L).
b3(L) :- bagof(X, Y^Z^(member(Y, [1,2]), findall(Z, member(Z, [Y]), X, [t])), L).
b4(L) :- setof(X, Y^Z^(member(Y, [2,1]), findall(Z, member(Z, [Y]), X, [t])), L).
b6(L) :- findall(X-W, bagof(Z, member(Z-W, [1-a,2-b,3-a]), X), L).
b7(L) :- findall(X, setof(Z, W^member(Z-W, [3-a,2-b,3-a]), X), L).
"""

SEAM = """\
p1(L) <- findall(X, (member(Y, [1,2]), findall(Z, member(Z, [Y]), X, [])), L)
q(L) <- (findall(X, member(X,[1]), A), findall(X, member(X,[2]), L, A))
"""


def test_nested_findall_native(native, ans):
    mod = native.load("l3_nested_findall", SRC)
    want = {
        "p1": [[[1], [2]]],
        "p2": [[("-", [1], []), ("-", [2], []), "end"]],
        "p3": [[[1, 1], [2, 2]]],
        "p4": [[[0, 2], [0, 1]]],
        "p5": [[2, 3]],
        "p6": [[[1], [2]]],
        "p8": [[[1], [2]]],
        "p9": [[[1, "tail"], [2, "tail"]]],
        "b2": [[[1], [2]]],
        "b3": [[[1, "t"], [2, "t"]]],
        "b4": [[[1, "t"], [2, "t"]]],
        "b6": [[("-", [1, 3], "a"), ("-", [2], "b")]],
        "b7": [[[2, 3]]],
    }
    for name, expected in want.items():
        assert ans(mod, name) == expected, name


def test_nested_findall_seam(native, ans):
    mod = native.load("l3_nested_findall_seam", SEAM, suffix=".seam",
                      frontend=None)
    assert ans(mod, "p1") == [[[1], [2]]]
    assert ans(mod, "q") == [[2, 1]]


def test_special_form_adapter_never_answers_another_arity():
    """The order-independent pin: the target set's iteration order follows
    str hashing (randomised per process), so the load tests above only fail
    on some runs.  Resolving ``findall/3`` BEFORE ``findall/4`` is the order
    that broke; both orders must leave the findall/4 builtin under the name."""
    from clausal.logic.builtins import BuiltinPredicate
    from clausal.logic.compiler.globals_env import _inject_resolved_targets
    from clausal.logic.database import Database
    for order in ([("findall", 3), ("findall", 4)],
                  [("findall", 4), ("findall", 3)]):
        base: dict = {}
        _inject_resolved_targets(order, base, Database(), {})
        assert isinstance(base["findall"], BuiltinPredicate), (order, base)
