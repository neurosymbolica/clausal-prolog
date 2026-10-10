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
