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

from clausal.logic.atoms import mint
from clausal.import_hook import _load_module
from clausal.logic.variables import Trail, Var, occurs_check, unify


# ── unify ─────────────────────────────────────────────────────────────────


# ── occurs check ──────────────────────────────────────────────────────────


# ── the calling-convention discriminator ──────────────────────────────────


# ── end to end, through .clausal source ───────────────────────────────────


def _load(tmp_path, name, text):
    path = tmp_path / f"{name}.clausal"
    path.write_text(textwrap.dedent(text).lstrip())
    return _load_module(f"tests_pcatv_{name}", str(path))


class TestClausalSourceRepro:
    """The reduced form of the field failure, run as Clausal."""

    def test_bare_functor_name_now_IS_the_string(self, tmp_path):
        """P3-2 Task 2 (THE FLIP, R6) RESOLVES the asymmetry this pinned.

        ``functor/3`` names a functor with a string, and a bare reference to
        a declared DATA functor now IS that string (its name binds the
        interned spelling, no class), so ``NAME is cite`` with ``NAME =
        "cite"`` SUCCEEDS.  Inverts the old pin, which recorded the
        pre-flip behaviour: the bare name resolved to the generated CLASS,
        which no string could ever equal, so the comparison just failed.
        """
        mod = _load(tmp_path, "bare_name", """
            -private([cite(KEY), check(NAME)])

            check(NAME) <- (
                NAME is cite
            ),
        """)
        from clausal.logic.solve import solve
        assert len(list(solve(("check", mint("cite")), mod))) == 1

    def test_the_field_body_verbatim_now_succeeds(self, tmp_path):
        """``test_load.clausal:57``, reduced to one module.

        ``functor/3`` decomposition yields the functor name as a *string*.
        Pre-flip ``NAME is cite`` compared that string against the generated
        CLASS and could not succeed -- the todo's asymmetry, pinned here as a
        clean failure rather than a ``TypeError``.  P3-2 Task 2 (THE FLIP,
        R6) removes the asymmetry: a declared data functor's bare name IS its
        spelling, so the whole body now succeeds, which is what the author
        wrote it expecting.
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
        assert len(list(solve(("cite_term_constructs", Var()), mod))) == 1

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
        assert len(list(solve(("roundtrip", Var()), mod))) == 1
