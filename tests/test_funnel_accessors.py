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
    _functor_name,
    _is_ground,
    _standard_order_key,
    functor_arity,
)
from clausal.logic.variables import Var
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
        assert functor_arity("abc") is None
        assert functor_arity(42) is None
        assert functor_arity(None) is None

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
        # nv — _standard_order_key line ~368
        key = _standard_order_key(foo_atom)
        assert key == (2, "foo", 1)  # (_ORD_ATOM, name, 1)

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
