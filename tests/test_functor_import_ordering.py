"""Clause heads bind by POSITION when the functor is imported in the same file.

``todo/done/functor-field-name-mismatch-diagnostic.md`` — a module that both declares
a functor locally and ``-import_from``s the same name used to emit its clause
heads with the LOCAL field names against the FOREIGN class the import rebound:

    -module(use, [verdict(STATUS, CITATIONS)])   # mints _fields=(STATUS, CITATIONS)
    -import_from(schema, [verdict])              # rebinds verdict -> schema's class
    verdict("ok", [])                            # verdict(STATUS=…, CITATIONS=…) -> TypeError

Field names are a module-local *labelling of slots*; **arity** is the
cross-module contract.  So a head for a functor the same file imports is
emitted positionally: it binds against whatever class the import supplied, and
a module-local labelling can no longer contradict a foreign class.  A genuine
disagreement is an arity disagreement, which still raises — with full
attribution — from ``PredicateMeta.__call__``.

The narrowing matters: heads are emitted positionally only where the file does
NOT emit a guarded class block at the head itself.  Where it does (the first
clause of a functor), the block re-mints the class to exactly the derived
fields, so keyword emission is precise and is left alone — that is the shape
``tests/fixtures/impord_atom_then_pred.clausal`` pins (import a 0-arity
vocabulary atom, then define a same-named predicate).
"""

from __future__ import annotations

import ast
import os
import warnings

import pytest

from clausal.logic.atoms import char_atom, mint
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.predicate import ClausalTermConstructionError, PredicateMeta
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref, walk
from clausal.templating.term_rewriting import EmbedTransformer


FIXTURES = os.path.join(os.path.dirname(__file__), "fixtures")


def _fixture_path(stem: str) -> str:
    return os.path.join(FIXTURES, f"{stem}.clausal")


def _load_fixture(stem: str):
    return _load_module(f"tests.fixtures.{stem}", _fixture_path(stem))


def _solutions(pred_cls, arity: int):
    """All solutions of *pred_cls* as tuples of stringified bindings."""
    args = [Var() for _ in range(arity)]
    return [
        tuple(walk(deref(a)) for a in args)
        for _ in call(pred_cls, *args)
    ]


def _unparse(source: str) -> str:
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=SyntaxWarning)
        tree = ast.parse(source)
        rewritten = EmbedTransformer(
            source_lines=source.splitlines(), filename="t.clausal",
        ).visit(tree)
    ast.fix_missing_locations(rewritten)
    return ast.unparse(rewritten)


# ── Codegen: which heads become positional ─────────────────────────────────


class TestHeadEmission:
    def test_imported_functor_head_is_positional(self):
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "head=f((A := Var()), (B := Var()))" in out
        assert "STATUS=" not in out
        assert "CITATIONS=" not in out

    def test_local_only_functor_head_stays_keyword(self):
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "STATUS=" in out
        assert "CITATIONS=" in out

    def test_aliased_import_does_not_make_the_original_positional(self):
        """``alias(f, F2)`` binds F2, not f — f is still purely local."""
        out = _unparse(
            "-module(m, [f(STATUS, CITATIONS)])\n"
            "-import_from(other, [alias(f, Renamed)])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "STATUS=" in out
        assert "CITATIONS=" in out

    def test_first_clause_that_mints_its_own_class_stays_keyword(self):
        """No local declaration → the head emits its own class block, so the
        bound class is known exactly and keyword emission is precise."""
        out = _unparse(
            "-module(m, [])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
        )
        assert "a=" in out and "b=" in out

    def test_second_clause_after_a_local_mint_is_positional(self):
        """import-then-declare shape: the first clause re-mints over the
        imported atom and the second binds positionally against that
        re-minted class."""
        out = _unparse(
            "-module(m, [])\n"
            "-import_from(other, [f])\n"
            "f(A, B) <- g(A, B)\n"
            "f(C, D) <- h(C, D)\n"
        )
        assert out.count("a=") == 1


# ── End to end: the pair that used to fail now loads ───────────────────────


class TestDeclareThenImport:
    """``-module(m, [f(…)])`` then ``-import_from(v, [f])`` — the ordering that
    produced the bare ``TypeError``."""

    def test_the_pair_loads(self):
        _load_module(
            "tests.fixtures.fnmismatch_schema",
            _fixture_path("fnmismatch_schema"),
        )
        use = _load_module(
            "tests.fixtures.fnmismatch_use", _fixture_path("fnmismatch_use"),
        )
        assert isinstance(use.fnm_verdict, PredicateMeta)

    def test_the_local_name_is_the_imported_class(self):
        schema = _load_module(
            "tests.fixtures.fnmismatch_schema",
            _fixture_path("fnmismatch_schema"),
        )
        use = _load_module(
            "tests.fixtures.fnmismatch_use", _fixture_path("fnmismatch_use"),
        )
        # The import wins the binding; identity is shared, not split.
        assert use.fnm_verdict is schema.fnm_verdict

    def test_solutions_flow_through_the_local_clause(self):
        _load_module(
            "tests.fixtures.fnmismatch_schema",
            _fixture_path("fnmismatch_schema"),
        )
        use = _load_module(
            "tests.fixtures.fnmismatch_use", _fixture_path("fnmismatch_use"),
        )
        assert _solutions(use.fnm_chk, 1) == [(mint("ok"),)]

    def test_differing_field_names_across_the_import(self):
        """The local declaration spells (STATUS, CITATIONS), the exporter
        (OUTCOME, CITES).  Identity is shared and the exporter's facts flow."""
        vocab = _load_fixture("impord_vocab")
        use = _load_fixture("impord_declare_then_import")
        assert use.impord_verdict is vocab.impord_verdict
        assert _solutions(use.impord_dti_check, 1) == [(mint("ok"),), (mint("no"),)]

    def test_a_local_fact_fills_the_foreign_slots_in_order(self):
        """The bodyless-fact path: ``impord_fverdict(maybe, pending)`` must
        land in slot order against the imported class, not by local name."""
        vocab = _load_fixture("impord_fact_vocab")
        use = _load_fixture("impord_declare_then_import_fact")
        assert use.impord_fverdict is vocab.impord_fverdict
        assert _solutions(vocab.impord_fverdict, 2) == [(mint("maybe"), mint("pending"))]


class TestImportThenDeclare:
    """The other textual ordering: import binds first, then the -module
    entry re-exports it with shared class identity."""

    def test_identity_and_solutions_are_preserved(self):
        vocab = _load_fixture("impord_vocab")
        use = _load_fixture("impord_import_then_declare")
        assert use.impord_verdict is vocab.impord_verdict
        assert _solutions(use.impord_itd_check, 1) == [(mint("ok"),), (mint("no"),)]


class TestZeroArityAtomThenPredicate:
    """The shape ``tests/fixtures/impord_atom_then_pred.clausal`` pins: import
    a 0-arity vocabulary atom and then define a same-named predicate.

    P3-1 Task 2 fix round 1 (controller ruling, 2026-09-04): pre-pivot, the
    clause-head class block re-minted a class that a DOTTED owner-path
    reference (``tests.fixtures.impord_atomvocab.impord_qd``) also happened
    to reach — a quirk of class re-minting, never a contract. Post-pivot
    (§1b/R2, atoms are plain strs, no class to re-mint), the split was:
    (a) the re-defined predicate IS registered in the importing module's own
    database and fully callable by its bare LOCAL name; (b) a reference that
    goes through the dotted OWNER path found the owner's atom and calling it
    was a genuine error. That ruling deferred "routing a qualified goal to
    the local predicate" to P3-3's qualified-goal design.

    P3-3 Task 5b (controller ruling, 2026-09-06) is that routing, and it
    SUPERSEDES half (b): resolution is keyed on ``(name, arity)``, an atom
    has no arity-N meaning (ISO treats ``f`` and ``f/2`` as unrelated
    objects), so the APPLIED form reaches this file's own ``impord_qd/2``.
    Half (a) is unchanged, and the BARE form still means the imported atom —
    the two positions get different globals keys, which is the whole point.
    """

    def test_local_name_call_reaches_the_redefined_predicate(self):
        """(a) ``impord_qd`` by its bare local name is the re-minted /2
        predicate, registered in ``impord_atom_then_pred``'s own database —
        independent of whatever the module ATTRIBUTE ``impord_qd`` (the
        atom's own spelling, unaffected by the local redefinition) holds."""
        _load_fixture("impord_atomvocab")
        use = _load_fixture("impord_atom_then_pred")
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_qd", k, v, module=lm)
        )
        assert results == [(mint("a"), 1), (mint("b"), 2)]

    def test_the_applied_form_reaches_the_local_predicate(self):
        """(b), as P3-3 Task 5b re-decides it: ``impord_atp_lookup``'s body
        applies ``impord_qd`` at arity 2.  ``-import_from`` remapped that call
        to the FULL dotted name, and the owner never defines ``impord_qd`` as
        a functor at any arity — so the remap named an ATOM, which has no
        arity-2 meaning, while this file's own ``impord_qd/2`` does.  The
        local row answers.

        See ``tests/test_import_arity_resolution.py`` for the dedicated
        Task 5b pins, including the negative one (an imported FUNCTOR of
        arity N colliding with local arity-N clauses is untouched)."""
        _load_fixture("impord_atomvocab")
        use = _load_fixture("impord_atom_then_pred")
        lm = use.__dict__["$module"]
        k, v = Var(), Var()
        results = sorted(
            (walk(deref(k)), walk(deref(v)))
            for _ in call("impord_atp_lookup", k, v, module=lm)
        )
        assert results == [(mint("a"), 1), (mint("b"), 2)]


class TestGenuineArityDisagreementStillRaises:
    """Field names can be reconciled by position; arity cannot."""

    def test_the_pair_raises_an_attributable_error(self):
        _load_fixture("impord_arity_vocab")
        with pytest.raises(ClausalTermConstructionError) as exc_info:
            _load_fixture("impord_arity_clash")
        msg = str(exc_info.value)
        assert "impord_narrow/1" in msg
        assert "2 positional argument(s)" in msg
        assert "impord_arity_vocab.clausal:" in msg
        assert "impord_arity_clash.clausal:" in msg
        assert "exactly one arity" in msg
