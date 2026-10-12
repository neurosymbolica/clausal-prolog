"""The design's Examples level (Task 16, Fable I1): the clp(q,r) example
programs under the port, against the oracle and the answers the examples
file documents.

The programs are read at test time from
``/workspace/claude_sicstus_clpq/test_examples_clpq.pl``, which inlines the
1.3.3 distribution's examples.  That file is outside ``library/clpq``, so
the licence acceptance for the 1.3.3 sources does not cover it: it is never
copied into this repository, and the tests skip where it is absent (as
test_acceptance.py does for filled_rectangle.pl).

What runs.  The file's own driver uses ``->`` and its matmul, root and
SEND+MORE checks use cuts, so Clausal (cut-free) cannot load it whole.  The
tests take the clauses of the cut-free example predicates by name: mg
(mortgage), monash_mg (the Monash mortgage), example/3 (simplex 1 to 9),
elim_example/2 and conv_hull/2 (eliminat), laplace/1 (symbolic 4 x 4 and
ground 11 x 11), fib/2, smm_p/8 (SEND+MORE=MONEY, without the file's cut:
``once/1`` takes the first answer) and opt_value/9 (option).  The query
predicates below are this test's own.  Not run: caneghem, the simplex
utility/electricity/water models, matmul, root, squares (test_acceptance.py
runs filled_rectangle), complex, invert, air, pictures, toolpath.

Two textual adaptations for Clausal, on the port's copy only (the oracle
reads the clauses as written):
- ``maximize(Z)`` / ``minimize(Z)`` (1.3.3's maximize/1) become
  ``maximize(Z, _)`` / ``minimize(Z, _)``: Clausal's surface has the /2
  form, which posts bv.pl's maximize/1 and binds the optimum
  (DEVIATIONS.md D20).
- ``<=`` inside braces becomes ``=<``: nf.pl's ``{<=(L, R)}`` is its
  ``{L =< R}``, but Clausal's .pl front end lowers only the seven
  comparisons in ``{}`` (clausal/tools/iso_l3.py ``_clpq_constraint``).

Each query is compared with the oracle (the local clpq.pl port of 1.3.3 on
Scryer: two ports of one source, not an independent check) answer by
answer, residuals by z3 equivalence, and with the values the examples
file documents, which come from neither port.
"""
import pathlib
import re
from fractions import Fraction

import pytest

from tests.clpq_oracle import clausal_answers, oracle_answers, same_solution_sets

PROGRAM = pathlib.Path("/workspace/claude_sicstus_clpq/test_examples_clpq.pl")

_PREDICATES = {
    "mg", "monash_mg", "allpos", "example", "elim_example", "conv_hull",
    "polytope", "positive_sum", "zero_list", "lin_comb", "lin_comb_r",
    "laplace", "laplace_vec", "fib", "smm_p", "smm_carry", "smm_dig",
    "smm_digit", "smm_difflist", "smm_notmem", "opt_h", "opt_r",
    "opt_value", "opt_check_param", "opt_get_sign", "opt_table",
}

_QUERIES = r"""
q_mortgage(MP, P, MP2, P2) :-
    mg(100000, 12, 1/100, 0, MP),
    mg(P, 12, 1/100, 0, MP),
    mg(Q, 120, 1/100, 0, MP2), {Q = 120000},
    mg(P2, 120, 1/100, 0, MP2).
q_monash_mortgage(MP) :- monash_mg(120000, 120, 1/100, 0, MP).
q_simplex(Z1, Z2, Z3, Z4, Z5, Z6, Z7, Z8, Z9, A1, B1, A3, B3) :-
    example(1, [A1, B1], Z1), example(2, _, Z2), example(3, [A3, B3], Z3),
    example(4, _, Z4), example(5, _, Z5), example(6, _, Z6),
    example(7, _, Z7), example(8, _, Z8), example(9, _, Z9).
q_eliminat(A1, A2, A3, A4, B0, B1, B2, B3, B4, C1, C2, C3, C4,
           D1, D2, D3, E1, E2) :-
    elim_example(1, [A1, A2, A3, A4]),
    elim_example(2, [B0, B1, B2, B3, B4]),
    elim_example(3, [C1, C2, C3, C4]),
    conv_hull([[1,0,0],[0,1,0],[0,0,1]], [D1, D2, D3]),
    conv_hull([[1,1],[2,0],[3,0],[1,2],[2,2]], [E1, E2]).
q_laplace_symbolic(B12, B13, B21, B24, B31, B34, B42, B43,
                   M22, M23, M32, M33) :-
    laplace([[B11,B12,B13,B14],[B21,M22,M23,B24],
             [B31,M32,M33,B34],[B44,B42,B43,B44]]).
q_laplace_ground(Center) :-
    X = [[0,0,0,0,0,0,0,0,0,0,0],
         [100,_,_,_,_,_,_,_,_,_,100], [100,_,_,_,_,_,_,_,_,_,100],
         [100,_,_,_,_,_,_,_,_,_,100], [100,_,_,_,_,_,_,_,_,_,100],
         [100,_,_,_,_,_,_,_,_,_,100], [100,_,_,_,_,_,_,_,_,_,100],
         [100,_,_,_,_,_,_,_,_,_,100], [100,_,_,_,_,_,_,_,_,_,100],
         [100,_,_,_,_,_,_,_,_,_,100],
         [100,100,100,100,100,100,100,100,100,100,100]],
    laplace(X),
    X = [_,_,_,_,_,[100,_,_,_,_,Center|_]|_].
q_fib(Z, Y) :- fib(10, Z), once(fib(Y, 89)).
q_smm(S, E, N, D, M, O, R, Y) :- once(smm_p(S, E, N, D, M, O, R, Y)).
q_option_go1(Value) :- opt_value(call, sell, 60, 5, _, 1/20, 50, _, Value).
q_option_go5(none) :-
    \+ ( {Put = 5, Exercise = 20, Interest = 1/10, S >= 0, W > 100},
         opt_value(put, buy, S, _, Put, Interest, Exercise, _, W) ).
"""

_HEAD = ":- use_module(library(clpq)).\n:- op(700, xfx, <=).\n"


def _clauses(text):
    """The clauses of _PREDICATES, as written: a clause starts at column 0
    and ends at a line ending in a full stop."""
    kept, current, keep = [], [], False
    for line in text.splitlines():
        if not current:
            match = re.match(r"([a-z][A-Za-z0-9_]*)", line)
            if not match:
                continue
            keep = match.group(1) in _PREDICATES
        current.append(line)
        if line.rstrip().endswith("."):
            if keep:
                kept.extend(current)
            current = []
    return "\n".join(kept) + "\n"


def _programs():
    if not PROGRAM.exists():
        pytest.skip(f"needs {PROGRAM}")
    clauses = _clauses(PROGRAM.read_text())
    assert "!" not in clauses and "->" not in clauses
    port = re.sub(r"\b(maximize|minimize)\((\w+)\)", r"\1(\2, _)", clauses)
    port = re.sub(r"(?<![=<>])<=", "=<", port)
    return (_HEAD + port + _QUERIES,
            ":- use_module(library(lists)).\n" + _HEAD + clauses + _QUERIES)


def _both(name, variables):
    port_program, oracle_program = _programs()
    goal = f"{name}({', '.join(variables)})"
    port = clausal_answers(port_program, goal, variables, "holzbaur")
    oracle = oracle_answers(oracle_program, goal, variables, timeout=120)
    assert same_solution_sets(port, oracle) == (True, ""), (port, oracle)
    return port


def test_the_cut_free_subset_is_found():
    port_program, _ = _programs()
    for name in ("mg", "monash_mg", "example", "elim_example", "laplace",
                 "fib", "smm_p", "opt_value"):
        assert re.search(rf"^{name}\(", port_program, re.M), name


def test_mortgage():
    [answer] = _both("q_mortgage", ["MP", "P", "MP2", "P2"])
    bindings = answer.bindings
    assert 0 < bindings["MP"] < 100000          # test_mg_forward
    assert bindings["P"] == 100000              # test_mg_backward
    assert bindings["MP2"] > 0 and bindings["P2"] == 120000


def test_monash_mortgage():
    [answer] = _both("q_monash_mortgage", ["MP"])
    assert 1721 < answer.bindings["MP"] < 1722  # test_mortgage_forward


def test_simplex_1_to_9():
    variables = [f"Z{i}" for i in range(1, 10)] + ["A1", "B1", "A3", "B3"]
    [answer] = _both("q_simplex", variables)
    documented = [17200, 7, 18850, 310, 5, -7, -70, Fraction(-39, 2),
                  Fraction(11429082625, 9792)]
    assert [answer.bindings[f"Z{i}"] for i in range(1, 10)] == documented
    assert [answer.bindings[v] for v in ("A1", "B1", "A3", "B3")] == \
        [40, 160, 38, 170]


def test_eliminat():
    # The projections: the file checks only that each holds; the residuals
    # are compared with the oracle's.
    variables = ["A1", "A2", "A3", "A4", "B0", "B1", "B2", "B3", "B4",
                 "C1", "C2", "C3", "C4", "D1", "D2", "D3", "E1", "E2"]
    [answer] = _both("q_eliminat", variables)
    assert answer.residual


def test_laplace():
    # The four inner points in terms of the eight boundary points the
    # stencil reads (the file only checks that it holds).
    [symbolic] = _both("q_laplace_symbolic",
                       ["B12", "B13", "B21", "B24", "B31", "B34", "B42",
                        "B43", "M22", "M23", "M32", "M33"])
    assert len(symbolic.residual) + len(symbolic.bindings) >= 4
    [ground] = _both("q_laplace_ground", ["Center"])
    assert ground.bindings["Center"] == 75      # test_laplace_ground


def test_fib():
    [answer] = _both("q_fib", ["Z", "Y"])
    assert (answer.bindings["Z"], answer.bindings["Y"]) == (89, 10)


def test_send_more_money():
    variables = ["S", "E", "N", "D", "M", "O", "R", "Y"]
    [answer] = _both("q_smm", variables)
    assert [answer.bindings[v] for v in variables] == [9, 5, 6, 7, 1, 0, 8, 2]


def test_option():
    [answer] = _both("q_option_go1", ["Value"])
    assert answer.bindings["Value"] == Fraction(-19, 4)
    assert len(_both("q_option_go5", ["X"])) == 1   # no solution for W > 100
