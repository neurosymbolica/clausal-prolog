"""An operator-node head argument must match the same under argument indexing.

A structural head argument (``kind(A + B, plus_)``) is hoisted at assert time
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

from clausal.logic.atoms import mint
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
-module(opidx, [kind(TERM, NAME), chk(N)])
-private([p, q, plus_, minus_, times_, other_])

kind(A + B, plus_) <- (number(1))
kind(A - B, minus_) <- (number(1))
kind(A * B, times_) <- (number(1))
kind(9, other_) <- (number(1))

chk(N) <- kind(p + q, N)
"""

# The same predicate one clause below the indexing threshold: this is the
# control, it always worked, and the indexed version must agree with it.
UNINDEXED_SRC = """\
-module(opnoidx, [kind(TERM, NAME), chk(N)])
-private([p, q, plus_, minus_, other_])

kind(A + B, plus_) <- (number(1))
kind(A - B, minus_) <- (number(1))
kind(9, other_) <- (number(1))

chk(N) <- kind(p + q, N)
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
        got = [deref(n) for _ in solve(indexed.chk(n), indexed)]
        assert got == [mint("plus_")]

    def test_indexed_agrees_with_unindexed(self, indexed, unindexed):
        a, b = Var(), Var()
        got_idx = [deref(a) for _ in solve(indexed.chk(a), indexed)]
        got_plain = [deref(b) for _ in solve(unindexed.chk(b), unindexed)]
        assert got_idx == got_plain

    def test_distinct_operators_still_discriminate(self, indexed):
        """Guard against an over-broad fix: a * b must not match the + clause."""
        n = Var()
        goal = indexed.kind(Mult(left=indexed.p, right=indexed.q), n)
        got = [deref(n) for _ in solve(goal, indexed)]
        assert got == [mint("times_")]

    def test_non_operator_clause_unaffected(self, indexed):
        n = Var()
        got = [deref(n) for _ in solve(indexed.kind(9, n), indexed)]
        assert got == [mint("other_")]


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


# ── the invariant the field filter rests on ──────────────────────────────────


def test_no_term_type_hides_a_semantic_field_behind_compare_false():
    """``compare=False`` must stay a synonym for "cosmetic metadata".

    ``_matched_field_names`` drops ``compare=False`` fields from a head pattern
    because runtime ``unify`` ignores them -- the custom ``__unify__`` methods
    consult only comparable fields, and everything else falls back to the
    dataclass ``==``, which is derived from them.  That equivalence is what
    keeps the argument-indexed head-match path agreeing with the hoisted
    ``Unify`` path.

    It is an invariant, not a mechanism: a term type that shipped a
    ``compare=False`` field its own ``__unify__`` *did* consult would be
    silently dropped from the pattern, and the indexed path would then
    over-match relative to ``unify`` -- wrong solutions, no error.  There are
    ten ``__unify__`` implementations, so a comment on each would rot; this
    fails instead, and points here.

    If you are adding a genuinely cosmetic field, add its name below.  If you
    are adding a semantic one, do not make it ``compare=False``.
    """
    import dataclasses

    import clausal.pythonic_ast.nodes as nodes
    import clausal.terms as terms

    cosmetic = {"position", "_position"}
    offenders = {}
    for module in (terms, nodes):
        for cls_name, obj in vars(module).items():
            if not (isinstance(obj, type) and dataclasses.is_dataclass(obj)):
                continue
            for field in dataclasses.fields(obj):
                if not field.compare and field.name not in cosmetic:
                    offenders.setdefault(field.name, []).append(
                        f"{module.__name__}.{cls_name}")

    assert offenders == {}, (
        "a term type carries a compare=False field that is not known-cosmetic; "
        "if unify consults it, head_match._matched_field_names will drop it "
        f"from the head pattern and the indexed path will over-match: {offenders}"
    )
