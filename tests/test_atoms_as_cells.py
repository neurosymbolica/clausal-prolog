"""Atom probes: the 1-tuple ``("foo",)`` IS the atom (spec §6.3, §6.4).
Each test names the spec row it pins.

Written as Stage A "accepted BESIDE the str atom" probes; after THE FLIP
(Task 11) a plain ``str`` is a STRING, so the dual-acceptance halves are
refusals now and these read as the atom's own contract.

Builtin goals are cell-shaped tuples, and ``solve/1`` (module=None) refuses
an unqualified cell goal outright (P3-3 Task 6, ``solve.py``'s
``_module_for_moduleless_solve``) — there is no calling module to infer for
a bare tuple goal, builtin or not.  So every probe here runs against a
throwaway loaded module, the same convention ``tests/test_cell_goals.py``
uses for cell goals (``_load_module`` + ``module.__dict__["$module"]``);
the module's own content is irrelevant since only builtins are exercised.
"""
import os
import tempfile

import pytest

import clausal.import_hook  # noqa: F401 — installs the meta-path finder
from clausal.import_hook import _load_module
from clausal.logic.atoms import char_atom, mint
from clausal.logic.cells import chars
from clausal.logic.cells import chars as _chars_carrier
from clausal.logic.exceptions import LogicException
from clausal.logic.predicate import is_atom_value
from clausal.logic.solve import solve
from clausal.logic.variables import Var, deref

CELL = "foo"


def _lm(module):
    return module.__dict__["$module"]


@pytest.fixture
def mod():
    with tempfile.NamedTemporaryFile(
        suffix=".clausal", mode="w", delete=False
    ) as f:
        f.write("z0,\n")
        path = f.name
    try:
        return _load_module("_atoms_as_cells_probe", path)
    finally:
        os.unlink(path)


def _true(goal, m):
    return len(list(solve(goal, _lm(m)))) == 1


def test_atom_1_accepts_cell_atom(mod):           # §6.3 row atom/1
    assert _true(("atom", CELL), mod)


def test_atomic_1_accepts_cell_atom(mod):         # §6.3 row atomic/1
    assert _true(("atomic", CELL), mod)


def test_compound_1_rejects_cell_atom(mod):       # §6.3 arity-0 is not compound
    assert not _true(("compound", CELL), mod)


def test_callable_1_accepts_cell_atom(mod):       # §6.3 row callable/1
    assert _true(("callable_", CELL), mod)


def test_must_be_atom_accepts_cell_atom_and_cell_type_name(mod):
    # THE FLIP retired Stage A's dual acceptance: a plain ``str`` is a
    # STRING now, so only the cell shape answers.
    assert _true(("must_be", "atom", CELL), mod)
    with pytest.raises(LogicException):
        list(solve(("must_be", chars("atom"), CELL), _lm(mod)))


def test_must_be_compound_accepts_cell(mod):
    assert _true(("must_be", "compound", ("f", 1)), mod)
    with pytest.raises(LogicException):
        list(solve(("must_be", "compound", CELL), _lm(mod)))


# ── Task 5: the name position (spec §5.4, §6.4; §13 rows 7–12, 18c) ───────────
#
# ``functor/3`` and ``unpack/2`` (``=..``) CONSTRUCT CELLS, never a
# ``Compound``, and hand back ``mint(slot0)`` as the name.  ``'.'``/2 in the
# name position builds the engine's list shapes (§5.4) — never a
# ``(".", H, T)`` cell.


def _one(goal, m, *vars_):
    """Solve *goal* against *m*, assert exactly ONE answer, and return the
    ``deref``'d values of *vars_* SNAPSHOTTED inside the iteration.

    ``solve`` undoes the trail when its generator is exhausted, so a deref
    taken after ``list(solve(...))`` sees the variables unbound again.
    """
    snaps = [tuple(deref(v) for v in vars_) for _ in solve(goal, _lm(m))]
    assert len(snaps) == 1, f"expected exactly 1 answer, got {len(snaps)}"
    return snaps[0]


def test_functor_3_constructs_a_cell_and_names_an_atom(mod):   # §6.4, §13 rows 7–8
    T = Var()
    (t,) = _one(("functor", T, mint("foo"), 2), mod, T)
    assert type(t) is tuple and t[0] == "foo" and len(t) == 3
    N, A = Var(), Var()
    n, a = _one(("functor", ("foo", 1), N, A), mod, N, A)
    assert n == mint("foo") and a == 1
    T0 = Var()
    (t0,) = _one(("functor", T0, mint("foo"), 0), mod, T0)
    assert t0 == mint("foo")


def test_functor_3_accepts_a_cell_atom_name(mod):              # §6.4, Stage A
    T = Var()
    (t,) = _one(("functor", T, "foo", 2), mod, T)
    assert type(t) is tuple and t[0] == "foo" and len(t) == 3
    T0 = Var()
    (t0,) = _one(("functor", T0, "foo", 0), mod, T0)
    assert t0 == "foo"


def test_univ_constructs_a_cell_and_round_trips(mod):          # §13 rows 10–11
    T = Var()
    (t,) = _one(("unpack", T, [mint("foo"), 1]), mod, T)
    assert t == ("foo", 1)
    L = Var()
    (lv,) = _one(("unpack", ("foo", 1, "bar"), L), mod, L)
    assert lv == [mint("foo"), 1, "bar"]
    T2 = Var()
    (t2,) = _one(("unpack", T2, lv), mod, T2)
    assert t2 == ("foo", 1, "bar")


def test_univ_accepts_a_cell_atom_name(mod):                   # §6.4, Stage A
    T = Var()
    (t,) = _one(("unpack", T, ["foo", 1]), mod, T)
    assert t == ("foo", 1)
    T0 = Var()
    (t0,) = _one(("unpack", T0, ["foo"]), mod, T0)
    assert t0 == "foo"


def test_functor_3_rejects_number_name_with_arity(mod):
    with pytest.raises(LogicException):
        list(solve(("functor", Var(), 3, 2), _lm(mod)))


def test_functor_3_rejects_a_non_atomic_name(mod):             # §6.4 type_error(atomic)
    with pytest.raises(LogicException):
        list(solve(("functor", Var(), [1, 2], 0), _lm(mod)))


def test_univ_rejects_a_non_atomic_single_element_name(mod):   # §6.4 type_error(atomic)
    with pytest.raises(LogicException):
        list(solve(("unpack", Var(), [[1, 2]]), _lm(mod)))


def test_cons_construction_never_builds_a_dot_cell(mod):       # §5.4, §13 row 18c
    T = Var()
    (t,) = _one(("unpack", T, [mint("."), char_atom("a"), "bc"]), mod, T)
    assert t == "abc"
    T2 = Var()
    (t2,) = _one(("unpack", T2, [mint("."), 1, [2]]), mod, T2)
    assert t2 == [1, 2]
    T3 = Var()
    (t3,) = _one(("functor", T3, mint("."), 2), mod, T3)
    from clausal.terms import SegList
    assert isinstance(t3, SegList)
    T4 = Var()
    (t4,) = _one(("unpack", T4, [mint("."), 1, []]), mod, T4)
    assert t4 == [1]


def test_gensym_and_global_atom_mint_atoms(mod):
    A = Var()
    (a,) = _one(("gensym", mint("g"), A), mod, A)
    assert is_atom_value(a)
    A2 = Var()
    (a2,) = _one(("gensym", "g", A2), mod, A2)              # cell prefix, Stage A
    assert is_atom_value(a2)
    G = Var()
    (g,) = _one(("global_atom", mint("zzq_probe"), G), mod, G)
    assert g == mint("zzq_probe")
    _one(("global_atom", mint("zzq_probe"), mint("zzq_probe")), mod)  # guard, by ==
    G2 = Var()
    (g2,) = _one(("global_atom", "zzq_probe", G2), mod, G2)  # cell name, Stage A
    assert g2 == mint("zzq_probe")


def test_type_error_term_carries_atom_args():
    from clausal.logic.exceptions import type_error
    t = type_error("atom", 3, "who")
    assert t.args[0].args[0] == mint("atom")
    assert t.args[1] == "who"                                  # context stays a string


def test_listing_takes_the_indicator_of_a_zero_arity_predicate(mod, capsys):
    # ``z0`` is the one fact the probe module defines (see the ``mod`` fixture).
    # Operator ruling 2026-09-25 ("do what Scryer does"): the bare atom ``z0`` is
    # type_error(predicate_indicator, z0); ``z0/0`` is the spelling.
    from clausal.logic.exceptions import LogicException
    with pytest.raises(LogicException) as exc:
        list(solve(("listing", "z0"), _lm(mod)))
    assert exc.value.term.args[0].args[0] == "predicate_indicator"
    assert len(list(solve(("listing", ("/", "z0", 0)), _lm(mod)))) == 1
    assert "z0/0" in capsys.readouterr().out


def test_resolve_module_accepts_a_cell_atom_designator(mod):
    from clausal.logic.solve import resolve_module
    assert (resolve_module(mint("_atoms_as_cells_probe"))
            is resolve_module("_atoms_as_cells_probe"))


def test_maybe_promote_uses_is_char_atom():
    """§6.2: the list→str promotion tests ``is_char_atom``, and joins the
    elements' SPELLINGS — not the elements themselves (Task 7)."""
    from clausal.logic.atoms import is_char_atom
    from clausal.logic.runtime import _seg_helpers
    assert _seg_helpers.maybe_promote_to_str([char_atom("a"), char_atom("b")]) == chars("ab")
    assert _seg_helpers.maybe_promote_to_str(["ab", "c"]) == ["ab", "c"]
    assert _seg_helpers.maybe_promote_to_str([]) == []
    # Every element the promotion accepts is exactly a char atom.
    assert is_char_atom(char_atom("a")) and not is_char_atom("ab")


def test_as_items_yields_char_atoms_for_a_str():
    """§6.2: ``_as_items`` on a str produces CHARS, not raw 1-char strs."""
    from clausal.logic.atoms import is_char_atom, spelling
    from clausal.logic.builtins.lists import _as_items, _seq_result
    items = _as_items(chars("abc"))
    assert len(items) == 3
    assert all(is_char_atom(c) for c in items)
    assert "".join(spelling(c) for c in items) == "abc"
    # ... and _seq_result reconstructs the str from those same chars.
    assert _seq_result(items, was_string=True) == chars("abc")
    assert _seq_result(items, was_string=False) is items


def test_segstring_walk_unify_and_eq_speak_chars():
    """§6.2: SegString's list-facing arms are char-atom-shaped (Task 7)."""
    from clausal.logic.atoms import is_char_atom, spelling
    from clausal.logic.variables import Trail, Var, deref, unify
    from clausal.terms import SegString, VarSeg
    # __walk__: a VarSeg bound to a char LIST joins the chars' spellings.
    X = Var()
    trail = Trail()
    assert unify(X, [char_atom("l"), char_atom("o")], trail)
    assert SegString(["hel", VarSeg(X)]).__walk__() == chars("hello")
    # __unify__ against a list: the walked str materialises as char atoms.
    A, B = Var(), Var()
    trail2 = Trail()
    assert SegString(["ab"]).__unify__([A, B], trail2)
    assert is_char_atom(deref(A)) and spelling(deref(A)) == "a"
    assert is_char_atom(deref(B)) and spelling(deref(B)) == "b"
    # __eq__ against a list of chars.
    assert SegString(["ab"]) == [char_atom("a"), char_atom("b")]
    assert not (SegString(["ab"]) == ["ab"])


def test_ground_seglist_of_cell_chars_round_trips():
    """§6.2 / Task 7 fix round 1: ``SegList.__walk__`` promotes a ground
    SegList of CELL chars to a ``str`` (``maybe_promote_to_str`` accepts the
    cell under Stage A dual acceptance), so every arm that reverses that
    promotion must hand back CHARS again.  Before the fix ``list(w)`` gave raw
    1-char strs and the SegList stopped being equal to — or unifiable with —
    its own elements."""
    from clausal.logic.variables import Trail, Var, deref, unify
    from clausal.terms import ConcreteSeg, SegList, VarSeg
    chars = ["a", "b"]
    sl = SegList([ConcreteSeg(list(chars))])

    # The promotion itself (the premise of the bug).
    assert sl.__walk__() == _chars_carrier("ab")

    # __eq__ list arm, __contains__, to_list, iteration, indexing.
    assert sl == chars
    assert "a" in sl and "b" in sl
    assert "c" not in sl
    assert sl.to_list() == chars
    assert list(sl) == chars
    assert sl[0] == "a"
    assert len(sl) == 2

    # __unify__ against the list of the same cell chars.
    t = Trail()
    assert unify(sl, list(chars), t)
    # ... and against a SegList built from the same cell chars.
    t2 = Trail()
    assert unify(sl, SegList([ConcreteSeg(list(chars))]).to_list(), t2)
    # THE FLIP reinstated the str<->char-list rule, so the CELL char shape
    # is the one that unifies with the promoted str; a list of one-element
    # STRINGS does not (spec §6.2: ``("a",)`` vs ``"a"`` still FAILS).
    t3 = Trail()
    assert not unify(SegList([ConcreteSeg([_chars_carrier("a"), _chars_carrier("b")])]), _chars_carrier("ab"), t3)
    t4 = Trail()
    assert unify(sl, _chars_carrier("ab"), t4)

    # ... and the vars in a matching pattern bind to the CELL chars.
    A, B = Var(), Var()
    t3 = Trail()
    assert unify(sl, [A, B], t3)
    assert deref(A) == "a" and deref(B) == "b"

    # A non-ground SegList still lines up against a str target, whose
    # ELEMENTS are chars and whose star SLICE stays a str (R-S2) —
    # ``_apply_seglist_split`` / ``_seglist_unify_gen``. Stage A's canonical
    # char is the plain str, so that is what a str target's elements match.
    X = Var()
    t5 = Trail()
    partial = SegList([ConcreteSeg([char_atom("h")]), VarSeg(X)])
    assert unify(partial, _chars_carrier("hi"), t5)
    assert deref(X) == _chars_carrier("i")
    # The CELL char is the canonical char now, so the same pattern written
    # with a literal 1-tuple matches too — it is the same term.
    Y = Var()
    t6 = Trail()
    assert unify(SegList([ConcreteSeg(["h"]), VarSeg(Y)]), _chars_carrier("hi"), t6)


def test_seglist_str_tail_and_head_are_char_lists():
    """``SegList + str`` / ``str + SegList`` splat the str into CHARS."""
    from clausal.logic.atoms import is_char_atom
    from clausal.terms import ConcreteSeg, SegList
    tail = (SegList([ConcreteSeg([1])]) + "ab").__walk__()
    assert tail[0] == 1 and all(is_char_atom(c) for c in tail[1:])
    head = ("ab" + SegList([ConcreteSeg([1])])).__walk__()
    assert head[-1] == 1 and all(is_char_atom(c) for c in head[:-1])


# ── Task 9: compiler-side acceptors and the identity pins (spec §5.2, §5.3) ──


def test_call_n_folds_cell_atom_goal(mod):
    """§5.2 / §6.4: ``call/N`` folds a CELL atom goal exactly as it folds
    today's str atom — ``call(atom, foo)`` is ``atom(foo)``.  Nothing in
    ``higher_order._resolve_named_goal`` needed changing (an arity-0 cell
    already answers ``compound_cell_shape``); this pins that it stays so."""
    assert _true(("call", "atom", "foo"), mod)
    # ... and a STRING goal is refused (THE FLIP, spec §6.4).
    with pytest.raises(LogicException):
        list(solve(("call", chars("atom"), "foo"), _lm(mod)))


def test_is_mangled_accepts_atom():
    """§5.3: ``is_mangled``/``demangle``/``demangle_for_display`` accept the
    ATOM as well as the bare spelling."""
    from clausal.logic.atoms import (
        demangle, demangle_for_display, is_mangled, mangle,
    )
    a = mint(mangle("m", "bar"))
    assert is_mangled(a)
    assert demangle(a) == ("m", "bar")
    assert demangle_for_display(a) == "m.bar"
    # ``mint`` is a str under Plan 0, so drive the CELL shape explicitly too —
    # otherwise this row only re-tests the bare spelling until Stage B.
    cell = mangle("m", "bar")
    assert is_mangled(cell)
    assert demangle(cell) == ("m", "bar")
    assert demangle_for_display(cell) == "m.bar"
    # A non-mangled atom is not mangled, and displays as its own spelling.
    assert not is_mangled(mint("bar"))
    assert not is_mangled("bar")
    assert demangle_for_display(mint("bar")) == "bar"
    assert demangle_for_display("bar") == "bar"
    # The bare-spelling calls are unchanged.
    assert is_mangled(mangle("m", "bar"))
    assert demangle_for_display(mangle("m", "bar")) == "m.bar"
    # A non-atom is still not mangled, and demangle still refuses it.
    assert not is_mangled(42)
    assert not is_mangled(("m", "bar"))
    with pytest.raises(ValueError):
        demangle("bar")


def test_functor_spelling_accepts_cell_atom():
    """§5.2: a module binding that is a CELL atom answers with its spelling,
    the same way today's str binding does (``terms_to_ast._functor_spelling``
    — the declared-data-functor binding shape, R6)."""
    from clausal.logic.compiler.terms_to_ast import _functor_spelling
    assert _functor_spelling("pt", "local_pt") == "pt"
    # A STRING binding is not an atom, so it is "some unrelated value" and
    # the leaf name is the answer.
    assert _functor_spelling(chars("pt"), "local_pt") == "local_pt"
    assert _functor_spelling(None, "local_pt") == "local_pt"


def test_atom_shadows_row_accepts_cell_atom():
    """§5.2: ``globals_env._atom_shadows_row`` — an ATOM binding is DATA and
    cannot be a call target, whether it is spelled as a str or as a cell."""
    from clausal.logic.compiler.globals_env import _atom_shadows_row
    from clausal.logic.database import Clause, Database
    from clausal.terms import Compound

    db = Database()
    db.assertz(Clause(head=Compound("shade", (1,)), body=[True]))
    assert _atom_shadows_row("shade", db, "shade", 1)
    # A STRING binding is not an atom, and is trusted as before.
    assert not _atom_shadows_row(chars("shade"), db, "shade", 1)
    # No such row → no shadowing; a non-atom binding is trusted as before.
    assert not _atom_shadows_row("shade", db, "shade", 2)
    assert not _atom_shadows_row(len, db, "shade", 1)
