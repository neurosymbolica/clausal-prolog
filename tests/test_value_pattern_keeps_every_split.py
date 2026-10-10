"""A pattern with two or more holes, unified as a value, gives every split.

Ruled 2026-10-08: ``[*A, *B] = [1, 2]`` has three answers wherever it is
written, in the order ``append/3`` gives them.  Under a driver, unify checks
that one split fits, leaves the holes unbound and queues a pending goal that
binds each split in turn (``_drive_seg_unify`` in clausal/terms.py,
``clausal.logic.pending``).  A bare ``unify`` from Python binds the first
split.
"""

import pytest

from clausal.logic.cells import chars
from clausal.logic.solve import solve
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.logic.to_python import to_python
from clausal.terms import SegList, VarSeg
from clausal.testing import load_clausal_module

_SRC = r"""
via_value(T, A, B) <- (P is [*A, *B], P is T)
mem(L, A, B) <- (P is [*A, *B], member(P, L))
count(T, N) <- (findall(A-B, (P is [*A, *B], P is T), Xs), length(Xs, N))
count3(T, N) <- (findall(A, (P is [*A, *B, *C], P is T), Xs), length(Xs, N))
not_unifiable(T) <- (P is [*A, *B], not (P is T))
iso_not_unifiable(T) <- (P is [*A, *B], '\\='(P, T))
dif_then(T, A, B) <- (P is [*A, *B], dif(P, T), A is [1])
reified(T, A, B, R) <- (P is [*A, *B], '='(P, T, R))
frozen(T, A, B) <- (freeze(A, A is [1, *_]), P is [*A, *B], P is T)
middle(T, A, B) <- (P is [*A, 2, *B], P is T)
via_call(T, A, B) <- call('=', [*A, *B], T)
oc_splits(R) <- findall(A-B, (P is [*A, *B], unify_with_occurs_check(P, [1, 2])), R)
oc_cyclic(A, B) <- (P is [*A, *B], unify_with_occurs_check(P, [A]))
oc_none(R) <- (P is [*A, *B], findall(1, unify_with_occurs_check(P, [X, P]), R))
subsumed_by_list(R) <- (P is [*A, *B], findall(1, subsumes_term([1, 2], P), R))
subsumes_a_list(R) <- (P is [*A, *B], findall(1, subsumes_term(P, [1, 2]), R))
subsumes_cyclic(R) <- (P is [*A, *B], findall(1, subsumes_term(P, [A]), R))
oc_only_last(R) <- (P is [*A, *B, *B], findall(1, (unify_with_occurs_check(P, [A]), not acyclic_term(A)), R))
"""


@pytest.fixture(scope="module")
def mod(tmp_path_factory):
    p = tmp_path_factory.mktemp("splits") / "splits.seam"
    p.write_text("-allow_singletons\n" + _SRC)
    return load_clausal_module(p)


def _answers(mod, name, *args, nvars):
    vs = [Var() for _ in range(nvars)]
    return [tuple(to_python(deref(v)) for v in vs)
            for _ in solve((name, *args, *vs), mod)]


@pytest.mark.parametrize("target, splits", [
    ([1, 2], [([], [1, 2]), ([1], [2]), ([1, 2], [])]),
    (chars("ab"), [("", "ab"), ("a", "b"), ("ab", "")]),
    (b"ab", [([], [97, 98]), ([97], [98]), ([97, 98], [])]),
])
def test_every_split_in_append_order(mod, target, splits):
    assert _answers(mod, "via_value", target, nvars=2) == splits


def test_member_gives_every_split_of_every_element(mod):
    assert _answers(mod, "mem", [[1, 2], [3]], nvars=2) == [
        ([], [1, 2]), ([1], [2]), ([1, 2], []), ([], [3]), ([3], [])]


def test_equal_targets_each_give_their_own_splits(mod):
    # The removed split cache lost the second target's answers.
    assert len(_answers(mod, "mem", [[1, 2], [1, 2]], nvars=2)) == 6


def test_findall_collects_every_split(mod):
    assert _answers(mod, "count", [1, 2, 3], nvars=1) == [(4,)]
    assert _answers(mod, "count3", [1, 2, 3], nvars=1) == [(10,)]


def test_a_fixed_element_between_holes(mod):
    assert _answers(mod, "middle", [1, 2, 3, 2], nvars=2) == [
        ([1], [3, 2]), ([1, 2, 3], [])]


def test_call_unify(mod):
    assert len(_answers(mod, "via_call", [1, 2], nvars=2)) == 3


@pytest.mark.parametrize("name", ["not_unifiable", "iso_not_unifiable"])
def test_not_unifiable_fails_when_a_split_fits(mod, name):
    assert _answers(mod, name, [1, 2], nvars=0) == []
    assert _answers(mod, name, [1, 2, 3], nvars=0) == []


def test_iso_not_unifiable_succeeds_when_no_split_fits(mod):
    assert _answers(mod, "iso_not_unifiable", 7, nvars=0) == [()]


def test_dif_suspends_on_a_split_pattern(mod):
    [(a, b)] = [(deref(x), deref(y)) for x, y in [(Var(), Var())]
                for _ in solve(("dif_then", [1, 2], x, y), mod)]
    assert to_python(a) == [1]
    assert not isinstance(b, list)      # still open, and still constrained


def test_reified_unify_is_true_per_split_then_false(mod):
    answers = _answers(mod, "reified", [1, 2], nvars=3)
    assert [r for *_, r in answers] == [True, True, True, False]


def test_a_frozen_hole_filters_the_splits(mod):
    assert _answers(mod, "frozen", [1, 2, 3], nvars=2) == [
        ([1], [2, 3]), ([1, 2], [3]), ([1, 2, 3], [])]


def test_bare_unify_binds_the_first_split():
    a, b = Var(), Var()
    assert unify(SegList([VarSeg(a), VarSeg(b)]), [1, 2], Trail())
    assert (to_python(deref(a)), to_python(deref(b))) == ([], [1, 2])


# same_length/2 of a text used to build N substring holes, which with the
# split pending goal gave every way of cutting any text (2026-10-10).
_PL = """\
too_short(L) :- same_length("abc", L), L = "xy".
too_long(L) :- same_length("abc", L), L = "wxyz".
fits(L) :- same_length("abc", L), L = "xyz".
"""


@pytest.fixture(scope="module")
def pl(tmp_path_factory):
    p = tmp_path_factory.mktemp("same_length") / "same_length.clausal"
    p.write_text(_PL)
    return load_clausal_module(p)


@pytest.mark.parametrize("name, answers", [
    ("too_short", []), ("too_long", []), ("fits", [(["x", "y", "z"],)]),
])
def test_same_length_of_a_text_keeps_its_length(pl, name, answers):
    assert _answers(pl, name, nvars=1) == answers


# The queued split goal binds with plain unification, outside the caller's
# checks: occurs-check unify and subsumes_term run it themselves and check
# every answer (security review, 2026-10-10).
def test_occurs_check_unify_gives_every_split(mod):
    [(r,)] = _answers(mod, "oc_splits", nvars=1)
    assert len(r) == 3


def test_occurs_check_unify_drops_a_cyclic_split(mod):
    # The second split binds A to [A]: a cycle, so not an answer.
    assert _answers(mod, "oc_cyclic", nvars=2) == [([], [[]])]


def test_occurs_check_unify_with_no_acyclic_split(mod):
    # Every split of P against [X, P] contains P: none is an answer (the
    # first split was never occurs-checked before either).
    assert _answers(mod, "oc_none", nvars=1) == [([],)]


def test_subsumes_term_rejects_a_split_pattern_as_specific(mod):
    # Every split binds a hole of Specific, so nothing subsumes it.
    assert _answers(mod, "subsumed_by_list", nvars=1) == [([],)]
    assert _answers(mod, "subsumes_a_list", nvars=1) == [([1],)]


def test_subsumes_term_skips_a_cyclic_split(mod):
    # The split A = [A] is a cycle: rejected before its variables are
    # collected (collecting them overflowed).
    assert _answers(mod, "subsumes_cyclic", nvars=1) == [([],)]


def test_occurs_check_unify_when_only_the_last_split_fits(mod):
    # With a repeated hole the earlier splits fail and the last one binds
    # A to a cycle; it is queued like any other, so it is checked (it got
    # through unchecked on 1b717269 too).
    assert _answers(mod, "oc_only_last", nvars=1) == [([],)]
