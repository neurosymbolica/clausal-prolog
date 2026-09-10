"""Variable names cross the Prolog boundary unchanged, in both directions.

A capital-initial name is a logic variable in Clausal and in ISO Prolog
alike, and ``_x`` is one in both, so there is nothing left for a translator
to rename.  ``clausal_var_to_prolog`` / ``prolog_var_to_clausal`` are the
identity.

The point of this file is that "identity" is a PROPERTY, not a spelling.
``assert f(x) == x`` passes for any implementation once identity is the
intent — including one where the call site was deleted — so the tests that
carry the weight here assert things the old mangler got WRONG and a future
regression would get wrong again:

* **Injectivity.** The old mangler sent ``_result`` and ``RESULT`` both to
  ``Result``; two distinct variables in one clause silently became one, and
  a per-clause rename table was bolted on to number the loser ``Result2``.
  Identity cannot collide, so the numbering is gone — and the way to notice
  it coming back is to count distinct names, not to read them.  The
  emission-level cases live with the defect that produced them, in
  test_prolog_fix_review.py::TestF022VarRenameInjective; what is here is the
  function-level property over a set of names, which that class does not
  state.
* **Round-trip fidelity.** Out to ``.pl`` and back returns the source
  spelling, for every shape the old mangler treated differently.
* **The wildcard.** ``_`` is the one name where identity might be wrong.
"""
import re

from clausal.tools.clausal_to_prolog import clausal_source_to_prolog
from clausal.tools.prolog_dialect import (
    clausal_var_to_prolog, prolog_var_to_clausal,
)
from clausal.tools.prolog_to_clausal import prolog_to_clausal


#: Variable spellings that are legal on BOTH sides of the boundary, chosen so
#: that the old mangler mapped them to at least two colliding pairs.
SHAPES = ("Foo", "FOO", "N0", "_x", "_result", "RESULT", "X")


def _prolog_var_names(text: str) -> list[str]:
    """Every variable token in emitted Prolog, in order, wildcards included."""
    return re.findall(r"(?<![A-Za-z0-9_])(_[A-Za-z0-9_]*|[A-Z][A-Za-z0-9_]*)", text)


# ── Injectivity: the property the rename table existed to fake ────────

def test_export_mangling_is_injective():
    """Distinct Clausal variables must map to distinct Prolog variables.

    The old mangler failed this (``_result`` and ``RESULT`` both -> ``Result``,
    ``Foo`` and ``FOO`` both -> ``Foo``), which is the whole reason a
    per-clause uniquifier existed.
    """
    mapped = [clausal_var_to_prolog(name) for name in SHAPES]
    assert len(set(mapped)) == len(SHAPES), dict(zip(SHAPES, mapped))


def test_import_mangling_is_injective():
    """Same property inbound: the old rule sent ``Foo`` and ``FOO`` to ``_foo``."""
    mapped = [prolog_var_to_clausal(name) for name in SHAPES]
    assert len(set(mapped)) == len(SHAPES), dict(zip(SHAPES, mapped))


# The ``_result``/``RESULT`` pair itself is pinned where the defect was filed,
# in test_prolog_fix_review.py::TestF022VarRenameInjective — including the
# three-way ``_x``/``X``/``_X`` collision and the one-variable-stays-one
# converse. Not repeated here.


def test_no_variable_acquires_a_numeric_disambiguation_suffix():
    """A near-collision must not be renumbered.

    ``FOO`` was emitted as ``Foo2`` — a suffix it never carried in the source,
    invented only because ``Foo`` had already claimed ``Foo``.  This is the
    pair F022 could not have covered: it was written when TitleCase was a
    load-time error rather than a variable, so ``Foo`` beside ``FOO`` was not
    a shape anyone could write.
    """
    emitted = clausal_source_to_prolog("p(Foo, FOO) <- q(Foo, FOO)")
    assert "p(Foo, FOO) :-" in emitted
    assert "Foo2" not in emitted
    assert len(set(_prolog_var_names(emitted))) == 2, emitted


# ── Round-trip fidelity ───────────────────────────────────────────────

def test_round_trip_preserves_every_variable_spelling():
    """Clausal -> .pl -> Clausal returns the source spellings exactly.

    One clause carrying every shape at once, on purpose: a per-clause rename
    table that renumbers would survive a one-name-per-test suite and die here.
    """
    source = "p(Foo, FOO, N0, _x, _) <- q(Foo, FOO, N0, _x, _)"
    returned = prolog_to_clausal(clausal_source_to_prolog(source))
    assert returned.strip() == "p(Foo, FOO, N0, _x, _) <- (q(Foo, FOO, N0, _x, _))"


# ── The wildcard ──────────────────────────────────────────────────────

def test_wildcard_stays_anonymous_in_both_directions():
    """``_`` is identity because ISO and Clausal AGREE on it, not by default.

    In both languages every occurrence of ``_`` is an independent fresh
    variable.  Identity is therefore right — and the failure mode to guard
    is the opposite one: a rename table that gave ``_`` a name would make two
    occurrences in one clause the SAME variable and change what the clause
    means.  So the assertion is that ``_`` stays spelled ``_`` every time it
    appears, never numbered and never named.
    """
    emitted = clausal_source_to_prolog("p(_, _) <- q(_, _)")
    assert "p(_, _) :-" in emitted
    assert "q(_, _)" in emitted
    assert set(_prolog_var_names(emitted)) == {"_"}, emitted

    returned = prolog_to_clausal("p(_, _) :- q(_, _).")
    assert returned.strip() == "p(_, _) <- (q(_, _))"


# ── The singleton pass must not undo injectivity ──────────────────────
#
# Deleting the rename table removed more than its stated purpose. Its OUTPUT
# had a property that a different pass silently relied on: every emitted base
# name was distinct, and none was underscore-led (the old mangler stripped
# leading underscores). ``_prefix_singletons`` renames a singleton to
# ``"_" + name`` without checking the target is free, which was safe only
# because that property held. Under identity it does not: a source can carry
# both ``X`` and ``_X``.

def test_singleton_prefix_does_not_collide_with_a_live_variable():
    """The bug this file exists to prevent, arriving through another door.

    ``X`` occurs once so the singleton pass wants to call it ``_X``; ``_X``
    already names a DIFFERENT variable in the same clause. Prefixing would
    unify the head's two arguments — a silent wrong answer of exactly the
    F022 kind, produced by a pass that never mapped names at all.

    The pass must decline. The ISO singleton warning it exists to silence is
    worth strictly less than a correct program.
    """
    emitted = clausal_source_to_prolog("p(X, _X) <- (q(_X))")
    assert "p(X, _X) :-" in emitted, emitted
    assert len(set(_prolog_var_names(emitted))) == 2, emitted


def test_singleton_prefix_declines_rather_than_building_a_constant_name():
    """``X_`` is a legal Clausal variable; ``_X_`` is a module constant.

    Prefixing a trailing-underscore singleton emits a name that is not a
    variable on the way back, so a file that loaded fine exports to a `.pl`
    whose re-import will not load. The inbound trailing-underscore strip used
    to absorb this; nothing does now, so the pass must not create it.
    """
    emitted = clausal_source_to_prolog("p(X_, Y) <- (q(Y))")
    assert "p(X_, Y) :-" in emitted, emitted
    assert "_X_" not in emitted, emitted
    # and the round trip survives
    assert prolog_to_clausal(emitted).strip() == "p(X_, Y) <- (q(Y))"


def test_singleton_prefixing_still_happens_when_it_is_safe():
    """Positive control: the two guards above must not disable the pass.

    A test that only checked declining would pass on a pass that never fired.
    """
    emitted = clausal_source_to_prolog(
        "schedule(high, DEPENDENCE, low) <- (q(1))")
    assert "_DEPENDENCE" in emitted, emitted
