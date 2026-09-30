"""Character/string builtins: char_type/2, char_code/2, upcase_atom/2,
downcase_atom/2, atom_length/2, atom_chars/2, atom_codes/2, atom_concat/3,
sub_atom/5, number_chars/2, number_codes/2.

These predicates are *relations* — they participate in unification and
backtracking (e.g. atom_concat(A, B, "hello") enumerates splits, char_type(C,
digit) enumerates digits).  Pure Python string methods can't do this.

Since strings now behave as character lists, the list predicates (append/3,
length/2, in_/2, etc.) work on strings directly.  For concatenation, splitting,
length, and membership, prefer the list predicates — they work uniformly on
both strings and lists.  The predicates here remain useful for ISO
compatibility, explicit type conversion (atom_chars/2), code-point operations
(atom_codes/2, char_code/2), character classification (char_type/2), and case
conversion (upcase_atom/2, downcase_atom/2).
"""

from __future__ import annotations

import re as _re
from decimal import Decimal as _Decimal
from typing import Any

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.atoms import (
    char_atom,
    is_atom as _term_is_atom,
    is_char_atom,
    mint,
    spelling,
)
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.builtins._registry import _builtin
from clausal.logic.builtins._helpers import (
    NIL_SPELLING, _is_empty_list, _check_nonneg_int_arg,
)
from clausal.logic.builtins.lists import _as_items

# ── C-accelerated inner loops (Option B: C helpers from Python generators) ───

try:
    from clausal.logic.builtins._chars_core import (
        char_type_find_types as _c_char_type_find_types,
        char_type_find_chars as _c_char_type_find_chars,
        atom_concat_split_find as _c_atom_concat_split_find,
        sub_atom_search as _c_sub_atom_search,
        sub_atom_enum as _c_sub_atom_enum,
        type_name_index as _c_type_name_index,
    )
except ImportError:
    _c_char_type_find_types = None
    _c_char_type_find_chars = None
    _c_atom_concat_split_find = None
    _c_sub_atom_search = None
    _c_sub_atom_enum = None
    _c_type_name_index = None


def _atom_to_str(val: Any) -> str | None:
    """Extract a string name from an atom value.

    This is THE funnel for "read an atom's spelling in a builtin" (spec
    §6.1).  Returns the spelling for a term atom — the arity-0 cell
    ``("foo",)`` — or ``__name__`` for a zero-arity PredicateMeta class,
    else ``None`` so the caller raises ``type_error(atom, …)``.

    THE FLIP retired the ``str``/``SegString`` arms F075 (C3 audit) added
    under the old "a str IS an atom" representation: a ``str`` and a ground
    ``SegString`` are STRINGS now, and a string in atom position is an ISO
    ``type_error(atom, …)`` — ``atom_length("abc", N)`` raises rather than
    answering 3 (spec §6.6).

    Task 15 item 2 (ISO alignment, Scryer-verified): the EMPTY list is the
    reserved atom ``'[]'`` — in every spelling, ``[]``/``""``/``b""`` — and
    its spelling is the two bracket characters, so ``atom_length([], 2)``
    and ``atom_chars([], ['[', ']'])`` answer as they do in Scryer.  The
    empty list is the ONE list this funnel reads: a non-empty one is the
    ``'.'/2`` compound and still raises.
    """
    if _term_is_atom(val):
        return spelling(val)
    if _is_empty_list(val):
        return NIL_SPELLING
    return None


# ── char_type/2 ───────────────────────────────────────────────────────────────

_CHAR_TYPES = {
    "alpha": str.isalpha,
    "digit": str.isdigit,
    "alnum": str.isalnum,
    "space": str.isspace,
    "upper": str.isupper,
    "lower": str.islower,
    "ascii": lambda c: ord(c) < 128,
    "punct": lambda c: not c.isalnum() and not c.isspace() and c.isprintable(),
    "print": str.isprintable,
    "control": lambda c: ord(c) < 32 or ord(c) == 127,
}

# Pre-compute ASCII chars for enumeration (Type bound, Char unbound).
_ASCII_CHARS = [chr(i) for i in range(128)]

# Pre-compute type membership for each char.
_CHAR_TO_TYPES: dict[str, list[str]] = {}
for _c in _ASCII_CHARS:
    _CHAR_TO_TYPES[_c] = [t for t, fn in _CHAR_TYPES.items() if fn(_c)]

# Pre-compute chars for each type.
_TYPE_TO_CHARS: dict[str, list[str]] = {}
for _t in _CHAR_TYPES:
    _TYPE_TO_CHARS[_t] = [c for c in _ASCII_CHARS if _CHAR_TYPES[_t](c)]


# F072 (C9 audit): Char-bound modes use full-Unicode classifiers
# (``str.isalpha`` etc.) — so ``char_type('α', alpha)`` succeeds. The
# Type-bound enumeration must therefore include non-ASCII chars to
# keep the relation consistent across modes. Lazy per-type cache: the
# first enumeration of a Unicode-eligible type walks the BMP once and
# memoises the full char list.
# F013 (A09): digit (str.isdigit: '٣', '²'…), space (NBSP '\xa0'…) and
# punct ('¡'…) are Unicode-aware in test-mode, so their enumeration must be
# too — otherwise char_type(C, digit) yields only the 10 ASCII digits while
# char_type('٣', digit) succeeds (mode-inconsistent). ascii/control stay
# ASCII: their classifiers are codepoint-bounded (< 128 / < 32 or == 127),
# so ASCII coverage is genuinely exhaustive.
_UNICODE_TYPES = {"alpha", "alnum", "upper", "lower", "print",
                  "digit", "space", "punct"}
_TYPE_TO_CHARS_UNICODE: dict[str, list[str]] = {}


def _type_to_chars_unicode(type_name: str) -> list[str]:
    """Return the full Unicode enumeration of chars matching *type_name*.

    Walks the Basic Multilingual Plane (0x0000-0xFFFF) on first call
    and caches the result. Returns the ASCII-only list for types not
    in ``_UNICODE_TYPES`` (``ascii``, ``control``) where the classifier
    is codepoint-bounded so ASCII coverage is already exhaustive.
    """
    if type_name not in _UNICODE_TYPES:
        return _TYPE_TO_CHARS.get(type_name, [])
    cached = _TYPE_TO_CHARS_UNICODE.get(type_name)
    if cached is not None:
        return cached
    fn = _CHAR_TYPES.get(type_name)
    if fn is None:
        return []
    # Walk the BMP — 65536 codepoints is fast (<100ms) and covers every
    # alphabetic / case / printable code point in common use. Surrogate
    # halves (0xD800-0xDFFF) are skipped because constructing ``chr``
    # of them yields invalid strings on some Python builds.
    chars = []
    for i in range(0x10000):
        if 0xD800 <= i <= 0xDFFF:
            continue
        c = chr(i)
        try:
            if fn(c):
                chars.append(c)
        except (TypeError, ValueError):
            continue
    _TYPE_TO_CHARS_UNICODE[type_name] = chars
    return chars


@_builtin("char_type", 2)
def _char_type__2(char, type_, trail, k):
    """char_type(Char, Type) — character classification as a relation.

    Both bound → test.  Char bound → enumerate types.  Type bound → enumerate
    chars.  Both unbound → instantiation_error.
    """
    vc = deref(char)
    vt = deref(type_)
    c_bound = not is_var(vc)
    t_bound = not is_var(vt)

    if not c_bound and not t_bound:
        raise LogicException(instantiation_error("char_type/2"))

    # Atoms-as-cells: Type is an atom, so it may arrive as a 1-tuple cell.
    # Read its spelling once here and classify on that; None means "bound to
    # something that is not an atom at all", which every mode rejects.
    type_name = spelling(vt) if t_bound and _term_is_atom(vt) else None

    if c_bound:
        if not is_char_atom(vc):
            return  # fail — not a single character
        vc = spelling(vc)

        if t_bound:
            # Both bound → test
            if type_name is None:
                return
            fn = _CHAR_TYPES.get(type_name)
            if fn is not None and fn(vc):
                yield None
        elif _c_char_type_find_types is not None:
            # Char bound, Type unbound → C-accelerated enumeration
            idx = 0
            while True:
                result = _c_char_type_find_types(vc, idx, type_, trail)
                if result is None:
                    break
                idx, mark = result
                yield None
                trail.undo(mark)
        else:
            # Char bound, Type unbound → enumerate matching types.
            # F014 (A09): _CHAR_TO_TYPES is a precomputed ASCII table, so a
            # non-ASCII char is absent → test each classifier dynamically
            # (mirrors the C helper), otherwise char_type('α', T) would
            # enumerate nothing on a build without the C extension.
            matching = _CHAR_TO_TYPES.get(vc)
            if matching is None:
                matching = [t for t, fn in _CHAR_TYPES.items() if fn(vc)]
            for t_name in matching:
                mark = trail.mark()
                if unify(type_, mint(t_name), trail):
                    yield None
                trail.undo(mark)
    elif (type_name in _UNICODE_TYPES) or _c_char_type_find_chars is None \
            or _c_type_name_index is None:
        # Type bound, Char unbound → Python enumeration. F072 (C9
        # audit): the C-accelerator only knows about ASCII, so we take
        # the Python path for any type whose Char-bound classifier
        # supports Unicode (alpha/alnum/upper/lower/print) — this keeps
        # the test-mode and enumeration-mode relations consistent.
        if type_name is None:
            return
        chars = _type_to_chars_unicode(type_name)
        if not chars:
            return
        for c in chars:
            mark = trail.mark()
            if unify(char, char_atom(c), trail):
                yield None
            trail.undo(mark)
    else:
        # Type bound, Char unbound → C-accelerated ASCII enumeration
        # (used for types whose classifier is codepoint-bounded ASCII,
        # e.g. ``ascii``, ``control``).
        if type_name is None:
            return
        tidx = _c_type_name_index(type_name)
        if tidx < 0:
            return
        idx = 0
        while True:
            result = _c_char_type_find_chars(tidx, idx, char, trail)
            if result is None:
                break
            idx, mark = result
            yield None
            trail.undo(mark)


# ── char_code/2 ──────────────────────────────────────────────────────────────

@_builtin("char_code", 2)
def _char_code__2(char, code, trail, k):
    """char_code(Char, Code) — bidirectional char ↔ integer code point.

    Char bound → unify Code with ord(Char).  Code bound → unify Char with
    chr(Code).  Both bound → test equality.  Both unbound → instantiation_error.
    """
    vc = deref(char)
    vn = deref(code)
    c_bound = not is_var(vc)
    n_bound = not is_var(vn)

    if not c_bound and not n_bound:
        raise LogicException(instantiation_error("char_code/2"))

    if c_bound:
        if not is_char_atom(vc):
            raise LogicException(type_error("character", vc, "char_code/2"))
        expected = ord(spelling(vc))
        mark = trail.mark()
        if unify(code, expected, trail):
            yield None
        trail.undo(mark)
    elif n_bound:
        # A09-F015 / A01-D001(c): a bool code is rejected (char_code(C, True)
        # must not build '\x01').
        if not isinstance(vn, int) or isinstance(vn, bool):
            raise LogicException(type_error("integer", vn, "char_code/2"))
        if not (0 <= vn < 0x110000):
            # ISO 8.16.6.3 d (Scryer-verified): not a character code.  This
            # used to FAIL silently.
            from clausal.logic.exceptions import representation_error  # noqa: PLC0415
            raise LogicException(
                representation_error("character_code", "char_code/2"))
        mark = trail.mark()
        if unify(char, char_atom(chr(vn)), trail):
            yield None
        trail.undo(mark)


# ── upcase_atom/2, downcase_atom/2 ────────────────────────────────────────────

@_builtin("upcase_atom", 2)
def _upcase_atom__2(atom, upper, trail, k):
    """upcase_atom(Atom, Upper) — unify Upper with uppercase version of Atom."""
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("upcase_atom/2"))
    atom_str = _atom_to_str(va)
    if atom_str is None:
        raise LogicException(type_error("atom", va, "upcase_atom/2"))
    mark = trail.mark()
    if unify(upper, mint(atom_str.upper()), trail):
        yield None
    trail.undo(mark)


@_builtin("downcase_atom", 2)
def _downcase_atom__2(atom, lower, trail, k):
    """downcase_atom(Atom, Lower) — unify Lower with lowercase version of Atom."""
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("downcase_atom/2"))
    atom_str = _atom_to_str(va)
    if atom_str is None:
        raise LogicException(type_error("atom", va, "downcase_atom/2"))
    mark = trail.mark()
    if unify(lower, mint(atom_str.lower()), trail):
        yield None
    trail.undo(mark)


def _refuse_non_list(val, who):
    """ISO 8.16.4.3 / 8.16.5.3 / 8.16.7.3 / 8.16.8.3 (Scryer-verified): a
    PARTIAL list -- ``[a | T]`` -- is an instantiation error, anything else
    that is not a list a ``type_error(list, L)``.  A partial list used to get
    the type error."""
    from clausal.terms import SegList, SegString, SegBytes  # noqa: PLC0415
    if isinstance(val, (SegList, SegString, SegBytes)):
        raise LogicException(instantiation_error(who))
    raise LogicException(type_error("list", val, who))


# ── atom_length/2 ────────────────────────────────────────────────────────────

@_builtin("atom_length", 2)
def _atom_length__2(atom, length, trail, k):
    """atom_length(Atom, length) — unify length with the length of Atom.

    Note: length/2 now accepts strings directly, so prefer ``length("hello", N)``
    for new code.  atom_length is kept for ISO compatibility.
    """
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("atom_length/2"))
    atom_str = _atom_to_str(va)
    if atom_str is None:
        raise LogicException(type_error("atom", va, "atom_length/2"))
    # ISO 8.16.1.3 c, d (Scryer-verified); used to FAIL silently.
    _check_nonneg_int_arg(deref(length), "atom_length/2")
    mark = trail.mark()
    if unify(length, len(atom_str), trail):
        yield None
    trail.undo(mark)


# ── atom_chars/2 ─────────────────────────────────────────────────────────────

@_builtin("atom_chars", 2)
def _atom_chars__2(atom, chars, trail, k):
    """atom_chars(Atom, Chars) — bidirectional atom ↔ char-list conversion.

    Atom bound → unify Chars with list(Atom).
    Chars bound (list of length-1 strings) → unify Atom with "".join(Chars).
    Both bound → test equality.
    """
    va = deref(atom)
    vc = deref(chars)
    a_bound = not is_var(va)
    c_bound = not is_var(vc)

    if a_bound:
        atom_str = _atom_to_str(va)
        if atom_str is None:
            raise LogicException(type_error("atom", va, "atom_chars/2"))
        mark = trail.mark()
        if unify(chars, [char_atom(c) for c in atom_str], trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        # F017 (A09): a str IS a char list and a bytes IS a code list under
        # strings-as-lists / bytes-as-codes, so route through _as_items
        # (str/bytes/ground Seg* → element list) rather than a bare
        # isinstance-list check. A str element then validates as a character.
        items = _as_items(vc)
        if items is None:
            _refuse_non_list(vc, "atom_chars/2")
        elems = []
        for elem in items:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_chars/2"))
            if not is_char_atom(e):
                raise LogicException(type_error("character", e, "atom_chars/2"))
            elems.append(spelling(e))
        mark = trail.mark()
        if unify(atom, mint("".join(elems)), trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("atom_chars/2"))


# ── atom_codes/2 ─────────────────────────────────────────────────────────────

@_builtin("atom_codes", 2)
def _atom_codes__2(atom, codes, trail, k):
    """atom_codes(Atom, Codes) — bidirectional atom ↔ code-point-list conversion.

    Atom bound → unify Codes with [ord(c) for c in Atom].
    Codes bound (list of ints) → unify Atom with "".join(chr(c) for c in Codes).
    """
    va = deref(atom)
    vc = deref(codes)
    a_bound = not is_var(va)
    c_bound = not is_var(vc)

    if a_bound:
        atom_str = _atom_to_str(va)
        if atom_str is None:
            raise LogicException(type_error("atom", va, "atom_codes/2"))
        mark = trail.mark()
        if unify(codes, [ord(c) for c in atom_str], trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        items = _as_items(vc)  # F017: bytes/str/ground Seg* → element list
        if items is None:
            _refuse_non_list(vc, "atom_codes/2")
        elems = []
        for elem in items:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_codes/2"))
            if not isinstance(e, int):
                raise LogicException(type_error("integer", e, "atom_codes/2"))
            if not (0 <= e < 0x110000):
                # ISO / Scryer: not a character code.  This used to FAIL
                # silently.
                from clausal.logic.exceptions import representation_error  # noqa: PLC0415
                raise LogicException(
                    representation_error("character_code", "atom_codes/2"))
            elems.append(chr(e))
        mark = trail.mark()
        if unify(atom, mint("".join(elems)), trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("atom_codes/2"))


# ── atom_concat/3 ─────────────────────────────────────────────────────────────

@_builtin("atom_concat", 3)
def _atom_concat__3(a, b, c, trail, k):
    """atom_concat(A, B, C) — string concatenation as a relation.

    A+B bound → forward concat.  C bound + A or B bound → prefix/suffix check.
    C bound + both A,B unbound → enumerate all splits.

    Note: append/3 now accepts strings directly, so prefer
    ``append("hel", "lo", X)`` for new code.  atom_concat is kept for ISO
    compatibility and for cases where string-typed results are required
    (append may return a list when inputs are mixed).
    """
    va, vb, vc = deref(a), deref(b), deref(c)
    # A09-F031 / F077: validate every BOUND arg is atom-shaped up front,
    # regardless of mode. Previously the check lived only in the final
    # instantiation branch, so a check-mode call like
    # atom_concat(12, "a", "12a") silently failed instead of raising the same
    # type_error(atom, 12) the open mode does.
    for arg_val in (va, vb, vc):
        if not is_var(arg_val) and _atom_to_str(arg_val) is None:
            raise LogicException(type_error("atom", arg_val, "atom_concat/3"))
    sa = _atom_to_str(va) if not is_var(va) else None
    sb = _atom_to_str(vb) if not is_var(vb) else None
    sc = _atom_to_str(vc) if not is_var(vc) else None
    a_bound = sa is not None
    b_bound = sb is not None
    c_bound = sc is not None

    if a_bound and b_bound:
        # Forward: A + B → C
        mark = trail.mark()
        if unify(c, mint(sa + sb), trail):
            yield None
        trail.undo(mark)
    elif c_bound and a_bound:
        # C and A bound: check prefix, unify remainder
        if sc.startswith(sa):
            mark = trail.mark()
            if unify(b, mint(sc[len(sa):]), trail):
                yield None
            trail.undo(mark)
    elif c_bound and b_bound:
        # C and B bound: check suffix, unify prefix
        if sc.endswith(sb):
            mark = trail.mark()
            if unify(a, mint(sc[:len(sc) - len(sb)]), trail):
                yield None
            trail.undo(mark)
    elif c_bound and _c_atom_concat_split_find is not None:
        # C bound, A and B unbound: C-accelerated split enumeration
        idx = 0
        while True:
            result = _c_atom_concat_split_find(sc, idx, a, b, trail)
            if result is None:
                break
            idx, mark = result
            yield None
            trail.undo(mark)
    elif c_bound:
        # C bound, A and B unbound: enumerate all splits
        for i in range(len(sc) + 1):
            mark = trail.mark()
            if unify(a, mint(sc[:i]), trail) and unify(b, mint(sc[i:]), trail):
                yield None
            trail.undo(mark)
    else:
        # Non-atom bound args are already rejected up front (F031/F077), so
        # reaching here means too few args are bound to compute C.
        raise LogicException(instantiation_error("atom_concat/3"))


# ── sub_atom/5 ────────────────────────────────────────────────────────────────

@_builtin("sub_atom", 5)
def _sub_atom__5(atom, before, length, after, sub, trail, k):
    """sub_atom(Atom, Before, length, After, Sub) — substring relation.

    Atom must be bound.  Relates Atom to its substrings with position info:
    Before + length + After = len(Atom), Sub = Atom[Before:Before+length].
    """
    va = deref(atom)
    if is_var(va):
        raise LogicException(instantiation_error("sub_atom/5"))
    va_str = _atom_to_str(va)
    if va_str is None:
        raise LogicException(type_error("atom", va, "sub_atom/5"))

    va = va_str
    n = len(va)
    # ISO 8.16.3.3 (Scryer-verified): a bound Before/Length/After must be a
    # non-negative integer (A09-F015 / A01-D001(c): a bool is not one, True
    # is not 1) and a bound Sub an atom.  These used to FAIL silently.
    for p in (before, length, after):
        _check_nonneg_int_arg(deref(p), "sub_atom/5")
    vs = deref(sub)
    if not is_var(vs) and _atom_to_str(vs) is None:
        raise LogicException(type_error("atom", vs, "sub_atom/5"))

    # Optimization: if Sub is bound to an atom, use str.find to locate
    # occurrences.  Atoms-as-cells: search on the spelling, so a 1-tuple
    # cell atom takes the same fast path a ``str`` atom does.
    vs_str = spelling(vs) if not is_var(vs) and _term_is_atom(vs) else None
    if vs_str is not None:
        if _c_sub_atom_search is not None:
            idx = 0
            while True:
                result = _c_sub_atom_search(va, vs_str, idx, before, length, after, trail)
                if result is None:
                    break
                idx, mark = result
                yield None
                trail.undo(mark)
            return
        sub_len = len(vs_str)
        start = 0
        while True:
            pos = va.find(vs_str, start)
            if pos == -1:
                break
            b, l, a = pos, sub_len, n - pos - sub_len
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail)):
                yield None
            trail.undo(mark)
            start = pos + 1
        return

    # General case: enumerate (Before, length) pairs.
    # Narrow ranges when Before or length is bound.
    vb = deref(before)
    vl = deref(length)

    if _c_sub_atom_enum is not None:
        # Early exit for out-of-range bound values (avoids O(n^2) wasted unifications)
        if not is_var(vb) and isinstance(vb, int) and (vb < 0 or vb > n):
            return
        if not is_var(vl) and isinstance(vl, int) and vl < 0:
            return
        vb_fixed = vb if (not is_var(vb) and isinstance(vb, int)) else -1
        vl_fixed = vl if (not is_var(vl) and isinstance(vl, int)) else -1
        flat = 0
        while True:
            result = _c_sub_atom_enum(
                va, flat, before, length, after, sub,
                vb_fixed, vl_fixed, trail)
            if result is None:
                break
            flat, mark = result
            yield None
            trail.undo(mark)
        return

    if not is_var(vb) and isinstance(vb, int):
        b_range = range(vb, vb + 1) if 0 <= vb <= n else range(0)
    else:
        b_range = range(n + 1)

    for b in b_range:
        if not is_var(vl) and isinstance(vl, int):
            if vl < 0 or b + vl > n:
                continue
            l_range = range(vl, vl + 1)
        else:
            l_range = range(n - b + 1)

        for l in l_range:
            a = n - b - l
            s = va[b:b + l]
            mark = trail.mark()
            if (unify(before, b, trail) and unify(length, l, trail)
                    and unify(after, a, trail) and unify(sub, mint(s), trail)):
                yield None
            trail.undo(mark)


# ── number_chars/2 ──────────────────────────────────────────────────────────────

#: ISO 6.4.1 layout, and the characters of a symbol-char name token (6.4.2)
_LAYOUT = frozenset(" \t\n\r\v\f")
_SYMBOL_CHARS = frozenset("+-*/\\^<>=~:.?@#&$")


class _NumberSyntax(Exception):
    """A number text that is not one: *kind* is Scryer's syntax_error
    formal (``unexpected_end_of_file``, ``unexpected_char``, ...) and
    *located* whether Scryer's context carries a position (``PI:0``)."""

    def __init__(self, kind: str, located: bool):
        super().__init__(kind)
        self.kind = kind
        self.located = located


def _eof():
    return _NumberSyntax("unexpected_end_of_file", False)


def _bad_char():
    return _NumberSyntax("unexpected_char", True)


def _skip_layout(s: str, i: int) -> int:
    """*i* moved past layout and comments; an unterminated ``/*`` is the
    end of the text."""
    n = len(s)
    while i < n:
        c = s[i]
        if c in _LAYOUT:
            i += 1
        elif c == "%":
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
        elif c == "/" and s.startswith("/*", i):
            j = s.find("*/", i + 2)
            if j < 0:
                raise _eof()
            i = j + 2
        else:
            break
    return i


def _digits(s: str, i: int, ok) -> int:
    """End of a digit run (``_`` digit groups included) starting at *i*."""
    n = len(s)
    j = i
    while j < n and ok(s[j]):
        j += 1
        if j + 1 < n and s[j] == "_" and ok(s[j + 1]):
            j += 1
    return j


def _char_code_token(s: str, j: int):
    """``0'c`` from its character at *j*: ``(code, end)``."""
    n = len(s)
    if j >= n:
        raise _eof()
    ch = s[j]
    if ch == "'":
        if j + 1 >= n:
            raise _eof()
        if s[j + 1] == "'":
            return 39, j + 2
        raise _bad_char()
    if ch == "\\":
        if j + 1 >= n:
            raise _eof()
        e = s[j + 1]
        if e in _CHAR_ESCAPES:
            return ord(_CHAR_ESCAPES[e]), j + 2
        if e == "x" or e in "01234567":
            base, k = (16, j + 2) if e == "x" else (8, j + 1)
            ok = (lambda c: c in "0123456789abcdefABCDEF") if base == 16 \
                else (lambda c: c in "01234567")
            m = k
            while m < n and ok(s[m]):
                m += 1
            if m == k or m >= n:
                raise _eof() if m >= n else _bad_char()
            if s[m] != "\\":
                raise _bad_char()
            code = int(s[k:m], base)
            if code >= 0x110000:
                raise _bad_char()
            return code, m + 1
        raise _bad_char()
    if ch == "\n":
        raise _bad_char()
    return ord(ch), j + 1


def _number_token_at(s: str, i: int):
    """The number token starting at the digit ``s[i]``: ``(value, end)``."""
    n = len(s)
    if s[i] == "0" and i + 1 < n:
        c1 = s[i + 1]
        if c1 == "'":
            return _char_code_token(s, i + 2)
        radix = {"x": 16, "o": 8, "b": 2}.get(c1)
        if radix is not None:
            ok = {16: lambda c: c in "0123456789abcdefABCDEF",
                  8: lambda c: c in "01234567",
                  2: lambda c: c in "01"}[radix]
            j = i + 2                # no digit groups here (Scryer)
            while j < n and ok(s[j]):
                j += 1
            if j > i + 2:
                return int(s[i + 2:j], radix), j
            if i + 2 >= n:
                raise _eof()
            return 0, i + 1          # ``0`` then garbage
    j = _digits(s, i, lambda c: "0" <= c <= "9")
    if j + 1 < n and s[j] == "." and "0" <= s[j + 1] <= "9":
        k = j + 1
        while k < n and "0" <= s[k] <= "9":
            k += 1
        if k < n and s[k] in "eE":
            m = k + 1
            if m < n and s[m] in "+-":
                m += 1
            if m < n and "0" <= s[m] <= "9":
                while m < n and "0" <= s[m] <= "9":
                    m += 1
                k = m
        value = float(s[i:k].replace("_", ""))
        if value in (float("inf"), float("-inf")):
            raise _NumberSyntax("infinite_float", True)
        return value, k
    text = s[i:j].replace("_", "")
    # through Decimal: CPython caps int(str) at ~4300 digits
    return (int(_Decimal(text)) if len(text) > 4000 else int(text)), j


def _other_token_end(s: str, i: int) -> int:
    """End of the non-number token at *i*, as Scryer's number reader
    consumes it; raises for a character that starts no such token."""
    n = len(s)
    c = s[i]
    if c.isalpha() and c.islower():
        j = i + 1
        while j < n and (s[j].isalnum() or s[j] == "_"):
            j += 1
        return j
    if c in _SYMBOL_CHARS:
        j = i + 1
        while j < n and s[j] in _SYMBOL_CHARS:
            j += 1
        return j
    if c == "'":
        j = i + 1
        while True:
            k = s.find("'", j)
            if k < 0:
                raise _eof()
            if k + 1 < n and s[k + 1] == "'":
                j = k + 2
                continue
            return k + 1
    if c in "!;":
        if i + 1 == n:
            raise _NumberSyntax("cannot_parse_big_int", True)
        raise _bad_char()
    raise _bad_char()                # a variable, punctuation, a quote ...


def _read_number_text(s: str):
    """The number *s* spells, read as Scryer's number_chars/2 reads it
    (ISO 8.16.7): layout and comments may lead, a ``-`` may stand before
    the number token (layout between them allowed), and nothing may
    follow it.  Anything else raises :class:`_NumberSyntax` with Scryer's
    formal: the text ending before a number was read is
    ``unexpected_end_of_file``, a character where none may be is
    ``unexpected_char`` (measured against Scryer 2026-09-30)."""
    n = len(s)
    i = _skip_layout(s, 0)
    if i == n:
        raise _eof()
    neg = False
    if s[i] == "-" and (i + 1 == n or s[i + 1] not in _SYMBOL_CHARS):
        neg = True
        i = _skip_layout(s, i + 1)
        if i == n:
            raise _eof()
    if "0" <= s[i] <= "9":
        value, end = _number_token_at(s, i)
        if end < n:
            raise _bad_char()
        return -value if neg else value
    end = _other_token_end(s, i)
    raise _eof() if end == n else _bad_char()


def _parse_number_chars(s: str, who: str):
    """*s* read as a number, or ``syntax_error(Kind)`` in Scryer's shape:
    the context is ``who`` (``number_chars/2``), or ``who:0`` for an error
    Scryer locates."""
    try:
        return _read_number_text(s)
    except _NumberSyntax as exc:
        from clausal.logic.exceptions import _error  # noqa: PLC0415
        name, _, arity = who.rpartition("/")
        pi = ("/", mint(name), int(arity))
        context = (":", pi, 0) if exc.located else pi
        raise LogicException(
            _error(("syntax_error", mint(exc.kind)), context)) from None


def _ground_items(v):
    """The element list of *v* when it is a proper list with no unbound
    element, else None."""
    items = _as_items(v)
    if items is None:
        return None
    items = [deref(e) for e in items]
    if any(is_var(e) for e in items):
        return None
    return items


@_builtin("number_chars", 2)
def _number_chars__2(number, chars, trail, k):
    """number_chars(Number, Chars) — bidirectional number ↔ char-list conversion.

    Chars a ground list → it is READ as a number (ISO 8.16.7, as Scryer
    reads it: leading layout, a ``-`` before the token, ``0x1A``, ``0'a``,
    ``1_000``) and unified with Number, so ``number_chars(1, ['0', '1'])``
    holds.  Text that is not a number raises ``syntax_error(Kind)`` with
    Scryer's formal (``unexpected_end_of_file`` / ``unexpected_char``).
    Otherwise Number must be a number and Chars unifies with its text.

    A09-F030 (2026-07): this used to parse with Python's ``int()`` /
    ``float()`` and FAIL on text they rejected, accepting ``" 1 "``,
    ``"+1"``, ``"1e5"`` and ``"inf"`` besides; ruled 2026-09-30 to follow
    ISO and Scryer.
    """
    vn = deref(number)
    vc = deref(chars)
    n_bound = not is_var(vn)
    if n_bound and (isinstance(vn, bool) or not isinstance(vn, (int, float))):
        raise LogicException(type_error("number", vn, "number_chars/2"))
    items = _ground_items(vc) if not is_var(vc) else None
    if items is not None:
        elems = []
        for e in items:
            if not is_char_atom(e):
                raise LogicException(type_error("character", e, "number_chars/2"))
            elems.append(spelling(e))
        parsed = _parse_number_chars("".join(elems), "number_chars/2")
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
        return
    if n_bound:
        mark = trail.mark()
        if unify(chars, [char_atom(c) for c in _number_text(vn)], trail):
            yield None
        trail.undo(mark)
        return
    if not is_var(vc):
        _refuse_partial(vc, "number_chars/2", is_char_atom, "character")
    raise LogicException(instantiation_error("number_chars/2"))


def _refuse_partial(vc, who, is_elem, elem_type):
    """Number unbound and a Chars/Codes that is not a ground list: a
    non-list is refused as before, a bound element of the wrong kind is
    ``type_error(elem_type, E)``; the caller then raises the
    instantiation error."""
    items = _as_items(vc)
    if items is None:
        _refuse_non_list(vc, who)
        return
    for e in items:
        e = deref(e)
        if is_var(e):
            return
        if not is_elem(e):
            raise LogicException(type_error(elem_type, e, who))


def _is_code(e) -> bool:
    return isinstance(e, int) and not isinstance(e, bool)


# ── number_codes/2 ──────────────────────────────────────────────────────────────

@_builtin("number_codes", 2)
def _number_codes__2(number, codes, trail, k):
    """number_codes(Number, Codes) — bidirectional number ↔ code-point-list.

    As number_chars/2 over character codes: a ground Codes list is READ as
    a number, and text that is not one raises Scryer's
    ``syntax_error(Kind)`` (A09-F030's silent failure, ruled 2026-09-30).
    """
    vn = deref(number)
    vc = deref(codes)
    n_bound = not is_var(vn)
    if n_bound and (isinstance(vn, bool) or not isinstance(vn, (int, float))):
        raise LogicException(type_error("number", vn, "number_codes/2"))
    items = _ground_items(vc) if not is_var(vc) else None
    if items is not None:
        elems = []
        for e in items:
            if not _is_code(e):
                raise LogicException(type_error("integer", e, "number_codes/2"))
            if not (0 <= e < 0x110000):
                # ISO / Scryer: not a character code.  This used to FAIL
                # silently.
                from clausal.logic.exceptions import representation_error  # noqa: PLC0415
                raise LogicException(
                    representation_error("character_code", "number_codes/2"))
            elems.append(chr(e))
        parsed = _parse_number_chars("".join(elems), "number_codes/2")
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
        return
    if n_bound:
        mark = trail.mark()
        if unify(codes, [ord(c) for c in _number_text(vn)], trail):
            yield None
        trail.undo(mark)
        return
    if not is_var(vc):
        _refuse_partial(vc, "number_codes/2", _is_code, "integer")
    raise LogicException(instantiation_error("number_codes/2"))


# ── atom_number/2 ───────────────────────────────────────────────────────────────

#: A number token as Prolog source writes one (ISO 6.4.4/6.4.5): an
#: optional ``-`` directly before it; decimal, ``0x``/``0o``/``0b`` or
#: ``0'c`` integers; a float needs a fraction and may carry an exponent.
_NUMBER_TOKEN = _re.compile(
    r"-?(?:0x[0-9a-fA-F]+|0o[0-7]+|0b[01]+|0'(?:\\.|.)"
    r"|[0-9]+\.[0-9]+(?:[eE][+-]?[0-9]+)?|[0-9]+)\Z", _re.S)


#: ``0'\\c`` escapes (ISO 6.4.2.1 plus Scryer's ``\\e``, ``\\s``)
_CHAR_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", "'": "'", "a": "\a",
                 "b": "\b", "f": "\f", "v": "\v", "r": "\r", "0": "\0",
                 "e": "\x1b", "s": " ", '"': '"', "`": "`"}


def _parse_number_token(text: str):
    """The number *text* spells as a Prolog number token, else None."""
    if not _NUMBER_TOKEN.match(text):
        return None
    neg = text.startswith("-")
    body = text[1:] if neg else text
    if body.startswith("0'"):
        ch = body[2:]
        if ch.startswith("\\"):
            if ch[1:] not in _CHAR_ESCAPES:
                return None
            ch = _CHAR_ESCAPES[ch[1:]]
        value = ord(ch)
    elif body[:2] in ("0x", "0o", "0b"):
        value = int(body[2:], {"0x": 16, "0o": 8, "0b": 2}[body[:2]])
    elif "." in body:
        value = float(body)
    else:
        # through Decimal: CPython caps int(str) at ~4300 digits
        value = int(_Decimal(body)) if len(body) > 4000 else int(body)
    return -value if neg else value


def _number_text(n) -> str:
    """*n* as a Prolog number token that both :func:`_parse_number_token`
    (atom_number/2) and :func:`_read_number_text` (number_chars/2) read
    back: a float always has its fraction (``1.0e+22``, not Python's
    ``1e+22``)."""
    if type(n) is int and abs(n) >= 10 ** 4000:
        return str(_Decimal(n))     # CPython caps str(int) at ~4300 digits
    s = str(n)
    if type(n) is float and "e" in s:
        mant, exp = s.split("e")
        if "." not in mant:
            s = f"{mant}.0e{exp}"
    return s


@_builtin("atom_number", 2)
def _atom_number__2(atom, number, trail, k):
    """atom_number(Atom, Number) -- Atom is the text of Number.

    Atom bound: it must be an atom, and it is read as a Prolog number token
    (an optional ``-`` directly before it; ``0x1A``, ``0'a``; a float needs
    its fraction).  Text that is not a number FAILS -- the predicate asks
    whether the atom is a number, it does not raise a syntax error -- and so
    does surrounding layout.  Atom unbound: Number must be a number, and
    Atom is its text (as number_codes/2 writes it).  Both unbound is
    instantiation_error; a bound non-atom Atom is type_error(atom, A); an
    unbound Atom beside a non-number is type_error(number, N).  It did not
    exist (existence_error(procedure, atom_number/2))."""
    va = deref(atom)
    if is_var(va):
        vn = deref(number)
        if is_var(vn):
            raise LogicException(instantiation_error("atom_number/2"))
        if isinstance(vn, bool) or not isinstance(vn, (int, float)):
            raise LogicException(type_error("number", vn, "atom_number/2"))
        mark = trail.mark()
        if unify(atom, mint(_number_text(vn)), trail):
            yield None
        trail.undo(mark)
        return
    if not _term_is_atom(va):
        raise LogicException(type_error("atom", va, "atom_number/2"))
    value = _parse_number_token(spelling(va))
    if value is None:
        return
    mark = trail.mark()
    if unify(number, value, trail):
        yield None
    trail.undo(mark)
