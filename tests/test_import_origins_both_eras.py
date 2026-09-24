"""F1 rows 27/29: the load channel's ``-import_from`` resolution, in BOTH eras.

Today an imported predicate's module-dict binding is a ``PredicateMeta``
class; after the flip it is a mangled atom.  Measured 2026-09-24 over the
house suite, no real load produces the mangled shape yet (0 of 2,079
non-class ``-import_from`` bindings is a declared predicate), so the atom
path is exercised here by building the binding directly against a REALLY
loaded owner, then checking it gives the SAME answers as the class.

Each check also asserts its population is non-empty: a resolver that quietly
answers ``None`` for both shapes would otherwise "agree" with itself.
"""

from __future__ import annotations

import os
import sys

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.import_diagnostics import describe_imported_predicate_redefinition
from clausal.logic.atoms import mangle
from clausal.logic.compiler_v2 import (
    _import_from_origins, _imported_binding,
    _imported_binding_by_canonical_name,
)
from clausal.logic.database import Database
from clausal.logic.predicate import (
    PredicateMeta, predicate_binding_name, resolve_predicate_row,
)
from clausal.pythonic_ast.nodes import ImportFromDirective

FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")

# Loaded under the name the mangled spelling carries, so the atom resolves
# through a real Database -- no monkeypatch.
_OWNER = "_rows2729_impclob_owner"


@pytest.fixture(scope="module")
def owner():
    sys.modules.pop(_OWNER, None)
    module = _load_module(_OWNER, os.path.join(FIXTURES,
                                               "impclob_owner.clausal"))
    yield module
    sys.modules.pop(_OWNER, None)


def _eras(owner):
    """The same predicate, ``impclob_colour/1``, in both binding shapes."""
    cls = owner.__dict__["impclob_colour"]
    assert isinstance(cls, PredicateMeta)
    return {"class": cls, "mangled": mangle(_OWNER, "impclob_colour")}


def _aliased_import():
    return [ImportFromDirective(
        module=_OWNER, names=[("impclob_colour", "hue")])]


def test_the_own_name_of_an_aliased_binding_is_read_in_both_eras(owner):
    for era, binding in _eras(owner).items():
        assert predicate_binding_name(binding) == "impclob_colour", era


def test_a_data_atom_or_unloaded_module_has_no_predicate_name(owner):
    assert predicate_binding_name("impclob_colour") is None      # plain str
    assert predicate_binding_name(mangle(_OWNER, "red")) is None  # data atom
    assert predicate_binding_name(
        mangle("_rows2729_not_loaded", "impclob_colour")) is None
    assert predicate_binding_name(None) is None


def test_origins_index_an_aliased_import_under_both_names_in_both_eras(owner):
    """Row 27.  Without the own-name entry the clause head's functor reaches
    nothing and the clobber refusal is skipped."""
    rows = {}
    for era, binding in _eras(owner).items():
        origins = _import_from_origins(_aliased_import(), {"hue": binding})
        assert set(origins) == {"hue", "impclob_colour"}, era
        assert origins["impclob_colour"] == (_OWNER, binding), era
        rows[era] = resolve_predicate_row(
            _imported_binding(origins, "impclob_colour"), arity=1)
    assert rows["class"] is not None
    assert rows["class"] is rows["mangled"]
    assert rows["class"].clauses, "the owner's row is empty: nothing compared"


def test_origins_keep_a_non_predicate_import_unbound(owner):
    origins = _import_from_origins(
        [ImportFromDirective(module=_OWNER, names=["red"])],
        {"red": mangle(_OWNER, "red")})
    assert origins == {"red": (_OWNER, None)}


def test_the_canonical_name_lookup_agrees_in_both_eras(owner):
    """Row 29, step 4a's lookup: foreign + arity-exact in both eras."""
    importer_db = Database()
    found = {}
    for era, binding in _eras(owner).items():
        origins = _import_from_origins(_aliased_import(), {"hue": binding})
        found[era] = _imported_binding_by_canonical_name(
            origins, importer_db, "impclob_colour", 1)
        assert _imported_binding_by_canonical_name(
            origins, importer_db, "impclob_colour", 2) is None, era
        owner_db = resolve_predicate_row(binding, arity=1).db
        assert _imported_binding_by_canonical_name(
            origins, owner_db, "impclob_colour", 1) is None, (
            f"{era}: the owner's own database is not foreign to it")
    assert found["class"] is _eras(owner)["class"]
    assert found["mangled"] == _eras(owner)["mangled"]


def test_the_redefinition_diagnostic_says_the_same_in_both_eras(owner):
    """Row 29's diagnostic consumer.  Reading ``_row`` off a mangled atom with
    ``getattr`` gave None without raising, so the message would have said
    "0 clauses, not recorded" -- silently wrong.  Only the declaration-site
    line is class-only, and it is passed separately."""
    texts = {}
    for era, binding in _eras(owner).items():
        texts[era] = describe_imported_predicate_redefinition(
            "impclob_colour", 1, "some_importer", _OWNER,
            resolve_predicate_row(binding, arity=1),
            exporter_module=owner)
    assert texts["class"] == texts["mangled"]
    assert "the 2 clauses already on impclob_colour" in " ".join(
        texts["class"].split())


def test_the_load_channel_s_refusal_text_is_the_same_in_both_eras(owner):
    """End to end through ``_redefinition_error``, which is where the binding
    becomes a row."""
    from types import SimpleNamespace
    from clausal.logic.compiler_v2 import _redefinition_error
    gate = SimpleNamespace(term=SimpleNamespace(args=(None, "GATE LINE")))
    texts = {}
    for era, binding in _eras(owner).items():
        origins = _import_from_origins(_aliased_import(), {"hue": binding})
        texts[era] = str(_redefinition_error(
            gate, "impclob_colour", 1, binding, origins, "some_importer",
            {_OWNER: owner}))
    # No declaration-site line in either era (ruling B, 2026-09-24), so the
    # two texts match verbatim.
    assert " is declared at " not in texts["class"]
    assert texts["class"] == texts["mangled"]
    assert "the 2 clauses already on impclob_colour" in " ".join(
        texts["mangled"].split())


def test_the_load_refusal_fires_through_the_real_gate_in_both_eras(owner):
    """End to end through ``_refuse_foreign_writes``: an importer that writes
    a clause for the aliased import is refused by ``Database.refusal_for``
    with ``through=`` the binding, and says the same thing in both eras.  An
    unresolved ``through=`` would let the write pass silently."""
    from types import SimpleNamespace
    from clausal.logic.compiler_v2 import _refuse_foreign_writes
    from clausal.terms import Compound
    node = SimpleNamespace(head=Compound("impclob_colour", ("teal",)))
    strip = lambda t: t     # nothing era-specific left (ruling B)
    texts = {}
    for era, binding in _eras(owner).items():
        origins = _import_from_origins(_aliased_import(), {"hue": binding})
        with pytest.raises(SyntaxError) as exc_info:
            _refuse_foreign_writes(Database(), [node], {_OWNER: owner},
                                   origins, "/elsewhere/importer.clausal",
                                   "some_importer")
        texts[era] = strip(str(exc_info.value))
    assert texts["class"] == texts["mangled"]
    assert " is declared at " not in texts["class"]
    assert "may not write impclob_colour/1" in texts["mangled"]
