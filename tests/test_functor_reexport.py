"""End-to-end regression tests: re-exporting an ``-import_from``'d functor
by listing it in the importer's own ``-module`` export list.

Background
----------
``todo/done/module-reexport-imported-functor-shadows.md`` reported that a module
which BOTH imports a functor and lists it in its ``-module`` export gets a
fresh, distinct predicate class — silently shadowing the import so a
downstream ``-import_from`` of the "re-exported" functor finds nothing.

Investigation (2026-07-22) showed the engine already does the right thing:
``compiler_v2._process_declarations`` only mints a fresh module-local class
when no class exists *or* the existing binding is the process-global default
(``existing is global_cls``).  An imported functor is module-local — never the
global default — so it is preserved, and listing it in ``-module`` re-exports
it with **shared class identity**.

The pre-existing ``test_atom_shadowing.py`` suite exercises the *narrowed
shadowing warning* by running ``_process_declarations`` in isolation, so it
never binds an actual imported class and cannot observe the identity outcome.
These tests close that gap: they load real modules through the import hook and
assert identity is shared and solutions flow across a ``vocab → queries →
downstream`` re-export chain.

If someone ever changes the narrowed trigger to re-mint predicate functors
(believing that matches the atom behavior), these tests fail loudly.
"""

from __future__ import annotations

import os

from clausal.logic.atoms import mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_fixture(stem: str) -> object:
    return _load_module(
        f"tests.fixtures.{stem}", _fixture_path(f"{stem}.clausal")
    )


def _solutions(pred_cls, arity: int):
    """Enumerate all solutions of a predicate as tuples of atom names.

    Bare atoms (e.g. ``a``, ``x``) reify to zero-arity ``PredicateMeta``
    classes whose ``str()`` is the atom name, so stringifying gives a stable,
    readable value to assert against.
    """
    args = [Var() for _ in range(arity)]
    out = []
    for _ in call(pred_cls, *args):
        out.append(tuple(walk(deref(a)) for a in args))
    return out


class TestFunctorReExport:
    """Listing an imported functor in ``-module`` re-exports it (shared class
    identity), rather than shadowing the import with a fresh empty class."""

    def test_intermediate_shares_identity_with_kit(self):
        vocab = _load_fixture("functor_reexport_vocab")
        queries = _load_fixture("functor_reexport_queries")

        assert isinstance(vocab.flip, PredicateMeta)
        # Re-declaring the imported functor in -module must NOT re-mint.
        assert queries.flip is vocab.flip
        # The re-exported class carries the vocab's clauses, not an empty class.
        assert len(queries.flip._state_row().clauses) == 2

    def test_downstream_import_resolves_to_kit_class(self):
        vocab = _load_fixture("functor_reexport_vocab")
        _queries = _load_fixture("functor_reexport_queries")
        downstream = _load_fixture("functor_reexport_downstream")

        # A downstream -import_from of the re-exported functor resolves to the
        # vocab's class through the intermediate module.
        assert downstream.flip is vocab.flip

    def test_downstream_query_sees_kit_facts(self):
        _kit = _load_fixture("functor_reexport_vocab")
        _queries = _load_fixture("functor_reexport_queries")
        downstream = _load_fixture("functor_reexport_downstream")

        # The whole point: goals over the re-exported functor find the vocab's
        # facts rather than silently finding nothing.
        assert _solutions(downstream.check, 2) == [(mint("a"), mint("x")), (mint("b"), mint("y"))]

    def test_intermediate_clause_uses_reexported_functor(self):
        _kit = _load_fixture("functor_reexport_vocab")
        queries = _load_fixture("functor_reexport_queries")

        # A clause in the intermediate module that uses the imported functor
        # also resolves to the vocab's class.
        assert _solutions(queries.my_query, 1) == [(mint("x"),), (mint("y"),)]
