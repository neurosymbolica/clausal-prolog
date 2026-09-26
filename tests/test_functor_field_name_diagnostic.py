"""Attributable diagnostics for functor field-name mismatches.

``todo/done/functor-field-name-mismatch-diagnostic.md`` — constructing a term whose
keyword-argument names do not match the bound class's ``_fields`` used to raise
a bare, context-free::

    TypeError: __init__() got an unexpected keyword argument 'arg_1'

with no functor, no field names and no source location, which makes it
unrepairable by a machine author.  ``PredicateMeta.__call__`` now re-raises a
``ClausalTermConstructionError`` naming the functor, both field-name tuples,
where the class was registered, where the construction happened, and which of
the two known causes it is:

* placeholder ``arg_N`` names on one side → a directive-minted class
  (``-dynamic``) that no real clause unseated, colliding with a
  clause/export-derived registration of the same functor;
* logic-variable-shaped kwargs against a 0-arity class → "Phenomenon A", an
  imported atom shadowing a same-named predicate
  (``implementation_plans/dict-atom-keys-vs-predicates.md``).
"""

from __future__ import annotations

import os

import pytest

from clausal.import_hook import _load_module
from clausal.logic.predicate import (
    ClausalTermConstructionError,
)
# W4b-3 slice 7: the PredicateMeta class is deleted; ``build_term_cell`` is
# the one raise site, reached here through ``term_ctor`` (which records its
# creation site as the "registered by:" line, as a declaration does).
from tests.predicate_api_support import term_ctor


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ── Unit level: the raise site itself ──────────────────────────────────────


def _cf(term, cls, name):
    """The value of field *name* in a term CELL built from *cls*.

    P2: construction yields a functor and POSITIONS; the field names stay on
    the class that declared them."""
    from clausal.logic.cells import cell_args
    return cell_args(term)[cls._fields.index(name)]


class TestConstructionErrorShape:
    """The error is a TypeError subclass carrying structured attributes."""

    def test_is_a_type_error(self):
        assert issubclass(ClausalTermConstructionError, TypeError)

    def test_names_functor_arity_and_both_field_tuples(self):
        cls = term_ctor("fnd_verdict", ["status", "citations"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(arg_0="ok", arg_1=[])
        msg = str(exc_info.value)
        assert "fnd_verdict/2" in msg
        assert "(arg_0, arg_1)" in msg
        assert "(status, citations)" in msg

    def test_carries_structured_attributes(self):
        cls = term_ctor("fnd_pair", ["left", "right"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(alpha=1, beta=2)
        err = exc_info.value
        assert err.functor == "fnd_pair"
        assert err.arity == 2
        assert err.supplied_fields == ("alpha", "beta")
        assert err.registered_fields == ("left", "right")

    def test_reports_the_construction_source_location(self):
        cls = term_ctor("fnd_where", ["only"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(nope=1)
        msg = str(exc_info.value)
        assert "constructed at:" in msg
        assert os.path.basename(__file__) in msg

    def test_the_registered_location_names_the_declaring_file(self):
        cls = term_ctor("fnd_regsite", ["only"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(nope=1)
        assert isinstance(exc_info.value.registered_at, tuple)
        filename, lineno = exc_info.value.registered_at
        assert os.path.basename(__file__) == os.path.basename(filename)
        assert lineno > 0

    def test_matching_field_names_still_construct(self):
        cls = term_ctor("fnd_ok", ["left", "right"])
        term = cls(left=1, right=2)
        assert _cf(term, cls, "left") == 1 and _cf(term, cls, "right") == 2


# ── Cause 1: directive-minted arg_N placeholders vs derived names ──────────


class TestDirectiveMintedPlaceholderMismatch:
    """A ``-dynamic``-minted class keeps ``arg_N`` names until a clause unseats
    it, so a sibling module that declares the same functor and imports it used
    to construct the foreign class with its own field names.

    That no longer raises: a head for a functor the same file imports is
    emitted POSITIONALLY, because field names are a module-local labelling of
    slots while arity is the cross-module contract
    (``tests/test_functor_import_ordering.py``).  The unit-level tests above
    still cover the message, which stays reachable through genuine arity
    conflicts — see ``TestAtomShadowsPredicate`` for one end to end.
    """

    def test_loading_the_pair_no_longer_raises_the_field_name_error(self):
        """The module body runs (the head is positional), so no
        ``ClausalTermConstructionError``.  The load itself is then REFUSED
        since 2026-09-24 -- ``fnmismatch_use`` supplies clauses for a
        predicate ``fnmismatch_schema`` only declares, the dropped
        "vocabulary-implements" idiom -- so what this pins is WHICH error
        stops it: the step-3d ``SyntaxError``, never the field-name one.
        (It used to assert that the pair loads and shares the schema's
        class; both were the idiom.)"""
        schema = _load_module(
            "tests.fixtures.fnmismatch_schema",
            os.path.join(FIXTURES, "fnmismatch_schema.clausal"),
        )
        # W4b-2d: the exporter's field names are read off its Database row
        # (the placeholder CLASS is gone -- the binding is a handle).
        from clausal.logic.predicate import field_names_for
        schema_db = schema.__dict__["$module"].db
        names_before = schema_db.field_names_at("fnm_verdict", 2)
        assert names_before is not None and len(names_before) == 2
        assert field_names_for(schema.fnm_verdict) == names_before
        with pytest.raises(SyntaxError) as exc_info:
            _load_module(
                "tests.fixtures.fnmismatch_use",
                os.path.join(FIXTURES, "fnmismatch_use.clausal"),
            )
        assert not isinstance(exc_info.value, ClausalTermConstructionError)
        assert "only declares fnm_verdict/2" in " ".join(
            str(exc_info.value).split())
        # The exporter's predicate is untouched by the refused load.
        assert schema_db.field_names_at("fnm_verdict", 2) == names_before
        assert field_names_for(schema.fnm_verdict) == names_before
        assert not schema_db.row("fnm_verdict", 2).clauses


# ── Cause 2 (Phenomenon A): imported atom shadows a same-named predicate ───


class TestAtomShadowsPredicate:
    """P3-1 §3a/§1b/R2 INVERSION: "Phenomenon A" (a same-named 0-arity atom
    import colliding with an N-arity predicate export, import binding last)
    dies outright rather than being diagnosed.

    Pre-pivot, the import bound the name to a zero-field ``PredicateMeta``
    atom CLASS, and calling it with keyword arguments raised a
    ``ClausalTermConstructionError`` naming the "0-arity atom shadows a
    predicate" cause specifically (``PredicateMeta.__call__``'s
    Phenomenon-A hint).  Atoms are now global-by-spelling interned strs: the
    import binds the name to the plain str ``"ash_query_key"``, and the
    clause head's attempted construction ``ash_query_key(P, V)`` is just
    calling a str, which raises Python's own ``TypeError`` — there is no
    ``PredicateMeta.__call__`` in the picture at all any more to attribute a
    custom diagnostic to.
    """

    def test_loading_the_pair_raises_a_plain_type_error(self):
        _load_module(
            "tests.fixtures.atomshadow_schema",
            os.path.join(FIXTURES, "atomshadow_schema.clausal"),
        )
        # Stage 2: the atom binding is the plain str.
        with pytest.raises(TypeError, match="'str' object is not callable"):
            _load_module(
                "tests.fixtures.atomshadow_use",
                os.path.join(FIXTURES, "atomshadow_use.clausal"),
            )

    def test_atom_cause_is_detected_at_unit_level_too(self):
        atom = term_ctor("fnd_bare_atom", [])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            atom(PROFILE=1, VALUE=2)
        msg = str(exc_info.value)
        assert "fnd_bare_atom/0" in msg
        assert "0-arity atom" in msg
        assert "-dynamic" not in msg


class TestCauseDiscrimination:
    """Neither hint fires for a plain rename mismatch."""

    def test_generic_mismatch_gets_neither_specific_hint(self):
        cls = term_ctor("fnd_generic", ["left", "right"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(alpha=1, beta=2)
        msg = str(exc_info.value)
        assert "0-arity atom" not in msg
        assert "arg_N" not in msg
        # but it still says what and where
        assert "fnd_generic/2" in msg
        assert "constructed at:" in msg
