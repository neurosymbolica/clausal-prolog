"""aggregate_all/3 for count, sum, max, min, bag and set did not exist
(existence_error(procedure, aggregate_all/3)).  No reference engine here
has it (the Scryer build lacks library(aggregate); Trealla's binary does not
load its library), so the rows pin the documented semantics: findall/3's
solutions, sum 0 and count 0 over none, max/min arithmetic and FAILING over
none, set as sort/2."""
from __future__ import annotations
from tests._suffix import SEAM

SRC = """\
p(1). p(3). p(2).
a1(C) :- aggregate_all(count, member(_,[a,b]), C).
a2(C) :- aggregate_all(count, fail, C).
a3(C) :- aggregate_all(sum(X), member(X,[1,2.5]), C).
a4(C) :- aggregate_all(sum(X), fail, C).
a5(C) :- aggregate_all(max(X), p(X), C).
a6(C) :- aggregate_all(max(X), fail, C).
a7(C) :- aggregate_all(min(X), p(X), C).
a8(C) :- aggregate_all(bag(X), member(X,[c,a,c]), C).
a9(C) :- aggregate_all(set(X), member(X,[c,a,c]), C).
a10(E) :- catch(aggregate_all(foo, true, _), E, true).
a11(E) :- catch(aggregate_all(_, true, _), E, true).
a12(E) :- catch(aggregate_all(sum(X), member(X,[a]), _), E, true).
a14(C) :- aggregate_all(max(X-1), p(X), C).
a15(C) :- aggregate_all(count, p(_), 3), C = y.
a16(C) :- aggregate_all(bag(X-Y), (member(X,[1,2]), Y = X), C).
a17(C) :- aggregate_all(sum(X), p(X), C).
a18(C) :- aggregate_all(min(X), fail, C).
a19(C) :- aggregate_all(bag(X), fail, C).
a20(C) :- G = p(X), aggregate_all(bag(X), G, C).
"""


def test_aggregate_all(native, ans):
    mod = native.load("l3_aggregate_all", SRC)
    want = {
        "a1": [2], "a2": [0], "a3": [3.5], "a4": [0], "a5": [3], "a6": [],
        "a7": [1], "a8": [["c", "a", "c"]], "a9": [["a", "c"]],
        "a10": [("error", ("type_error", "aggregate", "foo"),
                 ("/", "aggregate_all", 3))],
        "a11": [("error", "instantiation_error", ("/", "aggregate_all", 3))],
        "a12": [("error", ("type_error", "evaluable", ("/", "a", 0)),
                 ("/", "aggregate_all", 3))],
        "a14": [2], "a15": ["y"], "a16": [[("-", 1, 1), ("-", 2, 2)]],
        "a17": [6], "a18": [], "a19": [[]], "a20": [[1, 3, 2]],
    }
    for name, expected in want.items():
        assert ans(mod, name) == expected, name


def test_aggregate_all_from_the_seam(tmp_path):
    """The spec shapes as seam source builds them: ``count`` an atom,
    ``sum(X)`` a cell."""
    import uuid

    from clausal.import_hook import _load_module
    from clausal.logic.solve import _deref_walk, solve
    from clausal.logic.variables import Var
    src = ("-allow_singletons\n"
           "-private([count, sum(_), max(_), set(_)])\n"
           "p(1),\np(3),\np(2),\n"
           "g0(C) <- aggregate_all(count, p(_), C)\n"
           "g1(C) <- aggregate_all(sum(X), p(X), C)\n"
           "g2(C) <- aggregate_all(max(X), p(X), C)\n"
           "g3(C) <- aggregate_all(set(X), p(X), C)\n")
    name = f"_agg_seam_{uuid.uuid4().hex[:8]}"
    (tmp_path / f"{name}{SEAM}").write_text(src)
    m = _load_module(name, str(tmp_path / f"{name}{SEAM}"))
    got = []
    for i in range(4):
        v = Var()
        got.append([_deref_walk(v) for _ in solve((f"g{i}", v), m)])
    assert got == [[3], [6], [3], [[1, 2, 3]]]
