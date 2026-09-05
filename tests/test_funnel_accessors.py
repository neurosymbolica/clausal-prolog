"""Tests for the Phase 1 funnel accessors (task 1: fill the gaps).

Covers the four new accessors added to close gaps in the term-probe funnel:

  - ``predicate.term_field_names_of_class`` — class-level twin of
    ``term_field_names`` (models ``head_match.py``'s ``_resolved_field_names``,
    but lives here as the canonical version).
  - ``_helpers.functor_arity`` — single-traversal ``(functor, arity)`` for
    term shapes, replacing a ``_functor_name`` + ``_arity`` double walk.
  - ``predicate.term_field_values`` / ``predicate.term_field_dict`` — the
    reconstruct-pattern helpers (values tuple / name->value dict).

Also regression-covers the ``is_atom`` adoption at the four hand-rolled
``isinstance(x, PredicateMeta) and not x._fields`` sites inside
``_helpers.py`` (``_functor_name_py``, ``_arity_py``, ``_is_ground_py``,
``_standard_order_key``) — those sites must keep behaving exactly as before
now that they route through ``is_atom``.

Phase 2 bridge Task 1 (see ``docs/superpowers/plans/2026-09-03-phase2-bridge.md``)
adds two more sections at the bottom of this file:

  - ``TestPlainTupleAccessorRegression`` — pins TODAY's behavior of
    ``_functor_name``/``_arity``/``_nth_arg``/``_args_list``/``_is_compound``/
    ``functor_arity`` on plain (non-cell-shaped) tuples, i.e. a tuple whose
    slot 0 is not a str/``tuple``-type/Var. These accessors had NO tuple
    branch at all before the cell-awareness addition (verified against both
    the C extension and the ``_..._py`` fallbacks), so "today's behavior" is
    simply: ``_functor_name`` -> None, ``_arity`` -> None, ``_nth_arg`` ->
    raises IndexError, ``_args_list`` -> ``[]``, ``_is_compound`` -> False,
    ``functor_arity`` -> None. This class must stay green whether or not the
    cell branch exists — it is the "no regression on the default path"
    evidence for that branch.
  - ``TestCellFunnelAwareness`` — the additive cell branch itself (str
    functor, ``TUPLE_TAG`` tuple-data, and unbound-Var-functor cells).
"""

from __future__ import annotations

import dataclasses

import pytest

from clausal.logic.predicate import (
    PredicateMeta,
    is_atom,
    is_term_instance,
    make_atom,
    make_predicate,
    term_field_dict,
    term_field_names,
    term_field_names_of_class,
    term_field_values,
)
from clausal.logic.builtins._helpers import (
    _arity,
    _args_list,
    _functor_name,
    _is_compound,
    _is_ground,
    _nth_arg,
    _standard_order_key,
    functor_arity,
)
from clausal.logic.cells import TUPLE_TAG, make_cell, make_tuple_cell
from clausal.logic.variables import Var, deref, is_var
from clausal.terms import Compound, KWTerm
from clausal.pythonic_ast.nodes import Add


# ── Corpus ─────────────────────────────────────────────────────────────────

# A PredicateMeta term whose declared field order is NOT alphabetical, so a
# naive "sort the fields" implementation would silently pass while an
# order-sensitive one would not.
bar = make_predicate("bar", ["b", "a"])
foo_atom = make_atom("foo")


class NotADataclass:
    """A plain object: not a PredicateMeta instance, not a dataclass."""

    def __init__(self):
        self.x = 1


# ── term_field_names_of_class ────────────────────────────────────────────────


class TestTermFieldNamesOfClass:
    def test_predicate_meta_class_preserves_declared_order(self):
        # nv
        assert term_field_names_of_class(bar) == ("b", "a")

    def test_predicate_meta_atom_class_is_empty_tuple(self):
        # nv
        assert term_field_names_of_class(foo_atom) == ()

    def test_dataclass_class_matches_instance_field_set(self):
        # nv — must be the SAME set term_field_names yields for an instance,
        # nothing excluded (position included, despite compare=False).
        instance_names = term_field_names(Add(left=1, right=2))
        assert term_field_names_of_class(Add) == instance_names
        assert term_field_names_of_class(Add) == ("position", "left", "right")

    def test_plain_class_is_none(self):
        # nv
        assert term_field_names_of_class(NotADataclass) is None

    def test_non_class_value_is_none(self):
        # nv — an instance, not a class, is not a valid input shape
        assert term_field_names_of_class(bar(b=1, a=2)) is None
        assert term_field_names_of_class(42) is None
        assert term_field_names_of_class(None) is None


# ── term_field_values / term_field_dict ──────────────────────────────────────


class TestTermFieldValues:
    def test_predicate_meta_instance_order_matches_declared_fields(self):
        # nv
        t = bar(b=1, a=2)
        assert term_field_values(t) == (1, 2)  # (b, a) order, not alphabetical

    def test_dataclass_instance(self):
        # nv
        node = Add(left=10, right=20)
        assert term_field_values(node) == (None, 10, 20)  # (position, left, right)

    def test_non_term_instance_raises_type_error(self):
        # nv — mirrors term_field_names's own TypeError contract
        with pytest.raises(TypeError):
            term_field_values(NotADataclass())
        with pytest.raises(TypeError):
            term_field_values(42)


class TestTermFieldDict:
    def test_predicate_meta_instance(self):
        # nv
        t = bar(b=1, a=2)
        assert term_field_dict(t) == {"b": 1, "a": 2}

    def test_dataclass_instance(self):
        # nv
        node = Add(left=10, right=20)
        assert term_field_dict(node) == {"position": None, "left": 10, "right": 20}

    def test_non_term_instance_raises_type_error(self):
        # nv
        with pytest.raises(TypeError):
            term_field_dict(NotADataclass())


# ── functor_arity ─────────────────────────────────────────────────────────────


class TestFunctorArity:
    def test_compound_with_str_functor(self):
        # nv
        c = Compound("foo", (1, 2, 3))
        assert functor_arity(c) == ("foo", 3)

    def test_compound_with_var_functor_is_none(self):
        # nv — documented divergence from the composed accessors: a
        # non-str functor makes the WHOLE pair unresolvable, whereas
        # _functor_name/_arity composed would give (None, 2). functor_arity
        # only promises a result for well-formed (str-functor) compounds.
        c = Compound(Var(), (1, 2))
        assert functor_arity(c) is None
        assert (_functor_name(c), _arity(c)) == (None, 2)

    def test_predicate_meta_term_instance(self):
        # nv
        t = bar(b=1, a=2)
        assert functor_arity(t) == ("bar", 2)

    def test_predicate_meta_atom_class(self):
        # nv — the atom class IS its own functor value (like a number is
        # its own functor name), not its __name__ string.
        assert functor_arity(foo_atom) == (foo_atom, 0)

    def test_dataclass_node_instance(self):
        # nv
        node = Add(left=1, right=2)
        assert functor_arity(node) == ("Add", 3)  # (position, left, right)

    def test_kwterm_is_none(self):
        # nv — out of functor_arity's declared domain (term instances,
        # Compound, PredicateMeta atom classes only); KWTerm is a distinct
        # shape and is not funneled here.
        k = KWTerm("r", a=1, b=2)
        assert functor_arity(k) is None

    def test_non_term_values_are_none(self):
        # nv
        assert functor_arity([1, 2]) is None
        assert functor_arity(42) is None
        assert functor_arity(None) is None

    def test_str_is_atom_value(self):
        # P3-1 Task 1 (R2, str-as-atom acceptance): a plain str is now an
        # atom VALUE for functor_arity — it IS its own functor, arity 0 —
        # same shape as test_predicate_meta_atom_class above. This inverts
        # the pre-P3-1 "strings are out of functor_arity's domain" behavior
        # (formerly asserted here as ``functor_arity("abc") is None``);
        # see ``clausal/logic/predicate.py::is_atom_value``.
        assert functor_arity("abc") == ("abc", 0)
        assert functor_arity("") == ("", 0)

    @pytest.mark.parametrize(
        "term",
        [
            Compound("foo", ()),
            Compound("bar", (1, 2, 3)),
            bar(b=1, a=2),
            foo_atom,
            Add(left=1, right=2),
            make_atom("baz"),
            make_predicate("qux", ["x", "y", "z"])(x=1, y=2, z=3),
        ],
        ids=[
            "compound-nullary",
            "compound-3ary",
            "predicate-meta-instance",
            "predicate-meta-atom-1",
            "dataclass-node",
            "predicate-meta-atom-2",
            "predicate-meta-instance-3ary",
        ],
    )
    def test_agrees_with_composed_functor_name_and_arity(self, term):
        # nv — functor_arity must be a single-traversal equivalent of the
        # two-call composition, over the shapes it declares as its domain.
        assert functor_arity(term) == (_functor_name(term), _arity(term))


# ── is_atom adoption regression (the four migrated _helpers.py sites) ────────


class TestIsAtomAdoptionRegression:
    """The four hand-rolled ``isinstance(x, PredicateMeta) and not x._fields``
    sites in ``_helpers.py`` now route through ``is_atom``. Behavior at each
    call site must be unchanged.
    """

    def test_functor_name_of_atom_class_is_itself(self):
        # nv — _functor_name_py line ~54
        assert _functor_name(foo_atom) is foo_atom
        assert is_atom(foo_atom)

    def test_arity_of_atom_class_is_zero(self):
        # nv — _arity_py line ~79
        assert _arity(foo_atom) == 0

    def test_is_ground_of_atom_class_is_true(self):
        # nv — _is_ground_py line ~172 (checked isinstance(term, type) AND
        # isinstance(term, PredicateMeta) AND not term._fields; is_atom
        # covers the same shape since PredicateMeta instances are classes)
        assert _is_ground(foo_atom) is True

    def test_is_ground_of_nonatom_class_is_not_short_circuited_true(self):
        # nv — a PredicateMeta class WITH fields is not an atom, and is not
        # itself ground-checkable the same way (it's a class, not a term
        # instance); confirms the is_atom guard doesn't over-match.
        assert is_atom(bar) is False

    def test_standard_order_key_of_atom_class(self):
        # nv — _standard_order_key line ~368.  P3-1 Task 4 (standard-order
        # collapse, §1b/R2): the trailing 0/1 discriminator that used to
        # break str-vs-same-spelled-class ties is gone — a class atom keys
        # IDENTICALLY to the same-spelled str now, since post-pivot they are
        # the same atom.
        key = _standard_order_key(foo_atom)
        assert key == (2, "foo")  # (_ORD_ATOM, name)

    def test_standard_order_key_atom_sorts_adjacent_to_same_named_str(self):
        # nv — atoms and same-named strings interleave in standard order
        items = [foo_atom, "foo"]
        from clausal.logic.builtins._helpers import _standard_order_sorted

        result = _standard_order_sorted(items)
        assert result == ["foo", foo_atom] or result == [foo_atom, "foo"]
        # both orderings are stable/valid — assert it did not raise and
        # both elements are present
        assert set(id(x) for x in result) == {id(foo_atom), id("foo")}


# ── Task 2 migration regression (sites with no existing direct coverage) ─────


class TestMigrationRegression:
    """Task 2 (batch A migration) regression tests for sites the existing
    suite did not directly exercise at the migrated line. Everything else in
    the batch A file list (type_checks.py, chars.py, io.py, keyword_ops.py,
    _lower_goalop_shared.py, terms_to_ast.py, database.py's
    ``_normalize_structural_head_args``) is already covered by an existing
    focused suite — see task-2-report.md for the per-file mapping.
    """

    def test_list_dispatch_rebuilds_term_instance_head_at_pos(self):
        # nv — list_dispatch.py ~170
        from clausal.logic.compiler.list_dispatch import _lift_clause_at_pos
        from clausal.logic.database import Clause
        from clausal.terms import Unify

        pt = make_predicate("pt", ("a", "b"))
        v = Var()
        head = pt(a=v, b=99)
        clause = Clause(head=head, body=[Unify(left=v, right=[1, 2, 3])])

        lifted = _lift_clause_at_pos(clause, 0)

        assert lifted.head.a == [1, 2, 3]  # lifted field
        assert lifted.head.b == 99  # untouched field preserved via term_field_dict
        assert lifted.body == []  # matched Unify removed from body

    def test_term_expansion_instance_head_matching_functor_and_arity_detected(self):
        # nv — term_expansion.py ~40
        from types import SimpleNamespace
        from clausal.logic.term_expansion import _is_term_expansion_clause

        te = make_predicate("TermExpansion", ("a", "b", "c", "d"))
        head = te(a=1, b=2, c=3, d=4)
        pred_node = SimpleNamespace(head=head)
        assert _is_term_expansion_clause(pred_node)

    def test_term_expansion_instance_head_wrong_name_not_detected(self):
        # nv
        from types import SimpleNamespace
        from clausal.logic.term_expansion import _is_term_expansion_clause

        other = make_predicate("NotTermExpansion", ("a", "b", "c", "d"))
        head = other(a=1, b=2, c=3, d=4)
        pred_node = SimpleNamespace(head=head)
        assert not _is_term_expansion_clause(pred_node)

    def test_term_expansion_instance_head_wrong_arity_not_detected(self):
        # nv
        from types import SimpleNamespace
        from clausal.logic.term_expansion import _is_term_expansion_clause

        te3 = make_predicate("TermExpansion", ("a", "b", "c"))
        head = te3(a=1, b=2, c=3)
        pred_node = SimpleNamespace(head=head)
        assert not _is_term_expansion_clause(pred_node)


# ── Task 3 migration regression (batch B: compiler walkers, reflection, repl) ─


class TestMigrationRegressionBatchB:
    """Task 3 (batch B migration) regression tests for sites the existing
    suite did not directly exercise at the migrated line, plus the ONE
    sanctioned behavior fix in this phase (``repl.py``). Everything else in
    the batch B file list (globals_env.py's four collector walkers,
    head_match.py's ``_resolved_field_names``, compiler_v2.py's class-arity
    reads, clpb.py's BoolEq/BoolImpl probe, reflection.py's op-node name
    read) is already covered by an existing focused suite — see
    task-3-report.md for the per-file mapping.
    """

    # ── repl.py: the sanctioned behavior fix ──────────────────────────────

    def _borrowed_dispatch_and_predicate(self):
        """Build a real compiled 2-field predicate and hand back its
        ``_get_dispatch()`` trampoline function, so the dataclass tests below
        drive a genuine, battle-tested dispatch generator rather than a
        hand-rolled one that might not honour the trampoline protocol."""
        from clausal import in_  # a real compiled builtin: in_(elem, lst)
        return in_._get_dispatch()

    def test_repl_iter_from_goal_dataclass_term_round_trips(self):
        """repl.py's ``_iter_from_goal`` (~196-197): OLD BEHAVIOR (pre-funnel)
        — the entry guard was ``isinstance(type(goal_or_iter), PredicateMeta)``,
        which is False for ANY plain ``@dataclass`` instance no matter what
        methods its class implements, so passing a dataclass-based goal here
        fell through to ``iter(goal_or_iter)`` (a dataclass instance is not
        iterable) and RAISED ``TypeError: Solutions expects a predicate
        instance or iterator, got ...`` — even for a goal whose class fully
        implements the same ``_get_dispatch()`` duck-typed protocol a
        PredicateMeta term uses (the protocol ``solve.py``/the builtin
        registry drive via ``hasattr(x, '_get_dispatch')``, not an
        ``isinstance`` check).

        NEW BEHAVIOR (this test): the guard is ``is_term_instance`` (accepts
        a PredicateMeta instance OR a dataclass instance), and field access
        goes through ``term_field_names``/``term_field_values``. A
        dataclass-based goal that duck-types ``_get_dispatch()`` on its class
        now drives and yields bindings instead of raising — it round-trips.
        """
        import dataclasses as _dc
        from clausal.logic.predicate import PredicateMeta
        from clausal.logic.variables import Var
        from clausal.repl import _iter_from_goal

        dispatch = self._borrowed_dispatch_and_predicate()

        @_dc.dataclass
        class DCMember:
            elem: object
            lst: object

            @classmethod
            def _get_dispatch(cls):
                return dispatch

        # Concretely document the guard widening this fix depends on: a
        # dataclass instance's type is never a PredicateMeta instance, so
        # the OLD guard would have rejected DCMember unconditionally.
        probe = DCMember(elem=1, lst=[1, 2, 3])
        assert not isinstance(type(probe), PredicateMeta)

        x = Var()
        goal = DCMember(elem=x, lst=[1, 2, 3])
        solutions = list(_iter_from_goal(goal, _varnames={"X": x}))
        assert solutions == [{"X": 1}, {"X": 2}, {"X": 3}]

    def test_repl_conj_dataclass_term_round_trips(self):
        """repl.py's ``_conj`` (~152): same fix, same rationale as
        ``_iter_from_goal`` above — OLD BEHAVIOR raised ``TypeError: _conj:
        expected predicate instances, got ...`` for any dataclass-based goal;
        NEW BEHAVIOR drives it via ``is_term_instance`` +
        ``term_field_names``/``term_field_values``."""
        import dataclasses as _dc
        from clausal.logic.variables import Var
        from clausal.repl import _conj

        dispatch = self._borrowed_dispatch_and_predicate()

        @_dc.dataclass
        class DCMember2:
            elem: object
            lst: object

            @classmethod
            def _get_dispatch(cls):
                return dispatch

        x = Var()
        goal = DCMember2(elem=x, lst=[10, 20])
        solutions = list(_conj(goal, _varnames={"X": x}))
        assert solutions == [{"X": 10}, {"X": 20}]

    # ── testing.py ~799 / ~1187: __dataclass_fields__ -> term_field_names ─

    def test_pair_vars_operator_node_fallback_pairs_a_variable(self):
        # nv — testing.py ~799 (_pair_vars's operator-node dataclass fallback)
        from clausal.logic.variables import Var
        from clausal.pythonic_ast.nodes import Gt
        from clausal.reflection import Variable
        from clausal.testing import _pair_vars

        v = Var()
        runtime = Gt(left=v, right=1)
        reified = Gt(left=Variable(name="X"), right=1)
        out = []
        assert _pair_vars(runtime, reified, out) is True
        assert out == [("X", v)]

    def test_pair_vars_operator_node_fallback_rejects_class_mismatch(self):
        # nv
        from clausal.pythonic_ast.nodes import Gt, Not
        from clausal.testing import _pair_vars

        assert _pair_vars(Not(operand=1), Gt(left=1, right=2), []) is False

    def test_collect_var_ids_operator_node_fallback(self):
        # nv — testing.py ~1187 (_collect_var_ids's operator-node fallback)
        from clausal.logic.variables import Var
        from clausal.pythonic_ast.nodes import Gt
        from clausal.testing import _collect_var_ids

        v = Var()
        term = Gt(left=v, right=5)
        out: set[int] = set()
        _collect_var_ids(term, out)
        assert out == {id(v)}


# ── Phase 2 bridge Task 1: plain-tuple regression (default-path invariant) ───


class TestPlainTupleAccessorRegression:
    """Pins TODAY's accessor behavior on plain, non-cell-shaped tuples.

    None of ``_functor_name``/``_arity``/``_nth_arg``/``_args_list``/
    ``_is_compound`` (C-accelerated or the ``_..._py`` fallback) nor
    ``functor_arity`` has ever had a tuple branch — a bare Python tuple
    fell through every one of them before the cell-awareness addition.
    That absence is exactly what makes the cell branch purely additive:
    these tests exercise tuples whose slot 0 is NOT a str / ``tuple`` type
    / Var (so ``is_cell`` is False for every one of them, per
    ``clausal/logic/cells.py``'s BRIDGE-ENTRY RULING) and must keep passing
    unchanged after the cell branch lands.
    """

    def test_functor_name_of_plain_tuple_is_none(self):
        # nv
        assert _functor_name((1, 2)) is None
        assert _functor_name((3.5, "a", None)) is None
        assert _functor_name(()) is None  # empty tuple: still not cell-shaped

    def test_arity_of_plain_tuple_is_none(self):
        # nv
        assert _arity((1, 2)) is None
        assert _arity((3.5, "a", None)) is None

    def test_nth_arg_of_plain_tuple_raises_index_error(self):
        # nv — plain tuples were never decomposed by _nth_arg; it falls
        # through to the final "raise IndexError" for any non-term shape.
        with pytest.raises(IndexError):
            _nth_arg((1, 2), 1)
        with pytest.raises(IndexError):
            _nth_arg((1, 2), 2)

    def test_args_list_of_plain_tuple_is_empty(self):
        # nv
        assert _args_list((1, 2)) == []
        assert _args_list((3.5, "a", None)) == []

    def test_is_compound_of_plain_tuple_is_false(self):
        # nv
        assert _is_compound((1, 2)) is False
        assert _is_compound((3.5, "a", None)) is False

    def test_functor_arity_of_plain_tuple_is_none(self):
        # nv
        assert functor_arity((1, 2)) is None
        assert functor_arity((3.5, "a", None)) is None


# ── Phase 2 bridge Task 1: cell funnel awareness (additive branch) ───────────


class TestCellFunnelAwareness:
    """The additive cell branch in ``_helpers.py``'s funnel accessors.

    THE DISCIPLINE (see ``clausal/logic/cells.py``'s module docstring —
    formerly documented here, and there, as an accepted "known ambiguity"):
    a plain user tuple whose slot 0 happens to be a str (e.g. ``("hello",
    1)``) IS a str-functor cell by shape, full stop, and its accessor
    behavior reflects that (``_functor_name`` answers ``"hello"`` for it,
    same as any other str-functor cell).

    P3-2 Task 5 (§1b): the bridge's unbound-Var-functor cell (a
    higher-order, not-yet-resolved functor slot) is DEPRECATED — it caused
    the bridge's one Critical, imposed a deref on every recognition, and
    permitted category instability. A slot-0-Var tuple is no longer
    cell-shaped at all: the ``test_var_functor_tuple_*`` tests below build
    it as a raw tuple (``make_cell`` now rejects a Var functor) and pin
    that it falls through to plain-tuple handling everywhere.
    """

    def test_str_functor_cell_functor_name_and_arity(self):
        # nv
        c = make_cell("point", 1, 2)
        assert _functor_name(c) == "point"
        assert _arity(c) == 2

    def test_str_functor_cell_nth_arg_and_args_list(self):
        # nv
        c = make_cell("point", 1, 2)
        assert _nth_arg(c, 1) == 1
        assert _nth_arg(c, 2) == 2
        assert _args_list(c) == [1, 2]

    def test_str_functor_cell_nth_arg_out_of_range_raises(self):
        # nv
        c = make_cell("point", 1, 2)
        with pytest.raises(IndexError):
            _nth_arg(c, 3)
        with pytest.raises(IndexError):
            _nth_arg(c, 0)

    def test_str_functor_cell_is_compound(self):
        # nv
        assert _is_compound(make_cell("point", 1, 2)) is True

    def test_str_functor_zero_arity_cell(self):
        # nv — ("atom",) : arity 0, args [], still compound (unlike a
        # PredicateMeta atom class, which has arity 0 and IS its own
        # functor — a cell atom is a distinct shape).
        c = make_cell("atom")
        assert _functor_name(c) == "atom"
        assert _arity(c) == 0
        assert _args_list(c) == []
        assert _is_compound(c) is True

    def test_str_functor_cell_functor_arity(self):
        # nv
        c = make_cell("point", 1, 2)
        assert functor_arity(c) == ("point", 2)

    def test_str_functor_cell_agrees_with_composed_functor_name_and_arity(self):
        # nv — same invariant TestFunctorArity checks for term shapes.
        c = make_cell("point", 1, 2)
        assert functor_arity(c) == (_functor_name(c), _arity(c))

    def test_tuple_tag_cell_is_not_compound(self):
        # nv — a (tuple, ...) cell is tuple DATA, not a compound term; per
        # the task brief it must NOT be decomposed the way a str-functor
        # cell is.
        c = make_tuple_cell(1, 2, 3)
        assert c == (TUPLE_TAG, 1, 2, 3)
        assert _is_compound(c) is False

    def test_tuple_tag_cell_functor_name_arity_unchanged(self):
        # nv — falls through to the same "not a recognized shape" answer a
        # plain tuple gets, since it is explicitly not treated as compound.
        c = make_tuple_cell(1, 2, 3)
        assert _functor_name(c) is None
        assert _arity(c) is None
        assert _args_list(c) == []
        assert functor_arity(c) is None

    def test_var_functor_tuple_functor_name_is_none(self):
        # INVERTED (P3-2 Task 5, §1b): the bridge's higher-order slot-0-Var
        # cell is DEPRECATED — ``make_cell`` now rejects a Var functor
        # outright (see ``tests/test_cells.py``), so this builds the raw
        # tuple directly. A slot-0-Var tuple is no longer cell-shaped at
        # all: it falls through to the same plain-tuple answer any other
        # non-str, non-``tuple`` tag gets. (Formerly
        # ``test_var_functor_cell_functor_name_returns_the_var``, asserting
        # ``_functor_name(c) is v``.)
        v = Var()
        c = (v, 1, 2)  # NOT built via make_cell -- see above
        assert _functor_name(c) is None

    def test_var_functor_tuple_is_not_compound(self):
        # INVERTED (P3-2 Task 5, §1b). (Formerly
        # ``test_var_functor_cell_is_compound``, asserting ``True``.)
        v = Var()
        c = (v, 1, 2)
        assert _is_compound(c) is False

    def test_var_functor_tuple_arity_and_args_no_longer_resolve(self):
        # INVERTED (P3-2 Task 5, §1b): arity/args used to be positional and
        # independent of the (as yet unresolved) functor identity because
        # the cell branch decomposed the tuple regardless of what slot 0
        # was. Now the tuple isn't recognized as a cell at all, so it gets
        # the plain-tuple answer across the board. (Formerly
        # ``test_var_functor_cell_arity_and_args_still_resolve``.)
        v = Var()
        c = (v, 1, 2)
        assert _arity(c) is None
        assert _args_list(c) == []
        with pytest.raises(IndexError):
            _nth_arg(c, 1)

    def test_var_functor_tuple_functor_arity_is_none(self):
        # nv, still None -- but for a different reason now. Formerly
        # (``test_var_functor_cell_functor_arity_is_none``): None because
        # functor_arity only resolves a RESOLVED (str) functor, mirroring
        # the Compound-with-Var-functor precedent, even though the composed
        # ``_functor_name``/``_arity`` pair DID resolve arity for this
        # shape. P3-2 Task 5 (§1b): None now because the tuple isn't a cell
        # at all any more, and the composed pair agrees (both None) —
        # there is no longer a divergence here to document.
        v = Var()
        c = (v, 1, 2)  # NOT built via make_cell -- see above
        assert functor_arity(c) is None
        assert (_functor_name(c), _arity(c)) == (None, None)

    def test_the_discipline_plain_str_tuple_pinned_by_running_assertions(self):
        # RE-WORDED (P3-2 Task 5, §1b), same assertions: what this class's
        # docstring and ``clausal/logic/cells.py``'s module docstring used
        # to document as an accepted "known ambiguity" (BRIDGE-ENTRY RULING
        # #2 in the ledger) is now THE DISCIPLINE per the slot-0 narrowing:
        # every runtime tuple whose slot 0 is a str IS a cell, full stop —
        # ``("hello", 1)`` is a str-functor cell by shape, and every funnel
        # accessor treats it exactly like any other one. Pinned by RUNNING
        # assertions, not prose alone, so a future change to this rule
        # shows up as a failing test, not a silent behavior drift.
        # (Formerly
        # ``test_known_ambiguity_plain_str_tuple_pinned_by_running_assertions``.)
        plain_user_tuple = ("hello", 1)
        assert _functor_name(plain_user_tuple) == "hello"
        assert _arity(plain_user_tuple) == 1
        assert _args_list(plain_user_tuple) == [1]
        assert _is_compound(plain_user_tuple) is True
        assert functor_arity(plain_user_tuple) == ("hello", 1)


class TestCellGroundnessRegression:
    """``_is_ground`` was the SIXTH member of the cells-blind family.

    The Phase-2 cell-awareness pass wrapped ``_functor_name``/``_arity``/
    ``_nth_arg``/``_args_list``/``_is_compound`` and skipped this one, so a
    cell fell through to the "unknown shape -> True" tail and a term holding
    a free variable reported GROUND.  Two answers rode on it: ``ground/1``,
    and ``_findall_copy_row``, which gates the ISO per-solution copy on
    groundness — an ungrounded cell row skipped the copy and shared the
    caller's Var, so binding it afterwards mutated the collected row
    (A03-F006, reintroduced for cell rows).
    """

    def test_a_cell_holding_a_free_var_is_not_ground(self):
        # nv
        from clausal.logic.builtins._helpers import _is_ground

        assert _is_ground(make_cell("pt", 1, 2)) is True
        assert _is_ground(make_cell("pt", 1, Var())) is False

    def test_a_cell_nested_in_a_list_is_reached(self):
        """The C accelerator recursed into lists without returning to
        Python, which is why the top-level short-circuit other cells-blind
        shapes use could not work here."""
        # nv
        from clausal.logic.builtins._helpers import _is_ground

        assert _is_ground([1, make_cell("pt", 1, Var())]) is False
        assert _is_ground(Compound("f", (make_cell("pt", Var()),))) is False

    def test_it_agrees_with_the_class_twin(self):
        """The whole point: cell and class term answer the same."""
        # nv
        from clausal.logic.builtins._helpers import _is_ground
        from clausal.logic.predicate import make_predicate

        pt = make_predicate("pt", ["a", "b"])
        free = Var()
        assert _is_ground(pt(1, free)) is False
        assert _is_ground(make_cell("pt", 1, free)) is False

    def test_findall_copies_an_ungrounded_cell_row(self):
        """``_findall_copy_row``'s ISO copy, on the shape that skipped it.

        The row it returns must not be reachable from the caller's Var:
        binding that Var afterwards is exactly what used to mutate the
        already-collected row.
        """
        # nv
        from clausal.logic.compiler.globals_env import _findall_copy_row
        from clausal.logic.variables import Trail, unify

        x = Var()
        row = _findall_copy_row(make_cell("pt", 1, x))
        assert unify(x, 9, Trail())
        assert deref(x) == 9                 # the caller's Var did bind ...
        assert is_var(deref(row[2]))         # ... and the copy did not move
        assert deref(row[2]) is not deref(x)

    def test_compound_1_answers_for_a_cell(self):
        """``compound/1`` was the one type check that did not route through
        the funnel, so it answered False where ``functor/3``, ``arg/3``,
        ``=../2`` and ``callable/1`` all answered for the same term."""
        # nv
        from clausal.logic.builtins._helpers import _arity, _is_compound

        c = make_cell("pt", 1, 2)
        assert _is_compound(c) is True
        assert _arity(c) == 2
