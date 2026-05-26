"""Bidirectional head list-pattern unification — runtime helpers.

Called by generated compiled code, not by the compiler at compile
time.  The design rationale (two-phase input/output unification,
repeated Vars across list patterns, etc.) is described in the
extended block comment below.

The Python implementations (``_head_list_unify_input_py`` /
``_head_list_unify_output_py``) are the reference.  When the
``clausal.logic._list_unify`` C extension is available, the
unsuffixed names (``_head_list_unify_input`` / ``_output``) are
replaced with the C-accelerated versions; otherwise the Python
fallbacks are used.
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
# Related: ``_wrap_yields_with_output_guards`` is an AST rewriter (in the
# compiler) that replaces every ``yield None`` in the body with the guarded
# version.
#
# Related: ``_derive_field_names`` in term_rewriting.py deduplicates field
# names when the same Var name appears multiple times in a trailing-comma
# fact (e.g., ``append([], B, B)`` → fields ``b``, ``b_1``), preventing
# a SyntaxError from duplicate keyword arguments.
# ──────────────────────────────────────────────────────────────────────────────

from __future__ import annotations

from clausal.logic.variables import is_var, deref, unify
from clausal.terms import (
    SegList, ConcreteSeg, VarSeg,
    SegString,
)
from ._seg_helpers import maybe_promote_to_str


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

    # Normalise SegList / SegString: walk it; if ground it becomes a plain
    # list / str so the existing (list, str) arm below fires. F031 / F032
    # (C3 audit): the SegString arm mirrors SegList. A still-non-ground
    # SegString defers to output mode (returns None) so the body can
    # constrain the unbound holes — the output-mode helper then rebuilds
    # the pattern and tries the unify when called. A still-non-ground
    # SegList keeps the historical silent-False behaviour (SegList-vs-
    # SegList unification is blocked by F030, Phase 6).
    if isinstance(d, SegString):
        d = d.__walk__()
        if not isinstance(d, (list, str)):
            return None
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
        elif isinstance(s, str):
            # Liskov "strings-as-lists" rule: a str-bound star is treated
            # as a list of 1-char strs. Splat its chars into the result;
            # the final ``maybe_promote_to_str`` re-promotes the whole
            # result to a str when every element is 1-char-str.
            result.extend(s)
        elif isinstance(s, SegList):
            # Star derefs to a SegList — walk it first
            walked = s.__walk__()
            if isinstance(walked, list):
                result.extend(walked)
                result.extend(deref(v) for v in after_vals)
                # F033: promote list-of-1-char-strs back to str under the
                # Liskov "strings-as-lists" rule (default output is list;
                # str only when provable from the elements themselves).
                return unify(d, maybe_promote_to_str(result), trail)
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
        elif isinstance(s, SegString):
            # F034 (C3 audit): Star derefs to a SegString — walk it parallel
            # to the SegList branch. Ground → extend chars (treat the str as
            # a sequence of single-char strs, matching the "strings as char
            # lists" contract). Non-ground → rebuild via the segments.
            walked = s.__walk__()
            if isinstance(walked, str):
                result.extend(walked)
                result.extend(deref(v) for v in after_vals)
                # F033: promote list-of-1-char-strs back to str under the
                # Liskov "strings-as-lists" rule.
                return unify(d, maybe_promote_to_str(result), trail)
            else:
                # Still partially unbound SegString: convert each segment to
                # the SegList equivalent (str segments → ConcreteSeg of
                # chars) so the output remains a SegList for unification.
                after_result = [deref(v) for v in after_vals]
                segs = []
                if result:
                    segs.append(ConcreteSeg(result))
                for inner in walked.segments:
                    if isinstance(inner, str):
                        segs.append(ConcreteSeg(list(inner)))
                    else:  # VarSeg
                        segs.append(inner)
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
    # F033: promote list-of-1-char-strs back to str under the Liskov
    # "strings-as-lists" rule (default output is list; str only when
    # provable from the elements themselves).
    return unify(d, maybe_promote_to_str(result), trail)


# ── C-accelerated list unification (with Python fallback) ────────────────────
_head_list_unify_input = _head_list_unify_input_py
_head_list_unify_output = _head_list_unify_output_py
try:
    from clausal.logic.runtime._list_unify import (  # noqa: F811
        _head_list_unify_input,
        _head_list_unify_output,
    )
except ImportError:
    pass
