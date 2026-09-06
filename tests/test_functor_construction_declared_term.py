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

from clausal.logic.builtins.inspection import _functor__3, _univ__2
from clausal.logic.predicate import PredicateMeta, make_predicate
from clausal.logic.variables import Var, Trail, deref, unify


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
    """A declared functor of arity 1 — the shape from the field report."""
    return make_predicate("tfcdt_cite", ["key"])


# ── functor/3 construction ─────────────────────────────────────────────────


def test_class_name_builds_the_declared_term(cite):
    """The case that motivated this: hand construction the class itself."""
    built = built_by(_functor__3, cite, 1)
    assert isinstance(built, cite), (
        f"built {type(built).__name__}, not a {cite.__name__} instance"
    )


def test_constructed_term_unifies_with_the_real_thing(cite):
    """The property that was broken, stated as unification rather than type:
    what construction builds must unify with a term written out longhand."""
    assert unify(built_by(_functor__3, cite, 1), cite(Var()), Trail())


def test_atom_name_builds_a_generic_cell(cite):
    """An ATOM name is deliberately not resolved back to a class: resolving
    ``tfcdt_cite`` would have to pick a module, and a downstream helper
    library's ``entry_key/2`` relies on this arm building a generic term it
    can decompose to a name.

    That generic term is a CELL, not a ``Compound`` (atoms-as-cells design
    §6.4): cells are how the engine represents a compound data term, so what
    construction builds now unifies with the same term written longhand.
    """
    built = built_by(_functor__3, "tfcdt_cite", 1)
    assert type(built) is tuple and built[0] == "tfcdt_cite" and len(built) == 2
    assert not isinstance(built, cite)


def test_arity_mismatch_falls_through_to_a_generic_cell(cite):
    """A declared arity-1 class asked for at arity 2 is not that term, so the
    generic shape remains the honest answer — as today, and not an error.

    The functor spelling is pinned too: A09-F027 exists because a fall-through
    that stringified the name the wrong way once built a bogus functor like
    ``"f(1)"``, and a type-only assertion would not notice that.
    """
    built = built_by(_functor__3, cite, 2)
    assert type(built) is tuple and len(built) == 3
    assert built[0] == "tfcdt_cite"


def test_arity_zero_atom_asked_at_arity_one_is_still_generic():
    """A downstream helper library's own pattern: ``functor(PROBE, KEY, 1)``
    over an arity-0 schema atom must keep building a generic term, because
    ``entry_key/2`` then decomposes it to get the name.  Pinned so this fix
    cannot break that library; the generic term is a cell (§6.4), which
    decomposes through the same funnel a Compound did."""
    schema_atom = make_predicate("tfcdt_applicant_age", [])
    built = built_by(_functor__3, schema_atom, 1)
    assert type(built) is tuple and len(built) == 2
    assert built[0] == "tfcdt_applicant_age"


def test_arity_zero_still_yields_the_name_itself():
    """``functor(T, Name, 0)`` binds T to Name unchanged — the A09-F027
    round-trip property for atomic constants."""
    atom = make_predicate("tfcdt_zed", [])
    assert built_by(_functor__3, atom, 0) is atom


def test_metaclass_minted_class_also_rebuilds():
    """The fixtures above use ``make_predicate``, but an in-file predicate is
    minted as a generated ``class <functor>(metaclass=PredicateMeta)`` block
    (``_make_functor_class_ast``) — the route real ``.clausal`` source takes.
    The gate reads ``_fields``, which both origins carry, so cover the one the
    corpus actually uses."""
    class tfcdt_minted(metaclass=PredicateMeta):
        _fields = ("key",)

    built = built_by(_functor__3, tfcdt_minted, 1)
    assert isinstance(built, tfcdt_minted)
    assert unify(built, tfcdt_minted(Var()), Trail())


# ── the round trip ─────────────────────────────────────────────────────────


def test_decompose_then_reconstruct_round_trips(cite):
    """Decomposition yields an ATOM name, so rebuilding from that name yields
    the generic cell — but rebuilding from the class round-trips."""
    from clausal.logic.atoms import mint

    original = cite(Var())
    N, A, trail = Var(), Var(), Trail()
    gen = _functor__3(original, N, A, trail, None)
    next(gen)
    assert deref(N) == mint("tfcdt_cite")  # §6.4: the name position is atoms
    assert deref(A) == 1

    assert unify(built_by(_functor__3, cite, 1), original, Trail())


# ── unpack/2 construction (the sibling site) ───────────────────────────────


def test_unpack_class_name_builds_the_declared_term(cite):
    """``unpack/2`` shares the defect and must move with ``functor/3``."""
    built = built_by(_univ__2, [cite, 42])
    assert isinstance(built, cite), (
        f"built {type(built).__name__}, not a {cite.__name__} instance"
    )


def test_unpack_carries_the_argument_values(cite):
    """Unlike functor/3's fresh Vars, unpack supplies real arguments."""
    assert unify(built_by(_univ__2, [cite, 42]), cite(42), Trail())


def test_unpack_atom_name_builds_a_generic_cell(cite):
    assert built_by(_univ__2, ["tfcdt_cite", 42]) == ("tfcdt_cite", 42)


def test_unpack_arity_mismatch_falls_through_to_a_generic_cell(cite):
    built = built_by(_univ__2, [cite, 1, 2, 3])
    assert built == ("tfcdt_cite", 1, 2, 3)


# ── the shared error arm ───────────────────────────────────────────────────
#
# Both sites used to raise this inline.  Consolidating it into
# ``_construct_named`` means the culprit name is threaded in as ``who``, so
# nothing but a test keeps the two sites reporting themselves correctly.


@pytest.mark.parametrize(
    "builtin,args,who",
    [
        (_functor__3, (3, 1), "functor/3"),
        (_univ__2, ([3, 1, 2],), "unpack/2"),
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
