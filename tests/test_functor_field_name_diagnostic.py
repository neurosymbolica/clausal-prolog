"""Attributable diagnostics for functor field-name mismatches.

``todo/functor-field-name-mismatch-diagnostic.md`` — constructing a term whose
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
    PredicateMeta,
    make_predicate,
)


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


# ── Unit level: the raise site itself ──────────────────────────────────────


class TestConstructionErrorShape:
    """The error is a TypeError subclass carrying structured attributes."""

    def test_is_a_type_error(self):
        assert issubclass(ClausalTermConstructionError, TypeError)

    def test_names_functor_arity_and_both_field_tuples(self):
        cls = make_predicate("fnd_verdict", ["status", "citations"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(arg_0="ok", arg_1=[])
        msg = str(exc_info.value)
        assert "fnd_verdict/2" in msg
        assert "(arg_0, arg_1)" in msg
        assert "(status, citations)" in msg

    def test_carries_structured_attributes(self):
        cls = make_predicate("fnd_pair", ["left", "right"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(alpha=1, beta=2)
        err = exc_info.value
        assert err.functor == "fnd_pair"
        assert err.arity == 2
        assert err.supplied_fields == ("alpha", "beta")
        assert err.registered_fields == ("left", "right")

    def test_reports_the_construction_source_location(self):
        cls = make_predicate("fnd_where", ["only"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(nope=1)
        msg = str(exc_info.value)
        assert "constructed at:" in msg
        assert os.path.basename(__file__) in msg

    def test_registered_location_is_recorded_on_the_class(self):
        cls = make_predicate("fnd_regsite", ["only"])
        assert isinstance(cls._registered_at, tuple)
        filename, lineno = cls._registered_at
        assert os.path.basename(__file__) == os.path.basename(filename)
        assert lineno > 0

    def test_matching_field_names_still_construct(self):
        cls = make_predicate("fnd_ok", ["left", "right"])
        term = cls(left=1, right=2)
        assert term.left == 1 and term.right == 2

    def test_unrelated_type_error_is_not_swallowed(self):
        """A TypeError whose kwargs all ARE fields is re-raised untouched."""

        class fnd_raiser(metaclass=PredicateMeta):
            _fields = ("boom",)

        def _explode(self, boom=None):
            raise TypeError("something else entirely")

        fnd_raiser.__init__ = _explode
        with pytest.raises(TypeError) as exc_info:
            fnd_raiser(boom=1)
        assert not isinstance(exc_info.value, ClausalTermConstructionError)
        assert "something else entirely" in str(exc_info.value)


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

    def test_loading_the_pair_now_succeeds(self):
        schema = _load_module(
            "tests.fixtures.fnmismatch_schema",
            os.path.join(FIXTURES, "fnmismatch_schema.clausal"),
        )
        use = _load_module(
            "tests.fixtures.fnmismatch_use",
            os.path.join(FIXTURES, "fnmismatch_use.clausal"),
        )
        # The import wins the binding, and the local field spellings no longer
        # contradict it.
        assert use.fnm_verdict is schema.fnm_verdict
        assert use.fnm_verdict._fields == ("arg_0", "arg_1")


# ── Cause 2 (Phenomenon A): imported atom shadows a same-named predicate ───


class TestAtomShadowsPredicate:
    """``-module(m, [key(A, B)])`` + ``-import_from(v, [key])`` binds the atom
    last, so ``key(A, B)`` constructs the 0-arity atom.

    Since heads for an imported functor are emitted positionally, this arrives
    through the positional-overflow check rather than the keyword path — an
    ARITY disagreement, which is exactly what a genuine cross-module conflict
    reduces to.  The attribution and the Phenomenon-A hint are unchanged.
    """

    def test_loading_the_pair_names_the_atom_shadowing_cause(self):
        _load_module(
            "tests.fixtures.atomshadow_schema",
            os.path.join(FIXTURES, "atomshadow_schema.clausal"),
        )
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            _load_module(
                "tests.fixtures.atomshadow_use",
                os.path.join(FIXTURES, "atomshadow_use.clausal"),
            )
        msg = str(exc_info.value)
        assert "ash_query_key/0" in msg
        assert "2 positional argument(s)" in msg
        assert "0 field(s) ()" in msg
        assert "atomshadow_schema.clausal:" in msg
        assert "atomshadow_use.clausal:" in msg
        # which class of mistake — named explicitly, with a remedy
        assert "0-arity atom" in msg
        assert "shadow" in msg
        assert "un-export" in msg
        # and it is NOT diagnosed as the placeholder case
        assert "-dynamic" not in msg

    def test_atom_cause_is_detected_at_unit_level_too(self):
        atom = make_predicate("fnd_bare_atom", [])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            atom(PROFILE=1, VALUE=2)
        msg = str(exc_info.value)
        assert "fnd_bare_atom/0" in msg
        assert "0-arity atom" in msg
        assert "-dynamic" not in msg


class TestCauseDiscrimination:
    """Neither hint fires for a plain rename mismatch."""

    def test_generic_mismatch_gets_neither_specific_hint(self):
        cls = make_predicate("fnd_generic", ["left", "right"])
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            cls(alpha=1, beta=2)
        msg = str(exc_info.value)
        assert "0-arity atom" not in msg
        assert "arg_N" not in msg
        # but it still says what and where
        assert "fnd_generic/2" in msg
        assert "constructed at:" in msg
