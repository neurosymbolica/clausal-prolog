"""A predicate *class* used as a term value must unify, not raise TypeError.

``todo/done/internal-unify-typeerror-reaches-the-user-as-error-text.md`` — observed
in the field as::

    test_load.clausal:57 :: cite term constructs correctly
      — _make_unify.<locals>.__unify__() missing 1 required positional
        argument: 'trail'

from ``FUNCTOR_NAME is cite`` where ``cite(KEY)`` is a declared arity-1
functor.  Cost, measured across two formalization runs: 10 repair attempts,
neither recovering — the message names a closure inside the engine and a
parameter the author never wrote, so there is nothing to act on.

The mechanism.  The C unifier reaches a Python term type through
``PyObject_GetAttrString(t, "__unify__")``.  When ``t`` is an *instance* that
yields a bound method and the call ``hook(other, trail)`` lines up.  When ``t``
is a **class** used as a value — which is how Clausal spells a bare functor
name — the same lookup yields the *unbound* function, so ``hook(other, trail)``
lands ``other`` in ``self`` and leaves ``trail`` unfilled.  ``__occurs_check__``
has the identical shape and the identical break.

Zero-arity atoms never hit this because ``PredicateMeta`` deliberately installs
no hooks on them ("the class IS the value, so identity comparison handles
unification correctly").  These tests pin that a functor class of *any* arity
now behaves the same way when it appears as a value: identity decides, no
exception, and the engine's ordinary goal-failure diagnostic — which shows the
offending binding — is what the author gets.

They also pin the *identity-preserving* half of that claim, because the fix
adds a branch to the hottest hook in the engine and would be worth nothing if
it changed an answer: instance unification, occurs-check recursion into fields,
and the arity-0 atom's behaviour all have to come out where they were.
"""

from __future__ import annotations

import textwrap

import pytest

from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.variables import Trail, Var, occurs_check, unify


@pytest.fixture
def cite():
    """An arity-1 declared functor, as ``-private([cite(KEY)])`` mints it."""
    return make_predicate("pcatv_cite", ["key"])


# ── unify ─────────────────────────────────────────────────────────────────


class TestClassAsValueUnify:
    """``unify(<functor class>, X)`` decides by identity and never raises."""

    def test_against_its_own_name_as_a_string_fails_quietly(self, cite):
        # The exact field shape: FUNCTOR_NAME is bound to the *string* the
        # functor/3 decomposition produced, then compared against the class.
        assert unify(cite, "pcatv_cite", Trail()) is False

    def test_string_on_the_left_fails_quietly_too(self, cite):
        # The symmetric arm of the C hook — this is the one the field case
        # actually took, since `is` put the string first.
        assert unify("pcatv_cite", cite, Trail()) is False

    def test_against_itself_succeeds(self, cite):
        assert unify(cite, cite, Trail()) is True

    def test_against_a_different_functor_class_fails_quietly(self, cite):
        other = make_predicate("pcatv_other", ["key"])
        assert unify(cite, other, Trail()) is False

    def test_against_an_instance_of_itself_fails_quietly(self, cite):
        assert unify(cite, cite(key=1), Trail()) is False

    def test_against_none_fails(self, cite):
        # The class arm answers ``self is owner``; ``None`` is the value that
        # would sneak through if ``owner`` were ever left unset.
        assert unify(cite, None, Trail()) is False

    def test_binds_a_free_variable(self, cite):
        v = Var()
        trail = Trail()
        assert unify(v, cite, trail) is True
        from clausal.logic.variables import deref
        assert deref(v) is cite

    def test_instance_unification_is_untouched(self, cite):
        v = Var()
        trail = Trail()
        assert unify(cite(key=v), cite(key=7), trail) is True
        from clausal.logic.variables import deref
        assert deref(v) == 7

    def test_zero_arity_atom_and_functor_class_agree(self):
        """The arity-0 case already worked; arity-N must not differ."""
        atom = PredicateMeta("pcatv_zero", (), {"_fields": ()})
        assert unify(atom, "pcatv_zero", Trail()) is False
        assert unify(atom, atom, Trail()) is True


# ── occurs check ──────────────────────────────────────────────────────────


class TestClassAsValueOccursCheck:
    """``occurs_check(V, <functor class>)`` is False, not a TypeError.

    A bare class carries no arguments, so it can never contain a variable —
    the same reasoning ``PredicateMeta`` already applies to arity-0 atoms.
    """

    def test_free_variable_does_not_occur_in_a_bare_functor_class(self, cite):
        assert occurs_check(Var(), cite) is False

    def test_unify_with_occurs_check_reaches_the_same_answer(self, cite):
        from clausal.logic.variables import unify_with_occurs_check
        assert unify_with_occurs_check(Var(), cite, Trail()) is True

    def test_occurs_check_still_recurses_into_instances(self, cite):
        v = Var()
        assert occurs_check(v, cite(key=v)) is True


# ── the calling-convention discriminator ──────────────────────────────────


class TestCallingConventionDiscriminator:
    """Which convention a hook call is in must be decided, not guessed.

    ``__unify__`` serves two callers with the same name, so the branch that
    tells them apart is load-bearing: read it the wrong way round and field
    unification silently answers about the wrong operands.  A missing third
    argument is the only signal, and only the class-side call can be missing
    one.
    """

    def test_class_side_call_is_the_two_argument_one(self, cite):
        # Exactly what the C side does with a class-valued term.
        assert cite.__unify__(cite, Trail()) is True
        assert cite.__unify__("pcatv_cite", Trail()) is NotImplemented

    def test_instance_side_call_still_needs_all_three(self, cite):
        # And still recurses into the fields rather than taking the class arm.
        v = Var()
        assert cite(key=v).__unify__(cite(key=5), Trail()) is True
        from clausal.logic.variables import deref
        assert deref(v) == 5

    def test_class_side_occurs_check_is_the_one_argument_one(self, cite):
        assert cite.__occurs_check__(Var()) is False

    def test_deferring_lets_the_other_operand_answer(self, cite):
        """``NotImplemented``, not ``False`` — a hook on the far side must still
        get its turn, which is what keeps this change outcome-preserving."""
        from clausal.terms import SegList
        seg = SegList([1, 2, 3])
        # The class cannot unify with a SegList either way; what is pinned is
        # that the class arm defers instead of claiming the answer.
        assert cite.__unify__(seg, Trail()) is NotImplemented


# ── end to end, through .clausal source ───────────────────────────────────


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tests_pcatv_{name}", str(path))


class TestClausalSourceRepro:
    """The reduced form of the field failure, run as Clausal."""

    def test_bare_functor_name_compared_to_a_string_just_fails(self, tmp_path):
        mod = _load(tmp_path, "bare_name", """
            -private([cite(KEY), check(NAME)])

            check(NAME) <- (
                NAME is cite
            ),
        """)
        from clausal.logic.solve import solve
        # No solution, and — the point of the todo — no exception.
        assert list(solve(mod.check("cite"))) == []

    def test_the_field_body_verbatim_fails_instead_of_raising(self, tmp_path):
        """``test_load.clausal:57``, reduced to one module.

        ``functor/3`` decomposition yields the functor name as a *string*, so
        ``NAME is cite`` compares a string against the class and cannot
        succeed.  Whether that asymmetry is itself right is a separate
        question (see the todo); what this pins is that the author is told
        the goal *failed*, with the binding shown, rather than handed a
        TypeError about a parameter named ``trail``.
        """
        mod = _load(tmp_path, "field_body", """
            -private([cite(KEY), art_6_1, cite_term_constructs(OK)])

            cite_term_constructs(OK) <- (
                CITE_TERM is cite(art_6_1),
                functor(CITE_TERM, FUNCTOR_NAME, ARITY),
                FUNCTOR_NAME is cite,
                ARITY == 1,
                OK is 1
            ),
        """)
        from clausal.logic.solve import solve
        assert list(solve(mod.cite_term_constructs(Var()))) == []

    def test_functor_3_decomposition_names_the_functor_as_a_string(self, tmp_path):
        """What the same body *does* yield, once nothing raises."""
        mod = _load(tmp_path, "functor3", """
            -private([cite(KEY), art_6_1, roundtrip(OK)])

            roundtrip(OK) <- (
                CITE_TERM is cite(art_6_1),
                functor(CITE_TERM, NAME, ARITY),
                NAME == "cite",
                ARITY == 1,
                OK is 1
            ),
        """)
        from clausal.logic.solve import solve
        assert len(list(solve(mod.roundtrip(Var())))) == 1
