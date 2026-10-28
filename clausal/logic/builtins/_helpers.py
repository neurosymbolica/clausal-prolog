"""Shared helper functions for builtin predicates.

The heavy-lifting functions (_functor_name, _arity, _nth_arg, _args_list,
_is_compound, _is_ground) are implemented in C in _variables.c for performance.
Python reference implementations are kept here as fallbacks.
"""

from __future__ import annotations

from decimal import Decimal as _Decimal
from fractions import Fraction as _Fraction

from clausal.logic.number_kinds import numeric_kind as _numeric_kind
from numbers import Real as _Real
from typing import Any
import functools as _functools

from clausal.logic.variables import deref, is_var, exact_cell_number
from clausal.logic.predicate import (
    is_atom_value, is_term_instance, term_field_names,
)
from clausal.logic.cells import TUPLE_TAG, chars, is_chars, chars_text, refuse_reserved_1tuple
from clausal.logic.atoms import (
    char_atom, is_nil as _is_nil, NIL_SPELLING as _NIL_SPELLING,
    is_truth_atom, truth_spelling,
)
from clausal.terms import (
    Undefined as _Undefined,
    DictTerm, SetTerm, Quantity,
    SegList, SegString, SegBytes, VarSeg, ConcreteSeg,
)


# ── Python reference implementations ─────────────────────────────────────────


def _functor_name_py(term: Any) -> Any:
    """Return the functor name of a ground term, or None.

    Lists follow ISO cons-cell semantics (non-empty → ``"."``, empty →
    ``"[]"`` the nil atom). Bytes mirror that as the codes model (§1b:
    the codes model is untouched by the str~list cons-rule retirement).

    Strings follow the SAME cons-cell semantics as of THE FLIP
    (atoms-as-cells/strings §6.4): a ``str`` is a STRING — the list of its
    char atoms — so it answers what that list answers.  P3-1 §1b/R2 had
    RETIRED strs from cons-cell decomposition (a str was always an atom,
    hence its own functor name with arity 0); Task 12b retired that reading
    from this fallback and from its C twin ``_functor_name`` in
    ``variables/_variables.c`` in one move, so the two agree even when the
    accessor is called directly rather than through the funnel wrapper of
    the same name further down this file.  The empty string keeps the ISO
    nil-atom spelling ``"[]"``, as the empty list does.
    """
    if is_term_instance(term):
        return type(term).__name__
    if isinstance(term, list):
        return "[]" if len(term) == 0 else "."
    if is_chars(term):
        return "[]" if len(chars_text(term)) == 0 else "."
    if isinstance(term, str):
        return term                    # STAGE 2: an atom is its own functor name
    if isinstance(term, bytes):
        return "[]" if len(term) == 0 else "."
    if isinstance(term, (bool, int, float)) or term is None:
        # A09-F027: the atomic constant IS its own functor name (ISO:
        # functor(3, N, A) → N=3), so it roundtrips. repr(term) did not.
        return term
    return None


def _arity_py(term: Any) -> int | None:
    """Return the arity of a ground term, or None.

    Lists follow ISO cons-cell semantics: non-empty has arity 2
    (head + tail), empty has arity 0 (the nil atom). Bytes mirror that
    as the codes model (untouched by §1b).

    Strings follow the SAME cons-cell semantics as of THE FLIP
    (atoms-as-cells/strings §6.4): a ``str`` is a STRING — the list of its
    char atoms — so a non-empty one has arity 2 and the empty one arity 0.
    P3-1 §1b/R2 had RETIRED strs from cons-cell decomposition (a str was
    always atomic, arity 0, empty or not); Task 12b retired that reading
    from this fallback and from its C twin ``_arity`` in
    ``variables/_variables.c`` in one move, so the two agree even when the
    accessor is called directly rather than through the funnel wrapper of
    the same name further down this file.
    """
    if is_term_instance(term):
        return len(term_field_names(term))
    if isinstance(term, list):
        return 0 if len(term) == 0 else 2
    if is_chars(term):
        return 0 if len(chars_text(term)) == 0 else 2
    if isinstance(term, str):
        return 0                       # STAGE 2: an atom
    if isinstance(term, bytes):
        return 0 if len(term) == 0 else 2
    if isinstance(term, (bool, int, float)) or term is None:
        return 0
    return None


def _nth_arg_py(term: Any, n: int) -> Any:
    """Return the n-th argument (1-based) of a compound term, or raise IndexError.

    For lists, ISO cons-cell semantics apply:
      - n=1 → head (first element)
      - n=2 → tail (rest of list)
      - n>=3 → IndexError (arity is 2)
    Bytes mirror that as the codes model (untouched by §1b).

    P3-1 §1b/R2 (SUPERSEDED, kept as the fallback's own reading): strs
    were RETIRED from cons-cell decomposition — a str was always atomic
    (arity 0), so every index raised IndexError.

    THE FLIP (atoms-as-cells/strings §6.4) SHADOWS the ``str`` reading
    below: a ``str`` is a STRING now and answers what its char list
    answers, and the wrapper of the same name further down this file
    takes every ``str`` before it can reach here.  The P3-1 reading is
    kept verbatim because this function is the Python FALLBACK for the C
    accessor of the same name, whose own ``str`` arm is likewise
    shadowed; the twins are retired together or not at all.
    """
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

    P3-1 §1b/R2 (SUPERSEDED, kept as the fallback's own reading): strs
    were RETIRED from cons-cell decomposition — a str was always atomic
    (arity 0), so it always answered ``[]``.

    THE FLIP (atoms-as-cells/strings §6.4) SHADOWS the ``str`` reading
    below: a ``str`` is a STRING now and answers what its char list
    answers, and the wrapper of the same name further down this file
    takes every ``str`` before it can reach here.  The P3-1 reading is
    kept verbatim because this function is the Python FALLBACK for the C
    accessor of the same name, whose own ``str`` arm is likewise
    shadowed; the twins are retired together or not at all.
    """
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
    return is_term_instance(term)


def _is_ground_py(term: Any) -> bool:
    """True if term contains no unbound Vars."""
    term = deref(term)
    if is_var(term):
        return False
    if isinstance(term, (bool, int, float, str, bytes)) or term is None:
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
    # A dict term's VALUES are terms (its keys are ground by construction);
    # kept in step with ``walk_container_kind`` in ``c_is_ground``.
    if type(term) is DictTerm:
        return all(_is_ground_py(v) for v in term.data.values())
    if type(term) is dict:
        return all(_is_ground_py(v) for v in term.values())
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
    )

    # ``c_is_ground`` reads through every shape ``_is_ground_py`` does --
    # cells (``PyTuple_CheckExact``), Seg* partial lists/strings/byte
    # strings and dict terms at ANY depth (``walk_container_kind`` in
    # ``_variables.c``) -- so it is used directly.  The Python wrapper that
    # used to short-circuit a Seg* here (F083) caught one only at the TOP
    # level: ``ground(f([A|T]))`` answered TRUE.  Twin parity is pinned by
    # ``tests/test_python_fallbacks.py``.
    _is_ground = _c_is_ground
except ImportError:
    def _is_ground(term: Any) -> bool:
        """The twin without C: the same iterative fallback the C wrapper
        takes past its depth cap (``clausal.logic.rational_walk``)."""
        try:
            return _is_ground_py(term)
        except RecursionError:
            from clausal.logic.rational_walk import is_ground_iterative  # noqa: PLC0415
            return is_ground_iterative(term)


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
# Per §1b (P3-2 Task 5): only a cell with a STR functor is treated as
# compound/decomposable. A ``(tuple, ...)`` cell
# (``cells.TUPLE_TAG`` in slot 0) is tuple DATA, not a compound — it is
# deliberately left to fall through to the same "not a recognized shape"
# answer a plain tuple gets. The bridge's unbound-Var-functor cell (a
# higher-order, not-yet-resolved functor slot) is DEPRECATED per §1b — it
# caused the bridge's one Critical, imposed a deref on every recognition,
# and permitted category instability; see ``clausal/logic/cells.py``'s
# module docstring for the full ruling. A slot-0-Var tuple is therefore
# not cell-shaped at all any more and falls through to plain-tuple
# handling here, same as any other non-str, non-``tuple`` tag.
#
# THE DISCIPLINE (formerly documented here as an accepted "known
# ambiguity" — see ``clausal/logic/cells.py``'s module docstring for the
# full ruling): a plain user tuple whose slot 0 happens to be a str (e.g.
# ``("hello", 1)``) is a str-functor cell by shape, full stop, and the
# branch below treats it as one (e.g. ``_functor_name`` answers
# ``"hello"`` for it). Pinned by a running test
# (``tests/test_funnel_accessors.py::TestCellFunnelAwareness::
# test_the_discipline_plain_str_tuple_pinned_by_running_assertions``).
#
# §1b/Task 5: slot 0 is inspected RAW, never dereferenced — a legally
# constructed cell's slot 0 is always already a str or ``TUPLE_TAG``
# (``make_cell`` enforces this), so there is nothing to walk to.
# ``_cell_functor`` below is the funnel's single top-level cell-shape
# check — every accessor calls it exactly once per term, at most one
# ``type()``/attribute read of slot 0 per accessor call.

def _cell_functor(term: Any) -> tuple[bool, Any]:
    """Return ``(is_compound_cell, functor)`` for *term*, read RAW.

    ``is_compound_cell`` is True only for a str functor naming a PREDICATE —
    a ``('()', ...)`` tuple-DATA cell and a slot-0-Var tuple (deprecated,
    §1b) are both explicitly NOT compound. No deref.

    The tuple-DATA exclusion used to be free here: the tag was the ``tuple``
    TYPE object, so ``type(term[0]) is str`` already rejected it. Now that the
    tag is the reserved atom ``'()'`` the check has to be written down, and
    leaving it out would make every data tuple answer as the compound
    ``'()'/N`` — a goal, a clause head, an ``assertz`` argument.
    """
    from clausal.logic.cells import TUPLE_TAG, CHARS_TAG  # noqa: PLC0415
    if (type(term) is tuple and term and type(term[0]) is str
            and term[0] != TUPLE_TAG and term[0] != CHARS_TAG):   # the chars carrier is a STRING, not a cell
        return True, term[0]
    return False, None


_functor_name_precell = _functor_name
_arity_precell = _arity
_nth_arg_precell = _nth_arg
_args_list_precell = _args_list
_is_compound_precell = _is_compound


# THE FLIP (2026-09-06-atoms-as-cells-strings §6.4): a ``str`` is a STRING —
# the LIST of its char atoms — so every accessor below answers for a str
# exactly what it answers for that list: ``functor("hello", N, A)`` gives
# ``N = '.'``, ``A = 2``; ``arg(1, "hello", C)`` gives the char atom
# ``("h",)``; ``arg(2, "hello", T)`` gives the ``str`` SLICE ``"ello"``
# (R-S2: decomposition answers virtually, nothing is expanded), and the
# empty string answers as ``[]`` does.  These arms sit in FRONT of the
# pre-cell implementations (C or Python).  Task 12b retired P3-1's "a str is
# its own functor, arity 0" reading from ``_functor_name``/``_arity`` in BOTH
# halves (``_functor_name_py``/``_arity_py`` here and ``py_functor_name``/
# ``py_arity`` in ``variables/_variables.c``), so for those two the wrapper
# and the accessor it fronts now give the same answer.  ``_nth_arg`` and
# ``_args_list`` are still fronted rather than agreed with: their pre-cell
# halves have no ``str`` branch at all (a ``str`` falls through to
# ``IndexError`` / ``[]``), and giving them one means BUILDING a char-atom
# cell in C as well as Python — an addition, not a retirement, and not yet
# done.
#
# The str arms are spelled ``type(term) is str`` rather than routed through
# ``normalize_seg_input``, and that is deliberate rather than an exception to
# spec §14 item 8: a ``SegString`` never reaches these wrappers un-walked
# (``inspection.py`` normalizes at the builtin boundary), and a future
# mapped-string representation slots in at that same boundary, walking to
# whatever these arms already answer for.

def _functor_name(term: Any) -> Any:
    text = is_chars(term)
    if text:
        term = chars_text(term)       # the carrier decomposes as its text; a bare str is an ATOM (stage 2)
    is_compound_cell, f = _cell_functor(term)
    if is_compound_cell:
        return f
    if type(term) is str:
        return ("[]" if not term else ".") if text else term
    if is_truth_atom(term):
        return term                   # the atom true/false/undefined: its own name (D35)
    return _functor_name_precell(term)


def _arity(term: Any) -> int | None:
    text = is_chars(term)
    if text:
        term = chars_text(term)       # the carrier decomposes as its text; a bare str is an ATOM (stage 2)
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return len(term) - 1
    if type(term) is str:
        return (0 if not term else 2) if text else 0
    if is_truth_atom(term):
        return 0                      # an atom (D35)
    return _arity_precell(term)


def _nth_arg(term: Any, n: int) -> Any:
    text = is_chars(term)
    if text:
        term = chars_text(term)       # the carrier decomposes as its text; a bare str is an ATOM (stage 2)
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        if n < 1 or n > len(term) - 1:
            raise IndexError(f"arg index {n} out of range for {term!r}")
        return term[n]
    if type(term) is str:
        if term and text:
            if n == 1:
                return char_atom(term[0])
            if n == 2:
                return chars(term[1:])     # stage 1: a text TAIL is the carrier
        raise IndexError(f"arg index {n} out of range for {term!r}")
    return _nth_arg_precell(term, n)


def _args_list(term: Any) -> list:
    text = is_chars(term)
    if text:
        term = chars_text(term)       # the carrier decomposes as its text; a bare str is an ATOM (stage 2)
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return list(term[1:])
    if type(term) is str:
        return [char_atom(term[0]), chars(term[1:])] if (term and text) else []
    return _args_list_precell(term)


def _is_compound(term: Any) -> bool:
    text = is_chars(term)
    if text:
        term = chars_text(term)       # the carrier decomposes as its text; a bare str is an ATOM (stage 2)
    is_compound_cell, _f = _cell_functor(term)
    if is_compound_cell:
        return True
    if type(term) is str:
        # A string answers what the LIST it denotes answers, and a list is
        # not compound in this funnel (``_is_compound_py([1])`` is False) —
        # ``compound/1`` gates on this, and ISO's answer for a list is a
        # separate question the parked ``[]``-as-an-atom item covers.
        return False
    return _is_compound_precell(term)


# ── The list/nil shape (Task 15 item 2, ISO alignment) ───────────────────────
#
# ISO reads a list as ``'.'/2`` cons cells ending in the reserved ATOM
# ``'[]'``, and Scryer 0.10.0 answers accordingly: ``atom([])``,
# ``atomic([])``, ``callable([])`` true; ``compound([])`` false;
# ``compound([1,2])``, ``compound("abc")``, ``callable("foo")`` true.  A
# string and a code list ARE lists in this engine (spec §5.4), so all three
# spellings answer alike.  ``_is_compound`` above stays the CELL funnel — it
# deliberately answers False for a list — so the type checks ask these two
# first and fall through to it.

#: The spelling of the atom the empty list IS.  ``atom_length([], 2)`` and
#: ``atom_chars([], ['[', ']'])`` read it (Scryer-verified).  Re-exported
#: from ``clausal.logic.atoms``, which owns it — ``mint(NIL_SPELLING)``
#: answers ``[]`` (fix round 1, item 2), so the two must not drift.
NIL_SPELLING = _NIL_SPELLING


def _is_empty_list(term: Any) -> bool:
    """True iff *term* is the EMPTY LIST — ``[]``, ``chars("")``, ``b""`` or ``()``
    (STAGE 2: a bare ``""`` is the atom ``''``, not nil).

    The empty ``tuple`` is here and NOT in :func:`_is_non_empty_list`
    deliberately: a non-empty tuple is a CELL (or tuple-data), which has its
    own shape rules, while the empty one has no slot 0 and so is the list it
    holds -- nothing.

    The empty list is the reserved atom ``'[]'``.  The empty ``tuple`` is
    here because a plain (non-cell, non-``TUPLE_TAG``) tuple is treated as
    the list it holds throughout this module.  A ``Seg*`` is walked by the
    caller before this is asked.

    Delegates to ``atoms.is_nil`` rather than repeating the shape test (fix
    round 4): the two had drifted apart on subclasses — ``as_dict_key``'s
    copy of it did not fold a frozen ``-constants`` empty list.
    """
    return _is_nil(term)


def _is_non_empty_list(term: Any) -> bool:
    """True iff *term* is a NON-empty list, and so the ``'.'/2`` compound."""
    if is_chars(term):
        return len(chars_text(term)) > 0
    return type(term) in (list, bytes) and len(term) > 0


# ── Combined functor+arity probe ─────────────────────────────────────────────


def functor_arity(term: Any) -> tuple[Any, int] | None:
    """Return ``(functor_name, arity)`` for *term* in a single traversal, or None.

    Deliberately narrower than ``_functor_name``/``_arity`` composed: it only
    covers structural/term shapes (a str-functor cell, a
    term instance, a plain ``str`` atom value, or a ``PredicateMeta`` atom
    class), returning None for everything else — including lists
    and numbers, which the composed pair *does* resolve. Where both are
    defined for a shape they cover in common, they must agree (see
    ``tests/test_funnel_accessors.py::TestFunctorArity``); this function
    exists so callers who already know they hold a term shape (the common
    case in the compiler/inspection funnels) don't pay for two walks.

    THE FLIP (2026-09-06-atoms-as-cells-strings, spec §5.1): an atom is the
    arity-0 cell, so ``functor_arity(mint("red")) == ("red", 0)`` — slot 0
    and arity 0, the same answer ``_functor_name``/``_arity`` give it. A
    plain ``str`` is a STRING, i.e. the LIST of its char atoms, and lists
    are outside this function's declared domain: ``functor_arity("red")``
    is ``None``, exactly as ``functor_arity([("r",), ("e",), ("d",)])`` is.
    (``_functor_name``/``_arity`` DO resolve a list, and answer a non-empty
    string the ISO cons-cell reading ``"."``/2 and ``""`` the nil atom
    ``"[]"``/0 — that is the composed pair's wider domain, not a
    disagreement.)  This INVERTS the P3-1 Task 1 str-as-atom-value reading.
    See ``is_atom_value`` in ``clausal/logic/predicate.py``.

    The functor slot is ``str`` for a cell/term instance, but for a
    plain str atom value or a zero-arity atom class it is the value/class
    itself (``_functor_name_py``'s own contract: an atomic constant IS its
    own functor name), so the type is ``Any``, not ``str``.

    Phase 2 bridge Task 1: a str-functor cell resolves to ``(functor,
    arity)``. A ``(tuple, ...)`` tuple-DATA cell
    resolves to None. P3-2 Task 5 (§1b): the bridge's unbound-Var-functor
    cell is deprecated and no longer cell-shaped at all — a slot-0-Var
    tuple now falls through this whole function the same as any other
    plain tuple, resolving to None. ``_cell_functor`` is True only for a
    str functor, so ``f`` is always a str once ``is_compound_cell`` is
    True; no further check is needed.
    """
    is_compound_cell, f = _cell_functor(term)
    if is_compound_cell:
        return (f, len(term) - 1)
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
# cells of mixed shapes, declared term instances — define no ``__lt__``, so
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
# (Var < Number < Atom < compound, ISO 7.2.1 — a string and a list are both
# the ``'.'/2`` compound, so there is no band between atom and compound);
# everything with no term shape of its own keeps the old type-name grouping
# via ``_OpaqueOrder``.
#
# Every key is a tuple whose first element is one of these rank ints, so keys
# of different ranks decide on that int alone and the remaining elements are
# only ever compared against elements of the same shape.  The key is therefore
# TOTAL: sorting can never raise, which is what lets it stand in for a
# comparison the terms do not implement.

_ORD_VAR = 0
_ORD_NUM = 1
_ORD_ATOM = 2
_ORD_COMPOUND = 3
_ORD_DICT = 4
_ORD_SET = 5
_ORD_OTHER = 6

# Within the number band, at EQUAL value and dimension, the term's numeric
# TYPE decides. float before int is ISO 7.2.1; the rest are Clausal extensions
# and follow it, each its own kind. The ranks must agree with
# `iso_compare._numeric_tag` — two terms share a rank exactly when `'=='`
# calls them identical — because that is what makes
# `compare(=, X, Y) <=> X == Y` hold by construction rather than by luck.
# Spec §4b. An extension never interleaves between two ISO terms (§2), which
# is why Quantity ranks after every ISO numeric type rather than beside them.
_NUMERIC_RANK = {float: 0, int: 1, _Decimal: 3, _Fraction: 4}   # bool is an ATOM (D35); rank 2 retired; keyed by number_kinds.numeric_kind (the BASE kind)
_NUMERIC_RANK_QUANTITY = 5

# Flavours within _ORD_COMPOUND.  A cell and a declared term that render
# alike are *not* the same term (they do not unify), so they get adjacent
# but distinct places in the order rather than interleaving.
# (Flavour 1 was the keyword term's, retired with the class; the numbering
# is kept so the two remaining flavours order as they always did.)
_CF_POSITIONAL = 0   # cell
_CF_DECLARED = 2     # declared term instance / dataclass

# Task 15 item 1 (ISO alignment, Scryer-verified 2026-09-07).  There is no
# "sequence" band any more: a non-empty list -- and a string and a code list,
# which ARE lists (§5.4/§6.5) -- is the ``'.'/2`` COMPOUND it denotes, and
# keys in the compound band arity-first like every other compound.  So
# ``foo(x) < [z]`` (arity 1 before arity 2), ``[z] < f(a, b)`` (same arity,
# ``.`` before ``f``), and ``[] < a`` (``'[]'`` is an atom).  The retired
# bands ranked every sequence below every compound regardless of arity,
# which ISO 7.2.1 does not.
#
# The argument payload is the tuple of ELEMENT keys rather than a nested
# head/tail pair.  For a proper list the two comparisons agree: tuple-prefix
# order puts the shorter list first, which is what cons comparison gives
# because the shorter list's tail is the ATOM ``'[]'`` and atoms precede
# compounds.  The flat tuple is one allocation per list instead of one per
# cell.
_ORD_EMPTY_LIST_KEY = (_ORD_ATOM, "[]")
_ORD_CONS_NAME_KEY = (0, ".")


def _number_key(x, cell: int = 0) -> tuple:
    """The number-band key of a plain (undimensioned) number.

    Shared deliberately: a code list is a list of number TERMS, so the bytes
    branch must build element keys with EXACTLY this shape. When the scalar
    branch grew a dimension signature and a type rank and this did not, the
    two drifted and `b"ab"` stopped keying as `[97, 98]` — breaking both the
    "bytes IS the code list" invariant and the totality of the order, since a
    2-tuple key and a 4-tuple key compare int against tuple. Caught by
    tests/test_standard_order.py; one constructor prevents the recurrence.
    """
    # RULED 2026-09-17 Q2: two decimals of equal value and different SCALE
    # are distinct terms, ordered value first then scale (``1.0`` before
    # ``1.00``); every other kind carries scale 0.  The last component says
    # whether the term is the transfer CELL (1) or the object (0): the two
    # are different terms (``structural_eq`` says so), and a key that could
    # not tell them apart would let ``compare(=)`` hold where ``'=='`` says
    # no.  Both components are here, in the ONE number-key constructor, so
    # the shape stays uniform across the band (see the docstring above).
    scale = _number_scale(x)
    return (_ORD_NUM, (), x, _NUMERIC_RANK.get(_numeric_kind(x), 90), scale, cell)


def _number_scale(x) -> int:
    """The Decimal scale of a number term (``1.00`` -> 2); 0 for every other
    kind.  A subclass of Decimal is a Decimal (``numeric_kind``)."""
    return -x.as_tuple().exponent if isinstance(x, _Decimal) else 0


#: The spine of a list keys flat: one slot per element, then ONE slot for
#: what the spine ends in -- ``[]`` for a proper list, the tail ``T`` of
#: ``[E1, ..., En|T]``.  Slot against slot is what walking the two spines
#: compares (ISO 7.2.1, every cell is ``'.'/2``): two elements by their
#: keys; an element against an end is the cell ``'.'(E, ...)`` against
#: ``T``, which ``T``'s band, arity and name alone decide (a variable,
#: number or atom is before every compound, ``f(a, b)`` after ``'.'/2``),
#: so the end slot is ``(-1, key(T))`` when ``T`` comes before a cell and
#: ``(99, key(T))`` after; two ends by their keys.  Element keys start with
#: a band int from 0 to 6, between the two.  Before, a proper list was its
#: element keys alone and an improper one a nested ``(head, rest)`` pair,
#: so ``[a, b]`` against ``[a|c]`` compared ``b`` with ``c`` (``<``, where
#: ``[b]`` against ``c`` is ``>``) and ``[a|T]`` came after ``[a]``.
_ORD_LIST_END = (-1, (_ORD_ATOM, "[]"))
_ORD_CONS_HEAD = (_ORD_COMPOUND, 2, _ORD_CONS_NAME_KEY, _CF_POSITIONAL)


def _list_end_slot(tail_key: tuple) -> tuple:
    """The end slot (see above) of a spine ending in the term keyed *tail_key*."""
    return (-1 if tail_key[:4] < _ORD_CONS_HEAD else 99, tail_key)


def _cons_key(element_keys: tuple) -> tuple:
    """The standard-order key of the proper list with these elements."""
    return (_ORD_COMPOUND, 2, _ORD_CONS_NAME_KEY, _CF_POSITIONAL,
            element_keys + (_ORD_LIST_END,))


def _cons_chain_key(term) -> tuple:
    """The key of the cons cell ``'.'(H, T)`` -- an IMPROPER list
    ``[H1, ..., Hn|Tail]`` as its cells -- built along the tail spine by a
    loop: the flat spine key (:data:`_ORD_LIST_END`), where keying each
    cell as a compound recursed once per cell and overflowed at about 500
    cells (compare/3,
    sort/2, msort/2 on a hole-built improper list).  A spine that comes
    back to a cell or a SegList already on it (a cyclic list, whether the
    cycle closes through a hole or through a cell bound to itself) raises
    ``RecursionError``, as the recursion did, rather than looping; the
    objects are kept alive while their ids are recorded."""
    from clausal.terms import SegList  # noqa: PLC0415
    heads: list = []
    seen: set = set()
    keep: list = []
    t = term
    while True:
        if id(t) in seen:
            raise RecursionError("term_key: cyclic term")
        seen.add(id(t))
        keep.append(t)
        heads.append(t[1])
        t = deref(t[2])
        if isinstance(t, SegList):
            # A hole-built cyclic list closes its cycle through a hole,
            # whose binding is the same SegList object every lap.
            if id(t) in seen:
                raise RecursionError("term_key: cyclic term")
            seen.add(id(t))
            keep.append(t)
            from clausal.logic.runtime._seg_helpers import walk_seg  # noqa: PLC0415
            t = walk_seg(t)
        if type(t) is SegList:
            # a partial list in the tail: its elements continue the spine
            from clausal.logic.runtime._seg_helpers import partial_list_cells  # noqa: PLC0415
            cells = partial_list_cells(t)
            if cells is not None:
                t = cells
        if not (type(t) is tuple and len(t) == 3 and t[0] == "."):
            break
    tail_key = _term_key(t)
    if tail_key[:4] == _ORD_CONS_HEAD:
        # the spine goes on as a proper list (a cell whose tail is a list)
        elements = tail_key[4]
    else:
        elements = (_list_end_slot(tail_key),)
    return (_ORD_COMPOUND, 2, _ORD_CONS_NAME_KEY, _CF_POSITIONAL,
            tuple(_term_key(h) for h in heads) + elements)


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


def _term_key(term: Any) -> tuple:
    """Sort key implementing the standard order of terms.

    Total over every value a term can hold, so ``sorted(xs, key=...)`` never
    raises.  Recurses through compounds, lists, dicts, sets and cells,
    dereferencing as it goes, so nested numbers compare *numerically* rather
    than as strings.  A cell (spec §5.1) is NOT a sequence: an arity-0 cell
    is an atom and keys with the atom band identically to its str spelling
    (§6.5); an arity>0 cell -- ``str``-tagged or ``TUPLE_TAG``-tagged --
    keys in the compound band, arity first (ISO 7.2.1).  A list, a string
    and a code list key as the ``'.'/2`` compound they denote (Task 15
    item 1, :func:`_cons_key`); ``[]``/``""``/``b""`` key as the atom
    ``'[]'``.

    PUBLIC as ``clausal.term_key`` (dumb-seam step (b), 2026-09-26): the
    one sort key for terms a Python caller holds, so ``sorted(xs,
    key=term_key)`` is the engine's ``msort/2`` order and never raises on a
    mixed list.  ``_standard_order_key`` is the in-tree alias.  A ``Seg*``
    is walked (``walk_seg``) and keys as whatever that yields when it is no
    longer a ``Seg*`` -- a text Seg* as its string, a SegList as its list, a
    SegBytes as its code list -- the same answer the type checks give
    (``normalize_seg_input``); one that still walks to a ``Seg*`` (it holds
    an unbound hole) keeps the opaque band.  The walk sits on the fallthrough branch only, so
    every other key costs what it did (todo
    seg-star-keys-in-the-opaque-standard-order-band-2026-09-07).
    """
    term = deref(term)
    if is_var(term):
        # Unbound vars sort first, in a stable but arbitrary order — ISO
        # leaves the order among distinct variables implementation-defined.
        return (_ORD_VAR, id(term))
    # The concrete types first (fast), then the ABC for anything registered
    # into the numeric tower.  ``Decimal`` is a ``Number`` but not a ``Real``.
    if isinstance(term, Quantity):
        # A dimensioned number is a NUMBER: under the strict_units directive
        # every number in a program is a Quantity, and keying them in the
        # opaque band would sort every number after every atom and compound.
        # The dimension signature is sorted, so it is total and stable and
        # cross-dimension comparison neither raises nor falls back to repr —
        # which the opaque band did, via a `<` that rejects its own type.
        # Value, then the magnitude's Decimal scale, then its numeric KIND
        # (float before int, as for a bare number): ``100.0 m`` and
        # ``100 m`` are two terms to ``=`` and ``==`` (2026-10-23), and so
        # are ``10.0`` and ``10.00`` euro, so the key keeps them apart too,
        # or compare/3 says ``=`` where ``==`` says no and sort/2 and
        # setof/3 drop one.  The shape stays comparable with a bare number's
        # key (``_number_key``): the rank slot is the Quantity rank, which
        # never ties with a bare number's, and the extra slot comes last.
        v = term.value
        return (_ORD_NUM, tuple(sorted(term.dims.items())), v,
                _NUMERIC_RANK_QUANTITY, _number_scale(v), 0,
                _NUMERIC_RANK.get(_numeric_kind(v), 90))
    if term is True or term is False or term is _Undefined:
        # True/False/Undefined ARE the atoms true/false/undefined (D35,
        # ``atoms.is_truth_atom``, inlined: this is the hot path of every
        # sort): the atom band, by spelling -- Scryer orders
        # ``compare(>, true, a)`` and ``sort([true, 1], [1, true])``.
        # Before ``int`` below, since a bool IS an int to ``isinstance``.
        return (_ORD_ATOM, truth_spelling(term))
    if isinstance(term, (int, float, _Fraction, _Decimal, _Real)):
        # Plain numbers carry the EMPTY dimension signature, so a dimensionless
        # `Quantity` sorts among them by magnitude instead of after them.
        return _number_key(term)
    if isinstance(term, str):
        # STAGE 2 (spec 2026-09-18 §1): a str is an ATOM and keys in the atom
        # band by its spelling; the carrier below keys as its char list
        return (_ORD_ATOM, term)
    if isinstance(term, bytes):
        # A code list (§5.4): the list of its code NUMBERS, so ``b"ab"`` and
        # ``[97, 98]`` are one term in the order exactly as ``"ab"`` and its
        # char list are, and ``b""`` is the empty list.
        if not term:
            return _ORD_EMPTY_LIST_KEY
        return _cons_key(tuple(_number_key(c) for c in term))
    if is_chars(term):
        # STAGE 1 (spec 2026-09-18): the chars carrier keys exactly as the
        # str it holds -- the cons compound of its char atoms, ``'[]'`` when
        # empty -- so the two spellings of one text term have EQUAL keys.
        text = chars_text(term)
        if not text:
            return _ORD_EMPTY_LIST_KEY
        return _cons_key(tuple((_ORD_ATOM, c) for c in text))
    if type(term) is tuple and term and type(term[0]) is str and term[0] != TUPLE_TAG:
        # An exact-number cell -- the TRANSFER form of a Decimal or a Fraction
        # (RULED 2026-09-17) -- keys as the NUMBER it denotes, in the number
        # band, marked as the cell so it sorts right after its own object.
        # Only the canonical spelling; a look-alike falls through to the
        # compound band below.  See ``exact_cell_number``.
        num = exact_cell_number(term)
        if num is not None:
            return _number_key(num, 1)
        # A cell (spec §5.1).  STAGE 2: an atom is a str and keyed in the
        # atom band above; the 1-tuple is RESERVED and refuses just below.
        # Arity > 0 keys as a compound — arity first, then name
        # (ISO 7.2.1), positional flavour — never as a sequence.
        refuse_reserved_1tuple(term)   # STAGE 2: the arity-0 cell is RESERVED
        if len(term) == 3 and term[0] == ".":
            return _cons_chain_key(term)
        return (_ORD_COMPOUND, len(term) - 1, (0, term[0]), _CF_POSITIONAL,
                tuple(_term_key(a) for a in term[1:]))
    if type(term) is tuple and term and term[0] == TUPLE_TAG:
        return (_ORD_COMPOUND, len(term) - 1, (1, ""), _CF_POSITIONAL,
                tuple(_term_key(a) for a in term[1:]))
    if isinstance(term, (list, tuple)):
        # A LIST — the ``'.'/2`` compound it denotes, or the atom ``'[]'``
        # when empty (Task 15 item 1).  A plain ``tuple`` that is neither a
        # cell nor tuple-data keeps the list treatment it has always shared.
        if not term:
            return _ORD_EMPTY_LIST_KEY
        return _cons_key(tuple(_term_key(e) for e in term))
    if is_term_instance(term):
        names = term_field_names(term)
        return (_ORD_COMPOUND, len(names), (0, type(term).__name__), _CF_DECLARED,
                tuple(_term_key(getattr(term, n)) for n in names))
    if isinstance(term, (dict, DictTerm)):
        # DictTerm and a plain dict compare equal, so they share one key shape.
        pairs = [(_term_key(k), _term_key(v))
                 for k, v in term.items()]
        return (_ORD_DICT, tuple(sorted(pairs)))
    if isinstance(term, (set, frozenset, SetTerm)):
        return (_ORD_SET, tuple(sorted(_term_key(e) for e in term)))
    if isinstance(term, (SegList, SegString, SegBytes)):
        # A Seg* that walks to something else IS that string / list / bytes
        # (the type checks already answer for the walked form), so it keys
        # as that term -- ``walk_seg`` keeps the chars CARRIER, which keys as
        # the char list above, never as an atom.  One that still walks to a
        # Seg* holds an unbound hole and has no better key than the opaque
        # band.
        from clausal.logic.runtime._seg_helpers import walk_seg  # noqa: PLC0415
        walked = walk_seg(term)
        if not isinstance(walked, (SegList, SegString, SegBytes)):
            return _term_key(walked)
        # A partial list ``[B|A]`` is the compound ``'.'(B, A)`` (ISO
        # 6.3.5), keyed as its cells: it ranked after every term in the
        # opaque band, so ``compare(<, [B|A], [1|A])`` gave ``>``.
        from clausal.logic.runtime._seg_helpers import partial_list_cells  # noqa: PLC0415
        cells = partial_list_cells(walked)
        if cells is not None:
            return _cons_chain_key(cells)
    return (_ORD_OTHER, _OpaqueOrder(term))


#: In-tree alias; every builtin that sorts imports this name.  It is the
#: RAW key: a cyclic term, or one too deep to key, raises RecursionError,
#: which the sorts catch to compare that pair by ``term_compare``.
_standard_order_key = _term_key


def term_key(term: Any) -> tuple:
    """The PUBLIC standard-order sort key (``clausal.term_key``): the key
    :func:`_term_key` builds, for a Python caller.

    A sort key is a finite Python value, so a CYCLIC term (``X = f(X)``)
    has none: it raises ``error(resource_error(finite_memory), _)``, the
    error the engine raises where it knows it saw a cycle (ruling
    2026-10-24, provisional), and an acyclic term nested too deep to key
    raises ``error(resource_error(stack), _)`` -- both as a
    ``LogicException``, never a raw RecursionError (2026-10-24).
    ``compare/3`` and ``msort/2`` still order such terms: they catch the
    raw key's overflow and compare the pair by ``term_compare``; a Python
    caller orders cyclic terms by solving ``compare/3``."""
    try:
        return _term_key(term)
    except RecursionError:
        from clausal.logic.rational_walk import unwalkable_term_error  # noqa: PLC0415
        raise unwalkable_term_error(term, "term_key/1", "sort key") from None


# ── The standard order decided pairwise (cyclic and very deep terms) ─────────
#
# ``term_key`` builds a term's whole key, one nested tuple per level: there
# is no finite key for a CYCLIC term (``X = f(X)``, which ISO ``=/2`` builds
# with no occurs check), and a term nested deeper than Python's stack
# overflows while keying -- or while CPython compares two keys that deep.
# ``term_compare`` decides the same order pairwise, by an explicit stack,
# and takes a compound pair it meets again as equal (the coinductive
# reading, the 2026-10-13 ruling's requirements: keyed by the dereferenced
# objects themselves, kept alive while keyed), which is how Scryer orders
# rational trees: ``compare(=, X, Y)`` for ``X = f(X), Y = f(f(Y))``,
# ``<`` for ``X = f(X, a), Y = f(Y, b)``.  compare/3, the ``@<`` family and
# the sorts call it only when ``term_key`` raises RecursionError, so an
# ordinary term's order and speed are untouched.
#
# For an acyclic term it decides exactly as the keys do -- band, arity,
# name, then the arguments left to right, the first difference deciding --
# including lists: a proper list and an improper one both key as the flat
# spine (:data:`_ORD_LIST_END`), and a proper list against a cons cell is
# walked here cell by cell, head then rest, which is the same order (ISO
# 7.2.1: every cell is ``'.'/2``).  One order for both paths, so the sorts
# (keys) and compare/3's fallback agree and the order stays transitive
# across mixed triples
# (tests/test_term_compare_order.py).

_LEN = object()    # a stack marker: decide two lists' lengths after their common prefix


def _shallow_compound_key(t):
    """The first four components of ``term_key``'s compound-band key for
    *t* -- ``(band, arity, name, flavour)`` -- or None when *t* keys in
    another band (a variable, a number, an atom, ``[]``, a dict, a set, an
    opaque value) and ``term_key`` is the thing to call."""
    if isinstance(t, list):
        return (_ORD_COMPOUND, 2, _ORD_CONS_NAME_KEY, _CF_POSITIONAL) if t else None
    if type(t) is tuple and t and type(t[0]) is str and t[0] != TUPLE_TAG:
        if len(t) == 1 or exact_cell_number(t) is not None:
            return None
        return (_ORD_COMPOUND, len(t) - 1, (0, t[0]), _CF_POSITIONAL)
    if type(t) is tuple and t and t[0] == TUPLE_TAG:
        return (_ORD_COMPOUND, len(t) - 1, (1, ""), _CF_POSITIONAL)
    if is_term_instance(t):
        return (_ORD_COMPOUND, len(term_field_names(t)), (0, type(t).__name__),
                _CF_DECLARED)
    return None


def _compound_view(t):
    """*t* (dereferenced) as the shape ``term_compare`` walks: text and a
    code list as the list of their elements (the cons compound ``term_key``
    keys them as), a Seg* as what it walks to, a plain tuple that is neither
    a cell nor tuple-data as the list ``term_key`` reads it as."""
    if isinstance(t, bytes):
        return list(t)
    if is_chars(t):
        return list(chars_text(t))
    if isinstance(t, (SegList, SegString, SegBytes)):
        from clausal.logic.runtime._seg_helpers import walk_seg  # noqa: PLC0415
        walked = walk_seg(t)
        if not isinstance(walked, (SegList, SegString, SegBytes)):
            return _compound_view(walked)
        from clausal.logic.runtime._seg_helpers import partial_list_cells  # noqa: PLC0415
        cells = partial_list_cells(walked)
        return t if cells is None else cells
    if (type(t) is tuple and t and not (type(t[0]) is str and t[0] != TUPLE_TAG)
            and t[0] != TUPLE_TAG):
        return list(t)
    return t


def term_compare(a, b) -> int:
    """The standard order of *a* against *b*, decided pairwise: -1, 0 or 1.
    See the block comment above."""
    stack: list = [(a, b)]
    seen: set = set()
    keep: list = []
    while stack:
        item = stack.pop()
        if item[0] is _LEN:
            if item[1] != item[2]:
                return -1 if item[1] < item[2] else 1
            continue
        ox, oy = deref(item[0]), deref(item[1])
        if ox is oy:
            continue
        x, y = _compound_view(ox), _compound_view(oy)
        sx, sy = _shallow_compound_key(x), _shallow_compound_key(y)
        if sx is None and sy is None:
            kx, ky = _term_key(x), _term_key(y)
            if kx != ky:
                return -1 if kx < ky else 1
            continue
        if sx is None:
            return -1 if _term_key(x) < sy else 1
        if sy is None:
            return -1 if sx < _term_key(y) else 1
        if sx != sy:
            return -1 if sx < sy else 1
        # Keyed by the ORIGINAL objects (a Seg* walks to fresh cells every
        # time; the SegList itself is what a cycle comes back to).
        key = (id(ox), id(oy))
        if key in seen:
            continue
        seen.add(key)
        keep.append((ox, oy, x, y))
        if isinstance(x, list) and isinstance(y, list):
            # Two lists element by element, then the lengths.
            n = min(len(x), len(y))
            stack.append((_LEN, len(x), len(y)))
            for i in range(n - 1, -1, -1):
                stack.append((x[i], y[i]))
        elif isinstance(x, list) or isinstance(y, list):
            # A list against a cons cell, cell by cell: the heads, then the
            # rests (``[a, b]`` against ``[a|c]`` is ``[b]`` against ``c``).
            hx, rx = (x[0], x[1:]) if isinstance(x, list) else (x[1], x[2])
            hy, ry = (y[0], y[1:]) if isinstance(y, list) else (y[1], y[2])
            stack.append((rx, ry))
            stack.append((hx, hy))
        elif is_term_instance(x):
            names = term_field_names(x)
            for name in reversed(names):
                stack.append((getattr(x, name), getattr(y, name)))
        else:
            for i in range(len(x) - 1, 0, -1):
                stack.append((x[i], y[i]))
    return 0


def _term_compare_key(x):
    """``functools.cmp_to_key(term_compare)``'s key for *x*: the sort key
    the sorts fall back to when ``term_key`` cannot key an element."""
    return _functools.cmp_to_key(term_compare)(x)


# Exact types whose native ``<`` is KNOWN to agree with
# :func:`_standard_order_key`, each verified by measurement 2026-09-09.
# Membership is a POSITIVE claim and needs evidence; absence costs only speed,
# so the safe direction is to leave a type out.
#
# ``tuple`` is excluded because it is PROVEN wrong: cells key arity-first
# (ISO 7.2.1) while Python compares tuples elementwise, so
# ``[('f', 1, 2), ('g', 1)]`` sorts to ``[f/2, g/1]`` natively and
# ``[g/1, f/2]`` by key. ``list`` is excluded because it is NOT proven right —
# a list whose elements are compounds inherits exactly that disagreement.
# ``Quantity`` is excluded because its ``<`` raises across dimensions.
# ``Decimal`` LEFT this set 2026-09-17 (RULED Q2): two decimals of equal value
# and different scale are distinct terms ordered by scale, and Python's own
# ``<`` calls them equal -- so a homogeneous Decimal list sorted natively
# would keep ``[1.00, 1.0]`` in input order where the key says ``[1.0, 1.00]``.
# Membership is a positive claim, and the ruling removed the evidence.
_NATIVE_ORDER_SAFE = frozenset({int, float, bool, str, bytes, _Fraction})


def _standard_order_sorted(items: list) -> list:
    """Sort *items* into the standard order of terms.

    A homogeneous list of a known-safe type keeps Python's own ordering, which
    is the common case and the fast one. Everything else goes through
    :func:`_standard_order_key`.

    ``set(map(type, items))`` is one C-level pass and the set is bounded by the
    number of DISTINCT types, not the list length, so a million-element int
    list yields a one-element set. ``type()`` rather than ``isinstance()`` is
    deliberate: exact identity keeps subclasses off the native path, which
    matters for ``bool`` (a subclass of ``int``) and for any future
    ``Quantity`` subclass such as a strict-units one.

    This replaces a ``try/except TypeError`` that discovered incomparability by
    CATCHING A FAILURE. Two things escaped it. ``Quantity.__lt__`` raises
    ``UnitsMismatch``, which is not a ``TypeError``, so sorting across
    dimensions — or a quantity against a plain number — CRASHED rather than
    falling back. And equal-value ``int``/``float`` raise nothing at all, so
    the native path returned an INPUT-ORDER-DEPENDENT answer: ``[1, 1.0]`` and
    ``[1.0, 1]`` each sorted to themselves. A guard that fires only on
    exceptions cannot see either case; a type gate sees both.
    """
    types = set(map(type, items))
    if len(types) == 1 and types.pop() in _NATIVE_ORDER_SAFE:
        return sorted(items)
    try:
        return sorted(items, key=_standard_order_key)
    except RecursionError:
        # A cyclic or very deep element: no key, the pairwise order instead.
        return sorted(items, key=_term_compare_key)


def _check_nonneg_int_arg(val: Any, who: str) -> None:
    """ISO's argument check for an integer position that may be unbound.

    An unbound (already dereferenced) *val* passes; a bound one must be an
    integer (``type_error(integer, V)``; a bool is the truth value, not 1)
    and not negative (``domain_error(not_less_than_zero, V)``).  Builtins
    used to FAIL silently on these (``arg(x, f(a), _)``,
    ``sub_atom(abc, _, -1, _, _)``), where ISO and Scryer raise.
    """
    if is_var(val):
        return
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, domain_error, type_error)
    if not isinstance(val, int) or isinstance(val, bool):
        raise LogicException(type_error("integer", val, who))
    if val < 0:
        raise LogicException(domain_error("not_less_than_zero", val, who))
