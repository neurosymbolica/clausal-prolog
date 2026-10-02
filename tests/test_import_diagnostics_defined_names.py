"""``_defined_names`` (``import_diagnostics.py``, the "what may I import from
here" fallback for a module with no ``-module(...)`` directive) must select
the right population in BOTH eras: a ``PredicateMeta`` CLASS today, and a
module-qualified MANGLED ATOM (a plain ``str``, ``"module\\x1fname"``) after
the PredicateMeta retirement flip (W4b-2d).

``implementation_plans/w4b2-f2b-and-hard-families-2026-09-23.md`` F9
proposes filtering on ``is_mangled(value)`` "instead" of
``isinstance(value, PredicateMeta)`` -- taken literally that is wrong: TODAY
every binding is still a class, so an ``is_mangled``-only filter selects
NOTHING until the flip happens, and the diagnostic goes silently empty (no
test would notice, because a diagnostic that says nothing raises nothing).
The filter actually used below is ``is_declared_predicate_name`` (era-
agnostic: True for a ``PredicateMeta`` class OR a mangled atom naming a
declared predicate; False for anything else, including a plain string or a
mangled atom naming a DATA atom) -- see the module-level comment in
``import_diagnostics.py`` above ``_defined_names`` for the full rationale.

The non-negotiable: ``test_positive_control_*`` below assert the returned
list is NON-EMPTY and names exactly the expected predicates, in each era --
so a future change that empties this filter fails a test instead of quietly
shipping a blank diagnostic.
"""
from __future__ import annotations

import dataclasses
import os
import sys
import types

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.import_diagnostics import _defined_names
from clausal.logic.atoms import mangle

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture(name: str) -> str:
    return os.path.join(FIXTURES, name)


def _load_impexp_nomodule():
    """The real ``impexp_nomodule.seam`` fixture (no ``-module(...)``
    directive, two real predicates: ``impexp_nm_alpha/1``,
    ``impexp_nm_beta/2``) -- today's era, a genuinely loaded module whose
    own bindings are ``PredicateMeta`` classes."""
    modname = "_f9_defined_names_nomodule"
    sys.modules.pop(modname, None)
    return _load_module(modname, _fixture("impexp_nomodule.seam"))


def _load_hide_owner():
    """The real ``-hide`` fixture (``-module(hide_owner, [holds/1, label/1,
    same/2])``), loaded under sys.modules key ``"hide_owner"`` -- matching
    the module name ``mangle("hide_owner", ...)`` uses, so a mangled atom
    built against it resolves through a REAL Database, no monkeypatch
    anywhere (same pattern as ``test_w4b2b_binding_resolver.py``)."""
    return _load_module("hide_owner", _fixture("hide_owner.seam"))


# ── Positive control: class era (today) ─────────────────────────────────────


def test_positive_control_class_era_returns_the_modules_own_predicates():
    """NON-NEGOTIABLE: the population must not be empty, and must be
    exactly the module's own two predicates -- nothing from the pre-seeded
    ``predicate_builtins`` pool (``module_dict.update(predicate_builtins)``
    at exec start seeds every loaded module's namespace with the ENTIRE
    global atom pool) leaks through."""
    mod = _load_impexp_nomodule()
    entries = _defined_names(mod)
    assert entries, "population must not be empty"
    assert entries == [
        ("impexp_nm_alpha", "impexp_nm_alpha/1"),
        ("impexp_nm_beta", "impexp_nm_beta/2"),
    ]


# ── Positive control: mangled-atom era (post W4b-2d flip) ──────────────────


def test_positive_control_mangled_era_returns_the_modules_own_predicates():
    """Simulates the post-flip shape directly: a fake module namespace whose
    predicate bindings are mangled atoms (not classes), naming predicates in
    a REAL, separately loaded Clausal module (``hide_owner``).  This is the
    exact case F9's literal ``is_mangled``-only filter would still get
    right -- the failure mode this suite guards is the CLASS era going
    empty under that filter, not this one."""
    _load_hide_owner()
    fake_mod = types.ModuleType("hide_owner")
    fake_mod.holds = mangle("hide_owner", "holds")
    fake_mod.label = mangle("hide_owner", "label")
    fake_mod.same = mangle("hide_owner", "same")
    entries = _defined_names(fake_mod)
    assert entries, "population must not be empty"
    assert entries == [
        ("holds", "holds/1"),
        ("label", "label/1"),
        ("same", "same/2"),
    ]


def test_mangled_era_arity_suffix_does_not_come_from_field_names_for():
    """``_defined_names`` must render the ``/N`` suffix from the ARITY, not
    from ``field_names_for(value) or ()``.  When this was written,
    ``field_names_for`` answered ``None`` for all three mangled names (an
    ordinary clause head never calls ``declare_functor``), so an arity read
    through it would have rendered ``"holds"`` instead of ``"holds/1"``.

    Since W4b-2d task 5 (2026-09-24), a handle answers what the class it
    replaces carries -- by name, the one arity's registered signature (the
    step-4 stamp of the head's names) -- so the three now AGREE with the
    class era instead of answering ``None``.  The ``/N`` pin below still
    holds, which is the point of this test."""
    from clausal.logic.predicate import field_names_for

    owner = _load_hide_owner()
    owner_db = owner.__dict__["$module"].db
    for name, arity in (("holds", 1), ("label", 1), ("same", 2)):
        # The class's ``_fields`` (pre-flip) is the row's registered
        # signature now: read it off the owner's Database.
        signature = owner_db.signature_for(name, arity)
        assert signature is not None and len(signature) == arity, name
        assert (field_names_for(mangle("hide_owner", name))
                == field_names_for(owner.__dict__[name])
                == signature), name
    fake_mod = types.ModuleType("hide_owner")
    fake_mod.same = mangle("hide_owner", "same")
    assert _defined_names(fake_mod) == [("same", "same/2")]


# ── False positives: must NOT appear in either era ──────────────────────────


class TestFalsePositives:
    """The exact hazard the brief's literal wording would create in the
    other direction: a filter too WIDE picks up a plain module-level
    constant and mislabels it as an importable predicate."""

    def test_plain_string_constant_excluded(self):
        mod = _load_impexp_nomodule()
        mod.impexp_nm_plain_string = "not a predicate"
        names = dict(_defined_names(mod))
        assert "impexp_nm_plain_string" not in names

    def test_int_constant_excluded(self):
        mod = _load_impexp_nomodule()
        mod.impexp_nm_int_const = 42
        names = dict(_defined_names(mod))
        assert "impexp_nm_int_const" not in names

    def test_imported_non_predicate_python_callable_excluded(self):
        mod = _load_impexp_nomodule()
        mod.impexp_nm_join = os.path.join
        names = dict(_defined_names(mod))
        assert "impexp_nm_join" not in names

    def test_bare_dataclass_class_excluded(self):
        """A data functor's class -- never a ``PredicateMeta`` instance and
        never mangled -- must not be mistaken for a predicate in either
        era."""
        @dataclasses.dataclass
        class NotAPredicate:
            x: int

        mod = _load_impexp_nomodule()
        mod.impexp_nm_data_functor = NotAPredicate
        names = dict(_defined_names(mod))
        assert "impexp_nm_data_functor" not in names

    def test_mangled_atom_naming_a_non_predicate_atom_excluded(self):
        """``hide_secret`` is HIDDEN, and -- per
        ``test_w4b2b_binding_resolver.py``'s own positive control -- is
        registered as neither ``"predicate"`` nor ``"data"`` anywhere in
        ``hide_owner``'s db.  A mangled atom naming it must not appear."""
        _load_hide_owner()
        fake_mod = types.ModuleType("hide_owner")
        fake_mod.hide_secret = mangle("hide_owner", "hide_secret")
        names = dict(_defined_names(fake_mod))
        assert "hide_secret" not in names

    def test_class_era_reexported_predicate_excluded(self):
        """A predicate class re-exported (``from other import p``) into a
        module's namespace must not be reported as THIS module's own --
        existing behaviour, pinned so the era-2 branch below cannot regress
        it while adding the mangled-atom analogue."""
        owner = _load_impexp_nomodule()
        importer = types.ModuleType("_f9_defined_names_importer")
        importer.imported_alpha = owner.impexp_nm_alpha
        names = dict(_defined_names(importer))
        assert "imported_alpha" not in names

    def test_mangled_era_reexported_predicate_excluded(self):
        """The mangled-atom analogue of the above: the handle's OWN module
        half names ``hide_owner``, not the importing namespace, so it must
        be excluded from a DIFFERENTLY-named module's listing."""
        _load_hide_owner()
        importer = types.ModuleType("_f9_defined_names_mangled_importer")
        importer.imported_holds = mangle("hide_owner", "holds")
        names = dict(_defined_names(importer))
        assert "imported_holds" not in names
