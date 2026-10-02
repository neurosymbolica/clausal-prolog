"""Tests for Phase 2 and Phase 3 of GLOBAL_ATOMS_DEFAULT.

Phase 2 covers the bare-atom auto-mint hook — undeclared bare atom
references in .clausal files auto-mint into the process-wide
``predicate_builtins`` dict so that two modules each referencing the
same bare atom share its PredicateMeta class identity.

Phase 3 covers the ``-strict_atoms`` directive — a per-file opt-in that
disables the auto-mint default.  Bare references in a strict file must
be reachable via ``-module``, ``-private``, ``-import_from``, qualified
reference, or ``global_atom/2``; any other bare reference is a
compile-time ``NameError``.

The four cases in Phase 2 cover the precedence layering of resolution
rule 1 (private > module-decl > import > global fallthrough), per the
spec at ``implementation_plans/atoms_refactor/GLOBAL_ATOMS_DEFAULT.md``.

Atom names used here are deliberately unique to this test file
(``phase2*`` and ``phase3strict_*`` prefixes) so that cross-test
pollution of the process-wide global dict does not perturb assertions.
"""

from __future__ import annotations

import os
import tempfile
import warnings

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import chars
import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal import Var
from clausal.import_hook import _load_module, predicate_builtins
from clausal.logic.solve import solve   # P2: a cell goal is driven, never iterated
from clausal.logic.predicate import (
    is_declared_predicate, is_zero_field_class, is_atom_value,
    resolve_predicate_row,
)
from clausal.logic.variables import Trail, deref, unify
from clausal.logic.solve import call
from clausal.logic.builtins._helpers import functor_arity
from tests._suffix import SEAM


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_fixture(filename: str, mod_name: str) -> object:
    return _load_module(mod_name, _fixture_path(filename))


def _db_of(mod):
    return mod.__dict__["$module"].db


def _is_compiled_predicate(mod, name, arity):
    """*name* is bound in *mod* to a declared predicate at *arity* with a
    live row holding clauses.  After the W4b-2d flip the binding is a
    mangled HANDLE (a str), so this is asked of the module's Database, not
    answered by ``isinstance(..., PredicateMeta)``."""
    db = _db_of(mod)
    binding = getattr(mod, name)
    if not is_declared_predicate(binding, arity=arity, db=db):
        return False
    row = resolve_predicate_row(binding, arity=arity, db=db)
    return row is not None and not row.detached and bool(row.clauses)


# ── Case 1: two modules, both reference bare atom undeclared ────────────────


def test_bare_atoms_share_identity_across_modules():
    """Two modules that each declare ``phase2red`` on their own (neither
    imports it) see the same global atom: atoms are global by spelling.
    (The fixtures auto-minted it under -implicit_atoms before R8 removed it.)"""
    mod_a = _load_fixture(
        "global_atoms_a.seam",
        "tests.fixtures.global_atoms_a",
    )
    mod_b = _load_fixture(
        "global_atoms_b.seam",
        "tests.fixtures.global_atoms_b",
    )
    # THE FLIP (spec §5.1/§5.2): a bare atom lowers to the arity-0 CELL, and
    # sharing is stated as EQUALITY -- identity is an optimisation the spec
    # forbids observing.
    assert mod_a.phase2red == mint("phase2red")
    assert mod_a.phase2red == mod_b.phase2red
    assert mod_a.phase2red == predicate_builtins["phase2red"]


# ── Case 2: -private shadows the global ─────────────────────────────────────


def test_private_shadows_global():
    """P3-1 §1b/R2 INVERSION: a module that declares
    ``-private([phase2priv_orange])`` no longer owns a distinct private
    class — atoms are global-by-spelling interned strs, so the "private"
    declaration and a sibling's own -private declaration of the same name
    resolve to
    the identical global object.  (Pre-pivot this pinned the opposite:
    ``mod_a.phase2priv_orange is not mod_b.phase2priv_orange``.
    ``-private`` still has its module-local-identity story rewritten by
    ``-hide`` in Task 6; until then it is advisory only.)"""
    mod_a = _load_fixture(
        "global_atoms_priv_a.seam",
        "tests.fixtures.global_atoms_priv_a",
    )
    mod_b = _load_fixture(
        "global_atoms_priv_b.seam",
        "tests.fixtures.global_atoms_priv_b",
    )
    assert mod_a.phase2priv_orange == mint("phase2priv_orange")
    assert mod_b.phase2priv_orange == mint("phase2priv_orange")
    assert mod_a.phase2priv_orange == mod_b.phase2priv_orange
    assert mod_b.phase2priv_orange == predicate_builtins["phase2priv_orange"]


# ── Case 3: import wins over global ─────────────────────────────────────────


def test_import_wins_over_global():
    """If a module ``-import_from(M, [phase2import_yellow])`` and also
    bare-references the same name, the bare reference resolves to the
    imported class — not the global fallthrough."""
    mod_owner = _load_fixture(
        "global_atoms_owner.seam",
        "tests.fixtures.global_atoms_owner",
    )
    mod_importer = _load_fixture(
        "global_atoms_importer.seam",
        "tests.fixtures.global_atoms_importer",
    )
    # THE FLIP: the declared atom is the arity-0 cell.
    assert mod_owner.phase2import_yellow == mint("phase2import_yellow")
    assert mod_importer.phase2import_yellow == mod_owner.phase2import_yellow


# ── Case 4: module-decl atom does NOT become global ─────────────────────────


def test_module_decl_atom_is_not_global():
    """P3-1 §1b/R2 INVERSION: a module that declares
    ``-module(M, [phase2declonly_green])`` no longer keeps a distinct local
    class.  Another module that bare-references the same name without
    importing (it declares the name -private itself; before R8 it
    auto-minted it) now resolves to the SAME global str.  (Pre-pivot this pinned
    the opposite: ``mod_a.phase2declonly_green is not
    mod_b.phase2declonly_green``.)"""
    mod_a = _load_fixture(
        "global_atoms_decl_only_a.seam",
        "tests.fixtures.global_atoms_decl_only_a",
    )
    mod_b = _load_fixture(
        "global_atoms_decl_only_b.seam",
        "tests.fixtures.global_atoms_decl_only_b",
    )
    assert mod_a.phase2declonly_green == mint("phase2declonly_green")
    assert mod_b.phase2declonly_green == mint("phase2declonly_green")
    assert mod_a.phase2declonly_green == mod_b.phase2declonly_green
    assert mod_b.phase2declonly_green == predicate_builtins["phase2declonly_green"]


# ── Phase 3: -strict_atoms directive ────────────────────────────────────────


def _load_inline_clausal(name: str, source: str):
    """Write `source` to a temp .clausal file and try to load it.

    Used for must-fail-to-load fixtures — keeping them as persistent files
    under ``tests/fixtures/`` would cause pytest's ``.clausal`` collector
    in ``conftest.py`` to surface them as <load> failures.
    """
    with tempfile.NamedTemporaryFile(
        suffix=SEAM, mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


def test_strict_atoms_undeclared_atom_raises():
    """A file with ``-strict_atoms`` and a bare reference to an atom that is
    not declared, imported, or otherwise reached must fail to compile with
    a ``NameError`` naming the offending atom and the file."""
    # The auto-mint default for phase3strict_undeclared_red must NOT have
    # happened on a previous test run; assert that up front so the failure
    # is attributable to strict mode rather than a polluted dict.
    assert "phase3strict_undeclared_red" not in predicate_builtins
    source = (
        "-strict_atoms\n"
        "\n"
        "color_strict_undeclared(phase3strict_undeclared_red),\n"
    )
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_strict_atoms_undeclared_test", source)
    msg = str(exc_info.value)
    assert "strict_atoms" in msg
    assert "phase3strict_undeclared_red" in msg
    assert "_strict_atoms_undeclared_test" in msg
    # Diagnostic must point the author at the legitimate routes.
    assert "-module" in msg
    assert "-private" in msg
    assert "-import_from" in msg
    assert "global_atom" in msg
    # Strict mode must not have silently minted the undeclared atom.
    assert "phase3strict_undeclared_red" not in predicate_builtins


def test_strict_atoms_undeclared_dict_key_raises_without_polluting():
    """An undeclared bare-atom *dict key* under ``-strict_atoms`` must fail like
    any other undeclared atom — and must NOT pollute ``predicate_builtins``.

    Dict literals are built eagerly during exec (before the mint pass), so the
    ``$intern_atom`` key helper has to enforce strict mode itself rather than
    silently interning; this guards that regression.
    """
    assert "phase3strict_dictkey_violet" not in predicate_builtins
    source = (
        "-strict_atoms\n"
        "\n"
        "with_key(V) <- (V is {phase3strict_dictkey_violet: 1}"
        "[phase3strict_dictkey_violet]),\n"
    )
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_strict_atoms_dictkey_test", source)
    assert "strict_atoms" in str(exc_info.value)
    assert "phase3strict_dictkey_violet" in str(exc_info.value)
    # The eager key-intern must not have leaked the atom into the process dict.
    assert "phase3strict_dictkey_violet" not in predicate_builtins


def test_declared_atom_dict_key_interns():
    """A declared bare-atom dict key is interned into the process-wide dict,
    and it is the *same* object a value-position use binds — so ``{k: 1}[k]``
    reads back.  (It used to be exercised under the removed -implicit_atoms.)"""
    assert "phase_atomkey_teal" not in predicate_builtins
    source = (
        "-private([phase_atomkey_teal])\n"
        "read_key(V) <- (V is {phase_atomkey_teal: 7}[phase_atomkey_teal]),\n"
    )
    mod = _load_inline_clausal("_atomkey_intern_test", source)
    assert "phase_atomkey_teal" in predicate_builtins
    assert mod.phase_atomkey_teal is predicate_builtins["phase_atomkey_teal"]


def test_strict_atoms_private_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom listed
    in ``-private([...])`` must compile successfully — the private listing
    satisfies strict mode.  P3-1 §1b/R2 INVERSION: the resulting value is now
    the same global-by-spelling str as the process-wide pool, not a distinct
    module-local class (pre-pivot this pinned ``is not``)."""
    mod = _load_fixture(
        "strict_atoms_private.seam",
        "tests.fixtures.strict_atoms_private",
    )
    assert mod.phase3strict_private_orange == mint("phase3strict_private_orange")
    assert mod.phase3strict_private_orange == predicate_builtins.get(
        "phase3strict_private_orange"
    )


def test_strict_atoms_module_decl_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom listed
    in ``-module(M, [...])`` must compile successfully."""
    mod = _load_fixture(
        "strict_atoms_module_decl.seam",
        "tests.fixtures.strict_atoms_module_decl",
    )
    # THE FLIP: a declared atom is the arity-0 cell.
    assert mod.phase3strict_module_green == mint("phase3strict_module_green")


def test_strict_atoms_imported_atom_compiles():
    """A file with ``-strict_atoms`` and a bare reference to an atom brought
    in via ``-import_from`` must compile successfully — the import binds
    the name in module_dict before the strict-mode check runs."""
    mod_owner = _load_fixture(
        "strict_atoms_import_owner.seam",
        "tests.fixtures.strict_atoms_import_owner",
    )
    mod_importer = _load_fixture(
        "strict_atoms_import.seam",
        "tests.fixtures.strict_atoms_import",
    )
    # THE FLIP: a declared atom is the arity-0 cell.
    assert mod_owner.phase3strict_import_yellow == mint("phase3strict_import_yellow")
    # The importer's bare reference resolves to the same atom as the
    # owner's declaration.
    assert (
        mod_importer.phase3strict_import_yellow
        == mod_owner.phase3strict_import_yellow
    )


def test_strict_atoms_global_atom_builtin_compiles():
    """A file with ``-strict_atoms`` that reaches a name via
    ``global_atom("name", X)`` must compile — the directive restricts bare
    atom references, not the reflection escape hatch.  The string literal
    in ``global_atom("phase3strict_global_red", _atom)`` is not a bare
    Name node, so strict mode never flags it."""
    mod = _load_fixture(
        "strict_atoms_global_atom.seam",
        "tests.fixtures.strict_atoms_global_atom",
    )
    # Predicate compiled: lookup_strict_global/1 is a predicate with clauses.
    assert _is_compiled_predicate(mod, "lookup_strict_global", 1)


def test_strict_atoms_empty_file_compiles():
    """Edge case: a file with ``-strict_atoms`` and no clauses that bare-
    reference any atom must compile fine — strict mode has nothing to
    reject."""
    mod = _load_fixture(
        "strict_atoms_empty.seam",
        "tests.fixtures.strict_atoms_empty",
    )
    assert _is_compiled_predicate(mod, "ok", 1)


def test_strict_atoms_multiple_undeclared_reported_together():
    """When several undeclared atoms appear in a strict file, the diagnostic
    must enumerate them all in one message rather than failing at the
    first.  This makes the error easier to act on for the author."""
    # Names unique to this test to keep the global dict clean.
    for name in ("phase3strict_multi_alpha", "phase3strict_multi_beta"):
        assert name not in predicate_builtins
    source = (
        "-strict_atoms\n"
        "\n"
        "color_multi_alpha(phase3strict_multi_alpha),\n"
        "color_multi_beta(phase3strict_multi_beta),\n"
    )
    with pytest.raises(NameError) as exc_info:
        _load_inline_clausal("_strict_atoms_multi_test", source)
    msg = str(exc_info.value)
    assert "phase3strict_multi_alpha" in msg
    assert "phase3strict_multi_beta" in msg
    # Neither name should have been minted as a side effect.
    for name in ("phase3strict_multi_alpha", "phase3strict_multi_beta"):
        assert name not in predicate_builtins


# ── Visibility: `-private` is a surface marker, not an access control ───────


def test_private_names_are_importable_and_share_identity():
    """`-private` does NOT make a name unreachable from another module.

    Pins the decision recorded in
    ``todo/done/private-atoms-are-importable-contra-spec.md``: `-private`
    means "not part of my public surface", not "unreachable" — closer to
    Python's leading underscore than to C++ ``private``.  An
    ``-import_from`` of a private name succeeds, binds the *owner's* class
    (so the two modules share one identity), and emits no warning.

    This is load-bearing downstream: under strict atoms, a fixture module
    with no ``-module(...)`` export list has importing from its ``-private``
    list as its identity-preserving route across a file boundary.  If a
    future change starts rejecting or warning on this, it breaks that
    pattern — so the behaviour is pinned here rather than left to drift.

    P3-1 §1b/R2 INVERSION: pre-pivot, the private atom crossing the import
    boundary was a distinct module-local class (``is not
    predicate_builtins.get(...)``).  Atoms are now global-by-spelling
    interned strs, so "shares identity with the owner" is trivially true —
    it also shares identity with the process-wide global of the same
    spelling, which the assertion below restates.
    """
    owner = _load_fixture(
        "private_import_owner.seam",
        "tests.fixtures.private_import_owner",
    )
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        consumer = _load_fixture(
            "private_import_consumer.seam",
            "tests.fixtures.private_import_consumer",
        )

    # The private *atom* crossed the boundary, and it is the same object.
    assert owner.privimp_tag == mint("privimp_tag")
    assert consumer.privimp_tag == owner.privimp_tag
    # ...and it is ALSO the process-wide global atom of the same spelling
    # (§1b/R2 — there is no more module-local atom identity to distinguish).
    assert owner.privimp_tag == predicate_builtins.get("privimp_tag")

    # The private *predicate* crossed the boundary too.
    assert consumer.priv_imp_helper == owner.priv_imp_helper
    owner_row = resolve_predicate_row(owner.priv_imp_helper, arity=1,
                                      db=_db_of(owner))
    assert owner_row is not None
    assert resolve_predicate_row(consumer.priv_imp_helper, arity=1,
                                 db=_db_of(consumer)) is owner_row

    # Shared identity is the point: the query actually solves.
    assert list(solve(("priv_imp_use", Var()), consumer)) != []

    # No warning: importing a private name is a supported pattern, not a
    # smell.  A `ClausalPrivateAtomImportWarning`-style diagnostic would
    # fire on the legitimate anonymous-fixture pattern, so it is
    # deliberately absent.
    # Case-insensitive on purpose: the fixture's names are ``privimp_tag``
    # but also ``priv_imp_helper``/``priv_imp_use``, and a warning that
    # renders a predicate name in some other case would slip through a
    # case-sensitive filter — so the pin matches the ``privimp`` stem however
    # it is cased.  Matching every warning is not the alternative: loading a
    # fixture can legitimately emit unrelated ones.
    private_warnings = [
        w for w in caught if "privimp" in str(w.message).lower()
    ]
    assert private_warnings == [], (
        f"importing a -private name must not warn; got {private_warnings}"
    )


# ── P3-1 Task 1: str-as-atom acceptance (runtime readers, dual-accept) ──────
#
# R2 (implementation_plans/phase3-decomposition-and-p31-atom-pivot.md):
# ``atom(X)`` becomes true for every ``str`` -- co-extensional with
# ``string/1`` -- while zero-field PredicateMeta atom classes keep working
# (transitional dual-accept; the lowering flip that stops MINTING classes is
# Task 2). This section pins the READER-side acceptance: the ``atom/1`` and
# ``atomic/1`` builtins, ``functor_arity``, unification, and the
# ``atom_chars``/``atom_codes`` round trips all treat a plain str as an atom
# value. Strictly additive -- nothing here inverts a previously-true
# assertion except the ``functor_arity("abc") is None`` pin in
# ``test_funnel_accessors.py`` (moved/inverted there, cited to this ruling).


def _atoms_mod(name):
    """A throwaway compiled module, just to give ``call()`` a database to
    resolve builtins against (mirrors ``tests/test_bytes_type_checks.py``'s
    ``_mod`` helper)."""
    with tempfile.NamedTemporaryFile(suffix=SEAM, mode="w", delete=False) as f:
        f.write("noop(1),\n")
        f.flush()
        path = f.name
    try:
        return _load_module(name, path).__dict__["$module"]
    finally:
        os.unlink(path)


def _succeeds(pred, *args, mod):
    return sum(1 for _ in call(pred, *args, module=mod)) >= 1


class TestStrAtomAcceptance:
    """atom/1, atomic/1, string/1 co-extension for plain strs (R2)."""

    def test_atom_true_for_plain_str(self):
        mod = _atoms_mod("tsaa_atom_str")
        assert _succeeds("atom", mint("red"), mod=mod)

    def test_atom_true_for_empty_str(self):
        # The empty str is still a str, hence still an atom value under R2
        # -- no special-casing to the "[]" nil atom here (that's the ISO
        # cons-cell reading, a different accessor family; see functor_arity
        # tests below).
        mod = _atoms_mod("tsaa_atom_empty")
        assert _succeeds("atom", mint(""), mod=mod)



    def test_atomic_true_for_plain_str(self):
        # Already-true behavior (F082) -- pinned here alongside atom/1 per
        # the task brief.
        mod = _atoms_mod("tsaa_atomic_str")
        assert _succeeds("atomic", mint("red"), mod=mod)

    def test_atom_and_string_are_disjoint_after_the_flip(self):
        # THE FLIP (spec §6.3) INVERTS the P3-1 pin that atom/1 and string/1
        # were co-extensional for a ``str``: the atom is the CELL and the
        # ``str`` is the STRING, and neither answers the other's test.
        mod = _atoms_mod("tsaa_string_str")
        assert _succeeds("atom", mint("red"), mod=mod)
        assert not _succeeds("string", mint("red"), mod=mod)
        assert _succeeds("string", chars("red"), mod=mod)
        assert not _succeeds("atom", chars("red"), mod=mod)


class TestIsAtomValueHelper:
    """Unit checks for ``clausal.logic.predicate.is_atom_value`` -- the
    runtime-reader-facing widening of the class test that Task 1 introduces
    (see the DECISION RULE in the task brief: the class test itself is left
    untouched because some compiler call sites key off "zero-field CLASS,
    not str" -- this new helper is what the runtime readers use instead)."""

    def test_true_for_the_arity_0_cell(self):
        assert is_atom_value(mint("red")) is True
        assert is_atom_value(mint("")) is True

    def test_false_for_plain_str(self):
        # THE FLIP (spec §5.1) INVERTS the P3-1 acceptance: a STRING is not
        # an atom value.  Since stage 2 the bare ``str`` IS the atom, so the
        # string is spelled through its carrier.
        assert is_atom_value(chars("red")) is False
        assert is_atom_value(chars("")) is False


    def test_false_for_int_float_none_bytes(self):
        assert is_atom_value(42) is False
        assert is_atom_value(3.14) is False
        assert is_atom_value(None) is False
        assert is_atom_value(b"red") is False

    def test_false_for_unbound_var(self):
        assert is_atom_value(Var()) is False



class TestFunctorArityAtomCell:
    """``functor_arity(mint("red")) == ("red", 0)`` -- slot 0 and arity 0.

    THE FLIP INVERTS the P3-1 str-atom-value reading this class used to pin:
    a ``str`` is a STRING (a list), which is outside ``functor_arity``'s
    declared domain, so it answers ``None`` the way any other list does.
    See tests/test_funnel_accessors.py::TestFunctorArity for the primary
    pin."""

    def test_functor_arity_atom_cell(self):
        assert functor_arity(mint("red")) == ("red", 0)

    def test_functor_arity_empty_atom_cell(self):
        assert functor_arity(mint("")) == ("", 0)

    def test_functor_arity_plain_str_is_out_of_domain(self):
        # Stage 2: the bare ``str`` is the atom; the STRING is the carrier.
        assert functor_arity(chars("red")) is None
        assert functor_arity(chars("")) is None



class TestStrAtomUnification:
    """Plain str unification -- pinning already-true C rich-compare
    behavior, per the task brief ('no code change expected')."""

    def test_equal_strs_unify(self):
        trail = Trail()
        assert unify("red", "red", trail)

    def test_different_strs_do_not_unify(self):
        trail = Trail()
        assert not unify("red", "blue", trail)

    def test_str_unifies_with_unbound_var(self):
        trail = Trail()
        v = Var()
        assert unify(v, "red", trail)


class TestAtomCharsRoundTrip:
    """atom_chars/2 (and atom_codes/2) round trip a plain str both
    directions -- ``_atom_to_str`` already accepts strs (chars.py), pinned
    here per the task brief."""

    def test_atom_chars_atom_to_chars(self):
        mod = _atoms_mod("tacrt_a2c")
        out = Var()
        results = [deref(out) for _ in call("atom_chars", mint("ab"), out, module=mod)]
        assert results == [[mint("a"), mint("b")]]

    def test_atom_chars_chars_to_atom(self):
        mod = _atoms_mod("tacrt_c2a")
        out = Var()
        results = [deref(out) for _ in call("atom_chars", out, [mint("a"), mint("b")], module=mod)]
        assert results == [mint("ab")]

    def test_atom_codes_round_trip(self):
        mod = _atoms_mod("tacrt_codes")
        out = Var()
        results = [deref(out) for _ in call("atom_codes", mint("ab"), out, module=mod)]
        assert results == [[97, 98]]


# ── P3-1 Task 2: the lowering flip (bare atoms -> interned str Constants) ───
#
# Task 1 (above) taught the READERS to accept a plain str as an atom while
# class atoms still existed (transitional dual-accept).  Task 2 flips the
# WRITER: ``visit_Name``'s atom branch now emits a str ``Constant`` instead
# of a ``Name`` reference to a minted per-module class, and
# ``-module``/``-private`` stop minting zero-field atom classes at all.  The
# central, deliberate behavioral inversion: two modules declaring the SAME
# atom spelling (whether by bare fallthrough, ``-module``, or ``-private``)
# now unify with each other -- see
# implementation_plans/phase3-decomposition-and-p31-atom-pivot.md Task 2 and
# implementation_plans/tagged-tuple-term-representation.md §1b/§5 (rulings
# R2/R3).  Cross-module IDENTITY-shaped pins that this directly contradicts
# (module-decl/-private atoms no longer distinct) are Task 3's job to
# invert -- NOT touched here; see task-2-report.md's expected-red ledger.


def test_declared_atoms_unify_across_module_and_private():
    """A bare atom declared via ``-module`` in one module and via
    ``-private`` in a completely different, unrelated module now UNIFY.

    Pre-pivot this failed: ``-module``/``-private`` each minted a distinct
    per-module ``PredicateMeta`` class for the same spelling, so the two
    values were different objects that never unified.  Post-pivot both
    lower to the identical interned str ``"atompivot_cross_tag"`` -- atoms
    are global by spelling, with no per-module identity (§1b/R2).
    """
    mod_a = _load_fixture(
        "atompivot_module_a.seam",
        "tests.fixtures.atompivot_module_a",
    )
    mod_b = _load_fixture(
        "atompivot_private_b.seam",
        "tests.fixtures.atompivot_private_b",
    )
    lm_a = mod_a.__dict__["$module"]
    lm_b = mod_b.__dict__["$module"]
    out_a, out_b = Var(), Var()
    # deref INSIDE the loop -- call()'s generator undoes trail bindings on
    # backtrack past the last yield, so reading the Var after the generator
    # is exhausted (list(...) then deref) sees it unbound again.
    vals_a = [deref(out_a) for _ in call("tag_from_module_decl", out_a, module=lm_a)]
    vals_b = [deref(out_b) for _ in call("tag_from_private_decl", out_b, module=lm_b)]
    assert len(vals_a) == 1 and len(vals_b) == 1
    val_a, val_b = vals_a[0], vals_b[0]
    assert val_a == mint("atompivot_cross_tag")
    assert val_b == mint("atompivot_cross_tag")
    # Not just equal -- the SAME interned object, and they actually unify.
    assert val_a == val_b
    trail = Trail()
    assert unify(val_a, val_b, trail)


def test_bare_atom_arrives_as_the_arity_0_cell_at_python_seam():
    """The value a solved query binds for a bare atom is the arity-0 CELL
    at the actual Python seam (the object a caller of ``solve``/``call``
    gets back after ``deref``).  THE FLIP inverts the P3-1 pin that it was
    a plain ``str``."""
    source = (
        "-module(atompivot_seam_test, [seam(X), atompivot_seam_red])\n"
        "\n"
        "seam(atompivot_seam_red),\n"
    )
    mod = _load_inline_clausal("_atompivot_seam", source)
    lm = mod.__dict__["$module"]
    out = Var()
    results = [deref(out) for _ in call("seam", out, module=lm)]
    assert len(results) == 1
    val = results[0]
    assert val == mint("atompivot_seam_red")
    assert type(val) is str   # stage 2: the atom is the Python str


def test_strictness_preserved_across_the_lowering_flip():
    """The lowering flip changes WHAT a bare atom compiles to (the atom, not a
    class) but not WHETHER an undeclared one is allowed: strict-by-default
    still raises ``NameError``, and a declaration lifts it."""
    with pytest.raises(NameError):
        _load_inline_clausal(
            "_atompivot_strict_still_raises",
            "seam(atompivot_undeclared_atom),\n",
        )
    mod = _load_inline_clausal(
        "_atompivot_declared_lifts",
        "-private([atompivot_declared_atom])\n\n"
        "seam_declared(atompivot_declared_atom),\n",
    )
    assert mod.atompivot_declared_atom == mint("atompivot_declared_atom")


def test_true_lowers_to_truth_value_not_atom():
    """The ``_TRUTH_ALIASES`` Kleene fold in ``visit_Name`` must stay AHEAD
    of the atom-lowering branch -- ``true``/``false``/``undefined`` are NOT
    atoms.  Pins that ``true`` still compiles to the Python bool ``True``,
    never the str ``"true"`` (which the atom branch would otherwise
    produce now that atoms lower to str Constants too -- the two branches
    must stay distinguishable)."""
    source = (
        "-module(atompivot_truth_test, [truth_probe(X)])\n"
        "\n"
        "truth_probe(true),\n"
    )
    mod = _load_inline_clausal("_atompivot_truth", source)
    lm = mod.__dict__["$module"]
    out = Var()
    results = [deref(out) for _ in call("truth_probe", out, module=lm)]
    assert len(results) == 1
    val = results[0]
    assert val is True
    assert val != "true"
