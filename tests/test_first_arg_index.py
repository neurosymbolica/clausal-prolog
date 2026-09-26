"""Tests for V2-1: First-argument indexing.

Verifies that compile_predicate and compile_predicate_trampoline use
first-argument indexing when there are enough clauses, and that the
indexed dispatch produces the same results as unindexed dispatch.
"""

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
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
from tests.predicate_api_support import term_ctor
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
        c = Clause(head=Compound("f", (mint("hello"), 1)), body=[True])
        assert _extract_first_arg_key(c, 2) == ("hello", 0)
        # ...and the STRING of the same text is unindexable (spec §6.9).
        c_str = Clause(head=Compound("f", (chars("hello"), 1)), body=[True])
        assert _extract_first_arg_key(c_str, 2) is _INDEX_VAR

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
        c = Clause(head=Compound("f", (v,)), body=[Unify(left=mint("abc"), right=v)])
        assert _extract_first_arg_key(c, 1) == ("abc", 0)

    def test_zero_arity(self):
        # nv
        c = Clause(head=Compound("f", ()), body=[True])
        assert _extract_first_arg_key(c, 0) is _INDEX_VAR

    def test_predicate_meta_head(self):
        # nv
        color = term_ctor("color", ("name", "code"))

        v = Var()
        head = color(name=v, code=Var())
        c = Clause(head=head, body=[Unify(left=v, right=mint("red"))])
        assert _extract_first_arg_key(c, 2) == ("red", 0)

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


    def test_atom_reference_key_from_unify_unresolvable_without_env(self):
        """Without a compile-time *env* (or when the name isn't in it), the
        reference cannot be resolved to a runtime value, so the key must be
        ``_INDEX_VAR`` (a full clause scan — always correct) rather than a
        GUESS at what the reference denotes.  This is the P3-1 atom-pivot
        hotfix's default-safety property: an un-threaded caller degrades to
        unindexed dispatch instead of reproducing the pre-fix bug.
        """
        from clausal.terms import LoadName
        v = Var()
        c = Clause(head=Compound("color", (v,)),
                   body=[Unify(left=v, right=LoadName(name="red"))])
        assert _extract_first_arg_key(c, 1) is _INDEX_VAR
        assert _extract_first_arg_key(c, 1, env=None) is _INDEX_VAR
        assert _extract_first_arg_key(c, 1, env={}) is _INDEX_VAR


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
        assert _runtime_arg_key(("wrap", v)) is _INDEX_VAR
        # Nested one level deeper: the Var is inside an inner cell.
        assert _runtime_arg_key(("item", "r", ("met", v), "d")) is _INDEX_VAR
        # P3-3 Task 4 fold-in: the class-instance (``is_term_instance``)
        # analog of this gap, parked at P3-2 fix round 1 and wired here --
        # the repro from
        # todo/done/first-arg-index-partially-ground-instance-keys-into-bucket-2026-09-05.md.
        Wrap = term_ctor("wrap", ["sub"])
        assert _runtime_arg_key(Wrap(sub=Var())) is _INDEX_VAR

    def test_a_fully_ground_cell_still_keys_normally(self):
        """Regression for the fix above: a cell with no unbound Var
        anywhere inside it must still key normally -- the deep-groundness
        gate must not degrade the common case to an unindexed scan."""
        from clausal.logic.compiler.arg_index import _runtime_arg_key
        assert _runtime_arg_key(("wrap", "direct")) == ("wrap", 1)
        assert _runtime_arg_key(("item", "r", ("met", "direct"), "d")) == ("item", 3)
        Wrap = term_ctor("wrap", ["sub"])
        assert _runtime_arg_key(Wrap(sub="direct")) == ("wrap", 1)
        # ... and the gate is opt-out, exactly as it is for a cell: a
        # predicate/position whose lifted arms carry no literal sub-value
        # passes ``deep_gate=False`` and keeps the O(1) key.
        assert _runtime_arg_key(Wrap(sub=Var()), deep_gate=False) == ("wrap", 1)


class TestImportedAtomIndexKey:
    """P3-1 atom-pivot hotfix: ``_arg_to_index_key``'s LoadName/LoadAttr
    branch resolves the reference against a compile-time *env* and keys
    the RESOLVED VALUE through ``_runtime_arg_key`` — the same function a
    live runtime argument of that value goes through — instead of guessing
    a key from the reference's spelling (the pre-pivot ``(name, 0)``
    PredicateMeta-class convention, wrong for a post-pivot atom, which is
    its own ``str`` spelling).

    End-to-end (real cross-module ``.clausal`` fixtures, real dispatch)
    coverage lives in ``tests/test_imported_atom_head_index.py``; these are
    the unit-level key-agreement checks — including the missing table row
    (a bare imported-atom head arg) whose absence is why P3-2 Task 4's own
    key-agreement table didn't catch this bug.
    """

    def test_key_agreement_row_bare_imported_atom(self):
        """THE MISSING ROW: a bare imported-atom head arg.  Compile-time key
        (with *env* resolving the reference to the atom's plain ``str``) must
        equal the runtime key for that same resolved atom.  Pre-fix, the
        compile-time side guessed ``(name.rsplit('.', 1)[-1], 0)`` here —
        the exact mismatch that dropped 633 corpus tests.
        """
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key,
        )
        from clausal.terms import LoadName
        # The import machinery rewrites a bare imported reference into ONE
        # dotted ast.Name id (a single global lookup) -- see
        # terms_to_ast._resolve_functor_binding's docstring.
        ref = LoadName(name="pkg.schema.aa")
        env = {"pkg.schema.aa": mint("aa")}
        compile_key = _arg_to_index_key(ref, env)
        runtime_key = _runtime_arg_key(mint("aa"))
        assert compile_key == runtime_key == ("aa", 0)

    def test_key_agreement_row_dotted_loadattr_chain(self):
        """Item 2: the same agreement for a genuine ``LoadAttr`` chain (a
        literal ``mod.attr`` reference written in source), not just the
        single-dotted-``LoadName`` form the import machinery produces for a
        bare imported name.
        """
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key,
        )
        from clausal.terms import LoadName, LoadAttr
        ref = LoadAttr(object=LoadName(name="schema"), attr="aa")
        env = {"schema.aa": mint("aa")}
        compile_key = _arg_to_index_key(ref, env)
        runtime_key = _runtime_arg_key(mint("aa"))
        assert compile_key == runtime_key == ("aa", 0)

    def test_key_agreement_row_hide_mangled_atom(self):
        """Item 3: a ``-hide``-mangled atom keys as the MANGLED string on
        both sides -- not the bare tail.  The pre-fix formula
        (``dotted.rsplit('.', 1)[-1], 0)``) is wrong here in a second way:
        a mangled spelling (``module\x1fname``) contains no ``.``, so
        ``rsplit('.', 1)[-1]`` returns the whole mangled string UNCHANGED,
        giving the tuple key ``(mangled, 0)`` -- still a mismatch against
        the runtime key, which is the mangled string itself (an atom keys
        as its own spelling, mangled or not).
        """
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _runtime_arg_key, _INDEX_VAR,
        )
        from clausal.terms import LoadName
        mangled = "hidden_owner\x1fhidden_aa"
        ref = LoadName(name=mangled)
        env = {mangled: mint(mangled)}
        compile_key = _arg_to_index_key(ref, env)
        runtime_key = _runtime_arg_key(mint(mangled))
        assert compile_key == runtime_key == (mangled, 0)
        assert compile_key is not _INDEX_VAR

    def test_unresolvable_dotted_name_is_index_var(self):
        """Item 4: a dotted reference *env* doesn't know about (name absent,
        or *env* itself is ``None``) must key ``_INDEX_VAR`` -- never a
        guess.  This is always safe: ``_INDEX_VAR`` clauses become the
        bucket-set's DEFAULTS, merged into every bucket, so a caller still
        reaches the clause via the un-indexed fallback's ``unify()``.
        """
        from clausal.logic.compiler.arg_index import (
            _arg_to_index_key, _INDEX_VAR, _build_arg_index, _extract_arg_key,
        )
        from clausal.terms import LoadName
        ref = LoadName(name="py.sympy.inf")
        assert _arg_to_index_key(ref, None) is _INDEX_VAR
        assert _arg_to_index_key(ref, {}) is _INDEX_VAR
        assert _arg_to_index_key(ref, {"some.other.name": "x"}) is _INDEX_VAR

        # End-to-end within the indexer: 4+ clauses whose head arg all
        # resolve to _INDEX_VAR must not build a (mis-)indexed bucket set at
        # all -- _build_arg_index reports "no specific clauses" (None), the
        # correct signal to fall back to full-scan dispatch.
        clauses = []
        for i in range(4):
            v = Var()
            clauses.append(Clause(
                head=Compound("f", (v, "tag")),
                body=[Unify(left=v, right=LoadName(name=f"py.sympy.const{i}"))],
            ))
        for c in clauses:
            assert _extract_arg_key(c, 0, 2, env={}) is _INDEX_VAR
        assert _build_arg_index(clauses, 2, 0, env={}) is None


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
        fix-round-1 bench transcript, task4-bench.txt).  correctness (the
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
            c = mint("nil")
            for i in range(n):
                c = ("cons", i, c)
            return c

        depth = 2000  # far past the groundness walk's node budget (64)
        chain = build_chain(depth)
        N = Var()
        t0 = time.perf_counter()
        got = [deref(N) for _t in call("depth", chain, N, module=lm)]
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


class TestDeepGateFlagComputation:
    """Fix round 2 (controller design ruling): the deep-groundness gate
    (round 1) becomes COMPILE-TIME CONDITIONAL.  Bucket SELECTION by
    shallow ``(functor, arity)`` is always correct for a partially-ground
    caller; the only miss-hazard is a bucket ARM whose LIFTED pattern
    carries a literal sub-value.  ``list_dispatch.
    _lifted_head_arg_needs_deep_gate`` decides that, ONCE, at bucket-build
    time -- these tests pin the decision function itself before checking
    that it is actually wired through the compiler (the classes below).
    """

    def test_a_bare_var_needs_no_gate(self):
        """The lift was a no-op -- this clause keeps its body Unify,
        which handles a partially-ground caller correctly via real
        unify(); nothing to gate."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(Var()) is False

    def test_a_bare_atom_needs_no_gate(self):
        """A 0-arity atom reference (e.g. a lifted ``Pad1`` pad clause)
        has no sub-slots at all -- no partial-groundness risk, and it
        never even reaches ``_runtime_arg_key``'s cell-gated branch
        (atoms key through the PredicateMeta branch instead). Regression:
        an earlier version of this function duck-typed LoadName/LoadAttr
        as ``is_term_instance`` and wrongly said True, which would have
        turned the gate ON for every co-indexed cell bucket at the same
        position as a pad atom fact -- exactly the shape
        tests/fixtures/gate_microbench.clausal exercises."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        from clausal.terms import LoadName, LoadAttr
        assert _lifted_head_arg_needs_deep_gate(LoadName(name="pad1")) is False
        assert _lifted_head_arg_needs_deep_gate(
            LoadAttr(object=LoadName(name="m"), attr="atom")
        ) is False

    def test_a_fresh_var_cell_needs_no_gate(self):
        """``wrap(SUB)`` with SUB a genuine fresh Var in the clause --
        the compiled pattern captures SUB, it does not compare it -- no
        literal anywhere below the functor tag."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(("wrap", Var())) is False

    def test_a_ground_cell_needs_the_gate(self):
        """``wrap(direct)`` -- a real value below the functor tag compiles
        to a MatchValue: the exact hazard this round exists for."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(("wrap", "direct")) is True

    def test_call_loadname_fresh_var_arg_needs_no_gate(self):
        """The source-shaped compound reference (``Call(LoadName, args)``)
        with a fresh-Var argument -- the shape a genuine
        ``wrap(SUB)`` compiles to before any resolution."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        from clausal.terms import Call, LoadName
        v = Var()
        term = Call(func=LoadName(name="wrap"), args=[v], kwargs=[])
        assert _lifted_head_arg_needs_deep_gate(term) is False

    def test_call_loadname_atom_arg_needs_the_gate(self):
        """``wrap(direct)`` in its PRE-resolution ``Call(LoadName)`` shape
        -- ``direct`` is a nested bare atom reference, which DOES count
        as a literal once it is not the whole indexed value itself (the
        asymmetry ``test_a_bare_atom_needs_no_gate`` pins at the top
        level)."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        from clausal.terms import Call, LoadName
        term = Call(
            func=LoadName(name="wrap"),
            args=[LoadName(name="direct")], kwargs=[],
        )
        assert _lifted_head_arg_needs_deep_gate(term) is True

    def test_compound_fresh_var_arg_needs_no_gate(self):
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(
            Compound("g", (Var(),))
        ) is False

    def test_compound_ground_arg_needs_the_gate(self):
        """The pre-existing (not cell-specific) hazard: a lifted
        ``Compound`` literal arg is exactly as risky as a lifted cell
        literal arg -- the flag computation covers it the same way."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(
            Compound("g", (1,))
        ) is True

    def test_term_instance_ground_field_needs_the_gate(self):
        """Same pre-existing hazard, for a resolved term-INSTANCE literal
        (``is_term_instance`` branch) rather than a ``Compound`` AST node
        -- the reviewer's explicit ask: a lifted-literal INSTANCE bucket
        must also set the flag."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        Wrap = term_ctor("wrap", ["sub"])
        assert _lifted_head_arg_needs_deep_gate(Wrap(sub=1)) is True
        assert _lifted_head_arg_needs_deep_gate(Wrap(sub=Var())) is False

    def test_a_bare_scalar_needs_no_gate(self):
        """A plain scalar head arg is never lifted into anything the
        cell-gated branch of ``_runtime_arg_key`` even sees (it keys as
        itself, a hashable value, via the ``_INDEXABLE_TYPES`` branch)."""
        from clausal.logic.compiler.list_dispatch import (
            _lifted_head_arg_needs_deep_gate,
        )
        assert _lifted_head_arg_needs_deep_gate(0) is False
        assert _lifted_head_arg_needs_deep_gate("abc") is False


class TestDeepGateWiredThroughCompiler:
    """Fix round 2: the per-position flag is actually computed at
    bucket-build time (predicate.py) and reaches the compiled dispatch
    closure, not just the standalone decision function.
    """

    def _plans_for(self, functor, arity, db):
        """Capture the ``plans`` list a real compile passes to
        ``_make_groundness_dispatch_trampoline`` for *functor*/*arity*."""
        import clausal.logic.compiler.arg_index as arg_index_mod
        from clausal.logic.compiler import predicate as predicate_mod

        captured = []
        original = arg_index_mod._make_groundness_dispatch_trampoline

        def spy(plans, *a, **kw):
            captured.append(list(plans))
            return original(plans, *a, **kw)

        arg_index_mod._make_groundness_dispatch_trampoline = spy
        predicate_mod._make_groundness_dispatch_trampoline = spy
        try:
            compile_predicate_trampoline(
                functor, arity, db.clauses_for(functor, arity), db,
                globals_={},
            )
        finally:
            arg_index_mod._make_groundness_dispatch_trampoline = original
            predicate_mod._make_groundness_dispatch_trampoline = original
        assert captured, "the predicate did not build a groundness plan"
        return captured[0]

    def test_var_headed_recursion_position_flags_off(self):
        """The gate_microbench shape, built directly via the Python API:
        five clauses at position 0 (three atom pads + nil + a cons cell
        with ONLY fresh Vars below its functor tag) -- none of them lifts
        a literal, so the compiled plan's flag must be False."""
        from clausal.logic.database import Clause, Database
        from clausal.terms import Call, LoadName

        db = Database()
        for name in ("pad1", "pad2", "pad3"):
            db.assertz(Clause(
                head=Compound("depth", (Call(func=LoadName(name=name), args=[], kwargs=[]), 0)),
                body=[True],
            ))
        db.assertz(Clause(head=Compound("depth", ("nil", 0)), body=[True]))
        h, t, n1 = Var(), Var(), Var()
        db.assertz(Clause(
            head=Compound("depth", (("cons", h, t), Var())),
            body=[Unify(left=Var(), right=n1)],
        ))
        plans = self._plans_for("depth", 2, db)
        pos0_plans = [pl for pl in plans if pl[0] == 0]
        assert pos0_plans, plans
        for pos, idx_dict, dflt_fn, deep_gate in pos0_plans:
            assert deep_gate is False, (pos, deep_gate)

    def test_lifted_literal_cell_position_flags_on(self):
        """The tagged/2 shape (a ground-atom cell fact) built directly:
        one bucket's lifted clause carries a real value below its functor
        tag -- the compiled plan's flag must be True."""
        from clausal.logic.database import Clause, Database

        db = Database()
        for i in range(3):
            db.assertz(Clause(head=Compound("Boxed", (i, "pad")), body=[True]))
        db.assertz(Clause(
            head=Compound("Boxed", (("wrap", "direct"), "boxed")),
            body=[True],
        ))
        plans = self._plans_for("Boxed", 2, db)
        pos0_plans = [pl for pl in plans if pl[0] == 0]
        assert pos0_plans, plans
        assert any(deep_gate for _p, _i, _d, deep_gate in pos0_plans), plans

    def test_lifted_literal_instance_position_flags_on(self):
        """The reviewer's explicit ask: a lifted-literal INSTANCE bucket
        (an ``is_term_instance`` value, not a raw cell tuple) also sets
        the flag -- built via a real term-instance head, the way a
        Python-side producer (R6) still constructs one."""
        from clausal.logic.database import Clause, Database

        Wrap = term_ctor("wrap", ["sub"])
        db = Database()
        for i in range(3):
            db.assertz(Clause(head=Compound("Boxed2", (i, "pad")), body=[True]))
        db.assertz(Clause(
            head=Compound("Boxed2", (Wrap(sub="direct"), "boxed")),
            body=[True],
        ))
        plans = self._plans_for("Boxed2", 2, db)
        pos0_plans = [pl for pl in plans if pl[0] == 0]
        assert pos0_plans, plans
        assert any(deep_gate for _p, _i, _d, deep_gate in pos0_plans), plans


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
        c = Clause(head=Compound("color", (v,)),
                   body=[Unify(left=v, right=LoadName(name="red"))])
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
        """default (var-headed) clauses interleave with specific clauses."""
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
        fruit = term_ctor("fruit", ("name", "count"))

        db = Database()
        for name, count in [("apple", 5), ("banana", 3), ("cherry", 8),
                            ("date", 2), ("elderberry", 1)]:
            v1, v2 = Var(), Var()
            head = fruit(name=v1, count=v2)
            db.assertz(Clause(head=head, body=[Unify(left=v1, right=name),
                                                Unify(left=v2, right=count)]))

        fn = compile_predicate(
            "fruit", 2, db.clauses_for("fruit", 2), db,
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
    """atoms (zero-arity PredicateMeta classes) appearing inside a list
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
        # The atoms are the atoms (W4b-3 slice 7): they were zero-field
        # PredicateMeta classes, the shape of the original bug below, which
        # left with the class.  What stays pinned is the mixed scalar/list
        # last-argument compile.
        usd, non_o_a, non_o_x = "usd", "non_o_a", "non_o_x"
        ltr, smart_t, unrestricted = "ltr", "smart_t", "unrestricted"

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
        # THE FLIP: the atom round-trips as the arity-0 CELL ("usd",), not
        # the `usd` PredicateMeta class object passed in as a compile-time
        # value (and no longer as the P3-1 bare str either).
        last_args = [r[3] for r in results]
        assert [mint("usd"), 50000] in last_args
        assert [mint("usd"), 100000] in last_args


class TestNonAtomNestedInCellHeadArgUnreachable:
    """Pin CURRENT (broken, PRE-EXISTING) behavior: a non-atom value nested
    inside a data-functor/cell head argument is unreachable through the
    bucket that argument's OWN position indexes into, when dispatch is
    forced through that position specifically.

    See todo/imported-non-atom-constant-head-args-unreachable-2026-09-05.md
    for the full mechanism. PRE-DATES the imported-atom index-key hotfix
    (fix/imported-atom-index-key, 2026-09-05) -- verified by reproducing
    the identical result against the pre-fix engine; this hotfix's diff
    never touches ``head_match.py`` or the ``Call(LoadName)`` cell branch
    this lives in. NOT a regression.

    A TOP-LEVEL (non-nested) scalar reference is NOT affected --
    ``list_dispatch._lift_clause_at_pos`` unconditionally refuses to lift a
    bare ``LoadName``/``LoadAttr`` at the indexed position itself, so the
    head stays a Var and the body ``Unify`` resolves it correctly at
    runtime regardless of type. Only a reference NESTED inside an already-
    lifted cell/compound field reaches ``head_match.head_to_match_pattern``'s
    ``LoadName``/``LoadAttr`` branch, which only builds a real ``MatchValue``
    pattern for a ``str`` resolution -- anything else falls through to the
    dead ``is_term_instance`` fallback.

    This is a PIN of current behavior, not an endorsement: when the fix
    lands (extend the MatchValue branch to the full literal-safe type set,
    or refuse the lift for a non-literal-safe resolution), invert this
    assertion consciously.
    """

    def test_nested_non_atom_reference_unreachable_when_position_forced(self):
        from clausal.terms import Call, LoadName
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        clauses = []
        for i, val in zip((1, 2, 3, 4), (100, 200, 300, 400)):
            n_var, l_var = Var(), Var()
            wrap_call = Call(
                func=LoadName(name="wrap"),
                args=(LoadName(name=f"c.CONST{i}"),),
                kwargs=(),
            )
            clauses.append(Clause(
                head=Compound("level", (n_var, l_var)),
                body=[
                    Unify(left=n_var, right=i),
                    Unify(left=l_var, right=wrap_call),
                ],
            ))

        globals_ = {f"c.CONST{i}": v for i, v in zip((1, 2, 3, 4), (100, 200, 300, 400))}
        globals_["wrap"] = "wrap"
        globals_[FUNCTOR_SIGNATURES_KEY] = {"wrap": ("x",)}

        fn = compile_predicate_trampoline("level", 2, clauses, None, globals_=globals_)

        # Both args ground: dispatch picks the MORE selective position-0
        # index (4 distinct int keys) over position-1's single-key cell
        # bucket, so the broken nested pattern is never exercised here --
        # this direction is (and must stay) correct.
        results = _trampoline_solutions(fn, [3, ("wrap", 300)])
        assert len(results) == 1

        # Position 0 unbound: no info there, so dispatch is forced through
        # position 1's ('Wrap', 1) bucket -- the ONLY index available.
        # CURRENT (broken) behavior: 0 solutions. Correct behavior (once
        # the todo's fix lands) would be 1, binding the Var to 3.
        v = Var()
        results = _trampoline_solutions(fn, [v, ("wrap", 300)])
        assert results == [], (
            "if this now finds a solution, the head_match non-str gap "
            "(todo/imported-non-atom-constant-head-args-unreachable-"
            "2026-09-05.md) has been fixed -- invert this assertion and "
            "close the todo"
        )


class TestCellAtomHeadReference:
    """Stage A (2026-09-06-atoms-as-cells-strings, Task 9): a NESTED head
    reference that resolves to a CELL atom ``("red",)`` builds a real match
    pattern, the same way a ``str`` atom resolution already does.

    Same driving shape as ``test_nested_non_atom_reference_unreachable_when_
    position_forced`` above: only a reference nested inside an already-lifted
    cell argument reaches ``head_match.head_to_match_pattern``'s
    ``LoadName``/``LoadAttr`` branch, and only dispatch forced through that
    argument's own position exercises the pattern it builds.  A cell atom
    cannot be baked in as a bare ``ast.MatchValue`` (a ``match`` value pattern
    takes literals and dotted attribute lookups only, never a tuple constant),
    so the branch emits the cell SEQUENCE pattern ``case ('red',)`` instead.
    """

    def _clauses_and_globals(self, binding_of):
        from clausal.terms import Call, LoadName

        colours = ("red", "green", "blue", "amber")
        clauses = []
        for i, colour in enumerate(colours, start=1):
            n_var, l_var = Var(), Var()
            wrap_call = Call(
                func=LoadName(name="wrap"),
                args=(LoadName(name=colour),),
                kwargs=(),
            )
            clauses.append(Clause(
                head=Compound("level", (n_var, l_var)),
                body=[
                    Unify(left=n_var, right=i),
                    Unify(left=l_var, right=wrap_call),
                ],
            ))
        globals_ = {c: binding_of(c) for c in colours}
        globals_["wrap"] = "wrap"
        return clauses, globals_

    def test_nested_cell_atom_reference_matches_when_position_forced(self):
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        # The Stage B binding shape for a declared atom: the arity-0 cell.
        clauses, globals_ = self._clauses_and_globals(lambda c: c)
        globals_[FUNCTOR_SIGNATURES_KEY] = {"wrap": ("x",)}
        fn = compile_predicate_trampoline(
            "level", 2, clauses, None, globals_=globals_)

        # Position 0 unbound: dispatch is forced through position 1's cell
        # bucket, so the nested-reference pattern is what decides the match.
        v = Var()
        results = _trampoline_solutions(fn, [v, ("wrap", "blue")])
        assert results == [(3, ("wrap", "blue"))]

        # A cell atom no clause carries still fails.
        v = Var()
        assert _trampoline_solutions(fn, [v, ("wrap", "teal")]) == []

    def test_nested_str_atom_reference_still_matches(self):
        """Stage A additivity: today's ``str`` atom binding keeps taking the
        ``MatchValue`` path and keeps matching a ``str`` runtime value."""
        from clausal.logic.cells import FUNCTOR_SIGNATURES_KEY

        clauses, globals_ = self._clauses_and_globals(lambda c: c)
        globals_[FUNCTOR_SIGNATURES_KEY] = {"wrap": ("x",)}
        fn = compile_predicate_trampoline(
            "level", 2, clauses, None, globals_=globals_)

        v = Var()
        results = _trampoline_solutions(fn, [v, ("wrap", "blue")])
        assert results == [(3, ("wrap", "blue"))]

        # ... and the CELL shape must NOT match a str-atom clause (Stage A
        # keeps ``("blue",)`` and ``"blue"`` distinct — spec §6.2).
        v = Var()
        assert _trampoline_solutions(fn, [v, ("wrap", ("blue",))]) == []
