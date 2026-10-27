"""Iterative, cycle-aware twins of the engine's four term walkers.

``copy_term/2``, ``_deref_walk`` (the answer and findall snapshot),
``ground/1`` and ``term_variables/2`` each walk a term by a recursive
descent -- the C walkers in ``variables/_variables.c`` and
``_tabling_core.c``, one frame per level, capped at ``MAX_DEPTH`` -- which
is the fast path every ordinary term takes.  Two terms defeat it: a CYCLIC
term (ISO 7.3.2 lets ``=/2`` build ``X = f(X)``; the descent re-enters the
cell forever) and an acyclic term nested deeper than the cap.  Until
2026-10-24 both raised a raw ``RecursionError`` where Scryer answers --
``X = f(X), copy_term(X, Y)`` copies the cycle, ``ground(X)`` is true,
``term_variables(X, [])``, ``findall(X, true, [f(...)])``.

The walkers here are what the C wrappers (and the pure-Python twins when
there is no C) run INSTEAD when their descent raises RecursionError: an
explicit stack, so depth costs no frames, and for the two rebuilders a set
of the compounds whose copy is in progress.  A cycle in a term passes
through a bound variable into a compound already in progress (cells are
immutable tuples, so nothing else can close one); its copy is a fresh
variable -- the KNOT -- that is bound to the rebuilt compound once that
compound is complete.  The binding is made through a trail nobody keeps,
so nothing ever undoes it: the copy is as cyclic as the original and as
independent of the trail as any copy (a findall row survives backtracking
out of the goal that built the cycle).  The read-only walkers only need a
visited set.

Each walker answers exactly what its recursive twin answers on a term the
twin can walk (the shapes, the leaf rules and the identity short-circuits
are the twins', case for case; ``tests/test_python_fallbacks.py`` holds
the parity corpus) -- it is a fallback, not a second semantics.
"""
from __future__ import annotations

from typing import Any

from clausal.logic.cells import is_chars, flat_carrier
from clausal.logic.predicate import field_names_for, is_term_instance, term_field_names
from clausal.logic.variables import Trail, Var, deref, is_var, unify
from clausal.terms import (ConcreteSeg, DictTerm, Quantity, SegBytes, SegList,
                           SegListView, SegString, VarSeg)

#: The leaves every walker returns as they are (``_deref_walk_py`` adds
#: ``complex``; ``None`` is tested separately, it is not a type).
_ATOMIC = (bool, int, float, str, bytes, complex)

_LEAF = object()
_FRAME = object()


class _Frame:
    """One compound being rebuilt: its children still to visit, the values
    built so far, how to finish, and the knot variable a cycle back into
    it is copied as (None until a cycle reaches it)."""

    __slots__ = ("orig", "children", "built", "i", "finish", "knot")

    def __init__(self, orig: Any, children: list, finish) -> None:
        self.orig = orig
        self.children = children
        self.built: list = []
        self.i = 0
        self.finish = finish
        self.knot = None


def _tie(knot: Any, value: Any) -> None:
    """Bind *knot* to *value* for good: the trail that records it is
    dropped here, and a dropped trail undoes nothing."""
    unify(knot, value, Trail())


def _rebuild(root: Any, opener, leaf_var) -> Any:
    """Post-order rebuild of *root*: *opener(d)* says how a non-atomic,
    non-variable *d* is rebuilt -- ``(_LEAF, value)`` or ``(_FRAME,
    children, finish)`` -- and *leaf_var(v)* what an unbound variable
    becomes."""
    d = deref(root)
    if is_var(d):
        return leaf_var(d)
    if d is None or isinstance(d, _ATOMIC):
        return d
    opened = opener(d)
    if opened[0] is _LEAF:
        return opened[1]
    top = _Frame(d, opened[1], opened[2])
    frames = [top]
    active = {id(d): top}
    result = None
    while frames:
        frame = frames[-1]
        if frame.i < len(frame.children):
            child = deref(frame.children[frame.i])
            frame.i += 1
            if is_var(child):
                frame.built.append(leaf_var(child))
                continue
            if child is None or isinstance(child, _ATOMIC):
                frame.built.append(child)
                continue
            open_frame = active.get(id(child))
            if open_frame is not None:
                # A cycle: back into a compound whose copy is in progress.
                if open_frame.knot is None:
                    open_frame.knot = Var()
                frame.built.append(open_frame.knot)
                continue
            opened = opener(child)
            if opened[0] is _LEAF:
                frame.built.append(opened[1])
                continue
            child_frame = _Frame(child, opened[1], opened[2])
            active[id(child)] = child_frame
            frames.append(child_frame)
        else:
            frames.pop()
            del active[id(frame.orig)]
            value = frame.finish(frame.built)
            if frame.knot is not None:
                _tie(frame.knot, value)
            if frames:
                frames[-1].built.append(value)
            else:
                result = value
    return result


# ── _deref_walk ──────────────────────────────────────────────────────────────

def _open_walk(d: Any):
    """``_deref_walk_py`` / ``do_deref_walk``, shape by shape."""
    if isinstance(d, list):
        return (_FRAME, list(d), _as_list)
    if isinstance(d, tuple):
        if is_chars(d):
            return (_LEAF, flat_carrier(d))
        return (_FRAME, list(d), tuple)
    if isinstance(d, dict):
        children: list = []
        for k, v in d.items():
            children.append(k)
            children.append(v)
        return (_FRAME, children, _as_dict)
    if isinstance(d, (set, frozenset)):
        return (_FRAME, list(d), type(d))
    if type(d) is SegList:
        # Its holes resolved here, its ELEMENTS walked by this walk: the
        # hook (``__walk__``) walks them recursively, which is what failed
        # for an element too deep or cyclic for it (``[Y]``, ``Y = f(Y)``).
        shallow = d._walk_raw(deep=False)
        if isinstance(shallow, list):
            return (_FRAME, shallow, _promoted_list)
        if isinstance(shallow, SegList):
            return (_FRAME, list(shallow.segments), SegList)
        return _open_walk(shallow)          # an improper list's cons cells
    if type(d) is SegListView:
        # The rest of a long list, as a window of it: its elements, walked
        # here (its ``__walk__`` walks them recursively), to a plain list.
        return (_FRAME, d.elements(), _as_list)
    hook = getattr(d, "__walk__", None)
    if hook is not None:
        return (_LEAF, hook())
    if is_term_instance(d):
        names = term_field_names(d)
        return (_FRAME, [getattr(d, n) for n in names], _term_builder(type(d), names))
    return (_LEAF, d)


def _promoted_list(built: list):
    """A closed SegList's elements, as its ``__walk__`` gives them: a char
    list promoted to its ``str`` (F018)."""
    from clausal.logic.runtime._seg_helpers import maybe_promote_to_str  # noqa: PLC0415
    return maybe_promote_to_str(built)


def _as_list(built: list) -> list:
    return built


def _as_dict(built: list) -> dict:
    return dict(zip(built[0::2], built[1::2]))


def _term_builder(cls, names):
    def finish(built: list):
        return cls(**dict(zip(names, built)))
    return finish


def deref_walk_iterative(term: Any) -> Any:
    """``_deref_walk`` for a term too deep or cyclic for the recursive
    walkers: bindings resolved, unbound variables kept, a cycle tied with
    a knot variable."""
    return _rebuild(term, _open_walk, lambda v: v)


# ── copy_term ────────────────────────────────────────────────────────────────

def copy_term_iterative(term: Any, var_map: dict, attvars: list | None = None) -> Any:
    """``_copy_term_py`` / ``c_copy_term`` for a term too deep or cyclic for
    them: every unbound variable fresh (shared through *var_map*, keyed by
    the original's id), a cycle copied as a cycle.

    Every attributed variable met is reported to *attvars* once per call,
    whether or not *var_map* already held its copy: this walk runs after a
    recursive attempt that may have mapped (and reported) some variables
    and then been undone, and the caller drops that attempt's reports.  A
    variable the caller mapped in an EARLIER call may be reported again;
    ``_copy_attributes`` tolerates a repeat (its ``seen`` set)."""
    reported: set = set()

    def fresh(v):
        vid = id(v)
        got = var_map.get(vid)
        if got is None:
            got = var_map[vid] = Var()
        if (attvars is not None and vid not in reported
                and getattr(v, "attrs", None)):
            reported.add(vid)
            attvars.append((v, got))
        return got

    def opener(d):
        if field_names_for(d) == ():
            return (_LEAF, d)
        if isinstance(d, list):
            return (_FRAME, list(d), _as_list)
        if type(d) is tuple:
            return (_FRAME, list(d), _tuple_unless_unchanged(d))
        if isinstance(d, SegList):
            return (_FRAME, list(d.segments), SegList)
        if isinstance(d, (SegString, SegBytes)):
            return (_FRAME, list(d.segments), type(d))
        if type(d) is DictTerm or type(d) is dict:
            data = d.data if type(d) is DictTerm else d
            return (_FRAME, list(data.values()), _dict_unless_unchanged(d, data))
        if is_term_instance(d):
            names = term_field_names(d)
            return (_FRAME, [getattr(d, n) for n in names], _term_builder(type(d), names))
        return (_LEAF, d)

    return _rebuild(term, opener, fresh)


def _tuple_unless_unchanged(orig: tuple):
    def finish(built: list):
        if all(new is old for new, old in zip(built, orig)):
            return orig
        return tuple(built)
    return finish


def _dict_unless_unchanged(orig, data: dict):
    def finish(built: list):
        if all(new is old for new, old in zip(built, data.values())):
            return orig
        copied = dict(zip(data.keys(), built))
        return DictTerm(copied) if type(orig) is DictTerm else copied
    return finish


# ── ground/1 and term_variables/2 ────────────────────────────────────────────

def _children(d: Any) -> list | None:
    """The sub-terms of *d* in left-to-right order, for the read-only
    walkers (``_is_ground_py`` / ``_collect_vars_py``, shape by shape), or
    None for a leaf."""
    if isinstance(d, list):
        return list(d)
    if type(d) is tuple:
        return list(d)
    if isinstance(d, SegList):
        out: list = []
        for seg in d.segments:
            if isinstance(seg, ConcreteSeg):
                out.extend(seg.elements)
            elif isinstance(seg, VarSeg):
                out.append(seg.var)
            else:
                out.append(seg)
        return out
    if isinstance(d, (SegString, SegBytes)):
        out = []
        for seg in d.segments:
            if isinstance(seg, (str, bytes)):
                continue
            out.append(seg.var if isinstance(seg, VarSeg) else seg)
        return out
    if type(d) is DictTerm:
        return list(d.data.values())
    if type(d) is dict:
        return list(d.values())
    if is_term_instance(d):
        return [getattr(d, n) for n in term_field_names(d)]
    return None


def is_ground_iterative(term: Any) -> bool:
    """``ground/1`` for a term too deep or cyclic for the recursive walkers."""
    stack = [term]
    seen: set = set()
    keep: list = []
    while stack:
        d = deref(stack.pop())
        if is_var(d):
            return False
        if d is None or isinstance(d, (bool, int, float, str, bytes)):
            continue
        if id(d) in seen:
            continue
        seen.add(id(d))
        keep.append(d)
        children = _children(d)
        if children:
            stack.extend(children)
    return True


def collect_vars_iterative(term: Any, result: list) -> None:
    """``term_variables/2``'s walk for a term too deep or cyclic for the
    recursive walkers: every unbound variable once, in order of first
    appearance left to right, appended to *result*."""
    seen_vars = {id(v) for v in result}
    stack = [term]
    visited: set = set()
    keep: list = []
    while stack:
        d = deref(stack.pop())
        if is_var(d):
            if id(d) not in seen_vars:
                seen_vars.add(id(d))
                result.append(d)
            continue
        if d is None or isinstance(d, (bool, int, float, str, bytes)):
            continue
        if field_names_for(d) == ():
            continue
        if id(d) in visited:
            continue
        visited.add(id(d))
        keep.append(d)
        children = _children(d)
        if children:
            stack.extend(reversed(children))


def _dif_children(d: Any) -> list | None:
    """The sub-terms ``dif/2``'s variable walk descends into, shape for
    shape (the C ``collect_children`` in ``_constraints_dif.c``): what the
    unifier can bind through.  A SetTerm is a leaf (the unifier refuses
    var-element set unification)."""
    if isinstance(d, (tuple, list)):
        return list(d)
    if isinstance(d, DictTerm):
        return list(d.data.values())
    if isinstance(d, dict):
        return list(d.values())
    if isinstance(d, (SegList, SegString, SegBytes)):
        out: list = []
        for seg in d.segments:
            if isinstance(seg, VarSeg):
                out.append(seg.var)
            elif isinstance(seg, ConcreteSeg):
                out.extend(seg.elements)
            # a plain str/bytes segment is ground
        return out
    if isinstance(d, Quantity):
        return [d.value]
    if is_term_instance(d):
        return [getattr(d, n) for n in term_field_names(d)]
    return None


def collect_free_vars_iterative(term: Any, result: list, seen_ids: set) -> None:
    """``dif/2``'s variable walk (``constraints._collect_free_vars``): every
    unbound variable reachable from *term* through what the unifier binds
    through, once (*seen_ids* holds the ids already in *result*), in order
    of first appearance left to right.  Iterative with a visited set, so a
    cyclic term or one nested past the recursion limit ends."""
    stack = [term]
    visited: set = set()
    keep: list = []
    while stack:
        d = deref(stack.pop())
        if is_var(d):
            if id(d) not in seen_ids:
                seen_ids.add(id(d))
                result.append(d)
            continue
        if d is None or isinstance(d, (bool, int, float, str, bytes)):
            continue
        if id(d) in visited:
            continue
        visited.add(id(d))
        keep.append(d)
        children = _dif_children(d)
        if children:
            stack.extend(reversed(children))


def unwalkable_term_error(term: Any, what: str, answer: str = "answer"):
    """The ISO error for a term a RECURSIVE walk at the Python boundary
    could not descend (it raised RecursionError), as a ``LogicException``
    to raise: ``resource_error(finite_memory)`` when *term* is cyclic --
    the engine KNOWS it saw a cycle and *what* has no finite answer for
    one (ruling 2026-10-24, provisional, Scryer's idiom, as for
    ``assertz`` of a cyclic term) -- and ``resource_error(stack)`` for an
    acyclic term merely nested too deep, as ``python_error_term`` maps any
    other depth overflow.  The cycle test is iterative, so it answers for
    the very term that overflowed."""
    from clausal.logic.builtins.inspection import _is_acyclic  # noqa: PLC0415
    from clausal.logic.exceptions import (  # noqa: PLC0415
        LogicException, resource_error)
    if not _is_acyclic(term):
        return LogicException(resource_error(
            "finite_memory",
            f"{what}: a cyclic term (one built with no occurs check, "
            f"X = f(X)) has no finite {answer}"))
    return LogicException(resource_error(
        "stack",
        f"{what}: the term is nested deeper than Python's recursion limit"))
