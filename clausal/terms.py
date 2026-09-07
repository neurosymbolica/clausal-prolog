"""clausal.terms — logic term layer.

functor types and value types for the clausal logic programming system.

Python built-in types (int, float, str, bool, None, list) are terms directly —
no wrapper needed.  Logic variables are Var objects.  Structured terms are
instances of user-defined dataclasses (one class per functor) or Compound for
runtime-constructed terms.

Goal types are term types: the same classes serve as goal nodes when they appear
in a predicate body.  The compiler dispatches on the class via Python's match
statement.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from decimal import (
    Decimal, ROUND_HALF_UP, ROUND_HALF_EVEN, ROUND_HALF_DOWN,
    ROUND_UP, ROUND_DOWN, ROUND_CEILING, ROUND_FLOOR,
)
from types import MappingProxyType
from typing import Any, Optional

from .logic.atoms import (
    char_atom, demangle_for_display, is_char_atom, is_mangled, spelling,
)
from .logic.cells import TUPLE_TAG
from .logic.variables import Var, deref

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

@dataclass
class Compound:
    """Fallback for runtime-constructed or unknown-functor compound terms.

    Use when no compile-time dataclass exists for the functor, e.g.:
        Compound("cons", (head, tail))
        Compound(functor_var, args)
    """
    functor: str | Var
    args: tuple
    # Slice G — source position (start_line, start_col, end_line, end_col).
    # ``compare=False`` / ``repr=False`` keeps structural equality and
    # printing unaffected — position is cosmetic metadata only.
    # Underscore prefix: Clausal treats ``_name`` as a logic variable,
    # so this attribute is unreachable as a user field name.
    _position: Optional[tuple] = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        args_str = ", ".join(term_str(a) for a in self.args)
        f = self.functor if isinstance(self.functor, str) else term_str(self.functor)
        return f"{f}({args_str})"

    def __unify__(self, other, trail) -> bool:
        """Structural unification: same functor and arity, args unified pairwise.

        Functors are dereferenced before comparison (A01-F003 deref-only floor,
        parked decision A01-D004): a functor Var *bound* to a str matches the
        corresponding str functor. Binding an *unbound* functor Var (output
        mode) is out of scope for the deref-only floor, so two differing
        functors — including an unbound Var vs a str — simply fail to unify.
        """
        if not isinstance(other, Compound):
            return NotImplemented
        if deref(self.functor) != deref(other.functor) or len(self.args) != len(other.args):
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for a, b in zip(self.args, other.args):
            if not unify(a, b, trail):
                trail.undo(mark)
                return False
        return True

    def __occurs_check__(self, var) -> bool:
        """Called by C do_occurs_check: check if var appears in any arg.

        Without this hook do_occurs_check falls through to ``return 0`` for
        Compound, so unify_with_occurs_check would build the very cyclic term
        the check exists to prevent (A01-F001). The functor slot is not
        traversed here — Var functors are gated on parked decision A01-D004;
        a str functor is a no-op for occurs_check regardless.
        """
        from .logic.variables import occurs_check
        return any(occurs_check(var, a) for a in self.args)

    def __walk__(self):
        """Deep-substitute bindings (A01-F008): rebuild with walked args so a
        snapshot survives trail backtracking. The functor is dereferenced
        (F003 deref-only floor) and ``_position`` (Slice G) is preserved.
        Unbound Vars are left in place (walk sharing contract).
        """
        from .logic.variables import walk, deref
        return Compound(
            deref(self.functor),
            tuple(walk(a) for a in self.args),
            _position=self._position,
        )



# ── Open-world keyword term ────────────────────────────────────────────────────


class KWTerm:
    """Open-world keyword term — any functor, any keywords, dict-backed.

    For runtime-constructed terms where the functor has no compile-time class.
    Attributes are read from the backing dict.  Iteration yields values in
    insertion order.  Equality and unification match by keyword name (not
    position): ``KWTerm('r', a=1, b=2) == KWTerm('r', b=2, a=1)``.

    **Reserved keyword:** ``_position`` is consumed by the constructor
    as source-location metadata (Slice G — see :attr:`_position`), not
    stored as a keyword field.  The leading underscore makes it
    syntactically unreachable as a Clausal field name (Clausal parses
    ``_foo`` as a logic variable), so user code cannot collide with it.
    """

    __slots__ = ("_functor", "_fields", "_position")

    def __init__(self, functor: str, **kwargs: Any) -> None:
        object.__setattr__(self, "_functor", functor)
        # Slice G — source position; pop from kwargs before storing fields
        # so callers can pass ``_position=(...)`` from templater-emitted
        # constructor calls without polluting the keyword field set.
        object.__setattr__(self, "_position", kwargs.pop("_position", None))
        object.__setattr__(self, "_fields", dict(kwargs))

    @property
    def functor(self) -> str:
        return self._functor

    def __getattr__(self, name: str) -> Any:
        try:
            return self._fields[name]
        except KeyError:
            raise AttributeError(
                f"KWTerm {self._functor!r} has no field {name!r}"
            ) from None

    def __eq__(self, other: object) -> bool:
        if isinstance(other, KWTerm):
            return (
                self._functor == other._functor
                and self._fields == other._fields
            )
        return NotImplemented

    def __hash__(self) -> int:
        return hash((self._functor, tuple(sorted(self._fields.items()))))

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self._fields.items())
        return f"KWTerm({self._functor!r}, {args})"

    def __unify__(self, other, trail):
        """Called by C do_unify: match by functor + keyword name, then
        pairwise-unify field values (so Var-valued fields bind).

        Without this hook C ``do_unify`` falls back to rich-compare and
        Var fields compare by identity instead of binding (A01-F004).
        Mirrors :meth:`DictTerm.__unify__`.
        """
        if not isinstance(other, KWTerm):
            return NotImplemented
        if (self._functor != other._functor
                or self._fields.keys() != other._fields.keys()):
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for k in self._fields:
            if not unify(self._fields[k], other._fields[k], trail):
                trail.undo(mark)
                return False
        return True

    def __occurs_check__(self, var) -> bool:
        """Called by C do_occurs_check: check if var appears in any field
        value (A01-F001). Mirrors :meth:`DictTerm.__occurs_check__`."""
        from .logic.variables import occurs_check
        return any(occurs_check(var, v) for v in self._fields.values())

    def __walk__(self):
        """Deep-substitute bindings (A01-F008): rebuild with walked field
        values so a snapshot survives trail backtracking. ``_position``
        (Slice G) is preserved; unbound Vars are left in place."""
        from .logic.variables import walk
        return KWTerm(
            self._functor,
            _position=self._position,
            **{k: walk(v) for k, v in self._fields.items()},
        )

    def keys(self):
        return self._fields.keys()

    def values(self):
        return self._fields.values()

    def items(self):
        return self._fields.items()

    def __len__(self) -> int:
        return len(self._fields)

    def with_overrides(self, **overrides: Any) -> "KWTerm":
        """Return a new KWTerm with specified fields replaced."""
        new_fields = dict(self._fields)
        for k in overrides:
            if k not in new_fields:
                raise KeyError(f"KWTerm {self._functor!r} has no field {k!r}")
        new_fields.update(overrides)
        return KWTerm(self._functor, **new_fields)

    def with_extensions(self, **extensions: Any) -> "KWTerm":
        """Return a new KWTerm with additional fields appended."""
        new_fields = dict(self._fields)
        for k in extensions:
            if k in new_fields:
                raise KeyError(
                    f"KWTerm {self._functor!r} already has field {k!r}"
                )
        new_fields.update(extensions)
        return KWTerm(self._functor, **new_fields)


# ── SegList — segmented partial list ─────────────────────────────────────────


@dataclass
class ConcreteSeg:
    """A concrete (known) segment of a SegList — a fixed sequence of elements."""
    elements: list


@dataclass
class VarSeg:
    """A variable-length hole in a SegList — represents an unknown subsequence."""
    var: Var


def _seg_unify_cache_key(other, trail):
    """Build a hashable cache key for ``SegList`` / ``SegString`` ``__unify__``
    generator caching (see [[F015]] / [[F016]]).

    The key combines a *content-derived* form of ``other`` with the
    identity of ``trail`` so that re-calls with a freshly constructed but
    value-equal target (e.g. a ``[1, 2, 3]`` literal that is rebuilt each
    loop iteration) hit the same cached generator entry. ``str`` targets
    are already hashable; ``list`` targets are tupled, recursively
    substituting ``("id", id(e))`` for any unhashable element so the key
    itself stays hashable even if the list contains custom objects.

    Trail identity (``id(trail)``) is used because ``Trail`` is
    intentionally non-hashable and the cache lifetime is implicitly
    bounded by the trail's lifetime: once the trail is gone, any
    generator paused on it is unreachable too.
    """
    if isinstance(other, str):
        return (other, id(trail))
    if isinstance(other, bytes):
        return (other, id(trail))
    if isinstance(other, list):
        items = []
        for e in other:
            try:
                hash(e)
                items.append(e)
            except TypeError:
                items.append(("id", id(e)))
        return (tuple(items), id(trail))
    # Fall back to identity for anything else (unify only routes list/str
    # targets here today, so this is a defensive branch).
    return (id(other), id(trail))


# ── Seg* __unify__ generator cache (A01-F005) ──────────────────────────────────
#
# The public ``_seglist_unify_gen`` / ``_segstring_unify_gen`` /
# ``_segbytes_unify_gen`` generators (used directly by the compiler as
# ``$seglist_unify_gen`` and by tests via ``for _ in gen``) close over the
# ``trail`` and are fine when driven to exhaustion locally. But
# ``__unify__`` caches a *suspended* generator on ``self._unify_gens`` to
# expose non-determinism across calls; a suspended generator's frame pins
# its Trail (and everything the trail references) for the lifetime of the
# Seg* term, and the ``id(trail)`` key made the dict grow one entry per
# query forever (F005 probe: 20/20 dead trails stayed alive).
#
# The cache therefore drives a *trail-free* split enumerator (below) and
# applies each split against the current trail inline. A suspended entry
# holds only the walked term + target + split-iterator state — never the
# trail — so dropped trails are collectable. The cache is a small LRU
# (``_SEG_UNIFY_LRU_MAX`` entries) so it can't grow unboundedly, while
# still keeping several interleaved drives alive at once (a clear-all
# eviction livelocked them — A01-F005 follow-up). Re-enumeration after
# eviction restarts from the first split, which is indistinguishable from
# a fresh trail state for a correctly-driven caller.


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


def _apply_seglist_split(seglist, target_list, split, trail):
    """Bind *seglist* against *target_list* for one *split*; return True on
    success (bindings left on *trail*), False otherwise. Mirrors the inner
    loop of :func:`_seglist_unify_gen`."""
    from .logic.variables import unify
    # A ``str`` target is a char list: its ELEMENTS are chars, its SLICES
    # stay str (R-S2). Twin of ``_seg_helpers.seq_getitem``.
    target_is_str = type(target_list) is str
    pos = 0
    si = 0
    for seg in seglist.segments:
        if isinstance(seg, VarSeg):
            sz = split[si]; si += 1
            if not unify(seg.var, target_list[pos:pos + sz], trail):
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
            if not unify(seg.var, target_str[pos:pos + sz], trail):
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


# LRU capacity for the per-term ``_unify_gens`` cache. Small on purpose: it
# only needs to keep the handful of drives that can realistically be
# interleaved at once, while guaranteeing dead-trail entries are evicted
# quickly (A01-F005). Clear-all eviction (the first F005 fix) livelocked
# interleaved drives of one term against different targets: each new drive
# evicted the other's suspended generator, so every resume restarted from
# split 1 and neither drive could ever exhaust.
_SEG_UNIFY_LRU_MAX = 8


def _drive_seg_unify(cache, walked, other, trail, concrete_len, apply_fn):
    """Advance the ``__unify__`` split-drive by one successful split.

    ``cache`` maps ``(target-content, id(trail)) -> (split_gen, last_mark)``.
    The generator is the trail-free :func:`_seg_split_gen`; ``apply_fn`` binds
    a split against *trail*. The cache is a small LRU (at most
    :data:`_SEG_UNIFY_LRU_MAX` entries, insertion order = recency): evicted
    generators are ``close()``d, so stale drives are dropped promptly while
    concurrently interleaved drives stay alive (A01-F005 follow-up)."""
    key = _seg_unify_cache_key(other, trail)
    # Pop so a resumed entry is re-inserted at the MRU end below.
    entry = cache.pop(key, None)
    if entry is None:
        gen = _seg_split_gen(walked.segments, len(other), concrete_len)
    else:
        gen, last_mark = entry
        if last_mark is not None:
            # Undo the previous split's bindings before the next attempt,
            # mirroring the public generator's post-yield ``trail.undo``.
            trail.undo(last_mark)
    while True:
        try:
            split = next(gen)
        except StopIteration:
            return False
        mark = trail.mark()
        if apply_fn(walked, other, split, trail):
            while len(cache) >= _SEG_UNIFY_LRU_MAX:
                old_gen, _ = cache.pop(next(iter(cache)))
                old_gen.close()
            cache[key] = (gen, mark)
            return True
        trail.undo(mark)


class SegList:
    """A first-class term representing a list with variable-length holes.

    A SegList is a flat sequence of alternating ConcreteSeg and VarSeg objects.
    when every VarSeg's var is bound to a concrete list, the SegList is ground
    and ``__walk__`` returns a plain Python list.

    Example::

        [1, 2, *MID, 5, *TAIL]
        → SegList([ConcreteSeg([1, 2]), VarSeg(MID), ConcreteSeg([5]), VarSeg(TAIL)])
    """

    __slots__ = ("_segments", "_unify_gens")

    def __init__(self, segments: list):
        self._segments = list(segments)
        # F015 fix — per-(target, trail) generator cache so successive calls
        # to ``__unify__`` expose every split of ``_seglist_unify_gen`` rather
        # than committing to the first one. See ``__unify__`` below.
        self._unify_gens: dict = {}

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
        from .logic.variables import walk
        new_segs: list = []
        for seg in self._segments:
            if isinstance(seg, ConcreteSeg):
                walked_elems = [walk(e) for e in seg.elements]
                if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                    new_segs[-1] = ConcreteSeg(new_segs[-1].elements + walked_elems)
                else:
                    new_segs.append(ConcreteSeg(walked_elems))
            else:  # VarSeg
                v = walk(seg.var)
                if isinstance(v, str):
                    # VarSeg bound to a substring — expand to CHARS for SegList
                    chars = [char_atom(c) for c in v]
                    if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                        new_segs[-1] = ConcreteSeg(new_segs[-1].elements + chars)
                    else:
                        if chars:
                            new_segs.append(ConcreteSeg(chars))
                elif isinstance(v, list):
                    # Inline the concrete list into previous ConcreteSeg or new one
                    if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                        new_segs[-1] = ConcreteSeg(new_segs[-1].elements + v)
                    else:
                        if v:
                            new_segs.append(ConcreteSeg(v))
                elif isinstance(v, SegList):
                    # Inline nested SegList's segments. ``_walk_raw`` (not
                    # ``__walk__``): a nested ground SegList of chars would
                    # otherwise arrive PROMOTED to a str and fall into the
                    # ``._segments`` branch below, which a str does not have.
                    walked_inner = v._walk_raw()
                    if isinstance(walked_inner, list):
                        if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                            new_segs[-1] = ConcreteSeg(new_segs[-1].elements + walked_inner)
                        else:
                            if walked_inner:
                                new_segs.append(ConcreteSeg(walked_inner))
                    else:
                        # Inline the inner SegList's segments one by one
                        for inner_seg in walked_inner._segments:
                            if isinstance(inner_seg, ConcreteSeg):
                                if new_segs and isinstance(new_segs[-1], ConcreteSeg):
                                    new_segs[-1] = ConcreteSeg(
                                        new_segs[-1].elements + inner_seg.elements
                                    )
                                else:
                                    new_segs.append(ConcreteSeg(inner_seg.elements[:]))
                            else:
                                new_segs.append(inner_seg)
                else:
                    # Either still an unbound Var (keep the hole) or bound to
                    # an out-of-contract scalar. The latter left the term in
                    # silent limbo — non-ground forever, every unify quietly
                    # failing (A01-F009, mirroring the F024 char-list guard).
                    from .logic.variables import is_var
                    if not is_var(v):
                        raise PartialTermError(
                            f"SegList VarSeg bound to non-sequence value: "
                            f"{type(v).__name__} ({v!r}); VarSegs of a SegList "
                            f"must bind to list/str."
                        )
                    new_segs.append(VarSeg(v))

        # If no VarSegs remain, return a plain Python list of the elements.
        if all(isinstance(s, ConcreteSeg) for s in new_segs):
            result = []
            for s in new_segs:
                result.extend(s.elements)
            return result

        # Clean up empty ConcreteSegs
        new_segs = [s for s in new_segs
                    if not (isinstance(s, ConcreteSeg) and not s.elements)]
        if not new_segs:
            return []
        return SegList(new_segs)

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
        """Called by C do_unify. Drives the trail-free :func:`_seg_split_gen`
        one split per call against a list/str target, so repeated calls with
        the same ``(other, trail)`` enumerate every valid split rather than
        committing to the first.

        The C ``do_unify`` protocol hook is bool-valued, so we expose the
        non-determinism by caching the generator on ``self._unify_gens``
        keyed by ``(target-content, trail-identity)``.  Each call advances
        the cached generator by one step:

        * First call with a given ``(other, trail)`` creates the generator
          (via :func:`_seg_split_gen`) and pulls its first split — the
          target VarSegs are bound on ``trail`` and ``True`` is returned.
        * Subsequent calls resume the generator, undoing the previous
          split's bindings (a no-op if the caller already wound past them
          via ``trail.undo(mark)``) and yielding the next split.
        * When the generator is exhausted the cache entry is dropped and
          ``False`` is returned; a future call after the trail is reset
          re-enters from the first split.

        This makes the failure mode flagged by ledger entry F015 visible
        via the standard ``mark()`` / ``unify()`` / ``undo(mark)`` drive
        pattern: four calls in a row against ``[*A, *B] = [1, 2, 3]``
        surface all four splits.
        """
        from .logic.variables import unify, walk
        if isinstance(other, bytes):
            # Codes-model symmetry (A01-F007): the C layer unifies plain
            # int-lists with bytes, and SegBytes accepts list targets — so a
            # SegList of codes must accept a bytes target too. Convert to the
            # code list (list(b"GET") == [71, 69, 84]) and reuse the list path;
            # the conversion is deterministic, so cached retry drives stay
            # consistent.
            return self.__unify__(list(other), trail)
        if isinstance(other, (list, str)):
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
                if isinstance(other, str):
                    other = [char_atom(c) for c in other]
                return unify(walked, other, trail)
            # Non-ground — drive the cached split enumerator one step.
            # String targets pass through directly (list/str slicing both
            # yield the right shape). The cache holds a trail-free enumerator
            # so it never pins the trail (A01-F005).
            concrete_len = sum(len(s.elements) for s in walked.segments
                               if isinstance(s, ConcreteSeg))
            return _drive_seg_unify(self._unify_gens, walked, other, trail,
                                    concrete_len, _apply_seglist_split)
        if isinstance(other, SegList):
            return NotImplemented
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
        if isinstance(other, str):
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
                ok = ok and unify(seg.var, target_list[pos:pos + sz], trail)
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

    __slots__ = ("_segments", "_unify_gens")

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
        # F016 fix — per-(target, trail) generator cache; see
        # ``SegList.__init__`` / ``SegList.__unify__`` for the rationale.
        self._unify_gens: dict = {}

    @property
    def segments(self) -> list:
        return self._segments

    # ── Walk / normalisation ──────────────────────────────────────────────────

    def __walk__(self):
        """Called by C do_walk. Normalise: collapse bound VarSegs, merge
        adjacent strings. Returns a plain ``str`` when fully ground."""
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
                    walked_inner = v.__walk__()
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
        return isinstance(self.__walk__(), str)

    def to_str(self) -> str:
        """Walk and join. Raises ``TypeError`` if not fully ground."""
        w = self.__walk__()
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

        Against ``str``: drives ``_segstring_unify_gen`` one split per call
        so repeated calls with the same ``(other, trail)`` enumerate every
        valid split (mirror of :meth:`SegList.__unify__` — see its
        docstring for the full rationale; F016 in the ledger).
        Against ``list``: convert string segments to char elements and
        delegate.
        """
        from .logic.variables import unify
        if isinstance(other, str):
            walked = self.__walk__()
            if isinstance(walked, str):
                return walked == other
            # Non-ground — trail-free split-drive (A01-F005).
            concrete_len = sum(len(s) for s in walked.segments
                               if isinstance(s, str))
            return _drive_seg_unify(self._unify_gens, walked, other, trail,
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
            walked = self.__walk__()
            if isinstance(walked, str):
                return unify(walked, other, trail)
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
        w = self.__walk__()
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
        w = self.__walk__()
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
        w = self.__walk__()
        if isinstance(w, str):
            return char_atom(w[index]) if isinstance(index, int) else w[index]
        chars: list[str] = []
        for seg in w._segments:
            if isinstance(seg, str):
                chars.extend(seg)
            else:
                if isinstance(index, int) and 0 <= index < len(chars):
                    return char_atom(chars[index])
                # In-prefix forward slice is knowable (A01-F010); return a
                # str to match ground SegString slicing.
                if _slice_within_prefix(index, len(chars)):
                    return "".join(chars)[index]
                raise PartialTermError(
                    f"SegString[{index!r}] requires resolving an unbound "
                    f"VarSeg; only the concrete prefix (indices "
                    f"0..{len(chars) - 1}) is knowable. SegString={self!r}"
                )
        prefix = "".join(chars)
        return char_atom(prefix[index]) if isinstance(index, int) else prefix[index]

    def __repr__(self):
        return f"SegString({self._segments!r})"

    def __eq__(self, other):
        if isinstance(other, SegString):
            return self._segments == other._segments
        if isinstance(other, str):
            w = self.__walk__()
            return w == other if isinstance(w, str) else False
        if isinstance(other, list):
            # Symmetric with SegList — char-list unifies with str at runtime.
            w = self.__walk__()
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
                ok = ok and unify(seg.var, target_str[pos:pos + sz], trail)
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

    __slots__ = ("_segments", "_unify_gens")

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
        self._unify_gens: dict = {}

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
        if isinstance(other, bytes):
            walked = self.__walk__()
            if isinstance(walked, bytes):
                return walked == other
            # Non-ground — trail-free split-drive (A01-F005).
            concrete_len = sum(len(s) for s in walked.segments
                               if isinstance(s, bytes))
            return _drive_seg_unify(self._unify_gens, walked, other, trail,
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
    """
    __slots__ = ("_data", "_position")

    def __init__(self, data: dict, *, _position=None):
        self._data = dict(data)  # defensive copy
        self._position = _position  # Slice G

    @property
    def data(self) -> dict:
        return self._data

    def keys(self):   return self._data.keys()
    def values(self): return self._data.values()
    def items(self):  return self._data.items()
    def __len__(self): return len(self._data)
    def __getitem__(self, key): return self._data[key]
    def __contains__(self, key): return key in self._data
    def __iter__(self):          return iter(self._data)  # yields keys, like Python dict

    def __eq__(self, other):
        if isinstance(other, DictTerm):
            return self._data == other._data
        if isinstance(other, dict):
            return self._data == other
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
            other_data = other._data
        elif isinstance(other, dict):
            other_data = other
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
    scale. Trailing zeros are allowed (7.890 == 7.89). `value` is already Decimal."""
    scale = currency.scale
    if value != value.quantize(Decimal(1).scaleb(-scale)):
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


def _quantize_to_scale(value, scale, mode_str):
    """Quantize a Decimal to `scale` decimal places using a mode string."""
    rounding = _MONEY_ROUNDING.get(mode_str)
    if rounding is None:
        raise ValueError(f"unknown rounding mode {mode_str!r}; expected one of "
                         f"{sorted(_MONEY_ROUNDING)}")
    return value.quantize(Decimal(1).scaleb(-scale), rounding=rounding)


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


def _dims_str(dims: dict) -> str:
    """Human-readable dimension string, e.g. 'm·s^-2'."""
    if not dims:
        return "1"
    parts = []
    for k in sorted(dims, key=_dim_name):
        v = dims[k]
        name = _dim_name(k)
        parts.append(name if v == 1 else f"{name}^{v}")
    return "·".join(parts)


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
        return Decimal(str(x))
    if isinstance(x, str):
        return Decimal(x)
    raise TypeError(f"cannot coerce {x!r} to a Decimal currency amount")


class Quantity:
    """A number with physical dimensions for dimensional analysis.

    ``dims`` maps dimension keys (unit predicate objects) to integer exponents.
    Zero-valued exponents are removed automatically.  The empty dict means
    dimensionless.  Internally all values are stored in SI base units; named-unit
    predicates (``Metre``, ``Newton``, ``Watt``, …) in ``clausal.modules.units``
    handle scaling on the way in/out.

    Arithmetic:
        - ``+`` / ``-`` require identical dimension dicts; raises ``UnitsMismatch``
          otherwise.
        - ``*`` / ``/`` merge dimension dicts by addition / subtraction.
        - ``**`` scales every exponent by an integer constant; raises
          ``UnitsMismatch`` if the exponent is non-integer or has dimensions.
        - Plain numeric scalars (int/float) can be multiplied/divided freely.

    Clausal protocol:
        - ``__unify__`` — checks dims equality then unifies values.

    Uninstantiated dimensioned slots are plain ``AttVar`` objects carrying a
    ``"units"`` attribute (see ``clausal.logic.units_constraint``).  A
    ``Quantity`` always holds a ground numeric value — never a logic var.
    """

    __slots__ = ("_value", "_dims")

    def __init__(self, value, dims) -> None:
        if isinstance(dims, Quantity):
            # dims is a Quantity constant (e.g. Kilometer) — multiply:
            # Quantity(5, Kilometer) → Quantity(5 * 1000, {Metre: 1})
            a, b = self._num_pair(value, dims._value)
            self._value = a * b
            self._dims = dims._dims
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
        self._dims = MappingProxyType({k: v for k, v in actual_dims.items() if v != 0})
        if not isinstance(self._value, Decimal):
            for _k in self._dims:
                if getattr(_k, "is_currency", False):
                    self._value = _to_decimal(self._value)
                    break
        # Precision check only when TAGGING a raw number as a currency (dims is a
        # currency predicate). Arithmetic results pass a dims dict and are exempt.
        if getattr(dims, "is_currency", False):
            _check_currency_precision(self._value, dims)

    def __call__(self, value):
        """Scale this quantity by *value* — ``Byte(4)`` is ``4 * Byte`` (F048).

        Lets a scaled-unit constant (e.g. ``Byte``, ``mebi``) be used in the
        published ``n(Unit)`` call style, mirroring ``_UnitsPredicate.__call__``.
        """
        return Quantity(value, self)

    # ── Properties ──────────────────────────────────────────────────────────

    @property
    def value(self):
        return self._value

    @property
    def dims(self) -> MappingProxyType:
        return self._dims

    # ── Internal helpers ────────────────────────────────────────────────────

    def _require_same_dims(self, other: "Quantity", op: str) -> None:
        if not isinstance(other, Quantity):
            raise UnitsMismatch(
                f"Cannot {op} dimensioned ({_dims_str(self._dims)}) "
                f"with plain value {other!r}"
            )
        if self._dims != other._dims:
            raise UnitsMismatch(
                f"Unit mismatch for {op}: "
                f"{_dims_str(self._dims)} vs {_dims_str(other._dims)}"
            )

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
    def _num_pair(a, b):
        """Return (a, b) with a plain float coerced to Decimal when the other
        operand is a Decimal, so Decimal arithmetic never raises TypeError and
        stays exact. Uses Decimal(str(f)) — never Decimal(f) — and leaves ints
        alone (Decimal op int is already exact)."""
        if isinstance(a, Decimal) and isinstance(b, float) and not isinstance(b, bool):
            return a, Decimal(str(b))
        if isinstance(b, Decimal) and isinstance(a, float) and not isinstance(a, bool):
            return Decimal(str(a)), b
        return a, b

    # ── Arithmetic ──────────────────────────────────────────────────────────

    def __add__(self, other):
        if isinstance(other, (int, float, Decimal)) and not self._dims:
            a, b = self._num_pair(self._value, other)
            return Quantity(a + b, {})
        self._require_same_dims(other, "add")
        a, b = self._num_pair(self._value, other._value)
        return Quantity(a + b, self._dims)

    def __radd__(self, other):
        if isinstance(other, (int, float, Decimal)) and not self._dims:
            a, b = self._num_pair(other, self._value)
            return Quantity(a + b, {})
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, (int, float, Decimal)) and not self._dims:
            a, b = self._num_pair(self._value, other)
            return Quantity(a - b, {})
        self._require_same_dims(other, "subtract")
        a, b = self._num_pair(self._value, other._value)
        return Quantity(a - b, self._dims)

    def __rsub__(self, other):
        if isinstance(other, (int, float, Decimal)) and not self._dims:
            a, b = self._num_pair(other, self._value)
            return Quantity(a - b, {})
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, +1)
            a, b = self._num_pair(self._value, other._value)
            return Quantity(a * b, new_dims)
        a, b = self._num_pair(self._value, other)
        return Quantity(a * b, self._dims)

    def __rmul__(self, other):
        a, b = self._num_pair(other, self._value)
        return Quantity(a * b, self._dims)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, -1)
            a, b = self._num_pair(self._value, other._value)
            return Quantity(a / b, new_dims)
        a, b = self._num_pair(self._value, other)
        return Quantity(a / b, self._dims)

    def __rtruediv__(self, other):
        new_dims = {k: -v for k, v in self._dims.items()}
        a, b = self._num_pair(other, self._value)
        return Quantity(a / b, new_dims)

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
            # Dimensionless: allow any numeric exponent (e.g. sqrt via ** 0.5)
            return Quantity(self._value ** exp, {})
        new_dims = {k: v * exp for k, v in self._dims.items() if v * exp != 0}
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
        return f"Quantity({self._value!r}, {self._dims!r})"

    def __str__(self) -> str:
        return f"{self._value} {_dims_str(self._dims)}"

    def __format__(self, spec: str) -> str:
        cur = None
        if len(self._dims) == 1:
            (key, exp), = self._dims.items()
            if exp == 1 and getattr(key, "is_currency", False):
                cur = key
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

def list_to_cons(lst: list) -> object:
    """Convert a Python list to explicit Prolog-style cons structure.

    list_to_cons([1, 2, 3])  →  Compound("cons", (1, Compound("cons", (2, ...))))
    """
    result: object = Compound("nil", ())
    for elem in reversed(lst):
        result = Compound("cons", (elem, result))
    return result


def cons_to_list(term: object) -> list:
    """Convert a Prolog-style cons structure back to a Python list.

    Raises ValueError if term is not a proper nil-terminated cons chain.
    """
    result = []
    while isinstance(term, Compound) and term.functor == "cons" and len(term.args) == 2:
        result.append(term.args[0])
        term = term.args[1]
    if not (isinstance(term, Compound) and term.functor == "nil" and len(term.args) == 0):
        raise ValueError(f"Not a proper list: {term!r}")
    return result


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


def _get_undefined() -> "_UndefinedType":
    """Module-level factory used by ``_UndefinedType.__reduce__`` (picklable)."""
    return Undefined



Undefined = _UndefinedType()


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
    if isinstance(t, bool):
        return str(t)
    if isinstance(t, Decimal):
        return _c(str(t), 'number', style)
    if isinstance(t, (int, float, complex)):
        return _c(repr(t), 'number', style)
    if isinstance(t, str):
        # A STRING (THE FLIP, spec §6.7).  The colour role ``'string'`` finally
        # means what it says.  ``writeq`` prints it as a double-quoted string
        # token; ``write`` prints the bare text.  ``repr`` is gone: it picks
        # its own quotes by content, so ``"it's"`` came out single-quoted --
        # an ATOM to any reader.
        #
        # The EMPTY string is the empty list and prints ``[]`` in both
        # families (spec §6.7's table row), which is also what the list
        # branch below prints for ``[]``: the two spellings of one term
        # render alike.
        if t == "":
            return _c('[]', 'bracket', style, _bd)
        if not double_quotes:
            # ISO ``write_term(T, [])``: the string is the LIST of its char
            # atoms, so print it as that list, each char quoted per *quoted*
            # (Task 15 item 4; Scryer's own default).
            return _char_list_str(t, style, _bd, quoted, sep)
        return _c(quote_string(t) if quoted else t, 'string', style)
    if isinstance(t, bytes):
        # A CODE LIST (spec §5.4).  Under ``double_quotes(false)`` — the ISO
        # family — it prints as the list of code NUMBERS it denotes, so
        # ``write(b"ab")`` gives ``[97,98]`` and ``write(b"")`` gives ``[]``,
        # matching what ISO prints for the equal ``[97, 98]`` (fix round 1,
        # item 5).  The display family keeps the ``b'ab'`` spelling §6.7
        # records as "as today".
        if double_quotes:
            return repr(t)
        if not t:
            return _c('[]', 'bracket', style, _bd)
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
    if type(t) is tuple and t and type(t[0]) is str:
        # A CELL -- ``("pt", 1, 2)``.  P3-2 Task 2 (THE FLIP) makes this how
        # every compound term is represented, so the reader must see
        # ``pt(1, 2)``, the term they wrote, not a Python tuple repr.
        # Rendered exactly like the ``Compound`` branch below (same locale
        # name, same rainbow brackets), which is the shape it replaced.
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
        if len(t) == 1:
            # An ATOM -- an arity-0 cell (spec §6.7).  It is a name, not a
            # zero-argument call, so it prints bare (``flag``), never
            # ``flag()``.  Unlike the functor position above, an atom in an
            # ARGUMENT position must re-read as itself, so the writeq family
            # (``quoted=True``, the default) quotes it when ISO 6.4.2 says
            # it would not (``'foo bar'``); the write/1 display family
            # (``quoted=False``) always prints the bare spelling.
            # Locale translation happens BEFORE quoting (the translated
            # spelling is what has to re-read), and keeps the arity-0
            # lookup this branch had when it still printed ``flag()``.
            display = _locale_name(display_functor, style, 0)
            if quoted and not is_mangled(functor) and atom_needs_quotes(display):
                display = quote_atom(display)
            return _c(display, 'atom', style)
        args = t[1:]
        functor_s = _c(_locale_name(display_functor, style, len(args)), 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        return functor_s + ob + sep.join(
            term_str(a, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for a in args) + cb
    if type(t) is tuple and t and t[0] is TUPLE_TAG:
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
    if isinstance(t, Compound):
        functor = deref(t.functor)  # A01-F003: bound functor Var renders as its value, not anon
        functor_raw = _locale_name(functor, style, len(t.args)) if isinstance(functor, str) else term_str(functor, style, _bd, quoted=quoted, double_quotes=double_quotes, sep=sep)
        functor_s = _c(functor_raw, 'atom', style) if isinstance(functor, str) else functor_raw
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args_str = sep.join(term_str(a, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep) for a in t.args)
        return functor_s + ob + args_str + cb
    if isinstance(t, KWTerm):
        functor_s = _c(_locale_name(t.functor, style, len(t)), 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args = sep.join(f"{k}={term_str(v, style, _bd + 1, quoted=quoted, double_quotes=double_quotes, sep=sep)}" for k, v in t.items())
        return functor_s + ob + args + cb
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
        from clausal.logic.predicate import PredicateMeta, is_term_instance, term_field_names
        # Zero-arity atom class (the class IS the value).
        if isinstance(t, type) and isinstance(t, PredicateMeta) and not t._fields:
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

    Shapes ISO gives no canonical form for — ``KWTerm``, ``DictTerm``,
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
    if isinstance(t, bool):
        return str(t)
    if isinstance(t, Decimal):
        return str(t)
    if isinstance(t, (int, float, complex)):
        return repr(t)
    if isinstance(t, str):
        # A STRING (THE FLIP) — the list of its char atoms, so it prints as
        # the cons structure that list denotes (spec §6.7, Scryer-verified):
        # ``"abc"`` -> ``'.'(a,'.'(b,'.'(c,[])))``, ``""`` -> ``[]``.
        # ``write_canonical/1`` ignores the ``double_quotes`` flag by design,
        # which is why there is no mode to consult here.
        out = "[]"
        for c in reversed(t):
            out = "'.'(" + _quoted_atom_spelling(c) + "," + out + ")"
        return out
    if isinstance(t, bytes):
        return repr(t)
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
    if type(t) is tuple and t and type(t[0]) is str:
        # A CELL.  Slot 0 read RAW, no deref -- the recognition rule every
        # cell site uses.  An arity-0 cell is an atom and prints bare.
        head = _quoted_atom_spelling(t[0])
        if len(t) == 1:
            return head
        return head + "(" + ",".join(term_canonical(a) for a in t[1:]) + ")"
    if type(t) is tuple and t and t[0] is TUPLE_TAG:
        return "(" + ",".join(term_canonical(e) for e in t[1:]) + ")"
    if isinstance(t, Compound):
        f = deref(t.functor)
        head = _quoted_atom_spelling(f) if isinstance(f, str) else term_canonical(f)
        return head + "(" + ",".join(term_canonical(a) for a in t.args) + ")"
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

    if isinstance(t, Compound):
        if not t.args:
            return flat
        functor = deref(t.functor)  # A01-F003: bound functor Var renders as its value, not anon
        functor_raw = functor if isinstance(functor, str) else term_pformat(functor, child, width, style, _bd)
        functor_s = _c(functor_raw, 'atom', style) if isinstance(functor, str) else functor_raw
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(a) for a in t.args]
        return functor_s + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if type(t) is tuple and t and type(t[0]) is str:
        # A str-functor CELL -- the Compound-equivalent multi-line treatment
        # (P3-2 Task 7): a wide cell used to fall through every isinstance
        # branch above straight to ``return flat``, so a long ``pt(1, 2)``
        # never got the indented form a wide ``Compound`` gets.  Slot 0 read
        # RAW, no deref, matching every other cell recognition site (Task 5).
        args = t[1:]
        if not args:
            return flat
        functor_s = _c(t[0], 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(a) for a in args]
        return functor_s + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if type(t) is tuple and t and t[0] is TUPLE_TAG:
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

    if isinstance(t, KWTerm):
        functor_s = _c(t.functor, 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [f"{k} = {_r(v)}" for k, v in t.items()]
        return functor_s + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

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
    if isinstance(t, str):
        # A STRING -- the same writeq spelling ``term_str`` produces (spec
        # §6.7): a double-quoted string token, and ``[]`` for the empty
        # string, which is the empty list.
        if t == "":
            return _html_c('[]', 'bracket', _bd)
        return _html_c(esc(quote_string(t)), 'string')
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
    if isinstance(t, Compound):
        functor = deref(t.functor)  # A01-F003: bound functor Var renders as its value, not anon
        functor_raw = functor if isinstance(functor, str) else term_html(functor, _bd)
        functor_s = _html_c(esc(functor_raw), 'atom') if isinstance(functor, str) else functor_raw
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t.args)
        return functor_s + ob + args_str + cb
    if type(t) is tuple and t and type(t[0]) is str:
        # A str-functor CELL -- the ``Compound`` branch above's exact
        # counterpart (P3-2 Task 7); without this a cell fell through to the
        # ``esc(repr(t))`` tail, leaking the Python tuple repr into Jupyter
        # output.  Slot 0 read RAW, no deref (Task 5's rule).
        if len(t) == 1:
            # An ATOM -- an arity-0 cell prints as its (quoted) name, never
            # as ``flag()`` (spec §6.7); ``term_str`` owns that spelling.
            return _html_c(esc(term_str(t)), 'atom')
        functor_s = _html_c(esc(t[0]), 'atom')
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t[1:])
        return functor_s + ob + args_str + cb
    if type(t) is tuple and t and t[0] is TUPLE_TAG:
        # A tuple-DATA cell -- plain tuple display, brackets only.
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(e, _bd + 1) for e in t[1:])
        return ob + args_str + cb
    if isinstance(t, KWTerm):
        functor_s = _html_c(esc(t.functor), 'atom')
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args = ", ".join(f"{esc(k)}={term_html(v, _bd + 1)}" for k, v in t.items())
        return functor_s + ob + args + cb
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
    "Compound",
    "DictTerm",
    "SetTerm",
    "KWTerm",
    "SegList",
    "SegString",
    "SegBytes",
    "ConcreteSeg",
    "VarSeg",
    "PyThunk",
    "FStringThunk",
    # Units
    "Quantity",
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
    "list_to_cons",
    "cons_to_list",
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
