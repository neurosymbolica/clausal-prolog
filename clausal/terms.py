"""clausal.terms — logic term layer.

functor types and value types for the clausal logic programming system.

Python built-in types (int, float, str, bool, None, list) are terms directly —
no wrapper needed.  Logic variables are Var objects.  Structured terms are
cells: tuples ``(functor, *args)`` whose slot 0 is the functor atom, e.g.
``('f', 1, 2)`` for ``f(1, 2)``.

Goal types are term types: the same classes serve as goal nodes when they appear
in a predicate body.  The compiler dispatches on the class via Python's match
statement.
"""

from __future__ import annotations

import re as _re
import dataclasses as _dataclasses
from dataclasses import dataclass
from fractions import Fraction

from clausal.logic.exact_arith import exact_add, exact_mul, exact_sub  # ONE spelling of + - * (2026-09-18)
from clausal.logic import _units_flag
from decimal import (
    Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
    ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR,
)
from types import MappingProxyType
from typing import Any

from .logic.atoms import (
    _register_undefined as _register_undefined_atom, truth_spelling as _truth_spelling,
    as_dict_key as _as_dict_key, char_atom, demangle_for_display,
    is_char_atom, is_mangled, is_nil as _is_nil, spelling,
)
from .logic.cells import (TUPLE_TAG, CHARS_TAG, chars, is_chars, chars_text, chars_payload,
                          refuse_reserved_1tuple, _Text, text_slice)
from .logic.variables import Var, deref
# Operator table for ``term_writeq``; this module imports nothing from clausal.
from clausal.tools.prolog_operators import OperatorTable as _OperatorTable

# Re-export operator/expression classes already defined in pythonic_ast.
# They are plain dataclasses that work as both terms and goal nodes.
from .pythonic_ast.nodes import (
    # Arithmetic binary operators
    Add, Sub, Mult, Div, FloorDiv, Mod, Pow,
    # Bitwise / shift binary operators
    BitAnd, BitOr, BitXor, LShift, RShift,
    # Boolean binary operators (also conjunction / disjunction goals)
    And, Or,
    # Unary operators
    Not, Invert, Negate,
    # Comparison / unification operators
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq,
    StructuralEq, StructuralNeq,
    Lt, LtE, Gt, GtE, in_, NotIn,
    # Expression nodes used in predicate bodies
    Call, LoadName, LoadAttr, LoadSubscript, Slice,
    # Predicate clause term
    Predicate,
)


# ── Exceptions ────────────────────────────────────────────────────────────────


class PartialTermError(Exception):
    """Raised when a non-ground SegList/SegString cannot satisfy an operation.

    Deliberately not a :class:`TypeError` subclass — callers that previously
    caught the bare ``TypeError`` raised from ``to_list()`` / ``to_str()`` /
    ``str.join`` on partial Seg* terms were getting a leaked low-level
    CPython exception with no clausal-identity. ``PartialTermError`` lets
    those callers distinguish "this Seg* is partial / malformed" from
    generic Python type errors and surface a meaningful diagnostic.

    Audit findings: F021, F023, F024, F038, F039
    (docs/superpowers/audits/2026-05-25-string-implementation/findings.md).
    """


def _slice_within_prefix(index, prefix_len: int) -> bool:
    """True if ``index`` is a forward slice fully served by the first
    ``prefix_len`` elements of a non-ground Seg* term (A01-F010).

    Requires a non-negative ``start`` (or None → 0), a concrete ``stop``
    no larger than the prefix, and a forward ``step``. Negative bounds,
    open-ended (``stop is None``) or reverse slices depend on the trailing
    VarSeg's eventual binding and are *not* knowable from the prefix.
    """
    if not isinstance(index, slice):
        return False
    start, stop, step = index.start, index.stop, index.step
    return (
        (start is None or (isinstance(start, int) and start >= 0))
        and isinstance(stop, int) and 0 <= stop <= prefix_len
        and (step is None or (isinstance(step, int) and step > 0))
    )


# ── New term types ─────────────────────────────────────────────────────────────

def as_cells_for_match(term: Any, depth: int, classes: bool = False) -> Any:
    """``term`` dereferenced and made ready for a compiled clause-head
    ``match``, down to *depth* structure levels: a slot holding a Var BOUND
    to a structure becomes that structure -- a ``match`` does not
    dereference, so a sequence pattern never matched the Var
    (``w3(('k', V))`` with ``V = f(2)`` missed its bucket).

    *depth* and *classes* come from the BUILT patterns at that argument
    position (``head_match.finalize_subject_depths``): *depth* is their
    deepest structure nesting, and *classes* says whether any of them is a
    CLASS pattern (a term instance).  Only then are a dataclass instance's
    fields walked -- otherwise no class pattern can inspect them, and copying
    the instance would be waste (roborev 205).

    Nothing is copied unless something is converted: the result is
    ``deref(term)`` itself, and an unconverted slot keeps its original object.
    The C twin is ``as_cells_for_match`` in ``_variables.c``; it hands term
    instances back to :func:`_cells_below`.
    """
    term = deref(term)
    if depth <= 0:
        return term
    converted = _cells_below(term, depth, classes)
    return term if converted is None else converted


# Slot values a head pattern never destructures: skipped without a deref or a
# dataclass probe (roborev 205).  Exact types only -- a subclass takes the
# general path.
_SCALAR_SLOT_TYPES = frozenset({int, float, str, bool, bytes, type(None)})


def _cells_below(term: Any, depth: int, classes: bool = False) -> Any:
    """The converted form of the (already dereferenced) *term*, or None when
    nothing within *depth* structure levels needed converting.  A LEVEL is a
    cell (tuple) or, when *classes*, a dataclass term instance (its fields
    walked)."""
    if depth <= 0:
        return None
    if type(term) is tuple:
        new = _cells_in_slots(term, 1, depth, classes)
        return None if new is None else tuple(new)
    if classes and _is_structure_instance(term):
        if depth <= 1:
            return None
        changed = {}
        for f in _dataclasses.fields(term):
            sub = _cells_of(getattr(term, f.name), depth - 1, classes)
            if sub is not None:
                changed[f.name] = sub
        if not changed:
            return None
        import copy  # noqa: PLC0415
        new = copy.copy(term)
        for name, value in changed.items():
            object.__setattr__(new, name, value)
        return new
    return None


def _cells_of(slot: Any, depth: int, classes: bool) -> Any:
    """The replacement for one slot value at *depth*, or None to keep it."""
    if type(slot) in _SCALAR_SLOT_TYPES:
        return None
    elt = deref(slot)
    if (type(elt) is tuple
            or (classes and _is_structure_instance(elt))):
        sub = _cells_below(elt, depth, classes)
        if sub is not None:
            return sub
        if elt is not slot:
            return elt          # a Var bound to a structure: the structure
    return None


def _cells_in_slots(seq: Any, start: int, depth: int, classes: bool) -> "list | None":
    """*seq* as a list with its slots from *start* converted one level down,
    or None when none needed converting."""
    if depth <= 1 or len(seq) <= start:
        return None
    new = None
    for i in range(start, len(seq)):
        sub = _cells_of(seq[i], depth - 1, classes)
        if sub is not None:
            if new is None:
                new = list(seq)
            new[i] = sub
    return new


def _is_structure_instance(x: Any) -> bool:
    return _dataclasses.is_dataclass(x) and not isinstance(x, type)


# ── SegList — segmented partial list ─────────────────────────────────────────


@dataclass
class ConcreteSeg:
    """A concrete (known) segment of a SegList — a fixed sequence of elements."""
    elements: list


@dataclass
class VarSeg:
    """A variable-length hole in a SegList — represents an unknown subsequence."""
    var: Var


# ── Seg* __unify__ against a list or text ─────────────────────────────────────
#
# ``unify`` is deterministic: one call, one answer.  A partial list with ONE
# hole (``[1|T]``, ``[*A, x]``) has at most one split against a list of known
# length, so ``__unify__`` is exact for it.  With TWO OR MORE holes
# (``[*A, *B]``) there can be several splits.  Where the compiler sees the
# pattern (a clause head, an ``is`` goal) it enumerates them itself.  Where
# the pattern reaches ``unify`` as a value, ``_drive_seg_unify`` queues a
# pending goal that binds each split in turn, under a driver
# (``trail.defer``); a bare ``unify`` from Python binds the first split.
#
# ``__unify__`` used to cache a suspended split enumerator per term, keyed by
# the target's CONTENT and the trail, so that calling it again resumed at the
# next split.  No engine path calls it again for that purpose, and the key
# was wrong twice over: building it hashed the whole target on every call
# (a token-list DCG spent 85% of its time there, quadratic in the input),
# and a second, EQUAL target on the same trail resumed the first one's drive
# instead of starting its own -- ``P = [1|T], member(P, [[1,2],[1,2]])``
# lost the second answer.  Each call now starts from the first split.


def _seg_split_gen(segments, target_len, concrete_len):
    """Trail-free enumerator of candidate splits: yield one size-tuple per
    weak composition of the free length across the term's VarSegs.

    *concrete_len* is the total length consumed by concrete segments.
    Holds no trail and performs no binding — the driver applies each split.
    """
    if target_len < concrete_len:
        return
    n_stars = sum(1 for s in segments if isinstance(s, VarSeg))
    yield from _multi_star_splits(n_stars, target_len - concrete_len)


def _seg_slice_out(sl):
    """A slice of a split target as the term a hole binds to: a str target's
    slice is the chars CARRIER (stage 1); a list's slice is itself."""
    if type(sl) is str:
        return chars(sl)
    if type(sl) is _Text:
        return (CHARS_TAG, sl)          # a view of the target: the carrier of its text
    return sl


def _apply_seglist_split(seglist, target_list, split, trail):
    """Bind *seglist* against *target_list* for one *split*; return True on
    success (bindings left on *trail*), False otherwise. Mirrors the inner
    loop of :func:`_seglist_unify_gen`."""
    from .logic.variables import unify
    # A ``str`` target is a char list: its ELEMENTS are chars, its SLICES
    # stay str (R-S2). Twin of ``_seg_helpers.seq_getitem``.
    target_is_str = type(target_list) is str or type(target_list) is _Text
    pos = 0
    si = 0
    for seg in seglist.segments:
        if isinstance(seg, VarSeg):
            sz = split[si]; si += 1
            # A long slice of text is a view of it, not a copy (a view slices
            # to a view): a DCG step binds the rest of its input without
            # copying it, and the choice points do not each hold a copy.
            # Likewise a long rest of a list is a view of it.
            if type(target_list) is str:
                piece = text_slice(target_list, pos, pos + sz)
            elif type(target_list) is list or type(target_list) is SegListView:
                piece = list_rest(target_list, pos, pos + sz)
            else:
                piece = target_list[pos:pos + sz]
            if not unify(seg.var, _seg_slice_out(piece), trail):
                return False
            pos += sz
        else:
            for elem in seg.elements:
                if pos >= len(target_list):
                    return False
                at = (char_atom(target_list[pos]) if target_is_str
                      else target_list[pos])
                if not unify(elem, at, trail):
                    return False
                pos += 1
    return True


def _apply_segstring_split(segstring, target_str, split, trail):
    """SegString analogue of :func:`_apply_seglist_split` (str segments are
    compared, not unified). Mirrors :func:`_segstring_unify_gen`."""
    from .logic.variables import unify
    pos = 0
    si = 0
    for seg in segstring.segments:
        if isinstance(seg, VarSeg):
            sz = split[si]; si += 1
            if not unify(seg.var, chars(target_str[pos:pos + sz]), trail):   # stage 1
                return False
            pos += sz
        else:  # str
            end = pos + len(seg)
            if target_str[pos:end] != seg:
                return False
            pos = end
    return True


def _apply_segbytes_split(segbytes, target_bytes, split, trail):
    """SegBytes analogue of :func:`_apply_seglist_split`. Mirrors
    :func:`_segbytes_unify_gen`."""
    from .logic.variables import unify
    pos = 0
    si = 0
    for seg in segbytes.segments:
        if isinstance(seg, VarSeg):
            sz = split[si]; si += 1
            if not unify(seg.var, target_bytes[pos:pos + sz], trail):
                return False
            pos += sz
        else:  # bytes
            end = pos + len(seg)
            if target_bytes[pos:end] != seg:
                return False
            pos = end
    return True


def _drive_seg_unify(walked, other, trail, concrete_len, apply_fn):
    """Unify *walked* against *other*; True on success, False with the trail
    as it was.

    One hole has at most one split, bound here.  With two or more holes
    there can be several: ``[*A, *B] = [1, 2]`` has three answers, in the
    order ``append/3`` gives them.  Under a driver (``trail.defer``) this
    checks that one split fits, leaves the holes unbound and queues a pending
    goal that binds each split in turn, so the next goal boundary backtracks
    into every one (``clausal.logic.pending``).  When the first split that
    fits is the last candidate there is nothing to enumerate, and it is
    bound here.  Outside a driver (a bare ``unify`` from Python) the first
    split that fits is bound, as before."""
    splits = _seg_split_gen(walked.segments, len(other), concrete_len)
    for split in splits:
        mark = trail.mark()
        if apply_fn(walked, other, split, trail):
            if not trail.defer:
                return True
            rest = next(splits, None)
            if rest is None:
                return True        # the only candidate left: deterministic
            trail.undo(mark)

            def goal():
                for each in _seg_split_gen(walked.segments, len(other),
                                           concrete_len):
                    m = trail.mark()
                    if apply_fn(walked, other, each, trail):
                        yield None
                    trail.undo(m)

            trail.push_pending(goal)
            return True
        trail.undo(mark)
    return False


# ── _EMPTY_SEG_IS_NIL — an empty Seg* is the empty list, in every spelling ───
#
# Task 15 fix round 4, item 5.  Nil is ONE term with several spellings --
# ``[]``, ``""``, ``b""``, ``()`` -- and every top-level pair of them unifies.
# A ``Seg*`` that WALKS to nothing is that same term, so it must answer alike
# for all four; before this, each Seg only accepted the spelling its own arm
# is typed for, leaving a residual NON-TRANSITIVITY: ``SegString([""])``
# unified with ``""`` and ``""`` unified with ``b""``, but ``SegString([""])``
# and ``b""`` were False.
#
def _walked_nil(w) -> bool:
    """Is a Seg*'s raw walk the empty sequence?  A text Seg walks to a bare
    ``str`` (``SegString._walk_raw``), which after STAGE 2 is an ATOM to
    ``is_nil`` -- here it is the text, so ``""`` is nil."""
    return (w == "") if type(w) is str else _is_nil(w)


# The six ``__unify__``/``__eq__`` methods therefore ask ``_is_nil`` of the
# target and of their own WALKED value, ahead of everything else, and answer
# True.  Two properties make that safe:
#
#   * it is gated on the target being nil, so the (cheap) walk runs only for
#     a nil target, never on the hot arms;
#   * it tests the WALKED term, so an OPEN ``Seg*`` -- one with an unbound
#     ``VarSeg`` -- never reaches it and keeps its generator-driven split.
#     That is exactly what the round-3 narrowing protects: ``[*A] = ""``
#     binds ``A = ""`` (not ``A = []``), pinned by
#     tests/test_string_list_unification.py and re-pinned by
#     tests/test_segstring.py::TestAnEmptySegIsTheEmptyList.
#
# The round-3 ``()`` -> ``[]`` rewrite stays underneath for the NON-empty
# case (``unify(SegList([ConcreteSeg([1])]), ())`` must still be False by the
# ordinary list comparison, not by type mismatch).


# ── A partial list, read for the reified equality (=/3) and dif/2 ──────────
#
# The occurs-checked structural unifier behind ``reify_eq`` and ``dif``
# (``_structural_unify_oc`` in clausal/logic/_constraints_dif.c, and its
# Python twin in clausal.logic.constraints) PROBES: it unifies, looks at the
# trail, and undoes.  It was kept away from ``SegList.__unify__`` because
# that hook used to advance a cached split generator on every call with the
# same ``(target, trail)``, so the probe consumed the one split a partial
# list has and the real unification that followed answered False --
# ``'='([a, b], [a|L], T)`` gave only ``T = false``.  The cache is gone; a
# partial list has exactly one way to unify, and the unifier still reads it
# with these two helpers and pairs its elements itself.


def _partial_list_parts(t):
    """Read *t* (dereferenced, not a Var) as the list ``[E1, ..., En|Tail]``:
    ``(elements, tail)`` with *tail* an unbound Var, or ``(elements, None)``
    for a proper list (a ``list``, the nil ``()``, a chars carrier -- its
    chars -- a ``bytes`` -- its codes, as ``SegList.__unify__`` reads them -- or a
    SegList whose holes are all filled).  ``None`` for anything else: a
    SegList with a hole that is not its tail (``[*A, x]``), which only the
    split-searching ``SegList.__unify__`` can answer, and every non-list."""
    if isinstance(t, list):
        return t, None
    if type(t) is tuple and not t:
        return [], None                # () is the nil (atoms.NIL_KEY)
    if is_chars(t):
        return [char_atom(c) for c in chars_text(t)], None
    if isinstance(t, bytes):
        return list(t), None
    if isinstance(t, SegList):
        if not all(isinstance(g, (ConcreteSeg, VarSeg)) for g in t._segments):
            return None        # not a SegList this module builds (__unify__ too)
        w = t._walk_raw()
        if isinstance(w, list):
            return w, None
        segs = w.segments
        if not isinstance(segs[-1], VarSeg) or not all(
                isinstance(s, ConcreteSeg) for s in segs[:-1]):
            return None
        return [e for s in segs[:-1] for e in s.elements], deref(segs[-1].var)
    return None


def _partial_list_build(elements, tail):
    """The list ``[E1, ..., En|Tail]`` (*tail* an unbound Var, or None for
    ``[]``): what a shorter list's tail binds to."""
    if tail is None:
        return list(elements)
    if not elements:
        return tail
    return SegList([ConcreteSeg(list(elements)), VarSeg(tail)])


# ── Two OPEN SegLists (F030) ───────────────────────────────────────────────
#
# ISO unifies two partial lists element by element: ``[1|T1] = [H|T2]`` binds
# ``H = 1, T1 = T2``.  Two open SegLists used to answer False outright (the
# SegList-vs-SegList arm was NotImplemented), so ``L is [1, *_], L is [H, *_]``
# and a head pattern ``p([H, *T])`` called with ``[1, *_]`` both failed.
#
# Handled here: pair the elements of the two leading concrete runs, then
# finish with the one case unification decides without search -- a side whose
# remainder is a SINGLE hole takes the other side's remainder, and an empty
# remainder empties every hole on the other side.  That covers every pair of
# ISO partial lists (a concrete prefix and one tail hole) and any Clausal
# SegList meeting one.  Two remainders that both open with a hole and go on
# (``[*A, 1]`` against ``[*B, 2]``) are ambiguous -- there is no single most
# general unifier -- and stay unhandled (NotImplemented), as before.


def _seglist_tokens(walked) -> list:
    """The walked SegList as a flat token list: ``(False, element)`` for an
    element, ``(True, var)`` for a hole."""
    out: list = []
    for seg in walked.segments:
        if isinstance(seg, ConcreteSeg):
            out.extend((False, e) for e in seg.elements)
        else:
            out.append((True, seg.var))
    return out


def _seglist_from_tokens(tokens):
    """The list term *tokens* spells: a hole alone is its variable, no hole
    is a plain list, anything else a SegList."""
    if len(tokens) == 1 and tokens[0][0]:
        return tokens[0][1]
    if not any(is_hole for is_hole, _ in tokens):
        return [x for _, x in tokens]
    segs: list = []
    for is_hole, x in tokens:
        if is_hole:
            segs.append(VarSeg(x))
        elif segs and isinstance(segs[-1], ConcreteSeg):
            segs[-1].elements.append(x)
        else:
            segs.append(ConcreteSeg([x]))
    return SegList(segs)


def _is_cons_cell(t) -> bool:
    """Whether *t* is the ISO cons cell ``'.'(H, T)`` as a compound -- the
    representation of an IMPROPER list such as ``[b|foo]`` (a proper list
    is a Python ``list``, a partial one a ``SegList``)."""
    return type(t) is tuple and len(t) == 3 and t[0] == "."


def _unify_seglist_cons(walked, cell, trail):
    """A list pattern (*walked*: a ``SegList`` or a plain ``list``) against
    the cons cell *cell*: pair the pattern's leading elements with the
    cells' heads, then unify what is left of the pattern with the cells'
    tail.  ``[H, *T] = '.'(b, foo)`` binds ``H = b, T = foo``, as ISO's
    ``[H|T] = [b|foo]`` does; ``[b] = [b|foo]`` fails (a proper list is
    never an improper one)."""
    from .logic.variables import unify
    segs = (list(walked.segments) if isinstance(walked, SegList)
            else [ConcreteSeg(list(walked))])
    elems: list = []
    mark = trail.mark()
    tail = cell
    while _is_cons_cell(tail):
        while not elems and segs and isinstance(segs[0], ConcreteSeg):
            elems = list(segs.pop(0).elements)
        if not elems:
            break                        # a hole (or nothing) is next
        if not unify(elems.pop(0), tail[1], trail):
            trail.undo(mark)
            return False
        tail = deref(tail[2])
    rest = ([ConcreteSeg(elems)] if elems else []) + segs
    if _is_cons_cell(tail) and not (len(rest) == 1
                                    and isinstance(rest[0], VarSeg)):
        # Stopped at an interior hole (``[*A, b]``, ``[*A, *B]``): a hole
        # holds a LIST, so what follows it is a proper-list pattern and can
        # never be the improper remainder -- fail, rather than hand the same
        # SegList back to this function.
        trail.undo(mark)
        return False
    if not rest:
        rest_term: Any = []
    elif len(rest) == 1 and isinstance(rest[0], VarSeg):
        rest_term = rest[0].var          # the tail variable takes the rest
    elif len(rest) == 1:
        rest_term = list(rest[0].elements)
    else:
        rest_term = SegList(rest)
    if unify(rest_term, tail, trail):
        return True
    trail.undo(mark)
    return False


def _unify_open_seglists(a, b, trail):
    """Unify two walked, non-ground SegLists; NotImplemented when the pair is
    ambiguous (see the block comment above)."""
    from .logic.variables import unify, deref
    ta, tb = _seglist_tokens(a), _seglist_tokens(b)
    i = 0
    n = min(len(ta), len(tb))
    while i < n and not ta[i][0] and not tb[i][0]:
        if not unify(ta[i][1], tb[i][1], trail):
            return False
        i += 1
    ra, rb = ta[i:], tb[i:]
    for one, other in ((ra, rb), (rb, ra)):
        if len(one) == 1 and one[0][0]:
            hole = deref(one[0][1])
            # ``[*A]`` against ``[1, *A]`` would make A cyclic; ISO without
            # the occurs check builds a rational tree, which no walk here can
            # finish, so it fails instead.
            if any(h and deref(v) is hole for h, v in other) and len(other) > 1:
                return False
            return unify(one[0][1], _seglist_from_tokens(other), trail)
        if not one:
            if not all(h for h, _ in other):
                return False
            return all(unify(v, [], trail) for _, v in other)
    return NotImplemented


_WALK_END = object()   # end of a segment iterator in SegList._walk_raw


class SegList:
    """A first-class term representing a list with variable-length holes.

    A SegList is a flat sequence of alternating ConcreteSeg and VarSeg objects.
    when every VarSeg's var is bound to a concrete list, the SegList is ground
    and ``__walk__`` returns a plain Python list.

    Example::

        [1, 2, *MID, 5, *TAIL]
        → SegList([ConcreteSeg([1, 2]), VarSeg(MID), ConcreteSeg([5]), VarSeg(TAIL)])
    """

    __slots__ = ("_segments",)

    def __init__(self, segments: list):
        self._segments = list(segments)

    @property
    def segments(self) -> list:
        return self._segments

    # ── Walk / normalisation ──────────────────────────────────────────────────

    def _walk_raw(self):
        """``__walk__`` WITHOUT the F018 str promotion: a ground SegList
        normalises to its plain element ``list``, a non-ground one to a
        ``SegList`` (or ``[]``).

        Every arm of this class that needs the term's own ELEMENTS —
        ``__unify__``, ``__eq__``, ``__contains__``, ``__getitem__``,
        ``to_list``, ``_concrete_prefix`` — uses this rather than reversing
        ``__walk__``'s promotion.  While two char representations coexist
        (Stage A of 2026-09-06-atoms-as-cells-strings: a plain 1-char ``str``
        and the arity-0 cell ``("a",)`` are both chars), the promoted ``str``
        is a LOSSY encoding of the elements — re-splitting ``"ab"`` can only
        yield one of the two shapes, so a SegList of cell chars stopped being
        equal to, and unifiable with, its own elements.  Reading the elements
        directly is exact in both stages.
        """
        # Iterative, with one flat accumulator: a partial list built forward
        # through its open tail (a DCG, ``Hole = [a|Hole1]`` in a loop) is a
        # chain of SegLists, one link per step, and walking it recursively
        # overflowed the C stack at a few thousand links while copying the
        # accumulated elements at every level (quadratic).  Each segment
        # rule is the one the recursive walk applied.
        from .logic.variables import walk, deref, is_var
        segs: list = []          # finished segments: ConcreteSeg / VarSeg
        run: list = []           # the concrete elements since the last hole
        stack = [(iter(self._segments), id(self))]
        open_ids = {id(self)}    # SegLists being walked, to stop on a cycle
        while stack:
            seg = next(stack[-1][0], _WALK_END)
            if seg is _WALK_END:
                open_ids.discard(stack.pop()[1])
                continue
            if isinstance(seg, ConcreteSeg):
                run.extend(walk(e) for e in seg.elements)
                continue
            # One step, not ``walk``: a hole bound to the next link of the
            # chain is walked HERE, on the stack.  ``walk`` would resolve it
            # through that link's ``__walk__``, which is the recursion.
            v = deref(seg.var)
            if type(v) is SegListView:
                v = v.elements()           # its elements, walked below as a list's
            if not isinstance(v, SegList):
                v = walk(v)
            if is_chars(v):
                v = chars_text(v)          # stage 1: a hole bound to the carrier is a str-bound hole
            if isinstance(v, str):
                run.extend(char_atom(c) for c in v)   # a substring: its CHARS
            elif isinstance(v, list):
                run.extend(v)
            elif isinstance(v, SegList):
                if id(v) in open_ids:
                    raise RecursionError("cyclic partial list")
                stack.append((iter(v._segments), id(v)))
                open_ids.add(id(v))
            else:
                # Either still an unbound Var (keep the hole) or bound to an
                # out-of-contract scalar. The latter left the term in silent
                # limbo — non-ground forever, every unify quietly failing
                # (A01-F009, mirroring the F024 char-list guard).
                if not is_var(v):
                    raise PartialTermError(
                        f"SegList VarSeg bound to non-sequence value: "
                        f"{type(v).__name__} ({v!r}); VarSegs of a SegList "
                        f"must bind to list/str."
                    )
                if run:
                    segs.append(ConcreteSeg(run))
                    run = []
                segs.append(VarSeg(v))
        # If no VarSegs remain, return a plain Python list of the elements.
        if not segs:
            return run
        if run:
            segs.append(ConcreteSeg(run))
        return SegList(segs)

    def __walk__(self):
        """Called by C do_walk. Normalise: collapse bound VarSegs, merge
        adjacent ConcreteSegs. Returns a plain Python list when fully ground
        — promoted to a ``str`` when every element is a CHAR (F018, the
        Liskov "strings-as-lists" rule).

        This is the OUTWARD-facing form. Code inside this class that needs
        the elements themselves uses :meth:`_walk_raw`; see its docstring for
        why reversing the promotion is not exact during Stage A.
        """
        w = self._walk_raw()
        if isinstance(w, list):
            from .logic.runtime._seg_helpers import maybe_promote_to_str
            return maybe_promote_to_str(w)
        return w

    def is_ground(self) -> bool:
        """True iff the term contains no unbound Var.

        Not just "all VarSeg holes filled": a ConcreteSeg *element* Var
        leaves the term non-ground too (A01-F006 / prior art F083). Delegate
        to the canonical recursive ground check, which already understands
        Seg* shapes and element Vars."""
        from .logic.builtins._helpers import _is_ground
        return _is_ground(self)

    def to_list(self) -> list:
        """Walk and flatten. Raises ``TypeError`` if not fully ground.

        Reads the elements via :meth:`_walk_raw`, so the F018 str promotion
        never has to be reversed: the elements come back exactly as the
        SegList held them.
        """
        w = self._walk_raw()
        if isinstance(w, list):
            return w
        raise TypeError(
            f"SegList is not ground: {w!r}"
        )

    # ── C extension protocol hooks ────────────────────────────────────────────

    def __occurs_check__(self, var) -> bool:
        """Called by C do_occurs_check. Recurse into all elements and var slots."""
        from .logic.variables import occurs_check
        for seg in self._segments:
            if isinstance(seg, ConcreteSeg):
                if any(occurs_check(var, e) for e in seg.elements):
                    return True
            else:
                if occurs_check(var, seg.var):
                    return True
        return False

    def __unify__(self, other, trail):
        """Called by C do_unify.  Against a list or text, unifies the holes
        through :func:`_drive_seg_unify` (see "Seg* __unify__ against a list
        or text" above :func:`_seg_split_gen`): exact for one hole; every
        split, as a pending goal, for two or more."""
        from .logic.variables import unify, walk
        # An EMPTY Seg IS the empty list, in every spelling (fix round 4,
        # item 5).  See ``_EMPTY_SEG_IS_NIL`` above this class for why this
        # sits ahead of the ``()`` rewrite and why it leaves VarSeg alone.
        if _is_nil(other) and _walked_nil(self._walk_raw()):
            return True
        # The empty TUPLE is the empty LIST (fix round 3, item 3): it is the
        # hashable nil spelling ``atoms.NIL_KEY`` uses, and the arms below
        # gate on ``list``/``str``/``bytes``, so ``()`` was rejected outright
        # while ``[]`` succeeded -- one term, two answers.  Rewritten to
        # ``[]``, the spelling every arm knows, and ONLY ``()``: rewriting
        # ``""``/``b""`` as well would move a same-type target off its own
        # arm and change what a VarSeg binds to (``[*A] = ""`` binds
        # ``A = ""``, not ``A = []``).
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_payload(other)   # stage 1: the carrier is the text it holds here (a str, or a view read by position)
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if isinstance(other, bytes):
            # Codes-model symmetry (A01-F007): the C layer unifies plain
            # int-lists with bytes, and SegBytes accepts list targets — so a
            # SegList of codes must accept a bytes target too. Convert to the
            # code list (list(b"GET") == [71, 69, 84]) and reuse the list path.
            return self.__unify__(list(other), trail)
        if isinstance(other, list) or other_text or type(other) is SegListView:
            # (A view is read in place, as the list it is: indexed and
            # sliced, never walked.)
            walked = self._walk_raw()
            if isinstance(walked, list):
                # No unbound *VarSeg* remains, but ConcreteSeg *element* Vars
                # can still be present (``_walk_raw`` returns a plain list as
                # soon as the holes are filled). Comparing with ``==`` would
                # treat those element Vars by identity and drop satisfiable
                # bindings (A01-F006), so delegate to real (Var-aware,
                # trail-restoring) unification. ``_walk_raw`` (not
                # ``__walk__``) hands back the SegList's OWN elements, so the
                # F018 promotion never has to be undone; only the ``other``
                # side needs splitting, into CHARS.
                if other_text:
                    other = [char_atom(c) for c in other]
                return unify(walked, other, trail)
            # Non-ground: every split that fits (_drive_seg_unify).
            # String targets pass through directly (list/str slicing both
            # yield the right shape).
            concrete_len = sum(len(s.elements) for s in walked.segments
                               if isinstance(s, ConcreteSeg))
            return _drive_seg_unify(walked, other, trail,
                                    concrete_len, _apply_seglist_split)
        if isinstance(other, SegList):
            if not all(isinstance(g, (ConcreteSeg, VarSeg))
                       for g in (*self._segments, *other._segments)):
                return NotImplemented   # not a SegList this class builds
            walked = self._walk_raw()
            other_walked = other._walk_raw()
            if not isinstance(walked, SegList) or not isinstance(other_walked, SegList):
                # One side walks to a plain list: the list arm above decides.
                return unify(walked, other_walked, trail)
            return _unify_open_seglists(walked, other_walked, trail)
        if _is_cons_cell(other):
            return _unify_seglist_cons(self._walk_raw(), other, trail)
        return NotImplemented

    # ── sequence protocol (partial-aware) ────────────────────────────────────
    #
    # F021/F022/F039 (audit 2026-05-25): on non-ground SegLists the old code
    # called ``to_list()`` which raised a bare ``TypeError`` — a sequence-
    # protocol crash propagating out of duck-typed callers (``len``, ``iter``,
    # ``in``). The current contract for partial SegLists returns a
    # *partial answer* drawn from the ConcreteSeg prefix/positions, so a
    # caller iterating an unknown SegList still sees every knowable element
    # without committing on the VarSeg holes. ``__contains__`` likewise
    # returns ``True`` conservatively for items that could legitimately live
    # in an unbound VarSeg — a definite ``False`` on a satisfiable goal is
    # the worst-case silent incompleteness flagged by F022.
    #
    # The walked ConcreteSegs are flattened in order; an unbound VarSeg is
    # treated as an opaque gap (skipped during iteration / length counting).
    # Negative or partial indices into the gap raise ``PartialTermError``
    # rather than IndexError, so callers can distinguish "out of known prefix"
    # from "out of bounds".

    def _concrete_prefix(self) -> tuple[list, bool]:
        """Return (concrete_elements, has_var_seg) for the walked SegList.

        Used by the partial-aware sequence protocol. ``concrete_elements`` is
        the flat list of every element drawn from ConcreteSegs in segment
        order; ``has_var_seg`` is True iff at least one VarSeg remains
        unbound after walking.
        """
        w = self._walk_raw()
        if isinstance(w, list):
            return w, False
        elements: list = []
        has_var = False
        for seg in w._segments:
            if isinstance(seg, ConcreteSeg):
                elements.extend(seg.elements)
            else:
                has_var = True
        return elements, has_var

    def __len__(self) -> int:
        # Ground: exact length via the walked list.
        # Non-ground: the *minimum* knowable length (sum of ConcreteSeg
        # lengths). VarSegs contribute zero or more — the true length is
        # ``>= __len__``. Python's ``len()`` requires a non-negative int, so
        # we cannot represent the uncertainty here; the conservative lower
        # bound is the contract.
        elements, _ = self._concrete_prefix()
        return len(elements)

    def __iter__(self):
        # Ground: iterate the walked list.
        # Non-ground: yield every ConcreteSeg element in order, skipping
        # VarSeg gaps. Callers get the knowable prefix without a crash.
        elements, _ = self._concrete_prefix()
        return iter(elements)

    def __contains__(self, item) -> bool:
        # ``_walk_raw``: membership is over the SegList's OWN elements, so a
        # SegList of cell chars answers True for ``("a",)`` rather than for
        # the raw ``"a"`` the F018 promotion would have decoded to.
        w = self._walk_raw()
        if isinstance(w, list):
            return item in w
        # Non-ground: True if the item is in any ConcreteSeg; otherwise
        # *also* True conservatively when an unbound VarSeg remains
        # (it could be bound to a list containing the item). Only
        # definitively False when every segment is concrete and the item
        # is absent from all of them — the walked form would have been
        # a plain list in that case, so reaching here with no VarSeg is
        # unreachable, but we keep the branch for defensiveness.
        has_var = False
        for seg in w._segments:
            if isinstance(seg, ConcreteSeg):
                if item in seg.elements:
                    return True
            else:
                has_var = True
        return has_var

    def __getitem__(self, index):
        # Ground: normal list indexing.
        # Non-ground: index into the concrete prefix. If the requested
        # index falls within the concrete prefix we can return it; otherwise
        # raise PartialTermError so the caller can distinguish "known
        # absent" from "unknown until bound".
        # ``_walk_raw``: indexing yields the element the SegList holds.
        w = self._walk_raw()
        if isinstance(w, list):
            return w[index]
        elements: list = []
        for seg in w._segments:
            if isinstance(seg, ConcreteSeg):
                elements.extend(seg.elements)
            else:
                # Hit an unbound VarSeg before exhausting the requested
                # index — the value at ``index`` depends on the VarSeg's
                # eventual binding. We can still satisfy non-negative
                # indices that land within the prefix already collected.
                if isinstance(index, int) and 0 <= index < len(elements):
                    return elements[index]
                # A forward slice bounded entirely within the collected
                # prefix is fully knowable even though a VarSeg follows
                # (A01-F010). Negative/open-ended/reverse slices still
                # depend on the VarSeg and keep raising.
                if _slice_within_prefix(index, len(elements)):
                    return elements[index]
                raise PartialTermError(
                    f"SegList[{index!r}] requires resolving an unbound "
                    f"VarSeg; only the concrete prefix (indices "
                    f"0..{len(elements) - 1}) is knowable. SegList={self!r}"
                )
        # All concrete — but _walk_raw would have returned a list, so this
        # branch is mostly unreachable. Fall through to normal indexing.
        return elements[index]

    def __add__(self, other):
        """Lazy concatenation — returns a new SegList.

        F020 fix: ``str`` is accepted as a char-list tail under
        the Liskov "strings-as-lists" rule. ``SegList(['a','b']) + 'cd'``
        produces ``SegList(['a','b','c','d'])`` shape.
        """
        if isinstance(other, list):
            return SegList(self._segments + [ConcreteSeg(other)])
        if isinstance(other, str):
            # F020: Liskov — str is a list of CHARS.
            return SegList(
                self._segments + [ConcreteSeg([char_atom(c) for c in other])])
        if isinstance(other, SegList):
            return SegList(self._segments + other._segments)
        return NotImplemented

    def __radd__(self, other):
        """F020 fix: accept ``str`` as a char-list head."""
        if isinstance(other, list):
            return SegList([ConcreteSeg(other)] + self._segments)
        if isinstance(other, str):
            return SegList(
                [ConcreteSeg([char_atom(c) for c in other])] + self._segments)
        return NotImplemented

    def __eq__(self, other):
        # The empty TUPLE is the empty LIST (fix round 3, item 3), and the
        # arms below accept list/str/bytes only.
        if _is_nil(other) and _walked_nil(self._walk_raw()):
            return True          # fix round 4, item 5 — see _EMPTY_SEG_IS_NIL
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_text(other)      # stage 1: the carrier is the str it holds here
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if type(other) is SegListView:
            return other == self        # compared by elements (SegListView.__eq__)
        if isinstance(other, SegList):
            return self._segments == other._segments
        if isinstance(other, list):
            # ``_walk_raw``: compare the SegList's OWN elements. Going via
            # ``__walk__`` would compare a decoding of the F018 promotion,
            # which under Stage A cannot reproduce a cell char.
            w = self._walk_raw()
            if isinstance(w, list):
                return w == other
            return False
        if other_text:
            # Symmetric with SegString — str unifies with char-list at runtime,
            # so equality should hold when the SegList walks to a char list.
            # Compared by SPELLING, so both char shapes answer alike.
            w = self._walk_raw()
            if isinstance(w, list) and all(is_char_atom(c) for c in w):
                return "".join(spelling(c) for c in w) == other
            return False
        if isinstance(other, SegString):
            # Walk both and compare under the strings-as-lists contract.
            w_self = self._walk_raw()
            w_other = other.__walk__()
            if isinstance(w_self, list) and isinstance(w_other, str):
                return (
                    all(is_char_atom(c) for c in w_self)
                    and "".join(spelling(c) for c in w_self) == w_other
                )
            # Both non-ground (or mixed walks) — fall back to NotImplemented so
            # Python can try the right-hand side's __eq__.
            return NotImplemented
        return NotImplemented

    def __hash__(self):
        # F025 / Phase 2 Task 13 revision (user-confirmed):
        # SegList is *unconditionally* unhashable — matching Python's
        # ``list`` (also unhashable). The previous Task 5 contract
        # (hashable when ground, structurally hashable when non-ground)
        # over-specified the rule. Under the Liskov "strings-as-lists"
        # model the hashing behaviour of a Clausal-side seg container
        # is undefined; if a caller needs to hash a ground SegList they
        # can convert via ``to_list()`` / ``list(...)`` first.
        raise TypeError("unhashable type: 'SegList'")

    def __repr__(self) -> str:
        parts = []
        for seg in self._segments:
            if isinstance(seg, ConcreteSeg):
                parts.extend(repr(e) for e in seg.elements)
            else:
                parts.append(f"*{seg.var!r}")
        return f"[{', '.join(parts)}]"


# ── The rest of a list, as a window of it ─────────────────────────────────────
#
# Matching ``[H|T]`` against a list bound ``T`` to a fresh copy of the rest,
# and the choice points of a parse kept every copy alive: walking a list of n
# tokens -- a DCG over a token list, a clause head ``[a|T]`` recursing down it
# -- copied about n^2/2 elements and held them.  A long rest of a list is now
# a VIEW of the same list (the twin of the text view, ``cells._Text``):
# ``SegListView(base, lo, hi)`` reads ``base[lo:hi]``, and taking its rest
# again makes another view of the same base.
#
# A view holds the same element objects a slice would (a slice is shallow:
# a Var in it is the same Var), so it is the same term as the copy.  And it
# IS a ``SegList`` -- a partial list whose holes are all filled -- so every
# reader that does not know it reads it as one: its ``_segments`` is built on
# demand as ``[ConcreteSeg(base[lo:hi])]``, and the C walkers (ground/1,
# copy_term/2, term_variables/2) read that.  Only the head-match fast paths
# (``list_unify`` and its C twin), ``__unify__`` and the walk read the window
# itself.

LIST_VIEW_MIN = 64      # a shorter rest is copied, as before (twin: LIST_VIEW_MIN in C)


def list_rest(d, lo, hi):
    """``d[lo:hi]`` for a list or a :class:`SegListView` *d*, as the term a
    hole binds to: a view of the same base when it is long, else a fresh
    list.  The caller checked ``0 <= lo <= hi <= len(d)``."""
    if type(d) is SegListView:
        if hi - lo >= LIST_VIEW_MIN:
            return SegListView(d._base, d._lo + lo, d._lo + hi)
        return d._base[d._lo + lo:d._lo + hi]
    if hi - lo >= LIST_VIEW_MIN:
        return SegListView(d, lo, hi)
    return d[lo:hi]


class SegListView(SegList):
    """The elements ``base[lo:hi]`` of a list, read in place.  See "The rest
    of a list, as a window of it" above.  Equal to, and unifies as, the list
    of its elements; walks to that list (a fresh copy).  Its window is
    read-only."""

    __slots__ = ("_base", "_lo", "_hi", "_mat")

    def __new__(cls, *args):
        # ``type(t)(segments)`` is how a copier rebuilds a Seg* from its
        # copied segments (copy_term/2's C walker among them): for a view
        # that is a plain SegList of the copied elements.
        if len(args) == 1:
            return SegList(args[0])
        return object.__new__(cls)

    def __init__(self, base, lo, hi):
        if type(base) is not list or not 0 <= lo <= hi <= len(base):
            raise TypeError("SegListView needs a list and 0 <= lo <= hi <= len")
        self._base = base
        self._lo = lo
        self._hi = hi
        self._mat = None

    base = property(lambda self: self._base)
    lo = property(lambda self: self._lo)
    hi = property(lambda self: self._hi)

    def __reduce__(self):
        # A copy or a pickle holds the window's elements, not the base.
        return (list, (self.elements(),))

    @property
    def _segments(self):
        # Every reader that does not know a view reads a filled partial
        # list: ONE ConcreteSeg of a plain list, built once.
        m = self._mat
        if m is None:
            m = self._mat = [ConcreteSeg(self.elements())]
        return m

    @property
    def segments(self) -> list:
        return list(self._segments)

    def elements(self) -> list:
        """The elements, as a fresh list."""
        if self._hi > len(self._base):
            raise PartialTermError("the list under a SegListView shrank")
        return self._base[self._lo:self._hi]

    def _walk_raw(self):
        from .logic.variables import walk
        return walk(self.elements())

    def __walk__(self):
        # A list, as the rest of a list always walked: no F018 promotion
        # (walking a plain list does not promote it to text).
        from .logic.variables import walk
        return walk(self.elements())

    def __len__(self) -> int:
        return self._hi - self._lo

    def __iter__(self):
        return iter(self.elements())

    def __getitem__(self, index):
        n = self._hi - self._lo
        if self._hi > len(self._base):
            raise PartialTermError("the list under a SegListView shrank")
        if isinstance(index, slice):
            lo, hi, step = index.indices(n)
            if step == 1:
                return list_rest(self, lo, max(lo, hi))
            return self.elements()[index]
        if index < 0:
            index += n
        if not 0 <= index < n:
            raise IndexError("SegListView index out of range")
        return self._base[self._lo + index]

    def _same_window(self, other):
        return (other._base is self._base and other._lo == self._lo
                and other._hi == self._hi)

    def __eq__(self, other):
        if type(other) is SegListView:
            return self._same_window(other) or (
                len(other) == len(self) and other.elements() == self.elements())
        if type(other) is list:
            return len(other) == len(self) and other == self.elements()
        if isinstance(other, SegList):
            # A partial list spelled with other segments: compare elements.
            return self._walk_raw() == other._walk_raw()
        return SegList.__eq__(self, other)

    __hash__ = SegList.__hash__

    def __unify__(self, other, trail):
        from .logic.variables import unify
        if type(other) is SegListView:
            if self._same_window(other):
                return True
            if len(other) != len(self):
                return False
            return unify(self.elements(), other.elements(), trail)
        if type(other) is list:
            if len(other) != len(self):
                return False
            return unify(self.elements(), other, trail)
        if _is_nil(other):
            return False            # a view is never empty (LIST_VIEW_MIN)
        if type(other) is SegList:
            # A partial list against a view: the pattern takes the view as
            # its list target, read in place (``SegList.__unify__``), rather
            # than both being walked here.
            return other.__unify__(self, trail)
        return SegList.__unify__(self, other, trail)

    def __repr__(self) -> str:
        return repr(self.elements())


def _seglist_unify_gen(seglist, target_list, trail):
    """Non-deterministic generator: yield True for each valid split of
    *target_list* across the VarSegs of *seglist*.

    *seglist* must already be walk()-normalised (i.e. a SegList, not a plain
    list).  *target_list* must be a plain Python list.
    """
    from .logic.variables import unify
    min_len = sum(len(s.elements) for s in seglist.segments
                  if isinstance(s, ConcreteSeg))
    n = len(target_list)
    if n < min_len:
        return
    # A ``str`` target is a char list: its ELEMENTS are chars, its SLICES
    # stay str (R-S2). Twin of ``_seg_helpers.seq_getitem``.
    target_is_str = type(target_list) is str
    n_stars = sum(1 for s in seglist.segments if isinstance(s, VarSeg))
    remainder = n - min_len
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0
        for seg in seglist.segments:
            if isinstance(seg, VarSeg):
                sz = split[si]; si += 1
                ok = ok and unify(seg.var, _seg_slice_out(target_list[pos:pos + sz]), trail)
                pos += sz
            else:
                for elem in seg.elements:
                    if pos >= len(target_list):
                        ok = False
                        break
                    at = (char_atom(target_list[pos]) if target_is_str
                          else target_list[pos])
                    ok = ok and unify(elem, at, trail)
                    pos += 1
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)


def _multi_star_splits(n_stars: int, remainder: int):
    """Yield all weak compositions of *remainder* into *n_stars* parts
    (each bucket ≥ 0). Equivalent to the ``_multi_star_splits`` in
    ``compiler.py`` but lives here so runtime code can import it
    without circular imports.

    Implementation note: iterative depth-first traversal over a shared
    ``buf`` list, yielding a fresh tuple per step. Tuples are yielded
    in the same lexicographic order as the previous recursive
    ``(first,) + rest`` formulation, but without the O(n_stars) tuple
    concatenation per yield and without the deep generator-chaining
    overhead. The hot inner loop (incrementing the second-to-last
    bucket while the last bucket can still donate one unit) is a
    constant-work fast path; backtracking deeper into the buffer only
    happens once per fully-consumed inner row. See F026 in the
    2026-05-25 string-implementation audit.
    """
    if n_stars == 0:
        if remainder == 0:
            yield ()
        return
    if n_stars == 1:
        yield (remainder,)
        return
    buf = [0] * n_stars
    rem_at = [0] * n_stars
    rem_at[0] = remainder
    last = n_stars - 1
    last_m1 = last - 1
    # Initial descent — set every bucket except the last to 0, propagating
    # the running remainder so ``rem_at[i]`` is the budget available to
    # ``buf[i..last]`` given the chosen ``buf[0..i-1]``.
    idx = 0
    while idx < last:
        idx += 1
        rem_at[idx] = rem_at[idx - 1] - buf[idx - 1]
    while True:
        # ``buf[last]`` is whatever is left after the prefix; emit.
        buf[last] = rem_at[last_m1] - buf[last_m1]
        yield tuple(buf)
        # Fast path: walk the second-to-last bucket through 0..rem_at[last_m1]
        # without re-descending. This handles the common case where only the
        # last two positions vary between successive splits.
        if buf[last_m1] < rem_at[last_m1]:
            buf[last_m1] += 1
            continue
        # Inner row exhausted. Backtrack to find the next prefix that can
        # be incremented, then redescend (zeroing the right-tail buckets
        # and refreshing their ``rem_at`` budgets).
        idx = last_m1 - 1
        while idx >= 0 and buf[idx] >= rem_at[idx]:
            idx -= 1
        if idx < 0:
            return
        buf[idx] += 1
        idx += 1
        while idx <= last_m1:
            rem_at[idx] = rem_at[idx - 1] - buf[idx - 1]
            buf[idx] = 0
            idx += 1


# ── SegString — segmented partial string ──────────────────────────────────────


class SegString:
    """A SegList-like term backed by string segments instead of list segments.

    Segments are plain ``str`` objects (concrete text) alternating with
    ``VarSeg`` objects (variable-length string holes).  when every VarSeg is
    bound to a string, ``__walk__`` returns a plain Python ``str``.

    Example::

        SegString(["hel", VarSeg(X), "ld"])

    when ``X`` is bound to ``"lo wor"``, walking yields ``"hello world"``.
    VarSegs always bind to ``str`` (substrings), never char lists.
    """

    __slots__ = ("_segments",)

    def __init__(self, segments: list):
        # F024 (audit 2026-05-25): precondition-check segment shapes at
        # construction time. The SegString contract permits only ``str``
        # literals and ``VarSeg`` holes. Accepting other types (ints,
        # nested lists, …) silently rots through to ``__walk__`` / ``eq``
        # / ``hash`` / ``unify`` and surfaces as a confusing bare
        # ``TypeError`` from deep inside CPython. Reject early with a
        # typed clausal exception so the caller learns about the
        # malformed segment at construction, not three call frames away.
        for i, seg in enumerate(segments):
            if not isinstance(seg, (str, VarSeg)):
                raise PartialTermError(
                    f"SegString segment [{i}] is {type(seg).__name__} "
                    f"({seg!r}); expected str or VarSeg. SegString accepts "
                    f"only string literals and variable-length holes."
                )
        self._segments = list(segments)

    @property
    def segments(self) -> list:
        return self._segments

    # ── Walk / normalisation ──────────────────────────────────────────────────

    def __walk__(self):
        """Called by C do_walk.  The OUTWARD form: a ground SegString walks to
        the chars CARRIER (stage 1 of the atoms-as-str flip, spec
        2026-09-18), a non-ground one to a normalised SegString.  Code inside
        this class that needs the bare text uses :meth:`_walk_raw`."""
        w = self._walk_raw()
        return chars(w) if type(w) is str else w

    def _walk_raw(self):
        """Normalise: collapse bound VarSegs, merge adjacent strings.
        Returns a plain ``str`` when fully ground (the INTERNAL form)."""
        from .logic.variables import walk
        new_segs: list = []
        for seg in self._segments:
            if isinstance(seg, str):
                if new_segs and isinstance(new_segs[-1], str):
                    new_segs[-1] = new_segs[-1] + seg
                else:
                    new_segs.append(seg)
            else:  # VarSeg
                v = walk(seg.var)
                if is_chars(v):
                    v = chars_text(v)          # stage 1: a hole bound to the carrier
                if isinstance(v, str):
                    if new_segs and isinstance(new_segs[-1], str):
                        new_segs[-1] = new_segs[-1] + v
                    else:
                        new_segs.append(v)
                elif isinstance(v, list):
                    # VarSeg bound to a char list — join the chars'
                    # SPELLINGS into a string.
                    # F024 (audit 2026-05-25): validate every element is a
                    # CHAR before delegating to ``str.join`` so the
                    # malformed-segment case raises a typed clausal
                    # ``PartialTermError`` instead of leaking the raw
                    # ``TypeError: sequence item N: expected str instance,
                    # ... found`` from deep inside CPython. The leaked
                    # exception propagates through every method that
                    # touches ``__walk__`` (eq, hash, repr, unify,
                    # is_ground) and gives no signal that the SegString's
                    # VarSeg binding violates the char-list contract.
                    for i, elem in enumerate(v):
                        if not is_char_atom(elem):
                            raise PartialTermError(
                                f"SegString VarSeg bound to a non-char-list: "
                                f"element [{i}] is {type(elem).__name__} "
                                f"({elem!r}), expected a char. "
                                f"Full binding: {v!r}"
                            )
                    s = "".join(spelling(c) for c in v)
                    if new_segs and isinstance(new_segs[-1], str):
                        new_segs[-1] = new_segs[-1] + s
                    else:
                        new_segs.append(s)
                elif isinstance(v, SegString):
                    walked_inner = v._walk_raw()
                    if isinstance(walked_inner, str):
                        if new_segs and isinstance(new_segs[-1], str):
                            new_segs[-1] = new_segs[-1] + walked_inner
                        else:
                            new_segs.append(walked_inner)
                    else:
                        for inner_seg in walked_inner._segments:
                            if isinstance(inner_seg, str):
                                if new_segs and isinstance(new_segs[-1], str):
                                    new_segs[-1] = new_segs[-1] + inner_seg
                                else:
                                    new_segs.append(inner_seg)
                            else:
                                new_segs.append(inner_seg)
                else:
                    # Either still an unbound Var (keep the hole) or bound to
                    # an out-of-contract scalar — the latter left the term in
                    # silent limbo (A01-F009, mirroring the F024 char-list
                    # guard above).
                    from .logic.variables import is_var
                    if not is_var(v):
                        raise PartialTermError(
                            f"SegString VarSeg bound to non-str value: "
                            f"{type(v).__name__} ({v!r}); VarSegs of a "
                            f"SegString must bind to str."
                        )
                    new_segs.append(VarSeg(v))

        # If no VarSegs remain, return a plain str
        if all(isinstance(s, str) for s in new_segs):
            return "".join(new_segs)

        # Clean up empty strings
        new_segs = [s for s in new_segs if not (isinstance(s, str) and not s)]
        if not new_segs:
            return ""
        return SegString(new_segs)

    def is_ground(self) -> bool:
        """True if all VarSegs are bound — i.e. ``__walk__`` returns ``str``."""
        return isinstance(self._walk_raw(), str)

    def to_str(self) -> str:
        """Walk and join. Raises ``TypeError`` if not fully ground."""
        w = self._walk_raw()
        if isinstance(w, str):
            return w
        raise TypeError(f"SegString is not ground: {w!r}")

    # ── C extension protocol hooks ────────────────────────────────────────────

    def __occurs_check__(self, var) -> bool:
        """Called by C do_occurs_check."""
        from .logic.variables import occurs_check
        for seg in self._segments:
            if isinstance(seg, VarSeg) and occurs_check(var, seg.var):
                return True
        return False

    def __unify__(self, other, trail):
        """Called by C do_unify.

        Against text: unifies the holes through :func:`_drive_seg_unify`
        (mirror of :meth:`SegList.__unify__`).
        Against ``list``: convert string segments to char elements and
        delegate.
        """
        from .logic.variables import unify
        # An EMPTY Seg IS the empty list, in every spelling (fix round 4,
        # item 5).  See ``_EMPTY_SEG_IS_NIL``, above ``class SegList``.
        if _is_nil(other) and _walked_nil(self._walk_raw()):
            return True
        # The empty TUPLE is the empty LIST (fix round 3, item 3): it is the
        # hashable nil spelling ``atoms.NIL_KEY`` uses, and the arms below
        # gate on ``list``/``str``/``bytes``, so ``()`` was rejected outright
        # while ``[]`` succeeded -- one term, two answers.  Rewritten to
        # ``[]``, the spelling every arm knows, and ONLY ``()``: rewriting
        # ``""``/``b""`` as well would move a same-type target off its own
        # arm and change what a VarSeg binds to (``[*A] = ""`` binds
        # ``A = ""``, not ``A = []``).
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_text(other)      # stage 1: the carrier is the str it holds here
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if other_text:
            walked = self._walk_raw()
            if isinstance(walked, str):
                return walked == other
            # Non-ground: every split that fits (_drive_seg_unify).
            concrete_len = sum(len(s) for s in walked.segments
                               if isinstance(s, str))
            return _drive_seg_unify(walked, other, trail,
                                    concrete_len, _apply_segstring_split)
        if isinstance(other, list):
            # A ground SegString walks to a ``str``, and THE FLIP
            # (2026-09-06-atoms-as-cells-strings §6.2) reinstated the
            # str↔list arm in ``do_unify``: a ``str`` IS the list of its
            # char atoms.  So the ground case delegates straight back to
            # ``unify`` and the C arm does the work — no materialisation of
            # a char list here, which is what R-S2 (efficient
            # representations, always) asks for.  P3-1 had retired that arm,
            # which is why this branch used to build the list itself.
            walked = self._walk_raw()
            if isinstance(walked, str):
                return unify(chars(walked), other, trail)   # STAGE 2: the text, not a bare str atom
            # F023 (audit 2026-05-25): non-ground SegString vs list — the
            # old branch returned ``NotImplemented`` which the C top-level
            # unify treats as "no protocol match → False", silently
            # dropping logically-satisfiable goals like
            # ``unify(SegString(['a', VarSeg(X), 'c']), ['a','b','c'])``.
            # The companion ``SegList.__unify__(str)`` already routes
            # through ``_seglist_unify_gen`` against the string; build the
            # SegList equivalent (str segments → ConcreteSeg-of-chars,
            # VarSegs preserved) and delegate so the SegString-vs-list
            # path picks up the same generator-driven enumeration.
            equivalent_segs: list = []
            for seg in walked._segments:
                if isinstance(seg, str):
                    equivalent_segs.append(
                        ConcreteSeg([char_atom(c) for c in seg]))
                else:  # VarSeg
                    equivalent_segs.append(seg)
            return SegList(equivalent_segs).__unify__(other, trail)
        if isinstance(other, (SegString, SegList)):
            # STAGE 1: a ground side resolves the pair itself.  Both used to
            # walk to a bare str and meet in the C fallback's ``==``; now a
            # ground text Seg* walks to the CARRIER, and that fallback refuses
            # every tuple, so the pair has to be re-entered through ``unify``
            # with the ground side in its walked form (the other Seg's own
            # str/list arm then reads it).
            w = self._walk_raw()
            if isinstance(w, str):
                return unify(chars(w), other, trail)
            ow = other.__walk__()
            if not isinstance(ow, (SegString, SegList)):
                return self.__unify__(ow, trail)
            return NotImplemented
        return NotImplemented

    # ── sequence protocol (partial-aware) ────────────────────────────────────
    #
    # F038/F039 (audit 2026-05-25): SegString previously defined no
    # ``__iter__``, so even a *ground* ``SegString(["abc"])`` raised
    # ``TypeError: 'SegString' object is not iterable`` when handed to
    # ``iter(collection)`` (e.g. via ``_in_iter`` for body-position
    # ``elem in coll`` goals). The new sequence protocol mirrors the
    # partial-aware SegList contract: ground SegStrings iterate their
    # walked ``str`` as chars; non-ground SegStrings expose the concrete
    # prefix from str segments, treating VarSegs as opaque gaps.

    def _concrete_prefix(self) -> tuple[str, bool]:
        """Return (concrete_chars, has_var_seg) for the walked SegString.

        ``concrete_chars`` concatenates every ``str`` segment in segment
        order; ``has_var_seg`` is True iff at least one VarSeg remains
        unbound after walking.
        """
        w = self._walk_raw()
        if isinstance(w, str):
            return w, False
        parts: list = []
        has_var = False
        for seg in w._segments:
            if isinstance(seg, str):
                parts.append(seg)
            else:
                has_var = True
        return "".join(parts), has_var

    def __len__(self) -> int:
        # Ground: exact length of the walked str.
        # Non-ground: minimum length (sum of concrete str segments).
        # See SegList.__len__ — same conservative-lower-bound contract.
        chars, _ = self._concrete_prefix()
        return len(chars)

    def __iter__(self):
        # Ground: iterate the walked str as its CHAR ATOMS — a string is the
        # list of char atoms it denotes (THE FLIP, spec §6.2), so iterating
        # it must yield the same elements iterating that list does, and
        # ``X in "abc"`` binds ``X = ("a",)``.  Python's ``iter(str)``
        # yields 1-char ``str``s, which are one-element STRINGS here and
        # would be the wrong elements.
        # Non-ground: yield the concrete chars from str segments in
        # order, skipping VarSeg gaps.
        chars, _ = self._concrete_prefix()
        return iter([char_atom(c) for c in chars])

    def __contains__(self, item) -> bool:
        # Membership is over the ELEMENTS of the list this string denotes,
        # so the item that can be found is a CHAR ATOM (THE FLIP, §6.2) —
        # matching ``__iter__`` above and ``member/2`` on a plain ``str``.
        # A string item (``"ab" in "abc"``) is a substring question, not a
        # membership one, and is False here as it is for a list.
        if not is_char_atom(item):
            return False
        ch = spelling(item)
        w = self._walk_raw()
        if isinstance(w, str):
            return ch in w
        # Non-ground: True if the char is in any concrete str segment.
        # If absent but a VarSeg remains, return True conservatively
        # (the char could be bound inside the VarSeg). See SegList
        # for the same satisfiable-membership rule.
        has_var = False
        for seg in w._segments:
            if isinstance(seg, str):
                if ch in seg:
                    return True
            else:
                has_var = True
        return has_var

    def __getitem__(self, index):
        # An INT index selects one element of the list this string denotes —
        # a char atom (THE FLIP, §6.2).  A SLICE selects a sub-list, which
        # for a string is a ``str`` slice (R-S2: the tail of a string stays
        # a string, never expands).
        w = self._walk_raw()
        if isinstance(w, str):
            return char_atom(w[index]) if isinstance(index, int) else chars(w[index])
        char_buf: list[str] = []
        for seg in w._segments:
            if isinstance(seg, str):
                char_buf.extend(seg)
            else:
                if isinstance(index, int) and 0 <= index < len(char_buf):
                    return char_atom(char_buf[index])
                # In-prefix forward slice is knowable (A01-F010); return a
                # str to match ground SegString slicing.
                if _slice_within_prefix(index, len(char_buf)):
                    return chars("".join(char_buf)[index])
                raise PartialTermError(
                    f"SegString[{index!r}] requires resolving an unbound "
                    f"VarSeg; only the concrete prefix (indices "
                    f"0..{len(char_buf) - 1}) is knowable. SegString={self!r}"
                )
        prefix = "".join(char_buf)
        return char_atom(prefix[index]) if isinstance(index, int) else chars(prefix[index])

    def __repr__(self):
        return f"SegString({self._segments!r})"

    def __eq__(self, other):
        # The empty TUPLE is the empty LIST (fix round 3, item 3), and the
        # arms below accept list/str/bytes only.
        if _is_nil(other) and _walked_nil(self._walk_raw()):
            return True          # fix round 4, item 5 — see _EMPTY_SEG_IS_NIL
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_text(other)      # stage 1: the carrier is the str it holds here
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if isinstance(other, SegString):
            return self._segments == other._segments
        if other_text:
            w = self._walk_raw()
            return w == other if isinstance(w, str) else False
        if isinstance(other, list):
            # Symmetric with SegList — char-list unifies with str at runtime.
            w = self._walk_raw()
            if isinstance(w, str):
                return (
                    all(is_char_atom(c) for c in other)
                    and w == "".join(spelling(c) for c in other)
                )
            return False
        if isinstance(other, SegList):
            # Delegate to SegList's bidirectional handling for symmetry.
            return other.__eq__(self)
        return NotImplemented

    def __hash__(self):
        # F017 / Phase 2 Task 13 revision (user-confirmed):
        # SegString is *unconditionally* unhashable, symmetric with
        # SegList (and with Python's ``list``). The previous Task 5
        # contract (hashable when ground, structurally hashable when
        # non-ground) over-specified the rule; the Python eq/hash
        # invariant is trivially satisfied here because no SegString
        # instance is ever hashable. Callers needing hashability for a
        # ground SegString can convert via ``to_str()`` / ``str(...)``.
        raise TypeError("unhashable type: 'SegString'")


def _segstring_unify_gen(segstring, target_str, trail):
    """Non-deterministic generator: yield True for each valid split of
    *target_str* across the VarSegs of *segstring*.

    *segstring* must be a walked (non-ground) SegString.
    *target_str* must be a plain Python str.
    """
    from .logic.variables import unify
    min_len = sum(len(s) for s in segstring.segments if isinstance(s, str))
    n = len(target_str)
    if n < min_len:
        return
    n_stars = sum(1 for s in segstring.segments if isinstance(s, VarSeg))
    remainder = n - min_len
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0
        for seg in segstring.segments:
            if isinstance(seg, VarSeg):
                sz = split[si]; si += 1
                ok = ok and unify(seg.var, chars(target_str[pos:pos + sz]), trail)   # stage 1
                pos += sz
            else:  # str
                end = pos + len(seg)
                if target_str[pos:end] != seg:
                    ok = False
                pos = end
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)


# ── SegBytes — segmented byte string ─────────────────────────────────────────


class SegBytes:
    """A segmented byte string: concrete ``bytes`` literals alternating with
    ``VarSeg`` holes. The codes-model analog of :class:`SegString`.

    VarSegs bind to ``bytes`` substrings (never int-lists, never ``str``).
    Ground SegBytes walk to a plain ``bytes`` object; the int-code list is
    only what it *unifies-with*, preserving ``.decode()``/``.hex()``/identity.
    """

    __slots__ = ("_segments",)

    def __init__(self, segments: list):
        # Mirror SegString.__init__ (F024): the SegBytes contract permits
        # only ``bytes`` literals and ``VarSeg`` holes. Reject anything else
        # at construction with a typed clausal exception.
        for i, seg in enumerate(segments):
            if not isinstance(seg, (bytes, VarSeg)):
                raise PartialTermError(
                    f"SegBytes segment [{i}] is {type(seg).__name__} "
                    f"({seg!r}); expected bytes or VarSeg. SegBytes accepts "
                    f"only bytes literals and variable-length holes."
                )
        self._segments = list(segments)

    @property
    def segments(self):
        return self._segments

    def __walk__(self):
        """Normalise: collapse bound VarSegs, merge adjacent bytes. Returns a
        plain ``bytes`` when fully ground."""
        from .logic.variables import walk
        new_segs: list = []
        for seg in self._segments:
            if isinstance(seg, bytes):
                if new_segs and isinstance(new_segs[-1], bytes):
                    new_segs[-1] = new_segs[-1] + seg
                else:
                    new_segs.append(seg)
            else:  # VarSeg
                v = walk(seg.var)
                if isinstance(v, bytes):
                    if new_segs and isinstance(new_segs[-1], bytes):
                        new_segs[-1] = new_segs[-1] + v
                    else:
                        new_segs.append(v)
                elif isinstance(v, list):
                    # VarSeg bound to an int-code list — join into bytes.
                    # Mirror SegString's char-list guard (F024): validate the
                    # codes domain before bytes(...) so a malformed binding
                    # raises a typed PartialTermError, not a bare ValueError.
                    for i, elem in enumerate(v):
                        if not (isinstance(elem, int) and not isinstance(elem, bool)
                                and 0 <= elem <= 255):
                            raise PartialTermError(
                                f"SegBytes VarSeg bound to a non-byte-list: "
                                f"element [{i}] is {type(elem).__name__} "
                                f"({elem!r}), expected int in [0, 255]. "
                                f"Full binding: {v!r}"
                            )
                    b = bytes(v)
                    if new_segs and isinstance(new_segs[-1], bytes):
                        new_segs[-1] = new_segs[-1] + b
                    else:
                        new_segs.append(b)
                elif isinstance(v, SegBytes):
                    walked_inner = v.__walk__()
                    if isinstance(walked_inner, bytes):
                        if new_segs and isinstance(new_segs[-1], bytes):
                            new_segs[-1] = new_segs[-1] + walked_inner
                        else:
                            new_segs.append(walked_inner)
                    else:
                        for inner_seg in walked_inner._segments:
                            if isinstance(inner_seg, bytes):
                                if new_segs and isinstance(new_segs[-1], bytes):
                                    new_segs[-1] = new_segs[-1] + inner_seg
                                else:
                                    new_segs.append(inner_seg)
                            else:
                                new_segs.append(inner_seg)
                else:
                    # Either still an unbound Var (keep the hole) or bound to
                    # an out-of-contract scalar — the latter left the term in
                    # silent limbo (A01-F009, mirroring the F024 byte-list
                    # guard above).
                    from .logic.variables import is_var
                    if not is_var(v):
                        raise PartialTermError(
                            f"SegBytes VarSeg bound to non-bytes value: "
                            f"{type(v).__name__} ({v!r}); VarSegs of a "
                            f"SegBytes must bind to bytes or a list of byte codes."
                        )
                    new_segs.append(VarSeg(v))

        if all(isinstance(s, bytes) for s in new_segs):
            return b"".join(new_segs)
        new_segs = [s for s in new_segs if not (isinstance(s, bytes) and not s)]
        if not new_segs:
            return b""
        return SegBytes(new_segs)

    def _concrete_prefix(self) -> tuple[bytes, bool]:
        """Return (concrete_bytes, has_var_seg) for the walked SegBytes."""
        w = self.__walk__()
        if isinstance(w, bytes):
            return w, False
        parts: list = []
        has_var = False
        for seg in w._segments:
            if isinstance(seg, bytes):
                parts.append(seg)
            else:
                has_var = True
        return b"".join(parts), has_var

    def is_ground(self) -> bool:
        """True if all VarSegs are bound — i.e. ``__walk__`` returns ``bytes``."""
        return isinstance(self.__walk__(), bytes)

    def __occurs_check__(self, var) -> bool:
        """Called by C do_occurs_check."""
        from .logic.variables import occurs_check
        for seg in self._segments:
            if isinstance(seg, VarSeg) and occurs_check(var, seg.var):
                return True
        return False

    def __unify__(self, other, trail):
        from .logic.variables import unify
        # An EMPTY Seg IS the empty list, in every spelling (fix round 4,
        # item 5).  See ``_EMPTY_SEG_IS_NIL``, above ``class SegList``.
        if _is_nil(other) and _is_nil(self.__walk__()):
            return True
        # The empty TUPLE is the empty LIST (fix round 3, item 3): it is the
        # hashable nil spelling ``atoms.NIL_KEY`` uses, and the arms below
        # gate on ``list``/``str``/``bytes``, so ``()`` was rejected outright
        # while ``[]`` succeeded -- one term, two answers.  Rewritten to
        # ``[]``, the spelling every arm knows, and ONLY ``()``: rewriting
        # ``""``/``b""`` as well would move a same-type target off its own
        # arm and change what a VarSeg binds to (``[*A] = ""`` binds
        # ``A = ""``, not ``A = []``).
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_text(other)      # stage 1: the carrier is the str it holds here
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if isinstance(other, bytes):
            walked = self.__walk__()
            if isinstance(walked, bytes):
                return walked == other
            # Non-ground: every split that fits (_drive_seg_unify).
            concrete_len = sum(len(s) for s in walked.segments
                               if isinstance(s, bytes))
            return _drive_seg_unify(walked, other, trail,
                                    concrete_len, _apply_segbytes_split)
        if isinstance(other, list):
            # Ground SegBytes → bytes, then let C-level bytes↔list
            # unification handle the comparison.
            walked = self.__walk__()
            if isinstance(walked, bytes):
                return unify(walked, other, trail)
            # Non-ground: convert bytes segments to ConcreteSeg-of-int-codes
            # (list(b"GET") == [71,69,84]) and delegate to the SegList
            # generator-driven enumeration. Mirrors SegString's list arm
            # (F023 precedent).
            equivalent_segs: list = []
            for seg in walked._segments:
                if isinstance(seg, bytes):
                    equivalent_segs.append(ConcreteSeg(list(seg)))
                else:  # VarSeg
                    equivalent_segs.append(seg)
            return SegList(equivalent_segs).__unify__(other, trail)
        if isinstance(other, (SegBytes, SegList)):
            return NotImplemented
        return NotImplemented

    def __len__(self) -> int:
        prefix, _ = self._concrete_prefix()
        return len(prefix)

    def __iter__(self):
        # Ground: iterate the walked bytes as ints (matches list(b"abc")
        # == [97,98,99]). Non-ground: yield the concrete int prefix.
        prefix, _ = self._concrete_prefix()
        return iter(prefix)

    def __contains__(self, item) -> bool:
        w = self.__walk__()
        if isinstance(w, bytes):
            try:
                return item in w
            except (TypeError, ValueError):
                return False
        has_var = False
        for seg in w._segments:
            if isinstance(seg, bytes):
                try:
                    if item in seg:
                        return True
                except (TypeError, ValueError):
                    pass
            else:
                has_var = True
        sensible = (
            (isinstance(item, int) and not isinstance(item, bool)
             and 0 <= item <= 255)
            or isinstance(item, bytes)
        )
        return has_var if sensible else False

    def __getitem__(self, index):
        w = self.__walk__()
        if isinstance(w, bytes):
            return w[index]
        parts = bytearray()
        for seg in w._segments:
            if isinstance(seg, bytes):
                parts.extend(seg)
            else:
                if isinstance(index, int) and 0 <= index < len(parts):
                    return parts[index]
                # In-prefix forward slice is knowable (A01-F010); return
                # bytes to match ground SegBytes slicing.
                if _slice_within_prefix(index, len(parts)):
                    return bytes(parts)[index]
                raise PartialTermError(
                    f"SegBytes[{index!r}] requires resolving an unbound "
                    f"VarSeg; only the concrete prefix (indices "
                    f"0..{len(parts) - 1}) is knowable. SegBytes={self!r}"
                )
        return bytes(parts)[index]

    def __eq__(self, other):
        # The empty TUPLE is the empty LIST (fix round 3, item 3), and the
        # arms below accept list/str/bytes only.
        if _is_nil(other) and _is_nil(self.__walk__()):
            return True          # fix round 4, item 5 — see _EMPTY_SEG_IS_NIL
        if type(other) is tuple and not other:
            other = []
        other_text = False
        if is_chars(other):
            other = chars_text(other)      # stage 1: the carrier is the str it holds here
            other_text = True              # STAGE 2: only the carrier is text -- a bare str is an ATOM
        if isinstance(other, SegBytes):
            return self._segments == other._segments
        if isinstance(other, bytes):
            w = self.__walk__()
            return w == other if isinstance(w, bytes) else False
        if isinstance(other, list):
            # Codes-model symmetry: int-list unifies with bytes at runtime.
            w = self.__walk__()
            if isinstance(w, bytes):
                if all(isinstance(c, int) and not isinstance(c, bool)
                       and 0 <= c <= 255 for c in other):
                    return w == bytes(other)
                return False
            return False
        return NotImplemented

    def __hash__(self):
        # Unconditionally unhashable, symmetric with SegString (F017) and
        # Python's list. Convert a ground SegBytes via bytes(...) for hashing.
        raise TypeError("unhashable type: 'SegBytes'")

    def __repr__(self):
        return f"SegBytes({self._segments!r})"


def _segbytes_unify_gen(segbytes, target_bytes, trail):
    """Non-deterministic generator: yield True for each valid split of
    *target_bytes* across the VarSegs of *segbytes*.

    *segbytes* must be a walked (non-ground) SegBytes.
    *target_bytes* must be a plain Python bytes.
    """
    from .logic.variables import unify
    min_len = sum(len(s) for s in segbytes.segments if isinstance(s, bytes))
    n = len(target_bytes)
    if n < min_len:
        return
    n_stars = sum(1 for s in segbytes.segments if isinstance(s, VarSeg))
    remainder = n - min_len
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0
        for seg in segbytes.segments:
            if isinstance(seg, VarSeg):
                sz = split[si]; si += 1
                ok = ok and unify(seg.var, target_bytes[pos:pos + sz], trail)
                pos += sz
            else:  # bytes
                end = pos + len(seg)
                if target_bytes[pos:end] != seg:
                    ok = False
                pos = end
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)


# ── DictTerm — unification-aware dictionary ───────────────────────────────────


class DictTerm:
    """Unification-aware dictionary term.

    Keys must be ground (str, int, or other hashable atoms).
    Values may be Vars, participating in unification.

    Two DictTerms unify iff they have the same key set and values unify pairwise.

    NIL KEYS (fix round 2, item 2, operator-ruled 2026-09-07).  The empty
    list is the atom ``'[]'`` and has four spellings — ``[]``, ``""``,
    ``b""``, ``()`` — of which only the last two are hashable and only the
    last is unambiguous.  All four are ONE term, so they must be one key:
    every key that enters or is looked up here goes through
    ``atoms.as_dict_key``, which folds them onto ``()``.  Without it
    ``mint("[]")`` (the empty LIST, mutable) crashed a key position with a
    raw ``TypeError``, and ``{"": 1}`` and ``{b"": 1}`` were two different
    keys for one term.
    """
    __slots__ = ("_data", "_position")

    def __init__(self, data: dict, *, _position=None):
        # Defensive copy first, at C speed (fix round 3, item 4: the per-key
        # comprehension this replaces cost ~18x on an 8-key dict, and this
        # constructor is hot -- ``dict_put/4``, ``__walk__``, every dict
        # literal).  Only then is nil-key normalisation considered, and only
        # when a nil spelling is actually present:
        #   * ``[]`` is unhashable, so it cannot be IN a built dict -- it
        #     raises ``TypeError`` out of ``dict()`` and takes the slow arm;
        #   * ``""``/``b""`` are hashable, so two O(1) membership tests find
        #     them and the comprehension runs only then.
        # ``()`` is already the canonical form and needs nothing.
        if type(data) is not dict and not hasattr(data, "items"):
            # A ONE-SHOT iterable (a generator, ``zip``, an iterator of
            # pairs) is CONSUMED by the ``dict()`` below, so the ``except``
            # arm had nothing left to re-iterate: every entry ``dict()`` had
            # already drained was silently LOST, and
            # ``DictTerm(iter([([], 1), (a, 2)]))`` came back as ``{a: 2}``
            # (fix round 4, item 2).  Materialise once, here, so both arms
            # read the same pairs.  Any MAPPING is exempt -- ``dict()`` does
            # not consume one, and this constructor is hot -- and ``items``
            # is the same test the ``except`` arm uses to tell the two
            # shapes apart, so the two cannot disagree.  The exact-``dict``
            # test short-circuits it: that is the overwhelmingly common
            # caller and it costs ~8 ns against ``hasattr``'s ~36 ns on a
            # ~200 ns constructor.  ``hasattr`` and not
            # ``isinstance(data, dict)`` because callers do pass other
            # mappings -- a ``mappingproxy`` (``Quantity.dimensions``) and
            # ``DictTerm`` itself.
            data = list(data)
        try:
            self._data = dict(data)
        except TypeError:
            items = data.items() if hasattr(data, "items") else data
            self._data = {_as_dict_key(k): v for k, v in items}
        else:
            if b"" in self._data or chars("") in self._data:   # STAGE 2: a bare "" is the atom '', not nil
                self._data = {_as_dict_key(k): v
                              for k, v in self._data.items()}
        self._position = _position  # Slice G

    @staticmethod
    def normalised_key(key):
        """*key* in the canonical dict-key form this class stores.

        The one entry point for code that reads the underlying mapping
        directly (``.data``) instead of going through ``__getitem__``:
        ``dict_set``'s builtins, ``runtime.dict_ops``'s subscript,
        ``py.json``'s ``get/3``.  Every nil spelling -- ``[]``, ``""``,
        ``b""``, ``()`` -- folds onto ``()``; everything else passes
        through.  Same function as ``atoms.as_dict_key``, exposed here so a
        caller holding a ``DictTerm`` need not reach for the atoms module
        (fix round 3, item 1).
        """
        return _as_dict_key(key)

    @staticmethod
    def mapping_of(value):
        """The underlying mapping of a dict-valued TERM, or ``None``.

        The reading twin of :meth:`normalised_key`, and the ONE place the
        "read a mapping only with normalised keys" invariant is enforced: a
        ``DictTerm``'s ``.data`` is already normalised, while a PLAIN Python
        dict has not been through ``__init__`` and may still spell a nil key
        ``""`` or ``b""`` (``[]`` cannot be in one at all — it is
        unhashable).  Two O(1) membership tests decide that, and a
        normalising copy is made only when one hits, so the common path costs
        nothing (fix round 4, item 1).

        Callers must NOT mutate the result: for a plain dict with no nil key
        it IS the caller's object.

        Lives on the class so ``runtime.dict_ops`` can share ONE
        implementation with ``builtins.dict_set._dict_input`` — importing the
        builtins package from the runtime would drag in the whole registry.
        """
        if isinstance(value, DictTerm):
            return value._data                 # already nil-normalised
        if isinstance(value, dict):
            if b"" in value or chars("") in value:   # STAGE 2: a bare "" is the atom '', not nil
                return {_as_dict_key(k): v for k, v in value.items()}
            return value
        return None

    @property
    def data(self) -> dict:
        return self._data

    def keys(self):   return self._data.keys()
    def values(self): return self._data.values()
    def items(self):  return self._data.items()
    def get(self, key, default=None): return self._data.get(_as_dict_key(key), default)
    def __len__(self): return len(self._data)
    def __getitem__(self, key): return self._data[_as_dict_key(key)]
    def __contains__(self, key): return _as_dict_key(key) in self._data
    def __iter__(self):          return iter(self._data)  # yields keys, like Python dict

    def __eq__(self, other):
        if isinstance(other, DictTerm):
            return self._data == other._data
        if isinstance(other, dict):
            # Normalise the raw dict's nil key the way ``__init__`` would,
            # so ``DictTerm({(): 1}) == {"": 1}`` — one term, one key.
            return self._data == {_as_dict_key(k): v for k, v in other.items()}
        return NotImplemented

    def __hash__(self):
        return hash(frozenset(self._data.items()))

    def __repr__(self):
        inner = ", ".join(f"{k!r}: {v!r}" for k, v in self._data.items())
        return f"DictTerm({{{inner}}})"

    # ── Protocol hooks for C extension ──

    def __walk__(self):
        """Called by C do_walk: return new DictTerm with walked values."""
        from .logic.variables import walk
        new_data = {k: walk(v) for k, v in self._data.items()}
        return DictTerm(new_data)

    def __occurs_check__(self, var):
        """Called by C do_occurs_check: check if var appears in any value."""
        from .logic.variables import occurs_check
        return any(occurs_check(var, v) for v in self._data.values())

    def __unify__(self, other, trail):
        """Called by C do_unify: pairwise value unification.

        Accepts another DictTerm or a plain Python dict on the right so
        that library-returned dicts (e.g. from `_deep_deref` or a
        bidirectional predicate's backward direction) unify with
        Clausal-native dict literals without forcing a ++({...}) escape.
        """
        if isinstance(other, DictTerm):
            other_data = other._data          # already normalised
        elif isinstance(other, dict):
            # A raw Python dict has NOT been through ``__init__``, so its
            # keys still carry whichever nil spelling the producer used.
            other_data = {_as_dict_key(k): v for k, v in other.items()}
        else:
            return NotImplemented
        if self._data.keys() != other_data.keys():
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for key in self._data:
            if not unify(self._data[key], other_data[key], trail):
                trail.undo(mark)
                return False
        return True


# ── SetTerm — unification-aware set ──────────────────────────────────────────


class SetTerm:
    """Unification-aware set term.

    Elements must be ground (hashable). Backed by frozenset for immutability.
    Two SetTerms unify iff they contain the same elements.
    """
    __slots__ = ("_elements", "_position")

    def __init__(self, elements, *, _position=None):
        self._elements = frozenset(elements)
        self._position = _position  # Slice G

    @property
    def elements(self) -> frozenset:
        return self._elements

    def __len__(self): return len(self._elements)
    def __contains__(self, item): return item in self._elements
    def __iter__(self): return iter(self._elements)

    def __eq__(self, other):
        if isinstance(other, SetTerm):
            return self._elements == other._elements
        if isinstance(other, (set, frozenset)):
            return self._elements == frozenset(other)
        return NotImplemented

    def __hash__(self):
        return hash(self._elements)

    def __repr__(self):
        inner = ", ".join(repr(e) for e in sorted(self._elements, key=repr))
        return f"SetTerm({{{inner}}})"

    def __unify__(self, other, trail):
        """Called by C do_unify: element-wise equality (elements are ground).

        Accepts another SetTerm or a plain set/frozenset on the right for
        symmetry with library code that returns Python sets.
        """
        if isinstance(other, SetTerm):
            return self._elements == other._elements
        if isinstance(other, (set, frozenset)):
            return self._elements == frozenset(other)
        return NotImplemented


# ── Quantity — number with physical dimensions ────────────────────────────────


class UnitsMismatch(Exception):
    """Raised when dimensioned quantities with incompatible units are combined."""


class CurrencyPrecisionError(Exception):
    """Raised when a currency amount is constructed with more decimal places
    than the currency's scale allows (e.g. 7.891 for a 2-dp euro)."""


def _check_currency_precision(value, currency) -> None:
    """Raise CurrencyPrecisionError if `value` carries digits below `currency`'s
    scale. Trailing zeros are allowed (7.890 == 7.89). `value` is a Decimal or
    an exact Fraction (a Fraction is in scale iff value * 10**scale is
    integral)."""
    scale = currency.scale
    if isinstance(value, Fraction):
        in_scale = (value * 10 ** scale).denominator == 1
    else:
        in_scale = value == value.quantize(Decimal(1).scaleb(-scale))
    if not in_scale:
        raise CurrencyPrecisionError(
            f"{value} has more decimal places than {currency._name} supports "
            f"(scale {scale}). Combine per-currency literals "
            f"(e.g. 0.1(euro) + 0.2(euro)), round explicitly with "
            f"money_round(V, Mode, Out), or use money_precise for deliberate "
            f"sub-scale amounts."
        )


_MONEY_ROUNDING = {
    "half_up": ROUND_HALF_UP, "half_even": ROUND_HALF_EVEN,
    "half_down": ROUND_HALF_DOWN, "up": ROUND_UP, "down": ROUND_DOWN,
    "ceiling": ROUND_CEILING, "floor": ROUND_FLOOR,
}


def _fraction_to_decimal_if_terminating(fr: Fraction):
    """The exact Decimal equal to *fr* when its denominator divides a power
    of ten, else None. No rounding anywhere: the denominator is reduced by
    its factors of 2 and 5 and the numerator scaled to match."""
    den = fr.denominator
    k2 = k5 = 0
    while den % 2 == 0:
        den //= 2
        k2 += 1
    while den % 5 == 0:
        den //= 5
        k5 += 1
    if den != 1:
        return None
    k = max(k2, k5)
    scaled = fr.numerator * (10 ** k // fr.denominator)
    # Built from a string: exact whatever the decimal context's precision
    # (scaleb is a context operation and would round past 28 digits).
    return Decimal(f"{scaled}E-{k}")


def _round_fraction_to_int(fr: Fraction, rounding) -> int:
    """Round an exact rational to an integer under a ``decimal`` ROUND_* mode.

    Exact by construction — no intermediate Decimal division — so a CLP(Q)
    result such as a third of a yen rounds once, at the caller's chosen
    mode, and nowhere else. ``divmod`` floors, so ``q < fr < q + 1`` when the
    remainder is non-zero, and the tie test compares ``2 * rem`` with ``d``.
    """
    n, d = fr.numerator, fr.denominator
    q, rem = divmod(n, d)
    if rem == 0:
        return q
    if rounding == ROUND_FLOOR:
        return q
    if rounding == ROUND_CEILING:
        return q + 1
    if rounding == ROUND_DOWN:                    # toward zero
        return q if fr > 0 else q + 1
    if rounding == ROUND_UP:                      # away from zero
        return q + 1 if fr > 0 else q
    twice = 2 * rem
    if twice < d:
        return q
    if twice > d:
        return q + 1
    # exact tie
    if rounding == ROUND_HALF_UP:                 # away from zero
        return q + 1 if fr > 0 else q
    if rounding == ROUND_HALF_DOWN:               # toward zero
        return q if fr > 0 else q + 1
    if rounding == ROUND_HALF_EVEN:
        return q if q % 2 == 0 else q + 1
    raise ValueError(f"unsupported rounding mode {rounding!r}")


def _quantize_to_scale(value, scale, mode_str):
    """Quantize a Decimal — or an exact Fraction — to `scale` decimal places
    using a mode string. A Fraction is rounded exactly, without passing
    through a Decimal division first."""
    rounding = _MONEY_ROUNDING.get(mode_str)
    if rounding is None:
        raise ValueError(f"unknown rounding mode {mode_str!r}; expected one of "
                         f"{sorted(_MONEY_ROUNDING)}")
    if isinstance(value, Fraction):
        units = _round_fraction_to_int(value * 10 ** scale, rounding)
        return Decimal(f"{units}E-{scale}")     # exact, context-free
    unit = Decimal(1).scaleb(-scale)
    return value.quantize(unit, rounding=rounding)


def _format_money(value, currency, style, mode_str):
    """Format a Decimal currency value: style in symbol/code/name/plain."""
    v = _quantize_to_scale(value, currency.scale, mode_str)
    if style == "symbol":
        return f"{currency.symbol}{v}"
    if style == "code":
        return f"{v} {currency.iso_code}"
    if style == "name":
        return f"{v} {currency._name}"
    if style == "plain":
        return f"{v}"
    raise ValueError(f"unknown money style {style!r}; expected symbol/code/name/plain")


def _dim_name(k) -> str:
    """Return a short display name for a dimension key (predicate or string)."""
    return k._name if hasattr(k, "_name") else str(k)


#: A value that renders as a plain numeric literal needs no parentheses.
#: `Decimal('1E+18')` renders `1E+18`, which is one; `Fraction(10, 3)` renders
#: `10/3`, which is not.
_SIMPLE_NUMBER = _re.compile(r"-?\d+(\.\d*)?([eE][+-]?\d+)?$")


def _value_text(value) -> str:
    """The magnitude, parenthesised when it would not bind tightly enough.

    A currency Quantity keeps an exact ``Fraction``, so `10.00(usd) / 3`
    renders its value as ``10/3`` — and `10/3 (usd)` parses as
    ``10 / 3(usd)``, because the call binds tighter than the division. That
    round-trips to the same magnitude with an INVERTED dimension: dollars per
    unit rather than dollars, which looks right and is not. `(10/3) (usd)` is
    the annotation that was meant.

    Parenthesising anything that is not a plain numeric literal is the
    general form, so a future value type that renders an operator cannot
    reintroduce this quietly.
    """
    text = str(value)
    return text if _SIMPLE_NUMBER.match(text) else f"({text})"


def atom_keyed_dims(dims) -> dict:
    """A dimension mapping with every key normalised to its ATOM.

    THE one place that knows both spellings. Dims arrive from three
    directions -- the unit factories, ``Quantity(value, dims)``, and the CLP
    constraint (``UnitState`` / ``constrain_var_dims``) -- and rulebase code
    reaches two of them, via ``make_quantity/3`` and ``has_units/2``.

    Normalising in only some of them is not a partial fix but a WRONG one: a
    quantity keyed by predicates does not compare equal to one keyed by atoms,
    so `D == 10(newton)` simply stops holding, and a units constraint stops
    matching the quantity that satisfies it. Both failures are silent.

    Zero exponents are dropped here too, since every caller did that already.
    """
    return {
        (k if type(k) is str else _unit_identifier(k)): v
        for k, v in dims.items() if v != 0
    }


def _currency_info(key):
    """The currency metadata for a dimension *key*, or None if it is not one.

    THE single place that turns a dimension key into its metadata. It takes a
    KEY rather than an atom deliberately, so it works on both sides of the
    rekey: today *key* is a unit predicate, afterwards it is the atom itself,
    and ``_unit_identifier`` already answers for both.

    Every caller used to read ``getattr(key, "is_currency", False)`` directly.
    That spelling returns False for a ``str`` -- SILENTLY -- so it could not
    survive the rekey, and one choke point is what makes the flip a
    one-function change instead of a sweep.
    """
    from clausal.modules import _unit_registry          # noqa: PLC0415
    entry = _unit_registry.info(_unit_identifier(key))
    return entry if entry is not None and entry.is_currency else None


def _unit_identifier(key) -> str:
    """The name a dimension is BOUND to — what a rulebase can write.

    For a currency this is `CURRENCY_BINDINGS[iso_code]`, never `_name`.
    `_name` is the everyday display word, and since the ISO-code rename it is
    not an identifier for a shared word: `dollar` does not resolve, and for
    the 22 currencies sharing it, it could not say which one. The bindings
    keep the plain word where it is unique (`euro`, `baht`, `sterling`), so
    output stays readable rather than uniformly cryptic.
    """
    code = getattr(key, "iso_code", None)
    if code:
        from clausal.modules.countries import _data          # noqa: PLC0415
        bound = _data.CURRENCY_BINDINGS.get(code)
        if bound:
            return bound
    return _dim_name(key)


def _unit_expr_str(dims: dict) -> str:
    """A dims dict as a re-readable unit EXPRESSION.

    The text `str(Quantity)` puts in parentheses, so that its whole output
    parses back to an equal value. `metre·second^-1` used neither `·` nor `^`
    validly; this emits `metre / second` and `metre ** 2`, which the parser
    accepts and `_is_unit_expr` recognises.

    Empty dims render as `dimensionless`, a real unit predicate, so that a
    dimensionless quantity round-trips too rather than being the one shape
    that cannot — `4` alone re-reads as a plain number and `4 ()` is not an
    annotation.
    """
    if not dims:
        return "dimensionless"

    def term(name, exponent):
        return name if exponent == 1 else f"{name} ** {exponent}"

    items = sorted(((_unit_identifier(k), e) for k, e in dims.items()),
                   key=lambda pair: pair[0])
    numerator = [term(n, e) for n, e in items if e > 0]
    denominator = [term(n, -e) for n, e in items if e < 0]
    head = " * ".join(numerator) if numerator else "1"
    if not denominator:
        return head
    tail = " * ".join(denominator)
    if len(denominator) > 1:
        tail = f"({tail})"
    return f"{head} / {tail}"


def _dims_str(dims: dict, *, qualify: frozenset = frozenset()) -> str:
    """Human-readable dimension string, e.g. 'm·s^-2'.

    Keys whose NAME is in *qualify* are rendered with their ISO code
    (``dollar (AUD)``) so two same-named dimensions can be told apart.
    Only those: the trigger for qualifying is computed over a whole
    rendering, but the effect must land on the component that actually
    collides and nowhere else. ``AUD/second`` against ``USD/second`` shares
    one identical ``second``, which was never ambiguous and must render the
    same on both sides (a downstream user, 2026-09-11).

    A qualified key with no code is left bare rather than given an
    identity: ``id()`` differs between runs of the same program, which
    defeats log diffing, makes two reports of one fault look like two, and
    cannot be pinned by a test. ``_require_same_dims`` says the ambiguity
    remains in words instead -- the same sentence every time.
    """
    if not dims:
        return "1"
    if not qualify:
        # ONE renderer (operator, 2026-09-12): a diagnostic names the unit the
        # way a rulebase writes it. `usd vs aud` is unambiguous by
        # construction, where `dollar vs dollar` was not — so for currencies
        # the qualifier below is now unnecessary rather than merely correct.
        return _unit_expr_str(dims)
    parts = []
    for k in sorted(dims, key=_unit_identifier):
        v = dims[k]
        name = _unit_identifier(k)
        # Reached only for same-named dimensions the bindings cannot separate,
        # which after the ISO-code rename means NON-currency ones: the 31 base
        # dimension names are SI plus `bit` and do not intersect the currency
        # names, so this branch has no live case today. `pound` is a currency
        # word twelve times over and there is no `pound` mass unit yet.
        code = getattr(k, "iso_code", None) if name in qualify else None
        if code:
            name = f"{name} ({code})"
        parts.append(name if v == 1 else f"{name} ** {v}")
    return " * ".join(parts)


def _colliding_dim_names(a: dict, b: dict) -> frozenset:
    """Names carried by DIFFERENT dimension objects on the two sides.

    A name present on both sides for the same object is not a collision --
    it is the shared part of a compound, and qualifying it adds noise to
    the half of the message that was never in doubt.
    """
    def by_name(dims):
        out = {}
        for k in dims:
            out.setdefault(_dim_name(k), set()).add(id(k))
        return out
    left, right = by_name(a), by_name(b)
    return frozenset(n for n in left.keys() & right.keys()
                     if left[n] != right[n])


def _float_beside_exact(f, op=None):
    """The refusal a float earns beside a Decimal or a Fraction at run time
    (RULED 2026-09-17 Q5): no implicit coercion, it risks loss of precision.
    One spelling with ``clausal.logic.exact_arith``.

    *op* is the operator that met the pair (``"*"``), which becomes the
    error's context ``(*)/2``; without one the context stays unbound.  The
    remedy is the exact spelling of the float's own digits, ``rdiv(N, D)`` --
    a term every module can write (``decimal(M, S)``, which this message used
    to suggest, has no source spelling)."""
    from clausal.logic.exceptions import LogicException, type_error  # noqa: PLC0415
    try:
        exact = Fraction(repr(f))
        remedy = f"rdiv({exact.numerator}, {exact.denominator})"
    except (ValueError, OverflowError):      # inf / nan
        remedy = "rdiv(N, D)"
    where = f"({op})/2: " if op else ""
    return LogicException(type_error(
        "exact_number", f,
        f"{where}quantity arithmetic: a float beside an exact number is "
        f"refused (RULED 2026-09-17 Q5); write it exactly, as {remedy}, or "
        f"write the digits with the unit"))


def _to_decimal(x):
    """Coerce a numeric magnitude to Decimal for a currency amount.

    Uses Decimal(str(f)) for floats — never Decimal(f), which would expose the
    binary expansion. Rejects bool (an int subclass) rather than treating it as
    a number.
    """
    if isinstance(x, Decimal):
        return x
    if isinstance(x, bool):
        raise TypeError(f"cannot use {x!r} as a currency amount")
    if isinstance(x, int):
        return Decimal(x)
    if isinstance(x, float):
        _warn_if_literal_may_be_lost(x)
        return Decimal(str(x))
    if isinstance(x, str):
        return Decimal(x)
    raise TypeError(f"cannot coerce {x!r} to a Decimal currency amount")


#: Significant decimal digits a float literal is guaranteed to carry. Measured
#: on this code path over 40,000 random 2dp amounts per row, not quoted:
#:
#:      14 digits   0.00% lost      17 digits  83.11% lost
#:      15 digits   0.00% lost      18 digits  98.25% lost
#:      16 digits  11.77% lost      19 digits  99.80% lost
#:
#: So <=15 is a guarantee and 16+ is a HAZARD, not a certainty: about one
#: 17-digit money amount in six still survives intact. The warning says "may
#: not be" for that reason -- an amount in the band is not necessarily wrong,
#: and saying otherwise would make the warning a claim it cannot support.
_FLOAT_EXACT_SIGNIFICANT_DIGITS = 15


def _warn_if_literal_may_be_lost(f: float) -> None:
    """Warn when a float money magnitude is in the band where the WRITTEN
    amount may already be gone.

    This cannot detect the loss -- by here there is only the float, and what
    was typed is unrecoverable. It detects the only thing that is knowable:
    that the value carries more significant digits than a float literal is
    guaranteed to round-trip, so the amount may not be the one written. An
    integer magnitude is exact at any size, which is why the message points
    at minor units rather than merely reporting a hazard.
    """
    try:
        digits = len(Decimal(repr(f)).normalize().as_tuple().digits)
    except (ValueError, ArithmeticError):
        return                      # inf/nan: not a literal-precision question
    if digits <= _FLOAT_EXACT_SIGNIFICANT_DIGITS:
        return
    import warnings                                        # noqa: PLC0415
    from clausal.lint_warnings import ClausalCurrencyLiteralWarning  # noqa: PLC0415
    warnings.warn(
        f"{f!r} carries {digits} significant digits, but a float literal is "
        f"exact only to {_FLOAT_EXACT_SIGNIFICANT_DIGITS} — this may not be "
        f"the amount that was written. Declare it in a minor unit, where the "
        f"magnitude is an integer and exact at any size "
        f"(e.g. 155000 cent, not 1550.00 euro), or pass the amount as a "
        f"string to money/3.",
        ClausalCurrencyLiteralWarning, stacklevel=4)


class quantity:  # noqa: N801 -- see the naming note below
    """A number with physical dimensions for dimensional analysis.

    ``dims`` maps dimension keys (unit predicate objects) to integer exponents.
    Zero-valued exponents are removed automatically.  The empty dict means
    dimensionless.  Internally all values are stored in SI base units; named-unit
    predicates (``metre``, ``newton``, ``watt``, …) in ``clausal.modules.units``
    handle scaling on the way in/out.

    Arithmetic:
        - ``+`` / ``-`` require identical dimension dicts; raises ``UnitsMismatch``
          otherwise.
        - ``*`` / ``/`` merge dimension dicts by addition / subtraction.
        - ``//`` / ``%`` require identical dimension dicts (as ``divmod_/4``);
          the quotient is dimensionless, the remainder keeps the dimension.
        - ``**`` scales every exponent by an integer constant; raises
          ``UnitsMismatch`` if the exponent is non-integer or has dimensions.
        - Plain numeric scalars (int/float) can be multiplied/divided freely.
        - A currency value is an exact number: int, Fraction or Decimal. A
          Fraction is kept as-is (a CLP(Q) result such as a third of a yen);
          float is coerced through ``Decimal(str(f))``.

    Clausal protocol:
        - ``__unify__`` — checks dims equality then unifies values.

    Uninstantiated dimensioned slots are plain ``AttVar`` objects carrying a
    ``"units"`` attribute (see ``clausal.logic.units_constraint``).  A
    ``Quantity`` always holds a ground numeric value — never a logic var.
    """

    __slots__ = ("_value", "_dims")

    def __init__(self, value, dims) -> None:
        if not _units_flag.active:
            _units_flag.touch()          # the CLP side channel may now engage
        if type(value) is Fraction and value.denominator == 1:
            # The engine's one rule for integral rationals (present_number):
            # Fraction(1000, 1) is the term 1000, on the ground path too.
            value = int(value)
        if isinstance(dims, Quantity):
            # dims is a Quantity constant (e.g. kilometre) — multiply:
            # Quantity(5, kilometre) → Quantity(5 * 1000, {metre: 1})
            #
            # RULED 2026-09-18 (Q6, option C): a float the user WROTE beside
            # an EXACT factor is read through its shortest repr HERE, at
            # construction -- ``2.5(centimetre)``, ``5.25 percent`` -- because
            # these are the user's own digits.  At run time the same pair
            # RAISES (``_num_pair``); this is the one place a written literal
            # meets the vocabulary, and the only place the bridge survives.
            if type(value) is float and isinstance(dims._value, (Decimal, Fraction)):
                value = _to_decimal(value)
            a, b = self._num_pair(value, dims._value)
            product = a * b
            if type(product) is Fraction and product.denominator == 1:
                product = int(product)
            self._value = product
            # COPY: _dims is a plain dict now, so aliasing would let one
            # quantity's mutation reach another's -- and __hash__ reads _dims.
            self._dims = dict(dims._dims)
            return
        if hasattr(dims, '_dims'):
            # dims is a _UnitsPredicate — extract dims dict
            actual_dims = dims._dims
        else:
            actual_dims = dims
        if not hasattr(actual_dims, 'items'):
            # e.g. Quantity(5, 1000) from `5(kilo)` — an SI prefix scale, not a
            # unit. Raise a designed error instead of a raw AttributeError from
            # `.items()` below (F056).
            raise TypeError(
                f"cannot build a Quantity from {dims!r}: SI prefixes cannot be "
                f"used as units"
            )
        self._value = value
        # A PLAIN DICT, not a mappingproxy. The proxy was the one thing
        # blocking marshalling (a plain {'metre': 1} marshals in 14 bytes), and
        # it was never needed for hashing: __hash__ goes through
        # frozenset(self._dims.items()) and does not touch _dims. Immutability
        # moves to the `dims` PROPERTY, which is where callers reach it.
        self._dims = atom_keyed_dims(actual_dims)
        if not isinstance(self._value, (Decimal, Fraction)):
            for _k in self._dims:
                if _currency_info(_k) is not None:
                    self._value = _to_decimal(self._value)
                    break
        # Precision check only when TAGGING a raw number as a currency (dims is a
        # currency predicate). Arithmetic results pass a dims dict and are exempt.
        if getattr(dims, "is_currency", False):
            _check_currency_precision(self._value, dims)

    def __call__(self, value):
        """Scale this quantity by *value* — ``byte(4)`` is ``4 * byte`` (F048).

        Lets a scaled-unit constant (e.g. ``byte``, ``mebi``) be used in the
        published ``n(Unit)`` call style, mirroring ``_UnitsPredicate.__call__``.
        """
        return Quantity(value, self)

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def value(self):
        return self._value

    @property
    def dims(self) -> MappingProxyType:
        # A VIEW over the stored dict. __hash__ is computed from _dims, so a
        # caller mutating it would silently corrupt an already-hashed value:
        # the guarantee has to survive even though the storage is now mutable.
        return MappingProxyType(self._dims)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _require_same_dims(self, other: "Quantity", op: str) -> None:
        if not isinstance(other, Quantity):
            raise UnitsMismatch(
                f"Cannot {op} dimensioned ({_dims_str(self._dims)}) "
                f"with plain value {other!r}"
            )
        if self._dims != other._dims:
            left, right = _dims_str(self._dims), _dims_str(other._dims)
            note = ""
            if left == right:
                # The dims DIFFER but render the same, so the message would
                # report a true error in a form indistinguishable from an
                # engine bug -- "dollar vs dollar" -- and send its reader
                # looking in the wrong place. 25 of the 153 distinct currency
                # names are shared by two or more ISO codes (dollar 22,
                # franc 17, pound 12), and the confusion this catches is
                # exactly the one a name collision causes, so the diagnostic
                # cannot be the thing that collides. Triggered by the
                # collision rather than by currency: two differently-named
                # units need no code, and adding one there is noise.
                collide = _colliding_dim_names(self._dims, other._dims)
                left = _dims_str(self._dims, qualify=collide)
                right = _dims_str(other._dims, qualify=collide)
                if left == right:
                    # Nothing carried a code to tell them apart. Say so in
                    # words rather than printing an address: the same
                    # sentence every run, which a log diff and a test can
                    # both rely on.
                    #
                    # Unreachable on today's vocabulary, but by accident and
                    # not by construction: the 31 base dimension names in
                    # clausal/modules/units.py are SI plus `bit`, and their
                    # intersection with the 153 currency names is empty, so
                    # every same-named pair is currency-vs-currency and every
                    # currency has a code. `pound` is a currency name twelve
                    # times over and there is no `pound` mass unit yet -- the
                    # first non-SI mass unit anyone adds makes this live.
                    note = (" — these are different dimensions that share a "
                            "name")
            raise UnitsMismatch(
                f"Unit mismatch for {op}: {left} vs {right}{note}")

    @staticmethod
    def _merge_dims(a: dict, b: dict, sign: int) -> dict:
        """Return a merged dims dict: a + sign*b, zeros removed."""
        result = dict(a)
        for k, v in b.items():
            new_v = result.get(k, 0) + sign * v
            if new_v:
                result[k] = new_v
            else:
                result.pop(k, None)
        return result

    @staticmethod
    def _num_pair(a, b, op=None):
        """Return (a, b) ready for exact arithmetic.

        RULED 2026-09-18 (Q5 + Q6 option C): a float beside a Decimal or a
        Fraction at RUN TIME is refused -- ``type_error(exact_number, Float)``
        -- rather than coerced.  The shortest-repr bridge this used to apply
        (``Decimal(str(f))``) is exact only for a float the user WROTE, and at
        run time nothing can tell a written float from a computed one; the
        written case is handled at CONSTRUCTION (``__init__`` beside an exact
        factor, ``_to_decimal`` for money) and at DECLARATION.  Decimal beside
        Fraction still goes exact-to-exact as a Fraction."""
        if isinstance(a, Decimal) and isinstance(b, float) and not isinstance(b, bool):
            raise _float_beside_exact(b, op)
        if isinstance(b, Decimal) and isinstance(a, float) and not isinstance(a, bool):
            raise _float_beside_exact(a, op)
        # Decimal and Fraction compare equal in Python but do not add: a
        # Fraction-valued money quantity (a CLP(Q) result) meeting a
        # Decimal literal goes exact-to-exact via Fraction(Decimal).
        if isinstance(a, Decimal) and isinstance(b, Fraction):
            if a.is_finite():
                return Fraction(a), b
            return a, Decimal(b.numerator) / Decimal(b.denominator)   # result is NaN/Inf anyway
        if isinstance(b, Decimal) and isinstance(a, Fraction):
            if b.is_finite():
                return a, Fraction(b)
            return Decimal(a.numerator) / Decimal(a.denominator), b
        # A float beside a Fraction would silently produce a float: refused
        # the same way (Q5).
        if isinstance(a, Fraction) and isinstance(b, float) and not isinstance(b, bool):
            raise _float_beside_exact(b, op)
        if isinstance(b, Fraction) and isinstance(a, float) and not isinstance(a, bool):
            raise _float_beside_exact(a, op)
        return a, b

    # ── Arithmetic ──────────────────────────────────────────────────────────

    def __add__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(self._value, other, "+")
            return Quantity(exact_add(a, b), {})
        self._require_same_dims(other, "add")
        a, b = self._num_pair(self._value, other._value, "+")
        return Quantity(exact_add(a, b), self._dims)

    def __radd__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(other, self._value, "+")
            return Quantity(exact_add(a, b), {})
        if isinstance(other, (int, float, Decimal, Fraction)):
            # A NUMBER meeting a dimensioned quantity is a units error, and it
            # is the same error in either order. Returning NotImplemented here
            # let PYTHON raise `unsupported operand type(s)` instead, which is
            # not the engine's error type and says nothing about units -- and
            # `sum_list` then reported it as `type_error(number, <Quantity>)`,
            # naming the quantity as the offender. That was already confusing
            # and became self-contradictory once `number/1` accepted one.
            self._require_same_dims(other, "add")
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(self._value, other, "-")
            return Quantity(exact_sub(a, b), {})
        self._require_same_dims(other, "subtract")
        a, b = self._num_pair(self._value, other._value, "-")
        return Quantity(exact_sub(a, b), self._dims)

    def __rsub__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(other, self._value, "-")
            return Quantity(exact_sub(a, b), {})
        if isinstance(other, (int, float, Decimal, Fraction)):
            self._require_same_dims(other, "subtract")   # see __radd__
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, +1)
            a, b = self._num_pair(self._value, other._value, "*")
            return Quantity(exact_mul(a, b), new_dims)
        a, b = self._num_pair(self._value, other, "*")
        return Quantity(exact_mul(a, b), self._dims)

    def __rmul__(self, other):
        a, b = self._num_pair(other, self._value, "*")
        return Quantity(exact_mul(a, b), self._dims)

    @staticmethod
    def _all_finite(*xs) -> bool:
        """False when a Decimal operand is NaN or infinite: those cannot be
        made exact (``Fraction(Decimal('Infinity'))`` raises), so the exact
        paths fall back to Decimal's own arithmetic for them."""
        return all(x.is_finite() for x in xs if isinstance(x, Decimal))

    @staticmethod
    def _exact_div(a, b):
        """Divide exactly when an exact non-integer type (Decimal, Fraction)
        is involved: Decimal's own ``/`` rounds to the 28-digit context, so
        ``1000(yen) / 3`` on the ground path disagreed with the same
        expression through CLP(Q), which is exact. The quotient is computed
        as a Fraction; a terminating one is presented as a Decimal (what a
        Decimal operand pair produced before), a non-terminating one stays
        the exact Fraction, as the CLP path yields it (an integral one is
        presented as int by ``__init__``). Anything with a float keeps
        Python's float semantics."""
        exact = (int, Decimal, Fraction)
        if (isinstance(a, exact) and isinstance(b, exact)
                and not isinstance(a, bool) and not isinstance(b, bool)
                and Quantity._all_finite(a, b)):
            # int/int included: the engine's own `is` folds 10/3 to the
            # rational Fraction(10, 3), so a quantity must not answer with a
            # float where a bare number answers exactly.
            q = Fraction(a) / Fraction(b)
            if isinstance(a, Decimal) or isinstance(b, Decimal):
                d = _fraction_to_decimal_if_terminating(q)
                if d is not None:
                    return d
            return q
        return a / b

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, -1)
            a, b = self._num_pair(self._value, other._value, "/")
            return Quantity(self._exact_div(a, b), new_dims)
        a, b = self._num_pair(self._value, other, "/")
        return Quantity(self._exact_div(a, b), self._dims)

    def __rtruediv__(self, other):
        new_dims = {k: -v for k, v in self._dims.items()}
        a, b = self._num_pair(other, self._value, "/")
        return Quantity(self._exact_div(a, b), new_dims)

    @staticmethod
    def _floor_divmod(a, b):
        """Floor quotient and divisor-signed remainder for ANY pair of exact
        or real numbers. Python's ``Decimal // Decimal`` truncates toward
        zero and ``Decimal %`` takes the dividend's sign, unlike int and
        Fraction, so a currency amount (stored as Decimal) would round the
        other way from the same amount stored as int. The quotient is
        computed exactly as a Fraction (a float goes through its shortest
        repr, as ``_num_pair`` does) and so is the remainder — ``Decimal``
        multiplication and subtraction are context operations and would
        round past 28 digits — then presented in the operands' kind
        (Decimal for a Decimal pair, int for ints), so ``a == q * b + r``
        holds exactly with the divisor's sign on ``r``."""
        import math  # noqa: PLC0415

        def exact(x):
            if isinstance(x, float):
                return Fraction(Decimal(str(x)))
            return Fraction(x)
        if not Quantity._all_finite(a, b):
            return a // b, a % b                 # Decimal's own semantics for NaN/Infinity
        ea, eb = exact(a), exact(b)
        q = math.floor(ea / eb)
        if isinstance(a, float) or isinstance(b, float):
            return q, a - q * b                  # float semantics stay float
        rem = ea - q * eb                        # exact; never a context operation
        if isinstance(a, Decimal) or isinstance(b, Decimal):
            d = _fraction_to_decimal_if_terminating(rem)
            return q, d if d is not None else rem
        if rem.denominator == 1:
            return q, int(rem)
        return q, rem

    def __floordiv__(self, other):
        """The DIMENSION rule of ``divmod_/4``: operands share a dimension,
        the quotient is dimensionless (a dimensionless Quantity here, where
        ``divmod_/4`` binds a bare number — ``/`` has the same trait)."""
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(self._value, other, "//")
            return Quantity(self._floor_divmod(a, b)[0], {})
        self._require_same_dims(other, "floor-divide")
        a, b = self._num_pair(self._value, other._value, "//")
        return Quantity(self._floor_divmod(a, b)[0], {})

    def __mod__(self, other):
        """The DIMENSION rule of ``divmod_/4``: operands share a dimension,
        the remainder keeps it."""
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(self._value, other, "mod")
            return Quantity(self._floor_divmod(a, b)[1], {})
        self._require_same_dims(other, "take the remainder of")
        a, b = self._num_pair(self._value, other._value, "mod")
        return Quantity(self._floor_divmod(a, b)[1], self._dims)

    def __rfloordiv__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(other, self._value, "//")
            return Quantity(self._floor_divmod(a, b)[0], {})
        if isinstance(other, (int, float, Decimal, Fraction)):
            self._require_same_dims(other, "floor-divide")   # see __radd__
        return NotImplemented

    def __rmod__(self, other):
        if isinstance(other, (int, float, Decimal, Fraction)) and not self._dims:
            a, b = self._num_pair(other, self._value, "mod")
            return Quantity(self._floor_divmod(a, b)[1], {})
        if isinstance(other, (int, float, Decimal, Fraction)):
            self._require_same_dims(other, "take the remainder of")   # see __radd__
        return NotImplemented

    def __pow__(self, exp):
        if isinstance(exp, Quantity):
            if exp._dims:
                raise UnitsMismatch("Exponent cannot have dimensions")
            exp = exp._value
        if not isinstance(exp, int):
            if self._dims:
                raise UnitsMismatch(
                    f"Exponent must be an integer constant for dimensional "
                    f"quantities, got {exp!r}"
                )
            # dimensionless: allow any numeric exponent (e.g. sqrt via ** 0.5)
            return Quantity(self._value ** exp, {})
        new_dims = {k: v * exp for k, v in self._dims.items() if v * exp != 0}
        if isinstance(self._value, (Decimal, Fraction)) and self._all_finite(self._value):
            # Exact: Decimal ** n is a context operation and rounds past 28
            # digits, and a negative power is a division, which `/` keeps
            # exact — so ``Q ** -1`` and ``1 / Q`` agree. A terminating
            # result of a Decimal base presents as Decimal, as `/` does.
            power = Fraction(self._value) ** exp
            if isinstance(self._value, Decimal):
                d = _fraction_to_decimal_if_terminating(power)
                if d is not None:
                    return Quantity(d, new_dims)
            return Quantity(power, new_dims)
        if exp < 0 and isinstance(self._value, int) and not isinstance(self._value, bool):
            return Quantity(self._exact_div(1, self._value ** -exp), new_dims)
        return Quantity(self._value ** exp, new_dims)

    def __neg__(self):
        return Quantity(-self._value, self._dims)

    def __abs__(self):
        return Quantity(abs(self._value), self._dims)

    def __pos__(self):
        return self

    # ── Comparisons (same dims required) ────────────────────────────────────

    def _cmp_value(self, other):
        """Return (self_val, other_val) after verifying same dims, or raise."""
        if isinstance(other, Quantity):
            if self._dims != other._dims:
                raise UnitsMismatch(
                    f"Cannot compare {_dims_str(self._dims)} "
                    f"with {_dims_str(other._dims)}"
                )
            return self._value, other._value
        if not self._dims:
            return self._value, other
        raise UnitsMismatch(
            f"Cannot compare dimensioned ({_dims_str(self._dims)}) "
            f"with plain value {other!r}"
        )

    def __lt__(self, other):
        a, b = self._cmp_value(other)
        return a < b

    def __le__(self, other):
        a, b = self._cmp_value(other)
        return a <= b

    def __gt__(self, other):
        a, b = self._cmp_value(other)
        return a > b

    def __ge__(self, other):
        a, b = self._cmp_value(other)
        return a >= b

    def __eq__(self, other):
        if isinstance(other, Quantity):
            return self._dims == other._dims and self._value == other._value
        return NotImplemented

    def __hash__(self):
        return hash((self._value, frozenset(self._dims.items())))

    # ── Representation ───────────────────────────────────────────────────────

    def __repr__(self) -> str:
        # the CLASS name, not a hardcoded spelling -- repr is what an author
        # sees, so it must not outlive a rename
        return f"{type(self).__name__}({self._value!r}, {self._dims!r})"

    def __str__(self) -> str:
        # The output IS valid input: `292.00 (usd)` parses back to an equal
        # value. What this produced before resembled source and was not —
        # bare juxtaposition is a SyntaxError, and it named `dollar`, which
        # has not resolved since the ISO-code rename.
        unit = _unit_expr_str(self._dims)
        value = self._value
        if isinstance(value, Fraction) and value.denominator != 1:
            # A rational magnitude cannot ride inside the annotation: the
            # annotation evaluates its value as PYTHON, where `10/3` is float
            # division, so `(10/3) (usd)` reconstructs 3.3333333333333335 and
            # a currency refuses it outright. Dividing the QUANTITY is exact —
            # `10 (usd) / 3` rebuilds Fraction(10, 3) — so the unit goes on
            # the numerator. A currency Quantity keeps an exact Fraction, so
            # this is the ordinary shape for money that has been divided.
            return f"{value.numerator} ({unit}) / {value.denominator}"
        return f"{_value_text(value)} ({unit})"

    def __format__(self, spec: str) -> str:
        cur = None
        if len(self._dims) == 1:
            (key, exp), = self._dims.items()
            info = _currency_info(key) if exp == 1 else None
            if info is not None:
                cur = info
        if cur is None:
            return format(str(self), spec)
        # currency spec: "<style>" or "<style>,<mode>"; default style code, mode half_even
        style, _, mode = spec.partition(",")
        return _format_money(self._value, cur, style or "code", mode or "half_even")

    # ── Clausal unification protocol ─────────────────────────────────────────

    def __unify__(self, other, trail) -> bool:
        """Called by C do_unify: dims must match exactly; values are unified."""
        if not isinstance(other, Quantity):
            return NotImplemented
        if self._dims != other._dims:
            return False
        from .logic.variables import unify
        return unify(self._value, other._value, trail)


# ── Cons / list helpers ────────────────────────────────────────────────────────


#: THE NAME IS `quantity`, LOWERCASE, and this is not a style preference.
#: TitleCase RAISES at load since the identifier lint, so a functor spelled
#: `Quantity` cannot be written in Clausal source at all -- which makes the
#: CLASS's name and the TERM's name disagree for the one type whose whole job
#: is to be written by authors. Lowercase puts it in the same namespace as
#: `date`, `decimal` and `rdiv`: all writable, all atoms.
#:
#: `Quantity` stays as an alias because it is exported from this module and
#: reached from downstream files and bodies that this repository does not
#: edit. The ~945 in-tree call sites are a separate, mechanical migration --
#: separate because lowercase `quantity` ALREADY exists as a local variable in
#: 51 places, so a blanket rename would leave the class shadowed by a local in
#: any function that uses both.
Quantity = quantity


# ── Kleene truth value: Undefined ─────────────────────────────────────────────

class _UndefinedType:
    """The third strong-Kleene (K3) truth value, sitting beside ``True``/``False``.

    A process-wide singleton (module-level name :data:`Undefined`), injected into
    every predicate module by ``clausal.import_hook`` — so ``.clausal`` code can
    reference ``Undefined`` with no declaration, import, or export, exactly as it
    references ``True``/``False``.  It is an ordinary ground constant: unification
    treats it by identity (there is only ever one instance), and it is hashable
    (default identity hash) so it can key clause indexes.

    The name follows XSB/SWI, whose well-founded-semantics vocabulary calls the
    third value ``undefined``; ``.clausal`` source accepts the lowercase
    ``undefined`` as an alias, resolved to this same singleton at parse time.
    This is also the value :meth:`TableEntry.truth_value` reports for an
    unfounded answer — WFS's third value and K3's are the same lattice element,
    so the language spells them the same way.

    ``bool(Undefined)`` raises ``TypeError`` deliberately — ``Undefined`` has no
    Python truth value, so an accidental ``if Undefined:`` / ``while Undefined:``
    is caught loudly rather than silently treated as truthy.  (Contrast ``None``,
    which means "no value / absent"; ``Undefined`` means "truth value neither
    true nor false" — the two are deliberately distinct and never unify.)

    Copy/deepcopy/pickle all round-trip back to the same singleton via
    ``__reduce__`` so trailing, ``copy_term``, or serialisation can never mint a
    second instance and break identity-based unification.
    """

    __slots__ = ()

    def __new__(cls):
        # Return the existing singleton if it is already built, so that even a
        # direct ``_UndefinedType()`` call (or an unpickle that bypasses
        # ``__reduce__``) yields the one instance.
        existing = globals().get("Undefined")
        if existing is not None:
            return existing
        return super().__new__(cls)

    def __repr__(self) -> str:
        return "Undefined"

    __str__ = __repr__

    def __bool__(self):
        raise TypeError(
            "Undefined has no Python truth value (it is the third strong-Kleene "
            "truth value). Compare it explicitly (e.g. `T is Undefined`) instead "
            "of using it in a Python if/while."
        )

    def __reduce__(self):
        # Pickle/copy/deepcopy resolve to the module-level ``Undefined`` name,
        # preserving the singleton across process/serialisation boundaries.
        return (_get_undefined, ())

    def __unify__(self, other, trail):
        # The atom ``undefined``: identical to itself (the unifier's identity
        # fast path) and to the str of its spelling (``atoms.TRUTH_SPELLINGS``
        # -- the same atom in its other spelling); to nothing else.
        return type(other) is str and other == "undefined"


def _get_undefined() -> "_UndefinedType":
    """Module-level factory used by ``_UndefinedType.__reduce__`` (picklable)."""
    return Undefined



Undefined = _UndefinedType()
_register_undefined_atom(Undefined)   # the third truth atom: see clausal.logic.atoms


# ── Deferred Python expression thunk ──────────────────────────────────────────

class PyThunk:
    """Deferred Python expression: a lambda evaluated at search time.

    The lambda takes the dereferenced values of logic variables as positional
    arguments and returns the result.  ``var_objects`` is a list of ``Var``
    instances (in parameter order) so the compiler can map each to its local
    variable name via ``var_context`` and emit ``fn(deref(v0), ...)``.

    Used for:
    - **f-strings in .clausal files**: ``f"Hello, {NAME}!"`` — the lambda
      contains the native f-string, returns a formatted string.
    - **``++()`` Python escape in logic terms**: ``++len(X_)`` — the lambda
      wraps the Python expression, returns any Python value.

    The lambda keeps the Python code native — no term transformation — so any
    Python expression (method calls, builtins, arithmetic, etc.) works.
    """
    __slots__ = ('fn', 'var_objects', '_position')

    def __init__(self, fn, var_objects, *, _position=None):
        self.fn = fn
        self.var_objects = tuple(var_objects)
        self._position = _position  # Slice G

    def __repr__(self):
        return f"PyThunk({self.fn!r}, {self.var_objects!r})"


# Backward-compat alias — f-string thunks use the same mechanism.
FStringThunk = PyThunk


# ── Term-rendering style ───────────────────────────────────────────────────────

@dataclass
class TermStyle:
    """Controls how terms are rendered by :func:`term_str` and :func:`term_pformat`.

    Attributes
    ----------
    anon_var : str
        String printed for an unbound (anonymous) variable.  Default ``'_'``.
    colors : dict or None
        ANSI colour map, or ``None`` for no colouring.  Recognised keys:

        ``'number'``
            int / float / complex literals.
        ``'string'``
            Python ``str`` values (rendered with surrounding quotes).
        ``'atom'``
            functor names in compound terms and bare names (``LoadName``).
        ``'var'``
            Unbound (anonymous) variables — the *anon_var* string is coloured.
        ``'brackets'``
            A list of ANSI codes, one per nesting level.  Cycles when depth
            exceeds the list length.  Applies to ``(``, ``)``, ``[``, ``]``,
            ``{``, ``}``.
        ``'reset'``
            ANSI reset sequence (default ``'\\033[0m'``).
    """
    anon_var: str = '_'
    colors: dict | None = None
    locale: str | None = None


#: Ready-made colour scheme using standard ANSI escape codes.
ANSI_COLORS: dict = {
    'number':   '\033[33m',    # yellow
    'string':   '\033[32m',    # green
    'atom':     '\033[36m',    # cyan
    'var':      '\033[35m',    # magenta
    'brackets': ['\033[91m', '\033[93m', '\033[92m', '\033[96m', '\033[94m', '\033[95m'],
    'reset':    '\033[0m',
}

_current_style: TermStyle = TermStyle()


def get_style() -> TermStyle:
    """Return the current module-level :class:`TermStyle`."""
    return _current_style


def set_style(style: TermStyle) -> None:
    """Set the module-level :class:`TermStyle` used by :func:`term_str` and
    :func:`term_pformat`.
    """
    global _current_style
    _current_style = style


_ANSI_ESCAPE = _re.compile(r'\x1b\[[0-9;]*m')


def _visible_len(s: str) -> int:
    """Return the visible (non-ANSI) length of *s*."""
    return len(_ANSI_ESCAPE.sub('', s))


def _c(s: str, kind: str, style: TermStyle, bd: int = 0) -> str:
    """Wrap *s* with the ANSI escape for *kind* under *style*."""
    if style.colors is None:
        return s
    c = style.colors
    reset = c.get('reset', '\033[0m')
    if kind == 'bracket':
        brackets = c.get('brackets', [])
        code = brackets[bd % len(brackets)] if brackets else ''
    else:
        code = c.get(kind, '')
    return (code + s + reset) if code else s


# ── Readable term representation ───────────────────────────────────────────────

def _locale_name(name: str, style: TermStyle, arity: int | None = None) -> str:
    """Translate *name* via *style.locale* if set, otherwise return as-is."""
    if style.locale is None:
        return name
    from clausal.logic.translations import translate_predicate, translate_atom
    if arity is not None:
        entry = translate_predicate(style.locale, name, arity)
        if entry is not None:
            return entry.translated_functor
    result = translate_atom(style.locale, name)
    return result if result is not None else name


# ── ISO atom / string quoting (spec §6.7) ─────────────────────────────────────

#: ISO 6.4.2 graphic characters: an atom made only of these is a bare
#: "graphic token" (``+``, ``=..``, ``-->``) and needs no quotes.
_GRAPHIC_CHARS = frozenset("#$&*+-./:<=>?@^~\\")
#: ISO 6.4.2 solo / bracket tokens that stand for themselves unquoted.
_SOLO_ATOMS = frozenset({"[]", "{}", "!", ";"})


def atom_needs_quotes(s: str) -> bool:
    """Return True when the atom spelled *s* must be quoted to re-read as
    itself (ISO 6.4.2).

    Bare iff *s* is a solo token (``[]``, ``{}``, ``!``, ``;``), a
    lowercase-initial identifier (``foo``, ``fooBar_1``), or a run of
    graphic characters (``+``, ``=..``).  The empty atom, ``,`` and a lone
    ``.`` need quotes.
    """
    if s in _SOLO_ATOMS:
        return False
    if not s:
        return True
    if s == ".":
        # A lone ``.`` is the END TOKEN: unquoted it would terminate the
        # term being read.  Longer graphic runs containing a dot (``=..``)
        # are safe and stay bare; Scryer quotes exactly this one.
        return True
    if s[0].islower() and all(c.isalnum() or c == "_" for c in s):
        return False
    if all(c in _GRAPHIC_CHARS for c in s):
        return False
    return True


def _escape_quoted(s: str, quote: str) -> str:
    """Escape *s* for placement inside *quote* delimiters (ISO 6.4.2 escapes)."""
    out = []
    for c in s:
        if c == "\\":
            out.append("\\\\")
        elif c == quote:
            out.append("\\" + quote)
        elif c == "\n":
            out.append("\\n")
        elif c == "\t":
            out.append("\\t")
        elif ord(c) < 0x20 or c == "\x7f":
            out.append(f"\\x{ord(c):02x}\\")
        else:
            out.append(c)
    return "".join(out)


def quote_atom(s: str) -> str:
    """Return *s* as a single-quoted atom token."""
    return "'" + _escape_quoted(s, "'") + "'"


def quote_string(s: str) -> str:
    """Return *s* as a double-quoted string token."""
    return '"' + _escape_quoted(s, '"') + '"'


def _quoted_atom_spelling(spelling: str) -> str:
    """Return the writer's spelling of the atom whose runtime str is
    *spelling*, quoted when ISO says it must be.

    A mangled (``-hide``) atom renders its human ``module.name`` display
    form and is never quoted — that form is display-only and does not
    round-trip anyway (design doc §1b).
    """
    if is_mangled(spelling):
        return demangle_for_display(spelling)
    return quote_atom(spelling) if atom_needs_quotes(spelling) else spelling


def _char_list_str(text: str, style: "TermStyle", _bd: int, quoted: bool,
                   sep: str) -> str:
    """Render *text* as the bracketed LIST of char atoms it denotes.

    Task 15 item 4: what ``write_term(T, [])`` prints for a string, since
    ``double_quotes(false)`` is ISO's default.  Each character is an ATOM, so
    it takes the atom quoting rule (``[' ', a]`` under ``quoted(true)``);
    *sep* is ``","`` for the ISO family and ``", "`` for the Clausal display
    family (fix round 1, item 0).
    """
    ob = _c('[', 'bracket', style, _bd)
    cb = _c(']', 'bracket', style, _bd)
    parts = []
    for ch in text:
        parts.append(_c(quote_atom(ch) if quoted and atom_needs_quotes(ch)
                        else ch, 'atom', style))
    return ob + sep.join(parts) + cb


def term_str(t: Any, style: TermStyle | None = None, _bd: int = 0,
             *, quoted: bool = True, double_quotes: bool = True,
             sep: str = ", ") -> str:
    """Return a readable string representation of any term.

    *style* controls anonymous-variable display and optional ANSI colouring;
    defaults to the module-level style (see :func:`set_style`).  *_bd* is the
    bracket-depth counter used internally for rainbow-bracket colouring.

    *quoted* (spec §6.7) selects the writer family: the default ``True`` is
    the ``writeq/1`` family, which quotes an atom that would not re-read as
    itself (``'foo bar'``); ``quoted=False`` is the ``write/1`` display
    family, which prints the bare spelling.  It threads through every
    recursive call.

    *double_quotes* (Task 15 item 4) is ISO ``write_term/2``'s option of the
    same name.  The default ``True`` prints a string — and the char list that
    IS a string — in its double-quoted form (``"abc"``), the form Scryer's
    TOPLEVEL displays and the one ``writeq/1`` uses here; ``False`` prints it
    as the list of char atoms it denotes (``[a, b, c]``, or ``[a,b,c]`` under the ISO *sep*), each char rendered
    per *quoted*, which is what ISO ``write_term(T, [])`` gives.  It threads
    through every recursive call alongside *quoted*.

    *sep* (fix round 1, item 0) is what goes between a compound's arguments,
    a list's elements and a dict's pairs.  The ISO family — ``write/1``,
    ``writeln/1``, ``write_to_string/2``, ``writeq/1``, ``write_term/2`` —
    passes ``","`` so its output is byte-comparable with Scryer
    (``[a,b,c]``, ``f(a,b)``, ``{k:v}``); the Clausal display family
    (``write_text/1``, ``print_term/1``, ``term_to_string/2``, and this
    function's own default) keeps ``", "``.  A dict's key/value separator
    follows it: ``": "`` when *sep* ends in a space, ``":"`` otherwise.
    ``write_canonical/1`` does not come through here at all — it has its own
    renderer (:func:`term_canonical`).
    """
    if style is None:
        style = _current_style
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool) or t is Undefined:
        return _truth_spelling(t)   # the atoms true/false/undefined (D35)
    if isinstance(t, Decimal):
        return _c(str(t), 'number', style)
    if isinstance(t, (int, float, complex)):
        return _c(repr(t), 'number', style)
    if is_chars(t):
        # A STRING -- the chars carrier (spec 2026-09-18 §1).  ``writeq``
        # prints it as a double-quoted string token; ``write`` the bare text;
        # the ISO family (``double_quotes(false)``) the list of its chars.
        # The EMPTY string is the empty list and prints ``[]``.
        t = chars_text(t)
        if t == "":
            return _c('[]', 'bracket', style, _bd)
        if not double_quotes:
            return _char_list_str(t, style, _bd, quoted, sep)
        return _c(quote_string(t) if quoted else t, 'string', style)
    if isinstance(t, str):
        # STAGE 2 (spec 2026-09-18 §1): a str is an ATOM.  It prints as a
        # name: the writeq family (``quoted=True``) quotes it when ISO 6.4.2
        # would (``'foo bar'``), the display family prints the bare
        # spelling; a hidden atom shows its ``module.name`` form.
        display = demangle_for_display(t) if is_mangled(t) else t
        display = _locale_name(display, style, 0)
        if quoted and not is_mangled(t) and atom_needs_quotes(display):
            display = quote_atom(display)
        return _c(display, 'atom', style)
    if isinstance(t, bytes):
        # A CODE LIST (spec §5.4).  Under ``double_quotes(false)`` — the ISO
        # family — it prints as the list of code NUMBERS it denotes, so
        # ``write(b"ab")`` gives ``[97,98]`` and ``write(b"")`` gives ``[]``,
        # matching what ISO prints for the equal ``[97, 98]`` (fix round 1,
        # item 5).  The display family keeps the ``b'ab'`` spelling §6.7
        # records as "as today".
        if not t:
            # ``b""`` IS the empty list, in every family: one term, one
            # rendering (fix round 2, item 5).  Checked BEFORE the
            # ``double_quotes`` gate, which would otherwise print ``b''``
            # for it in the display family while ``""`` printed ``[]``.
            return _c('[]', 'bracket', style, _bd)
        if double_quotes:
            return repr(t)
        ob = _c('[', 'bracket', style, _bd)
        cb = _c(']', 'bracket', style, _bd)
        return ob + sep.join(_c(repr(code), 'number', style) for code in t) + cb
    if isinstance(t, list):
        # A list of CHAR ATOMS *is* a string (spec §6.7's table row: Scryer
        # prints ``[a, b]`` as ``"ab"``), so it renders as one -- the same
        # text the equal ``str`` renders -- unless ``double_quotes`` is off,
        # in which case the ordinary bracketed element form below IS the
        # string's rendering and nothing special is needed.  ``[1, 2]`` and
        # every other list keep the bracketed element form throughout.
        if double_quotes and t and all(is_char_atom(e) for e in t):
            text = "".join(spelling(e) for e in t)
            return _c(quote_string(text) if quoted else text, 'string', style)
        ob = _c('[', 'bracket', style, _bd)
        cb = _c(']', 'bracket', style, _bd)
        return ob + sep.join(term_str(e, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for e in t) + cb
    if isinstance(t, Var):
        return _c(style.anon_var, 'var', style)
    if type(t) is tuple and not t:
        # The empty TUPLE is the empty list -- the hashable nil spelling
        # ``atoms.NIL_KEY`` uses (fix round 2, items 2 and 5).  It must be
        # decided HERE: both cell tests below are falsy on it, so it used to
        # fall all the way to ``repr(t)`` and print ``()``.
        return _c('[]', 'bracket', style, _bd)
    if type(t) is tuple and t and type(t[0]) is str and t[0] != TUPLE_TAG:
        # A CELL -- ``("pt", 1, 2)``.  P3-2 Task 2 (THE FLIP) makes this how
        # every compound term is represented, so the reader must see
        # ``pt(1, 2)``, the term they wrote, not a Python tuple repr.
        # Same locale name and rainbow brackets the retired ``Compound``
        # class rendered with, which is the shape it replaced.
        #
        # Slot 0 is read RAW -- no deref -- exactly ``_helpers._cell_functor``'s
        # rule (P3-2 Task 5/Task 7 review): a bound-Var functor is not a legal
        # cell slot 0 any more (the higher-order slot-0-Var cell is deprecated,
        # see ``clausal/logic/cells.py``'s module docstring), so a tuple whose
        # slot 0 is a Var -- bound or not -- is NOT a compound here and falls
        # through to the ordinary (non-cell) rendering below, same as any
        # other non-str, non-``TUPLE_TAG`` slot 0.
        functor = t[0]
        # P3-1 Task 6 (-hide, design doc section 1b): the functor gets the
        # same mangled-atom display substitution as the str branch above --
        # WITHOUT the quoting, since a functor position is never quoted.
        display_functor = demangle_for_display(functor) if is_mangled(functor) else functor
        refuse_reserved_1tuple(t)      # STAGE 2: the arity-0 cell is RESERVED
        args = t[1:]
        functor_s = _c(_locale_name(display_functor, style, len(args)), 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        return functor_s + ob + sep.join(
            term_str(a, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for a in args) + cb
    if type(t) is tuple and t and t[0] == TUPLE_TAG:
        # A tuple-DATA cell -- ``(tuple, e1, e2)`` -- represents plain tuple
        # data, not a compound (P3-2 Task 5's ``TUPLE_TAG`` convention).  It
        # renders as the ordinary tuple display it stands for: ``(e1, e2)``,
        # brackets through ``_c(...)`` like the list branch above;
        # ``(TUPLE_TAG,)`` (no elements) renders as ``()``.
        elems = t[1:]
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        return ob + sep.join(
            term_str(e, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for e in elems) + cb
    if isinstance(t, DictTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        # The key/value separator follows *sep* (fix round 1, item 0): the
        # ISO family prints ``{k:v}``, the display family ``{k: v}``.
        kv = ": " if sep.endswith(" ") else ":"
        inner = sep.join(
            f"{term_str(k, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep)}{kv}"
            f"{term_str(v, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep)}"
            for k, v in t.items()
        )
        return ob + inner + cb
    if isinstance(t, SetTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        inner = sep.join(term_str(e, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for e in sorted(t.elements, key=repr))
        return ob + inner + cb
    cls = type(t)
    op = getattr(cls, "op", None)

    # BinOp-style: left op right
    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        return ob + term_str(t.left, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) + f" {op} " + term_str(t.right, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) + cb

    # UnaryOp-style: op operand
    if op is not None and hasattr(t, "operand"):
        operand_str = term_str(t.operand, style, _bd, quoted=quoted, double_quotes=double_quotes, sep=sep)
        if op.isalpha():
            return f"{op} {operand_str}"
        return f"{op}{operand_str}"

    if isinstance(t, Call):
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args_str = sep.join(term_str(a, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for a in t.args)
        return term_str(t.func, style, _bd, quoted=quoted, double_quotes=double_quotes, sep=sep) + ob + args_str + cb
    if isinstance(t, LoadName):
        return _c(t.name, 'atom', style)
    if isinstance(t, Predicate):
        return f"{term_str(t.head, style, _bd, quoted=quoted, double_quotes=double_quotes, sep=sep)} <- {term_str(t.body, style, _bd, quoted=quoted, double_quotes=double_quotes, sep=sep)}"

    # PredicateMeta instances with locale translation.
    if style.locale is not None:
        from clausal.logic.predicate import is_term_instance, term_field_names, field_names_for
        # Zero-arity atom class (the class IS the value).
        if field_names_for(t) == ():
            return _c(_locale_name(t.__name__, style), 'atom', style)
        if is_term_instance(t):
            cls_name = _locale_name(type(t).__name__, style, len(term_field_names(t)))
            ob = _c('(', 'bracket', style, _bd)
            cb = _c(')', 'bracket', style, _bd)
            parts = sep.join(term_str(getattr(t, f), style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for f in term_field_names(t))
            return _c(cls_name, 'atom', style) + ob + parts + cb

    return repr(t)


def term_canonical(t: Any) -> str:
    """Return the ``write_canonical/1`` rendering of *t* (spec §6.7).

    Quoted atoms, no operator forms, no space after a comma, and every list
    printed as the ``'.'/2`` cons structure it denotes, ending in ``[]``
    (``'.'(1,'.'(2,[]))``) — byte-comparable with Scryer's output.  The
    representation itself is untouched (spec §5.4: ``'.'/2`` is a view,
    never a representation); only the rendering expands.  Same dispatch
    order as :func:`term_str`.

    The output never carries ANSI colour, whatever style is current: a
    canonical rendering exists to be compared byte for byte, so it spells
    numbers and variables itself rather than borrowing :func:`term_str`'s
    coloured spellings.

    Shapes ISO gives no canonical form for — ``DictTerm``,
    ``SetTerm``, ``Predicate``, ``Call``, and opaque Python objects — fall
    back to :func:`term_str`; there is no ``'…'/N`` structure to print them
    as, so the display rendering is the best available answer.
    """
    if not isinstance(t, (str, bytes, int, float)):
        t = deref(t)
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool) or t is Undefined:
        return _truth_spelling(t)   # the atoms true/false/undefined (D35)
    if isinstance(t, Decimal):
        return str(t)
    if isinstance(t, (int, float, complex)):
        return repr(t)
    if is_chars(t):
        # A STRING: the cons structure of its chars (Scryer-verified), ``[]`` when empty
        out = "[]"
        for c in reversed(chars_text(t)):
            out = "'.'(" + _quoted_atom_spelling(c) + "," + out + ")"
        return out
    if isinstance(t, str):
        return _quoted_atom_spelling(t)   # STAGE 2: a str is an ATOM
    if isinstance(t, bytes):
        # A CODE LIST: the cons structure of its codes, as for ``[97, 98]``
        out = "[]"
        for c in reversed(t):
            out = "'.'(" + repr(c) + "," + out + ")"
        return out
    if isinstance(t, list):
        out = "[]"
        for e in reversed(t):
            out = "'.'(" + term_canonical(e) + "," + out + ")"
        return out
    if isinstance(t, (SegList, SegString)):
        # A partial list/string: walk first (spec §6.7) and print what it
        # walks to.  A still-partial walk keeps its holes, each rendered as
        # the variable it is: ``[h, e | T]`` -> ``'.'(h,'.'(e,_N))``.
        walked = t.__walk__()
        if not isinstance(walked, (SegList, SegString)):
            return term_canonical(walked)
        return _seg_canonical(walked)
    if isinstance(t, Var):
        return _canonical_var(t)
    if type(t) is tuple and t and type(t[0]) is str and t[0] != TUPLE_TAG:
        # A CELL.  Slot 0 read RAW, no deref -- the recognition rule every
        # cell site uses.  An arity-0 cell is an atom and prints bare.
        refuse_reserved_1tuple(t)      # STAGE 2: the arity-0 cell is RESERVED
        head = _quoted_atom_spelling(t[0])
        return head + "(" + ",".join(term_canonical(a) for a in t[1:]) + ")"
    if type(t) is tuple and t and t[0] == TUPLE_TAG:
        return "(" + ",".join(term_canonical(e) for e in t[1:]) + ")"
    # Operator nodes -- recognised exactly as ``term_str`` recognises them
    # (an ``op`` class attribute plus ``left``/``right`` or ``operand``),
    # but canonical form has NO operator syntax: ``1 + 2`` is the term
    # ``+(1,2)`` and prints as one.
    cls = type(t)
    op = getattr(cls, "op", None)
    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        head = _quoted_atom_spelling(_iso_op_functor(cls))
        return (head + "(" + term_canonical(t.left) + ","
                + term_canonical(t.right) + ")")
    if op is not None and hasattr(t, "operand"):
        head = _quoted_atom_spelling(_iso_op_functor(cls))
        return head + "(" + term_canonical(t.operand) + ")"
    return term_str(t)


def _canonical_var(v) -> str:
    """Spell an unbound variable for canonical output: ``_`` + its identity.

    ``term_str`` prints every variable as the style's single anonymous
    ``_``, which makes ``f(X,Y)`` and ``f(X,X)`` indistinguishable;
    ISO/Scryer print distinct ``_N``.  The engine's own variable identity
    (``Var._id``, the counter ``compiler/terms_to_ast.py`` keys its variable
    context on) is that ``N``; a variable-like object without one falls back
    to its object identity, which is at least stable within a rendering.
    """
    vid = getattr(v, "_id", None)
    return "_" + (str(vid) if vid is not None else str(id(v)))


#: Operator node classes whose ISO functor name differs from the PYTHON
#: surface spelling their ``op`` attribute carries.  ``mod`` is ISO 9.1.3's
#: name for ``%``, and ``=<`` is ISO's spelling of ``<=`` (the same mapping
#: ``builtins/constraints.py``'s ``op_map`` already uses); the three
#: remaining comparison entries are the equivalences the node classes' own
#: docstrings record (``pythonic_ast/nodes.py``: "Prolog ``=:=/2``",
#: "Prolog ``=\\=/2``", "Prolog ``\\==/2``").  Every other operator's ``op``
#: string IS the functor's spelling -- ``<``, ``>``, ``>=`` and structural
#: ``==`` included -- so it needs no entry.
_ISO_OP_FUNCTOR = {
    "Mod": "mod",
    "LtE": "=<",
    "ArithEq": "=:=",
    "ArithNeq": "=\\=",
    "StructuralNeq": "\\==",
}


def _iso_op_functor(cls) -> str:
    """Return the functor name an operator node's class denotes."""
    return _ISO_OP_FUNCTOR.get(cls.__name__, cls.op)


def _seg_canonical(seg) -> str:
    """Render a still-partial ``SegList``/``SegString`` as a ``'.'/2`` chain
    whose tail is the trailing hole (a helper for :func:`term_canonical`)."""
    # Flatten to (elements..., tail) where tail is the LAST segment when it
    # is an unbound hole, else the empty list.
    rendered: list[str] = []
    segments = list(seg.segments)
    tail = "[]"
    if segments and isinstance(segments[-1], VarSeg):
        tail = _canonical_var(deref(segments[-1].var))
        segments = segments[:-1]
    for s in segments:
        if isinstance(s, VarSeg):
            # An interior hole stands for an unknown NUMBER of elements, so
            # no cons chain can spell it exactly; it renders as the variable
            # in the one element position it occupies.
            rendered.append(_canonical_var(deref(s.var)))
        elif isinstance(s, str):
            # SegString text.  THE FLIP (spec §6.2): the ELEMENTS of a string
            # are its CHAR ATOMS -- iterating the ``str`` directly yields
            # 1-char ``str`` values, each of which is a one-element STRING and
            # would print as its own ``'.'(c,[])`` chain.
            rendered.extend(_quoted_atom_spelling(c) for c in s)
        else:
            rendered.extend(term_canonical(e) for e in s.elements)  # ConcreteSeg
    out = tail
    for r in reversed(rendered):
        out = "'.'(" + r + "," + out + ")"
    return out


# ── Scryer-style writeq (the uncaught-error rendering) ────────────────────────
#
# ``term_writeq`` prints a term the way Scryer's toplevel prints an uncaught
# error term: ``write_term(T, [quoted(true), double_quotes(true),
# numbervars(true)])`` WITH operator syntax, no space after a comma, a
# distinct ``_N`` per variable.  ``LogicException``'s message uses it
# (ruling R2 of the Compound retirement, 2026-09-27).  It is its own entry
# point rather than a ``term_str`` switch: ``term_str`` has no operator
# layout, and giving ``writeq/1`` one is a separate, visible change.  Shapes
# with no Prolog spelling (dicts, sets, keyword terms, ``foo()``, Python
# objects) are handed to ``term_str`` in its ISO spelling.

import collections as _collections
import contextvars as _contextvars
import functools as _functools
import unicodedata as _unicodedata

#: Scryer's operator table with no library loaded (ISO Table 7 plus ``+``
#: fy 200, ``div`` and ``rdiv`` yfx 400).
_WQ_OPS = _OperatorTable.scryer_builtin_default()


#: Named escapes Scryer writes inside a quoted token; every other control or
#: non-printing character is ``\xHH\`` (lower-case hex, no padding).
_WQ_ESCAPES = {"\\": "\\\\", "\n": "\\n", "\t": "\\t", "\r": "\\r",
               "\a": "\\a", "\b": "\\b", "\f": "\\f", "\v": "\\v"}


def _wq_quote(s: str, q: str) -> str:
    out = []
    for c in s:
        if c == q:
            out.append("\\" + q)
        elif c in _WQ_ESCAPES:
            out.append(_WQ_ESCAPES[c])
        elif c != " " and _unicodedata.category(c)[0] in "CZ":
            out.append(f"\\x{ord(c):x}\\")
        else:
            out.append(c)
    return q + "".join(out) + q


@_functools.lru_cache(maxsize=1024)
def _wq_atom(s: str) -> str:
    if is_mangled(s):
        return demangle_for_display(s)
    # ``/*`` opens a comment at the start of a token, so Scryer quotes it.
    if atom_needs_quotes(s) or s.startswith("/*"):
        return _wq_quote(s, "'")
    return s


def _wq_float(x: float) -> str:
    """Scryer's float spelling: shortest round-trip digits, always a ``.0``
    mantissa, exponent without ``+`` or padding (``1.0e16``, ``1.5e-7``),
    positional for magnitudes in [1e-5, 1e16)."""
    r = repr(x)
    if "e" not in r:
        return r
    mant, exp = r.split("e")
    e = int(exp)
    if e == -5:
        return format(Decimal(r), "f")
    if "." not in mant:
        mant += ".0"
    return f"{mant}e{e}"


def _wq_is_op_atom(name: str) -> bool:
    ops = _WQ_OPS
    return (ops.lookup_infix(name) is not None
            or ops.lookup_prefix(name) is not None)


def _wq_glue(left: str, right: str) -> bool:
    """True when *left* followed directly by *right* would read as one
    token: two graphic characters, or two alphanumerics."""
    if not left or not right:
        return False
    a, b = left[-1], right[0]
    return ((a in _GRAPHIC_CHARS and b in _GRAPHIC_CHARS)
            or ((a.isalnum() or a == "_") and (b.isalnum() or b == "_")))


def _wq_cell(t):
    """``(name, args)`` when *t* is a compound with an atom functor and at
    least one argument (a cell or an operator node), else
    None."""
    if type(t) is tuple and len(t) > 1 and type(t[0]) is str and t[0] != TUPLE_TAG:
        return t[0], t[1:]
    op = getattr(type(t), "op", None)
    if isinstance(op, str):
        if hasattr(t, "left") and hasattr(t, "right"):
            return _iso_op_functor(type(t)), (t.left, t.right)
        if hasattr(t, "operand"):
            return _iso_op_functor(type(t)), (t.operand,)
    return None


def _wq_list(elems: list, tail) -> str:
    quoted, double_quotes, ignore_ops, _nv = _WQ_OPTS.get()
    if (double_quotes and tail is None and elems
            and all(is_char_atom(deref(e)) for e in elems)):
        text = "".join(spelling(deref(e)) for e in elems)
        return _wq_quote(text, '"') if quoted else text
    if ignore_ops:
        # ``ignore_ops(true)``: a list is the ``'.'/2`` compound it is, as
        # Scryer writes it.
        out = _wq(tail, 999) if tail is not None else "[]"
        for e in reversed(elems):
            out = _wq_name(".") + "(" + _wq(e, 999) + "," + out + ")"
        return out
    body = ",".join(_wq(e, 999) for e in elems)
    if tail is not None:
        body += "|" + _wq(tail, 999)
    return "[" + body + "]"


#: While ``term_writeq(..., local_vars=True)`` renders, the variables seen so
#: far, by identity, in order of first appearance.  Each renders as a
#: placeholder, NUL + digits + NUL, resolved once the whole term is written.
#: ``_wq_quote`` escapes a NUL inside every quoted token; only a raw NUL-digits-
#: NUL run inside a ``term_str`` fallback (a dict key, say) could collide.
_WQ_LOCAL_VARS: _contextvars.ContextVar = _contextvars.ContextVar(
    "_WQ_LOCAL_VARS", default=None)


#: The ISO write options in force while ``term_write`` renders:
#: ``(quoted, double_quotes, ignore_ops, numbervars)``.  ``term_writeq``
#: leaves the default, which is how Scryer's toplevel prints an uncaught
#: error: quoted, double-quoted strings, operators, ``'$VAR'`` as a letter.
_WQ_DEFAULT_OPTS = (True, True, False, True)
_WQ_OPTS: _contextvars.ContextVar = _contextvars.ContextVar(
    "_WQ_OPTS", default=_WQ_DEFAULT_OPTS)


def _wq_name(s: str) -> str:
    """An atom in a NAME position under the options in force: quoted when
    ``quoted(true)`` and ISO 6.4.2 needs it, else its bare spelling."""
    if _WQ_OPTS.get()[0]:
        return _wq_atom(s)
    return demangle_for_display(s) if is_mangled(s) else s


def _wq_var(v) -> str:
    seen = _WQ_LOCAL_VARS.get()
    if seen is None:
        return _canonical_var(v)
    n = seen.setdefault(id(v), len(seen))
    return f"\x00{n}\x00"


def _wq_local_names(text: str, seen: dict) -> str:
    """Resolve the ``_wq_var`` placeholders in *text*: ``_`` for a variable
    written once, ``_1``, ``_2``, ... (by first appearance) for one written
    more than once."""
    if not seen:
        return text
    counts = _collections.Counter(_WQ_PLACEHOLDER.findall(text))
    names: dict[str, str] = {}
    shared = 0
    for n in sorted(counts, key=int):
        if counts[n] == 1:
            names[n] = "_"
        else:
            shared += 1
            names[n] = f"_{shared}"
    return _WQ_PLACEHOLDER.sub(lambda m: names.get(m.group(1), m.group(0)), text)


_WQ_PLACEHOLDER = _re.compile("\x00(\\d+)\x00")


def _wq(t: Any, prec: int, operand: bool = False) -> str:
    if not isinstance(t, (str, bytes, int, float, tuple, list)):
        t = deref(t)
    if isinstance(t, Var):
        return _wq_var(t)
    quoted, double_quotes, ignore_ops, numbervars = _WQ_OPTS.get()
    if isinstance(t, bool) or t is None:
        return term_str(t, quoted=quoted, double_quotes=double_quotes, sep=",")
    if isinstance(t, float):
        return _wq_float(t)
    if isinstance(t, int):
        return str(t)
    if is_chars(t):
        text = chars_text(t)
        if not text:
            return "[]"
        if double_quotes:
            return _wq_quote(text, '"') if quoted else text
        # ``double_quotes(false)``: a string is the list of its chars.
        return _wq_list(list(text), None)
    if isinstance(t, str):
        s = _wq_name(t)
        return ("(" + s + ")" if operand and not ignore_ops
                and _wq_is_op_atom(t) else s)
    if isinstance(t, bytes):
        return "[" + ",".join(str(b) for b in t) + "]"
    if isinstance(t, list) or (type(t) is tuple and not t):
        return _wq_list(list(t), None)
    if isinstance(t, (SegList, SegString)):
        walked = t.__walk__()
        if not isinstance(walked, (SegList, SegString)):
            return _wq(walked, prec, operand)
        if isinstance(walked, SegList):
            segs = list(walked.segments)
            tail = None
            if segs and isinstance(segs[-1], VarSeg):
                tail = segs.pop().var
            if not any(isinstance(s, VarSeg) for s in segs):
                elems = [e for s in segs for e in s.elements]
                if not elems:
                    return _wq(tail, prec, operand)
                return _wq_list(elems, tail)
        return term_str(walked, quoted=quoted, double_quotes=double_quotes,
                        sep=",")
    if isinstance(t, Quantity):
        # A units quantity is written as its source spelling, ``10 (usd)`` --
        # what ``writeq/1`` prints -- not the Python repr
        # ``quantity(Decimal('10'), {'usd': 1})`` (triage C17).
        return str(t)
    cell = _wq_cell(t)
    if cell is None:
        return term_str(t, quoted=quoted, double_quotes=double_quotes,
                        sep=",")
    name, args = cell
    ops = _WQ_OPS
    if ignore_ops:
        if (numbervars and name == "$VAR" and len(args) == 1
                and type(deref(args[0])) is int and deref(args[0]) >= 0):
            arg = deref(args[0])
            return chr(ord("A") + arg % 26) + (str(arg // 26) if arg >= 26 else "")
        return _wq_name(name) + "(" + ",".join(_wq(a, 999) for a in args) + ")"
    if name == "." and len(args) == 2:
        # The ISO cons cell: an IMPROPER list ``[b|foo]`` is the compound
        # ``'.'(b, foo)`` (a proper list is a Python list), and Scryer
        # writes it in list notation, ``[a,b|c]``.
        elems = [args[0]]
        tail = deref(args[1])
        while True:
            c = _wq_cell(tail) if type(tail) is tuple else None
            if c is None or c[0] != "." or len(c[1]) != 2:
                break
            elems.append(c[1][0])
            tail = deref(c[1][1])
        if _is_nil(tail):
            return _wq_list(elems, None)
        if isinstance(tail, list):
            return _wq_list(elems + tail, None)
        return _wq_list(elems, tail)
    if len(args) == 2:
        e = ops.lookup_infix(name)
        if e is not None:
            p, spec = e.precedence, e.specifier
            left = _wq(args[0], p if spec[0] == "y" else p - 1, True)
            right = _wq(args[1], p if spec[2] == "y" else p - 1, True)
            if name == ",":
                s = left + "," + right
            elif name[0].isalpha():
                s = left + " " + name + " " + right
            else:
                s = (left + (" " if _wq_glue(left, name) else "") + name
                     + (" " if _wq_glue(name, right) else "") + right)
            return "(" + s + ")" if p > prec else s
    if len(args) == 1:
        arg = deref(args[0])
        if name == "{}":
            return "{" + _wq(arg, 1200) + "}"
        if numbervars and name == "$VAR" and type(arg) is int and arg >= 0:
            return chr(ord("A") + arg % 26) + (str(arg // 26) if arg >= 26 else "")
        e = ops.lookup_prefix(name)
        if e is not None:
            p, spec = e.precedence, e.specifier
            if (name == "-" and not isinstance(arg, bool)
                    and isinstance(arg, (int, float)) and arg >= 0):
                # ``-(1)`` is not the number ``-1``: Scryer writes ``- (1)``.
                a = "(" + _wq(arg, 1200) + ")"
            else:
                a = _wq(arg, p if spec == "fy" else p - 1, True)
            sep = " " if (a[0] == "(" or name[0].isalpha()
                          or _wq_glue(name, a)) else ""
            s = _wq_name(name) + sep + a
            return "(" + s + ")" if p > prec else s
    return _wq_name(name) + "(" + ",".join(_wq(a, 999) for a in args) + ")"


def term_write(t: Any, *, quoted: bool, double_quotes: bool = False,
               ignore_ops: bool = False, numbervars: bool = True) -> str:
    """Render *t* as ISO ``write_term/2`` does with these options, byte for
    byte as Scryer writes it: operator syntax (unless *ignore_ops*), no space
    after a comma, a distinct ``_N`` per variable, Scryer's float spelling,
    and -- under *quoted* -- every atom, functor included, quoted when it
    would not re-read as itself.  The ISO writer family (``write/1``,
    ``writeq/1``, ``write_term/2``) prints through this."""
    token = _WQ_OPTS.set((quoted, double_quotes, ignore_ops, numbervars))
    try:
        return _wq(t, 1200)
    finally:
        _WQ_OPTS.reset(token)


def term_writeq(t: Any, *, local_vars: bool = False) -> str:
    """Render *t* as Scryer prints an uncaught error term.

    ``writeq``-style with operators: ``error(type_error(evaluable,(+)/2),
    (is)/2)``, ``- (1)``, ``a- -1``, ``"abc"`` for a string, ``_N`` for each
    variable, ``'$VAR'(N)`` as a letter.  The comment that opens the
    "Scryer-style writeq" section says what it does and does not share with
    ``writeq/1``.  A shape with no Prolog spelling (dict, set, keyword term,
    ``foo()``, a partial list with an interior hole) is printed whole by
    ``term_str``, so terms nested inside it lose the operator layout and the
    distinct ``_N`` variables.

    *local_vars* names the variables within this term instead of by the
    engine's global identity: one written once is ``_``, one written more
    than once ``_1``, ``_2``, ... in order of first appearance.  The text is
    then the same for every copy of the term, which ``_N`` is not.  A
    subterm handed whole to ``term_str`` (see above) prints its variables
    as ``_`` itself, so sharing with such a subterm is not shown.
    """
    token = _WQ_LOCAL_VARS.set({} if local_vars else None)
    try:
        text = _wq(t, 1200)
        return _wq_local_names(text, _WQ_LOCAL_VARS.get()) if local_vars else text
    finally:
        _WQ_LOCAL_VARS.reset(token)


# ── Pretty-formatted term representation ──────────────────────────────────────

_PFORMAT_INDENT = "  "


def term_pformat(
    t: Any,
    depth: int = 0,
    width: int | None = None,
    style: TermStyle | None = None,
    _bd: int = 0,
) -> str:
    """Pretty-format a term with indentation for multi-line display.

    Uses standard (non-canonical) form — operators appear in their expected
    position (infix, prefix).  Short terms are kept on one line; longer
    terms are expanded with *depth*-level indentation.

    *width* is the line-width budget.  when ``None`` (the default) it is
    resolved once from the terminal via ``shutil.get_terminal_size()`` and
    then threaded through all recursive calls so every sub-term uses the
    same value.

    *style* controls anonymous-variable display and optional ANSI colouring;
    defaults to the module-level style (see :func:`set_style`).  *_bd* is the
    bracket-depth counter used internally for rainbow-bracket colouring.
    """
    if style is None:
        style = _current_style
    if width is None:
        import shutil
        width = shutil.get_terminal_size(fallback=(80, 24)).columns

    flat = term_str(t, style, _bd)
    if _visible_len(flat) + len(_PFORMAT_INDENT) * depth <= width:
        return flat

    pad = _PFORMAT_INDENT * depth
    child = depth + 1
    ipad = _PFORMAT_INDENT * child

    def _join(items: list) -> str:
        return (",\n" + ipad).join(items)

    def _r(v):
        return term_pformat(v, child, width, style, _bd + 1)

    if isinstance(t, list):
        if not t:
            return flat
        if all(is_char_atom(e) for e in t):
            # A list of char atoms IS a string and ``term_str`` renders it as
            # one (spec §6.7).  There is nothing to break across lines — a
            # string is a single token — so a long one stays flat rather
            # than being exploded into one char atom per line.
            return flat
        ob = _c('[', 'bracket', style, _bd)
        cb = _c(']', 'bracket', style, _bd)
        items = [_r(e) for e in t]
        return ob + "\n" + ipad + _join(items) + "\n" + pad + cb


    if type(t) is tuple and t and type(t[0]) is str and t[0] != TUPLE_TAG:
        # A str-functor CELL -- the multi-line treatment (P3-2 Task 7): a
        # wide cell used to fall through every isinstance branch above
        # straight to ``return flat``, so a long ``pt(1, 2)`` never got the
        # indented form.  Slot 0 read
        # RAW, no deref, matching every other cell recognition site (Task 5).
        args = t[1:]
        if not args:
            return flat
        # A ``-hide`` functor displays in its human ``module.name`` form, as
        # the flat ``term_str`` branch does; the raw spelling carries the
        # internal separator.
        fname = demangle_for_display(t[0]) if is_mangled(t[0]) else t[0]
        functor_s = _c(fname, 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(a) for a in args]
        return functor_s + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if type(t) is tuple and t and t[0] == TUPLE_TAG:
        # A tuple-DATA cell -- same multi-line treatment as the list branch
        # above, since this is what it displays as (``TUPLE_TAG`` itself
        # never appears in the rendering).
        elems = t[1:]
        if not elems:
            return flat
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(e) for e in elems]
        return ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if isinstance(t, DictTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        items = [f"{_r(k)}: {_r(v)}" for k, v in t.items()]
        return ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if isinstance(t, SetTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        items = [_r(e) for e in sorted(t.elements, key=repr)]
        return ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    cls = type(t)
    op = getattr(cls, "op", None)

    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        left = _r(t.left)
        right = _r(t.right)
        return ob + "\n" + ipad + left + "\n" + ipad + op + " " + right + "\n" + pad + cb

    if op is not None and hasattr(t, "operand"):
        operand = _r(t.operand)
        if op.isalpha():
            return op + " " + operand
        return op + operand

    if isinstance(t, Call):
        if not t.args:
            return flat
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(a) for a in t.args]
        func_str = term_pformat(t.func, depth, width, style, _bd)
        return func_str + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if isinstance(t, Predicate):
        head = _r(t.head)
        body = _r(t.body)
        return head + " <-\n" + ipad + body

    return flat


# ── HTML term representation (Jupyter notebooks) ─────────────────────────────

import html as _html_mod
import re as _re_mod

JUPYTER_CSS = """\
<style>
.clausal-output { font-family: monospace; white-space: pre-wrap; line-height: 1.5; }
.clausal-output .clausal-number { color: #b58900; }
.clausal-output .clausal-string { color: #859900; }
.clausal-output .clausal-atom { color: #2aa198; }
.clausal-output .clausal-var { color: #d33682; font-style: italic; }
.clausal-output .clausal-bracket-0 { color: #dc322f; }
.clausal-output .clausal-bracket-1 { color: #b58900; }
.clausal-output .clausal-bracket-2 { color: #859900; }
.clausal-output .clausal-bracket-3 { color: #2aa198; }
.clausal-output .clausal-bracket-4 { color: #268bd2; }
.clausal-output .clausal-bracket-5 { color: #d33682; }
.clausal-output .clausal-or { color: #6c71c4; font-weight: bold; }
.clausal-output .clausal-footer { color: #93a1a1; font-style: italic; margin-top: 0.3em; }
</style>"""


def _html_c(s: str, kind: str, bd: int = 0) -> str:
    """Wrap *s* in an HTML span with a CSS class for *kind*.

    The input *s* must already be HTML-escaped.
    """
    if kind == 'bracket':
        cls = f'clausal-bracket-{bd % 6}'
    else:
        cls = f'clausal-{kind}'
    return f'<span class="{cls}">{s}</span>'


def term_html(t: Any, _bd: int = 0) -> str:
    """Return an HTML representation of any term with CSS class spans.

    Parallel to :func:`term_str` but produces HTML instead of ANSI-colored
    text.  All text content is HTML-escaped.  Bracket depth *_bd* controls
    rainbow-bracket CSS classes (``clausal-bracket-0`` through ``-5``).
    """
    esc = _html_mod.escape
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool):
        return esc(str(t))
    if isinstance(t, Decimal):
        return _html_c(esc(str(t)), 'number')
    if isinstance(t, (int, float, complex)):
        return _html_c(esc(repr(t)), 'number')
    if is_chars(t):
        # A STRING -- the chars carrier: the same spelling ``term_str``
        # produces (a double-quoted string token, ``[]`` for the empty one).
        # It used to fall to the cell branch and render as ``$chars("abc")``.
        text = chars_text(t)
        if text == "":
            return _html_c('[]', 'bracket', _bd)
        return _html_c(esc(quote_string(text)), 'string')
    if isinstance(t, str):
        # An ATOM (stage 2 of the atoms-as-str flip; this branch still read
        # a str as a STRING and printed ``"foo"``): ``term_str``'s spelling,
        # quoted when it must be, a ``-hide`` atom in its ``module.name``
        # form.
        return _html_c(esc(term_str(t)), 'atom')
    if isinstance(t, bytes):
        return esc(repr(t))
    if isinstance(t, list):
        # A list of char atoms IS a string and renders as one -- same rule as
        # ``term_str``'s list branch.
        if t and all(is_char_atom(e) for e in t):
            return _html_c(
                esc(quote_string("".join(spelling(e) for e in t))), 'string')
        ob = _html_c('[', 'bracket', _bd)
        cb = _html_c(']', 'bracket', _bd)
        return ob + ", ".join(term_html(e, _bd + 1) for e in t) + cb
    if isinstance(t, Var):
        return _html_c('_', 'var')
    if type(t) is tuple and t and type(t[0]) is str and t[0] != TUPLE_TAG:
        # A str-functor CELL (P3-2 Task 7); without this a cell fell through to the
        # ``esc(repr(t))`` tail, leaking the Python tuple repr into Jupyter
        # output.  Slot 0 read RAW, no deref (Task 5's rule).
        if len(t) == 1:
            # An ATOM -- an arity-0 cell prints as its (quoted) name, never
            # as ``flag()`` (spec §6.7); ``term_str`` owns that spelling.
            return _html_c(esc(term_str(t)), 'atom')
        functor_s = _html_c(esc(term_str(t[0])), 'atom')
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t[1:])
        return functor_s + ob + args_str + cb
    if type(t) is tuple and t and t[0] == TUPLE_TAG:
        # A tuple-DATA cell -- plain tuple display, brackets only.
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(e, _bd + 1) for e in t[1:])
        return ob + args_str + cb
    if isinstance(t, DictTerm):
        ob = _html_c('{', 'bracket', _bd)
        cb = _html_c('}', 'bracket', _bd)
        inner = ", ".join(
            f"{term_html(k, _bd + 1)}: {term_html(v, _bd + 1)}"
            for k, v in t.items()
        )
        return ob + inner + cb
    if isinstance(t, SetTerm):
        ob = _html_c('{', 'bracket', _bd)
        cb = _html_c('}', 'bracket', _bd)
        inner = ", ".join(term_html(e, _bd + 1) for e in sorted(t.elements, key=repr))
        return ob + inner + cb

    cls = type(t)
    op = getattr(cls, "op", None)

    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        return ob + term_html(t.left, _bd + 1) + f" {esc(op)} " + term_html(t.right, _bd + 1) + cb
    if op is not None and hasattr(t, "operand"):
        operand_s = term_html(t.operand, _bd)
        esc_op = esc(op)
        if op.isalpha():
            return f"{esc_op} {operand_s}"
        return f"{esc_op}{operand_s}"

    if isinstance(t, Call):
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t.args)
        return term_html(t.func, _bd) + ob + args_str + cb
    if isinstance(t, LoadName):
        return _html_c(esc(t.name), 'atom')
    if isinstance(t, Predicate):
        return f"{term_html(t.head, _bd)} &lt;- {term_html(t.body, _bd)}"

    return esc(repr(t))


def term_pformat_html(t: Any, width: int = 120) -> str:
    """Pretty-format a term as HTML.

    Uses :func:`term_html` for rendering.  If the flat representation
    exceeds *width* visible characters, wraps in a ``<pre>`` block.
    """
    flat = term_html(t)
    visible = _re_mod.sub(r'<[^>]+>', '', flat)
    if len(visible) <= width:
        return flat
    return f"<pre>{flat}</pre>"


# ── Public API ─────────────────────────────────────────────────────────────────

__all__ = [
    # Logic variable
    "Var",
    # New term types
    "DictTerm",
    "SetTerm",
    "SegList",
    "SegListView",
    "SegString",
    "SegBytes",
    "ConcreteSeg",
    "VarSeg",
    "PyThunk",
    "FStringThunk",
    # Units
    "quantity",
    "Quantity",   # deprecated alias; see the naming note in terms.py
    "UnitsMismatch",
    # Kleene (K3) third truth value
    "Undefined",
    # Partial-term error (catchable by callers of partial Seg* ops)
    "PartialTermError",
    # Rendering style
    "TermStyle",
    "ANSI_COLORS",
    "get_style",
    "set_style",
    # Helpers
    "term_str",
    "term_pformat",
    # Canonical (write_canonical/1) rendering and ISO 6.4.2 quoting
    "term_canonical",
    "atom_needs_quotes",
    "quote_atom",
    "quote_string",
    # HTML rendering (Jupyter)
    "JUPYTER_CSS",
    "term_html",
    "term_pformat_html",
    # Arithmetic binary operators
    "Add", "Sub", "Mult", "Div", "FloorDiv", "Mod", "Pow",
    # Bitwise / shift binary operators
    "BitAnd", "BitOr", "BitXor", "LShift", "RShift",
    # Boolean binary operators
    "And", "Or",
    # Unary operators
    "Not", "Invert", "Negate",
    # Comparison / unification operators
    "Unify", "DoesNotUnify", "Evaluate", "ArithEq", "ArithNeq", "Lt", "LtE", "Gt", "GtE", "in_", "NotIn",
    # Expression nodes
    "Call", "LoadName", "LoadAttr", "LoadSubscript", "Slice",
    # Predicate clause term
    "Predicate",
]


def seg_closed(term):
    """The sequence a ``SegList`` / ``SegString`` / ``SegBytes`` walks to when
    every hole is filled -- a list, chars carrier or bytes -- else None.

    This, not groundness, is what makes a partial list a PROPER list: the
    elements may still be unbound.  ``[V, *T]`` with ``T`` bound to ``[]`` is
    the one-element list ``[V]`` (a DCG over ``[_]`` builds exactly that), yet
    it is not ground.  Testing ``is_ground`` here made length/2, is_list/1 and
    every list builtin treat it as an open list."""
    w = term.__walk__()
    return None if isinstance(w, (SegList, SegString, SegBytes)) else w
