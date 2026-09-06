"""Constant-list membership lowers to a frozenset — semantics pins.

``X in [c1, c2, …]`` against a run of compile-time constants now consults
a memoised frozenset instead of scanning the list with ``unify()`` (see
:mod:`clausal.logic.runtime.const_set`).  A ``set`` is not a list, so the
substitution is only sound where nothing observable tells them apart.
The tests below pin the four ways they could differ:

* **order** — an unbound left operand must still enumerate in list order;
* **duplicates** — membership is a choice point, so ``a in [a, a, b]``
  succeeds twice and a set must not collapse that;
* **hashability** — an unhashable element or left operand must fall back
  to the scan, not raise ``TypeError``;
* **unification vs equality** — a set answers ``hash``/``__eq__`` where
  the scan answers ``unify()``; for the whitelisted types those must
  agree, including across the numeric tower (``1`` vs ``1.0``).

Every case is asserted against **both** builds — with the ``const_set``
optimisation on and off — so the tests establish that the fast path
agrees with the scan it replaces, not merely that it answers something
plausible.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from clausal.logic.atoms import char_atom, mint
from clausal.import_hook import _load_module
from clausal.logic.compiler.compile_ctx import (
    _ALL_OPTIMISATIONS,
    _default_enabled_optimisations,
)
from clausal.logic.solve import call
from clausal.logic.variables import Var, deref
from clausal.logic.runtime.const_set import _const_set, _CONST_SET_TYPES


# ── Harness ───────────────────────────────────────────────────────────────────

_SRC = """\
-private([a, b, c, d, e])

# ── order: an unbound left operand enumerates the list, in list order
order(X) <- (X in [c, a, b])
order_strings(X) <- (X in ["c", "a", "b"])

# ── duplicates: one solution per occurrence, ground or not
dup_enumerate(X) <- (X in [a, a, b])
dup_ground(X) <- (X in [a, a, b])
dup_numeric(X) <- (X in [1.0, 1])

# ── unification vs equality across the numeric tower
numeric(X) <- (X in [1, 2.5, 3])
tower(X) <- (X in [10, 20, 30])
bools(X) <- (X in ["y", "n", 7])

# ── the plain check-mode cases the fast path is for
atoms4(X) <- (X in [a, b, c, d])
strings4(X) <- (X in ["acquire", "dispose", "amend", "cancel"])
notin4(X) <- (X not in [a, b, c, d])
mixed(X) <- (X in [a, "a", 1, None])

# ── unhashable / off-whitelist / non-constant right operands keep the scan
tuples(X) <- (X in [(1, 2), (3, 4)])
nested(X) <- (X in [[1, 2], [3, 4]])
partial(X, Y) <- (X in [a, Y, c])

# ── the left operand may be an unhashable term
compound_probe(X) <- (X in [a, b, c, d])

# ── membership must still act as a choice point for the goals after it
after(X, Z) <- (X in [a, b, c], Z in [1, 2])

# ── one memo cell per callsite: enough clauses to trigger first-argument
# indexing, each with its own constant list, so an aliased cell would let
# one clause answer with another clause's set
band(1, X) <- (X in [a, b])
band(2, X) <- (X in [b, c])
band(3, X) <- (X in [c, d])
band(4, X) <- (X in [d, e])
band(5, X) <- (X in [e, a])
"""


def _load(name: str, const_set: bool):
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write(_SRC)
        path = f.name
    prev = os.environ.get("CLAUSAL_DISABLE_OPT")
    os.environ["CLAUSAL_DISABLE_OPT"] = "" if const_set else "const_set"
    try:
        pymod = _load_module(name, path)
        return pymod, pymod.__dict__["$module"]
    finally:
        if prev is None:
            os.environ.pop("CLAUSAL_DISABLE_OPT", None)
        else:
            os.environ["CLAUSAL_DISABLE_OPT"] = prev
        os.unlink(path)


_ON = _load("_t_cset_on", const_set=True)
_OFF = _load("_t_cset_off", const_set=False)


@pytest.fixture(params=[True, False], ids=["const_set-on", "const_set-off"])
def build(request):
    """The module compiled with the fast path on / off.

    Both must answer identically; that equality *is* the property under
    test, so every case runs twice rather than trusting one build.
    """
    return _ON if request.param else _OFF


def _solutions(build, functor, *args):
    """All solutions of ``functor(*args)``, each Var argument dereferenced."""
    pymod, mod = build
    resolved = [getattr(pymod, a[1:]) if isinstance(a, str) and a.startswith("@")
                else a for a in args]
    out = []
    for _ in call(functor, *resolved, module=mod):
        out.append(tuple(deref(a) for a in resolved))
    return out


def _values(build, functor, *args):
    """The first component of each solution — the usual single-Var case."""
    return [row[0] for row in _solutions(build, functor, *args)]


def _atom(build, name):
    return getattr(build[0], name)


# ── Order ─────────────────────────────────────────────────────────────────────

def test_unbound_left_operand_enumerates_in_list_order(build):
    """``X in [c, a, b]`` yields c, a, b — list order, not set order.

    Solution order is observable in Clausal (first-solution semantics,
    ``findall`` results, gold-test transcripts), so the fast path must
    decline whenever the left operand is unbound.

    P3-1 R2: atoms are interned global ``str``s (no more zero-field atom
    class with a ``.__name__`` attribute) — the atom's spelling IS the
    returned value.
    """
    names = _values(build, "order", Var())
    assert names == [char_atom("c"), char_atom("a"), char_atom("b")]


def test_unbound_left_operand_enumerates_strings_in_list_order(build):
    """Same for a list whose elements are literals, where CPython would
    otherwise be free to constant-fold the display into a frozenset."""
    assert _values(build, "order_strings", Var()) == [char_atom("c"), char_atom("a"), char_atom("b")]


# ── Duplicates ────────────────────────────────────────────────────────────────

def test_duplicate_element_yields_one_solution_per_occurrence(build):
    """``X in [a, a, b]`` with X unbound succeeds three times.

    P3-1 R2: atoms are interned global ``str``s — no ``.__name__``.
    """
    names = _values(build, "dup_enumerate", Var())
    assert names == [char_atom("a"), char_atom("a"), char_atom("b")]


def test_duplicate_element_yields_two_solutions_when_ground(build):
    """``a in [a, a, b]`` succeeds **twice** — membership is a choice point.

    This is the case a naive set substitution silently breaks: it would
    drop one solution from any conjunction to the right of the goal.
    """
    assert len(_solutions(build, "dup_ground", _atom(build, "a"))) == 2


def test_hash_equal_duplicates_count_as_duplicates(build):
    """``1 in [1.0, 1]`` succeeds twice, because ``unify(1, 1.0)`` succeeds.

    ``1.0`` and ``1`` are distinct list elements but a single set element,
    so the duplicate check has to be by hash-equality, not by surface form.
    """
    assert len(_solutions(build, "dup_numeric", 1)) == 2


# ── Unification vs equality ───────────────────────────────────────────────────

def test_int_matches_float_element(build):
    """``1 in [1, 2.5, 3]``: ints and floats unify by ``==``, and so does
    the set, so the two agree."""
    assert len(_solutions(build, "numeric", 1)) == 1


def test_float_matches_int_element(build):
    """``20.0 in [10, 20, 30]`` — cross-type, in the direction the set
    lookup has to hash the *float* and find the *int*."""
    assert len(_solutions(build, "tower", 20.0)) == 1


def test_bool_matches_int_element(build):
    """``True`` is ``1`` to both ``unify()`` and ``hash``; ``7`` is neither."""
    assert len(_solutions(build, "bools", True)) == 0
    assert len(_solutions(build, "bools", 7)) == 1


def test_string_matches_same_named_atom(build):
    """P3-1 §5/R2: an atom is an interned global ``str`` — its name IS the
    atom, so ``a`` (the atom) and ``"a"`` (the string) are the SAME term
    under both ``unify()`` and ``hash``/``__eq__``. ``mixed`` holds both
    ``a`` and ``"a"`` as distinct list *elements* (still two occurrences,
    per the duplicates contract this module pins elsewhere), so querying
    either spelling now matches both positions.

    (Formerly ``test_string_does_not_match_same_named_atom``, inverted —
    the pre-pivot per-module atom-class identity this test pinned no
    longer exists.)
    """
    assert len(_solutions(build, "mixed", "a")) == 2
    assert len(_solutions(build, "mixed", _atom(build, "a"))) == 2
    assert len(_solutions(build, "mixed", "b")) == 0


def test_atom_from_a_different_module_matches(build):
    """P3-1 §5/R2: atoms are global by spelling (no more per-module atom
    identity/class), so the same-named atom minted by a *different*
    compiled build is literally the same ``str`` and DOES match.

    (Formerly ``test_atom_from_a_different_module_does_not_match``,
    inverted — cross-module atom-identity mismatch was the retired
    per-module atom-class behaviour.)
    """
    other = _OFF if build is _ON else _ON
    assert len(_solutions(build, "atoms4", _atom(other, "a"))) == 1


def test_none_element_matches(build):
    assert len(_solutions(build, "mixed", None)) == 1


# ── Hashability / fallback ────────────────────────────────────────────────────

def test_off_whitelist_elements_fall_back(build):
    """Tuples hash fine, but ``tuple`` is off the whitelist — a tuple's
    ``unify()`` recurses into its members, which ``==`` does not model when
    a member is a Var.  The scan must still run, in list order."""
    assert _values(build, "tuples", Var()) == [(1, 2), (3, 4)]
    assert len(_solutions(build, "tuples", (3, 4))) == 1


def test_nested_list_elements_fall_back_without_raising(build):
    """Lists are unhashable, so ``X in [[1,2],[3,4]]`` keeps the scan."""
    assert _values(build, "nested", Var()) == [[1, 2], [3, 4]]
    assert len(_solutions(build, "nested", [3, 4])) == 1


def test_unhashable_left_operand_falls_back_without_raising(build):
    """``[1,2] in [a, b, c, d]`` must fail, not raise ``TypeError``.

    The frozenset exists for this callsite, so only the runtime type
    guard on the left operand keeps ``[1,2] in frozenset`` from being
    attempted.
    """
    assert _solutions(build, "compound_probe", [1, 2]) == []


def test_partial_list_falls_back(build):
    """A list holding a variable is not a constant list; the emitted set
    would be memoised from whatever the first call happened to bind."""
    x, y = Var(), Var()
    rows = _solutions(build, "partial", x, y)
    assert len(rows) == 3


# ── Choice-point behaviour is preserved ───────────────────────────────────────

def test_membership_remains_a_choice_point_for_later_goals(build):
    """The fast path replaces the collection, not the loop, so the goals
    to the right of a membership still see one solution per match."""
    rows = _solutions(build, "after", _atom(build, "b"), Var())
    assert [r[1] for r in rows] == [1, 2]


def test_notin_ground_hit_and_miss(build):
    assert _solutions(build, "notin4", _atom(build, "e")) == [(_atom(build, "e"),)]
    assert _solutions(build, "notin4", _atom(build, "a")) == []


def test_each_callsite_gets_its_own_memoised_set(build):
    """Five indexed clauses of one predicate, five different constant lists.

    All five memo cells live in the same per-predicate globals dict, so this
    pins that each clause answers from its own set rather than from whichever
    one was memoised first.  (Two things keep them apart: the cell name comes
    from a per-compilation counter, and each clause's globals are copied
    before the next clause compiles.  Only the observable outcome is asserted
    here — either mechanism alone is currently sufficient.)
    """
    expected = {
        "a": {1, 5}, "b": {1, 2}, "c": {2, 3}, "d": {3, 4}, "e": {4, 5},
    }
    for name, bands in expected.items():
        atom = _atom(build, name)
        got = {n for n in (1, 2, 3, 4, 5)
               if _solutions(build, "band", n, atom)}
        assert got == bands, f"atom {name}: matched bands {got}, want {bands}"


def test_notin_unbound_left_operand(build):
    """``X not in [...]`` with X unbound: the scan unifies X with the first
    element, so the goal fails.  The fast path must not change that."""
    assert _solutions(build, "notin4", Var()) == []


# ── The runtime eligibility check, directly ───────────────────────────────────

class TestConstSetBuilder:
    """``$const_set`` is the single gate that decides a callsite is safe.
    Its refusals are what the fallback tests above rely on."""

    def test_accepts_distinct_scalars(self):
        assert _const_set([1, 2, 3]) == frozenset({1, 2, 3})

    def test_refuses_duplicates(self):
        assert _const_set([char_atom("a"), char_atom("a"), char_atom("b")]) is False

    def test_refuses_hash_equal_duplicates(self):
        assert _const_set([1, 1.0]) is False
        assert _const_set([0, False]) is False

    def test_refuses_unhashable_element(self):
        assert _const_set([[1], [2]]) is False

    def test_refuses_off_whitelist_element(self):
        from decimal import Decimal
        # Hashable, but ``hash(Decimal('nan'))`` raises, so Decimal is off
        # the whitelist wholesale rather than case by case.
        assert _const_set([Decimal("1"), Decimal("2")]) is False

    def test_refuses_var_element(self):
        assert _const_set([Var(), Var()]) is False

    def test_refuses_short_and_non_list(self):
        assert _const_set([1]) is False
        assert _const_set([]) is False
        assert _const_set((1, 2)) is False

    def test_whitelisted_types_all_hash_without_raising(self):
        """Every whitelisted type must have a total ``hash``; otherwise the
        runtime guard would let a membership test raise."""
        from fractions import Fraction
        samples = [0, 0.0, float("nan"), True, complex(1, 2), "s", b"s",
                   None, Fraction(1, 3)]
        for value in samples:
            assert value.__class__ in _CONST_SET_TYPES
            hash(value)  # must not raise


def test_const_set_is_a_registered_optimisation():
    assert "const_set" in _ALL_OPTIMISATIONS


def test_const_set_is_disableable_by_env(monkeypatch):
    monkeypatch.setenv("CLAUSAL_DISABLE_OPT", "const_set")
    assert "const_set" not in _default_enabled_optimisations()
