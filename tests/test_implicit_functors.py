"""``-implicit_functors``: the per-module open-world (OWA) functor-construction
flag (P3-2 Task 6, user ruling R7).

Spec: ``implementation_plans/tagged-tuple-term-representation.md`` §1
("Open-world construction is a per-module toggle: signatures from -module
are advisory when on ... checked when off"); task brief:
``.superpowers/sdd/p32-cell-default-flip/task-6-brief.md``.

Construction checking is ON by default everywhere (P3-2 Tasks 1-2): a
keyword-free reference to an undeclared functor is a runtime ``NameError``
and an over-arity reference to a declared one is a compile-time
``SyntaxError`` (``clausal.logic.compiler.terms_to_ast.
cell_signature_for_name`` / ``_place_signature_slots``).  A module carrying
``-implicit_functors`` opts OUT of both checks for keyword-free
construction: any functor at any WRITTEN arity, declared or not, compiles to
a cell.  Keyword construction/matching still needs a real signature to place
its named slots against, flag or no flag.  The identical rule applies on the
HEAD side (``head_match.head_to_match_pattern``'s ``Call(LoadName)``
branch), so a flagged module's clause heads pattern-match the cells its own
bodies build.

Groups:

1. ``TestDirective`` -- directive parsing: bare/parenthesised forms, no
   arguments, dispatch + the unknown-directive message.
2. ``TestImplicitFunctors`` -- the OWA construction/matching rule itself,
   its default-off pins (the SAME source without the flag reproduces
   today's errors), keyword-construction's compile error, the
   assert+query round trip (head-side symmetry), and strict-atoms
   orthogonality.
3. ``TestDottedOwaGate`` -- fix round 1 (Important finding): a DOTTED OWA-
   unknown reference (an unresolvable qualified name, e.g. a typo'd or
   missing attribute on a real imported module) must NOT take the OWA cell
   branch -- it falls through to the existing (loud) failure path, same
   class and timing as without the flag. A legitimately resolved dotted
   DATA functor is unaffected (regression guard).
"""

from __future__ import annotations

import pathlib

import pytest

from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref

from tests.tagged_terms_support import capture_predicate_codegen

_FIXTURES_DIR = pathlib.Path(__file__).parent / "fixtures"


def _load_inline(name: str, source: str):
    """Compile *source* as a ``.clausal`` module named *name*."""
    import tempfile
    import os

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, f"{name}.clausal")
        with open(path, "w") as fh:
            fh.write(source)
        return _load_module(name, path)


def _load_fixture(basename: str):
    module_name = f"tests.fixtures.{basename}"
    return _load_module(module_name, str(_FIXTURES_DIR / f"{basename}.clausal"))


def _logic_module(mod):
    return mod.__dict__["$module"]


# ── Directive ────────────────────────────────────────────────────────────────


class TestDirective:
    def test_bare_form_is_accepted(self):
        _load_inline(
            "_if_bare",
            "-implicit_functors\n-module(_if_bare, [p(A)])\np(1),\n",
        )

    def test_parenthesised_form_is_accepted(self):
        _load_inline(
            "_if_paren",
            "-implicit_functors()\n-module(_if_paren, [p(A)])\np(1),\n",
        )

    def test_rejects_arguments(self):
        with pytest.raises(SyntaxError) as exc_info:
            _load_inline(
                "_if_args",
                "-implicit_functors(foo)\n-module(_if_args, [p(A)])\np(1),\n",
            )
        assert "-implicit_functors takes no arguments" in str(exc_info.value)

    def test_unknown_directive_message_lists_implicit_functors(self):
        with pytest.raises(SyntaxError) as exc_info:
            _load_inline(
                "_if_unknown",
                "-no_such_directive(1)\n-module(_if_unknown, [p(A)])\np(1),\n",
            )
        message = str(exc_info.value)
        assert "known directives:" in message
        assert "-implicit_functors" in message

    def test_sets_the_module_namespace_flag(self):
        from clausal.logic.cells import IMPLICIT_FUNCTORS_FLAG

        mod = _load_inline(
            "_if_flagset",
            "-implicit_functors\n-module(_if_flagset, [p(A)])\np(1),\n",
        )
        assert mod.__dict__[IMPLICIT_FUNCTORS_FLAG] is True

    def test_flag_absent_without_the_directive(self):
        from clausal.logic.cells import IMPLICIT_FUNCTORS_FLAG

        mod = _load_inline(
            "_if_noflagset",
            "-module(_if_noflagset, [p(A)])\np(1),\n",
        )
        assert IMPLICIT_FUNCTORS_FLAG not in mod.__dict__


# ── OWA construction / matching ─────────────────────────────────────────────


class TestImplicitFunctors:
    # -- undeclared functor: construction + head symmetry + round trip -----

    def test_undeclared_functor_constructs_a_cell(self):
        """``wibble(1, 2)`` has no signature anywhere -- OWA still builds it."""
        src = capture_predicate_codegen(
            "tests.fixtures.implicit_functors_unknown_owa", ["p"]
        )
        assert "('wibble', 1, 2)" in src
        assert "wibble(1, 2)" not in src

    def test_undeclared_functor_round_trips_through_a_query(self):
        mod = _load_fixture("implicit_functors_unknown_owa")
        lm = _logic_module(mod)
        x = Var()
        answers = [deref(x) for _t in call("p", x, module=lm)]
        assert answers == [("wibble", 1, 2)]

    def test_head_side_symmetry_matches_the_same_owa_unknown_functor(self):
        """A flagged module's clause HEADS pattern-match the cells its own
        bodies build -- the phase's standing construction/matching
        symmetry, driven end to end (not just at the codegen level)."""
        mod = _load_fixture("implicit_functors_unknown_owa")
        lm = _logic_module(mod)
        a, b = Var(), Var()
        got = [
            (deref(a), deref(b))
            for _t in call("unwrap", ("wibble", 7, 8), a, b, module=lm)
        ]
        assert got == [(7, 8)]

    def test_assert_and_query_round_trip_inside_one_flagged_module(self):
        """Full driven round trip: ``p/1`` constructs the OWA-unknown cell,
        ``unwrap/3`` (a head pattern over that SAME functor) destructures
        whatever ``p/1`` produced -- construction and matching agreeing end
        to end within a single flagged module."""
        mod = _load_fixture("implicit_functors_unknown_owa")
        lm = _logic_module(mod)
        w = Var()
        built = [deref(w) for _t in call("p", w, module=lm)]
        assert built == [("wibble", 1, 2)]
        x, y = Var(), Var()
        got = [
            (deref(x), deref(y))
            for _t in call("unwrap", built[0], x, y, module=lm)
        ]
        assert got == [(1, 2)]

    def test_undeclared_functor_default_off_pin_is_a_query_time_nameerror(self):
        """The SAME source without the flag: today's default (construction
        checked) behaviour -- an undeclared functor is a runtime
        ``NameError`` when the goal referencing it actually runs."""
        mod = _load_fixture("implicit_functors_unknown_plain")
        lm = _logic_module(mod)
        x = Var()
        with pytest.raises(NameError, match=r"wibble"):
            list(call("p", x, module=lm))

    # -- declared functor at a different arity: advisory under OWA ---------

    def test_declared_functor_at_a_different_arity_constructs_at_written_arity(self):
        """``point/2`` IS declared; referenced at arity 3 under OWA the
        signature is advisory -- the cell is built at the WRITTEN arity."""
        src = capture_predicate_codegen(
            "tests.fixtures.implicit_functors_arity_owa", ["p"]
        )
        assert "('point', 10, 20, 30)" in src

    def test_declared_functor_over_arity_round_trips_through_a_query(self):
        mod = _load_fixture("implicit_functors_arity_owa")
        lm = _logic_module(mod)
        x = Var()
        answers = [deref(x) for _t in call("p", x, module=lm)]
        assert answers == [("point", 10, 20, 30)]

    def test_declared_functor_under_arity_is_also_advisory_not_backfilled(self):
        """Wholesale advisory (§1: "any arity/functor constructs a cell"):
        a SHORT positional reference builds the cell at the WRITTEN arity
        too, rather than backfilling the omitted slot with a fresh ``Var()``
        the way the unconditional (unflagged) placement rule does."""
        mod = _load_inline(
            "_if_underarity",
            "-implicit_functors\n"
            "-module(_if_underarity, [point(x, y), p(A)])\n"
            "p(point(1)),\n",
        )
        lm = _logic_module(mod)
        x = Var()
        answers = [deref(x) for _t in call("p", x, module=lm)]
        assert answers == [("point", 1)]

    def test_declared_functor_over_arity_default_off_pin_is_a_load_time_syntaxerror(self):
        """The SAME source without the flag: today's default (construction
        checked) behaviour -- an over-arity reference to a declared functor
        is a compile-time ``SyntaxError`` naming the functor, raised while
        the module LOADS."""
        with pytest.raises(SyntaxError, match=r"point/2"):
            _load_fixture("implicit_functors_arity_plain")

    # -- keyword construction is refused, flag or no flag --------------------

    def test_keyword_construction_is_refused_under_the_flag_too(self):
        """Three tests lived here: an OWA-unknown functor built with keywords
        errored naming its missing signature; a DECLARED functor placed its
        keywords by field name; an unknown FIELD name was rejected naming
        ``point/2``.  All three asked what keyword construction does under
        ``-implicit_functors``, and the answer since 2026-09-19 is that it
        does not load at all — the flag makes KEYWORD-FREE construction
        advisory and has nothing to say about a spelling the language has
        retired.  What the flag still does is covered by the OWA tests below.
        """
        for source in (
            "p(wobble(x=1)),\n",           # OWA-unknown functor
            "p(point(y=2, x=1)),\n",       # declared functor, keywords by name
            "p(point(z=1)),\n",            # unknown field name
        ):
            with pytest.raises(SyntaxError, match="keyword arguments"):
                _load_inline(
                    "_if_kw" + str(abs(hash(source)) % 10000),
                    "-implicit_functors\n"
                    "-module(_if_kw, [point(x, y), p(A)])\n" + source,
                )

    # -- predicate references keep class/goal emission under OWA -----------

    def test_a_predicate_reference_keeps_class_goal_emission_under_owa(self):
        """A functor WITH clauses is a predicate, not data -- calling it is
        a goal, and OWA does not change that (a goal is not data)."""
        _load_inline(
            "_if_pred",
            "-implicit_functors\n"
            "-module(_if_pred, [q(A), r(A)])\n"
            "q(1),\n"
            "r(X) <- call(q(X)),\n",
        )
        src = capture_predicate_codegen("_if_pred", ["r"])
        assert "('q'," not in src

    # -- strict-atoms orthogonality ------------------------------------------

    def test_strict_atoms_orthogonality_bare_atom_still_needs_declaration(self):
        """``-implicit_functors`` opens functor CONSTRUCTION, not atom
        vocabulary: a bare (0-arity) ATOM reference in a flagged module that
        also carries ``-strict_atoms`` is still an undeclared-atom
        ``NameError`` -- the two directives are independent mechanisms."""
        with pytest.raises(NameError, match=r"undeclared atom"):
            _load_inline(
                "_if_strict_orth",
                "-implicit_functors\n"
                "-strict_atoms\n"
                "-module(_if_strict_orth, [p(A)])\n"
                "p(some_undeclared_bare_atom),\n",
            )

    def test_strict_atoms_orthogonality_functor_construction_still_works(self):
        """...while functor CONSTRUCTION in that SAME flagged+strict module
        is unaffected: an OWA-unknown functor still builds a cell."""
        mod = _load_inline(
            "_if_strict_orth_ok",
            "-implicit_functors\n"
            "-strict_atoms\n"
            "-module(_if_strict_orth_ok, [p(A)])\n"
            "p(wibble(1, 2)),\n",
        )
        lm = _logic_module(mod)
        x = Var()
        answers = [deref(x) for _t in call("p", x, module=lm)]
        assert answers == [("wibble", 1, 2)]


# ── Fix round 1: dotted OWA-unknown references stay loud ────────────────────


class TestDottedOwaGate:
    """Fix round 1, Important finding (reviewer-confirmed live): a DOTTED
    OWA-unknown reference (``other.NoSuchThing(1, 2)``) used to silently
    build a cell tagged with the WHOLE dotted string -- violating R5's
    base-name-spelling invariant, producing permanently-unmatchable dead
    data, and converting a loud ``NameError`` into silent success.

    Ruling: OWA opens the flagged module's OWN functor vocabulary; an
    unresolvable DOTTED prefix is a name-resolution failure (missing import
    or typo) that must stay loud, on both construction (Site A) and head
    matching. Gate: the OWA branch only fires for a plain (dot-free) name.
    """

    def test_dotted_owa_unknown_construction_stays_a_query_time_nameerror(self):
        """(a) The reviewer's exact repro: a dotted reference to a
        nonexistent attribute on a REAL imported module, in a flagged
        module's body, still raises ``NameError`` -- not a silently-built
        cell tagged with the whole dotted string."""
        mod = _load_inline(
            "_if_dot_owa",
            "-implicit_functors\n"
            "-import_module(tests.fixtures.importable_utils)\n"
            "-module(_if_dot_owa, [p(A)])\n"
            "p(tests.fixtures.importable_utils.NoSuchThing(1, 2)),\n",
        )
        lm = _logic_module(mod)
        x = Var()
        with pytest.raises(
            NameError,
            match=r"tests\.fixtures\.importable_utils\.NoSuchThing",
        ):
            list(call("p", x, module=lm))

    def test_dotted_owa_unknown_construction_matches_the_unflagged_error(self):
        """Same source minus the flag: identical error CLASS, identical
        MESSAGE, identical TIMING (raised when ``p/1`` is driven, not at
        load) -- OWA changes nothing about this dotted, unresolvable case."""
        flagged = _load_inline(
            "_if_dot_owa_cmp_flag",
            "-implicit_functors\n"
            "-import_module(tests.fixtures.importable_utils)\n"
            "-module(_if_dot_owa_cmp_flag, [p(A)])\n"
            "p(tests.fixtures.importable_utils.NoSuchThing(1, 2)),\n",
        )
        plain = _load_inline(
            "_if_dot_owa_cmp_plain",
            "-import_module(tests.fixtures.importable_utils)\n"
            "-module(_if_dot_owa_cmp_plain, [p(A)])\n"
            "p(tests.fixtures.importable_utils.NoSuchThing(1, 2)),\n",
        )
        # Both LOAD cleanly -- the dotted reference is only diagnosed lazily,
        # when the goal that references it actually runs (same as any other
        # unresolved global in this compiler).
        with pytest.raises(NameError) as flagged_exc:
            list(call("p", Var(), module=_logic_module(flagged)))
        with pytest.raises(NameError) as plain_exc:
            list(call("p", Var(), module=_logic_module(plain)))
        assert str(flagged_exc.value) == str(plain_exc.value)

    def test_dotted_owa_unknown_head_reference_stays_a_query_time_nameerror(self):
        """(c) Head-side twin of (a): a dotted reference to a nonexistent
        attribute used as a clause HEAD pattern in a flagged module still
        raises ``NameError`` at drive time, identical class/message to the
        unflagged twin -- head_match's mirrored gate is exercised, not just
        Site A's."""
        flagged = _load_inline(
            "_if_dot_owa_head_flag",
            "-implicit_functors\n"
            "-import_module(tests.fixtures.importable_utils)\n"
            "-module(_if_dot_owa_head_flag, [unwrap(W, X)])\n"
            "unwrap(tests.fixtures.importable_utils.NoSuchThing(X), X),\n",
        )
        plain = _load_inline(
            "_if_dot_owa_head_plain",
            "-import_module(tests.fixtures.importable_utils)\n"
            "-module(_if_dot_owa_head_plain, [unwrap(W, X)])\n"
            "unwrap(tests.fixtures.importable_utils.NoSuchThing(X), X),\n",
        )
        with pytest.raises(
            NameError,
            match=r"tests\.fixtures\.importable_utils\.NoSuchThing",
        ) as flagged_exc:
            list(call("unwrap", ("NoSuchThing", 9), Var(), module=_logic_module(flagged)))
        with pytest.raises(NameError) as plain_exc:
            list(call("unwrap", ("NoSuchThing", 9), Var(), module=_logic_module(plain)))
        assert str(flagged_exc.value) == str(plain_exc.value)

    def test_a_legitimately_imported_dotted_functor_is_unaffected_by_the_gate(self):
        """(b) Regression guard: the dot-gate must not disturb the RESOLVED
        path -- a dotted reference that DOES resolve to a declared data
        functor (via ``-import_module``) still emits the base-spelling cell
        under OWA, exactly as it does without the flag."""
        mod = _load_inline(
            "_if_dot_resolved",
            "-implicit_functors\n"
            "-import_module(tests.fixtures.implicit_functors_dotted_owner)\n"
            "-module(_if_dot_resolved, [p(A)])\n"
            "p(tests.fixtures.implicit_functors_dotted_owner.wrap(5)),\n",
        )
        src = capture_predicate_codegen("_if_dot_resolved", ["p"])
        assert "('wrap', 5)" in src
        lm = _logic_module(mod)
        x = Var()
        answers = [deref(x) for _t in call("p", x, module=lm)]
        assert answers == [("wrap", 5)]

    def test_a_legitimately_imported_dotted_functor_matches_the_unflagged_path(self):
        """...and produces the IDENTICAL cell whether or not the importer
        carries ``-implicit_functors`` -- the resolved-dotted-name path
        (``cell_signature_for_name`` finding a real registry entry) does not
        even reach the new OWA branches."""
        flagged = _load_inline(
            "_if_dot_resolved_cmp_flag",
            "-implicit_functors\n"
            "-import_module(tests.fixtures.implicit_functors_dotted_owner)\n"
            "-module(_if_dot_resolved_cmp_flag, [p(A)])\n"
            "p(tests.fixtures.implicit_functors_dotted_owner.wrap(5)),\n",
        )
        plain = _load_inline(
            "_if_dot_resolved_cmp_plain",
            "-import_module(tests.fixtures.implicit_functors_dotted_owner)\n"
            "-module(_if_dot_resolved_cmp_plain, [p(A)])\n"
            "p(tests.fixtures.implicit_functors_dotted_owner.wrap(5)),\n",
        )
        x1, x2 = Var(), Var()
        flagged_answers = [deref(x1) for _t in call("p", x1, module=_logic_module(flagged))]
        plain_answers = [deref(x2) for _t in call("p", x2, module=_logic_module(plain))]
        assert flagged_answers == plain_answers == [("wrap", 5)]
