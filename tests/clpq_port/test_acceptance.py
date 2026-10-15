"""Acceptance (Task 15): filled_rectangle under the port against the oracle.

filled_rectangle(A, C) fills an A x 1 rectangle with the list C of squares,
all of different sizes (Colmerauer's example, the clp(q,r) distribution's
examples/squares.pl).  The program is loaded from
``filled_rectangle.pl`` in ``CLAUSAL_CLPQ_EXAMPLES_DIR`` (default
``/workspace/claude_sicstus_clpq``, tests/clpq_example_files.py) with
``use_module(clpq)`` changed to ``use_module(library(clpq))``; the tests skip
when it is missing, or fail when CLAUSAL_REQUIRE_CLPQ_EXAMPLES=1.

The oracle is the LOCAL clpq.pl port of clp(q,r) 1.3.3 running on Scryer
(``tests/clpq_oracle.py``); upstream Scryer has no CLP(Q).  Agreement is two
ports of the same 1.3.3 source agreeing, not an independent check: a bug
1.3.3 itself has would show in both.

What the program must give: n = 1 has one answer, the trivial 1 x 1
square.  No perfect squared rectangle has 2 to 8 squares, so n = 2..8 has
no answer.  n = 9 has 8 answers, the same on both ports; the first two
are the two that squares.pl's comment documents.  Legacy gives wrong answers
below 9 (DEVIATIONS.md D22); it is not tested here.

n <= 7 runs in the default suite; CLAUSAL_SLOW_TESTS=1 runs n = 8 and the
n = 9 comparison as well (ruling R32).
"""
import os
import time

from fractions import Fraction

import pytest

from tests.clpq_example_files import example_file
from tests.clpq_oracle import clausal_answers, oracle_answers, same_solution_sets

PROGRAM = "filled_rectangle.pl"


def _source():
    text = example_file(PROGRAM).read_text()
    assert ":- use_module(clpq)." in text
    return text.replace(":- use_module(clpq).", ":- use_module(library(clpq)).")


def _query(n):
    squares = [f"C{i}" for i in range(1, n + 1)]
    return f"C = [{', '.join(squares)}], filled_rectangle(A, C)", ["A", "C"] + squares


def _without_the_list(answers):
    """C is also shown as C1..Cn, each an exact number; drop the list text."""
    for answer in answers:
        answer.bindings.pop("C", None)
    return answers


def port(n):
    goal, shown = _query(n)
    return _without_the_list(clausal_answers(_source(), goal, shown, "holzbaur"))


def oracle(n, timeout=60):
    goal, shown = _query(n)
    program = ":- use_module(library(lists)).\n" + _source()
    return _without_the_list(oracle_answers(program, goal, shown, timeout=timeout))


def test_one_square_is_the_trivial_rectangle():
    got, want = port(1), oracle(1)
    assert len(want) == 1 and want[0].bindings["A"] == 1
    assert same_solution_sets(got, want) == (True, "")


@pytest.mark.parametrize("n", range(2, 8))
def test_no_perfect_squared_rectangle_has_fewer_than_9_squares(n):
    assert oracle(n) == []
    assert port(n) == []


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="about 3 s on the port, set CLAUSAL_SLOW_TESTS=1")
def test_no_perfect_squared_rectangle_has_8_squares():
    assert port(8) == []


@pytest.mark.skipif(os.environ.get("CLAUSAL_SLOW_TESTS") != "1",
                    reason="about 30 s (port and oracle), set CLAUSAL_SLOW_TESTS=1")
def test_filled_rectangle_with_9_squares_answers_as_the_oracle(record_property):
    start = time.perf_counter()
    got = port(9)
    port_seconds = time.perf_counter() - start
    start = time.perf_counter()
    want = oracle(9, timeout=600)
    oracle_seconds = time.perf_counter() - start
    record_property("port_seconds", round(port_seconds, 1))
    record_property("oracle_seconds", round(oracle_seconds, 1))
    print(f"filled_rectangle n=9: port {port_seconds:.1f} s (clausal CLI, "
          f"CLAUSAL_CLPQ=holzbaur), local clpq.pl port on Scryer "
          f"{oracle_seconds:.1f} s, {len(got)} and {len(want)} solutions")
    assert len(want) == 8
    assert same_solution_sets(got, want) == (True, "")
    # Every answer examples/squares.pl's comment documents for
    # `length(L, 9), filled_rectangle(A, L)`, its first two, in its order:
    # the only values here that come from neither port.
    documented = [
        (Fraction(33, 32), [Fraction(n, 32) for n in (15, 18, 8, 7, 4, 14, 1, 10, 9)]),
        (Fraction(69, 61), [Fraction(n, 61) for n in (33, 36, 28, 5, 2, 9, 25, 7, 16)]),
    ]
    for answer, (width, squares) in zip(got, documented):
        assert answer.bindings["A"] == width
        assert [answer.bindings[f"C{i}"] for i in range(1, 10)] == squares
