"""Regression: a trailing comma after a ``<-`` rule must not crash at load.

``head <- (body)`` parses in Python as ``Compare(head < -body)``.  A trailing
comma wraps that in a one-element ``Tuple``.  The EmbedTransformer used to only
recognise trailing-comma *facts* (``Tuple([Call])``), so a trailing-comma
*rule* (``Tuple([Compare])``) fell through to plain term rewriting and emitted
references to never-bound head variables, raising ``NameError`` at module-exec
time.

Originally reported (todo/multi-clause-compound-head-nameerror.md) as a
compound-term list-head problem, but that was a red herring: the real trigger
is the trailing comma, independent of head shape.  Proof by isolation:
compound heads with newline separators load fine, while bare ``[H, *T]`` heads
with commas between rules fail — so the head shape is irrelevant.
"""

import os

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call


def _load(tmp_path, source: str, name: str):
    path = os.path.join(str(tmp_path), f"{name}.clausal")
    with open(path, "w") as f:
        f.write(source)
    return _load_module(name, path)


def _module(mod):
    return mod.__dict__["$module"]


def test_bare_var_heads_with_commas_between_rules(tmp_path):
    """Two bare ``[H, *T]`` rules separated by commas load and run."""
    src = (
        "-module(csr_bare, [ q(XS, N) ])\n"
        "q([], 0),\n"
        "q([H, *T], N) <- (q(T, M), N == H + M),\n"
        "q([H, *T], N) <- (q(T, N))\n"
    )
    mod = _load(tmp_path, src, "csr_bare")
    logic_mod = _module(mod)
    sols = list(call("q", [1, 2, 3], 6, module=logic_mod))
    assert len(sols) >= 1


def test_compound_list_heads_with_commas_between_rules(tmp_path):
    """The originally-reported shape: 2+ ``[pair(A,B), *T]`` clauses w/ commas."""
    src = (
        "-module(csr_compound, [ pair(A, B), q(XS, N) ])\n"
        "q([], 0),\n"
        "q([pair(A, B), *T], N) <- (A == 1, q(T, M), N == B + M),\n"
        "q([pair(A, B), *T], N) <- (not (A == 1), q(T, N))\n"
    )
    mod = _load(tmp_path, src, "csr_compound")
    logic_mod = _module(mod)
    # P3-2 Task 2 (THE FLIP, R6): ``pair`` is a data functor -- the caller
    # hands in the cells the clause heads match.
    assert mod.__dict__["pair"] == mint("pair")
    # pairs with A==1 contribute B; A!=1 contribute 0.
    # [pair(1,10), pair(0,99), pair(1,5)] -> 10 + 5 = 15
    lst = [("pair", 1, 10), ("pair", 0, 99), ("pair", 1, 5)]
    sols = list(call("q", lst, 15, module=logic_mod))
    assert len(sols) >= 1


def test_trailing_comma_on_final_rule(tmp_path):
    """A trailing comma even on the last rule should be tolerated."""
    src = (
        "-module(csr_trailing, [ q(XS, N) ])\n"
        "q([], 0),\n"
        "q([H, *T], N) <- (q(T, M), N == H + M),\n"
    )
    mod = _load(tmp_path, src, "csr_trailing")
    logic_mod = _module(mod)
    sols = list(call("q", [4, 5], 9, module=logic_mod))
    assert len(sols) >= 1
