"""Regression tests for the P3-1 atom-pivot's missed call-site in
``clausal/logic/compiler/arg_index.py::_arg_to_index_key``.

Diagnosis: a rule head naming an atom IMPORTED from another module, in a
predicate with >= ``arg_index._INDEX_THRESHOLD`` (4) clauses, called with
that argument BOUND, silently lost its clause -- the compile-time index key
still used the pre-pivot ``(name, 0)`` PredicateMeta-class convention while
the post-pivot runtime key for a plain-string atom is the string itself.
Bucket mismatch -> the caller falls through to the bucket's DEFAULT clause
set (empty, or whichever var-headed clause happens to exist), producing
either zero solutions or a wrong answer. First-bad commit: P3-1's
``3cc2652a`` ("the lowering flip + minting stop"), which touched every
OTHER atom-key call-site but not ``arg_index.py``.

Fix: thread the compile-time namespace (``base_globals``) into
``_arg_to_index_key``'s LoadName/LoadAttr branch and key the RESOLVED VALUE
through ``_runtime_arg_key`` -- the same function a live runtime argument of
that value goes through -- rather than guessing a key from the reference's
spelling.  Unresolvable -> ``_INDEX_VAR`` (always-correct fallback: full
clause scan, still answers via ``unify()``).

These tests use REAL cross-module ``.clausal`` fixtures (mirroring the
corpus's own "vocabulary module + sibling rule module" idiom) so the
regression is pinned end-to-end, not just at the key-function level -- see
``tests/test_first_arg_index.py`` for the unit-level key-agreement coverage
(the -hide-mangled-atom and unresolvable-name cases, and the missing
key-agreement table row this bug's own gap in test coverage left behind).

Three DISTINCT importer shapes are covered, each a genuinely different AST
path through the fix: a bare single-hop ``-import_from``
(``TestBareImportedAtomHeadArg``), a literal dotted ``mod.attr`` reference
compiling to a ``LoadAttr`` chain (``TestDottedQualifiedAtomHeadArg``), and
the atom re-exported through a package ``__init__`` -- two import hops
(``TestPackageReexportedAtomHeadArg``, the diagnosis's own ``mini/`` shape).
"""

from __future__ import annotations

import os

from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import _load_module
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_owner() -> None:
    _load_module(
        "tests.fixtures.atom_index_owner",
        _fixture_path("atom_index_owner.clausal"),
    )


def _load_owner_bare() -> None:
    """Same source, registered under its BARE module name.

    Mirrors the working ``qualified_atom_vocab``/``qualified_atom_consumer``
    convention: ``-import_module(atom_index_owner)`` in the dotted-importer
    fixture resolves this bare registration, not the ``tests.fixtures.``
    dotted one -- keeping the LoadAttr-chain evaluation to a single level
    (unrelated multi-level ``tests.fixtures.X.Y`` value-reference quirk
    otherwise gets in the way; it is not part of the atom-pivot bug this
    file targets).
    """
    _load_module(
        "atom_index_owner",
        _fixture_path("atom_index_owner.clausal"),
    )


def _load_bare_importer() -> object:
    _load_owner()
    return _load_module(
        "tests.fixtures.atom_index_bare_importer",
        _fixture_path("atom_index_bare_importer.clausal"),
    )


def _load_dotted_importer() -> object:
    _load_owner_bare()
    return _load_module(
        "tests.fixtures.atom_index_dotted_importer",
        _fixture_path("atom_index_dotted_importer.clausal"),
    )


def _level_solutions(mod: object, n: int, atom_value) -> list:
    logic_mod = mod.__dict__["$module"]
    out = []
    for _ in call("level", n, atom_value, module=logic_mod):
        out.append(atom_value)
    return out


def _level_of(mod: object, n: int):
    """Query Level(n, L) with L unbound; return the resolved atom or None."""
    logic_mod = mod.__dict__["$module"]
    v = Var()
    results = []
    for _ in call("level", n, v, module=logic_mod):
        results.append(deref(v))
    return results


class TestBareImportedAtomHeadArg:
    """Item 1: the minimized corpus-shaped repro (bare ``-import_from``)."""

    def test_ground_call_reaches_the_matching_clause(self):
        mod = _load_bare_importer()
        # Each of the 4 rule clauses names a DIFFERENT imported atom in its
        # head. A ground call with the matching atom bound must reach
        # EXACTLY that clause (pre-fix: reached NONE -- zero solutions).
        assert _level_of(mod, 1) == [mint("aa")]
        assert _level_of(mod, 2) == [mint("bb")]
        assert _level_of(mod, 3) == ["cc"]
        assert _level_of(mod, 4) == ["dd"]

    def test_ground_call_with_the_atom_supplied_by_the_caller(self):
        """Symmetric direction: caller supplies the atom value (as the
        bound 2nd argument) rather than reading it out -- this is exactly
        the shape the corpus escalation hit (``cdd_level(P, 'standard')``)."""
        mod = _load_bare_importer()
        assert _level_solutions(mod, 1, mint("aa")) == [mint("aa")]
        assert _level_solutions(mod, 4, "dd") == ["dd"]
        # A mismatched pairing must still correctly fail (not spuriously
        # succeed via some other clause's bucket).
        assert _level_solutions(mod, 1, "dd") == []


class TestDottedQualifiedAtomHeadArg:
    """Item 2: the same shape via a literal dotted qualified reference.

    ``-import_module`` + ``atom_index_owner.aa`` written directly in the
    rule head compiles to a ``LoadAttr`` CHAIN (``_dotted_name_from_loadattr``
    walks it to the same dotted string a bare cross-module reference's
    single ``LoadName`` already carries), a different AST shape than
    ``TestBareImportedAtomHeadArg`` exercises but the same key function
    and the same pre-fix bug (the old code guessed a key from the
    reference's spelling regardless of which AST shape it arrived in).
    """

    def test_ground_call_reaches_the_matching_clause(self):
        mod = _load_dotted_importer()
        assert _level_of(mod, 1) == [mint("aa")]
        assert _level_of(mod, 2) == [mint("bb")]
        assert _level_of(mod, 3) == ["cc"]
        assert _level_of(mod, 4) == ["dd"]

    def test_ground_call_with_the_atom_supplied_by_the_caller(self):
        mod = _load_dotted_importer()
        assert _level_solutions(mod, 1, mint("aa")) == [mint("aa")]
        assert _level_solutions(mod, 4, "dd") == ["dd"]
        assert _level_solutions(mod, 1, "dd") == []


def _load_pkg_reexport_importer() -> object:
    """Item 2 (as the diagnosis itself specified it, §9): the atom is
    re-exported through a package ``__init__`` -- TWO import hops
    (``tests.fixtures.atom_index_pkg.schema`` declares the atoms;
    ``tests.fixtures.atom_index_pkg/__init__.clausal`` re-exports them via
    its own ``-import_from``; this importer imports the PACKAGE, not the
    schema submodule directly). No pre-load of the package/schema is
    needed -- loading the importer module triggers the real Python import
    machinery (via the import hook) for both hops, same as any ordinary
    cross-module ``-import_from`` resolves its target.
    """
    return _load_module(
        "tests.fixtures.atom_index_pkg_reexport_importer",
        _fixture_path("atom_index_pkg_reexport_importer.clausal"),
    )


class TestPackageReexportedAtomHeadArg:
    """Item 2, AS THE DIAGNOSIS SPECIFIED IT (§9's own regression-test list):
    "the same [imported-atom-head-arg] shape with the atom re-exported
    through a package ``__init__`` (two import hops)". This is the
    diagnosis's own ``mini/`` reproduction shape
    (``pkg/schema.clausal`` -> ``pkg/__init__.clausal`` re-export ->
    ``pkg.computation``'s bare use), reproduced here as a real fixture
    rather than referenced only from the diagnosis's scratch directory.

    (``TestDottedQualifiedAtomHeadArg`` above covers a DIFFERENT case --
    a literal dotted ``mod.attr`` reference, a single import hop -- which
    was substituted for this one in the fix's first pass; both are real,
    distinct regression shapes and both are now covered.)
    """

    def test_ground_call_reaches_the_matching_clause(self):
        mod = _load_pkg_reexport_importer()
        assert _level_of(mod, 1) == [mint("aa")]
        assert _level_of(mod, 2) == [mint("bb")]
        assert _level_of(mod, 3) == ["cc"]
        assert _level_of(mod, 4) == ["dd"]

    def test_ground_call_with_the_atom_supplied_by_the_caller(self):
        mod = _load_pkg_reexport_importer()
        assert _level_solutions(mod, 1, mint("aa")) == [mint("aa")]
        assert _level_solutions(mod, 4, "dd") == ["dd"]
        assert _level_solutions(mod, 1, "dd") == []

    def test_the_two_hop_reference_is_genuinely_indexed(self):
        """Not just correct -- actually reaches a real per-atom bucket
        (``arg_index._build_arg_index`` returns 4 distinct string-keyed
        buckets for this position), matching what
        ``TestBareImportedAtomHeadArg`` demonstrates for the single-hop
        shape. Verified by driving the compiler directly rather than
        trusting the dispatch-function's own ``__globals__`` after the
        fact (that inspects a different, already-pruned dict and gives a
        false negative -- see the corrected residual-perf paragraph in
        .hotfix-report.md for how that misread the single-hop shape
        during the first pass of this fix).
        """
        import clausal.logic.compiler.arg_index as ai
        import clausal.logic.compiler.predicate as pred_mod

        seen = {}
        orig_build = ai._build_arg_index

        def traced(clauses, arity, pos, threshold=ai._INDEX_THRESHOLD, env=None):
            result = orig_build(clauses, arity, pos, threshold, env)
            if arity == 2 and pos == 1:
                seen["result"] = result
            return result

        ai._build_arg_index = traced
        pred_mod._build_arg_index = traced
        try:
            _load_pkg_reexport_importer()
        finally:
            ai._build_arg_index = orig_build
            pred_mod._build_arg_index = orig_build

        assert seen.get("result") is not None, (
            "expected a real index at position 1 -- got None (unindexed fallback)"
        )
        assert sorted(seen["result"]["buckets"].keys()) == [mint("aa"), mint("bb"), "cc", "dd"]
        assert seen["result"]["n_distinct"] == 4
