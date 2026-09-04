"""Phase 2 bridge, Task 3 -- the parity corpus.

Spec: ``docs/superpowers/plans/2026-09-03-phase2-bridge.md`` Task 3; design:
``implementation_plans/tagged-tuple-term-representation.md``.

Task 2 (``tests/test_tagged_terms.py``) proved the cell representation's
MECHANISM correct on one fixture pair (``tagged_shapes`` / ``tagged_shapes_
tagged``).  This module is the wider CORPUS: three fixture pairs chosen to
span the categories the brief calls out --

======================================  =================================================
category                                fixture pair
======================================  =================================================
recursion + compound answers            ``struct_tabling`` / ``struct_tabling_tagged``
                                         (also Task 4's interning fixture)
multi-clause dispatch on compound       ``tagged_shapes`` / ``tagged_shapes_tagged``
heads, atoms as values                  (Task 2's own fixture -- REUSED per the task
                                         brief's "reuse/extend rather than reinvent";
                                         the query set below is additional to, not a
                                         copy of, Task 2's ``TestParity``)
list/tuple data mixing                  ``head_list_compound`` /
                                         ``head_list_compound_tagged`` (declared
                                         compound functors nested INSIDE list literals)
======================================  =================================================

Every comparison goes through ``tests.tagged_terms_support.normalize_term``
(or ``normalize_answers``), which canonicalises a cell ``("f", a, b)`` and a
class term ``f(A=a, B=b)`` to the same tuple -- so an assertion here is about
the TERM two representations produced, not about which representation
produced it.  Per each fixture pair there is also one MUST-FAIL query,
asserted to fail on both halves (parity of failure is as load-bearing as
parity of success -- a corpus that only agreed on the happy path would be
unsound).

WHAT THE PAIRS MEAN AFTER THE FLIP (P3-2 Task 2).  ``-tagged_terms`` is
deleted and cells are unconditional, so the two halves of each pair are now
the same program under two module names and compile identically.  The pair
is KEPT, and this module keeps running, because the EXPECTED VALUES here
were recorded while the plain half still used the class representation:
they are the old-golden-vs-new-default anchor for the flip.  A cell-era
answer that differs from what the class era produced fails here, which is
exactly the regression this file exists to catch.

The two halves are still queried through independent module universes
(``importlib.import_module`` of the plain and the ``_tagged`` dotted names),
and still never by handing one half's class instance to the other -- per
Task 2's pinned finding that a declared functor's still-minted class
constructor matches nothing in its own module's clauses.
"""

from __future__ import annotations

import importlib
import os
import time

import pytest

from clausal.logic.cells import is_cell, cell_args
from clausal.logic.variables import Var, deref
from clausal.logic.solve import call

from tests.tagged_terms_support import normalize_term


def _fixture(module_name: str):
    return importlib.import_module(module_name)


def _logic_module(mod):
    return mod.__dict__["$module"]


def _answers(module_name, goal, build_args, out_positions):
    """Run *goal* against *module_name* and return normalised out-args.

    ``build_args`` receives the loaded module (so callers can reach the
    module's own atom/functor classes for the class-term half) and returns
    the full positional argument tuple. ``out_positions`` selects which of
    those arguments to collect and normalise per solution.
    """
    mod = _fixture(module_name)
    args = build_args(mod)
    out = []
    for _trail in call(goal, *args, module=_logic_module(mod)):
        out.append(tuple(normalize_term(args[i]) for i in out_positions))
    return out


# ── struct_tabling / struct_tabling_tagged ──────────────────────────────────
#
# Recursion + compound answers: Nats/2 is TABLED and builds an O(K)-deep
# cons/nil chain -- this is also the fixture Task 4's interning measurement
# depends on, so its tagged half must already answer correctly (without
# interning) before that stage begins.

_ST_PLAIN = "tests.fixtures.struct_tabling"
_ST_TAGGED = "tests.fixtures.struct_tabling_tagged"


class TestStructTablingParity:
    @pytest.mark.parametrize("n", [0, 1, 3, 8])
    def test_nats_builds_the_same_chain(self, n):
        def build(mod):
            return (n, Var())

        plain = _answers(_ST_PLAIN, "Nats", build, [1])
        tagged = _answers(_ST_TAGGED, "Nats", build, [1])
        assert plain == tagged
        assert len(plain) == 1

    def test_nats_chain_shape_is_canonical(self):
        """Nats(3, L) => cons(3, cons(2, cons(1, nil))) in both halves.

        P3-1 atom pivot (§1b): the chain's tail ``nil`` is the interned str
        "nil" in both halves, not a wrapped ("nil",) atom-class shape --
        see phase3-decomposition-and-p31-atom-pivot.md Task 7 work item 1.
        """
        def build(mod):
            return (3, Var())

        expected = ("cons", 3, ("cons", 2, ("cons", 1, "nil")))
        plain = _answers(_ST_PLAIN, "Nats", build, [1])
        tagged = _answers(_ST_TAGGED, "Nats", build, [1])
        assert plain == [(expected,)]
        assert tagged == [(expected,)]

    def test_nats_open_query_is_deterministic_both_halves(self):
        """Nats/2 has exactly one answer per N -- an open query drained to
        exhaustion must yield exactly one solution on both halves."""
        for module_name in (_ST_PLAIN, _ST_TAGGED):
            mod = _fixture(module_name)
            L = Var()
            results = list(call("Nats", 4, L, module=_logic_module(mod)))
            assert len(results) == 1, module_name

    def test_nats_ground_query_success_parity(self):
        """A caller-supplied, already-built matching chain succeeds on both
        halves.

        P3-2 Task 2 (THE FLIP, R6): the plain half's chain is a CELL chain
        now.  It used to be built from that module's ``cons`` class, because
        that is what its clauses built; post-flip both modules build cells,
        and the class constructor (still minted by the ``-module`` rewrite)
        would match nothing -- see ``test_tagged_terms.py``'s
        ``test_a_declared_data_functors_class_constructor_matches_nothing``.
        """
        plain_mod = _fixture(_ST_PLAIN)
        chain = ("cons", 3, ("cons", 2, ("cons", 1, plain_mod.nil)))
        assert len(list(call("Nats", 3, chain, module=_logic_module(plain_mod)))) == 1

        tagged_mod = _fixture(_ST_TAGGED)
        cell_chain = ("cons", 3, ("cons", 2, ("cons", 1, tagged_mod.nil)))
        assert len(list(call("Nats", 3, cell_chain, module=_logic_module(tagged_mod)))) == 1

    def test_nats_ground_query_failure_parity(self):
        """A caller-supplied chain with the wrong head value fails on both."""
        plain_mod = _fixture(_ST_PLAIN)
        # R6: a cell chain on this half too -- see the success twin above.
        bad_chain = ("cons", 99, ("cons", 2, ("cons", 1, plain_mod.nil)))
        assert list(call("Nats", 3, bad_chain, module=_logic_module(plain_mod))) == []

        tagged_mod = _fixture(_ST_TAGGED)
        bad_cell_chain = ("cons", 99, ("cons", 2, ("cons", 1, tagged_mod.nil)))
        assert list(call("Nats", 3, bad_cell_chain, module=_logic_module(tagged_mod))) == []

    def test_must_fail_negative_n_fails_both_halves(self):
        """Neither clause head matches a negative N: Nats(0, nil) needs N=0,
        the recursive clause's ``N > 0`` guard rejects it too."""
        def build(mod):
            return (-1, Var())

        assert _answers(_ST_PLAIN, "Nats", build, [1]) == []
        assert _answers(_ST_TAGGED, "Nats", build, [1]) == []


# ── tagged_shapes / tagged_shapes_tagged (reused fixture) ───────────────────
#
# Multi-clause dispatch on compound heads (point/2, circle/2, seg/3 separate
# by functor and by arity) + atoms as values (nil, and the num/str arms).
# This pair already exists from Task 2; the query set below is additional
# corpus coverage, not a repeat of Task 2's own TestParity/TestCellHeadDispatch.

_TS_PLAIN = "tests.fixtures.tagged_shapes"
_TS_TAGGED = "tests.fixtures.tagged_shapes_tagged"


class TestTaggedShapesParity:
    def test_mk_then_depth_round_trip_multiple_n(self):
        for n in (0, 2, 6):
            for module_name in (_TS_PLAIN, _TS_TAGGED):
                mod = _fixture(module_name)
                lm = _logic_module(mod)
                T, D = Var(), Var()
                got = []
                for _t in call("mk", n, T, module=lm):
                    for _t2 in call("depth", T, D, module=lm):
                        got.append(deref(D))
                    break
                assert got == [n], (module_name, n)

    def test_pair_up_then_kind_composition(self):
        """Build a seg/3 via pair_up, then classify it via kind/2 -- chains
        two predicates' cell traffic through one query, both halves."""
        for module_name in (_TS_PLAIN, _TS_TAGGED):
            mod = _fixture(module_name)
            lm = _logic_module(mod)
            P, K = Var(), Var()
            got = []
            for _t in call("pair_up", 1, 2, P, module=lm):
                for _t2 in call("kind", P, K, module=lm):
                    got.append(deref(K))
            assert got == ["seg3"], module_name

    def test_open_kind_query_answer_set_parity(self):
        def build(mod):
            return (Var(), Var())

        plain = _answers(_TS_PLAIN, "kind", build, [1])
        tagged = _answers(_TS_TAGGED, "kind", build, [1])
        assert plain == tagged
        assert len(plain) == 6  # pt, circ, seg3, empty, num, str

    def test_must_fail_seg_with_wrong_arity_fails_both_halves(self):
        """kind/2 has no clause for seg/2 (only seg/3): each module's own
        3-field seg constructor called with 2 args must raise -- not the
        query itself -- so the must-fail probe is a wrong-arity cell/term
        passed as already-built data instead."""
        K = Var()
        # A 2-arg "seg" shape has no clause on either side (seg/2 is not
        # declared -- only seg/3 is): a plain data tuple expresses that
        # shape identically for both halves.
        plain_mod = _fixture(_TS_PLAIN)
        assert list(call("kind", (1, 2), K, module=_logic_module(plain_mod))) == []

        tagged_mod = _fixture(_TS_TAGGED)
        assert list(call("kind", ("seg", 1, 2), K, module=_logic_module(tagged_mod))) == []


# ── head_list_compound / head_list_compound_tagged ──────────────────────────
#
# List/tuple data mixing: item2/1, pair/2, c/1, d/1 are declared compound
# functors nested INSIDE list literals, in both head and body position.
# Every clause here is a Test/1 fact rather than an open predicate, so parity
# is checked by running the fixture's own Test suite through both halves and
# comparing which descriptions succeed.

_HLC_PLAIN = "tests.fixtures.head_list_compound"
_HLC_TAGGED = "tests.fixtures.head_list_compound_tagged"


def _passing_test_descriptions(module_name):
    from clausal.testing import collect_tests, run_test

    mod = _fixture(module_name)
    names = collect_tests(mod)
    passed = []
    for name in names:
        result = run_test(mod, name)
        if result.passed:
            passed.append(name)
    return names, passed


class TestHeadListCompoundParity:
    def test_same_tests_pass_both_halves(self):
        plain_names, plain_passed = _passing_test_descriptions(_HLC_PLAIN)
        tagged_names, tagged_passed = _passing_test_descriptions(_HLC_TAGGED)
        assert plain_names == tagged_names
        assert plain_passed == tagged_passed
        # Every Test/1 clause in this fixture is written to pass (it is a
        # regression corpus, not an error-path corpus) -- confirm the parity
        # isn't a vacuous "both empty".
        assert plain_passed == plain_names

    def test_ev_deep_output_mode_answer_parity(self):
        """The output-mode query (S left open) -- not just the boolean
        Test/1 wrapper -- answers the same value both halves.

        ev_deep/1's single arg is [c(d(S))] -- a LIST containing a nested
        compound, built as the cell literals ``("c", ("d", S))``: the same
        shape the fixture's own Test/1 clauses exercise, queried directly
        here (S open) so the assertion is on the *answer*, not just the
        pass/fail Test/1 wrapper above.

        P3-2 Task 2 (THE FLIP, R6): the plain half used to build that list
        through its ``c``/``d`` CLASSES.  Both halves compile to cells now,
        so both are queried with cells; the recorded answer ("met") is
        unchanged from the class era, which is the point of keeping this
        test.
        """
        for module_name in (_HLC_PLAIN, _HLC_TAGGED):
            mod = _fixture(module_name)
            lm = _logic_module(mod)
            S = Var()
            got = [
                normalize_term(S)
                for _t in call("ev_deep", [("c", ("d", S))], module=lm)
            ]
            assert got == ["met"], module_name

    def test_must_fail_ev_deep_input_mismatch_fails_both_halves(self):
        for module_name in (_HLC_PLAIN, _HLC_TAGGED):
            mod = _fixture(module_name)
            lm = _logic_module(mod)
            # R6: cells on both halves -- see the success twin above.
            arg = [("c", ("d", "no"))]
            assert list(call("ev_deep", arg, module=lm)) == [], module_name


# ── Timing spot-check ────────────────────────────────────────────────────────
#
# One fixture, both halves, same protocol as benchmarks/workloads.py::
# bench_struct_tabling (fresh module reload per rep, so tabling's per-answer
# freeze/copy work is measured every time rather than hitting the COMPLETE
# fast path after the first rep). n is kept small relative to the benchmark's
# ~1500 target -- this is a smoke-level "same order of magnitude" check that
# must run fast inside the normal suite, not a measurement (Task 4 owns the
# real one). A cliff is REPORTABLE, not a hard failure: the assertion below
# allows a generous margin so ordinary CI jitter cannot flip it, and the
# report records the raw ratio either way.

_TIMING_N = int(os.environ.get("CLAUSAL_PARITY_TIMING_N", "300"))
_TIMING_REPS = 3


def _time_struct_tabling(fixture_path, n=_TIMING_N, reps=_TIMING_REPS):
    from clausal.testing import load_clausal_module

    start = time.perf_counter()
    for _ in range(reps):
        mod = load_clausal_module(fixture_path)
        lm = mod.__dict__["$module"]
        nil = mod.nil
        L = Var()
        for _t in call("Nats", n, L, module=lm):
            node = deref(L)
            length = 0
            while node is not nil:
                if is_cell(node):
                    node = deref(cell_args(node)[1])
                else:
                    node = deref(node.T)
                length += 1
            assert length == n
            break
    return time.perf_counter() - start


class TestTimingSpotCheck:
    def test_struct_tabling_tagged_is_same_order_of_magnitude(self):
        here = os.path.dirname(__file__)
        plain_path = os.path.join(here, "fixtures", "struct_tabling.clausal")
        tagged_path = os.path.join(here, "fixtures", "struct_tabling_tagged.clausal")

        plain_t = _time_struct_tabling(plain_path)
        tagged_t = _time_struct_tabling(tagged_path)

        ratio = tagged_t / plain_t if plain_t > 0 else float("inf")
        # Generous bound: cell dispatch is UNINDEXED this stage (all-clauses
        # fallback per the plan's binding constraint), so some slowdown is
        # expected and acceptable -- a genuine order-of-magnitude CLIFF
        # (~10x+) is what this guards against, not any slowdown at all.
        assert ratio < 20, (
            f"struct_tabling_tagged took {ratio:.2f}x struct_tabling "
            f"(plain={plain_t:.4f}s tagged={tagged_t:.4f}s, n={_TIMING_N}, "
            f"reps={_TIMING_REPS}) -- report this as a timing cliff finding, "
            f"not a silent pass."
        )
