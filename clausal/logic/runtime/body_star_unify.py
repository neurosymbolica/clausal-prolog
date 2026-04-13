"""Body-position star-list unification — runtime helpers.

Called by generated compiled code for body ``is``-goals involving
star-unpack patterns (``[X, *Xs] is Foo``).  Handles both directions:
deconstruction (target is a list, vars receive elements) and
construction (target is a Var, vars are bound — build a list).

Also provides ``_in_iter`` for membership enumeration (``elem in coll``
goals) and ``_build_star_list`` / ``_build_multi_star_list`` for
constructing list values that may include star-unpacks.
"""

from __future__ import annotations

from clausal.logic.variables import is_var, deref, unify
from clausal.terms import (
    DictTerm,
    SegList, ConcreteSeg, VarSeg,
    SegString,
    _multi_star_splits,
)

from .list_unify import _head_list_unify_input, _head_list_unify_output


def _body_star_unify(target, before_vals, star_val, after_vals, trail):
    """Bidirectional star-list unification for body-position Is goals.

    Handles both deconstruction (target is a ground list) and construction
    (target is an unbound Var, pattern vars are bound).
    """
    d = deref(target)

    # Normalise ground SegList → plain list so the list branch fires.
    # Non-ground SegLists delegate to _head_list_unify_input which returns False.
    if isinstance(d, SegList):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if isinstance(d, list):
        # Deconstruction: split list according to the pattern
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if is_var(d):
        # Construction: build list from bound vars and unify with target
        return _head_list_unify_output(target, before_vals, star_val, after_vals, trail)

    return False


def _build_star_list(before, star, after):
    """Build a list from [*before, *star, *after], dereffing the star element.

    If star is an unbound Var, returns a partial list (the Var itself when
    before and after are empty, otherwise raises — caller should use Is/unify).
    in_ practice, star should be bound to a list by the time body code runs.

    when star is bound to a ``str`` and all before/after elements are
    single-char strings, returns a ``str`` (or ``SegString`` when partial).
    """
    d = deref(star)
    if isinstance(d, str):
        # Check if all before/after elements are single-char strings
        b = list(before)
        a = list(after)
        if (all(isinstance(e, str) and len(e) == 1 for e in b) and
                all(isinstance(e, str) and len(e) == 1 for e in a)):
            return "".join(b) + d + "".join(a)
        # Mixed types — fall through to list construction
        return b + list(d) + a
    if isinstance(d, list):
        return list(before) + d + list(after)
    if isinstance(d, SegList):
        walked = d.__walk__()
        if isinstance(walked, list):
            return list(before) + walked + list(after)
        # non-ground SegList — wrap into a new SegList
        segs = []
        if before:
            segs.append(ConcreteSeg(list(before)))
        segs.extend(walked.segments)
        if after:
            segs.append(ConcreteSeg(list(after)))
        return SegList(segs)
    if isinstance(d, SegString):
        walked = d.__walk__()
        if isinstance(walked, str):
            b = list(before)
            a = list(after)
            if (all(isinstance(e, str) and len(e) == 1 for e in b) and
                    all(isinstance(e, str) and len(e) == 1 for e in a)):
                return "".join(b) + walked + "".join(a)
            return b + list(walked) + a
        # non-ground SegString — wrap into a new SegString or SegList
        b = list(before)
        a = list(after)
        if (all(isinstance(e, str) and len(e) == 1 for e in b) and
                all(isinstance(e, str) and len(e) == 1 for e in a)):
            new_segs = []
            prefix = "".join(b)
            if prefix:
                new_segs.append(prefix)
            new_segs.extend(walked.segments)
            suffix = "".join(a)
            if suffix:
                new_segs.append(suffix)
            return SegString(new_segs)
        # Mixed types — convert SegString segments to SegList segments
        segs = []
        if b:
            segs.append(ConcreteSeg(b))
        for seg in walked.segments:
            if isinstance(seg, str):
                segs.append(ConcreteSeg(list(seg)))
            else:  # VarSeg
                segs.append(seg)
        if a:
            segs.append(ConcreteSeg(a))
        return SegList(segs)
    # star is an unbound Var — build a SegList
    segs = []
    if before:
        segs.append(ConcreteSeg(list(before)))
    segs.append(VarSeg(d))
    if after:
        segs.append(ConcreteSeg(list(after)))
    return SegList(segs)


def _build_multi_star_list(segments):
    """Build a SegList from a sequence of (kind, value) segments.

    Each segment is ("fixed", [elem, ...]) for concrete elements or
    ("star", var) for a splat variable.  Returns a plain list when all
    star vars are bound, otherwise a SegList.

    when all concrete elements are single-char strings and all star vars are
    bound to strings, returns a plain ``str`` (or ``SegString`` when partial).
    """
    segs = []
    all_str = True  # track whether all parts are string-compatible
    for kind, val in segments:
        if kind == "star":
            d = deref(val)
            if isinstance(d, str):
                if segs and isinstance(segs[-1], ConcreteSeg):
                    segs[-1] = ConcreteSeg(segs[-1].elements + list(d))
                else:
                    if d:
                        segs.append(ConcreteSeg(list(d)))
            elif isinstance(d, list):
                all_str = False
                if segs and isinstance(segs[-1], ConcreteSeg):
                    segs[-1] = ConcreteSeg(segs[-1].elements + d)
                else:
                    if d:
                        segs.append(ConcreteSeg(d))
            elif isinstance(d, SegList):
                all_str = False
                walked = d.__walk__()
                if isinstance(walked, list):
                    if segs and isinstance(segs[-1], ConcreteSeg):
                        segs[-1] = ConcreteSeg(segs[-1].elements + walked)
                    elif walked:
                        segs.append(ConcreteSeg(walked))
                else:
                    segs.extend(walked.segments)
            elif isinstance(d, SegString):
                walked = d.__walk__()
                if isinstance(walked, str):
                    if segs and isinstance(segs[-1], ConcreteSeg):
                        segs[-1] = ConcreteSeg(segs[-1].elements + list(walked))
                    elif walked:
                        segs.append(ConcreteSeg(list(walked)))
                else:
                    # Non-ground SegString — give up on string result
                    all_str = False
                    for inner_seg in walked.segments:
                        if isinstance(inner_seg, str):
                            if segs and isinstance(segs[-1], ConcreteSeg):
                                segs[-1] = ConcreteSeg(segs[-1].elements + list(inner_seg))
                            else:
                                segs.append(ConcreteSeg(list(inner_seg)))
                        else:
                            segs.append(inner_seg)
            else:
                all_str = False
                segs.append(VarSeg(d))
        else:  # "fixed"
            elems = [deref(e) for e in val]
            if any(not isinstance(e, str) or len(e) != 1 for e in elems):
                all_str = False
            if segs and isinstance(segs[-1], ConcreteSeg):
                segs[-1] = ConcreteSeg(segs[-1].elements + elems)
            else:
                if elems:
                    segs.append(ConcreteSeg(elems))
    if not any(isinstance(s, VarSeg) for s in segs):
        result = []
        for seg in segs:
            result.extend(seg.elements)
        # If all parts were string-compatible, return a str
        if all_str and all(isinstance(e, str) and len(e) == 1 for e in result):
            return "".join(result)
        return result
    return SegList(segs)


def _in_iter(collection, pair_mode):
    """Runtime iterator for ``in`` expressions.

    *pair_mode* is True when the left side of ``in`` is a tuple pattern
    (e.g. ``(KEY, VALUE) in DICT``).  For DictTerms, pair_mode switches
    from key iteration to (key, value) pair iteration.
    """
    if pair_mode and isinstance(collection, DictTerm):
        return collection.items()
    return iter(collection)


def _body_multi_star_unify(target, segments, trail):
    """Body-position multi-star unification.

    *segments* is a list of ``("fixed", [var1, var2, ...])`` or
    ``("star", var)`` tuples describing the pattern.

    The target must be a ground list — unbound Var targets are not supported
    for multi-star patterns (same as head-position multi-star).

    Yields once per valid split (combinatorial backtracking).
    """
    d = deref(target)
    # Strings are handled directly (no list conversion) so that star vars
    # bind to substrings preserving str type.
    if not isinstance(d, (list, str)):
        if isinstance(d, SegList):
            d = d.__walk__()
            if not isinstance(d, (list, str)):
                # non-ground SegList — construct SegList and bind, then stop
                segs = [
                    VarSeg(deref(val)) if kind == "star"
                    else ConcreteSeg([deref(e) for e in val])
                    for kind, val in segments
                ]
                mark = trail.mark()
                if unify(target, SegList(segs), trail):
                    yield True
                trail.undo(mark)
                return
        elif is_var(d):
            # Unbound target: construct a SegList from the pattern and bind it
            segs = [
                VarSeg(deref(val)) if kind == "star"
                else ConcreteSeg([deref(e) for e in val])
                for kind, val in segments
            ]
            mark = trail.mark()
            if unify(d, SegList(segs), trail):
                yield True
            trail.undo(mark)
            return
        else:
            return  # not a list/string → no solutions

    # Parse segments into fixed counts and star positions
    stars = []
    fixed_total = 0
    for kind, val in segments:
        if kind == "fixed":
            fixed_total += len(val)
        else:
            stars.append(val)

    n_stars = len(stars)
    n = len(d)
    if n < fixed_total:
        return  # list/string too short

    remainder = n - fixed_total
    # Generate all ways to distribute `remainder` items among `n_stars` stars.
    # For strings, d[pos] yields single-char strings and d[pos:pos+n] yields
    # substrings, so star vars bind to str — preserving the string type.
    for split in _multi_star_splits(n_stars, remainder):
        mark = trail.mark()
        ok = True
        pos = 0
        si = 0  # star index
        for kind, val in segments:
            if not ok:
                break
            if kind == "fixed":
                for v in val:
                    if not unify(v, d[pos], trail):
                        ok = False
                        break
                    pos += 1
            else:  # star
                length = split[si]
                if not unify(val, d[pos:pos + length], trail):
                    ok = False
                pos += length
                si += 1
        if ok:
            yield True
        trail.undo(mark)
