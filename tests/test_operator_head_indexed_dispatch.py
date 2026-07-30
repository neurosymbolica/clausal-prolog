"""An operator-node head argument must match the same under argument indexing.

A structural head argument (``Kind(A + B, plus_)``) is hoisted at assert time
into a body ``Unify`` (``clausal.logic.database._normalize_structural_head_args``),
where runtime ``unify`` — i.e. ``BinOp.__unify__`` — decides the match and
correctly ignores the non-semantic ``position`` field.

Once the predicate crosses ``_INDEX_THRESHOLD`` clauses, ``_lift_clause_at_pos``
(Phase 8) lifts that ``Unify`` back into the head so ``head_to_match_pattern``
can emit a pattern instead of a runtime unify.  The pattern must test exactly
the fields unification tests: an operator node's ``position`` tuple is
``compare=False`` cosmetic metadata, so a head pattern that tests it makes the
indexed path disagree with the unindexed one.

Two symptoms of testing it, both covered here:

* the position tuple is a ground non-primitive, so it is classified as an
  *opaque head literal* and compiled to a ``$headlit_<id>`` capture+unify
  guard.  The globals collector only injects those keys for terms it finds in
  the *pre-lift* head, so the name is never defined and the compiled bucket
  raises ``NameError: name '$headlit_<id>' is not defined`` per goal, at
  runtime (this is what broke 6/10 self-tests of the shipped
  ``clausal/examples/symbolic_diff.clausal``);
* were the name injected, the pattern would compare the clause's source
  position against the caller's — silently zero solutions.
"""

import ast
import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.compiler.head_match import head_to_match_pattern
from clausal.logic.solve import solve, _query_cache
from clausal.logic.variables import Var, deref
from clausal.pythonic_ast.nodes import Add, Mult


EXAMPLES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "clausal", "examples",
)

# Four clauses is _INDEX_THRESHOLD, so Kind/2 is compiled with argument-index
# buckets and the operator head args are lifted back into the bucket heads.
# Deliberately unlike symbolic_diff: no recursion, no arithmetic evaluation,
# no numeric literals in any head.
INDEXED_SRC = """\
-module(opidx, [Kind(TERM, NAME), Chk(N)])
-private([p, q, plus_, minus_, times_, other_])

Kind(A + B, plus_) <- (number(1))
Kind(A - B, minus_) <- (number(1))
Kind(A * B, times_) <- (number(1))
Kind(9, other_) <- (number(1))

Chk(N) <- Kind(p + q, N)
"""

# The same predicate one clause below the indexing threshold: this is the
# control, it always worked, and the indexed version must agree with it.
UNINDEXED_SRC = """\
-module(opnoidx, [Kind(TERM, NAME), Chk(N)])
-private([p, q, plus_, minus_, other_])

Kind(A + B, plus_) <- (number(1))
Kind(A - B, minus_) <- (number(1))
Kind(9, other_) <- (number(1))

Chk(N) <- Kind(p + q, N)
"""


@pytest.fixture(autouse=True)
def _clear_query_cache():
    _query_cache.clear()
    yield
    _query_cache.clear()


@pytest.fixture(scope="module")
def indexed(tmp_path_factory):
    d = tmp_path_factory.mktemp("opidx")
    p = d / "opidx.clausal"
    p.write_text(INDEXED_SRC)
    return _load_module("opidx_mod", str(p))


@pytest.fixture(scope="module")
def unindexed(tmp_path_factory):
    d = tmp_path_factory.mktemp("opnoidx")
    p = d / "opnoidx.clausal"
    p.write_text(UNINDEXED_SRC)
    return _load_module("opnoidx_mod", str(p))


class TestOperatorHeadUnderArgIndexing:
    def test_indexed_operator_head_matches(self, indexed):
        """The bug: raises NameError '$headlit_<id>' instead of matching."""
        n = Var()
        got = [str(deref(n)) for _ in solve(indexed.Chk(n))]
        assert got == ["plus_"]

    def test_indexed_agrees_with_unindexed(self, indexed, unindexed):
        a, b = Var(), Var()
        got_idx = [str(deref(a)) for _ in solve(indexed.Chk(a))]
        got_plain = [str(deref(b)) for _ in solve(unindexed.Chk(b))]
        assert got_idx == got_plain

    def test_distinct_operators_still_discriminate(self, indexed):
        """Guard against an over-broad fix: a * b must not match the + clause."""
        n = Var()
        goal = indexed.Kind(Mult(left=indexed.p, right=indexed.q), n)
        got = [str(deref(n)) for _ in solve(goal)]
        assert got == ["times_"]

    def test_non_operator_clause_unaffected(self, indexed):
        n = Var()
        got = [str(deref(n)) for _ in solve(indexed.Kind(9, n))]
        assert got == ["other_"]


class TestHeadPatternIgnoresNonSemanticFields:
    """Pin the mechanism, not just the symptom."""

    def test_position_is_not_matched_and_mints_no_headlit(self):
        node = Add(left=Var(), right=Var())
        node.position = (1, 2, 3, 4)
        list_guards: list[tuple] = []
        pat = head_to_match_pattern(node, {}, [], list_guards)
        assert isinstance(pat, ast.MatchClass)
        assert "position" not in pat.kwd_attrs
        assert list(pat.kwd_attrs) == ["left", "right"]
        assert not [g for g in list_guards if g and g[0] == "headlit"], (
            "the cosmetic position tuple must not become an opaque head literal"
        )


class TestSymbolicDiffExampleEndToEnd:
    def test_all_self_tests_pass(self):
        from clausal.testing import run_file

        results = run_file(os.path.join(EXAMPLES_DIR, "symbolic_diff.clausal"))
        failed = [(r.name, str(r.error)) for r in results.results if not r.passed]
        assert failed == []
        assert len(results.results) == 10
