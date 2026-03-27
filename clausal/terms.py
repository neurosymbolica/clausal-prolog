"""clausal.terms — logic term layer.

Functor types and value types for the clausal logic programming system.

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
from types import MappingProxyType
from typing import Any

from .logic.variables import Var

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
    Unify, DoesNotUnify, Evaluate, ArithEq, ArithNeq, Lt, LtE, Gt, GtE, In, NotIn,
    # Expression nodes used in predicate bodies
    Call, LoadName, LoadAttr, LoadSubscript, Slice,
    # Predicate clause term
    Predicate,
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

    def __str__(self) -> str:
        args_str = ", ".join(term_str(a) for a in self.args)
        f = self.functor if isinstance(self.functor, str) else term_str(self.functor)
        return f"{f}({args_str})"

    def __unify__(self, other, trail) -> bool:
        """Structural unification: same functor and arity, args unified pairwise."""
        if not isinstance(other, Compound):
            return NotImplemented
        if self.functor != other.functor or len(self.args) != len(other.args):
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for a, b in zip(self.args, other.args):
            if not unify(a, b, trail):
                trail.undo(mark)
                return False
        return True



# ── Open-world keyword term ────────────────────────────────────────────────────


class KWTerm:
    """Open-world keyword term — any functor, any keywords, dict-backed.

    For runtime-constructed terms where the functor has no compile-time class.
    Attributes are read from the backing dict.  Iteration yields values in
    insertion order.  Equality and unification match by keyword name (not
    position): ``KWTerm('r', a=1, b=2) == KWTerm('r', b=2, a=1)``.
    """

    __slots__ = ("_functor", "_fields")

    def __init__(self, functor: str, **kwargs: Any) -> None:
        object.__setattr__(self, "_functor", functor)
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


class SegList:
    """A first-class term representing a list with variable-length holes.

    A SegList is a flat sequence of alternating ConcreteSeg and VarSeg objects.
    When every VarSeg's var is bound to a concrete list, the SegList is ground
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

    def __walk__(self):
        """Called by C do_walk. Normalise: collapse bound VarSegs, merge adjacent
        ConcreteSegs. Returns a plain Python list when fully ground."""
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
                    # VarSeg bound to a substring — expand to chars for SegList
                    chars = list(v)
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
                    # Inline nested SegList's segments
                    walked_inner = v.__walk__()
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
                    # Still unbound — keep as VarSeg with walked var
                    new_segs.append(VarSeg(v))

        # If no VarSegs remain, return a plain Python list
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

    def is_ground(self) -> bool:
        """True if all VarSegs are bound — i.e. ``__walk__`` returns a plain list."""
        return isinstance(self.__walk__(), list)

    def to_list(self) -> list:
        """Walk and flatten. Raises ``TypeError`` if not fully ground."""
        w = self.__walk__()
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
        """Called by C do_unify. Deterministic unification of self against other.

        For a plain list or string target: attempt the first valid split and
        return True.  Strings are passed directly (not converted to char lists)
        so that VarSegs bind to substrings preserving str type.
        """
        from .logic.variables import unify, walk
        if isinstance(other, (list, str)):
            walked = self.__walk__()
            if isinstance(walked, list):
                # Fully ground SegList → compare with target
                if isinstance(other, str):
                    return walked == list(other)
                return walked == other
            # Use the generator; take the first solution only.
            # Pass string targets directly — string slicing returns substrings.
            for _ in _seglist_unify_gen(walked, other, trail):
                return True
            return False
        if isinstance(other, SegList):
            return NotImplemented
        return NotImplemented

    # ── Sequence protocol (ground delegation) ────────────────────────────────

    def __len__(self) -> int:
        return len(self.to_list())

    def __iter__(self):
        return iter(self.to_list())

    def __contains__(self, item) -> bool:
        w = self.__walk__()
        if isinstance(w, list):
            return item in w
        # Check ConcreteSegs only — uncertain for VarSegs
        for seg in w._segments:
            if isinstance(seg, ConcreteSeg) and item in seg.elements:
                return True
        return False

    def __getitem__(self, index):
        return self.to_list()[index]

    def __add__(self, other):
        """Lazy concatenation — returns a new SegList."""
        if isinstance(other, list):
            return SegList(self._segments + [ConcreteSeg(other)])
        if isinstance(other, SegList):
            return SegList(self._segments + other._segments)
        return NotImplemented

    def __radd__(self, other):
        if isinstance(other, list):
            return SegList([ConcreteSeg(other)] + self._segments)
        return NotImplemented

    def __eq__(self, other):
        if isinstance(other, SegList):
            return self._segments == other._segments
        if isinstance(other, list):
            w = self.__walk__()
            if isinstance(w, list):
                return w == other
            return False
        return NotImplemented

    def __hash__(self):
        # SegLists are mutable (vars can bind), so not hashable by default
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
                    ok = ok and unify(elem, target_list[pos], trail)
                    pos += 1
            if not ok:
                break
        if ok:
            yield True
        trail.undo(mark)


def _multi_star_splits(n_stars: int, remainder: int):
    """Yield all ways to assign *remainder* items across *n_stars* buckets
    (each bucket ≥ 0).  Equivalent to ``_multi_star_splits`` in compiler.py
    but lives here so runtime code can import it without circular imports.
    """
    if n_stars == 0:
        if remainder == 0:
            yield ()
        return
    if n_stars == 1:
        yield (remainder,)
        return
    for first in range(remainder + 1):
        for rest in _multi_star_splits(n_stars - 1, remainder - first):
            yield (first,) + rest


# ── SegString — segmented partial string ──────────────────────────────────────


class SegString:
    """A SegList-like term backed by string segments instead of list segments.

    Segments are plain ``str`` objects (concrete text) alternating with
    ``VarSeg`` objects (variable-length string holes).  When every VarSeg is
    bound to a string, ``__walk__`` returns a plain Python ``str``.

    Example::

        SegString(["hel", VarSeg(X), "ld"])

    When ``X`` is bound to ``"lo wor"``, walking yields ``"hello world"``.
    VarSegs always bind to ``str`` (substrings), never char lists.
    """

    __slots__ = ("_segments",)

    def __init__(self, segments: list):
        self._segments = list(segments)

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
                    # VarSeg bound to a char list — join into string
                    s = "".join(v)
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
                    # Still unbound — keep as VarSeg
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

        Against ``str``: split by string slicing — VarSegs bind to substrings.
        Against ``list``: convert string segments to char elements and delegate.
        """
        from .logic.variables import unify
        if isinstance(other, str):
            walked = self.__walk__()
            if isinstance(walked, str):
                return walked == other
            for _ in _segstring_unify_gen(walked, other, trail):
                return True
            return False
        if isinstance(other, list):
            # Ground SegString → str, then let C-level str↔list unification
            # (Phase 1) handle the comparison.
            walked = self.__walk__()
            if isinstance(walked, str):
                from .logic.variables import unify as _unify
                return _unify(walked, other, trail)
            # Non-ground: can't unify SegString with list directly
            return NotImplemented
        if isinstance(other, (SegString, SegList)):
            return NotImplemented
        return NotImplemented

    def __repr__(self):
        return f"SegString({self._segments!r})"

    def __eq__(self, other):
        if isinstance(other, SegString):
            return self._segments == other._segments
        if isinstance(other, str):
            w = self.__walk__()
            return w == other if isinstance(w, str) else NotImplemented
        return NotImplemented

    def __hash__(self):
        w = self.__walk__()
        return hash(w) if isinstance(w, str) else id(self)


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


# ── DictTerm — unification-aware dictionary ───────────────────────────────────


class DictTerm:
    """Unification-aware dictionary term.

    Keys must be ground (str, int, or other hashable atoms).
    Values may be Vars, participating in unification.

    Two DictTerms unify iff they have the same key set and values unify pairwise.
    """
    __slots__ = ("_data",)

    def __init__(self, data: dict):
        self._data = dict(data)  # defensive copy

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
        return isinstance(other, DictTerm) and self._data == other._data

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
        """Called by C do_unify: pairwise value unification."""
        if not isinstance(other, DictTerm):
            return NotImplemented
        if self._data.keys() != other._data.keys():
            return False
        from .logic.variables import unify
        mark = trail.mark()
        for key in self._data:
            if not unify(self._data[key], other._data[key], trail):
                trail.undo(mark)
                return False
        return True


# ── SetTerm — unification-aware set ──────────────────────────────────────────


class SetTerm:
    """Unification-aware set term.

    Elements must be ground (hashable). Backed by frozenset for immutability.
    Two SetTerms unify iff they contain the same elements.
    """
    __slots__ = ("_elements",)

    def __init__(self, elements):
        self._elements = frozenset(elements)

    @property
    def elements(self) -> frozenset:
        return self._elements

    def __len__(self): return len(self._elements)
    def __contains__(self, item): return item in self._elements
    def __iter__(self): return iter(self._elements)

    def __eq__(self, other):
        return isinstance(other, SetTerm) and self._elements == other._elements

    def __hash__(self):
        return hash(self._elements)

    def __repr__(self):
        inner = ", ".join(repr(e) for e in sorted(self._elements, key=repr))
        return f"SetTerm({{{inner}}})"

    def __unify__(self, other, trail):
        """Called by C do_unify: element-wise equality (elements are ground)."""
        if not isinstance(other, SetTerm):
            return NotImplemented
        return self._elements == other._elements


# ── Quantity — number with physical dimensions ────────────────────────────────


class UnitsMismatch(Exception):
    """Raised when dimensioned quantities with incompatible units are combined."""


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
            self._value = value * dims._value
            self._dims = dims._dims
            return
        if hasattr(dims, '_dims'):
            # dims is a _UnitsPredicate — extract dims dict
            actual_dims = dims._dims
        else:
            actual_dims = dims
        self._value = value
        self._dims = MappingProxyType({k: v for k, v in actual_dims.items() if v != 0})

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

    # ── Arithmetic ──────────────────────────────────────────────────────────

    def __add__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Quantity(self._value + other, {})
        self._require_same_dims(other, "add")
        return Quantity(self._value + other._value, self._dims)

    def __radd__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Quantity(other + self._value, {})
        return NotImplemented

    def __sub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Quantity(self._value - other, {})
        self._require_same_dims(other, "subtract")
        return Quantity(self._value - other._value, self._dims)

    def __rsub__(self, other):
        if isinstance(other, (int, float)) and not self._dims:
            return Quantity(other - self._value, {})
        return NotImplemented

    def __mul__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, +1)
            return Quantity(self._value * other._value, new_dims)
        return Quantity(self._value * other, self._dims)

    def __rmul__(self, other):
        return Quantity(other * self._value, self._dims)

    def __truediv__(self, other):
        if isinstance(other, Quantity):
            new_dims = self._merge_dims(self._dims, other._dims, -1)
            return Quantity(self._value / other._value, new_dims)
        return Quantity(self._value / other, self._dims)

    def __rtruediv__(self, other):
        new_dims = {k: -v for k, v in self._dims.items()}
        return Quantity(other / self._value, new_dims)

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
        return format(str(self), spec)

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
    __slots__ = ('fn', 'var_objects')

    def __init__(self, fn, var_objects):
        self.fn = fn
        self.var_objects = tuple(var_objects)

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
            Functor names in compound terms and bare names (``LoadName``).
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


def term_str(t: Any, style: TermStyle | None = None, _bd: int = 0) -> str:
    """Return a readable string representation of any term.

    *style* controls anonymous-variable display and optional ANSI colouring;
    defaults to the module-level style (see :func:`set_style`).  *_bd* is the
    bracket-depth counter used internally for rainbow-bracket colouring.
    """
    if style is None:
        style = _current_style
    if t is None:
        return "None"
    if t is ...:
        return "..."
    if isinstance(t, bool):
        return str(t)
    if isinstance(t, (int, float, complex)):
        return _c(repr(t), 'number', style)
    if isinstance(t, str):
        return _c(repr(t), 'string', style)
    if isinstance(t, bytes):
        return repr(t)
    if isinstance(t, list):
        ob = _c('[', 'bracket', style, _bd)
        cb = _c(']', 'bracket', style, _bd)
        return ob + ", ".join(term_str(e, style, _bd + 1) for e in t) + cb
    if isinstance(t, Var):
        return _c(style.anon_var, 'var', style)
    if isinstance(t, Compound):
        functor_raw = _locale_name(t.functor, style, len(t.args)) if isinstance(t.functor, str) else term_str(t.functor, style, _bd)
        functor_s = _c(functor_raw, 'atom', style) if isinstance(t.functor, str) else functor_raw
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args_str = ", ".join(term_str(a, style, _bd + 1) for a in t.args)
        return functor_s + ob + args_str + cb
    if isinstance(t, KWTerm):
        functor_s = _c(_locale_name(t.functor, style, len(t)), 'atom', style)
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args = ", ".join(f"{k}={term_str(v, style, _bd + 1)}" for k, v in t.items())
        return functor_s + ob + args + cb
    if isinstance(t, DictTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        inner = ", ".join(
            f"{term_str(k, style, _bd + 1)}: {term_str(v, style, _bd + 1)}"
            for k, v in t.items()
        )
        return ob + inner + cb
    if isinstance(t, SetTerm):
        ob = _c('{', 'bracket', style, _bd)
        cb = _c('}', 'bracket', style, _bd)
        inner = ", ".join(term_str(e, style, _bd + 1) for e in sorted(t.elements, key=repr))
        return ob + inner + cb
    cls = type(t)
    op = getattr(cls, "op", None)

    # BinOp-style: left op right
    if op is not None and hasattr(t, "left") and hasattr(t, "right"):
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        return ob + term_str(t.left, style, _bd + 1) + f" {op} " + term_str(t.right, style, _bd + 1) + cb

    # UnaryOp-style: op operand
    if op is not None and hasattr(t, "operand"):
        operand_str = term_str(t.operand, style, _bd)
        if op.isalpha():
            return f"{op} {operand_str}"
        return f"{op}{operand_str}"

    if isinstance(t, Call):
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        args_str = ", ".join(term_str(a, style, _bd + 1) for a in t.args)
        return term_str(t.func, style, _bd) + ob + args_str + cb
    if isinstance(t, LoadName):
        return _c(t.name, 'atom', style)
    if isinstance(t, Predicate):
        return f"{term_str(t.head, style, _bd)} <- {term_str(t.body, style, _bd)}"

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
            parts = ", ".join(term_str(getattr(t, f), style, _bd + 1) for f in term_field_names(t))
            return _c(cls_name, 'atom', style) + ob + parts + cb

    return repr(t)


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

    *width* is the line-width budget.  When ``None`` (the default) it is
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
        ob = _c('[', 'bracket', style, _bd)
        cb = _c(']', 'bracket', style, _bd)
        items = [_r(e) for e in t]
        return ob + "\n" + ipad + _join(items) + "\n" + pad + cb

    if isinstance(t, Compound):
        if not t.args:
            return flat
        functor_raw = t.functor if isinstance(t.functor, str) else term_pformat(t.functor, child, width, style, _bd)
        functor_s = _c(functor_raw, 'atom', style) if isinstance(t.functor, str) else functor_raw
        ob = _c('(', 'bracket', style, _bd)
        cb = _c(')', 'bracket', style, _bd)
        items = [_r(a) for a in t.args]
        return functor_s + ob + "\n" + ipad + _join(items) + "\n" + pad + cb

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
    if isinstance(t, (int, float, complex)):
        return _html_c(esc(repr(t)), 'number')
    if isinstance(t, str):
        return _html_c(esc(repr(t)), 'string')
    if isinstance(t, bytes):
        return esc(repr(t))
    if isinstance(t, list):
        ob = _html_c('[', 'bracket', _bd)
        cb = _html_c(']', 'bracket', _bd)
        return ob + ", ".join(term_html(e, _bd + 1) for e in t) + cb
    if isinstance(t, Var):
        return _html_c('_', 'var')
    if isinstance(t, Compound):
        functor_raw = t.functor if isinstance(t.functor, str) else term_html(t.functor, _bd)
        functor_s = _html_c(esc(functor_raw), 'atom') if isinstance(t.functor, str) else functor_raw
        ob = _html_c('(', 'bracket', _bd)
        cb = _html_c(')', 'bracket', _bd)
        args_str = ", ".join(term_html(a, _bd + 1) for a in t.args)
        return functor_s + ob + args_str + cb
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
    "SegString",
    "PyThunk",
    "FStringThunk",
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
    "Unify", "DoesNotUnify", "Evaluate", "ArithEq", "ArithNeq", "Lt", "LtE", "Gt", "GtE", "In", "NotIn",
    # Expression nodes
    "Call", "LoadName", "LoadAttr", "LoadSubscript", "Slice",
    # Predicate clause term
    "Predicate",
]
