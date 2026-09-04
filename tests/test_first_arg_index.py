"""Tests for V2-1: First-argument indexing.

Verifies that compile_predicate and compile_predicate_trampoline use
first-argument indexing when there are enough clauses, and that the
indexed dispatch produces the same results as unindexed dispatch.
"""

import pytest

from clausal.logic.database import Clause, Database
from clausal.logic.compiler import (
    compile_predicate_trampoline as compile_predicate,
    compile_predicate_trampoline,
)
from clausal.logic.compiler.arg_index import (
    _extract_first_arg_key,
    _build_first_arg_index,
    _INDEX_VAR,
    _INDEX_THRESHOLD,
)
from clausal.logic.predicate import PredicateMeta, make_atom
from clausal.logic.variables import Var, Trail, deref, unify
from clausal.logic.trampoline import StepGenerator, solutions, DONE
from clausal.terms import Compound, Unify
from clausal.logic.builtins import _normalize_fact_clause


# ── Helpers ──────────────────────────────────────────────────────────────────


def _simple_solutions(dispatch, args, trail=None):
    """Collect all solutions from a trampoline-mode dispatch function.

    (Legacy name kept for minimal test churn; now drives trampoline protocol.)
    """
    return _trampoline_solutions(dispatch, args, trail)


def _trampoline_solutions(dispatch, args, trail=None):
    """Collect all solutions from a trampoline-mode dispatch function."""
    if trail is None:
        trail = Trail()
    sg = StepGenerator(dispatch, None, None, None, *args, trail)
    return solutions(sg, lambda: tuple(deref(a) for a in args))


# ── Test _extract_first_arg_key ──────────────────────────────────────────────


class TestExtractFirstArgKey:
    def test_compound_literal(self):
        # nv
        c = Clause(head=Compound("f", (42,)), body=[True])
        assert _extract_first_arg_key(c, 1) == 42

    def test_compound_string(self):
        # nv
        c = Clause(head=Compound("f", ("hello", 1)), body=[True])
        assert _extract_first_arg_key(c, 2) == "hello"

    def test_compound_var(self):
        # nv
        v = Var()
        c = Clause(head=Compound("f", (v, 1)), body=[True])
        assert _extract_first_arg_key(c, 2) is _INDEX_VAR

    def test_compound_var_with_unify(self):
        """Var + Unify pattern from _normalize_dataclass_fact."""
        # nv
        v = Var()
        c = Clause(head=Compound("f", (v, Var())), body=[Unify(left=v, right=99)])
        assert _extract_first_arg_key(c, 2) == 99

    def test_compound_var_with_unify_reversed(self):
        """Unify with reversed left/right."""
        # nv
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left="abc", right=v)])
        assert _extract_first_arg_key(c, 1) == "abc"

    def test_zero_arity(self):
        # nv
        c = Clause(head=Compound("f", ()), body=[True])
        assert _extract_first_arg_key(c, 0) is _INDEX_VAR

    def test_predicate_meta_head(self):
        # nv
        class color(metaclass=PredicateMeta):
            _fields = ("name", "code")

        v = Var()
        head = color(name=v, code=Var())
        c = Clause(head=head, body=[Unify(left=v, right="red")])
        assert _extract_first_arg_key(c, 2) == "red"

    def test_non_indexable_first_arg(self):
        """Term instances are not indexed; int-lists are now bytes-indexed (Task 11)."""
        # nv — [1, 2] is a valid codes list: canonicalises to b'\x01\x02'
        c = Clause(head=Compound("f", ([1, 2], "x")), body=[True])
        assert _extract_first_arg_key(c, 2) == b'\x01\x02'

    def test_bool_key(self):
        # nv
        c = Clause(head=Compound("f", (True,)), body=[True])
        assert _extract_first_arg_key(c, 1) is True

    def test_none_key(self):
        """None is indexable — extracted from Var+Unify pattern."""
        # nv
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=v, right=None)])
        assert _extract_first_arg_key(c, 1) is None

    def test_none_key_direct(self):
        """None directly in Compound head is also indexable."""
        # nv
        c = Clause(head=Compound("f", (None,)), body=[True])
        assert _extract_first_arg_key(c, 1) is None

    def test_atom_reference_key_from_unify(self):
        """A keyword-atom fact (``Color(C=Red)``) compiles to a Var head with a
        ``Unify(field_var, LoadName('Red'))`` body.  The extracted key must be the
        0-arity atom key ``('Red', 0)`` — matching the runtime ``PredicateMeta``
        key — not the compound-term key ``('LoadName', 2)`` for the reference node.
        """
        # nv — regression for map_coloring private-atom-fact indexing bug
        from clausal.terms import LoadName
        v = Var()
        c = Clause(head=Compound("Color", (v,)),
                   body=[Unify(left=v, right=LoadName(name="Red"))])
        assert _extract_first_arg_key(c, 1) == ("Red", 0)


class TestCellIndexKey:
    """P3-2 Task 4: the key functions learn cells.

    ``_arg_to_index_key`` and ``_runtime_arg_key`` both grow a cell branch,
    ABOVE the generic ``(list, tuple)`` branch (a cell IS a tuple). Same key
    shape as ``Compound``/class-instance/``Call(LoadName)`` — ``(functor,
    arity)`` — so all four producers share one bucket.
    """

    def test_compound_cell_keys_functor_arity(self):
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key,
        )
        assert _arg_to_index_key(("point", 1, 2)) == ("point", 2)
        assert _runtime_arg_key(("point", 1, 2)) == ("point", 2)

    def test_tuple_data_cell_keys_by_length(self):
        """A tuple-DATA cell (slot 0 is the ``TUPLE_TAG`` marker) keys as
        ``(TUPLE_TAG, len - 1)`` — length-keyed, since it has no functor."""
        from clausal.logic.cells import TUPLE_TAG
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key,
        )
        assert _arg_to_index_key((TUPLE_TAG, 1, 2)) == (TUPLE_TAG, 2)
        assert _runtime_arg_key((TUPLE_TAG, 1, 2)) == (TUPLE_TAG, 2)
        # Different lengths key differently.
        assert _arg_to_index_key((TUPLE_TAG, 1)) == (TUPLE_TAG, 1)

    def test_slot_0_var_tuple_is_unindexable(self):
        """A slot-0 ``Var`` (higher-order/deprecated functor position, §1b)
        falls through to ``_INDEX_VAR`` — neither a str functor nor the
        ``TUPLE_TAG`` marker, so no bucket can be assigned at compile OR
        runtime without resolving the Var first."""
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key, _INDEX_VAR,
        )
        v = Var()
        assert _arg_to_index_key((v, 1, 2)) is _INDEX_VAR
        assert _runtime_arg_key((v, 1, 2)) is _INDEX_VAR

    def test_bytelist_coalescing_regression(self):
        """R8 retires the STR/char-list coalesce only — the BYTES side
        (``_bytelist_to_bytes_or_none``) is explicitly KEPT (the codes model)
        and must still coalesce a byte-list with a ``bytes`` scalar."""
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key,
        )
        assert _arg_to_index_key([97, 98, 99]) == b"abc"
        assert _runtime_arg_key([97, 98, 99]) == b"abc"
        assert _runtime_arg_key(b"abc") == b"abc"

    def test_charlist_no_longer_coalesces_with_str(self):
        """R8: retired.  A char-list key is now ``_INDEX_VAR`` (unindexed),
        not the joined str — see ``_arg_to_index_key``'s docstring."""
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key, _INDEX_VAR,
        )
        assert _arg_to_index_key(["a", "b", "c"]) is _INDEX_VAR
        assert _runtime_arg_key(["a", "b", "c"]) is _INDEX_VAR

    def test_bucket_sharing_across_producers(self):
        """A clause with a live cell arg (``assertz``-style) and one with a
        compile-time ``Compound`` node in the same argument position select
        the SAME bucket key — the mechanism ``_build_arg_index`` relies on
        to merge clauses from different producers into one bucket.

        End-to-end proof (real predicate, real bucket function, driven
        through ``call()``) lives in
        ``tests/test_tagged_terms.py::TestBucketPatternIntegration::
        test_asserted_cell_and_compile_time_compound_share_a_bucket``,
        which uses the REALISTIC ``.clausal``-source shape for a compound
        reference (``Call(LoadName('point'), args)``, hoisted to a body
        ``Unify`` — see ``_lift_clause_at_pos``'s docstring) rather than a
        bare ``Compound`` object, which no reachable ``.clausal`` clause
        head carries directly. This unit-level test isolates the KEY
        function itself against the plain ``Compound`` branch instead.
        """
        source_clause = Clause(
            head=Compound("kind", (Compound("point", (1, 2)), "pt")),
            body=[True],
        )
        asserted_clause = Clause(
            head=Compound("kind", (("point", 3, 4), "pt2")),
            body=[True],
        )
        source_key = _extract_first_arg_key(source_clause, 2)
        asserted_key = _extract_first_arg_key(asserted_clause, 2)
        assert source_key == asserted_key == ("point", 2)

    def test_a_cell_with_an_unbound_slot_is_unindexable(self):
        """Regression, found by the full-suite gate (not anticipated by the
        Task 4 brief): a cell that is ground at slot 0 (the functor) but
        carries an UNBOUND Var deeper inside must key ``_INDEX_VAR``, not
        ``(functor, arity)``.

        Mechanism: the bucket that key would route to embeds each of a
        matching clause's own elements as a plain, equality-only
        ``MatchValue`` when that clause's element is a ground literal (no
        ``== or $unify`` hybrid fallback the way a TOP-level indexed
        argument gets) — an unbound Var in the CALLER's slot can never
        satisfy that literal pattern, where the un-indexed fallback's full
        ``unify()`` would happily bind it.  See
        ``tests/test_head_match_imported_compound.py::
        test_indexed_imported_compound_at_second_position_enumerates_all_rows``
        for the end-to-end repro this was found from.
        """
        from clausal.logic.compiler.arg_index import _runtime_arg_key, _INDEX_VAR
        v = Var()
        assert _runtime_arg_key(("Wrap", v)) is _INDEX_VAR
        # Nested one level deeper: the Var is inside an inner cell.
        assert _runtime_arg_key(("Item", "r", ("Met", v), "d")) is _INDEX_VAR
        # NOTE: the class-instance (``is_term_instance``) analog of this gap
        # is DELIBERATELY left unfixed (fix round 1, controller ruling): a
        # pre-existing bug, not exercised by the cell repro that forced this
        # gate, and the branch is exactly O(1) today -- see
        # todo/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md.

    def test_a_fully_ground_cell_still_keys_normally(self):
        """Regression for the fix above: a cell with no unbound Var
        anywhere inside it must still key normally -- the deep-groundness
        gate must not degrade the common case to an unindexed scan."""
        from clausal.logic.compiler.arg_index import _runtime_arg_key
        assert _runtime_arg_key(("Wrap", "direct")) == ("Wrap", 1)
        assert _runtime_arg_key(("Item", "r", ("Met", "direct"), "d")) == ("Item", 3)


class TestGroundnessWalkCompleteness:
    """Fix round 1 (reviewer Important-1 + Minor-3): the deep-groundness
    walk (``_is_deeply_ground`` / ``_is_deeply_ground_walk`` in
    arg_index.py) must be BOUNDED (a node budget) and must recurse into
    every term shape a cell slot can actually hold, not just
    tuple/list/term-instance.
    """

    def test_nested_var_functor_tuple_is_not_ground(self):
        """A nested tuple whose OWN slot 0 is not a str/TUPLE_TAG functor
        tag is not a cell -- every element, INCLUDING element 0, must be
        checked.  Before the fix, ANY tuple unconditionally skipped
        element 0 (assuming it was always a functor slot), so
        ``("W", (Var(), 1))`` read as ground -- the inner tuple's slot 0,
        the Var, was never even looked at."""
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        v = Var()
        assert _is_deeply_ground(("W", (v, 1))) is False
        assert _is_deeply_ground(("W", (1, 2))) is True

    def test_nested_dictterm_with_a_var_value_is_not_ground(self):
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        from clausal.terms import DictTerm
        v = Var()
        assert _is_deeply_ground(("W", DictTerm({"a": v}))) is False
        assert _is_deeply_ground(("W", DictTerm({"a": 1}))) is True

    def test_nested_kwterm_with_a_var_field_is_not_ground(self):
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        from clausal.terms import KWTerm
        v = Var()
        assert _is_deeply_ground(("W", KWTerm("k", x=v))) is False
        assert _is_deeply_ground(("W", KWTerm("k", x=1))) is True

    def test_nested_compound_with_a_var_arg_is_not_ground(self):
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        v = Var()
        assert _is_deeply_ground(("W", Compound("g", (v,)))) is False
        assert _is_deeply_ground(("W", Compound("g", (1,)))) is True

    def test_nested_seglist_with_an_open_hole_is_not_ground(self):
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        from clausal.terms import SegList, ConcreteSeg, VarSeg
        assert _is_deeply_ground(
            ("W", SegList([ConcreteSeg([1, 2]), VarSeg(Var())]))
        ) is False
        assert _is_deeply_ground(("W", SegList([ConcreteSeg([1, 2])]))) is True

    def test_setterm_is_ground(self):
        """SetTerm's own contract requires ground (hashable) elements;
        checked anyway, defensively and cheaply, for consistency with
        DictTerm's values."""
        from clausal.logic.compiler.arg_index import _is_deeply_ground
        from clausal.terms import SetTerm
        assert _is_deeply_ground(("W", SetTerm({1, 2, 3}))) is True

    def test_the_walk_is_budgeted(self):
        """A large, fully-ground argument must not cost O(argument size) --
        the walk gives up (returns False, degrading to a full scan) once
        its node budget is exhausted rather than walking the whole thing.
        """
        from clausal.logic.compiler import arg_index

        big_ground = ("point",) + tuple(range(10_000))
        assert arg_index._is_deeply_ground(big_ground) is False
        # A structure comfortably within budget is still read correctly.
        small_ground = ("point",) + tuple(range(10))
        assert arg_index._is_deeply_ground(small_ground) is True

    def test_budget_exhaustion_degrades_key_to_index_var_not_a_wrong_bucket(self):
        """Driven at the ``_runtime_arg_key`` level: budget exhaustion on a
        large ground cell must route to the safe ``_INDEX_VAR`` fallback,
        never to a bucket lookup that then silently drops the cell's own
        actual (ground, just large) content."""
        from clausal.logic.compiler.arg_index import _runtime_arg_key, _INDEX_VAR
        big_ground = ("point",) + tuple(range(10_000))
        assert _runtime_arg_key(big_ground) is _INDEX_VAR

    def test_driven_nested_dictterm_var_reaches_the_fallback_and_binds(self):
        """End-to-end: a >threshold predicate with a DictTerm-carrying cell
        fact, queried with an unbound Var nested inside the caller's
        DictTerm value, must still find the fact (via the un-indexed
        fallback's full ``unify()``) -- not silently miss it because the
        caller's cell key wrongly routed to an exact-match bucket.
        """
        from clausal.logic.compiler import predicate as predicate_mod
        from clausal.logic.database import Clause, Database, Module
        from clausal.logic.solve import call
        from clausal.terms import DictTerm

        db = Database()
        # Four pad clauses (distinct scalar keys) + one DictTerm-carrying
        # cell fact, to cross _INDEX_THRESHOLD and give the cell fact's
        # functor its own bucket.
        for i in range(4):
            db.assertz(Clause(head=Compound("Probe", (i, "pad")), body=[True]))
        db.assertz(Clause(
            head=Compound("Probe", (("Box", DictTerm({"a": 1})), "boxed")),
            body=[True],
        ))
        predicate_mod.compile_predicate_trampoline(
            "Probe", 2, db.clauses_for("Probe", 2), db, globals_={},
        )
        lm = Module("_t4r1_dictterm_probe")
        lm.db = db

        K = Var()
        v = Var()
        got = [
            deref(K)
            for _t in call("Probe", ("Box", DictTerm({"a": v})), K, module=lm)
        ]
        assert got == ["boxed"], got

    def test_driven_deep_cons_chain_in_the_indexed_argument_is_correct_and_bounded(self):
        """End-to-end regression for the reviewer's exact scenario: a
        NON-tabled predicate that recurses over a cons-cell chain carried
        in its OWN indexed (position-0) argument
        (tests/fixtures/gate_microbench.clausal, also used by the
        fix-round-1 bench transcript, task4-bench.txt).  Correctness (the
        depth comes back right) and boundedness (it completes quickly for
        a chain far deeper than the walk's node budget) in one test.
        """
        import os
        import time
        from clausal.import_hook import _load_module
        from clausal.logic.solve import call

        fixture = os.path.join(
            os.path.dirname(__file__), "fixtures", "gate_microbench.clausal"
        )
        mod = _load_module("tests.fixtures.gate_microbench_regress", fixture)
        lm = mod.__dict__["$module"]

        def build_chain(n):
            c = "nil"
            for i in range(n):
                c = ("cons", i, c)
            return c

        depth = 2000  # far past the groundness walk's node budget (64)
        chain = build_chain(depth)
        N = Var()
        t0 = time.perf_counter()
        got = [deref(N) for _t in call("Depth", chain, N, module=lm)]
        elapsed = time.perf_counter() - t0
        assert got == [depth], got
        # Generous bound (this runs in ~0.01-0.1s on ordinary hardware) --
        # the point is ruling out quadratic blowup, not pinning a tight
        # perf number in a functional test.
        assert elapsed < 5.0, (
            f"depth-{depth} recursion over its own indexed argument took "
            f"{elapsed:.2f}s -- looks like the groundness gate's node "
            f"budget stopped bounding its cost."
        )


class TestLiftClauseAtPos:
    def test_does_not_lift_loadname_atom(self):
        """A ``LoadName`` atom reference must NOT be lifted into the head.

        Lifting would emit a ``MatchClass(LoadName, ...)`` head pattern that no
        runtime value ever matches (the atom resolves to a ``PredicateMeta``,
        not a ``LoadName`` node), so the bucket would yield nothing.  Leaving the
        body ``Unify`` in place lets the runtime resolve the reference to the
        atom.  Mirrors the existing str/bytes skip.
        """
        # nv — regression for map_coloring private-atom-fact bucket lifting bug
        from clausal.terms import LoadName
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        v = Var()
        c = Clause(head=Compound("Color", (v,)),
                   body=[Unify(left=v, right=LoadName(name="Red"))])
        lifted = _lift_clause_at_pos(c, 0)
        # Unchanged: head still a Var, body Unify retained.
        assert lifted.head.args[0] is v
        assert len(lifted.body) == 1

    def test_str_literal_is_now_lifted(self):
        """P3-2 Task 4 (R8): the F095 str half of the lift-skip is retired.

        A str-content list is no longer coalesced with a str bucket (§1b),
        so lifting a str literal into the head no longer risks breaking a
        list caller reaching this clause via a shared bucket — the bucket
        is exclusively str-keyed now.
        """
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=v, right="abc")])
        lifted = _lift_clause_at_pos(c, 0)
        assert lifted.head.args[0] == "abc"
        assert lifted.body == []

    def test_bytes_literal_is_still_not_lifted(self):
        """The bytes half of the F095 skip stays — the codes model (bytes
        ~ byte-list) is deliberately kept, so a bytes-headed clause must
        stay reachable via the loose ``_head_list_unify_input_py`` runtime
        check inside a merged byte-list bucket, exactly as before R8."""
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=v, right=b"abc")])
        lifted = _lift_clause_at_pos(c, 0)
        assert lifted.head.args[0] is v
        assert len(lifted.body) == 1

    def test_ground_str_content_list_literal_is_not_lifted(self):
        """New in Task 4: a ground list literal that is NOT byte-list
        coalescible (here, a char list) must not be lifted.

        Traced by driving the todo's repro
        (todo/done/first-arg-indexing-str-caller-still-reaches-list-fact-2026-09-04.md):
        such a list keys ``_INDEX_VAR`` and is merged as a "matches
        anything" default into every specific-key bucket including a
        same-length str literal's own bucket; lifting it turns the head
        into a sequence pattern whose runtime helper
        (``_head_list_unify_input_py``) still treats a str/bytes target as
        an indexable list — a residual pre-P3-1 hole untouched by the
        ``_variables.c`` do_unify retirement. Leaving the body ``Unify`` in
        place uses strict ``unify()``, which correctly rejects a str
        caller.
        """
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        v = Var()
        c = Clause(head=Compound("f", (v,)),
                   body=[Unify(left=v, right=["a", "b", "c"])])
        lifted = _lift_clause_at_pos(c, 0)
        # Unchanged: head still a Var, body Unify retained.
        assert lifted.head.args[0] is v
        assert len(lifted.body) == 1

    def test_ground_int_list_literal_is_still_lifted(self):
        """A ground list of ints in [0, 255] IS byte-list coalescible — it
        keys as the joined ``bytes`` value (a SPECIFIC key, never merged as
        a default into an unrelated bucket) — so lifting it stays safe and
        is unchanged by Task 4.  Regression for
        ``tests/test_funnel_accessors.py::TestMigrationRegression::
        test_list_dispatch_rebuilds_term_instance_head_at_pos``, which
        relies on exactly this."""
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        v = Var()
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=v, right=[1, 2, 3])])
        lifted = _lift_clause_at_pos(c, 0)
        assert lifted.head.args[0] == [1, 2, 3]
        assert lifted.body == []


# ── Test _build_first_arg_index ──────────────────────────────────────────────


class TestBuildFirstArgIndex:
    def test_too_few_clauses(self):
        # nv
        clauses = [Clause(head=Compound("f", (i,)), body=[True]) for i in range(3)]
        assert _build_first_arg_index(clauses, 1) is None

    def test_zero_arity(self):
        # nv
        clauses = [Clause(head=Compound("f", ()), body=[True]) for _ in range(10)]
        assert _build_first_arg_index(clauses, 0) is None

    def test_all_defaults(self):
        """All clauses have variable first arg — no index."""
        # nv
        clauses = [
            Clause(head=Compound("f", (Var(), Var())), body=[True])
            for _ in range(5)
        ]
        assert _build_first_arg_index(clauses, 2) is None

    def test_basic_partition(self):
        # nv
        clauses = [
            Clause(head=Compound("f", (1,)), body=[True]),
            Clause(head=Compound("f", (2,)), body=[True]),
            Clause(head=Compound("f", (3,)), body=[True]),
            Clause(head=Compound("f", (4,)), body=[True]),
        ]
        index = _build_first_arg_index(clauses, 1)
        assert index is not None
        assert set(index["buckets"].keys()) == {1, 2, 3, 4}
        assert index["defaults"] == []
        # Each bucket has exactly one clause
        for key, bucket in index["buckets"].items():
            assert len(bucket) == 1

    def test_mixed_with_defaults(self):
        # nv
        v1, v2 = Var(), Var()
        clauses = [
            Clause(head=Compound("f", (1, Var())), body=[True]),   # idx 0, key=1
            Clause(head=Compound("f", (v1, v2)), body=[True]),     # idx 1, default
            Clause(head=Compound("f", (2, Var())), body=[True]),   # idx 2, key=2
            Clause(head=Compound("f", (3, Var())), body=[True]),   # idx 3, key=3
        ]
        index = _build_first_arg_index(clauses, 2)
        assert index is not None
        assert len(index["defaults"]) == 1
        # Bucket for key=1 has clause 0 + default clause 1
        assert len(index["buckets"][1]) == 2
        # Bucket for key=2 has default clause 1 + clause 2
        assert len(index["buckets"][2]) == 2
        # Bucket for key=3 has default clause 1 + clause 3
        assert len(index["buckets"][3]) == 2


# ── Integration tests: simple mode ──────────────────────────────────────────


class TestIndexedDispatchSimple:
    def _make_fact_db(self, functor, facts):
        """Build a Database with normalized fact clauses."""
        db = Database()
        for fact_args in facts:
            clause = _normalize_fact_clause(Compound(functor, tuple(fact_args)))
            db.assertz(clause)
        return db

    def test_ground_lookup(self):
        """Ground first-arg query uses index to find the right clause."""
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["red", v], trail)
        assert results == [("red", 255)]

    def test_var_first_arg_enumerates_all(self):
        """Unbound first-arg query tries all clauses."""
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == 5

    def test_no_match_returns_empty(self):
        """Ground first-arg with no matching clause yields nothing."""
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["purple", v], trail)
        assert results == []

    def test_mixed_var_and_specific(self):
        """Default (var-headed) clauses interleave with specific clauses."""
        # clauses: f(1, a), f(X, b), f(2, c), f(3, d), f(X, e)
        # All ground values normalized to Var+Unify for output-mode queries.
        # nv
        db = Database()
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "c"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "d"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "e"))))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()

        # Query f(1, Y): should get (1, a), (1, b), (1, e)
        y = Var()
        results = _simple_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

        # Query f(2, Y): should get (2, b), (2, c), (2, e)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [2, y], trail)
        assert [r[1] for r in results] == ["b", "c", "e"]

        # Query f(99, Y): should get (99, b), (99, e) — only defaults
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [99, y], trail)
        assert [r[1] for r in results] == ["b", "e"]

    def test_integer_keys(self):
        """Large fact table with integer first args."""
        # nv
        n = 20
        db = self._make_fact_db("num", [(i, i * i) for i in range(n)])
        fn = compile_predicate("num", 2, db.clauses_for("num", 2), db)

        # Specific lookup
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, [7, v], trail)
        assert results == [(7, 49)]

        # Enumerate all
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == n

    def test_string_keys(self):
        """Fact table with string first args."""
        # nv
        facts = [("apple", 1), ("banana", 2), ("cherry", 3),
                 ("date", 4), ("elderberry", 5)]
        db = self._make_fact_db("fruit", facts)
        fn = compile_predicate("fruit", 2, db.clauses_for("fruit", 2), db)

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["cherry", v], trail)
        assert results == [("cherry", 3)]

    def test_below_threshold_no_index(self):
        """Few clauses → no indexing, still works."""
        # nv
        db = self._make_fact_db("small", [(1, "a"), (2, "b")])
        fn = compile_predicate("small", 2, db.clauses_for("small", 2), db)
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, [1, v], trail)
        assert results == [(1, "a")]


# ── Integration tests: trampoline mode ───────────────────────────────────────


class TestIndexedDispatchTrampoline:
    def _make_fact_db(self, functor, facts):
        db = Database()
        for fact_args in facts:
            clause = _normalize_fact_clause(Compound(functor, tuple(fact_args)))
            db.assertz(clause)
        return db

    def test_ground_lookup(self):
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["red", v], trail)
        assert results == [("red", 255)]

    def test_var_first_arg_enumerates_all(self):
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(results) == 5

    def test_no_match_returns_empty(self):
        # nv
        db = self._make_fact_db("color", [
            ("red", 255), ("green", 128), ("blue", 0),
            ("yellow", 200), ("white", 255),
        ])
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["purple", v], trail)
        assert results == []

    def test_mixed_var_and_specific(self):
        # nv
        db = Database()
        db.assertz(_normalize_fact_clause(Compound("f", (1, "a"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "b"))))
        db.assertz(_normalize_fact_clause(Compound("f", (2, "c"))))
        db.assertz(_normalize_fact_clause(Compound("f", (3, "d"))))
        db.assertz(_normalize_fact_clause(Compound("f", (Var(), "e"))))
        fn = compile_predicate_trampoline("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()

        # f(1, Y): (1,a), (1,b), (1,e)
        y = Var()
        results = _trampoline_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

        # f(2, Y): (2,b), (2,c), (2,e)
        trail = Trail()
        y = Var()
        results = _trampoline_solutions(fn, [2, y], trail)
        assert [r[1] for r in results] == ["b", "c", "e"]

        # f(99, Y): (99,b), (99,e)
        trail = Trail()
        y = Var()
        results = _trampoline_solutions(fn, [99, y], trail)
        assert [r[1] for r in results] == ["b", "e"]

    def test_large_fact_table(self):
        # nv
        n = 50
        db = self._make_fact_db("num", [(i, i * i) for i in range(n)])
        fn = compile_predicate_trampoline(
            "num", 2, db.clauses_for("num", 2), db,
        )
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, [42, v], trail)
        assert results == [(42, 42 * 42)]

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _trampoline_solutions(fn, [v1, v2], trail)
        assert len(results) == n


# ── Dynamic predicate re-indexing ────────────────────────────────────────────


class TestDynamicReindex:
    def test_assertz_rebuilds_index_simple(self):
        """After assertz, lazy recompile rebuilds the index."""
        # nv
        db = Database()
        db.mark_dynamic("color", 2)
        for args in [("red", 1), ("green", 2), ("blue", 3), ("white", 4)]:
            db.assertz(_normalize_fact_clause(Compound("color", args)))
        fn = compile_predicate("color", 2, db.clauses_for("color", 2), db)

        # Initial lookup works
        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["red", v], trail)
        assert results == [("red", 1)]

        # Add a new clause — triggers lazy recompile on next use
        db.assertz(_normalize_fact_clause(Compound("color", ("purple", 5))))

        # The dispatch fn stored in db should now lazily recompile
        new_fn = db.get_dispatch("color", 2)
        trail = Trail()
        v = Var()
        results = _simple_solutions(new_fn, ["purple", v], trail)
        assert results == [("purple", 5)]

    def test_assertz_rebuilds_index_trampoline(self):
        # nv
        db = Database()
        db.mark_dynamic("color", 2)
        for args in [("red", 1), ("green", 2), ("blue", 3), ("white", 4)]:
            db.assertz(_normalize_fact_clause(Compound("color", args)))
        fn = compile_predicate_trampoline(
            "color", 2, db.clauses_for("color", 2), db,
        )

        trail = Trail()
        v = Var()
        results = _trampoline_solutions(fn, ["red", v], trail)
        assert results == [("red", 1)]

        db.assertz(_normalize_fact_clause(Compound("color", ("purple", 5))))
        new_fn = db.get_dispatch("color", 2)
        trail = Trail()
        v = Var()
        results = _trampoline_solutions(new_fn, ["purple", v], trail)
        assert results == [("purple", 5)]


# ── PredicateMeta integration ────────────────────────────────────────────────


class TestPredicateMetaIndexing:
    def test_predicate_meta_facts(self):
        """PredicateMeta class facts with normalized Var+Unify heads."""
        # nv
        class fruit(metaclass=PredicateMeta):
            _fields = ("name", "count")

        db = Database()
        for name, count in [("apple", 5), ("banana", 3), ("cherry", 8),
                            ("date", 2), ("elderberry", 1)]:
            v1, v2 = Var(), Var()
            head = fruit(name=v1, count=v2)
            db.assertz(Clause(head=head, body=[Unify(left=v1, right=name),
                                                Unify(left=v2, right=count)]))

        fn = compile_predicate(
            "fruit", 2, db.clauses_for("fruit", 2), db,
            globals_={"fruit": fruit},
        )

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["cherry", v], trail)
        assert results == [("cherry", 8)]

        trail = Trail()
        v = Var()
        results = _simple_solutions(fn, ["missing", v], trail)
        assert results == []

        trail = Trail()
        v1, v2 = Var(), Var()
        results = _simple_solutions(fn, [v1, v2], trail)
        assert len(results) == 5


# ── Edge cases ───────────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_single_arity(self):
        """Arity-1 predicates can be indexed."""
        # nv
        db = Database()
        for i in range(5):
            db.assertz(_normalize_fact_clause(Compound("p", (i,))))
        fn = compile_predicate("p", 1, db.clauses_for("p", 1), db)
        trail = Trail()
        results = _simple_solutions(fn, [3], trail)
        assert results == [(3,)]

    def test_duplicate_keys(self):
        """Multiple clauses with the same first-arg key."""
        # nv
        db = Database()
        for args in [(1, "a"), (1, "b"), (2, "c"), (2, "d"), (1, "e")]:
            db.assertz(_normalize_fact_clause(Compound("f", args)))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [1, y], trail)
        assert [r[1] for r in results] == ["a", "b", "e"]

    def test_none_as_key(self):
        """None as first argument value is indexable."""
        # nv
        db = Database()
        for v in [None, 1, 2, 3]:
            db.assertz(_normalize_fact_clause(Compound("f", (v, str(v)))))
        fn = compile_predicate("f", 2, db.clauses_for("f", 2), db)
        trail = Trail()
        y = Var()
        results = _simple_solutions(fn, [None, y], trail)
        assert results == [(None, "None")]

    def test_bool_vs_int(self):
        """True/1 and False/0 share hash buckets in Python — both found."""
        # nv
        db = Database()
        for v in [True, False, 0, 1, 2]:
            db.assertz(_normalize_fact_clause(Compound("f", (v,))))
        fn = compile_predicate("f", 1, db.clauses_for("f", 1), db)
        trail = Trail()
        # True == 1 and False == 0 in Python, so querying with True finds both
        results = _simple_solutions(fn, [True], trail)
        # Both True and 1 should match (they're equal in Python)
        assert len(results) >= 1


class TestAtomInListHead:
    """Atoms (zero-arity PredicateMeta classes) appearing inside a list
    pattern in the clause head — regression for the indexer-driven bucket
    compile that emitted the atom class into an ``ast.Constant`` node and
    triggered ``TypeError: got an invalid type in Constant: PredicateMeta``.

    The bug surfaced only when indexing fired (>= _INDEX_THRESHOLD clauses)
    and the chosen index bucket contained at least one clause whose head
    matches on a list literal containing an atom — see
    ``todo/insurance_required_predicate_meta_quirk.md`` in
    ``packages/clausal-thai_imm_rules`` for the original report.
    """

    def test_mixed_scalar_and_list_last_args(self):
        """Compile a 4-clause predicate mixing scalar-last and ``[atom, int]``
        list-last heads.  The combination forces indexing on a position whose
        bucket re-includes the list-pattern clauses; the list pattern
        ``[usd, 50000]`` then carries the ``usd`` atom into the head-match
        AST.

        P3-1 §1b/R2 INVERSION: pre-pivot, the atom had to be lowered as a
        ``Name`` reference rather than embedded into an ``ast.Constant`` (a
        live zero-field ``PredicateMeta`` class is not a valid ``ast.Constant``
        value).  Atoms are now global-by-spelling interned strs, so the SAME
        compatibility lowering that used to be the bug fix (emit an
        ``ast.Constant`` of the class's ``__name__``) is simply the atom's
        normal, unconditional lowering — the round-tripped last arg comes
        back as the plain str ``'usd'``, not the ``usd`` class object.
        """
        # nv
        usd = make_atom("usd")
        non_o_a = make_atom("non_o_a")
        non_o_x = make_atom("non_o_x")
        ltr = make_atom("ltr")
        smart_t = make_atom("smart_t")
        unrestricted = make_atom("unrestricted")

        db = Database()
        clauses = [
            (non_o_a, 40000, 400000, 3000000),
            (non_o_x, 40000, 400000, unrestricted),
            (ltr,     unrestricted, unrestricted, [usd, 50000]),
            (smart_t, unrestricted, unrestricted, [usd, 100000]),
        ]
        for args in clauses:
            db.assertz(_normalize_fact_clause(Compound("InsuranceRequired", args)))

        # Before the fix this raised
        # ``TypeError: got an invalid type in Constant: PredicateMeta``.
        fn = compile_predicate(
            "InsuranceRequired", 4,
            db.clauses_for("InsuranceRequired", 4),
            db,
            globals_={
                "usd": usd, "non_o_a": non_o_a, "non_o_x": non_o_x,
                "ltr": ltr, "smart_t": smart_t, "unrestricted": unrestricted,
            },
        )

        # Query with an unbound last arg routes through the fallback
        # (no bucket key for an unbound Var), so every clause's full head
        # match runs — verifying all four lowered clauses are well-formed.
        trail = Trail()
        a, b, c, d = Var(), Var(), Var(), Var()
        results = _simple_solutions(fn, [a, b, c, d], trail)
        assert len(results) == 4
        # The list-pattern clauses round-trip the atom-bearing last arg.
        # The atom comes back as the plain str 'usd' (§1b/R2), not the
        # `usd` PredicateMeta class object passed in as a compile-time value.
        last_args = [r[3] for r in results]
        assert ["usd", 50000] in last_args
        assert ["usd", 100000] in last_args
