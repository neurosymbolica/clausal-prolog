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

from ._seg_helpers import maybe_promote_to_str
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
        # F043: promote list-of-1-char-strs back to str under the Liskov
        # "strings-as-lists" rule. The default is list; str only when the
        # whole result is provably all 1-char strs.
        return maybe_promote_to_str(list(before) + d + list(after))
    if isinstance(d, SegList):
        walked = d.__walk__()
        if isinstance(walked, list):
            # F043: promote list-of-1-char-strs back to str.
            return maybe_promote_to_str(list(before) + walked + list(after))
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

    Under the Liskov "strings-as-lists" rule, when every part is
    str-compatible (1-char-str fixed elements, str / ground-SegString
    stars, non-ground SegString stars) the result is promoted to a
    plain ``str`` (ground) or a ``SegString`` (non-ground). F043 fix:
    a non-ground SegString star no longer demotes the whole result to
    SegList; instead the segments preserve their string identity and
    the build returns a SegString.
    """
    # First pass: do we have any non-string-compatible content?
    # If every star derefs to a str / ground-SegString / non-ground
    # SegString and every fixed element is a 1-char str, we can build
    # a SegString instead of a SegList.
    string_mode = True
    for kind, val in segments:
        if kind == "star":
            d = deref(val)
            if isinstance(d, str):
                continue
            if isinstance(d, SegString):
                continue
            if isinstance(d, list):
                if not all(isinstance(e, str) and len(e) == 1 for e in d):
                    string_mode = False
                    break
                continue
            if isinstance(d, SegList):
                walked = d.__walk__()
                if isinstance(walked, list):
                    if not all(isinstance(e, str) and len(e) == 1 for e in walked):
                        string_mode = False
                        break
                    continue
                # Non-ground SegList → cannot guarantee str-compat
                string_mode = False
                break
            if is_var(d):
                # Unbound var — can't prove str-compat
                string_mode = False
                break
            # Other types (int, term, etc.)
            string_mode = False
            break
        else:  # "fixed"
            elems = [deref(e) for e in val]
            if any(not isinstance(e, str) or len(e) != 1 for e in elems):
                string_mode = False
                break

    if string_mode:
        # Build SegString segments (str / VarSeg only).
        str_segs: list = []
        for kind, val in segments:
            if kind == "star":
                d = deref(val)
                if isinstance(d, str):
                    if d:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + d
                        else:
                            str_segs.append(d)
                elif isinstance(d, SegString):
                    walked = d.__walk__()
                    if isinstance(walked, str):
                        if walked:
                            if str_segs and isinstance(str_segs[-1], str):
                                str_segs[-1] = str_segs[-1] + walked
                            else:
                                str_segs.append(walked)
                    else:
                        for inner_seg in walked.segments:
                            if isinstance(inner_seg, str):
                                if inner_seg:
                                    if str_segs and isinstance(str_segs[-1], str):
                                        str_segs[-1] = str_segs[-1] + inner_seg
                                    else:
                                        str_segs.append(inner_seg)
                            else:  # VarSeg
                                str_segs.append(inner_seg)
                elif isinstance(d, list):
                    # list of 1-char strs (guaranteed by first-pass check)
                    s = "".join(d)
                    if s:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + s
                        else:
                            str_segs.append(s)
                elif isinstance(d, SegList):
                    walked = d.__walk__()
                    # walked is a list of 1-char strs (first-pass check)
                    s = "".join(walked)
                    if s:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + s
                        else:
                            str_segs.append(s)
            else:  # "fixed" — all 1-char strs (first-pass check)
                elems = [deref(e) for e in val]
                s = "".join(elems)
                if s:
                    if str_segs and isinstance(str_segs[-1], str):
                        str_segs[-1] = str_segs[-1] + s
                    else:
                        str_segs.append(s)
        # Ground? return str. Otherwise SegString.
        if all(isinstance(s, str) for s in str_segs):
            return "".join(str_segs)
        return SegString(str_segs)

    # SegList path — same as before.
    segs = []
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
                if segs and isinstance(segs[-1], ConcreteSeg):
                    segs[-1] = ConcreteSeg(segs[-1].elements + d)
                else:
                    if d:
                        segs.append(ConcreteSeg(d))
            elif isinstance(d, SegList):
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
                    for inner_seg in walked.segments:
                        if isinstance(inner_seg, str):
                            if segs and isinstance(segs[-1], ConcreteSeg):
                                segs[-1] = ConcreteSeg(segs[-1].elements + list(inner_seg))
                            else:
                                segs.append(ConcreteSeg(list(inner_seg)))
                        else:
                            segs.append(inner_seg)
            else:
                segs.append(VarSeg(d))
        else:  # "fixed"
            elems = [deref(e) for e in val]
            if segs and isinstance(segs[-1], ConcreteSeg):
                segs[-1] = ConcreteSeg(segs[-1].elements + elems)
            else:
                if elems:
                    segs.append(ConcreteSeg(elems))
    if not any(isinstance(s, VarSeg) for s in segs):
        result = []
        for seg in segs:
            result.extend(seg.elements)
        # F043: promote list-of-1-char-strs back to str under the
        # Liskov "strings-as-lists" rule.
        return maybe_promote_to_str(result)
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


def _segstring_align(ss, segments, trail, target):
    """Align a non-ground SegString with a multi-star pattern, yielding one
    True per valid alignment.

    Strategy: bind every VarSeg in *ss* to the empty string ``""`` and
    let the SegString collapse to its concatenated concrete prefix.  The
    pattern is then enumerated against the collapsed str via the existing
    ground-string enumeration logic in this module's caller.

    Binding every VarSeg to ``""`` is one valid extension among many; it
    is the witness needed to demonstrate the goal is satisfiable when the
    SegString's concrete chars already line up with the pattern.  More
    aggressive search (enumerating non-empty VarSeg bindings) is out of
    scope here — the structural-unify path is best-effort and parity-
    matched with the SegList branch (which similarly yields zero today
    pending F030 / Phase 6).
    """
    from clausal.terms import VarSeg as _VarSeg

    # Collect VarSegs that need to be bound to "" to make ss ground.
    var_segs = [s for s in ss.segments if isinstance(s, _VarSeg)]
    if not var_segs:
        # Already ground modulo walk — fall through to caller.
        return

    mark = trail.mark()
    bind_ok = True
    for vs in var_segs:
        if not unify(vs.var, "", trail):
            bind_ok = False
            break
    if not bind_ok:
        trail.undo(mark)
        return

    # Re-walk the SegString — should now be a plain str.
    collapsed = ss.__walk__()
    if not isinstance(collapsed, str):
        # Some VarSeg was already bound to a non-str (e.g. another
        # SegString) — give up.
        trail.undo(mark)
        return

    # Enumerate splits over the collapsed str (replicates the ground
    # branch of _body_multi_star_unify so we don't recurse and risk
    # re-entering this helper).
    fixed_total = sum(len(v) for k, v in segments if k == "fixed")
    n_stars = sum(1 for k, _ in segments if k == "star")
    n = len(collapsed)
    if n < fixed_total:
        trail.undo(mark)
        return

    remainder = n - fixed_total
    yielded = False
    for split in _multi_star_splits(n_stars, remainder):
        inner = trail.mark()
        ok = True
        pos = 0
        si = 0
        for kind, val in segments:
            if not ok:
                break
            if kind == "fixed":
                for v in val:
                    if not unify(v, collapsed[pos], trail):
                        ok = False
                        break
                    pos += 1
            else:  # star
                length = split[si]
                if not unify(val, collapsed[pos:pos + length], trail):
                    ok = False
                pos += length
                si += 1
        if ok:
            yield True
            yielded = True
        trail.undo(inner)
    if not yielded:
        # No alignment matched; unbind the empty-VarSeg witnesses.
        trail.undo(mark)
        return
    trail.undo(mark)


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
        # F040 / F041 (C3 audit): SegList and SegString are walked uniformly
        # here. Ground forms (walk → list / str) fall through to the
        # enumeration loop below.
        if isinstance(d, (SegList, SegString)):
            d_walked = d.__walk__()
            if isinstance(d_walked, (list, str)):
                d = d_walked
            elif isinstance(d_walked, SegString):
                # F041: non-ground SegString — try a structural 1:1
                # alignment between the SegString's segments and the
                # pattern's segments. Each str segment in the SegString
                # supplies a fixed-length char prefix that must line up
                # with a "fixed" run of pattern vars; each VarSeg in the
                # SegString supplies a substring that can absorb a "star"
                # pattern slot. The walked SegString has merged adjacent
                # str segments, so the structure is canonical.
                yield from _segstring_align(d_walked, segments, trail, target)
                return
            else:
                # non-ground SegList — construct SegList from the pattern
                # and try unify. SegList-vs-SegList is still blocked by
                # F030 so this typically yields zero, matching the prior
                # silent-fail behaviour.
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
            # Unbound target: build the result via _build_multi_star_list so
            # the same str / SegString promotion rule applies. F042: when
            # all fixed elements deref to 1-char strs and every star derefs
            # to a str / SegString, the result is a plain str or SegString
            # rather than a SegList — the Liskov "strings-as-lists" rule
            # applied at the unbound-target construction site.
            built = _build_multi_star_list(segments)
            mark = trail.mark()
            if unify(d, built, trail):
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
