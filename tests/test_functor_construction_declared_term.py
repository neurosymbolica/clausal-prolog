"""``functor/3`` and ``unpack/2`` construction must rebuild a *declared* term.

Both construction sites reduced a ``PredicateMeta`` name to ``name.__name__``
and built a generic :class:`~clausal.terms.Compound` from the string, throwing
the class away even when the caller handed it over directly.  So
decompose-then-reconstruct never round-tripped for a declared with-fields term:

    T is cite(art), functor(T, N, A), functor(T2, N, A)   # T2 does not unify with T

and neither did handing construction the class itself, ``functor(T2, cite, 1)``.
The rebuilt Compound *renders identically* to the real term — a failing goal
reported ``T2 = cite(_)`` against a goal ``T2 is cite(_)`` — so the mismatch was
invisible at the surface.  See
``todo/done/functor-3-names-an-atom-as-a-class-but-a-compound-as-a-string.md``.

A downstream helper library had already hit this and documented a workaround
rather than a fix ("ATTR-LIST BRANCH — VERIFIED SEMANTICS"): its note that a
constructed entry "does NOT unify with a declared term-class instance of the
same name/arity" is this defect, measured from the outside.

Only the **class** arm changes.  A plain ATOM name still builds a generic
term, with no attempt to resolve it back to a class: which module's ``cite`` a
bare name means is genuinely ambiguous under module-local atom identity, and
that library's ``entry_key/2`` depends on the name arm behaving exactly as it
does today.

The atoms-as-cells design (§6.4, 2026-09-06) then replaced that generic term:
it is a CELL, ``("tfcdt_cite", X)``, not a ``Compound``.  The property these
tests pin is unchanged — an atom name builds the *generic* shape, a class name
builds the *declared* one — only the generic shape's spelling moved.
"""

import pytest

from clausal.logic.atoms import mint
from clausal.logic.cells import is_cell, cell_functor, cell_arity
from clausal.logic.builtins.inspection import _functor__3, _univ__2

from clausal.logic.variables import Var, Trail, deref, unify
from tests.predicate_api_support import term_ctor


def built_by(builtin, *args):
    """Return what *builtin* constructs into its first argument.

    The builtins undo their trail mark on resumption, so the binding only
    exists *during* a yield — ``list(...)`` would hand back a bare Var.  A
    goal-level harness is not usable here either: a ``PredicateMeta`` passed
    as a literal goal argument is rejected up front by the compiler
    (``PredicateAsTermError``), and handing over the class is precisely the
    case under test.
    """
    term = Var()
    trail = Trail()
    gen = builtin(term, *args, trail, None)
    try:
        next(gen)
    except StopIteration:
        return None
    return deref(term)


@pytest.fixture
def cite():
    """A declared functor of arity 1 — the shape from the field report.  A
    term constructor (``term_ctor``); it was a ``make_predicate`` class,
    whose class-as-NAME tests went with the class at W4b-3 slice 7."""
    return term_ctor("tfcdt_cite", ["key"])


# ── functor/3 construction ─────────────────────────────────────────────────


def test_atom_name_builds_a_generic_cell(cite):
    """An ATOM name is deliberately not resolved back to a class: resolving
    ``tfcdt_cite`` would have to pick a module, and a downstream helper
    library's ``entry_key/2`` relies on this arm building a generic term it
    can decompose to a name.

    That generic term is a CELL, not a ``Compound`` (atoms-as-cells design
    §6.4): cells are how the engine represents a compound data term, so what
    construction builds now unifies with the same term written longhand.
    """
    built = built_by(_functor__3, mint("tfcdt_cite"), 1)
    assert type(built) is tuple and built[0] == "tfcdt_cite" and len(built) == 2


def test_arity_zero_atom_asked_at_arity_one_is_still_generic():
    """A downstream helper library's own pattern: ``functor(PROBE, KEY, 1)``
    over an arity-0 schema atom must keep building a generic term, because
    ``entry_key/2`` then decomposes it to get the name.  Pinned so this fix
    cannot break that library; the generic term is a cell (§6.4), which
    decomposes through the same funnel a Compound did."""
    schema_atom = mint("tfcdt_applicant_age")   # the atom (a class until W4b-3 slice 7)
    built = built_by(_functor__3, schema_atom, 1)
    assert type(built) is tuple and len(built) == 2
    assert built[0] == "tfcdt_applicant_age"


def test_builtin_name_atom_builds_a_generic_cell_not_a_type_error():
    """W4b-1 fix round 1 (review): ``field_names_for`` used to have a
    ``_BUILTIN_FIELDS`` fallback, so ``functor(T, when, 2)`` -- an ordinary
    atom that happens to spell a registered builtin -- resolved to
    ``('condition', 'goal')`` in ``_construct_named``'s class arm and then
    called ``name_val(*args)`` on a plain ``str``, raising ``TypeError:
    'str' object is not callable``.  The fallback is removed; a bare
    builtin-shaped name must build the generic cell exactly like any other
    atom name (``test_atom_name_builds_a_generic_cell`` above), never raise."""
    built = built_by(_functor__3, mint("when"), 2)
    assert is_cell(built) and cell_functor(built) == "when"
    assert cell_arity(built) == 2


def test_arity_zero_still_yields_the_name_itself():
    """``functor(T, Name, 0)`` binds T to Name unchanged — the A09-F027
    round-trip property for atomic constants."""
    atom = mint("tfcdt_zed")        # the atom (a class until W4b-3 slice 7)
    assert built_by(_functor__3, atom, 0) == atom


# ── the round trip ─────────────────────────────────────────────────────────


# ── unpack/2 construction (the sibling site) ───────────────────────────────


def test_unpack_atom_name_builds_a_generic_cell(cite):
    assert built_by(_univ__2, [mint("tfcdt_cite"), 42]) == ("tfcdt_cite", 42)


# ── the shared error arm ───────────────────────────────────────────────────
#
# Both sites used to raise this inline.  Consolidating it into
# ``_construct_named`` means the culprit name is threaded in as ``who``, so
# nothing but a test keeps the two sites reporting themselves correctly.


@pytest.mark.parametrize(
    "builtin,args,who",
    [
        (_functor__3, (3, 1), "functor/3"),
        (_univ__2, ([3, 1, 2],), "(=..)/2"),   # unpack/2 is '=..'/2's alias
    ],
)
def test_non_atom_name_raises_type_error_naming_its_own_site(builtin, args, who):
    """A09-F027: a non-atom functor is ``type_error(atom, Name)``, not a bogus
    term — ``unpack(T, [3, 1, 2])`` once built ``Compound("3", (1, 2))``.  Each
    site must name *itself* as the culprit."""
    from clausal.logic.exceptions import LogicException

    with pytest.raises(LogicException) as exc_info:
        built_by(builtin, *args)
    assert who in str(exc_info.value)
    assert "atom" in str(exc_info.value)


# ── CRITICAL 2 (final fix wave, 2026-09-23): a mangled NAME is not a class ──
#
# CRITICAL 1's fix made ``field_names_for``'s arm 3 actually answer for a
# mangled atom string resolved against a real loaded module.  That answering
# is not by itself "this is a class" -- ``_construct_named``'s class arms
# used to be gated on ``_ctor_fields is not None`` alone, so once arm 3
# started answering for a plain ``str``, the exact-arity match branch called
# ``name_val(*args)`` on a string (``TypeError: 'str' object is not
# callable``) and the mismatch branch read ``name_val.__name__`` on a string
# (``AttributeError: 'str' object has no attribute '__name__'``).  These two
# defects used to cancel (arm 3 was inert, so ``_ctor_fields`` was always
# ``None`` for a mangled name) -- fixing CRITICAL 1 alone would have made
# ``functor/3`` crash on every migrated call site that hands it a mangled
# name at a mismatched arity.


@pytest.fixture
def loaded_hide_owner():
    """Load the real fixture module once; ``same/2`` has real field names
    ``('x', 'y')`` (declared ``-module(hide_owner, [holds/1, label/1,
    same/2])``)."""
    import os

    import clausal.import_hook  # noqa: F401 -- installs the meta-path finder
    from clausal.import_hook import _load_module

    fixture = os.path.join(
        os.path.dirname(__file__), "fixtures", "hide_owner.clausal")
    return _load_module("hide_owner", fixture)


def test_mangled_name_at_matching_arity_does_not_crash(loaded_hide_owner):
    """Exact arity match (2 args for ``same/2``) used to take the
    ``name_val(*args)`` branch and raise ``TypeError: 'str' object is not
    callable``; a mangled name is not a class, so it must fall through to
    the generic cell shape instead, same as any other atom name."""
    from clausal.logic.atoms import mangle

    name = mangle("hide_owner", "same")
    built = built_by(_functor__3, name, 2)
    assert built == (name, built[1], built[2])
    assert len(built) == 3


def test_mangled_name_at_mismatched_arity_does_not_crash(loaded_hide_owner):
    """Arity mismatch (1 arg for ``same/2``, declared at 2) used to take the
    ``mint(name_val.__name__)`` fall-through branch and raise
    ``AttributeError: 'str' object has no attribute '__name__'`` -- a
    string has no ``__name__``.  Must fall through to the generic cell
    shape cleanly instead."""
    from clausal.logic.atoms import mangle

    name = mangle("hide_owner", "same")
    built = built_by(_functor__3, name, 1)
    assert built == (name, built[1])
    assert len(built) == 2
