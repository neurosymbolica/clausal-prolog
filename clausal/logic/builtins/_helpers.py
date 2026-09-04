"""Shared helper functions for builtin predicates.

The heavy-lifting functions (_functor_name, _arity, _nth_arg, _args_list,
_is_compound, _is_ground) are implemented in C in _variables.c for performance.
Python reference implementations are kept here as fallbacks.
"""

from __future__ import annotations

from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction
from numbers import Real as _Real
from typing import Any

from clausal.logic.variables import deref, is_var
from clausal.logic.predicate import is_atom, is_atom_value, is_term_instance, term_field_names
from clausal.terms import (
    Compound, KWTerm, DictTerm, SetTerm,
    SegList, SegString, SegBytes, VarSeg, ConcreteSeg,
)


# ── Python reference implementations ─────────────────────────────────────────


def _functor_name_py(term: Any) -> Any:
    """Return the functor name of a ground term, or None.

    Lists follow ISO cons-cell semantics (non-empty → ``"."``, empty →
    ``"[]"`` the nil atom). Bytes mirror that as the codes model (§1b:
    the codes model is untouched by the str~list cons-rule retirement).

    P3-1 §1b/R2: strs are RETIRED from cons-cell decomposition — a str
    is now always an atom (runtime str = atom), so it is its own functor
    name with arity 0, exactly like any other atomic constant. (The
    empty string keeps the ISO nil-atom spelling ``"[]"`` — the one str
    value that legitimately reads as a list-shaped atom, matching the
    empty-list case.)
    """
    if isinstance(term, Compound):
        return term.functor if isinstance(term.functor, str) else None
    if isinstance(term, KWTerm):
        return term.functor
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, str):
        return "[]" if len(term) == 0 else term
    if isinstance(term, bytes):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float)) or term is None:
        # A09-F027: the atomic constant IS its own functor name (ISO:
        # functor(3, N, A) → N=3), so it roundtrips. repr(term) did not.
        return term
    if is_atom(term):
        return term
    return None


def _arity_py(term: Any) -> int | None:
    """Return the arity of a ground term, or None.

    Lists follow ISO cons-cell semantics: non-empty has arity 2
    (head + tail), empty has arity 0 (the nil atom). Bytes mirror that
    as the codes model (untouched by §1b).

    P3-1 §1b/R2: strs are RETIRED from cons-cell decomposition — a str
    is always atomic (arity 0) now, whether empty or not.
    """
    if isinstance(term, Compound):
        return len(term.args)
    if isinstance(term, KWTerm):
        return len(term)
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if isinstance(term, str):
        return 0
    if isinstance(term, bytes):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float)) or term is None:
        return 0
    if is_atom(term):
        return 0
    return None


def _nth_arg_py(term: Any, n: int) -> Any:
    """Return the n-th argument (1-based) of a compound term, or raise IndexError.

    For lists, ISO cons-cell semantics apply:
      - n=1 → head (first element)
      - n=2 → tail (rest of list)
      - n>=3 → IndexError (arity is 2)
    Bytes mirror that as the codes model (untouched by §1b).

    P3-1 §1b/R2: strs are RETIRED from cons-cell decomposition — a str
    is always atomic (arity 0) now, so every index raises IndexError
    (falls through to the final ``raise IndexError`` below).
    """
    if isinstance(term, Compound):
        if n < 1 or n > len(term.args):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return term.args[n - 1]
    if isinstance(term, KWTerm):
        vals = list(term.values())
        if n < 1 or n > len(vals):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return vals[n - 1]
    if is_term_instance(term):
        fields = term_field_names(term)
        if n < 1 or n > len(fields):
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return getattr(term, fields[n - 1])
    if isinstance(term, list) and len(term) > 0:
        if n == 1:
            return term[0]
        if n == 2:
            return term[1:]
        raise IndexError(f"arg index {n} out of range for {term!r}")
    if isinstance(term, bytes) and len(term) > 0:
        if n == 1:
            return term[0]
        if n == 2:
            return term[1:]
        raise IndexError(f"arg index {n} out of range for {term!r}")
    raise IndexError(f"arg index {n} out of range for {term!r}")


def _args_list_py(term: Any) -> list:
    """Return the argument list of a compound term.

    For lists, ISO cons-cell semantics: non-empty returns
    ``[head, tail]``; empty returns ``[]`` (the nil atom has no args).
    Bytes mirror that as the codes model (untouched by §1b).

    P3-1 §1b/R2: strs are RETIRED from cons-cell decomposition — a str
    is always atomic (arity 0) now, so it always answers ``[]`` (falls
    through to the final ``return []`` below).
    """
    if isinstance(term, Compound):
        return list(term.args)
    if isinstance(term, KWTerm):
        return list(term.values())
    if is_term_instance(term):
        return [getattr(term, name) for name in term_field_names(term)]
    if isinstance(term, list):
        if len(term) == 0:
            return []
        return [term[0], term[1:]]
    if isinstance(term, bytes):
        if len(term) == 0:
            return []
        return [term[0], term[1:]]
    return []


def _is_compound_py(term: Any) -> bool:
    return (
        isinstance(term, (Compound, KWTerm))
        or is_term_instance(term)
    )


def _is_ground_py(term: Any) -> bool:
    """True if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
        return True
    if is_atom(term):
        return True
    if isinstance(term, list):
        return all(_is_ground_py(e) for e in term)
    if type(term) is tuple:
        # A CELL -- ``("pt", 1, Y)``.  P3-2 Task 2 (THE FLIP) makes this how
        # every compound data term is represented, so falling through to the
        # "unknown shape -> True" tail answered GROUND for a term holding a
        # free variable.  Two answers changed on that: ``ground/1`` said yes
        # to ``pt(1, Y)``, and ``_findall_copy_row``
        # (``compiler/globals_env.py``) gates the ISO per-solution copy on
        # this predicate, so a cell row with a free var skipped the copy and
        # shared the caller's Var -- binding it afterwards mutated the
        # collected row (A03-F006, reintroduced for cell rows).
        #
        # ``type(...) is tuple``, NOT ``isinstance`` (P3-2 Task 2C fix round 1,
        # controller ruling): a tuple SUBCLASS is not a cell -- ``is_cell``
        # excludes one by design -- and reading through one here while
        # ``copy_term`` and ``term_variables`` treat it as opaque produced an
        # incoherent trio: a namedtuple holding a free Var was reported
        # NON-ground yet had no enumerable variables and could not be copied.
        # Exact-type in all three keeps the three answers consistent and keeps
        # a namedtuple as opaque as it was pre-flip.  Kept in step with
        # ``c_is_ground``'s ``PyTuple_CheckExact``.
        return all(_is_ground_py(e) for e in term)
    if isinstance(term, Compound):
        return isinstance(term.functor, str) and all(_is_ground_py(a) for a in term.args)
    if isinstance(term, KWTerm):
        return all(_is_ground_py(v) for v in term.values())
    # F083 (audit 2026-05-25): recurse into Seg* containers so that
    # ``ground/1`` returns False for any SegList/SegString that still
    # holds an unbound ``VarSeg``. Both the Python fallback and the C
    # ``c_is_ground`` historically fell through to "True" for Seg* —
    # see [[F083]] in the 2026-05-25 string audit findings ledger.
    if isinstance(term, SegList):
        for seg in term.segments:
            if isinstance(seg, ConcreteSeg):
                if not all(_is_ground_py(e) for e in seg.elements):
                    return False
            elif isinstance(seg, VarSeg):
                if not _is_ground_py(seg.var):
                    return False
            else:
                # Unknown segment type — be conservative and walk it.
                if not _is_ground_py(seg):
                    return False
        return True
    if isinstance(term, SegString):
        for seg in term.segments:
            if isinstance(seg, str):
                continue
            if isinstance(seg, VarSeg):
                if not _is_ground_py(seg.var):
                    return False
            else:
                if not _is_ground_py(seg):
                    return False
        return True
    if isinstance(term, SegBytes):
        for seg in term.segments:
            if isinstance(seg, bytes):
                continue
            if isinstance(seg, VarSeg):
                if not _is_ground_py(seg.var):
                    return False
            else:
                if not _is_ground_py(seg):
                    return False
        return True
    if is_term_instance(term):
        return all(_is_ground_py(getattr(term, name)) for name in term_field_names(term))
    return True


# ── C-accelerated versions (with Python fallback) ────────────────────────────

_functor_name = _functor_name_py
_arity = _arity_py
_nth_arg = _nth_arg_py
_args_list = _args_list_py
_is_compound = _is_compound_py
_is_ground = _is_ground_py

try:
    from clausal.logic.variables._variables import (
        _functor_name,
        _arity,
        _nth_arg,
        _args_list,
        _is_compound,
        _is_ground as _c_is_ground,
        _register_term_types,
    )
    # Register Compound and KWTerm types with the C extension
    _register_term_types(Compound, KWTerm)

    # F083 (audit 2026-05-25): the C ``_is_ground`` does not know about
    # SegList / SegString / SegBytes and falls through to "True" for any
    # unknown container. Short-circuit the Seg* shapes in Python so a
    # SegList / SegString / SegBytes that still holds an unbound ``VarSeg``
    # reports *not* ground. Other shapes still go through the fast C path.
    # P3-2 Task 2 (THE FLIP) briefly made this Python-only: ``c_is_ground``
    # had no tuple branch, so a CELL -- a bare tuple, and post-flip how every
    # compound data term is represented -- fell through its tail to "ground"
    # and ``ground(pt(1, Y))`` answered TRUE.  Task 2C gave ``c_is_ground``
    # the branch (``PyTuple_CheckExact``, matching this module's
    # ``type(term) is tuple`` gate and the two in ``inspection.py``) and this
    # dispatch is back to the Seg*-only short-circuit.  Twin parity is pinned
    # by ``tests/test_python_fallbacks.py::TestCellIsGroundTwinParity``.
    def _is_ground(term: Any) -> bool:
        t = deref(term)
        if isinstance(t, (SegList, SegString, SegBytes)):
            return _is_ground_py(t)
        return _c_is_ground(t)
except ImportError:
    pass


# ── Cell awareness (Phase 2 bridge Task 1, additive) ─────────────────────────
#
# Tagged cells (``clausal.logic.cells``) are plain tuples that already
# unify/walk through the engine's EXISTING C tuple branches (see the
# design doc ``implementation_plans/tagged-tuple-term-representation.md``
# and the Phase 2 bridge plan's Global Constraints) — nothing above this
# point needs to change for that.
#
# What DOES need to change is this funnel: neither the C
# ``_functor_name``/``_arity``/``_nth_arg``/``_args_list``/``_is_compound``
# nor their Python fallbacks above have EVER had a plain-tuple branch (no
# ``PyTuple_Check`` in ``py_functor_name`` et al. in ``_variables.c``, no
# ``isinstance(term, tuple)`` in the ``_..._py`` functions above) — a bare
# tuple has always fallen through every one of them unchanged (functor
# name/arity None, args_list [], is_compound False, nth_arg raises
# IndexError). ``tests/test_funnel_accessors.py::TestPlainTupleAccessorRegression``
# pins that fact directly against a plain, non-cell-shaped tuple (slot 0
# not a str/``tuple``-type/Var), so wrapping each already-selected
# implementation (C when available, else the ``_..._py`` fallback) with an
# ``is_cell``-gated branch in FRONT of it is purely additive: nothing that
# isn't cell-shaped can reach the new code at all.
#
# Per the task brief: only cells with a STR or unbound-Var functor are
# treated as compound/decomposable, same as a Compound term. A
# ``(tuple, ...)`` cell (``cells.TUPLE_TAG`` in slot 0) is tuple DATA, not
# a compound — it is deliberately left to fall through to the same "not a
# recognized shape" answer a plain tuple gets.
#
# KNOWN AMBIGUITY (accepted, not solved — see ``clausal/logic/cells.py``'s
# module docstring for the full ruling): a plain user tuple whose slot 0
# happens to be a str (e.g. ``("hello", 1)``) is indistinguishable from a
# str-functor cell by shape, and the branch below — gated on cell-shape
# alone, as the plan requires — DOES change its accessor behavior (e.g.
# ``_functor_name`` used to answer None for it, now answers ``"hello"``).
# That is the documented bridge-stage tradeoff; pinned by a running test
# (``tests/test_funnel_accessors.py::TestCellFunnelAwareness::
# test_known_ambiguity_plain_str_tuple_pinned_by_running_assertions``).
#
# Review fix (finding #1): slot 0 must be inspected DEREFERENCED, not raw
# — a cell built with an unbound-Var functor that ``unify`` has since
# bound must not vanish from recognition just because its functor slot
# resolved. ``cells._cell_shape(term)`` derefs slot 0 exactly once and
# hands back both "is this cell-shaped at all" and the resolved value;
# ``_cell_functor`` below layers on "and is it COMPOUND" (str/Var, not
# ``TUPLE_TAG``) without a second deref, and every accessor calls
# ``_cell_functor`` exactly once — one deref of slot 0 per top-level
# accessor call, never two.

from clausal.logic.cells import TUPLE_TAG as _CELL_TUPLE_TAG, _cell_shape


def _cell_functor(term: Any) -> tuple[bool, Any]:
    """Return ``(is_compound_cell, resolved_functor)`` for *term*.

    ``is_compound_cell`` is True only for a str or unbound-Var functor —
    a ``(tuple, ...)`` tuple-DATA cell (resolved slot 0 is
    ``cells.TUPLE_TAG``) is explicitly NOT compound, per the task brief.
    Dereferences slot 0 at most once (via ``cells._cell_shape``).
    """
    ok, f = _cell_shape(term)
    if ok and f is not _CELL_TUPLE_TAG:
        return True, f
    return False, None


_functor_name_precell = _functor_name
_arity_precell = _arity
_nth_arg_precell = _nth_arg
_args_list_precell = _args_list
_is_compound_precell = _is_compound


def _functor_name(term: Any) -> Any:
    is_compound_cell, f = _cell_functor(term)
    if is_compound_cell:
        return f
    return _functor_name_precell(term)


def _arity(term: Any) -> int | None:
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return len(term) - 1
    return _arity_precell(term)


def _nth_arg(term: Any, n: int) -> Any:
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        if n < 1 or n > len(term) - 1:
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return term[n]
    return _nth_arg_precell(term, n)


def _args_list(term: Any) -> list:
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return list(term[1:])
    return _args_list_precell(term)


def _is_compound(term: Any) -> bool:
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return True
    return _is_compound_precell(term)


# ── Combined functor+arity probe ─────────────────────────────────────────────


def functor_arity(term: Any) -> tuple[Any, int] | None:
    """Return ``(functor_name, arity)`` for *term* in a single traversal, or None.

    Deliberately narrower than ``_functor_name``/``_arity`` composed: it only
    covers structural/term shapes (a well-formed, str-functor ``Compound``, a
    term instance, a plain ``str`` atom value, or a ``PredicateMeta`` atom
    class), returning None for everything else — including ``KWTerm``, lists
    and numbers, which the composed pair *does* resolve. Where both are
    defined for a shape they cover in common, they must agree (see
    ``tests/test_funnel_accessors.py::TestFunctorArity``); this function
    exists so callers who already know they hold a term shape (the common
    case in the compiler/inspection funnels) don't pay for two walks.

    P3-1 Task 1 (R2, str-as-atom acceptance): a plain ``str`` is now an
    atom VALUE here — ``functor_arity("red") == ("red", 0)``. This USED
    to deliberately diverge from ``_functor_name``/``_arity`` (which gave
    a non-empty str the ISO cons-cell reading: functor ``"."``, arity 2)
    — Task 5 (§1b) retired that cons-cell reading, so ``_functor_name``/
    ``_arity`` now agree with ``functor_arity`` for every NON-EMPTY str:
    a str is atomic (its own functor value, arity 0). One residual,
    pre-existing (Task 1) divergence remains for the EMPTY str: this
    function's ``is_atom_value`` branch answers ``("", 0)`` (the empty
    str is its own functor value, same as any other atom), whereas
    ``_functor_name``/``_arity`` special-case it to the ISO nil-atom
    spelling ``("[]", 0)`` (shared with the empty-LIST case, which this
    function's declared domain excludes) — see
    ``tests/test_funnel_accessors.py::TestFunctorArity::test_str_is_atom_value``.
    See ``is_atom_value`` in ``clausal/logic/predicate.py``.

    The functor slot is ``str`` for a ``Compound``/term instance, but for a
    plain str atom value or a zero-arity atom class it is the value/class
    itself (``_functor_name_py``'s own contract: an atomic constant IS its
    own functor name), so the type is ``Any``, not ``str``.

    Caller warning: any ``is_term_instance`` guard admits ``Compound`` (it is
    a dataclass), and ``functor_arity`` will answer for the *Compound*, not
    for its Python class -- do not use it to get a class/type name (e.g. for
    diagnostic display of a ``Compound`` head). Callers that want the type
    name unconditionally must not route a value that might be a ``Compound``
    through ``functor_arity`` first.

    Phase 2 bridge Task 1: a str-functor cell resolves to ``(functor,
    arity)`` same as a Compound. A ``(tuple, ...)`` tuple-DATA cell or an
    unbound-Var-functor cell resolves to None — deliberately narrower here
    than the composed ``_functor_name``/``_arity`` pair (which DOES resolve
    a Var-functor cell's arity), mirroring the existing
    Compound-with-Var-functor precedent above. Uses ``_cell_functor``
    (single deref of slot 0, review fix finding #1) rather than inspecting
    ``term[0]`` raw.
    """
    is_compound_cell, f = _cell_functor(term)
    if is_compound_cell:
        if isinstance(f, str):
            return (f, len(term) - 1)
        return None
    if isinstance(term, Compound):
        if not isinstance(term.functor, str):
            return None
        return (term.functor, len(term.args))
    if is_term_instance(term):
        return (type(term).__name__, len(term_field_names(term)))
    if is_atom_value(term):
        # Mirrors _functor_name_py: the atom (str value or zero-arity
        # class) IS its own functor value (ISO: functor(3, N, A) -> N=3
        # for numbers; an atom is the same story), not its __name__
        # string. R2 (P3-1 Task 1): a plain str counts here too.
        return (term, 0)
    return None


# ── Standard order of terms ──────────────────────────────────────────────────
#
# ``sort/2``, ``msort/2``, ``setof/3`` and the ``*_by`` higher-order builtins
# sort with Python's ``sorted()`` when the elements happen to be mutually
# comparable, and fall back to a sort *key* when they are not.  Terms —
# ``Compound``, ``KWTerm``, declared term instances — define no ``__lt__``, so
# any list of them takes the fallback.
#
# That fallback used to be ``(type name, repr(x))``, which ordered a compound's
# arguments by their *decimal rendering*: ``score(15) < score(2) < score(9)``,
# because ``"15" < "2" < "9"``.  ``msort`` did not raise — it returned a
# well-formed list in a confidently wrong order, and a test asserting "the
# result is sorted" passed.  See
# ``todo/msort-orders-compound-integer-args-as-strings.md``.
#
# ``_standard_order_key`` replaces it with a structural key that recurses into
# arguments, so a compound's arguments get exactly the comparison the same
# values get when bare.  Ranks follow the ISO standard order of terms
# (Var < Number < Atom < String < Compound); everything with no term shape of
# its own keeps the old type-name grouping via ``_OpaqueOrder``.
#
# Every key is a tuple whose first element is one of these rank ints, so keys
# of different ranks decide on that int alone and the remaining elements are
# only ever compared against elements of the same shape.  The key is therefore
# TOTAL: sorting can never raise, which is what lets it stand in for a
# comparison the terms do not implement.

_ORD_VAR = 0
_ORD_NUM = 1
_ORD_ATOM = 2
_ORD_BYTES = 3
_ORD_SEQ = 4
_ORD_COMPOUND = 5
_ORD_DICT = 6
_ORD_SET = 7
_ORD_OTHER = 8

# Flavours within _ORD_COMPOUND.  A generic ``Compound`` and a declared term
# that render alike are *not* the same term (they do not unify — see
# ``todo/a-generic-compound-renders-identically-to-a-declared-term.md``), so
# they get adjacent but distinct places in the order rather than interleaving.
# The flavour also keeps the argument payloads shape-uniform: positional
# flavours carry a tuple of keys, ``KWTerm`` carries name/key pairs, and the
# two are never compared against each other.
_CF_POSITIONAL = 0   # Compound
_CF_KEYWORD = 1      # KWTerm (keyword-matched: fields sorted by name)
_CF_DECLARED = 2     # declared term instance / dataclass


class _OpaqueOrder:
    """Order key for a value with no term shape of its own.

    Same Python type: compare with ``<``, so ``date``/``datetime``/``Quantity``
    and friends keep their *natural* order even here (``repr`` would order
    ``date(2020, 1, 15)`` before ``date(2020, 1, 2)``).  Different types: order
    by type name, the grouping this fallback has always used.  Never raises —
    a value whose ``<`` rejects its own type (a ``Quantity`` compared across
    dimensions) drops to ``repr``, which is arbitrary but total.
    """

    __slots__ = ("value", "type_name")

    def __init__(self, value: Any) -> None:
        self.value = value
        self.type_name = type(value).__name__

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, _OpaqueOrder):
            return NotImplemented
        if self.type_name != other.type_name:
            return False
        if self.value is other.value:
            return True
        try:
            return bool(self.value == other.value)
        except Exception:
            return repr(self.value) == repr(other.value)

    def __lt__(self, other: "_OpaqueOrder") -> bool:
        if not isinstance(other, _OpaqueOrder):
            return NotImplemented
        if self.type_name != other.type_name:
            return self.type_name < other.type_name
        try:
            return bool(self.value < other.value)
        except Exception:
            return repr(self.value) < repr(other.value)


def _standard_order_key(term: Any) -> tuple:
    """Sort key implementing the standard order of terms.

    Total over every value a term can hold, so ``sorted(xs, key=...)`` never
    raises.  Recurses through compounds, lists, dicts and sets, dereferencing
    as it goes, so nested numbers compare *numerically* rather than as strings.
    """
    term = deref(term)
    if is_var(term):
        # Unbound vars sort first, in a stable but arbitrary order — ISO
        # leaves the order among distinct variables implementation-defined.
        return (_ORD_VAR, id(term))
    # The concrete types first (fast), then the ABC for anything registered
    # into the numeric tower.  ``Decimal`` is a ``Number`` but not a ``Real``.
    if isinstance(term, (bool, int, float, _Fraction, _Decimal, _Real)):
        return (_ORD_NUM, term)
    if isinstance(term, str):
        return (_ORD_ATOM, term)
    if is_atom(term):
        # P3-1 Task 4 (standard-order collapse), status corrected by the
        # Task 7 sweep: NOT a transient pre-pivot straggler after all. The
        # compiler stopped minting atom-shaped classes in Task 2, and the
        # last live production atom-class-construction path
        # (``global_atom/2``'s mint-on-demand mode) was fixed in Task 7 to
        # install the interned str instead — but a bare 0-arity PREDICATE
        # declared with explicit call syntax (``-module(m, [p()])``, as
        # opposed to the bare-Name atom syntax ``-module(m, [p])``) still
        # legitimately mints a real ``PredicateMeta`` class with no fields,
        # and a reference to that predicate BY NAME (not called) reaches
        # here as a live term value. Per §1b/R2 that class and a
        # same-spelled str are still the SAME atom for ordering purposes,
        # so this key must not be distinguishable from the str key above:
        # no trailing discriminator, ``(_ORD_ATOM, "work")`` for both
        # ``"work"`` and a 0-arity predicate class named ``work``.
        return (_ORD_ATOM, term.__name__)
    if isinstance(term, bytes):
        return (_ORD_BYTES, term)
    if isinstance(term, (list, tuple)):
        return (_ORD_SEQ, tuple(_standard_order_key(e) for e in term))
    if isinstance(term, Compound):
        functor = deref(term.functor)
        # A Var functor has no name to order by; park all of them after the
        # named ones and let the arguments decide between them.
        name_key = (0, functor) if isinstance(functor, str) else (1, "")
        return (_ORD_COMPOUND, len(term.args), name_key, _CF_POSITIONAL,
                tuple(_standard_order_key(a) for a in term.args))
    if isinstance(term, KWTerm):
        # KWTerm equality is by keyword *name*, not position, so the key must
        # be too — otherwise two equal terms could sort to different places.
        by_name = dict(term.items())
        fields = tuple(
            (name, _standard_order_key(by_name[name])) for name in sorted(by_name)
        )
        return (_ORD_COMPOUND, len(fields), (0, term.functor), _CF_KEYWORD, fields)
    if is_term_instance(term):
        names = term_field_names(term)
        return (_ORD_COMPOUND, len(names), (0, type(term).__name__), _CF_DECLARED,
                tuple(_standard_order_key(getattr(term, n)) for n in names))
    if isinstance(term, (dict, DictTerm)):
        # DictTerm and a plain dict compare equal, so they share one key shape.
        pairs = [(_standard_order_key(k), _standard_order_key(v))
                 for k, v in term.items()]
        return (_ORD_DICT, tuple(sorted(pairs)))
    if isinstance(term, (set, frozenset, SetTerm)):
        return (_ORD_SET, tuple(sorted(_standard_order_key(e) for e in term)))
    return (_ORD_OTHER, _OpaqueOrder(term))


def _standard_order_sorted(items: list) -> list:
    """Sort *items* into the standard order of terms.

    Mutually comparable elements keep Python's own ordering — that path was
    always right and stays the fast one.  Anything else (any compound, or a
    mix of types) goes through :func:`_standard_order_key`.
    """
    try:
        return sorted(items)
    except TypeError:
        return sorted(items, key=_standard_order_key)
