"""Tests that Python fallback implementations match C versions.

These ensure the codebase works correctly even if C extensions fail to build.
Each test calls the _py fallback directly and verifies it produces the same
result as the C-accelerated version.
"""

from __future__ import annotations

import pytest

from clausal.logic.variables import Var, Trail, deref, unify, is_var
from clausal.logic.predicate import PredicateMeta
from clausal.terms import Compound, KWTerm


# ── predicate.py fallbacks ───────────────────────────────────────────────────

from clausal.logic.predicate import (
    _is_term_instance_py,
    _is_zero_field_class_py,
    _term_field_names_py,
    is_term_instance,
    is_zero_field_class,
    term_field_names,
)


class Pt(metaclass=PredicateMeta):
    _fields = ("x", "y")


class Atom(metaclass=PredicateMeta):
    _fields = ()


class TestIsTermInstanceFallback:

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _is_term_instance_py(t) == is_term_instance(t) == True

    def test_class_not_instance(self):
        # nv
        assert _is_term_instance_py(Pt) == is_term_instance(Pt) == False

    def test_int_not_instance(self):
        # nv
        assert _is_term_instance_py(42) == is_term_instance(42) == False

    def test_compound_is_dataclass(self):
        # nv
        c = Compound("f", (1,))
        assert _is_term_instance_py(c) == is_term_instance(c)

    def test_var_not_instance(self):
        # nv
        assert _is_term_instance_py(Var()) == is_term_instance(Var()) == False


class TestIsZeroFieldClassFallback:
    """Task 12 renamed the zero-field-CLASS test; the C symbol stays
    ``is_atom`` and is imported under the new name in ``predicate.py``."""

    def test_zero_arity(self):
        # nv
        assert _is_zero_field_class_py(Atom) == is_zero_field_class(Atom) == True

    def test_non_zero_arity(self):
        # nv
        assert _is_zero_field_class_py(Pt) == is_zero_field_class(Pt) == False

    def test_not_predicate_meta(self):
        # nv
        assert _is_zero_field_class_py(int) == is_zero_field_class(int) == False


class TestTermFieldNamesFallback:

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _term_field_names_py(t) == term_field_names(t) == ("x", "y")

    def test_compound_dataclass(self):
        # nv
        c = Compound("f", (1, 2))
        py = _term_field_names_py(c)
        c_ver = term_field_names(c)
        assert py == c_ver

    def test_non_term_raises(self):
        # nv
        with pytest.raises(TypeError):
            _term_field_names_py(42)


# ── _helpers.py fallbacks ────────────────────────────────────────────────────

from clausal.logic.builtins._helpers import (
    _functor_name_py, _arity_py, _nth_arg_py, _args_list_py,
    _is_compound_py, _is_ground_py,
    _functor_name, _arity, _nth_arg, _args_list,
    _is_compound, _is_ground,
)


class TestFunctorNameFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2))
        assert _functor_name_py(c) == _functor_name(c) == "f"

    def test_kwterm(self):
        # nv
        t = KWTerm("rel", a=1)
        assert _functor_name_py(t) == _functor_name(t) == "rel"

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _functor_name_py(t) == _functor_name(t) == "Pt"

    def test_list_empty(self):
        # nv
        assert _functor_name_py([]) == _functor_name([]) == "[]"

    def test_list_nonempty(self):
        # nv
        assert _functor_name_py([1]) == _functor_name([1]) == "."

    def test_int(self):
        # nv
        assert _functor_name_py(42) == _functor_name(42)

    def test_string_nonempty_is_a_cons_cell(self):
        # nv
        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.4) reversed
        # P3-1's retirement: a str is a STRING now — the list of its
        # char atoms — so it decomposes as that list does.  Task 12b
        # retired the pre-cell "a str is its own functor" arm from the
        # ``_py`` twin AND from the C accessor together, so all three
        # answers agree even when the fallback is called directly.
        assert _functor_name("hello") == _functor_name_py("hello") == "."

    def test_string_empty_nil(self):
        # nv
        # F089 (audit 2026-06-13): empty str → "[]" (the nil atom) —
        # unaffected by the P3-1 §1b cons-rule retirement (the empty
        # string is the one str value that legitimately reads as the
        # list-shaped nil atom, matching the empty-list case above).
        assert _functor_name_py("") == _functor_name("") == "[]"


class TestArityFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2, 3))
        assert _arity_py(c) == _arity(c) == 3

    def test_predicate_instance(self):
        # nv
        t = Pt(x=1, y=2)
        assert _arity_py(t) == _arity(t) == 2

    def test_int(self):
        # nv
        assert _arity_py(42) == _arity(42) == 0

    def test_atom(self):
        # nv
        assert _arity_py(Atom) == _arity(Atom) == 0

    def test_string_nonempty_is_arity_two(self):
        # nv
        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.4) reversed
        # P3-1's retirement: a str is a STRING now — the list of its
        # char atoms — so it decomposes as that list does.  Task 12b
        # retired the pre-cell "a str is atomic" arm from the ``_py``
        # twin AND from the C accessor together.
        assert _arity("hello") == _arity_py("hello") == 2

    def test_string_empty_is_arity_zero(self):
        # nv — unaffected by the retirement (empty str was already 0).
        assert _arity_py("") == _arity("") == 0


class TestNthArgFallback:

    def test_compound_first(self):
        # nv
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 1) == _nth_arg(c, 1) == 10

    def test_compound_second(self):
        # nv
        c = Compound("f", (10, 20))
        assert _nth_arg_py(c, 2) == _nth_arg(c, 2) == 20

    def test_out_of_range(self):
        # nv
        c = Compound("f", (10,))
        with pytest.raises(IndexError):
            _nth_arg_py(c, 5)
        with pytest.raises(IndexError):
            _nth_arg(c, 5)

    def test_string_args_are_head_char_and_str_tail(self):
        # nv
        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.4) reversed
        # P3-1's retirement: a str is a STRING now — the list of its
        # char atoms — so it decomposes as that list does.  The funnel
        # WRAPPER answers; the pre-cell ``_py`` twin still carries the
        # retired atom reading and is no longer reached for a str.
        assert _nth_arg("hello", 1) == char_atom("h")
        assert _nth_arg("hello", 2) == "ello"
        with pytest.raises(IndexError):
            _nth_arg("hello", 3)
        with pytest.raises(IndexError):
            _nth_arg_py("hello", 1)


class TestArgsListFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1, 2, 3))
        assert _args_list_py(c) == _args_list(c) == [1, 2, 3]

    def test_predicate_instance(self):
        # nv
        t = Pt(x=10, y=20)
        assert _args_list_py(t) == _args_list(t) == [10, 20]

    def test_non_compound(self):
        # nv
        assert _args_list_py(42) == _args_list(42) == []

    def test_string_nonempty_args_are_head_and_tail(self):
        # nv
        # THE FLIP (2026-09-06-atoms-as-cells-strings §6.4) reversed
        # P3-1's retirement: a str is a STRING now — the list of its
        # char atoms — so it decomposes as that list does.  The funnel
        # WRAPPER answers; the pre-cell ``_py`` twin still carries the
        # retired atom reading and is no longer reached for a str.
        assert _args_list("hello") == [char_atom("h"), "ello"]
        assert _args_list_py("hello") == []


class TestIsCompoundFallback:

    def test_compound(self):
        # nv
        c = Compound("f", (1,))
        assert _is_compound_py(c) == _is_compound(c) == True

    def test_kwterm(self):
        # nv
        t = KWTerm("r", a=1)
        assert _is_compound_py(t) == _is_compound(t) == True

    def test_int(self):
        # nv
        assert _is_compound_py(42) == _is_compound(42) == False


class TestIsGroundFallback:

    def test_ground_int(self):
        # nv
        assert _is_ground_py(42) == _is_ground(42) == True

    def test_ground_list(self):
        # nv
        assert _is_ground_py([1, 2]) == _is_ground([1, 2]) == True

    def test_unbound_var(self):
        # nv
        v = Var()
        assert _is_ground_py(v) == _is_ground(v) == False

    def test_list_with_var(self):
        # nv
        v = Var()
        assert _is_ground_py([1, v]) == _is_ground([1, v]) == False

    def test_compound_with_var(self):
        # nv
        v = Var()
        c = Compound("f", (1, v))
        assert _is_ground_py(c) == _is_ground(c) == False

    def test_compound_ground(self):
        # nv
        c = Compound("f", (1, 2))
        assert _is_ground_py(c) == _is_ground(c) == True

    def test_kwterm_with_var(self):
        # nv
        v = Var()
        t = KWTerm("r", a=v)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_kwterm_ground(self):
        # nv
        t = KWTerm("r", a=1)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_predicate_instance_with_var(self):
        # nv
        v = Var()
        t = Pt(x=v, y=1)
        assert _is_ground_py(t) == _is_ground(t) == False

    def test_predicate_instance_ground(self):
        # nv
        t = Pt(x=1, y=2)
        assert _is_ground_py(t) == _is_ground(t) == True

    def test_bound_var_ground(self):
        # nv
        v = Var()
        trail = Trail()
        unify(v, 42, trail)
        assert _is_ground_py(v) == _is_ground(v) == True

    def test_atom_ground(self):
        # nv
        assert _is_ground_py(Atom) == _is_ground(Atom) == True


# ── inspection.py fallbacks ──────────────────────────────────────────────────

from clausal.logic.builtins.inspection import (
    _copy_term_py, _collect_vars_py,
    _copy_term_impl, _collect_vars_impl,
)


class TestCopyTermFallback:

    def test_ground_unchanged(self):
        # nv
        assert _copy_term_py(42, {}) == _copy_term_impl(42, {}) == 42

    def test_list_copied(self):
        # nv
        py = _copy_term_py([1, 2, 3], {})
        c = _copy_term_impl([1, 2, 3], {})
        assert py == c == [1, 2, 3]

    def test_var_freshened(self):
        # nv
        x = Var()
        py_result = _copy_term_py(x, {})
        c_result = _copy_term_impl(x, {})
        assert is_var(py_result) and py_result is not x
        assert is_var(c_result) and c_result is not x

    def test_compound_copied(self):
        # nv
        c = Compound("f", (1, Var()))
        py = _copy_term_py(c, {})
        assert isinstance(py, Compound)
        assert py.functor == "f"
        assert py.args[0] == 1
        assert is_var(py.args[1])

    def test_kwterm_functor_preserved(self):
        """KWTerm copy preserves functor (bug fix verification)."""
        # nv
        t = KWTerm("rel", a=1, b=2)
        py = _copy_term_py(t, {})
        c = _copy_term_impl(t, {})
        assert py.functor == "rel"
        assert c.functor == "rel"

    def test_kwterm_var_freshened(self):
        # nv
        x = Var()
        t = KWTerm("r", a=x)
        py = _copy_term_py(t, {})
        assert is_var(py._fields["a"])
        assert py._fields["a"] is not x

    def test_sharing_preserved(self):
        # nv
        x = Var()
        py = _copy_term_py([x, x], {})
        assert py[0] is py[1]  # same fresh var
        assert py[0] is not x


class TestCollectVarsFallback:

    def test_ground_no_vars(self):
        # nv
        py_result = []
        _collect_vars_py(42, py_result)
        c_result = []
        _collect_vars_impl(42, c_result)
        assert py_result == c_result == []

    def test_single_var(self):
        # nv
        x = Var()
        py_result = []
        _collect_vars_py(x, py_result)
        c_result = []
        _collect_vars_impl(x, c_result)
        assert len(py_result) == len(c_result) == 1

    def test_dedup(self):
        # nv
        x = Var()
        py_result = []
        _collect_vars_py([x, x, x], py_result)
        c_result = []
        _collect_vars_impl([x, x, x], c_result)
        assert len(py_result) == len(c_result) == 1

    def test_compound_vars(self):
        # nv
        x, y = Var(), Var()
        c = Compound("f", (x, 1, y))
        py_result = []
        _collect_vars_py(c, py_result)
        c_result = []
        _collect_vars_impl(c, c_result)
        assert len(py_result) == len(c_result) == 2


# ── P3-2 Task 2C: cells (plain tuples) through the C twins ───────────────────
#
# THE FLIP (Task 2) made a plain tuple — a CELL — the representation of every
# compound data term, and the three C walkers behind ``copy_term/2``,
# ``term_variables/2`` and ``ground/1`` had no tuple branch: a cell was an
# opaque leaf, so a "copy" kept the ORIGINAL's variables, ``term_variables``
# saw none of them, and ``ground/1`` said yes to a term holding a free Var.
# Task 2 bought correctness by running the Python twins unconditionally at a
# measured ~3.4x cost; Task 2C gave the C functions the branch and restored
# the dispatch.
#
# C/Python twin drift is silent corruption rather than an error, so these
# tests compare the RAW C entry points against the Python twins over a corpus
# of shapes, and separately pin the wrapper (which is what the engine calls).

from typing import NamedTuple

from clausal.logic.cells import TUPLE_TAG
from clausal.logic.predicate import term_field_names as _tfn
from clausal.terms import SegList, SegString, VarSeg, ConcreteSeg

try:
    from clausal.logic.variables._variables import (
        _copy_term_impl as _c_copy_raw,
        _collect_vars_impl as _c_collect_raw,
        _is_ground as _c_is_ground_raw,
        _functor_name as _c_functor_name_raw,
        _arity as _c_arity_raw,
    )
    _HAVE_C = True
except ImportError:  # pragma: no cover — pure-Python build
    _HAVE_C = False

requires_c = pytest.mark.skipif(not _HAVE_C, reason="C accelerator not built")


class _NT(NamedTuple):
    """A tuple SUBCLASS — deliberately NOT a cell.

    All six implementations gate their cell branch on exact type
    (``type(x) is tuple`` / ``PyTuple_CheckExact``), so a tuple subclass is
    opaque to every one of them: ``is_cell`` excludes a subclass by design, a
    rebuild would lose the subclass's type, and an implementation that read
    THROUGH one while its siblings did not would answer "not ground" for a
    term whose variables it could neither enumerate nor copy (Task 2C fix
    round 1, controller ruling).
    """

    a: object
    b: object


def _corpus():
    """(name, term) pairs, rebuilt on every call so the Vars are fresh.

    Excludes ``Seg*``: those are short-circuited to Python by the wrapper on
    purpose (F092/F093 — the C twins have never known about them), so raw-C
    parity is not claimed for them.  They are covered through the wrapper by
    the ``TestWrapperUsesTheCPathAgain`` Seg* tests below.
    """
    X, Y, Z = Var(), Var(), Var()
    bound = Var()
    unify(bound, ("pt", 1, 2), Trail())
    return [
        # --- pre-cell shapes: these must not move ---
        ("int", 42),
        ("str", "abc"),
        ("float", 1.5),
        ("bytes", b"xy"),
        ("none", None),
        ("bool", True),
        ("var", X),
        ("bound_var_to_cell", bound),
        ("list", [1, X, 2]),
        ("compound", Compound("f", (1, X))),
        ("compound_var_functor", Compound(X, (1, 2))),
        ("kwterm", KWTerm("r", a=X, b=2)),
        ("instance", Pt(x=X, y=2)),
        ("atom_class", Atom),
        ("class_with_fields", Pt),
        # --- cells ---
        ("cell_ground", ("pt", 1, 2)),
        ("cell_with_var", ("pt", 1, X)),
        ("cell_zero_arity", ("pt",)),
        ("cell_empty_tuple", ()),
        ("cell_shared_var", ("pt", X, X)),
        ("cell_var_functor", (X, 1, 2)),
        ("cell_nested", ("outer", ("inner", X), Y)),
        ("cell_deep_nested", ("a", ("b", ("c", ("d", X))))),
        ("tuple_data_cell", (TUPLE_TAG, 1, X)),
        ("tuple_data_nested", (TUPLE_TAG, ("pt", X), Y)),
        # --- cells reached only through another container ---
        ("cell_in_list", [("pt", X), ("pt", Y)]),
        ("cell_in_list_in_cell", ("f", [("g", X)], Y)),
        ("cell_in_compound", Compound("f", (("g", X), 2))),
        ("cell_in_kwterm", KWTerm("r", a=("g", X))),
        ("cell_in_instance", Pt(x=("g", X), y=2)),
        ("instance_in_cell", ("f", Pt(x=X, y=2))),
        ("compound_in_cell", ("f", Compound("g", (X,)))),
        ("list_of_lists_of_cells", [[("p", X)], [("q", Y), ("r", Z)]]),
        # --- shared structure across two cells ---
        ("cell_pair_sharing", ("f", ("g", X), ("h", X))),
        # --- tuple SUBCLASS: not a cell for copy/collect, ground reads it ---
        ("namedtuple", _NT(a=1, b=X)),
        ("namedtuple_ground", _NT(a=1, b=2)),
        ("namedtuple_in_cell", ("f", _NT(a=1, b=X))),
    ]


# A PRE-EXISTING twin divergence this corpus turned up, unrelated to cells and
# deliberately not "fixed" by Task 2C (a non-cell answer change is exactly what
# this phase's invariant forbids): A01-F003 taught the C twins to visit a
# ``Compound``'s FUNCTOR slot — an unbound functor Var is a variable of the
# term — but the Python twins in ``inspection.py`` still walk ``term.args``
# only.  ``c_is_ground`` and ``_is_ground_py`` DO agree here (both reject a
# non-str functor), so only the copy/collect pair diverges.  Pinned below by
# ``test_a_var_functor_compound_is_a_known_twin_divergence`` so the drift is on
# record rather than silent.
_KNOWN_COMPOUND_FUNCTOR_DIVERGENCE = {"compound_var_functor"}


def _shape(term):
    """Structural fingerprint: fresh Vars compare by FIRST-OCCURRENCE POSITION.

    Two copies made by two implementations can never share Var identity, so
    identity is normalised away and everything else is compared exactly —
    including the concrete container type, which is the whole point (a cell
    rebuilt as a list, or a namedtuple flattened to a plain tuple, must show
    up as a difference).
    """
    seen: dict = {}

    def go(t):
        t = deref(t)
        if is_var(t):
            return seen.setdefault(id(t), "V%d" % len(seen))
        if t is None or isinstance(t, (bool, int, float, str, bytes)):
            return ("lit", type(t).__name__, t)
        if isinstance(t, type):
            return ("type", t.__module__, t.__qualname__)
        if isinstance(t, list):
            return ("list", [go(e) for e in t])
        if type(t) is tuple:
            return ("cell", [go(e) for e in t])
        if isinstance(t, tuple):  # tuple SUBCLASS (namedtuple, ...)
            return ("tuple_subclass", type(t).__qualname__, [go(e) for e in t])
        if isinstance(t, Compound):
            return ("compound", go(t.functor), [go(a) for a in t.args])
        if isinstance(t, KWTerm):
            return ("kwterm", t.functor, [(k, go(v)) for k, v in t.items()])
        if isinstance(t, SegList):
            return ("seglist", [go(s) for s in t.segments])
        if isinstance(t, SegString):
            return ("segstring", [go(s) for s in t.segments])
        if isinstance(t, ConcreteSeg):
            return ("concreteseg", [go(e) for e in t.elements])
        if isinstance(t, VarSeg):
            return ("varseg", go(t.var))
        if is_term_instance(t):
            return ("inst", type(t).__qualname__,
                    [(n, go(getattr(t, n))) for n in _tfn(t)])
        return ("opaque", repr(t))

    return go(term)


@requires_c
class TestCellCopyTermTwinParity:
    """``c_copy_term`` vs ``_copy_term_py`` over the whole corpus."""

    @pytest.mark.parametrize("name", [n for n, _ in _corpus()])
    def test_copy_is_structurally_identical(self, name):
        # nv
        term_py = dict(_corpus())[name]
        term_c = dict(_corpus())[name]
        assert _shape(term_py) == _shape(term_c), "corpus builder is not deterministic"
        assert _shape(_copy_term_py(term_py, {})) == _shape(_c_copy_raw(term_c, {}))

    @pytest.mark.parametrize("name", [n for n, _ in _corpus()])
    def test_copy_shares_no_variable_with_the_original(self, name):
        """The bug: a cell "copy" that handed back the original's Vars."""
        # nv
        for impl in (lambda t: _copy_term_py(t, {}), lambda t: _c_copy_raw(t, {})):
            term = dict(_corpus())[name]
            originals: list = []
            _collect_vars_py(term, originals)
            copied: list = []
            _collect_vars_py(impl(term), copied)
            assert len(copied) == len(originals)
            assert not ({id(v) for v in copied} & {id(v) for v in originals})

    def test_a_ground_cell_is_returned_unchanged_by_identity(self):
        """Reuse-if-unchanged: the twin's allocation-free path, mirrored in C."""
        # nv
        cell = ("pt", 1, ("q", 2))
        assert _copy_term_py(cell, {}) is cell
        assert _c_copy_raw(cell, {}) is cell
        # ... and the nested slot is not rebuilt either
        assert _c_copy_raw(cell, {})[2] is cell[2]

    def test_a_cell_with_a_var_is_a_new_tuple(self):
        # nv
        x = Var()
        cell = ("pt", 1, x)
        for out in (_copy_term_py(cell, {}), _c_copy_raw(cell, {})):
            assert out is not cell
            assert type(out) is tuple
            assert out[0] == "pt" and out[1] == 1
            assert is_var(out[2]) and out[2] is not x

    def test_sharing_inside_a_cell_is_preserved(self):
        # nv
        x = Var()
        cell = ("f", ("g", x), ("h", x))
        for out in (_copy_term_py(cell, {}), _c_copy_raw(cell, {})):
            assert out[1][1] is out[2][1]
            assert out[1][1] is not x

    def test_a_var_functor_slot_is_freshened(self):
        """Slot 0 needs no special case: the generic recursion freshens it."""
        # nv
        x = Var()
        cell = (x, 1)
        for out in (_copy_term_py(cell, {}), _c_copy_raw(cell, {})):
            assert is_var(out[0]) and out[0] is not x

    def test_a_str_functor_slot_keeps_its_identity(self):
        # nv
        functor = "pt"
        cell = (functor, Var())
        assert _c_copy_raw(cell, {})[0] is functor

    def test_the_tuple_tag_survives_a_copy(self):
        """``TUPLE_TAG`` is the ``tuple`` TYPE — it must not be rebuilt."""
        # nv
        cell = (TUPLE_TAG, 1, Var())
        for out in (_copy_term_py(cell, {}), _c_copy_raw(cell, {})):
            assert out[0] is TUPLE_TAG

    def test_a_namedtuple_is_not_flattened_into_a_cell(self):
        """``type(x) is tuple``, not ``isinstance`` — both twins agree."""
        # nv
        nt = _NT(a=1, b=Var())
        assert type(_copy_term_py(nt, {})) is _NT
        assert type(_c_copy_raw(nt, {})) is _NT
        # ... and, being an unknown shape to both, it is returned as-is
        assert _copy_term_py(nt, {}) is nt
        assert _c_copy_raw(nt, {}) is nt

    def test_a_shared_var_map_threads_across_two_calls(self):
        """Sharing survives when one map copies two terms — as clause copying does."""
        # nv
        x = Var()
        shared: dict = {}
        a = _c_copy_raw(("head", x), shared)
        b = _c_copy_raw(("body", x), shared)
        assert a[1] is b[1] and a[1] is not x

    def test_a_deeply_nested_cell_chain_copies(self):
        """200 levels of cell — well inside both twins' recursion budgets."""
        # nv
        x = Var()
        term: object = x
        for _ in range(200):
            term = ("f", term)
        for out in (_copy_term_py(term, {}), _c_copy_raw(term, {})):
            probe = out
            for _ in range(200):
                probe = probe[1]
            assert is_var(probe) and probe is not x


@requires_c
class TestCellCollectVarsTwinParity:
    """``c_collect_vars`` vs ``_collect_vars_py`` over the whole corpus."""

    @pytest.mark.parametrize(
        "name",
        [n for n, _ in _corpus() if n not in _KNOWN_COMPOUND_FUNCTOR_DIVERGENCE],
    )
    def test_same_variables_in_the_same_order(self, name):
        # nv
        term = dict(_corpus())[name]
        py_result: list = []
        _collect_vars_py(term, py_result)
        c_result: list = []
        _c_collect_raw(term, c_result)
        # These walk the SAME term, so identity comparison is exact.
        assert [id(v) for v in py_result] == [id(v) for v in c_result]

    def test_a_var_inside_a_cell_is_found(self):
        # nv
        x = Var()
        result: list = []
        _c_collect_raw(("pt", 1, x), result)
        assert result == [x]

    def test_a_functor_slot_var_is_found_first(self):
        # nv
        f, x = Var(), Var()
        result: list = []
        _c_collect_raw((f, x), result)
        assert result == [f, x]

    def test_dedup_across_nested_cells(self):
        # nv
        x = Var()
        result: list = []
        _c_collect_raw(("f", ("g", x), ("h", x)), result)
        assert result == [x]

    def test_a_namedtuple_is_a_leaf_for_both_twins(self):
        """One third of the coherent trio — see
        ``TestTupleSubclassTrioIsCoherent``."""
        # nv
        nt = _NT(a=1, b=Var())
        py_result: list = []
        _collect_vars_py(nt, py_result)
        c_result: list = []
        _c_collect_raw(nt, c_result)
        assert py_result == c_result == []

    def test_a_deeply_nested_cell_chain_is_walked(self):
        # nv
        x = Var()
        term: object = x
        for _ in range(200):
            term = ("f", term)
        result: list = []
        _c_collect_raw(term, result)
        assert result == [x]

    def test_a_var_functor_compound_is_a_known_twin_divergence(self):
        """Pre-existing, not a cell question — see the note at
        ``_KNOWN_COMPOUND_FUNCTOR_DIVERGENCE``.  The C twin visits the functor
        slot (A01-F003), the Python twin does not.  Recorded, not fixed."""
        # nv
        f = Var()
        term = Compound(f, (1, 2))
        py_result: list = []
        _collect_vars_py(term, py_result)
        c_result: list = []
        _c_collect_raw(term, c_result)
        assert py_result == []
        assert c_result == [f]
        # The CELL analogue has no such split: both twins walk slot 0.
        cell_py: list = []
        _collect_vars_py((f, 1, 2), cell_py)
        cell_c: list = []
        _c_collect_raw((f, 1, 2), cell_c)
        assert cell_py == cell_c == [f]


@requires_c
class TestCellIsGroundTwinParity:
    """``c_is_ground`` vs ``_is_ground_py`` over the whole corpus."""

    @pytest.mark.parametrize("name", [n for n, _ in _corpus()])
    def test_same_answer(self, name):
        # nv
        term = dict(_corpus())[name]
        assert _is_ground_py(term) == bool(_c_is_ground_raw(term))

    def test_a_cell_holding_a_free_var_is_not_ground(self):
        """The bug: ``ground(pt(1, Y))`` answered TRUE."""
        # nv
        assert _c_is_ground_raw(("pt", 1, Var())) is False
        assert _c_is_ground_raw(("pt", 1, 2)) is True

    def test_a_cell_nested_in_a_compound_is_reached(self):
        # nv
        assert _c_is_ground_raw(Compound("f", (("pt", Var()),))) is False

    def test_a_namedtuple_is_opaque_to_both_twins(self):
        """Exact-type, like the copy/collect twins — controller ruling, Task 2C
        fix round 1.  The first cut read through a tuple subclass here
        (``isinstance``) while copy/collect stayed exact, which made a
        namedtuple holding a free Var NON-ground yet unenumerable and
        uncopyable.  The coherent trio is asserted whole in
        ``TestTupleSubclassTrioIsCoherent`` below; this pins the ground half
        against BOTH twins."""
        # nv
        nt = _NT(a=1, b=Var())
        assert _is_ground_py(nt) is True
        assert _c_is_ground_raw(nt) is True
        # ... while the CELL with the same free Var is not ground, in both.
        cell = ("f", 1, Var())
        assert _is_ground_py(cell) is False
        assert _c_is_ground_raw(cell) is False

    def test_a_deeply_nested_cell_chain_is_walked(self):
        # nv
        term: object = Var()
        for _ in range(200):
            term = ("f", term)
        assert _is_ground_py(term) is False
        assert _c_is_ground_raw(term) is False


@requires_c
class TestStringDecompositionTwinParity:
    """A ``str`` decomposes as its char LIST does — in all three answers.

    Task 12 found the ``str`` arms of ``_functor_name_py``/``_arity_py`` and
    of their C twins ``_functor_name``/``_arity`` still carrying P3-1's
    retired reading ("a str IS an atom, so it is its own functor with arity
    0").  The post-flip WRAPPER in ``builtins/_helpers.py`` answered
    ``"."``/2 in front of them, so the arms were shadowed and the suite was
    green — but calling the accessor directly, as any out-of-tree consumer
    of the C module can, still got the pre-flip answer.  Task 12b retired
    both halves in one move (the global constraint: Python and C twins
    change together, with the parity tests run).

    This is the case that fails if either half is retired alone.
    """

    @pytest.mark.parametrize("text,name,arity", [
        ("hello", ".", 2),
        ("a", ".", 2),
        ("", "[]", 0),
    ])
    def test_c_and_python_agree_with_the_wrapper(self, text, name, arity):
        # nv
        assert _c_functor_name_raw(text) == _functor_name_py(text) == name
        assert _c_arity_raw(text) == _arity_py(text) == arity
        # …and the funnel wrapper, which is what the builtins call.
        assert _functor_name(text) == name
        assert _arity(text) == arity

    def test_the_answer_is_the_char_list_s_answer(self):
        """The reading itself, not just twin agreement: a string answers
        exactly what the list of its char atoms answers (§6.4)."""
        # nv
        chars = [char_atom(c) for c in "hi"]
        assert _c_functor_name_raw("hi") == _c_functor_name_raw(chars)
        assert _c_arity_raw("hi") == _c_arity_raw(chars)
        assert _c_functor_name_raw("") == _c_functor_name_raw([])
        assert _c_arity_raw("") == _c_arity_raw([])


class TestWrapperUsesTheCPathAgain:
    """The dispatch Task 2 bypassed, restored — and Seg* still short-circuited."""

    @pytest.mark.parametrize(
        "name",
        [n for n, _ in _corpus() if n not in _KNOWN_COMPOUND_FUNCTOR_DIVERGENCE],
    )
    def test_wrapper_agrees_with_the_python_twin(self, name):
        # nv
        term_a = dict(_corpus())[name]
        term_b = dict(_corpus())[name]
        assert _shape(_copy_term_py(term_a, {})) == _shape(_copy_term_impl(term_b, {}))

        py_result: list = []
        _collect_vars_py(term_a, py_result)
        c_result: list = []
        _collect_vars_impl(term_a, c_result)
        assert [id(v) for v in py_result] == [id(v) for v in c_result]

        assert _is_ground_py(term_a) == _is_ground(term_a)

    def test_seg_list_still_gets_an_independent_copy(self):
        """F092: the C twins are Seg*-blind; the wrapper must keep routing them."""
        # nv
        x = Var()
        seg = SegList([ConcreteSeg([1]), VarSeg(x)])
        copied = _copy_term_impl(seg, {})
        assert isinstance(copied, SegList)
        assert copied.segments[1].var is not x

    def test_seg_list_vars_are_still_collected(self):
        """F093."""
        # nv
        x = Var()
        seg = SegList([ConcreteSeg([1]), VarSeg(x)])
        result: list = []
        _collect_vars_impl(seg, result)
        assert result == [x]

    def test_seg_string_with_a_free_varseg_is_still_not_ground(self):
        """F083."""
        # nv
        assert _is_ground(SegString([VarSeg(Var())])) is False

    def test_a_cell_inside_a_seg_list_is_reached_through_the_python_route(self):
        # nv
        x = Var()
        seg = SegList([ConcreteSeg([("pt", x)])])
        result: list = []
        _collect_vars_impl(seg, result)
        assert result == [x]
        assert _is_ground(seg) is False


class TestTupleSubclassTrioIsCoherent:
    """A tuple SUBCLASS is opaque to all three functions, or to none.

    Task 2C's first cut split the trio: ``ground/1`` read through a namedtuple
    (inclusive check) while ``copy_term`` and ``term_variables`` treated it as
    opaque (exact checks).  A ``_NT(a=1, b=Var())`` was then reported
    NON-ground while having no enumerable variables and no copy that could
    freshen them — an incoherent answer, and a change to pre-flip behaviour
    for a shape that is not a cell.  The controller ruled exact-type
    everywhere.  Each assertion below is stated against BOTH implementations
    and beside the CELL that the same three functions DO see into, so the line
    the trio draws is the cell/non-cell line and nothing else.
    """

    def test_the_three_answers_agree_that_a_namedtuple_is_opaque(self):
        # nv
        x = Var()
        nt = _NT(a=1, b=x)

        # ground/1: opaque -> nothing inside is seen -> GROUND.
        assert _is_ground_py(nt) is True
        assert _c_is_ground_raw(nt) is True
        assert _is_ground(nt) is True

        # term_variables/2: opaque -> no variables.
        for collect in (_collect_vars_py, _c_collect_raw, _collect_vars_impl):
            result: list = []
            collect(nt, result)
            assert result == []

        # copy_term/2: opaque -> returned as-is, sharing x with the original.
        for copy in (lambda t: _copy_term_py(t, {}),
                     lambda t: _c_copy_raw(t, {}),
                     lambda t: _copy_term_impl(t, {})):
            out = copy(nt)
            assert out is nt
            assert out.b is x

    def test_the_cell_with_the_same_free_var_is_seen_by_all_three(self):
        """The contrast case: exact-type excludes the SUBCLASS, not tuples."""
        # nv
        x = Var()
        cell = ("f", 1, x)

        assert _is_ground_py(cell) is False
        assert _c_is_ground_raw(cell) is False
        assert _is_ground(cell) is False

        for collect in (_collect_vars_py, _c_collect_raw, _collect_vars_impl):
            result: list = []
            collect(cell, result)
            assert result == [x]

        for copy in (lambda t: _copy_term_py(t, {}),
                     lambda t: _c_copy_raw(t, {}),
                     lambda t: _copy_term_impl(t, {})):
            out = copy(cell)
            assert out is not cell
            assert is_var(out[2]) and out[2] is not x

    def test_a_namedtuple_nested_inside_a_cell_stays_opaque(self):
        """The trio must not leak through a container, either."""
        # nv
        x = Var()
        term = ("f", _NT(a=1, b=x))
        assert _is_ground(term) is True
        result: list = []
        _collect_vars_impl(term, result)
        assert result == []
        # The cell around it is still rebuilt only if something changed —
        # nothing did, so the identity short-circuit returns the original.
        assert _copy_term_impl(term, {}) is term


class TestTheWrapperActuallyReachesC:
    """The dispatch restoration itself, not just the twins' agreement.

    Every other test in this file compares the wrapper against the Python
    twin, so reverting ``_copy_term_impl`` / ``_collect_vars_impl`` /
    ``_is_ground`` to "call the Python twin unconditionally" would leave the
    file green while quietly giving back the whole point of Task 2C.  These
    tests fail in that case.

    Two independent methods, because neither alone is enough: an ORACLE shape
    on which the two implementations demonstrably differ, and a SPY on the
    module-global C name (looked up at call time inside the wrapper, so
    ``monkeypatch.setattr`` on the module reaches it).
    """

    # --- oracle: Compound with a Var functor (see
    #     _KNOWN_COMPOUND_FUNCTOR_DIVERGENCE).  Python walks args only, C
    #     visits the functor slot too (A01-F003), so the answer names the
    #     implementation that ran.

    @requires_c
    def test_term_variables_wrapper_returns_the_c_answer(self):
        # nv
        f = Var()
        term = Compound(f, (1, 2))

        control: list = []
        _collect_vars_py(term, control)
        assert control == [], "oracle broken: the twins no longer differ here"

        result: list = []
        _collect_vars_impl(term, result)
        assert result == [f], "the wrapper ran the PYTHON twin, not C"

    @requires_c
    def test_copy_term_wrapper_returns_the_c_answer(self):
        # nv
        f = Var()
        term = Compound(f, (1, 2))

        control = _copy_term_py(term, {})
        assert control.functor is f, "oracle broken: the twins no longer differ"

        out = _copy_term_impl(term, {})
        assert is_var(out.functor)
        assert out.functor is not f, "the wrapper ran the PYTHON twin, not C"

    # --- spy: ground/1's twins agree on the oracle shape (both reject a
    #     non-str functor), so the only way to prove which one ran is to watch
    #     the C entry point.  Applied to all three for symmetry.

    def test_is_ground_wrapper_calls_the_c_entry_point(self, monkeypatch):
        # nv
        if not _HAVE_C:
            pytest.skip("C accelerator not built")
        from clausal.logic.builtins import _helpers

        calls = []
        real = _helpers._c_is_ground
        monkeypatch.setattr(
            _helpers, "_c_is_ground",
            lambda t: (calls.append(t), real(t))[1],
        )
        assert _helpers._is_ground(("pt", 1, 2)) is True
        assert len(calls) == 1, "the wrapper never reached the C _is_ground"

    def test_copy_and_collect_wrappers_call_their_c_entry_points(self, monkeypatch):
        # nv
        if not _HAVE_C:
            pytest.skip("C accelerator not built")
        from clausal.logic.builtins import inspection

        copies, collects = [], []
        real_copy = inspection._c_copy_term_impl
        real_collect = inspection._c_collect_vars_impl
        monkeypatch.setattr(
            inspection, "_c_copy_term_impl",
            lambda t, m: (copies.append(t), real_copy(t, m))[1],
        )
        monkeypatch.setattr(
            inspection, "_c_collect_vars_impl",
            lambda t, r: (collects.append(t), real_collect(t, r))[1],
        )
        cell = ("pt", 1, Var())
        inspection._copy_term_impl(cell, {})
        inspection._collect_vars_impl(cell, [])
        assert len(copies) == 1, "the wrapper never reached the C _copy_term_impl"
        assert len(collects) == 1, "the wrapper never reached the C _collect_vars_impl"

    def test_the_seg_star_shapes_still_bypass_c(self, monkeypatch):
        """The other half of the dispatch: Seg* must NOT reach the blind C."""
        # nv
        if not _HAVE_C:
            pytest.skip("C accelerator not built")
        from clausal.logic.builtins import _helpers, inspection

        seen = []
        monkeypatch.setattr(
            inspection, "_c_copy_term_impl",
            lambda t, m: seen.append(("copy", t)),
        )
        monkeypatch.setattr(
            inspection, "_c_collect_vars_impl",
            lambda t, r: seen.append(("collect", t)),
        )
        monkeypatch.setattr(
            _helpers, "_c_is_ground",
            lambda t: seen.append(("ground", t)),
        )
        seg = SegList([ConcreteSeg([1]), VarSeg(Var())])
        inspection._copy_term_impl(seg, {})
        inspection._collect_vars_impl(seg, [])
        _helpers._is_ground(seg)
        assert seen == [], f"a Seg* shape reached the C twins: {seen}"


# ── runtime/list_unify.py twins — chars go through char_atom/is_char_atom ────
#
# atoms-as-cells/strings Task 7. Under Plan 0 (an atom IS its spelling) these
# assertions hold for both twins already; their value is as the regression net
# for the Stage B flip, when a char becomes the arity-0 cell ``("a",)``. So
# every *output* char is checked through ``is_char_atom`` / ``spelling`` rather
# than against a literal ``"a"``, while *inputs* stay literal shapes — a Stage B
# break shows up here as a twin divergence or a failed helper assertion instead
# of as a silent behaviour change deep in a corpus program.

from clausal.logic.atoms import char_atom, is_char_atom, spelling as _spelling
from clausal.logic.runtime.list_unify import (
    _head_list_unify_input_py,
    _head_list_unify_output_py,
)

try:
    from clausal.logic.runtime._list_unify import (
        _head_list_unify_input as _c_list_unify_input,
        _head_list_unify_output as _c_list_unify_output,
    )
    _HAVE_LIST_UNIFY_C = True
except ImportError:  # pragma: no cover — pure-Python build
    _HAVE_LIST_UNIFY_C = False

requires_list_unify_c = pytest.mark.skipif(
    not _HAVE_LIST_UNIFY_C, reason="_list_unify C accelerator not built"
)

_INPUT_TWINS = (
    [_head_list_unify_input_py, _c_list_unify_input]
    if _HAVE_LIST_UNIFY_C else [_head_list_unify_input_py]
)
_OUTPUT_TWINS = (
    [_head_list_unify_output_py, _c_list_unify_output]
    if _HAVE_LIST_UNIFY_C else [_head_list_unify_output_py]
)


@requires_list_unify_c
class TestListUnifyCharTwinParity:
    """``_head_list_unify_*`` C vs Python: which results promote to a str,
    and what shape the destructured chars have."""

    def test_a_str_target_destructures_into_char_atoms(self):
        """``[H, *T]`` against ``"abc"``: H is a CHAR, T is the str tail."""
        # nv
        outs = []
        for impl in _INPUT_TWINS:
            h, t = Var(), Var()
            trail = Trail()
            assert impl("abc", [h], t, [], trail) is True
            assert is_char_atom(deref(h))
            outs.append((_spelling(deref(h)), deref(t)))
        assert outs[0] == ("a", "bc")
        assert len(set(outs)) == 1, f"twins disagree: {outs}"

    def test_a_str_star_promotes_the_output_back_to_a_str(self):
        """A str-sourced star splats into chars and re-promotes (star_was_str)."""
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, star = Var(), Var()
            trail = Trail()
            unify(star, "ab", trail)
            assert impl(target, [], star, [], trail) is True
            outs.append(deref(target))
        assert outs[0] == "ab"
        assert len(set(outs)) == 1, f"twins disagree: {outs}"

    def test_a_list_of_chars_star_is_promoted(self):
        """``[a, b]`` IS the string "ab" — THE FLIP deleted the
        ``star_was_str`` gate, so both twins build the compact form."""
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, star = Var(), Var()
            trail = Trail()
            unify(star, [char_atom("a"), char_atom("b")], trail)
            assert impl(target, [], star, [], trail) is True
            got = deref(target)
            assert got == "ab"
            outs.append(got)
        assert outs == ["ab"] * len(_OUTPUT_TWINS)

    def test_two_char_strs_beside_a_str_star_are_not_promoted(self):
        """A non-char element blocks the promotion in both twins."""
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, before, star = Var(), Var(), Var()
            trail = Trail()
            unify(before, "xy", trail)          # a TWO-char str: not a char
            unify(star, "ab", trail)
            assert impl(target, [before], star, [], trail) is True
            got = deref(target)
            assert isinstance(got, list), f"{impl} promoted {got!r}"
            assert got[0] == "xy"
            assert all(is_char_atom(c) for c in got[1:])
            outs.append(repr(got))
        assert len(set(outs)) == 1, f"twins disagree: {outs}"

    def test_a_cell_shaped_char_is_a_char_to_both_twins(self):
        """Stage A dual acceptance reaches the C twins.

        ``char_atom("a")`` is a plain str under Plan 0, so the cell shape has
        to be written as a literal here.  Fix round 1: the C
        ``is_char_atom_obj`` was str-only, so ``[("a",)] + "b"`` promoted to
        ``"ab"`` in Python and stayed a list in C — a silent twin divergence
        on the very shape Stage B makes canonical.
        """
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, before, star = Var(), Var(), Var()
            trail = Trail()
            unify(before, ("a",), trail)        # a CELL-shaped char
            unify(star, "b", trail)
            assert impl(target, [before], star, [], trail) is True
            outs.append(deref(target))
        assert outs[0] == "ab", outs
        assert len(set(outs)) == 1, f"twins disagree: {outs}"

    def test_a_cell_shaped_non_char_blocks_promotion_in_both_twins(self):
        """The dual acceptance is the CHAR cell only, not any 1-tuple."""
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, before, star = Var(), Var(), Var()
            trail = Trail()
            unify(before, ("ab",), trail)       # arity-0 cell, but not a char
            unify(star, "c", trail)
            assert impl(target, [before], star, [], trail) is True
            got = deref(target)
            assert isinstance(got, list), f"{impl} promoted {got!r}"
            outs.append(repr(got))
        assert len(set(outs)) == 1, f"twins disagree: {outs}"

    def test_a_segstring_star_splats_into_char_atoms(self):
        """A ground SegString star walks to a str and splats as chars."""
        # nv
        outs = []
        for impl in _OUTPUT_TWINS:
            target, star = Var(), Var()
            trail = Trail()
            unify(star, SegString(["a", "b"]), trail)
            assert impl(target, [], star, [], trail) is True
            outs.append(deref(target))
        assert outs[0] == "ab"
        assert len(set(outs)) == 1, f"twins disagree: {outs}"
