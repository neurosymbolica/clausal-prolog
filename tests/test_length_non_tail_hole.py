"""length/2 of a list pattern whose hole is not its tail
(todo/done/length-of-a-pattern-with-a-non-tail-hole-has-no-answer-2026-10-11.md).

``P is [*A, *B], length(P, N)`` answers as ISO ``length(P, N)`` on the
equivalent partial list would, then ``P = A ++ B``: for each length, in
increasing order, every split of that many fresh variables in append/3
order.  ``[a|T]`` (the hole is the tail) already worked."""
from clausal.logic.solve import _deref_walk, solve
from clausal.logic.variables import Var, is_var
from tests._suffix import SEAM

_SRC = """\
l(N, A, B) <- (P is [*A, *B], length(P, N))
l1(N, A, B) <- (P is [*A, 1, *B], length(P, N))
l3(N, A, B, C) <- (P is [*A, *B, 9, *C], length(P, N))
"""


def _mod(tmp_path):
    from clausal.import_hook import _load_module
    p = tmp_path / f"length_hole{SEAM}"
    p.write_text(_SRC)
    return _load_module("length_hole", str(p))


def _shape(t):
    """A walked answer with each unbound variable as ``'_'``."""
    if is_var(t):
        return "_"
    if isinstance(t, list):
        return [_shape(x) for x in t]
    return t


def _answers(m, goal, out, limit=50):
    return [_shape(_deref_walk(out))
            for _, _ in zip(solve(goal, m), range(limit))]


def test_bound_length_every_split_in_append_order(tmp_path):
    m = _mod(tmp_path)
    failures = []
    for n in range(4):
        A, B = Var(), Var()
        got = _answers(m, ("l", n, A, B), [A, B])
        want = [[["_"] * i, ["_"] * (n - i)] for i in range(n + 1)]
        if got != want:
            failures.append((n, got, want))
    assert not failures, failures


def test_bound_length_with_a_concrete_element(tmp_path):
    m = _mod(tmp_path)
    failures = []
    for n, want in [(0, []), (1, [[[], []]]),
                    (2, [[[], ["_"]], [["_"], []]])]:
        A, B = Var(), Var()
        got = _answers(m, ("l1", n, A, B), [A, B])
        if got != want:
            failures.append((n, got, want))
    assert not failures, failures


def test_bound_length_three_holes_and_an_element(tmp_path):
    # [*A, *B, 9, *C] of length 2: the one free place goes to C, B, then A
    m = _mod(tmp_path)
    A, B, C = Var(), Var(), Var()
    got = _answers(m, ("l3", 2, A, B, C), [A, B, C])
    assert got == [[[], [], ["_"]], [[], ["_"], []], [["_"], [], []]]


def test_unbound_length_enumerates_lengths_then_splits(tmp_path):
    m = _mod(tmp_path)
    A, B, N = Var(), Var(), Var()
    got = _answers(m, ("l", N, A, B), [N, A, B], limit=6)
    want = [[n, ["_"] * i, ["_"] * (n - i)]
            for n in range(3) for i in range(n + 1)]
    assert got == want[:6]


def test_unbound_length_starts_at_the_concrete_length(tmp_path):
    m = _mod(tmp_path)
    A, B, N = Var(), Var(), Var()
    got = _answers(m, ("l1", N, A, B), [N, A, B], limit=3)
    assert got == [[1, [], []], [2, [], ["_"]], [2, ["_"], []]]


def test_errors_on_n_still_raised(tmp_path):
    from clausal.logic.exceptions import LogicException
    m = _mod(tmp_path)
    failures = []
    for bad in (-1, "a", 1.0):
        try:
            list(solve(("l", bad, Var(), Var()), m))
            failures.append((bad, "no error"))
        except LogicException:
            pass
    assert not failures, failures
