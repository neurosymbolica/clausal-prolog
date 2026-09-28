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

from clausal.logic.variables import Var, is_var, deref, unify
from clausal.terms import (
    DictTerm,
    SegList, ConcreteSeg, VarSeg,
    SegString,
    SegBytes,
    _multi_star_splits,
)

from clausal.logic.atoms import is_char_atom
from clausal.logic.cells import chars, is_chars, chars_text  # stage 1: the chars carrier


def _unwrap(d):
    """A deref'd star / target value with the chars carrier read as its text
    (stage 1): the builders below keep bare ``str`` as their INTERNAL form and
    hand every text RESULT out as the carrier again (``_text_out``)."""
    return chars_text(d) if is_chars(d) else d


def _text_out(x):
    return chars(x) if type(x) is str else x
from ._seg_helpers import (
    maybe_promote_to_str, join_chars, seq_getitem, str_chars,
)
from .list_unify import _head_list_unify_input, _head_list_unify_output


def _body_star_unify(target, before_vals, star_val, after_vals, trail):
    """Bidirectional star-list unification for body-position Is goals.

    Handles both deconstruction (target is a ground list / str / Seg*) and
    construction (target is an unbound Var, pattern vars are bound).
    """
    d = deref(target)
    if type(d) is str:
        return False                   # STAGE 2: an atom is not a sequence

    # Normalise ground SegList → plain list so the list branch fires.
    # Non-ground SegLists delegate to _head_list_unify_input which returns False.
    if isinstance(d, SegList):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    # F034 / F067-F069 (C3 + C10): SegString and str are walked / handled
    # identically to SegList / list. ``_head_list_unify_input`` already
    # implements the Liskov "strings-as-lists" destructuring (str slicing
    # preserves str type for the star var), so the body-Is path inherits
    # the same contract.
    if isinstance(d, SegString):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if isinstance(d, SegBytes):
        return _head_list_unify_input(target, before_vals, star_val, after_vals, trail)

    if isinstance(d, (list, str, bytes)) or is_chars(d):
        # Deconstruction: split list/str/bytes according to the pattern
        # (the chars carrier destructures as its text -- stage 1; both twins
        # of ``_head_list_unify_input`` read it)
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
    chars, returns a ``str`` (or ``SegString`` when partial).
    """
    d = _unwrap(deref(star))
    if isinstance(d, str):
        # Check if all before/after elements are chars
        b = list(before)
        a = list(after)
        if (all(is_char_atom(e) for e in b) and
                all(is_char_atom(e) for e in a)):
            return chars(join_chars(b) + d + join_chars(a))   # stage 1
        # Mixed types — fall through to list construction
        return b + str_chars(d) + a
    if isinstance(d, bytes):
        b = list(before)
        a = list(after)
        codes_ok = all(isinstance(e, int) and not isinstance(e, bool)
                       and 0 <= e <= 255 for e in b + a)
        if codes_ok:
            return bytes(b) + d + bytes(a)
        # Mixed — fall through to list construction (codes view).
        return b + list(d) + a
    if isinstance(d, list):
        # F043: promote a list of chars back to str under the Liskov
        # "strings-as-lists" rule. The default is list; str only when the
        # whole result is provably all chars.
        return maybe_promote_to_str(list(before) + d + list(after))
    if isinstance(d, SegList):
        walked = d.__walk__()
        if is_chars(walked):
            walked = str_chars(chars_text(walked))   # stage 1: a char SegList walks to the carrier
        if isinstance(walked, list):
            # F043: promote a list of chars back to str.
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
        walked = _unwrap(d.__walk__())
        if isinstance(walked, str):
            b = list(before)
            a = list(after)
            if (all(is_char_atom(e) for e in b) and
                    all(is_char_atom(e) for e in a)):
                return chars(join_chars(b) + walked + join_chars(a))   # stage 1
            return b + str_chars(walked) + a
        # non-ground SegString — wrap into a new SegString or SegList
        b = list(before)
        a = list(after)
        if (all(is_char_atom(e) for e in b) and
                all(is_char_atom(e) for e in a)):
            new_segs = []
            prefix = join_chars(b)
            if prefix:
                new_segs.append(prefix)
            new_segs.extend(walked.segments)
            suffix = join_chars(a)
            if suffix:
                new_segs.append(suffix)
            return SegString(new_segs)
        # Mixed types — convert SegString segments to SegList segments
        segs = []
        if b:
            segs.append(ConcreteSeg(b))
        for seg in walked.segments:
            if isinstance(seg, str):
                segs.append(ConcreteSeg(str_chars(seg)))
            else:  # VarSeg
                segs.append(seg)
        if a:
            segs.append(ConcreteSeg(a))
        return SegList(segs)
    if isinstance(d, SegBytes):
        walked = d.__walk__()
        b = list(before)
        a = list(after)
        codes_ok = all(isinstance(e, int) and not isinstance(e, bool)
                       and 0 <= e <= 255 for e in b + a)
        if isinstance(walked, bytes):
            if codes_ok:
                return bytes(b) + walked + bytes(a)
            return b + list(walked) + a
        # non-ground SegBytes
        if codes_ok:
            new_segs = []
            prefix = bytes(b)
            if prefix:
                new_segs.append(prefix)
            new_segs.extend(walked.segments)
            suffix = bytes(a)
            if suffix:
                new_segs.append(suffix)
            return SegBytes(new_segs)
        # Mixed — convert SegBytes segments to SegList segments (int codes).
        segs = []
        if b:
            segs.append(ConcreteSeg(b))
        for seg in walked.segments:
            if isinstance(seg, bytes):
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
    str-compatible (char fixed elements, str / ground-SegString
    stars, non-ground SegString stars) the result is promoted to a
    plain ``str`` (ground) or a ``SegString`` (non-ground). F043 fix:
    a non-ground SegString star no longer demotes the whole result to
    SegList; instead the segments preserve their string identity and
    the build returns a SegString.
    """
    # First pass: do we have any non-string-compatible content?
    # If every star derefs to a str / ground-SegString / non-ground
    # SegString and every fixed element is a char, we can build
    # a SegString instead of a SegList.
    string_mode = True
    for kind, val in segments:
        if kind == "star":
            d = _unwrap(deref(val))
            if isinstance(d, str):
                continue
            if isinstance(d, SegString):
                continue
            if isinstance(d, list):
                if not all(is_char_atom(e) for e in d):
                    string_mode = False
                    break
                continue
            if isinstance(d, SegList):
                walked = d.__walk__()
                if is_chars(walked):
                    continue           # stage 1: a char SegList walks to the carrier (all chars)
                if isinstance(walked, list):
                    if not all(is_char_atom(e) for e in walked):
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
            if any(not is_char_atom(e) for e in elems):
                string_mode = False
                break

    if string_mode:
        # Build SegString segments (str / VarSeg only).
        str_segs: list = []
        for kind, val in segments:
            if kind == "star":
                d = _unwrap(deref(val))
                if isinstance(d, str):
                    if d:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + d
                        else:
                            str_segs.append(d)
                elif isinstance(d, SegString):
                    walked = _unwrap(d.__walk__())
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
                    # list of chars (guaranteed by first-pass check)
                    s = join_chars(d)
                    if s:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + s
                        else:
                            str_segs.append(s)
                elif isinstance(d, SegList):
                    walked = d.__walk__()
                    # walked is a list of chars (first-pass check)
                    s = chars_text(walked) if is_chars(walked) else join_chars(walked)
                    if s:
                        if str_segs and isinstance(str_segs[-1], str):
                            str_segs[-1] = str_segs[-1] + s
                        else:
                            str_segs.append(s)
            else:  # "fixed" — all chars (first-pass check)
                elems = [deref(e) for e in val]
                s = join_chars(elems)
                if s:
                    if str_segs and isinstance(str_segs[-1], str):
                        str_segs[-1] = str_segs[-1] + s
                    else:
                        str_segs.append(s)
        # Ground? return str. Otherwise SegString.
        if all(isinstance(s, str) for s in str_segs):
            return chars("".join(str_segs))   # stage 1: a text result is the carrier
        return SegString(str_segs)

    bytes_mode = True
    bytes_source_present = False
    for kind, val in segments:
        if kind == "star":
            d = _unwrap(deref(val))
            if isinstance(d, bytes):
                bytes_source_present = True
                continue
            if isinstance(d, SegBytes):
                bytes_source_present = True
                continue
            if isinstance(d, list):
                if not all(isinstance(e, int) and not isinstance(e, bool)
                           and 0 <= e <= 255 for e in d):
                    bytes_mode = False
                    break
                continue
            if isinstance(d, SegList):
                walked = d.__walk__()
                if isinstance(walked, list) and all(
                    isinstance(e, int) and not isinstance(e, bool)
                    and 0 <= e <= 255 for e in walked
                ):
                    continue
                bytes_mode = False
                break
            bytes_mode = False
            break
        else:  # "fixed"
            elems = [deref(e) for e in val]
            if any(not (isinstance(e, int) and not isinstance(e, bool)
                        and 0 <= e <= 255) for e in elems):
                bytes_mode = False
                break

    # Only build bytes when a bytes/SegBytes source is actually present —
    # a pure int-list / SegList pattern must stay a list (promiscuity guard).
    if bytes_mode and not bytes_source_present:
        bytes_mode = False

    if bytes_mode:
        byte_segs: list = []

        def _push_bytes(bb):
            if bb:
                if byte_segs and isinstance(byte_segs[-1], bytes):
                    byte_segs[-1] = byte_segs[-1] + bb
                else:
                    byte_segs.append(bb)

        for kind, val in segments:
            if kind == "star":
                d = _unwrap(deref(val))
                if isinstance(d, bytes):
                    _push_bytes(d)
                elif isinstance(d, SegBytes):
                    walked = d.__walk__()
                    if isinstance(walked, bytes):
                        _push_bytes(walked)
                    else:
                        for inner_seg in walked.segments:
                            if isinstance(inner_seg, bytes):
                                _push_bytes(inner_seg)
                            else:  # VarSeg
                                byte_segs.append(inner_seg)
                elif isinstance(d, list):
                    _push_bytes(bytes(d))
                elif isinstance(d, SegList):
                    _push_bytes(bytes(d.__walk__()))
            else:  # "fixed" — all ints in [0,255]
                _push_bytes(bytes(deref(e) for e in val))
        if all(isinstance(s, bytes) for s in byte_segs):
            return b"".join(byte_segs)
        return SegBytes(byte_segs)

    # SegList path — same as before.
    segs = []
    for kind, val in segments:
        if kind == "star":
            d = _unwrap(deref(val))
            if isinstance(d, str):
                if segs and isinstance(segs[-1], ConcreteSeg):
                    segs[-1] = ConcreteSeg(segs[-1].elements + str_chars(d))
                else:
                    if d:
                        segs.append(ConcreteSeg(str_chars(d)))
            elif isinstance(d, list):
                if segs and isinstance(segs[-1], ConcreteSeg):
                    segs[-1] = ConcreteSeg(segs[-1].elements + d)
                else:
                    if d:
                        segs.append(ConcreteSeg(d))
            elif isinstance(d, SegList):
                walked = d.__walk__()
                if is_chars(walked):
                    walked = str_chars(chars_text(walked))   # stage 1: a char SegList walks to the carrier
                if isinstance(walked, list):
                    if segs and isinstance(segs[-1], ConcreteSeg):
                        segs[-1] = ConcreteSeg(segs[-1].elements + walked)
                    elif walked:
                        segs.append(ConcreteSeg(walked))
                else:
                    segs.extend(walked.segments)
            elif isinstance(d, SegString):
                walked = _unwrap(d.__walk__())
                if isinstance(walked, str):
                    if segs and isinstance(segs[-1], ConcreteSeg):
                        segs[-1] = ConcreteSeg(segs[-1].elements + str_chars(walked))
                    elif walked:
                        segs.append(ConcreteSeg(str_chars(walked)))
                else:
                    for inner_seg in walked.segments:
                        if isinstance(inner_seg, str):
                            if segs and isinstance(segs[-1], ConcreteSeg):
                                segs[-1] = ConcreteSeg(
                                    segs[-1].elements + str_chars(inner_seg))
                            else:
                                segs.append(ConcreteSeg(str_chars(inner_seg)))
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
        # F043: promote a list of chars back to str under the
        # Liskov "strings-as-lists" rule.
        return maybe_promote_to_str(result)
    return SegList(segs)


def _in_iter(collection, pair_mode, trail=None):
    """Runtime iterator for ``in`` expressions.

    *pair_mode* is True when the left side of ``in`` is a tuple pattern
    (e.g. ``(KEY, VALUE) in DICT``).  For DictTerms, pair_mode switches
    from key iteration to (key, value) pair iteration.

    An OPEN list -- an unbound variable, or a partial list ``[a, *T]`` -- is
    member/2's open mode (ISO prologue; Scryer): its known elements, then
    ``T = [E|_]``, ``T = [_, E|_]``, ... without end.  With *trail* (the
    positive ``in`` goal) each such candidate binds the tail and is undone
    before the next; without it (``not in``, which only asks whether some
    candidate unifies) the open tail is one fresh variable, which always
    does -- so ``E not in T`` fails for an open ``T``, as ``\\+ member``.
    """
    if type(collection) is list:
        return iter(collection)
    data = DictTerm.mapping_of(collection)
    if data is not None:
        # A plain dict is a dict-valued term too (the dictterm-only sweep):
        # without the pair arm, pair mode iterated its KEYS, which never
        # unify with the tuple pattern — silent no-solutions.
        #
        # ``mapping_of``, not ``collection`` raw (Task 15 fix round 5, item
        # 1): this was the last reader that took a caller's PLAIN dict
        # unfolded, so ``K in {"": 1}`` ENUMERATED the key ``""`` while
        # ``gen_dict/3`` and ``dict_keys/2`` over the same term yield the
        # canonical ``()`` — one term, two enumerations.  A nil-free plain
        # dict is handed back uncopied (two O(1) membership tests), so the
        # common case still iterates in place.
        return data.items() if pair_mode else iter(data)
    if type(collection) is str:
        return iter(())                # STAGE 2: an atom is not a collection
    collection = _unwrap(collection)    # the carrier iterates as its chars
    if type(collection) is str:
        # THE FLIP (spec §6.2): a string is the LIST OF ITS CHAR ATOMS, so
        # ``X in "abc"`` enumerates ``("a",)``, ``("b",)``, ``("c",)`` — the
        # same elements ``X in [a, b, c]`` enumerates.  Python's own
        # ``iter(str)`` yields 1-char ``str``s, which are one-element
        # STRINGS and would make the two spellings of one term enumerate
        # different things.  ``SegString.__iter__`` answers char atoms for
        # the same reason.
        return iter(str_chars(collection))
    if is_var(collection) or isinstance(collection, SegList):
        from clausal.logic.builtins.lists import _open_skeleton  # noqa: PLC0415
        skel = _open_skeleton(collection)
        if skel is not None:
            return _in_open_iter(skel, trail)
    return iter(collection)


def _in_open_iter(skel, trail):
    """member/2's candidates on an open list (see :func:`_in_iter`)."""
    from clausal.logic.builtins.lists import _partial  # noqa: PLC0415
    prefix, tail = skel
    yield from prefix
    if trail is None:
        yield Var()
        return
    k = 0
    while True:
        mark = trail.mark()
        h = Var()
        if unify(tail, _partial([Var() for _ in range(k)] + [h], Var()), trail):
            yield h
        trail.undo(mark)
        k += 1


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
        if not unify(vs.var, chars(""), trail):   # stage 1: an empty TEXT hole
            bind_ok = False
            break
    if not bind_ok:
        trail.undo(mark)
        return

    # Re-walk the SegString — should now be a plain str.
    collapsed = _unwrap(ss.__walk__())
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
                    # ``collapsed`` is a str: a fixed slot sees a CHAR.
                    if not unify(v, seq_getitem(collapsed, pos), trail):
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


def _segbytes_align(ss, segments, trail, target):
    """Align a non-ground SegBytes with a multi-star pattern, yielding one
    True per valid alignment.

    Strategy: bind every VarSeg in *ss* to the empty bytes ``b""`` and
    let the SegBytes collapse to its concatenated concrete prefix.  The
    pattern is then enumerated against the collapsed bytes via the
    ground-bytes enumeration logic in this module's caller.

    Fixed slots see int codes (``collapsed[pos]`` is an int for ``bytes``);
    star slots see bytes slices (``collapsed[pos:pos+length]`` is ``bytes``).
    """
    from clausal.terms import VarSeg as _VarSeg

    var_segs = [s for s in ss.segments if isinstance(s, _VarSeg)]
    if not var_segs:
        return

    mark = trail.mark()
    bind_ok = True
    for vs in var_segs:
        if not unify(vs.var, b"", trail):
            bind_ok = False
            break
    if not bind_ok:
        trail.undo(mark)
        return

    collapsed = ss.__walk__()
    if not isinstance(collapsed, bytes):
        trail.undo(mark)
        return

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
    if type(d) is str:
        return                         # STAGE 2: an atom is not a sequence -- no solutions
    d = _unwrap(d)
    # Strings and bytes are handled directly (no list conversion) so that star
    # vars bind to substrings/subbytes preserving type.
    if not isinstance(d, (list, str, bytes)):
        # F040 / F041 (C3 audit): SegList and SegString are walked uniformly
        # here. Ground forms (walk → list / str / bytes) fall through to the
        # enumeration loop below.
        if isinstance(d, (SegList, SegString, SegBytes)):
            d_walked = _unwrap(d.__walk__())
            if isinstance(d_walked, (list, str, bytes)):
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
            elif isinstance(d_walked, SegBytes):
                yield from _segbytes_align(d_walked, segments, trail, target)
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
            # all fixed elements deref to chars and every star derefs
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
    # For strings, seq_getitem(d, pos) yields a CHAR and d[pos:pos+n] yields a
    # substring, so star vars bind to str — preserving the string type.
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
                    if not unify(v, seq_getitem(d, pos), trail):
                        ok = False
                        break
                    pos += 1
            else:  # star
                length = split[si]
                if not unify(val, _text_out(d[pos:pos + length]), trail):   # stage 1
                    ok = False
                pos += length
                si += 1
        if ok:
            yield True
        trail.undo(mark)
