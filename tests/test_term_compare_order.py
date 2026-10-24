"""``_helpers.term_compare`` (the pairwise standard order compare/3 and the
sorts fall back to for a cyclic or too-deep term) is ONE order with
``term_key``: on every acyclic pair the two agree, and over mixed triples
-- proper lists, improper lists, cyclic lists, compounds, atoms, numbers --
the order is transitive.  The review of the first cut found
``A = [a, b], B = [a|foo], X = [a|X]`` gave ``A < B``, ``X < A``, ``B < X``:
the fallback read a proper list against an improper one as the cons cells
both denote, where the key reads the list flat."""
from __future__ import annotations

import itertools
import random

from clausal.logic.builtins._helpers import term_compare, term_key
from clausal.logic.variables import Trail, Var, unify


def _sign(a, b):
    ka, kb = term_key(a), term_key(b)
    return -1 if ka < kb else (1 if kb < ka else 0)


def _cyclic_list(*prefix):
    """``X = [p1, ..., pn|X]`` as the cons cells (what a SegList walks to)."""
    x = Var()
    cell = x
    for e in reversed(prefix):
        cell = (".", e, cell)
    assert unify(x, cell, Trail())
    return x


ACYCLIC = [
    "a", "b", "foo", 1, 2, 1.0, [], ["a"], ["a", "b"], ["a", "b", "c"], ["b"],
    (".", "a", "foo"), (".", "a", (".", "b", "foo")), (".", "a", ["b"]),
    (".", "a", (".", "b", [])), ("f", "a"), ("f", ("f", "a")), ("g", "a", "b"),
    ("f", ["a"]), ["a", ("f", "b")], (".", 1, 2), [1, 2], (".", 1, [2, 3]),
]


def test_the_fallback_agrees_with_the_key_on_every_acyclic_pair():
    for a, b in itertools.product(ACYCLIC, repeat=2):
        assert term_compare(a, b) == _sign(a, b), (a, b)
        assert term_compare(a, b) == -term_compare(b, a), (a, b)


def test_the_reviewed_triple_is_transitive():
    a, b, x = ["a", "b"], (".", "a", "foo"), _cyclic_list("a")
    assert term_compare(a, b) == -1          # b against foo: atoms
    assert term_compare(a, x) == -1          # b against the cycle's cell: atom < compound
    assert term_compare(b, x) == -1          # foo against the cell
    assert term_compare(x, a) == 1 and term_compare(x, b) == 1


def test_transitive_over_random_mixed_triples():
    pool = ACYCLIC + [_cyclic_list("a"), _cyclic_list("a", "b"), _cyclic_list(1),
                      _cyclic_list("b"), _cyclic_list("a", "foo")]
    rng = random.Random(2026_10_24)
    for _ in range(3000):
        p, q, r = (rng.choice(pool) for _ in range(3))
        pq, qr, pr = term_compare(p, q), term_compare(q, r), term_compare(p, r)
        if pq <= 0 and qr <= 0:
            assert pr <= 0, (p, q, r)
        if pq >= 0 and qr >= 0:
            assert pr >= 0, (p, q, r)
        if pq == 0 and qr == 0:
            assert pr == 0, (p, q, r)
