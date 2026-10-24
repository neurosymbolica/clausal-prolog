"""One term, one reading: a star bound to a non-list (2026-10-22).

Ruling (todo/done/star-splice-readings-and-cyclic-seglist-eq-2026-10-14.md):
a hole bound to a non-list is the IMPROPER TAIL -- never spliced as
characters -- and a star element must be a list.  So ``[*A, x]`` with ``A``
the atom ``foo`` is ``type_error(list, foo)``, ``[*A]`` is ``foo`` and
``[b, *A]`` is ``[b|foo]``, and the answer is the same whether ``A`` was
bound before the list was built, after it, or through an alias.

Before: ``[*A, x]`` read three ways (``[foo, x]``, ``"foox"``, a type
error) depending on WHEN ``A`` was bound; ``[*A, *B]`` with ``A = [b|foo]``
spliced ``foo``'s characters even when ``B = []``; and the seam ``==``
answered FALSE for two identical cyclic lists (Scryer: yes).
"""

from __future__ import annotations

import itertools
import os
import random
import re

import pytest

from clausal.logic.exceptions import LogicException
from clausal.logic.runtime.body_star_unify import (
    _build_multi_star_list, _build_star_list,
)
from clausal.logic.runtime.list_unify import (
    _head_list_unify_output, _head_list_unify_output_py,
)
from clausal.logic.solve import call
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.terms import (
    ConcreteSeg, SegList, VarSeg, _rational_eq, term_writeq,
)
from clausal.testing import load_clausal_module

_N = itertools.count()

# Each predicate builds one list from stars and binds the stars BEFORE the
# build (b), AFTER it (a) or through an ALIAS bound after it (u); ``R`` is
# read back through a second unification, so the walk runs.
SEAM = """\
-private([a, x, b, c, d, foo, yes, no])
cons_cd(C) <- (C is [c, *D], D is d)
# I1: [*A, *B] with A the improper list [b|foo]
i1_nil_b(R) <- (T is foo, A is [b, *T], B is [], R is [*A, *B])
i1_nil_a(R) <- (R is [*A, *B], A is [b, *T], T is foo, B is [], P is R, R is P)
i1_nil_u(R) <- (R is [*A, *B], A is A2, A2 is [b, *T], T is foo, B is [], P is R, R is P)
i1_x_b(R) <- (T is foo, A is [b, *T], B is [x], R is [*A, *B])
i1_x_a(R) <- (R is [*A, *B], A is [b, *T], T is foo, B is [x], P is R, R is P)
i1_num_b(R) <- (T is 1, A is [b, *T], B is [], R is [*A, *B])
i1_num_a(R) <- (R is [*A, *B], A is [b, *T], T is 1, B is [], P is R, R is P)
i1_cons_b(R) <- (cons_cd(T), A is [b, *T], B is [], R is [*A, *B])
i1_cons_a(R) <- (R is [*A, *B], A is [b, *T], cons_cd(T), B is [], P is R, R is P)
# I2: [*A, x] with A an atom or a number
i2_atom_b(R) <- (A is foo, R is [*A, x])
i2_atom_a(R) <- (R is [*A, x], A is foo, P is R, R is P)
i2_atom_u(R) <- (R is [*A, x], A is A2, A2 is foo, P is R, R is P)
i2_num_b(R) <- (A is 1, R is [*A, x])
i2_num_a(R) <- (R is [*A, x], A is 1, P is R, R is P)
i2_improper_a(R) <- (R is [*A, x], A is [b, *T], T is foo, P is R, R is P)
# The tail position stays the improper tail
tail_atom_b(R) <- (A is foo, R is [x, *A])
tail_atom_a(R) <- (R is [x, *A], A is foo, P is R, R is P)
tail_only_b(R) <- (A is foo, R is [*A])
tail_only_a(R) <- (R is [*A], A is foo, P is R, R is P)
# M6: [*A, *B] with A an atom
m6_x_b(R) <- (A is foo, B is [x], R is [*A, *B])
m6_x_a(R) <- (R is [*A, *B], A is foo, B is [x], P is R, R is P)
m6_x_u(R) <- (R is [*A, *B], B is [x], A is A2, A2 is foo, P is R, R is P)
m6_nil_b(R) <- (A is foo, B is [], R is [*A, *B])
m6_nil_a(R) <- (R is [*A, *B], A is foo, B is [], P is R, R is P)
# M4: the seam == on cyclic lists
m4_same(R) <- (X is [a, *X], Y is [a, *Y], X == Y, R is yes)
m4_unrolled(R) <- (X is [a, *X], Y is [a, a, *Y], X == Y, R is yes)
m4_differ(R) <- (X is [a, *X], Y is [b, *Y], X == Y, R is yes)
m4_period(R) <- (X is [a, *X], Y is [a, b, *Y], X == Y, R is yes)
m4_ne(R) <- (X is [a, *X], Y is [a, *Y], X != Y, R is yes)
# M5: a cyclic star before an element
m5(R) <- (X is [a, *X], R is [*X, x])
# Cycles reached out of phase (review 2026-10-22): one rational tree
m4_phase(R) <- (T is [a, b, *T], X is [b, *T], Y is [b, a, *Y], X == Y, R is yes)
m4_phase_ne(R) <- (T is [a, b, *T], X is [b, *T], Y is [b, a, *Y], X != Y, R is yes)
m4_prefix(R) <- (T is [a, *T], X is [b, *T], Z is [a, a, *Z], Y is [b, *Z], X == Y, R is yes)
m4_prefix_ne(R) <- (T is [a, *T], X is [b, *T], Y is [a, b, *Y], X == Y, R is yes)
# An unbound hole before the improper tail
p3(R) <- (Q is [*A, x, *T], T is foo, Q is [1, 2, x], R is yes)
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    d = tmp_path_factory.mktemp("star_splice_readings")
    p = d / f"_star_splice_readings{next(_N)}.seam"
    p.write_text(SEAM)
    return load_clausal_module(str(p))


def _first(mod, name):
    r = Var()
    for _ in call(name, r, module=mod):
        return term_writeq(deref(r))
    return None


def _type_error_list(exc_info, culprit):
    formal = exc_info.value.term[1]
    assert formal[:2] == ("type_error", "list"), exc_info.value.term
    assert term_writeq(formal[2]) == culprit, exc_info.value.term


# ── I1: an empty hole after the improper tail is nothing ─────────────────────

@pytest.mark.parametrize("name, out", [
    ("i1_nil_b", "[b|foo]"), ("i1_nil_a", "[b|foo]"), ("i1_nil_u", "[b|foo]"),
    ("i1_num_b", "[b|1]"), ("i1_num_a", "[b|1]"),
    ("i1_cons_b", "[b,c|d]"), ("i1_cons_a", "[b,c|d]"),
])
def test_an_empty_star_after_the_improper_tail_is_nothing(mod, name, out):
    assert _first(mod, name) == out


@pytest.mark.parametrize("name", ["i1_x_b", "i1_x_a"])
def test_a_star_after_an_improper_star_is_a_type_error(mod, name):
    with pytest.raises(LogicException) as exc:
        _first(mod, name)
    _type_error_list(exc, "[b|foo]")


# ── I2 / M6: a non-list star before an element is a type error ──────────────

@pytest.mark.parametrize("name, culprit", [
    ("i2_atom_b", "foo"), ("i2_atom_a", "foo"), ("i2_atom_u", "foo"),
    ("i2_num_b", "1"), ("i2_num_a", "1"),
    ("i2_improper_a", "[b|foo]"),
    ("m6_x_b", "foo"), ("m6_x_a", "foo"), ("m6_x_u", "foo"),
])
def test_a_non_list_star_before_an_element_is_a_type_error(mod, name, culprit):
    with pytest.raises(LogicException) as exc:
        _first(mod, name)
    _type_error_list(exc, culprit)


@pytest.mark.parametrize("name, out", [
    ("tail_atom_b", "[x|foo]"), ("tail_atom_a", "[x|foo]"),
    ("tail_only_b", "foo"), ("tail_only_a", "foo"),
    ("m6_nil_b", "foo"), ("m6_nil_a", "foo"),
])
def test_a_non_list_last_star_is_the_tail(mod, name, out):
    assert _first(mod, name) == out


# ── M4: the seam == on cyclic lists answers as Scryer does ──────────────────

@pytest.mark.parametrize("name, out", [
    ("m4_same", "yes"), ("m4_unrolled", "yes"), ("m4_differ", None),
    ("m4_period", None), ("m4_ne", None),
    ("m4_phase", "yes"), ("m4_phase_ne", None), ("m4_prefix", "yes"),
    ("m4_prefix_ne", None),
])
def test_seam_eq_on_cyclic_lists(mod, name, out):
    assert _first(mod, name) == out


# ── M5: a cyclic star before an element raises a catchable type error ───────

def test_a_cyclic_star_before_an_element_is_a_type_error(mod):
    with pytest.raises(LogicException) as exc:
        _first(mod, "m5")
    formal = exc.value.term[1]
    assert formal[:2] == ("type_error", "list"), exc.value.term
    assert isinstance(str(exc.value), str)


# ── The SegList walk itself, hole by hole ────────────────────────────────────

def _improper_b_foo(tail="foo"):
    t = Var()
    unify(t, tail, Trail())
    return SegList([ConcreteSeg(["b"]), VarSeg(t)])


def _bound(v):
    x = Var()
    unify(x, v, Trail())
    return x


@pytest.mark.parametrize("after, out", [
    ([], "[b|foo]"),
    ([ConcreteSeg([])], "[b|foo]"),
    ([VarSeg(_bound([]))], "[b|foo]"),
    ([VarSeg(_bound(SegList([])))], "[b|foo]"),
    ([VarSeg(_bound([])), ConcreteSeg([])], "[b|foo]"),
])
def test_walk_empty_content_after_the_tail_is_nothing(after, out):
    w = SegList([VarSeg(_bound(_improper_b_foo())), *after])._walk_raw()
    assert term_writeq(w) == out


@pytest.mark.parametrize("after", [
    [ConcreteSeg(["x"])],
    [VarSeg(_bound(["x"]))],
    [VarSeg(_bound(SegList([ConcreteSeg(["x"])])))],
    [VarSeg(_bound(("$chars", "x")))],
    [VarSeg(Var())],
    [VarSeg(_bound("foo"))],
])
def test_walk_content_after_the_tail_is_a_type_error(after):
    seg = SegList([VarSeg(_bound(_improper_b_foo())), *after])
    with pytest.raises(LogicException) as exc:
        seg._walk_raw()
    _type_error_list(exc, "[b|foo]")
    with pytest.raises(LogicException):
        seg.__walk__()


@pytest.mark.parametrize("tail, out", [("foo", "foo"), (1, "1"), ((".", "c", "d"), "[c|d]")])
def test_walk_a_non_list_hole_before_an_element_is_a_type_error(tail, out):
    seg = SegList([VarSeg(_bound(tail)), ConcreteSeg(["x"])])
    with pytest.raises(LogicException) as exc:
        seg._walk_raw()
    _type_error_list(exc, out)


def test_walk_never_splices_an_atom_as_characters():
    # [*A, *B] with A = foo, B = [x]: foo is not a list, and never "f, o, o".
    seg = SegList([VarSeg(_bound("foo")), VarSeg(_bound(["x"]))])
    with pytest.raises(LogicException) as exc:
        seg._walk_raw()
    _type_error_list(exc, "foo")
    # The culprit is the star whose value is not a list, at any depth.
    inner = SegList([VarSeg(_bound("foo")), VarSeg(_bound(["x"]))])
    with pytest.raises(LogicException) as exc:
        SegList([VarSeg(_bound(inner))])._walk_raw()
    _type_error_list(exc, "foo")
    with pytest.raises(LogicException) as exc:
        SegList([VarSeg(_bound(SegList([VarSeg(_bound("foo"))]))),
                 ConcreteSeg(["x"])])._walk_raw()
    _type_error_list(exc, "foo")


def _instantiation_error(exc_info):
    assert exc_info.value.term[1] == "instantiation_error", exc_info.value.term


def test_walk_an_unbound_hole_before_the_tail_is_an_instantiation_error():
    # [*A, x|foo] with A unbound cannot be spelled yet: neither a SegList
    # (its holes hold lists) nor cons cells (A has no length), but a term
    # once A is bound -- instantiation_error (operator ruling 2026-10-23;
    # it was a raw PartialTermError), never "x, f, o, o".
    seg = SegList([VarSeg(Var()), ConcreteSeg(["x"]), VarSeg(_bound("foo"))])
    with pytest.raises(LogicException) as exc:
        seg._walk_raw()
    _instantiation_error(exc)
    seg = SegList([VarSeg(Var()), VarSeg(_bound(1))])
    with pytest.raises(LogicException) as exc:
        seg.__walk__()
    _instantiation_error(exc)


def test_seam_unbound_hole_before_the_tail_is_catchable(mod):
    with pytest.raises(LogicException) as exc:
        _first(mod, "p3")
    _instantiation_error(exc)


# ── The builders agree with the walk ─────────────────────────────────────────

def _out(fn):
    r = Var()
    assert fn(r)
    return term_writeq(deref(r))


def _run_output(impl, before, star, after):
    return _out(lambda r: impl(r, list(before), star, list(after), Trail()))


@pytest.mark.parametrize("impl", [_head_list_unify_output, _head_list_unify_output_py],
                         ids=["c", "py"])
@pytest.mark.parametrize("star, culprit", [
    (_bound("foo"), "foo"), (_bound(1), "1"), (_bound((".", "c", "d")), "[c|d]"),
    (_bound(_improper_b_foo()), "[b|foo]"),
])
def test_output_builders_reject_a_non_list_star_before_an_element(impl, star, culprit):
    with pytest.raises(LogicException) as exc:
        _run_output(impl, [], star, ["x"])
    _type_error_list(exc, culprit)
    with pytest.raises(LogicException) as exc:
        _run_output(impl, ["q"], star, ["x"])
    _type_error_list(exc, culprit)


@pytest.mark.parametrize("impl", [_head_list_unify_output, _head_list_unify_output_py],
                         ids=["c", "py"])
def test_output_builders_keep_the_tail_and_the_nil_spellings(impl):
    assert _run_output(impl, ["q"], _bound("foo"), []) == "[q|foo]"
    assert _run_output(impl, ["qq"], _bound(()), ["xx"]) == "[qq,xx]"
    assert _run_output(impl, ["qq"], _bound("[]"), ["xx"]) == "[qq,xx]"
    assert _run_output(impl, ["qq"], _bound([]), ["xx"]) == "[qq,xx]"


@pytest.mark.parametrize("star, culprit", [
    (_bound("foo"), "foo"), (_bound(1), "1"), (_bound(_improper_b_foo()), "[b|foo]"),
])
def test_build_star_list_rejects_a_non_list_star_before_an_element(star, culprit):
    with pytest.raises(LogicException) as exc:
        _build_star_list([], star, ["x"])
    _type_error_list(exc, culprit)
    assert term_writeq(_build_star_list(["q"], star, [])) in ("[q|foo]", "[q|1]", "[q,b|foo]")


def test_build_star_list_nil_spellings_are_empty():
    assert term_writeq(_build_star_list(["qq"], _bound(()), ["xx"])) == "[qq,xx]"
    assert term_writeq(_build_star_list(["qq"], _bound("[]"), ["xx"])) == "[qq,xx]"
    assert term_writeq(_build_multi_star_list(
        [("fixed", ["qq"]), ("star", _bound(())), ("star", _bound("[]")),
         ("fixed", ["xx"])])) == "[qq,xx]"


@pytest.mark.parametrize("segments, out", [
    ([("star", _bound(_improper_b_foo())), ("star", _bound([]))], "[b|foo]"),
    ([("star", _bound(_improper_b_foo())), ("fixed", []), ("star", _bound(()))], "[b|foo]"),
    ([("star", _bound(_improper_b_foo(1))), ("star", _bound([]))], "[b|1]"),
    ([("star", _bound("foo")), ("star", _bound([]))], "foo"),
    ([("fixed", ["q"]), ("star", _bound([1])), ("star", _bound("foo"))], "[q,1|foo]"),
])
def test_build_multi_star_list_tail(segments, out):
    assert term_writeq(_build_multi_star_list(segments)) == out


@pytest.mark.parametrize("segments, culprit", [
    ([("star", _bound(_improper_b_foo())), ("star", _bound(["x"]))], "[b|foo]"),
    ([("star", _bound("foo")), ("star", _bound(["x"]))], "foo"),
    ([("star", _bound("foo")), ("fixed", ["x"]), ("star", _bound([]))], "foo"),
    ([("star", _bound("foo")), ("star", Var())], "foo"),
    ([("star", _bound(1)), ("star", _bound(("$chars", "x")))], "1"),
    ([("star", _bound("foo")), ("star", _bound("foo"))], "foo"),
])
def test_build_multi_star_list_rejects_content_after_a_non_list_star(segments, culprit):
    with pytest.raises(LogicException) as exc:
        _build_multi_star_list(segments)
    _type_error_list(exc, culprit)


def test_build_multi_star_list_unbound_hole_before_the_tail_is_an_instantiation_error():
    with pytest.raises(LogicException) as exc:
        _build_multi_star_list([("star", Var()), ("star", _bound("foo"))])
    _instantiation_error(exc)


# ── SegList.__eq__ on cyclic and improper lists ──────────────────────────────

def _cyclic(*cycle, prefix=()):
    """``[*prefix|T]`` with ``T = [*cycle|T]``, hole-built."""
    x = Var()
    unify(x, SegList([ConcreteSeg(list(cycle)), VarSeg(x)]), Trail())
    if not prefix:
        return deref(x)
    return SegList([ConcreteSeg(list(prefix)), VarSeg(x)])


def test_seglist_eq_identical_cyclic_lists():
    assert _cyclic("a") == _cyclic("a")
    assert _cyclic("a") == _cyclic("a", "a")
    assert _cyclic("a", "b") == _cyclic("a", "b", "a", "b")
    assert not (_cyclic("a") == _cyclic("b"))
    assert not (_cyclic("a") == _cyclic("a", "b"))
    assert _cyclic("a") != _cyclic("b")
    # Reached out of phase: [b|T], T = [a,b|T] against Y = [b,a|Y] is one
    # rational tree (Scryer: yes); this pair HUNG when every lap re-walked
    # the SegLists into fresh cells.
    assert _cyclic("a", "b", prefix=("b",)) == _cyclic("b", "a")
    assert not (_cyclic("a", "b", prefix=("b",)) != _cyclic("b", "a"))
    assert _cyclic("a", prefix=("b",)) == _cyclic("a", "a", prefix=("b",))
    assert not (_cyclic("a", prefix=("b",)) == _cyclic("b", "a", "a"))
    assert not (_cyclic("a", prefix=("b",)) == _cyclic("a", "b"))
    assert not (_cyclic("a", "b", prefix=("b",)) == _cyclic("a", "b"))


def test_seglist_eq_cyclic_against_cons_cells_and_improper():
    x = Var()
    cell = (".", "a", x)
    unify(x, cell, Trail())
    assert _cyclic("a") == cell
    assert _cyclic("a") == x
    assert not (_cyclic("a") == (".", "a", "foo"))
    assert _improper_b_foo() == (".", "b", "foo")
    assert _improper_b_foo() == _improper_b_foo()
    assert not (_improper_b_foo() == _improper_b_foo(1))
    assert not (_improper_b_foo() == ["b", "foo"])


def test_cyclic_seglist_repr_terminates():
    r = repr(_cyclic("a"))
    assert isinstance(r, str)


# ── Deep improper lists in the standard order (M1) ──────────────────────────

DEEP = """\
mk(0, L, L).
mk(N, L, [N|T]) :- N > 0, N1 is N-1, mk(N1, L, T).
m1a(O) :- mk(500, foo, A), mk(500, foo, B), compare(O, A, B).
m1b(O) :- mk(500, foo, A), mk(500, bar, B), compare(O, A, B).
m1c :- mk(500, foo, A), msort([A, A], [A, A]), sort([A, A], [A]).
m1d(N) :- mk(1500, [], L), assertz(big(L)), big(X), length(X, N).
m3c(O) :- X = [a|X], Y = [a|Y], compare(O, X, Y).
"""


@pytest.fixture(scope="module")
def deep(tmp_path_factory):
    d = tmp_path_factory.mktemp("star_splice_deep")
    p = d / f"_star_splice_deep{next(_N)}.pl"
    p.write_text(DEEP)
    return load_clausal_module(str(p))


def test_compare_and_sort_on_a_500_cell_improper_list(deep):
    # term_key recursed once per cons cell and overflowed at about 500.
    assert _first(deep, "m1a") == "="
    assert _first(deep, "m1b") == ">"
    assert next(call("m1c", module=deep), None) is not None


def test_assertz_of_a_1500_cell_list(deep):
    assert _first(deep, "m1d") == "1500"


def test_compare_on_two_distinct_cyclic_lists_answers_as_scryer(deep):
    # Scryer: ``=`` -- two cyclic lists that are one rational tree.  Until
    # 2026-10-24 this raised a clean RecursionError (the spine loop had no
    # cycle-aware comparison); compare/3 now falls back to the pairwise
    # order (``_helpers.term_compare``) when the key cannot be built.  See
    # tests/iso/test_cyclic_terms_scryer.py for the row against the oracle.
    assert _first(deep, "m3c") == "="


# ── _rational_eq: a fuzz over acyclic and cyclic shapes ─────────────────────

def _random_term(rng, depth):
    k = rng.random()
    if depth <= 0 or k < 0.3:
        return rng.choice([0, 1, 1.0, "a", "b", "foo", ()])
    if k < 0.6:
        return [_random_term(rng, depth - 1) for _ in range(rng.randint(0, 3))]
    if k < 0.8:
        return ("f", *[_random_term(rng, depth - 1) for _ in range(rng.randint(1, 2))])
    return (".", _random_term(rng, depth - 1), _random_term(rng, depth - 1))


def _unroll(prefix, cycle, n):
    out = list(prefix)
    while len(out) < n:
        out.extend(cycle)
    return out[:n]


def test_rational_eq_agrees_with_python_equality_on_acyclic_terms():
    rng = random.Random(2026_10_22)
    for _ in range(400):
        a = _random_term(rng, 4)
        b = a if rng.random() < 0.5 else _random_term(rng, 4)
        assert _rational_eq(a, b) == (a == b), (a, b)
    # A copy is equal; a Var is only itself.
    v = Var()
    assert _rational_eq(["x", v, ("f", 1)], ["x", v, ("f", 1)])
    assert not _rational_eq([v], [Var()])


def test_rational_eq_on_deep_and_cyclic_terms():
    # A cons chain of 5000 cells needs no recursion.
    a = b = "foo"
    for i in range(5000):
        a, b = (".", i, a), (".", i, b)
    assert _rational_eq(a, b)
    assert not _rational_eq(a, (".", 4999, (".", 4998, "foo")))
    # Two cyclic lists are equal iff their eventually periodic sequences
    # are: the bisimulation Scryer's ==/2 decides.  Prefixes put the two
    # cycles out of phase.
    rng = random.Random(7)
    for _ in range(300):
        pp = [rng.choice("ab") for _ in range(rng.randint(0, 2))]
        p = [rng.choice("ab") for _ in range(rng.randint(1, 4))]
        qp = [rng.choice("ab") for _ in range(rng.randint(0, 2))]
        q = [rng.choice("ab") for _ in range(rng.randint(1, 4))]
        n = len(pp) + len(qp) + 2 * len(p) * len(q)
        same = _unroll(pp, p, n) == _unroll(qp, q, n)
        got = _rational_eq(_cyclic(*p, prefix=pp), _cyclic(*q, prefix=qp))
        assert got == same, (pp, p, qp, q)
    # A cyclic compound that differs in an acyclic leaf is not equal, and
    # the same compound built twice is (the UNSOUND shapes of
    # tests/test_partial_list_improper_tail.py).
    x, y = Var(), Var()
    unify(x, ("f", x, [1, 2, 3]), Trail())
    unify(y, ("f", y, [1, 2, 4]), Trail())
    assert not _rational_eq(x, y)
    z = Var()
    unify(z, ("f", z, [1, 2, 3]), Trail())
    assert _rational_eq(x, z)


# ── The Scryer oracle on random prefixed cycles ──────────────────────────────

def _scryer_cycle_cases(seed, n_cases):
    rng = random.Random(seed)
    cases = []
    for _ in range(n_cases):
        cases.append(tuple(
            [rng.choice("ab") for _ in range(rng.randint(0, 2))]
            if k % 2 == 0 else [rng.choice("ab") for _ in range(rng.randint(1, 3))]
            for k in range(4)))
    return cases


def _pl_cyclic(prefix, cycle, t, x):
    """``T = [*cycle|T], X = [*prefix|T]`` as Prolog text (``X = T`` when
    the prefix is empty)."""
    tail = f"[{','.join(prefix)}|{t}]" if prefix else t
    return f"{t} = [{','.join(cycle)}|{t}], {x} = {tail}"


@pytest.mark.parametrize("seed", [1, 2])
def test_rational_eq_agrees_with_scryer_on_random_cycles(seed, tmp_path):
    # 150 random pairs of [*P|T], T = [*C|T] per seed, with prefixes of 0-2
    # and cycles of 1-3 atoms, so the cycles are reached out of phase and
    # unrolled differently; Scryer's ==/2 is the oracle.  (The hanging case
    # of the 2026-10-22 review, T = [a,b|T], X = [b|T] against Y = [b,a|Y],
    # is in this family.)
    from tests._oracles import SCRYER, run_scryer
    if not os.path.exists(SCRYER):
        pytest.skip(f"scryer not built at {SCRYER}")
    cases = _scryer_cycle_cases(seed, 150)
    lines = [":- use_module(library(between))."]
    for i, (pp, p, qp, q) in enumerate(cases):
        lines.append(f"c({i}) :- {_pl_cyclic(pp, p, 'T', 'X')}, "
                     f"{_pl_cyclic(qp, q, 'S', 'Y')}, X == Y.")
    lines.append("main :- between(0, %d, N), (c(N) -> write(N-yes) ; write(N-no)), "
                 "nl, fail." % (len(cases) - 1))
    lines.append("main.")
    pl = tmp_path / "cycles.pl"
    pl.write_text("\n".join(lines) + "\n")
    out = run_scryer(str(pl), ["main"], timeout=120).stdout
    oracle = {}
    for line in out.splitlines():
        m = re.fullmatch(r"(\d+)-(yes|no)", line.strip())
        if m:
            oracle[int(m.group(1))] = m.group(2) == "yes"
    assert len(oracle) == len(cases), out[-500:]
    problems = []
    for i, (pp, p, qp, q) in enumerate(cases):
        got = _rational_eq(_cyclic(*p, prefix=pp), _cyclic(*q, prefix=qp))
        if got != oracle[i]:
            problems.append((pp, p, qp, q, got, oracle[i]))
    assert not problems, problems


def test_term_key_on_a_cons_cell_bound_to_itself_raises_rather_than_loops():
    # X = '.'(a, X) with no SegList on the spine: the spine loop recorded
    # only SegLists and looped (base: RecursionError).
    from clausal.logic.builtins._helpers import term_key
    x = Var()
    unify(x, (".", "a", x), Trail())
    with pytest.raises(RecursionError):
        term_key(deref(x))
    y = Var()
    unify(y, (".", "a", (".", "b", y)), Trail())
    with pytest.raises(RecursionError):
        term_key(y)
