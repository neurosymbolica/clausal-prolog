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
  it coming back is to count distinct names, not to read them.
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


def test_previously_colliding_pair_stays_distinct_through_the_export():
    """``_result`` and ``RESULT`` in one clause survive as two variables.

    This is the centrepiece.  Under the old mangler the emitted clause read
    ``p(Result, Result2) :- q(Result, Result2).`` — correct only because the
    uniquifier renamed the second one.  Under identity no rename happens, so
    the assertion is on both the answer and the count.
    """
    emitted = clausal_source_to_prolog("p(_result, RESULT) <- q(_result, RESULT)")
    assert "p(_result, RESULT) :-" in emitted
    assert "q(_result, RESULT)" in emitted
    assert len(set(_prolog_var_names(emitted))) == 2, emitted


def test_no_variable_acquires_a_numeric_disambiguation_suffix():
    """A near-collision must not be renumbered.

    ``FOO`` was emitted as ``Foo2`` — a suffix it never carried in the source,
    invented only because ``Foo`` had already claimed ``Foo``.  Nothing in the
    emitted clause may now differ from the source spelling.
    """
    emitted = clausal_source_to_prolog("p(Foo, FOO) <- q(Foo, FOO)")
    assert "p(Foo, FOO) :-" in emitted
    assert "Foo2" not in emitted


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
