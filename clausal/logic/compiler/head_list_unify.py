"""Runtime helpers for bidirectional list-pattern unification.

These functions are called by generated compiled code, not by the
compiler at compile time.  The design rationale (two-phase input/output
unification, repeated Vars across list patterns, etc.) is described in
the extended block comment below.

Also provides the trampoline → simple-mode bridge ``_tramp_call``.
"""

# ── Bidirectional list pattern unification ────────────────────────────────────
#
# Problem
# -------
# A clause like ``append([HEAD, *TAIL], B, [HEAD, *RESULT]) <- append(TAIL, B, RESULT)``
# has list patterns in head positions 1 and 3.  Python's ``match`` statement
# can only *destructure* sequences — it requires the value to already be a
# list.  But position 3 may receive an unbound Var (output mode), so a plain
# MatchSequence would fail to match.
#
# Additionally, the same Var ``HEAD`` appears in both positions 1 and 3 —
# Python's ``match`` rejects duplicate name bindings in a single case arm.
#
# Solution: two-phase list unification
# -------------------------------------
# List patterns in clause heads compile as **wildcard captures** (MatchAs)
# instead of MatchSequence.  Each list pattern records a "list guard" with
# its decomposed structure (before-star elements, star var, after-star
# elements).  At runtime, unification proceeds in two phases:
#
# 1. **Input phase** (before the body runs):
#    ``_head_list_unify_input(target, before_vars, star_var, after_vars, trail)``
#    - If *target* is a list → destructure and unify each var.  Returns True.
#    - If *target* is an unbound Var → defer.  Returns None.
#    - Otherwise → clause doesn't match.  Returns False.
#
# 2. **Output phase** (at each solution / yield point):
#    ``_head_list_unify_output(target, before_vars, star_var, after_vars, trail)``
#    - Called only for guards that returned None in phase 1.
#    - Constructs ``[deref(v1), deref(v2), *deref(star), ...]`` from the
#      now-bound vars and unifies the result with *target*.
#
# The output phase runs at yield points rather than before the body because
# the body may bind vars that the list pattern depends on (e.g., RESULT in
# ``append`` is bound by the recursive call).
#
# Compiled code structure (for ``append`` clause 2)::
#
#     case [_lcap0, _v10, _lcap1]:        # wildcards for all args
#         _v8 = Var(); _v9 = Var(); _v11 = Var()   # list-pattern vars
#         _lr0 = _head_list_unify_input(_lcap0, [_v8], _v9, [], trail)
#         _lr1 = _head_list_unify_input(_lcap1, [_v8], _v11, [], trail)
#         if _lr0 is not False and _lr1 is not False:
#             for _ in dispatch(_v9, _v10, _v11, trail, k):  # body
#                 if (_lr0 is not None or _head_list_unify_output(...)) \
#                 and (_lr1 is not None or _head_list_unify_output(...)):
#                     yield None                               # solution
#
# Repeated Vars across list patterns (e.g., HEAD in positions 1 and 3) work
# because both guards reference the *same* Var() object (_v8).  Phase-1
# input destructuring binds it from one list; phase-2 output construction
# uses the bound value to build the other list.
#
# Related: ``_wrap_yields_with_output_guards`` is an AST rewriter that
# replaces every ``yield None`` in the body with the guarded version.
#
# Related: ``_derive_field_names`` in term_rewriting.py deduplicates field
# names when the same Var name appears multiple times in a trailing-comma
# fact (e.g., ``append([], B, B)`` → fields ``b``, ``b_1``), preventing
# a SyntaxError from duplicate keyword arguments.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from clausal.logic.variables import is_var, deref, unify
from clausal.logic.trampoline import DONE, StepGenerator
from clausal.terms import (
    DictTerm,
    SegList, ConcreteSeg, VarSeg,
    SegString,
    _multi_star_splits,
)


def _head_list_unify_input_py(target, var_vals, star_val, after_vals, trail):
    """Input-mode list pattern unification: destructure a list or string.

    Returns True if target is a list (or string) and all elements unify.
    Returns None if target is an unbound Var (defer to output mode).
    Returns False if target is incompatible.

    Strings are treated as lists of single-character strings: indexing and
    slicing work identically on both types, so the same destructuring logic
    handles ``[H, *T]`` against either ``["h", "e"]`` or ``"he"``.
    """
    d = deref(target)

    # ── fast path: [H, *T] on a plain list ──
    if type(d) is list and star_val is not None and not after_vals:
        n = len(var_vals)
        if len(d) < n:
            return False
        for i in range(n):
            if not unify(var_vals[i], d[i], trail):
                return False
        return unify(star_val, d[n:], trail)
    # ── end fast path ──

    # Normalise SegList: walk it; if ground it becomes a plain list.
    # Non-ground SegLists can't be matched against a single-star pattern yet
    # (SegList-vs-SegList unification is Phase 6) — return False to fail.
    if isinstance(d, SegList):
        d = d.__walk__()
        if not isinstance(d, (list, str)):
            return False

    if isinstance(d, (list, str)):
        n_before = len(var_vals)
        n_after = len(after_vals)
        min_len = n_before + n_after
        if star_val is None:
            if len(d) != min_len:
                return False
        else:
            if len(d) < min_len:
                return False
        for i, v in enumerate(var_vals):
            if not unify(v, d[i], trail):
                return False
        if star_val is not None:
            star_end = len(d) - n_after if n_after else len(d)
            if not unify(star_val, d[n_before:star_end], trail):
                return False
        for i, v in enumerate(after_vals):
            if not unify(v, d[len(d) - n_after + i], trail):
                return False
        return True

    elif is_var(d):
        # Defer to output mode — vars will be bound by body
        return None

    else:
        return False


def _head_multi_star_error():
    """Raise when a multi-star list pattern receives an unbound variable."""
    raise TypeError(
        "Cannot match multi-star pattern against unbound variable"
    )


def _head_list_unify_output_py(target, var_vals, star_val, after_vals, trail):
    """Output-mode list pattern unification: construct list from bound vars.

    Called after body execution when target was an unbound Var.
    """
    d = deref(target)
    if not is_var(d):
        # Already bound (e.g., by body) — switch to input mode
        return _head_list_unify_input_py(target, var_vals, star_val, after_vals, trail)
    result = [deref(v) for v in var_vals]
    if star_val is not None:
        s = deref(star_val)
        if isinstance(s, list):
            result.extend(s)
        elif isinstance(s, SegList):
            # Star derefs to a SegList — walk it first
            walked = s.__walk__()
            if isinstance(walked, list):
                result.extend(walked)
                result.extend(deref(v) for v in after_vals)
                return unify(d, result, trail)
            else:
                # Still partially unbound: build a new SegList
                after_result = [deref(v) for v in after_vals]
                segs = []
                if result:
                    segs.append(ConcreteSeg(result))
                segs.extend(walked.segments)
                if after_result:
                    segs.append(ConcreteSeg(after_result))
                return unify(d, SegList(segs), trail)
        elif is_var(s):
            # Build a SegList: [*before, *s, *after] with s unbound
            after_result = [deref(v) for v in after_vals]
            segs = []
            if result:
                segs.append(ConcreteSeg(result))
            segs.append(VarSeg(s))
            if after_result:
                segs.append(ConcreteSeg(after_result))
            return unify(d, SegList(segs), trail)
        else:
            result.append(s)
    result.extend(deref(v) for v in after_vals)
    return unify(d, result, trail)


# ── C-accelerated list unification (with Python fallback) ────────────────────
_head_list_unify_input = _head_list_unify_input_py
_head_list_unify_output = _head_list_unify_output_py
try:
    from clausal.logic._list_unify import (  # noqa: F811
        _head_list_unify_input,
        _head_list_unify_output,
    )
except ImportError:
    pass


# ── Body-position star-list unification (Phase 5) ─────────────────────────────


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


# ── _tramp_call: bridge simple-mode → trampoline-mode ─────────────────────────


def _tramp_call(dispatch_fn, args, trail):
    """Call a trampoline-mode dispatch fn from simple-mode context.

    Drives a mini-trampoline internally and yields None per solution.
    Used by simple-mode code paths (lambda bodies, NAF, once) that need
    to call trampoline-mode predicates.
    """
    sg = StepGenerator(dispatch_fn, None, *args, trail)
    gen, value = sg.send(None)
    while True:
        if gen is None:
            if value is DONE:
                return
            yield None
            gen, value = sg.send(None)
        else:
            gen, value = gen.send(value)
