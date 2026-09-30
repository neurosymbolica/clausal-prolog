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

from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier
from clausal.logic.variables import is_var, deref, unify
from clausal.terms import (
    SegList, ConcreteSeg, VarSeg,
    SegString, SegBytes, _is_cons_cell, _unify_seglist_cons,
)
from ._seg_helpers import (
    maybe_promote_to_str, maybe_promote_to_bytes, seq_getitem, str_chars,
)


def _pattern_term(var_vals, star_val, after_vals):
    """The list term a head list pattern spells: ``[V1 ... Vn, *S, A1 ...
    Am]`` -- a plain list without a star, else a ``SegList``."""
    if star_val is None:
        return list(var_vals) + list(after_vals)
    segs = []
    if var_vals:
        segs.append(ConcreteSeg(list(var_vals)))
    segs.append(VarSeg(star_val))
    if after_vals:
        segs.append(ConcreteSeg(list(after_vals)))
    return SegList(segs)


def _seglist_input_fallback(target, var_vals, star_val, after_vals, trail):
    """Input mode against an OPEN SegList *target* (F030): build the pattern
    as the list term it spells and unify the two terms, which pairs the
    elements and hands the tail over (``SegList.__unify__``).
    ``p([H, *T])`` called with ``[1, *_]`` binds ``H = 1`` there, as ISO's
    ``[H|T] = [1|_]`` does; it used to fail.  Shared by the C twin, which
    calls it for this one case."""
    return bool(unify(target, _pattern_term(var_vals, star_val, after_vals),
                      trail))


def _cons_cell_input_fallback(cell, var_vals, star_val, after_vals, trail):
    """Input mode against the ISO cons cell *cell* -- ``('.', H, T)``, the
    term an improper list such as ``[b|foo]`` is (D50): build the pattern as
    the list term it spells and take the cell apart exactly as body
    unification does (``_unify_seglist_cons``).  ``p([H|T])`` called with
    ``[b|foo]`` binds ``H = b, T = foo``; a proper pattern (no star, or
    elements after the star) matches only a chain that ends in ``[]``.
    Undoes its own bindings on failure.  Shared by the C twin.

    The pattern is deliberately NOT walked first (``SegList.__unify__``
    walks): a star already bound to an atom -- ``p(T, [a|T])`` called as
    ``p(foo, [a|foo])`` -- would walk to the atom's characters, and the
    unwalked hole hands the cell's tail to the bound star instead."""
    return bool(_unify_seglist_cons(
        _pattern_term(var_vals, star_val, after_vals), cell, trail))


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
    d_text = False
    if is_chars(d):
        d = chars_text(d); d_text = True   # the carrier destructures as its text
    elif type(d) is str:
        return False                   # STAGE 2: a bare str is an ATOM, not a sequence

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
    # SegList is unified with the pattern as a term
    # (``_seglist_input_fallback``, F030).
    if isinstance(d, SegString):
        d = d.__walk__()
        if is_chars(d):
            d = chars_text(d); d_text = True   # a ground SegString walks to the carrier
        if not (isinstance(d, list) or d_text):
            return None
    if isinstance(d, SegBytes):
        d = d.__walk__()
        if not isinstance(d, (list, bytes)):
            return None
    if isinstance(d, SegList):
        d = d.__walk__()
        if is_chars(d):
            d = chars_text(d); d_text = True   # a ground char SegList walks to the carrier
        if not (isinstance(d, list) or d_text):
            return _seglist_input_fallback(d, var_vals, star_val, after_vals, trail)

    if isinstance(d, (list, bytes)) or d_text:   # STAGE 2: text only through the carrier
        n_before = len(var_vals)
        n_after = len(after_vals)
        min_len = n_before + n_after
        if star_val is None:
            if len(d) != min_len:
                return False
        else:
            if len(d) < min_len:
                return False
        # ``seq_getitem`` (twin of the C ``seq_getitem``) makes a str's
        # element a CHAR; a list's / bytes' element is unchanged. The star
        # SLICE keeps the container's own type (R-S2: a str tail stays a str).
        for i, v in enumerate(var_vals):
            if not unify(v, seq_getitem(d, i), trail):
                return False
        if star_val is not None:
            star_end = len(d) - n_after if n_after else len(d)
            star_slice = d[n_before:star_end]
            if type(star_slice) is str:
                star_slice = chars(star_slice)   # stage 1: a str tail is the carrier
            if not unify(star_val, star_slice, trail):
                return False
        for i, v in enumerate(after_vals):
            if not unify(v, seq_getitem(d, len(d) - n_after + i), trail):
                return False
        return True

    elif is_var(d):
        # Defer to output mode — vars will be bound by body
        return None

    elif _is_cons_cell(d):
        # An improper list (D50): take the cell apart as the body does.
        return _cons_cell_input_fallback(d, var_vals, star_val, after_vals, trail)

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
    # THE FLIP (atoms-as-cells/strings §6.2) DELETED the ``star_was_str``
    # gate that used to stand here (and its C twin in ``_list_unify.c``).
    # It guarded a hazard that no longer exists: under P3-1 an atom was a
    # plain ``str``, so an output list that happened to hold two 1-char
    # atoms would have been "promoted" into a str and silently re-created
    # the retired str~list cons identity.  A char is a CELL now, so a list
    # of chars IS the string, and building the compact representation is
    # not a back door — it is R-S2's rule that a string stays a string.
    if star_val is not None:
        s = deref(star_val)
        s_text = is_chars(s)
        if s_text:
            s = chars_text(s)          # a carrier-bound star splats as its chars
        if isinstance(s, list):
            result.extend(s)
        elif s_text:                   # STAGE 2: a bare str star is an ATOM element (the else arm)
            # Liskov "strings-as-lists" rule: a str-bound star is treated
            # as a list of CHARS. Splat its chars into the result;
            # the final ``maybe_promote_to_str`` re-promotes the whole
            # result to a str when every element is a char.
            result.extend(str_chars(s))
        elif isinstance(s, bytes):
            # Codes-model parallel of the str-star branch: a bytes-bound
            # star is treated as a list of int codes. Iterating bytes yields
            # ints; promote the result back to bytes (only fires because a
            # bytes source is present here — no spurious bytes otherwise).
            result.extend(s)
            result.extend(deref(v) for v in after_vals)
            return unify(d, maybe_promote_to_bytes(result), trail)
        elif isinstance(s, SegBytes):
            walked = s.__walk__()
            if isinstance(walked, bytes):
                result.extend(walked)
                result.extend(deref(v) for v in after_vals)
                return unify(d, maybe_promote_to_bytes(result), trail)
            else:
                # Non-ground SegBytes: convert each bytes segment to a
                # ConcreteSeg of int codes (list(b"GET") == [71,69,84]) and
                # rebuild as a SegList for unification — mirrors the
                # SegString non-ground output path.
                after_result = [deref(v) for v in after_vals]
                segs = []
                if result:
                    segs.append(ConcreteSeg(result))
                for inner in walked.segments:
                    if isinstance(inner, bytes):
                        segs.append(ConcreteSeg(list(inner)))
                    else:  # VarSeg
                        segs.append(inner)
                if after_result:
                    segs.append(ConcreteSeg(after_result))
                return unify(d, SegList(segs), trail)
        elif isinstance(s, SegList):
            # Star derefs to a SegList — walk it first.
            # Review fix (fix round 1): SegList.__walk__ itself applies
            # maybe_promote_to_str to a fully-ground result (terms.py),
            # so a ground SegList of all chars walks to a STR, not
            # a list — mirror the C twin's ``PyList_Check(walked) ||
            # PyUnicode_Check(walked)`` gate exactly (_list_unify.c, the
            # SegList/SegString ground-walk branch) rather than only
            # handling ``list``. A walked str splats through ``str_chars``
            # (the C twin's per-char ``PyUnicode_Substring`` splice, now
            # wrapped in ``char_atom_obj``).
            walked = s.__walk__()
            if is_chars(walked):
                walked = chars_text(walked)   # stage 1
            if isinstance(walked, (list, str)):
                result.extend(
                    str_chars(walked) if isinstance(walked, str) else walked
                )
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
            # a sequence of chars, matching the "strings as char
            # lists" contract). Non-ground → rebuild via the segments.
            walked = s.__walk__()
            if is_chars(walked):
                walked = chars_text(walked)   # stage 1
            if isinstance(walked, str):
                result.extend(str_chars(walked))
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
                        segs.append(ConcreteSeg(str_chars(inner)))
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
    # A list of chars IS a string (§6.2), so the compact representation is
    # always the right one to build — see the note where ``star_was_str``
    # used to be set.
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
