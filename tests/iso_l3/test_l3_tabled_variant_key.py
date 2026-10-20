"""The tabling variant key numbers variables by first occurrence, so two
terms key alike iff they are variants (equal up to a consistent renaming of
variables; ISO/XSB variant checking): ``f(_, _)`` and ``f(X, X)`` are two
answers and ``w(f(A, B))`` / ``w(f(A, A))`` are two subgoals, while
``f(X, Y)`` and ``f(Y, X)`` are one.  The key used to map every unbound
variable to one sentinel, which took ``f(X, X)`` for a duplicate of
``f(_, _)`` and replayed the ``w(f(X, X))`` table for a later ``w(f(A, B))``
call -- through negation, a proof of a falsehood
(todo/done/tabled-variant-key-conflates-repeated-variables-2026-10-20.md)."""
from __future__ import annotations

import pytest

from clausal.logic import tabling
from clausal.logic.tabling import make_subgoal_key
from clausal.logic.variables import Trail, Var, is_var
from clausal.terms import ConcreteSeg, SegList, VarSeg


def _parts(term):
    if isinstance(term, SegList):
        out = []
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                out.extend(seg.elements)
            elif isinstance(seg, VarSeg):
                out.append(seg.var)
            else:
                out.append(seg)
        return out
    return list(term)


def shape(term):
    """A term with every unbound variable shown as ``"_"``."""
    if is_var(term):
        return "_"
    if isinstance(term, SegList):
        return ("|", *(shape(e) for e in _parts(term)))
    if isinstance(term, list):
        return [shape(e) for e in term]
    if isinstance(term, tuple):
        return tuple(shape(e) for e in term)
    return term


def variables(term, out=None):
    """The distinct unbound variables of *term*, in order (identity)."""
    if out is None:
        out = []
    if is_var(term):
        if all(term is not v for v in out):
            out.append(term)
    elif isinstance(term, (list, tuple, SegList)):
        for e in _parts(term):
            variables(e, out)
    return out


def _db(mod):
    return mod.__dict__["$module"].db


def _tables(mod, functor):
    return [k for k in _db(mod).table_store if k[0] == functor]


# ── The todo's repro, on each surface ───────────────────────────────────────

TODO = """\
:- table(w/1).
w(f(_, _)).
w(f(X, X)).
first(X) :- w(f(X, X)).
all_w(L) :- findall(T, w(T), L).
wrong :- first(_), \\+ (w(f(A, B)), A = a, B = b).
"""


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_an_answer_with_a_repeated_variable_is_not_a_duplicate(native, ans, suffix):
    """``w(f(_, _))`` and ``w(f(X, X))`` are two answers: the second is a
    different variant (its variables are one), not a duplicate of the first."""
    mod = native.load("l3_vk_todo" + suffix.strip("."), TODO, suffix=suffix)
    [rows] = ans(mod, "all_w")
    assert [shape(r) for r in rows] == [("f", "_", "_"), ("f", "_", "_")]
    general, repeated = rows
    assert len(variables(general)) == 2
    assert len(variables(repeated)) == 1


@pytest.mark.parametrize("suffix", [".pl", ".clausal"])
def test_a_negation_does_not_replay_the_repeated_variable_table(native, ans, suffix):
    """``first(_)`` tables ``w(f(X, X))``; the later ``w(f(A, B))`` is a
    different subgoal and must not replay that table.  The negation of a
    provable goal fails: ``w(f(a, b))`` holds."""
    mod = native.load("l3_vk_naf" + suffix.strip("."), TODO, suffix=suffix)
    assert ans(mod, "wrong", 0) == []


def test_calls_differing_in_repeated_variables_are_distinct_subgoals(native):
    """From Python: ``w(f(A, A))`` then ``w(f(A, B))`` are two tables.  The
    first call has one answer (both clauses instantiate to ``f(V, V)``
    against it, one variant); the second has both."""
    from clausal.logic.solve import call
    mod = native.load("l3_vk_calls", TODO)
    a = Var()
    assert [shape(a) for _ in call("w", ("f", a, a), module=mod)] == ["_"]
    a, b = Var(), Var()
    rows = [(shape(a), shape(b), a is b) for _ in call("w", ("f", a, b), module=mod)]
    assert rows == [("_", "_", False), ("_", "_", False)]
    assert len(_tables(mod, "w")) == 2


# ── Answer dedup ────────────────────────────────────────────────────────────

DEDUP = """\
:- table(v/1).
v(f(X, Y, X)).
v(f(Y, X, Y)).
v(f(X, X, Y)).
v(f(X, Y, Y)).
v(f(X, Y, Z)).
v(f(X, X, X)).
v(f(_, _, _)).
:- table(l/1).
l([A, B, A]).
l([A, A, B]).
l([A, B, B]).
l([B, A, B]).
l([_A, _B, _C]).
l(g([A, h(B)], A, B)).
l(g([B, h(A)], B, A)).
l(g([A, h(B)], B, A)).
l([_X | _T]).
l([_Y | _S]).
l([T | T]).
"""


def test_variants_are_one_answer_and_non_variants_are_kept(native, ans):
    """``f(X, Y, X)`` and ``f(Y, X, Y)`` are variants (one answer); the
    sharing patterns ``f(X, X, Y)``, ``f(X, Y, Y)``, ``f(X, Y, Z)``,
    ``f(X, X, X)`` are four more; ``f(_, _, _)`` repeats ``f(X, Y, Z)``."""
    mod = native.load("l3_vk_dedup", DEDUP)
    rows = ans(mod, "v")
    assert len(rows) == 5
    patterns = []
    for r in rows:
        vs = variables(r)
        patterns.append(tuple(vs.index(x) for x in r[1:]))
    assert patterns == [(0, 1, 0), (0, 0, 1), (0, 1, 1), (0, 1, 2), (0, 0, 0)]


def test_variables_in_different_positions_of_lists_and_compounds(native, ans):
    """The numbering follows first occurrence through lists, nested cells
    and the open tail of a partial list."""
    mod = native.load("l3_vk_lists", DEDUP)
    rows = ans(mod, "l")
    assert [shape(r) for r in rows] == [
        ["_", "_", "_"], ["_", "_", "_"], ["_", "_", "_"], ["_", "_", "_"],
        ("g", ["_", ("h", "_")], "_", "_"), ("g", ["_", ("h", "_")], "_", "_"),
        ("|", "_", "_"), ("|", "_", "_"),
    ]
    patterns = []
    for r in rows:
        vs = variables(r)
        parts = _parts(r) if not isinstance(r, tuple) else _parts(r[1]) + list(r[2:])
        patterns.append(tuple(vs.index(x) if is_var(x) else vs.index(x[1]) for x in parts))
    # [A, B, A], [A, A, B], [A, B, B] ([B, A, B] is its variant), [A, B, C];
    # g([A, h(B)], A, B) (its variant with A/B swapped dropped), g([A, h(B)], B, A);
    # [X | T] ([Y | S] is its variant), [T | T].
    assert patterns == [(0, 1, 0), (0, 0, 1), (0, 1, 1), (0, 1, 2),
                        (0, 1, 0, 1), (0, 1, 1, 0), (0, 1), (0, 0)]


# ── Call variance through negation (subsumption) ───────────────────────────

SUBSUME = """\
:- table(p/2).
p(1, 2).
p(3, 3).
diag(X) :- p(X, X).
after_diag :- diag(_), \\+ p(1, 2).
after_diag_true :- diag(_), \\+ p(2, 1).
"""


def test_a_complete_repeated_variable_table_does_not_cover_a_ground_call(native, ans):
    """``p(X, X)`` complete (one answer, ``p(3, 3)``) does not subsume
    ``p(1, 2)``: the negation evaluates ``p(1, 2)`` itself and fails, as
    ``p(1, 2)`` is a fact.  ``\\+ p(2, 1)`` holds."""
    mod = native.load("l3_vk_subsume", SUBSUME)
    assert ans(mod, "after_diag", 0) == []
    assert ans(mod, "after_diag_true", 0) == [()]


# ── Attributed variables key as variables ──────────────────────────────────

def test_an_attributed_variable_keys_as_a_variable():
    """A constrained variable is a variable to the key (its attributes are
    not part of the variant): ``dif(X, a), w(f(X, Y))`` is the subgoal
    ``w(f(X, Y))``, and the sharing is seen through the attribute."""
    from clausal.logic.constraints import dif
    trail = Trail()
    x, y = Var(), Var()
    assert dif(x, "a", trail)
    assert make_subgoal_key((("f", x, y),), trail) == make_subgoal_key((("f", Var(), Var()),), trail)
    assert make_subgoal_key((("f", x, x),), trail) == make_subgoal_key((("f", y, y),), trail)
    assert make_subgoal_key((("f", x, x),), trail) != make_subgoal_key((("f", x, y),), trail)


# ── WFS: a conditional answer is kept apart from its sharing variants ──────

WFS = """\
:- table(u/0).
:- table(w/0).
u :- \\+ w.
w :- \\+ u.
:- table(p/1).
p(f(X, X)) :- u.
p(f(_, _)).
p(f(1, _)) :- u.
p(f(1, 1)).
"""


def test_a_conditional_answer_with_a_repeated_variable_is_its_own_row(native):
    """``p(f(X, X))`` is WFS-undefined (it rests on the u/w cycle) and
    ``p(f(_, _))`` is true: two rows, each with its own truth.  The
    conditional ``p(f(1, X))`` is neither merged with ``p(f(1, 1))`` nor
    with ``p(f(_, _))``."""
    from clausal.logic.solve import query_wfs
    from clausal.terms import Undefined
    mod = native.load("l3_vk_wfs", WFS)
    x = Var()
    rows = [(shape(r["X"]), len(variables(r["X"])), r["_truth"])
            for r in query_wfs(("p", x), {"X": x}, mod)]
    assert sorted(rows, key=repr) == sorted([
        (("f", "_", "_"), 1, Undefined),
        (("f", "_", "_"), 2, True),
        (("f", 1, "_"), 1, Undefined),
        (("f", 1, 1), 0, True),
    ], key=repr)


# ── A large table ──────────────────────────────────────────────────────────

BIG = """\
:- table(big/2).
big(N, f(A, A, B)) :- between(1, 1500, N), B = g(N, _).
big(N, f(A, B, A)) :- between(1, 1500, N), B = g(N, _).
big(N, f(B, A, B)) :- between(1, 1500, N), A = g(N, _).
count(C) :- findall(x, big(_, _), L), length(L, C).
"""


def test_a_large_table_keeps_each_sharing_pattern(native, ans):
    """3000 rows: per N, ``f(A, A, g(N, _))`` and ``f(A, g(N, _), A)`` are
    distinct; ``f(B, g(N, _), B)`` is a variant of the second."""
    mod = native.load("l3_vk_big", BIG)
    assert ans(mod, "count") == [3000]


# ── The key itself, in both twins ──────────────────────────────────────────

_TWINS = [("py", tabling._make_subgoal_key_py)]
try:
    from clausal.logic._tabling_core import make_subgoal_key as _c_key
    _TWINS.append(("c", _c_key))
except ImportError:
    pass


@pytest.fixture(params=_TWINS, ids=[t[0] for t in _TWINS])
def key(request):
    fn = request.param[1]
    return lambda *args: fn(args, Trail())


def test_variables_are_numbered_by_first_occurrence(key):
    x, y, z = Var(), Var(), Var()
    assert key(x, y) == key(y, x) == key(Var(), Var())
    assert key(x, x) == key(y, y) != key(x, y)
    assert key(("f", x, [y, x]), y) == key(("f", y, [z, y]), z)
    assert key(("f", x, [y, x]), y) != key(("f", x, [y, x]), x)
    assert key(x, 1, x) != key(x, 1, y)
    assert key(x) == key(y) and key(x) != key(1)


def test_the_two_twins_agree(key):
    """Every twin produces the same key for the same term, so a table keyed
    by one is found by the other (P52 lock-step)."""
    x, y = Var(), Var()
    terms = [(x, y), (x, x), (("f", x, [y, x, 1]), y), ([x, y, x],),
             ({"a": x, "b": y, "c": x},), (("g", x), ("g", y), ("g", x))]
    for args in terms:
        keys = {name: fn(args, Trail()) for name, fn in _TWINS}
        assert len(set(keys.values())) == 1, (args, keys)


def test_a_dict_keys_the_same_whatever_its_insertion_order(key):
    """A dict is order-free (A04-F005): the numbering of the variables in
    its values does not depend on the order the keys were inserted in."""
    x, y = Var(), Var()
    assert key({"a": x, "b": y}, x) == key({"b": y, "a": x}, x)
    assert key({"a": x, "b": y}, x) != key({"a": x, "b": y}, y)


def test_a_ground_key_is_unchanged(key):
    assert key(1, "a", ("f", 2), [3, "b"]) == (1, "a", ("__tuple__", "f", 2), ("__list__", 3, "b"))


def test_a_partial_list_numbers_its_elements_and_its_tail(key):
    from clausal.logic.solve import solve  # noqa: F401 -- the engine builds SegLists
    x, t, s = Var(), Var(), Var()
    xt = SegList([ConcreteSeg([x]), VarSeg(t)])
    tt = SegList([ConcreteSeg([t]), VarSeg(t)])
    ys = SegList([ConcreteSeg([Var()]), VarSeg(s)])
    assert key(xt) == key(ys)
    assert key(xt) != key(tt)
    assert key(xt, x) != key(xt, t)
    # a hole is not an element variable: [*A, x] is not [X, x]
    assert key(SegList([VarSeg(t), ConcreteSeg(["x"])])) != key([x, "x"])


def test_key_subsumes_is_consistent_over_repeated_variables(key):
    """A complete ``p(X, Y)`` table covers ``p(1, 2)`` and ``p(1, 1)``; a
    ``p(X, X)`` table covers ``p(1, 1)`` only (and ``p(Z, Z)``, its own
    variant, not ``p(Z, W)``)."""
    sub = tabling._key_subsumes
    x, y = Var(), Var()
    assert sub(key(x, y), key(1, 2)) and sub(key(x, y), key(1, 1))
    assert sub(key(x, x), key(1, 1)) and not sub(key(x, x), key(1, 2))
    assert sub(key(x, y), key(x, x)) and not sub(key(x, x), key(x, y))
    assert sub(key(x, ("f", 1)), key(2, ("f", 1))) and not sub(key(x, ("f", 1)), key(2, ("f", 2)))


def test_naf_on_a_complete_repeated_variable_table(key):
    """At the NAF entry point: a complete ``p(X, X)`` table with the answer
    ``(1, 1)`` decides ``not p(1, 1)`` (false) but not ``not p(1, 2)``
    (no spawn without a db: the conservative truth)."""
    from clausal.logic.tabling import TableEntry, _naf_tabled
    x = Var()
    entry = TableEntry()
    entry.add_answer((1, 1))
    entry.status = "complete"
    ts = {("p", 2, key(x, x)): entry}
    assert _naf_tabled("p", 2, (1, 1), Trail(), ts) is False
    assert _naf_tabled("p", 2, (1, 2), Trail(), ts) is True
    a, b = Var(), Var()
    assert _naf_tabled("p", 2, (a, a), Trail(), ts) is False
    assert _naf_tabled("p", 2, (a, b), Trail(), ts) is True


def test_the_seam_structural_key_numbers_variables():
    """The seam's fallback key for an unhashable answer (a partial list, a
    dict holding a list) numbers variables the same way."""
    from clausal.logic.seam import _answer_key
    from clausal.terms import DictTerm
    x, y = Var(), Var()
    k = lambda *answer: _answer_key(make_subgoal_key, answer)  # noqa: E731
    assert k(DictTerm({"a": [x]}), x) == k(DictTerm({"a": [y]}), y)
    assert k(DictTerm({"a": [x]}), x) != k(DictTerm({"a": [x]}), y)
    sl = SegList([ConcreteSeg([x]), VarSeg(y)])
    assert k(sl, x) != k(sl, y)
    assert k(sl, x, y) == k(SegList([ConcreteSeg([y]), VarSeg(x)]), y, x)
