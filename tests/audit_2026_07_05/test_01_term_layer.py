"""A01 term-layer & C unification — adversarial audit tests (2026-07-05).

Findings ledger: docs/superpowers/audits/2026-07-05-fable-partition/01-term-layer/findings.md

Suspected-bug tests assert the *correct* behaviour and are marked
``@pytest.mark.xfail(strict=False)`` with the finding ID; confirmed-correct
behaviour is a plain regression guard.  Run PER FILE only:

    python -m pytest tests/audit_2026_07_05/test_01_term_layer.py -v
"""
import gc
import subprocess
import sys
import textwrap
import threading
import weakref

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars
from clausal.logic.variables import (
    Trail,
    UnboundVarCoercionError,
    Var,
    deref,
    get_attr,
    is_var,
    occurs_check,
    put_attr,
    register_attr_hook,
    unify,
    unify_with_occurs_check,
    unregister_attr_hook,
    walk,
)
from clausal.logic.variables import _variables as _c
from clausal.terms import (
    Compound,
    ConcreteSeg,
    DictTerm,
    KWTerm,
    PartialTermError,
    Quantity,
    SegBytes,
    SegList,
    SegString,
    SetTerm,
    VarSeg,
    term_str,
)


@pytest.fixture
def trail():
    t = Trail()
    yield t
    t.reset()


def _fresh_pred_class(fields=("a", "b")):
    from clausal.logic.predicate import PredicateMeta
    return PredicateMeta("audit_pt", (), {"_fields": fields})


# ─────────────────────────────────────────────────────────────────────────────
# A01-F001 — occurs-check blind to Compound / KWTerm / PredicateMeta instances
# ─────────────────────────────────────────────────────────────────────────────

class TestF001OccursCheckBlindness:
    def test_occurs_check_sees_var_in_compound_args(self, trail):
        X = Var()
        assert occurs_check(X, Compound("f", (X,))) is True

    def test_uoc_rejects_cyclic_compound(self, trail):
        X = Var()
        assert unify_with_occurs_check(X, Compound("f", (X,)), trail) is False

    def test_occurs_check_sees_var_in_kwterm(self, trail):
        X = Var()
        assert occurs_check(X, KWTerm("r", a=X)) is True

    def test_occurs_check_sees_var_in_predicate_meta_instance(self, trail):
        X = Var()
        inst = _fresh_pred_class()(X, 2)
        assert occurs_check(X, inst) is True

    def test_control_traversed_containers(self, trail):
        X = Var()
        assert occurs_check(X, [1, X])
        assert occurs_check(X, (1, X))
        assert occurs_check(X, DictTerm({"k": X}))
        assert occurs_check(X, SegList([ConcreteSeg([X])]))
        assert occurs_check(X, SegString([VarSeg(X)]))
        Y = Var()
        assert unify(Y, [X], trail)
        assert occurs_check(X, Y)  # through a binding chain


# ─────────────────────────────────────────────────────────────────────────────
# A01-F003 — Compound Var-functor support broken across the layer
# ─────────────────────────────────────────────────────────────────────────────

class TestF003CompoundVarFunctor:
    # A01-F003 deref-only floor (parked decision A01-D004, options a/b): a
    # functor Var *bound* to a str behaves as that str across unify, copy_term,
    # _is_ground, _collect_vars and the render functions. The one output-mode
    # case (binding an *unbound* functor Var) stays xfail — it needs D004→(a).
    def test_bound_var_functor_unifies(self, trail):
        F = Var()
        assert unify(F, "f", trail)
        assert unify(Compound(F, (1,)), Compound("f", (1,)), trail) is True

    @pytest.mark.xfail(strict=False,
                       reason="A01-F003/D004: unbound functor var binding (output mode) "
                              "is out of scope for the deref-only floor; needs D004→(a)")
    def test_unbound_var_functor_binds(self, trail):
        F = Var()
        assert unify(Compound(F, (1,)), Compound("f", (1,)), trail) is True
        assert deref(F) == "f"

    def test_copy_term_freshens_functor_var(self):
        F, X = Var(), Var()
        copied = _c._copy_term_impl(Compound(F, (X,)), {})
        assert copied.args[0] is not X          # args are freshened (control)
        assert copied.functor is not F          # functor should be too

    def test_is_ground_derefs_functor(self, trail):
        F = Var()
        assert unify(F, "f", trail)
        assert _c._is_ground(Compound(F, (1,))) is True

    def test_collect_vars_sees_functor_var(self):
        F = Var()
        out = []
        _c._collect_vars_impl(Compound(F, (1,)), out)
        assert F in out

    def test_term_str_derefs_bound_functor(self, trail):
        F = Var()
        assert unify(F, "f", trail)
        assert term_str(Compound(F, (1,))) == "f(1)"

    def test_term_html_derefs_bound_functor(self, trail):
        from clausal.terms import term_html
        F = Var()
        assert unify(F, "f", trail)
        assert ">f<" in term_html(Compound(F, (1,)))
        assert ">_<" not in term_html(Compound(F, (1,)))

    def test_term_pformat_derefs_bound_functor(self, trail):
        from clausal.terms import term_pformat
        F = Var()
        assert unify(F, "f", trail)
        # force the multi-line expansion path (narrow width) so the functor is
        # rendered by term_pformat's own Compound arm, not term_str's flat form
        out = term_pformat(Compound(F, (1, 2, 3)), width=4)
        assert out.startswith("f(")

    def test_control_str_functor_semantics(self, trail):
        assert unify(Compound("f", ()), Compound("f", ()), trail)
        assert not unify(Compound("f", (1,)), Compound("g", (1,)), trail)
        assert not unify(Compound("f", (1,)), Compound("f", (1, 2)), trail)
        X = Var()
        assert unify(Compound("f", (X, 2)), Compound("f", (1, 2)), trail)
        assert deref(X) == 1


# ─────────────────────────────────────────────────────────────────────────────
# A01-F004 — KWTerm has no __unify__: Var-valued fields never bind
# ─────────────────────────────────────────────────────────────────────────────

class TestF004KWTermUnify:
    def test_kwterm_var_field_binds(self, trail):
        Y = Var()
        assert unify(KWTerm("r", a=Y, b=2), KWTerm("r", a=1, b=2), trail) is True
        assert deref(Y) == 1

    def test_control_ground_kwterm(self, trail):
        assert unify(KWTerm("r", a=1), KWTerm("r", a=1), trail)
        assert not unify(KWTerm("r", a=1), KWTerm("r", a=2), trail)
        assert not unify(KWTerm("r", a=1), KWTerm("s", a=1), trail)
        # keyword-order independence (documented)
        assert KWTerm("r", a=1, b=2) == KWTerm("r", b=2, a=1)

    def test_kwterm_reserved_position_and_mutators(self):
        k = KWTerm("r", a=1, _position=(1, 2, 3, 4))
        assert list(k.keys()) == ["a"] and k._position == (1, 2, 3, 4)
        with pytest.raises(KeyError):
            k.with_overrides(zzz=1)
        with pytest.raises(KeyError):
            k.with_extensions(a=2)


# ─────────────────────────────────────────────────────────────────────────────
# A01-F005 — Seg* _unify_gens retention pins dead Trails (memory)
# ─────────────────────────────────────────────────────────────────────────────

class TestF005UnifyGensRetention:
    def test_dead_trails_are_collectable(self):
        sl = SegList([VarSeg(Var()), VarSeg(Var())])
        refs = []
        for _ in range(20):
            t = Trail()
            m = t.mark()
            unify(sl, [1, 2, 3], t)   # first split only — generator suspended
            t.undo(m)
            refs.append(weakref.ref(t))
            del t
        gc.collect()
        alive = sum(1 for r in refs if r() is not None)
        assert alive == 0, f"{alive}/20 dead trails pinned by _unify_gens"
        # Bounded LRU (A01-F005 follow-up): never more than the LRU capacity.
        assert len(sl._unify_gens) <= 8

    def test_control_exhausted_generator_is_dropped(self):
        sl = SegList([VarSeg(Var())])
        t = Trail()
        m = t.mark()
        n = 0
        while unify(sl, [1], t):
            n += 1
            t.undo(m)
            assert n < 10
        assert n == 1
        assert len(sl._unify_gens) == 0

    def test_interleaved_drives_do_not_evict_each_other(self):
        # A01-F005 follow-up: the clear-all eviction meant two interleaved
        # drives of the same Seg* term against different targets evicted each
        # other — every resume restarted from split 1 and the outer drive
        # never exhausted (livelock).  With the LRU both drives stay live.
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), VarSeg(B)])
        t1, t2 = Trail(), Trail()
        m1 = t1.mark()
        outer_splits = []
        inner_splits = []
        n = 0
        while unify(sl, [1, 2], t1):
            n += 1
            assert n <= 3, (
                "outer drive livelocked: splits repeat forever because the "
                "interleaved drive evicted its generator")
            outer_splits.append((deref(A), deref(B)))
            t1.undo(m1)
            # Interleave one step of a drive against a DIFFERENT target.
            m2 = t2.mark()
            if unify(sl, [7, 8, 9], t2):
                inner_splits.append((deref(A), deref(B)))
                t2.undo(m2)
        assert outer_splits == [([], [1, 2]), ([1], [2]), ([1, 2], [])]
        # Finish the interleaved drive: it must resume where it left off and
        # enumerate the remaining splits of [7, 8, 9].
        m2 = t2.mark()
        k = 0
        while unify(sl, [7, 8, 9], t2):
            k += 1
            assert k <= 4, "inner drive livelocked after outer exhausted"
            inner_splits.append((deref(A), deref(B)))
            t2.undo(m2)
        assert inner_splits == [
            ([], [7, 8, 9]), ([7], [8, 9]), ([7, 8], [9]), ([7, 8, 9], []),
        ]

    def test_lru_eviction_bounds_cache_and_closes_generators(self):
        # Drive many distinct (target, trail) pairs one step each: the cache
        # must stay bounded at the LRU capacity (evicted generators closed).
        sl = SegList([VarSeg(Var()), VarSeg(Var())])
        t = Trail()
        for i in range(30):
            m = t.mark()
            assert unify(sl, [i, i + 1, i + 2], t)
            t.undo(m)
        assert len(sl._unify_gens) <= 8


# ─────────────────────────────────────────────────────────────────────────────
# A01-F006 — SegList "ground" unify path uses == : element Vars never bind
# ─────────────────────────────────────────────────────────────────────────────

class TestF006SegListElementVarGroundPath:
    def test_element_var_binds_direct(self, trail):
        E = Var()
        assert unify(SegList([ConcreteSeg([E, 2])]), [1, 2], trail) is True
        assert deref(E) == 1

    def test_element_var_binds_after_varseg_bound(self, trail):
        A, E = Var(), Var()
        sl = SegList([VarSeg(A), ConcreteSeg([E])])
        assert unify(A, [1], trail)
        assert unify(sl, [1, 2], trail) is True
        assert deref(E) == 2

    def test_is_ground_false_with_element_var(self):
        E = Var()
        assert SegList([ConcreteSeg([E, 2])]).is_ground() is False

    def test_control_unbound_varseg_path_binds_elements(self, trail):
        B, E = Var(), Var()
        assert unify(SegList([VarSeg(B), ConcreteSeg([E])]), [1, 2], trail)
        assert deref(B) == [1] and deref(E) == 2


# ─────────────────────────────────────────────────────────────────────────────
# A01-F007 — SegList.__unify__ has no bytes-target arm (codes-model asymmetry)
# ─────────────────────────────────────────────────────────────────────────────

class TestF007SegListVsBytes:
    def test_seglist_of_codes_unifies_with_bytes(self, trail):
        A = Var()
        assert unify(SegList([ConcreteSeg([71]), VarSeg(A)]), b"GET", trail) is True

    def test_control_code_list_and_segbytes(self, trail):
        B = Var()
        assert unify([71, B], b"GE", trail) and deref(B) == 69
        trail.reset()
        V = Var()
        assert unify(SegBytes([b"GE", VarSeg(V)]), b"GET", trail)
        assert deref(V) == b"T"
        trail.reset()
        W = Var()
        assert unify(SegBytes([VarSeg(W)]), [71, 69, 84], trail)
        assert deref(W) == [71, 69, 84]


# ─────────────────────────────────────────────────────────────────────────────
# A01-F008 — C walk() blind to Compound/KWTerm/PredicateMeta instances
# ─────────────────────────────────────────────────────────────────────────────

class TestF008WalkFunctorTerms:
    def test_walk_snapshot_of_compound_survives_undo(self, trail):
        X = Var()
        assert unify(X, 1, trail)
        snap = walk(Compound("f", (X,)))
        trail.reset()
        assert deref(snap.args[0]) == 1  # snapshot must not decay to unbound

    def test_walk_snapshot_of_kwterm_survives_undo(self, trail):
        X = Var()
        assert unify(X, 1, trail)
        snap = walk(KWTerm("r", a=X, b=2))
        trail.reset()
        assert deref(snap.a) == 1
        assert snap.functor == "r" and snap.b == 2

    def test_walk_snapshot_of_term_instance_survives_undo(self, trail):
        X = Var()
        assert unify(X, 1, trail)
        # P2: a plain class CONSTRUCTS A CELL now, so a live INSTANCE --
        # which is what this test is about, and which the bridge still
        # produces (reflection, clpb, term expansion) -- has to be minted
        # with the bridge flag.  Without it this was testing the cell path
        # under a name that says instance.
        cls = _fresh_pred_class()
        cls._clausal_instances = True
        inst = cls(X, 2)
        snap = walk(inst)
        trail.reset()
        assert deref(snap.a) == 1 and snap.b == 2

    def test_walk_preserves_compound_position(self, trail):
        X = Var()
        assert unify(X, 1, trail)
        snap = walk(Compound("f", (X,), _position=(1, 2, 3, 4)))
        assert snap._position == (1, 2, 3, 4)  # Slice G metadata not dropped

    def test_walk_shares_unbound_vars(self, trail):
        X = Var()  # unbound
        snap = walk(Compound("f", (X,)))
        assert snap.args[0] is X  # unbound Vars left in place, not copied

    def test_control_walk_rebuilds_list_tuple_and_segs(self, trail):
        X = Var()
        assert unify(X, 1, trail)
        wl, wt = walk([X]), walk((X,))
        A = Var()
        assert unify(A, chars("i!"), trail)
        # THE FLIP: a char list holds CHAR ATOMS; ``["h"]`` is a list of one
        # one-character STRING and would not promote.
        ws = walk(SegList([ConcreteSeg([char_atom("h")]), VarSeg(A)]))
        trail.reset()
        assert wl == [1] and wt == (1,)
        assert ws == chars("hi!")  # F018 Liskov promotion (prior art regression guard)


# ─────────────────────────────────────────────────────────────────────────────
# A01-F009 — SegString VarSeg bound to a non-str scalar: silent failure
# ─────────────────────────────────────────────────────────────────────────────

class TestF009SegStringScalarBinding:
    def test_scalar_varseg_binding_raises_partial_term_error(self, trail):
        Z = Var()
        assert unify(Z, 5, trail)
        ss = SegString(["a", VarSeg(Z)])
        with pytest.raises(PartialTermError):
            ss.__walk__()

    def test_control_charlist_binding_guard(self, trail):
        Z = Var()
        assert unify(Z, ["x", 5], trail)  # non-char list → F024 typed error
        ss = SegString(["a", VarSeg(Z)])
        with pytest.raises(PartialTermError):
            ss.__walk__()

    def test_control_construction_guard(self):
        with pytest.raises(PartialTermError):
            SegString(["a", 5])
        with pytest.raises(PartialTermError):
            SegBytes([b"a", "not-bytes"])


# ─────────────────────────────────────────────────────────────────────────────
# A01-F010 — Seg* __getitem__ slice within concrete prefix raises
# ─────────────────────────────────────────────────────────────────────────────

class TestF010SliceWithinPrefix:
    def test_segstring_slice_in_prefix(self):
        B = Var()
        ss = SegString(["abc", VarSeg(B)])
        assert ss[0:2] == chars("ab")   # stage 2: a slice of text is TEXT (the carrier)

    def test_seglist_slice_in_prefix(self):
        B = Var()
        sl = SegList([ConcreteSeg([1, 2, 3]), VarSeg(B)])
        assert sl[0:2] == [1, 2]

    def test_segbytes_slice_in_prefix(self):
        B = Var()
        sb = SegBytes([b"abc", VarSeg(B)])
        assert sb[0:2] == b"ab"

    def test_control_int_index_semantics(self):
        B = Var()
        ss = SegString(["abc", VarSeg(B)])
        assert ss[1] == mint("b")
        with pytest.raises(PartialTermError):
            ss[5]  # beyond knowable prefix

    def test_control_out_of_prefix_slice_still_raises(self):
        B = Var()
        ss = SegString(["abc", VarSeg(B)])
        with pytest.raises(PartialTermError):
            ss[0:5]        # stop past prefix depends on the VarSeg
        with pytest.raises(PartialTermError):
            ss[2:]         # open-ended depends on the VarSeg
        with pytest.raises(PartialTermError):
            ss[-1:2]       # negative start depends on total length


# ─────────────────────────────────────────────────────────────────────────────
# A01-F011 — terms.__all__ omissions (doc-drift)
# ─────────────────────────────────────────────────────────────────────────────

class TestF011AllExports:
    def test_public_term_types_exported(self):
        import clausal.terms as terms_mod
        for name in ("SegList", "ConcreteSeg", "VarSeg", "Quantity",
                     "UnitsMismatch", "PartialTermError"):
            assert name in terms_mod.__all__, name


# ─────────────────────────────────────────────────────────────────────────────
# Prior-art regression guards + D001/D002 characterization
# ─────────────────────────────────────────────────────────────────────────────

class TestPriorArtAndCharacterization:
    def test_f015_drive_pattern_enumerates_all_splits(self):
        """Prior art F015: mark/unify/undo drive yields every split."""
        A, B = Var(), Var()
        sl = SegList([VarSeg(A), VarSeg(B)])
        t = Trail()
        m = t.mark()
        splits = []
        while unify(sl, [1, 2, 3], t):
            splits.append((deref(A), deref(B)))
            t.undo(m)
        assert splits == [([], [1, 2, 3]), ([1], [2, 3]), ([1, 2], [3]), ([1, 2, 3], [])]

    def test_f030_seg_vs_seg_nonground_still_unsupported(self, trail):
        """Prior art F030 (deferred): non-ground Seg* vs Seg* unification."""
        A, B = Var(), Var()
        assert unify(SegList([VarSeg(A)]), SegList([VarSeg(B)]), trail) is False
        assert unify(SegString([VarSeg(Var())]), SegString([VarSeg(Var())]), trail) is False

    def test_d001_cross_type_numeric_unification_characterization(self, trail):
        """A01-D001 (design question): unify falls back to Python ==."""
        import decimal
        import fractions
        assert unify(1, True, trail)
        assert unify(1, 1.0, trail)
        assert unify(0, False, trail)
        assert unify(decimal.Decimal(1), 1, trail)
        assert unify(fractions.Fraction(1, 2), 0.5, trail)
        assert not unify(1, "1", trail)

    def test_d002_quantity_dimensionless_characterization(self, trail):
        """A01-D002 (design question): eq/unify strict, comparisons lenient."""
        q = Quantity(5, {})
        assert (q == 5) is False
        assert q <= 5 and q >= 5
        assert unify(q, 5, trail) is False
        # dimensioned behaviour is coherent
        from clausal.terms import UnitsMismatch
        q1 = Quantity(5, {"m": 1})
        with pytest.raises(UnitsMismatch):
            q1 + 3
        assert unify(q1, Quantity(5, {"m": 1}), trail)
        assert not unify(q1, Quantity(5, {"s": 1}), trail)


# ─────────────────────────────────────────────────────────────────────────────
# Core regression guards: trail, hooks, modes, structure
# ─────────────────────────────────────────────────────────────────────────────

class TestTrailSemantics:
    def test_mark_undo_reset_and_past_mark(self, trail):
        X = Var()
        m = trail.mark()
        assert unify(X, 1, trail)
        trail.undo(m)
        assert not X.is_bound
        trail.undo(999)  # already past — silently skipped
        with pytest.raises(ValueError):
            trail.undo(-1)

    def test_record_callback_fires_on_undo(self, trail):
        called = []
        trail.record(lambda: called.append(1))
        trail.reset()
        assert called == [1]
        with pytest.raises(TypeError):
            trail.record(42)

    def test_cross_thread_mutation_rejected(self):
        t = Trail()
        results = []

        def other():
            try:
                unify(Var(), 1, t)
                results.append("unify-ok")
            except RuntimeError:
                results.append("unify-rejected")
            try:
                t.undo(0)
                results.append("undo-ok")
            except RuntimeError:
                results.append("undo-rejected")

        th = threading.Thread(target=other)
        th.start()
        th.join()
        assert results == ["unify-rejected", "undo-rejected"]

    def test_partial_failure_rolls_back(self, trail):
        X, Y = Var(), Var()
        assert unify([X, Y, 3], [1, 2, 4], trail) is False
        assert not X.is_bound and not Y.is_bound

    def test_unify_wrong_trail_type(self):
        with pytest.raises(TypeError):
            unify(1, 2, "not a trail")


class TestAttrHooks:
    def test_wake_backtrack_and_reject(self, trail):
        seen = []
        register_attr_hook("a01k", lambda av, bt, tr: (seen.append(bt), True)[1])
        try:
            A = Var()
            put_attr(A, "a01k", "cdata", trail)
            assert get_attr(A, "a01k") == "cdata"
            m = trail.mark()
            assert unify(A, 42, trail)
            assert seen == [42]
            trail.undo(m)
            assert not A.is_bound and get_attr(A, "a01k") == "cdata"

            register_attr_hook("a01k", lambda av, bt, tr: False)
            assert unify(A, 43, trail) is False
            assert not A.is_bound  # rejection rolled back
        finally:
            unregister_attr_hook("a01k")
        trail.reset()
        assert get_attr(A, "a01k") is None  # put_attr undone

    def test_hookless_attr_unification_characterization(self, trail):
        """A01-D003 (resolved-from-docs): semantics entirely left to hooks —
        binding an attributed var with no registered hook succeeds silently."""
        Z = Var()
        put_attr(Z, "a01_nohook", "constraint", trail)
        assert unify(Z, 42, trail) is True


class TestUnifyModes:
    def test_str_char_atom_list_unifies_all_modes(self, trail):
        """THE FLIP (spec §6.2): a string IS the list of its CHAR ATOMS, so
        the str~list arm is back — INVERTING the P3-1 Task 5 retirement this
        test pinned. What stays false is the pre-flip 1-char-``str`` reading:
        ``"a"`` is a one-element STRING, not a char, so it never unifies
        with the char atom.
        """
        # Stage 2: a bare ``str`` is an ATOM; the STRING is ``chars(...)``.
        H, T = Var(), Var()
        assert unify(chars("ab"), [H, T], trail)
        assert deref(H) == char_atom("a") and deref(T) == char_atom("b")
        trail.reset()
        assert unify(chars(""), [], trail) and unify([], chars(""), trail)
        assert unify(chars("a"), [char_atom("a")], trail)
        assert not unify(chars("a"), [chars("a")], trail)     # "a" is a STRING, not a char
        assert not unify([mint("ab")], chars("ab"), trail)   # 'ab' is 2 chars
        assert not unify(chars("ab"), [char_atom("a")], trail)

    def test_bytes_list_codes_all_modes(self, trail):
        H = Var()
        assert unify(b"GE", [H, 69], trail) and deref(H) == 71
        trail.reset()
        assert unify(b"", [], trail)
        assert not unify(b"a", ["a"], trail)    # codes model: int, not char

    def test_seg_nested_inlining_and_min_len(self, trail):
        A, B = Var(), Var()
        inner = SegList([ConcreteSeg([2]), VarSeg(B)])
        outer = SegList([ConcreteSeg([1]), VarSeg(A)])
        assert unify(A, inner, trail)
        assert unify(outer, [1, 2, 3], trail)
        assert deref(B) == [3]
        trail.reset()
        X = Var()
        ss = SegString(["abc", VarSeg(X)])
        assert not unify(ss, chars("ab"), trail)       # shorter than min_len
        assert unify(ss, chars("abc"), trail) and deref(X) == chars("")

    def test_dictterm_both_orders_and_mismatch(self, trail):
        V1, V2 = Var(), Var()
        assert unify(DictTerm({"a": V1}), {"a": 1}, trail) and deref(V1) == 1
        assert unify({"a": 1}, DictTerm({"a": V2}), trail) and deref(V2) == 1
        assert not unify(DictTerm({"a": 1}), {"b": 1}, trail)
        assert not unify(DictTerm({"a": 1}), {"a": 1, "b": 2}, trail)

    def test_setterm_ground_contract(self, trail):
        assert unify(SetTerm({1, 2}), {1, 2}, trail)
        assert not unify(SetTerm({1}), {1, 2}, trail)

    def test_unify_hook_exception_propagates_and_rolls_back(self, trail):
        class Boom:
            def __unify__(self, other, tr):
                raise ValueError("boom")
        X = Var()
        with pytest.raises(ValueError):
            unify([X, Boom()], [1, Boom()], trail)
        assert not X.is_bound

    def test_var_coercion_and_chains(self, trail):
        X = Var()
        with pytest.raises(UnboundVarCoercionError):
            int(X)
        chain = [Var() for _ in range(2000)]
        for a, b in zip(chain, chain[1:]):
            assert unify(a, b, trail)
        assert unify(chain[-1], 7, trail)
        assert deref(chain[0]) == 7 and int(chain[0]) == 7 and is_var(chain[0]) is False


class TestDepthAndCycles:
    def test_max_depth_recursion_error_is_clean(self):
        """Nesting past MAX_DEPTH raises RecursionError — no crash (subprocess)."""
        code = textwrap.dedent("""
            from clausal.logic.variables import Trail, unify
            l1, l2 = 0, 0
            for _ in range(51000):
                l1 = [l1]; l2 = [l2]
            t = Trail()
            try:
                unify(l1, l2, t)
                print("NO-ERROR")
            except RecursionError:
                print("CLEAN")
        """)
        p = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=180, env={"PYTHONPATH": "/workspace/clausal-bug-fix"},
        )
        assert p.returncode == 0 and p.stdout.strip() == "CLEAN"

    def test_cyclic_unify_raises_cleanly(self):
        code = textwrap.dedent("""
            from clausal.logic.variables import Trail, unify
            t = Trail()
            l1 = [1]; l1.append(l1)
            l2 = [1]; l2.append(l2)
            try:
                unify(l1, l2, t)
                print("NO-ERROR")
            except RecursionError:
                print("CLEAN")
        """)
        p = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True,
            timeout=180, env={"PYTHONPATH": "/workspace/clausal-bug-fix"},
        )
        assert p.returncode == 0 and p.stdout.strip() == "CLEAN"


# ─────────────────────────────────────────────────────────────────────────────
# C-toolkit leak checks (spec §C-finding verification toolkit)
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaks:
    def test_unify_backtrack_loop_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            X, Y = Var(), Var()
            m = t.mark()
            unify([X, "b"], ["a", Y], t)
            t.undo(m)
        refcount_stable(thunk, iterations=2000)

    def test_str_list_loop_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            X = Var()
            m = t.mark()
            unify("abc", ["a", X, "c"], t)
            t.undo(m)
        refcount_stable(thunk, iterations=2000)

    def test_compound_unify_loop_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            X = Var()
            m = t.mark()
            unify(Compound("f", (X, 2)), Compound("f", (1, 2)), t)
            t.undo(m)
        refcount_stable(thunk, iterations=2000)

    def test_put_attr_wake_loop_stable(self, refcount_stable):
        def thunk():
            t = Trail()
            X = Var()
            put_attr(X, "a01leak", [1, 2], t)
            m = t.mark()
            unify(X, 5, t)
            t.undo(m)
            t.reset()
        refcount_stable(thunk, iterations=2000)

    def test_bound_value_refcount_stable(self, getrefcount_stable):
        val = ["shared", "value"]
        t = Trail()

        def exercise():
            X = Var()
            m = t.mark()
            unify(X, val, t)
            t.undo(m)
        getrefcount_stable(val, exercise, iterations=2000)

    def test_trail_refcount_stable(self, getrefcount_stable):
        t = Trail()

        def exercise():
            X = Var()
            m = t.mark()
            unify(X, 1, t)
            t.undo(m)
        getrefcount_stable(t, exercise, iterations=2000)
