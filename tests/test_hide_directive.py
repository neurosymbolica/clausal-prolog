"""Tests for the ``-hide`` directive (P3-1 Task 6, atom-pivot plan).

Design authority: ``implementation_plans/tagged-tuple-term-representation.md``
§1a (atoms global by spelling; ``-hide`` is the opt-in module-local escape
hatch) and §1b (the Phase 3 rulings — R1 fixes the mangling separator at
U+E000; the guarantee is uniqueness + analysis soundness, NOT runtime
security).  See ``clausal/logic/atoms.py`` for the mangling helpers and
``clausal/templating/term_rewriting.py``'s ``_handle_hide_directive``/
``visit_Name`` for the compiler-side substitution.

Fixtures (``tests/fixtures/hide_*.clausal``):
  * ``hide_owner.clausal`` -- declares ``-module(hide_owner, ...)`` and
    ``-hide([hide_secret])``; every ``hide_secret`` reference inside it
    compiles to the SAME mangled Constant.
  * ``hide_other.clausal`` -- a DIFFERENT module declaring the SAME bare
    spelling ``hide_secret``, but only via ``-private`` (an ordinary
    global atom, not hidden) -- cross-module isolation.
  * ``hide_importer.clausal`` -- imports ``holds/1`` FROM ``hide_owner``
    (so it can receive the mangled value as an opaque bound argument) and
    separately declares its OWN bare ``hide_secret`` -- proving that
    importing the hiding module does not grant the ability to SPELL the
    hidden atom.

Atom names used here are prefixed ``hide_`` (unique to this test file), so
cross-test pollution of the process-wide global-atom pool does not perturb
assertions (same discipline as ``test_global_atoms_default.py``).
"""

from __future__ import annotations

import io as _io
import os
import sys as _sys
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import HIDDEN_SEP, demangle, demangle_for_display, is_mangled, mangle
from clausal.logic.builtins import get_builtin_dispatch
from clausal.logic.solve import call
from clausal.logic.trampoline import StepGenerator, solutions
from clausal.logic.variables import Trail, Var, deref, unify
from clausal.reflection import Atom, render_source
from clausal.testing import _render_value


def _fixture_path(filename: str) -> str:
    return os.path.join(os.path.dirname(__file__), "fixtures", filename)


def _load_fixture(filename: str, mod_name: str) -> object:
    return _load_module(mod_name, _fixture_path(filename))


def _load_inline_clausal(name: str, source: str):
    """Write *source* to a temp .clausal file and load it.

    Used for must-fail-to-load / throwaway cases — a persistent file under
    ``tests/fixtures/`` would be picked up by ``conftest.py``'s ``.clausal``
    auto-collector and surface a load failure as its own (unrelated)
    collection error.  Mirrors ``test_global_atoms_default.py``'s helper of
    the same name.
    """
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(source)
        f.flush()
        path = f.name
    try:
        return _load_module(name, path)
    finally:
        os.unlink(path)


# ── clausal/logic/atoms.py: mangle/demangle helpers ─────────────────────────


class TestMangleHelpers:
    def test_mangle_embeds_hidden_sep(self):
        mangled = mangle("m", "foo")
        assert mangled == f"m{HIDDEN_SEP}foo"
        assert is_mangled(mangled)

    def test_plain_str_is_not_mangled(self):
        assert not is_mangled("plain_atom")
        assert not is_mangled("")

    def test_demangle_round_trips(self):
        mangled = mangle("owner_mod", "spelling")
        assert demangle(mangled) == ("owner_mod", "spelling")

    def test_demangle_rejects_unmangled(self):
        with pytest.raises(ValueError):
            demangle("plain")

    def test_demangle_for_display_qualifies(self):
        mangled = mangle("owner_mod", "spelling")
        assert demangle_for_display(mangled) == "owner_mod.spelling"

    def test_demangle_for_display_passes_through_plain(self):
        assert demangle_for_display("plain") == "plain"


# ── Within-module unification ────────────────────────────────────────────────


def test_hidden_atom_unifies_within_its_module():
    """Two independent compile-time references to a ``-hide``-en atom in
    its OWNING module (``holds(hide_secret)`` and ``label(hide_secret)``)
    both compile to the identical mangled Constant, so a rule joining them
    (``same(X, Y) <- holds(X), label(Y)``) solves with ``X == Y``."""
    mod = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    out_x, out_y = Var(), Var()
    # deref INSIDE the loop -- call()'s generator undoes trail bindings on
    # backtrack past the last yield (see test_global_atoms_default.py's
    # matching note).
    vals = [(deref(out_x), deref(out_y)) for _ in mod.same(out_x, out_y)]
    assert len(vals) == 1
    val_x, val_y = vals[0]
    expected = mangle("hide_owner", "hide_secret")
    assert val_x == val_y == expected
    assert is_mangled(val_x)
    trail = Trail()
    assert unify(val_x, val_y, trail)


# ── Cross-module isolation ───────────────────────────────────────────────────


def test_cross_module_same_spelling_does_not_unify():
    """``hide_other.clausal`` declares the SAME bare spelling
    (``hide_secret``) but never hides it -- an ordinary global atom.  It
    must NOT unify with ``hide_owner``'s hidden atom of the same
    spelling: different (mangled vs. plain) runtime strs."""
    owner = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    other = _load_fixture("hide_other.clausal", "tests.fixtures.hide_other")

    out_owner = Var()
    owner_vals = [deref(out_owner) for _ in owner.holds(out_owner)]
    out_other = Var()
    other_vals = [deref(out_other) for _ in other.reaches(out_other)]

    assert owner_vals == [mangle("hide_owner", "hide_secret")]
    assert other_vals == ["hide_secret"]
    assert owner_vals[0] != other_vals[0]

    trail = Trail()
    assert not unify(owner_vals[0], other_vals[0], trail)


# ── Importing the hiding module still can't reach it by spelling ────────────


def test_importer_cannot_spell_hidden_atom():
    """``hide_importer.clausal`` imports ``holds/1`` from ``hide_owner``
    (so it CAN receive the mangled value as an opaque bound argument via
    ``imported_secret/1``) but independently declares its OWN bare
    ``hide_secret`` (via ``-private``, an ordinary global atom) bound by
    ``local_secret/1``.  The two must differ -- importing the predicate
    that PRODUCES the hidden value does not grant the ability to SPELL
    that value."""
    importer = _load_fixture(
        "hide_importer.clausal", "tests.fixtures.hide_importer")

    out_imported = Var()
    imported_vals = [
        deref(out_imported) for _ in importer.imported_secret(out_imported)
    ]
    out_local = Var()
    local_vals = [
        deref(out_local) for _ in importer.local_secret(out_local)
    ]

    assert imported_vals == [mangle("hide_owner", "hide_secret")]
    assert local_vals == ["hide_secret"]
    assert imported_vals[0] != local_vals[0]


# ── atom_chars forgery: documented out-of-warranty, not blocked ─────────────


def test_atom_chars_forgery_constructs_mangled_str():
    """§1b: "the guarantee is uniqueness + analysis soundness, not runtime
    security" -- ``atom_chars/2`` (chars -> atom direction) CAN construct
    the exact mangled str character-by-character, entirely outside the
    reader (which refuses HIDDEN_SEP in source, R1).  This is a
    DOCUMENTED, PINNED capability -- not a bug to fix; forging the mangled
    spelling requires already knowing both the owning module's name and
    the atom's bare spelling, which is the same "collision avoidance, not
    a lock" stance Python's own ``__name`` mangling takes."""
    target = mangle("hide_owner", "hide_secret")
    chars = list(target)
    assert HIDDEN_SEP in chars  # the forger must supply the raw separator

    out = Var()
    trail = Trail()
    dispatch = get_builtin_dispatch("atom_chars", 2, None)
    results = solutions(
        StepGenerator(dispatch, None, None, None, out, chars, trail),
        snapshot=lambda: deref(out),
    )
    assert results == [target]
    assert is_mangled(results[0])


# ── Printing: mangled atoms render the human ``module.name`` form ───────────


def test_renderer_shows_human_form_for_mangled_atom():
    """The reified-term renderer (``clausal.reflection``) renders a
    mangled atom's HUMAN form (``module.name``, matching how a qualified
    predicate reference already prints) while the raw runtime str keeps
    HIDDEN_SEP -- see ``_ClauseRenderer.term``'s ``Atom`` branch."""
    mangled = mangle("hide_owner", "hide_secret")
    assert render_source(Atom(name=mangled)) == "hide_owner.hide_secret"
    # The raw str itself is untouched -- only PRINTING demangles.
    assert HIDDEN_SEP in mangled


def test_near_miss_renderer_shows_human_form():
    """The ``clausal.testing`` near-miss/diagnostic renderer (Task 4's
    ``_reify_value``/``_render_value``) also renders a mangled atom's
    bound runtime value in human form, reusing the SAME
    ``demangle_for_display`` substitution point as the reflection
    renderer above."""
    mangled = mangle("hide_owner", "hide_secret")
    text = _render_value(mangled, path=_fixture_path("hide_owner.clausal"))
    assert text == "hide_owner.hide_secret"


def test_end_to_end_solved_value_renders_human_form():
    """A value actually solved out of the owning module (not a
    hand-constructed mangle() call) renders the same human form through
    the near-miss renderer."""
    mod = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    out = Var()
    vals = [deref(out) for _ in mod.holds(out)]
    assert len(vals) == 1
    text = _render_value(vals[0], path=_fixture_path("hide_owner.clausal"))
    assert text == "hide_owner.hide_secret"


# ── Prolog writer builtins: write/1, write_to_string/2, term_to_string/2 ────
#
# P3-1 Task 6 fix round: the reflection/diagnostic renderers above are NOT
# the only "writer" -- clausal/logic/builtins/io.py's write/1, writeln/1,
# write_to_string/2 (via _format_term_for_io) and print_term/1,
# term_to_string/2, listing/1, portray_clause/1 (via clausal.terms.term_str)
# independently format terms for I/O.  Design doc section 1b promises "the
# writer renders the human form" for ANY writer, not just reflection's --
# this section pins that promise for the actual Prolog-facing builtins.
# NOT a round-trip: the human ``module.name`` form re-reads as a different
# (unmangled) term -- display only, per section 1b's own guarantee; the raw
# mangled str is what actually travels/unifies/marshals.


def _dispatch_solutions(name, arity, *args, snap):
    """Run a builtin predicate directly and collect a snapshot per solution
    (mirrors tests/test_chars.py's ``_run_collect`` helper)."""
    trail = Trail()
    dispatch = get_builtin_dispatch(name, arity, None)
    return solutions(
        StepGenerator(dispatch, None, None, None, *args, trail), snapshot=snap
    )


def test_write_to_string_renders_human_form_for_hidden_atom():
    """``write_to_string/2`` on a solved hidden-atom value renders the
    human ``module.name`` form -- no raw HIDDEN_SEP in the output."""
    mod = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    out = Var()
    vals = [deref(out) for _ in mod.holds(out)]
    assert len(vals) == 1
    val = vals[0]
    assert is_mangled(val)

    result = Var()
    texts = _dispatch_solutions(
        "write_to_string", 2, val, result, snap=lambda: deref(result))
    assert texts == ["hide_owner.hide_secret"]
    assert HIDDEN_SEP not in texts[0]


def test_term_to_string_renders_human_form_for_hidden_atom():
    """``term_to_string/2`` (the ``term_str``-backed writer, also feeding
    ``print_term/1``) renders the same human form -- no raw HIDDEN_SEP."""
    mod = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    out = Var()
    vals = [deref(out) for _ in mod.holds(out)]
    val = vals[0]

    result = Var()
    texts = _dispatch_solutions(
        "term_to_string", 2, val, result, snap=lambda: deref(result))
    assert len(texts) == 1
    assert HIDDEN_SEP not in texts[0]
    assert "hide_owner.hide_secret" in texts[0]


def test_portray_clause_spot_check_renders_human_form():
    """Spot check (fix-round item 2): ``portray_clause/1`` -- backed by
    ``clausal.terms.term_pformat``, which itself starts from ``term_str``
    -- also renders the human form for a hidden atom, with no raw
    HIDDEN_SEP anywhere in its output."""
    mod = _load_fixture("hide_owner.clausal", "tests.fixtures.hide_owner")
    out = Var()
    vals = [deref(out) for _ in mod.holds(out)]
    val = vals[0]

    trail = Trail()
    dispatch = get_builtin_dispatch("portray_clause", 1, None)
    buf = _io.StringIO()
    old_stdout = _sys.stdout
    _sys.stdout = buf
    try:
        list(solutions(StepGenerator(dispatch, None, None, None, val, trail)))
    finally:
        _sys.stdout = old_stdout
    text = buf.getvalue()
    assert HIDDEN_SEP not in text
    assert "hide_owner.hide_secret" in text


# ── -hide requires a preceding -module ───────────────────────────────────────


def test_hide_without_module_raises_syntax_error():
    """A ``-hide(...)`` with no ``-module(...)`` yet declared in the same
    file is a compile-time error (the simplest sound rule: the mangled
    spelling embeds the module name, and there is no principled identity
    to mangle into without one)."""
    source = "-hide([hide_no_module_atom])\n\nProbe(hide_no_module_atom),\n"
    with pytest.raises(SyntaxError, match="-hide requires a preceding -module"):
        _load_inline_clausal("_hide_no_module_test", source)


def test_hide_entries_must_be_bare_atoms():
    """``-hide`` is atom-only: a predicate-signature shape
    (``foo(A, B)``) is rejected -- predicates are already module-local
    through Python's own module scoping, so hiding does not apply to
    them."""
    source = (
        "-module(hide_bad_shape_test, [Probe(X)])\n"
        "-hide([foo(A, B)])\n"
        "\n"
        "Probe(1),\n"
    )
    with pytest.raises(SyntaxError, match="-hide entries must be bare atoms"):
        _load_inline_clausal("_hide_bad_shape_test", source)


# ── Strictness interplay: -hide entries count as declared ───────────────────


def test_hide_entries_count_as_declared_for_strictness():
    """A ``-strict_atoms`` file may bare-reference a name that is declared
    ONLY via ``-hide`` (no separate ``-module``/``-private`` listing) with
    no ``NameError`` -- ``-hide`` registers into ``transformer._atoms`` for
    strictness purposes, same as ``-module``/``-private`` (build step 2).
    ``hide_owner.clausal`` itself already carries ``-strict_atoms`` and
    loads clean (exercised by every other test above); this test isolates
    the claim with a minimal, self-contained fixture."""
    source = (
        "-strict_atoms\n"
        "-module(hide_strict_test, [Probe(X)])\n"
        "-hide([hide_strict_secret])\n"
        "\n"
        "Probe(hide_strict_secret),\n"
    )
    mod = _load_inline_clausal("_hide_strict_interplay_test", source)
    lm = mod.__dict__["$module"]
    out = Var()
    vals = [deref(out) for _ in call("Probe", out, module=lm)]
    assert vals == [mangle("hide_strict_test", "hide_strict_secret")]


def test_hide_does_not_satisfy_strictness_for_other_undeclared_atoms():
    """Sanity check on the strictness claim above: ``-hide`` only
    declares the names it LISTS -- an unrelated bare atom in the same
    strict file is still a compile-time ``NameError``."""
    source = (
        "-strict_atoms\n"
        "-module(hide_strict_neg_test, [Probe(X)])\n"
        "-hide([hide_strict_secret_declared])\n"
        "\n"
        "Probe(hide_strict_secret_undeclared),\n"
    )
    with pytest.raises(NameError):
        _load_inline_clausal("_hide_strict_interplay_neg_test", source)
