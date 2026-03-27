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

from typing import Any

from clausal.logic.variables import deref, is_var, unify
from clausal.logic.predicate import PredicateMeta
from clausal.logic.exceptions import LogicException, instantiation_error, type_error
from clausal.logic.builtins._registry import _builtin


def _atom_to_str(val: Any) -> str | None:
    """Extract a string name from an atom value.

    Returns the string for str atoms, __name__ for zero-arity PredicateMeta
    classes, or None if val is not an atom.
    """
    if isinstance(val, str):
        return val
    if isinstance(val, PredicateMeta) and not val._fields:
        return val.__name__
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

    if c_bound:
        if not isinstance(vc, str) or len(vc) != 1:
            return  # fail — not a single character

        if t_bound:
            # Both bound → test
            if not isinstance(vt, str):
                return
            fn = _CHAR_TYPES.get(vt)
            if fn is not None and fn(vc):
                yield None
        else:
            # Char bound, Type unbound → enumerate matching types
            for t_name in _CHAR_TO_TYPES.get(vc, []):
                mark = trail.mark()
                if unify(type_, t_name, trail):
                    yield None
                trail.undo(mark)
    else:
        # Type bound, Char unbound → enumerate matching chars
        if not isinstance(vt, str):
            return
        chars = _TYPE_TO_CHARS.get(vt)
        if chars is None:
            return
        for c in chars:
            mark = trail.mark()
            if unify(char, c, trail):
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
        if not isinstance(vc, str) or len(vc) != 1:
            raise LogicException(type_error("character", vc, "char_code/2"))
        expected = ord(vc)
        mark = trail.mark()
        if unify(code, expected, trail):
            yield None
        trail.undo(mark)
    elif n_bound:
        if not isinstance(vn, int) or vn < 0:
            raise LogicException(type_error("integer", vn, "char_code/2"))
        mark = trail.mark()
        if unify(char, chr(vn), trail):
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
    if unify(upper, atom_str.upper(), trail):
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
    if unify(lower, atom_str.lower(), trail):
        yield None
    trail.undo(mark)


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
        if unify(chars, list(atom_str), trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "atom_chars/2"))
        # Deref each element and validate
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_chars/2"))
            if not isinstance(e, str) or len(e) != 1:
                raise LogicException(type_error("character", e, "atom_chars/2"))
            elems.append(e)
        mark = trail.mark()
        if unify(atom, "".join(elems), trail):
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
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "atom_codes/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("atom_codes/2"))
            if not isinstance(e, int):
                raise LogicException(type_error("integer", e, "atom_codes/2"))
            elems.append(chr(e))
        mark = trail.mark()
        if unify(atom, "".join(elems), trail):
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
    sa = _atom_to_str(va) if not is_var(va) else None
    sb = _atom_to_str(vb) if not is_var(vb) else None
    sc = _atom_to_str(vc) if not is_var(vc) else None
    a_bound = sa is not None
    b_bound = sb is not None
    c_bound = sc is not None

    if a_bound and b_bound:
        # Forward: A + B → C
        mark = trail.mark()
        if unify(c, sa + sb, trail):
            yield None
        trail.undo(mark)
    elif c_bound and a_bound:
        # C and A bound: check prefix, unify remainder
        if sc.startswith(sa):
            mark = trail.mark()
            if unify(b, sc[len(sa):], trail):
                yield None
            trail.undo(mark)
    elif c_bound and b_bound:
        # C and B bound: check suffix, unify prefix
        if sc.endswith(sb):
            mark = trail.mark()
            if unify(a, sc[:len(sc) - len(sb)], trail):
                yield None
            trail.undo(mark)
    elif c_bound:
        # C bound, A and B unbound: enumerate all splits
        for i in range(len(sc) + 1):
            mark = trail.mark()
            if unify(a, sc[:i], trail) and unify(b, sc[i:], trail):
                yield None
            trail.undo(mark)
    else:
        # C unbound and not enough info to compute it
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
    vs = deref(sub)

    # Optimization: if Sub is bound, use str.find to locate occurrences.
    if not is_var(vs) and isinstance(vs, str):
        sub_len = len(vs)
        start = 0
        while True:
            pos = va.find(vs, start)
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
                    and unify(after, a, trail) and unify(sub, s, trail)):
                yield None
            trail.undo(mark)


# ── number_chars/2 ──────────────────────────────────────────────────────────────

@_builtin("number_chars", 2)
def _number_chars__2(number, chars, trail, k):
    """number_chars(Number, Chars) — bidirectional number ↔ char-list conversion.

    Number bound → unify Chars with list(str(Number)).
    Chars bound (list of single-char strings) → parse as int or float.
    Both bound → test equality.
    """
    vn = deref(number)
    vc = deref(chars)
    n_bound = not is_var(vn)
    c_bound = not is_var(vc)

    if n_bound:
        if isinstance(vn, bool) or not isinstance(vn, (int, float)):
            raise LogicException(type_error("number", vn, "number_chars/2"))
        mark = trail.mark()
        if unify(chars, list(str(vn)), trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "number_chars/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("number_chars/2"))
            if not isinstance(e, str) or len(e) != 1:
                raise LogicException(type_error("character", e, "number_chars/2"))
            elems.append(e)
        s = "".join(elems)
        try:
            parsed = int(s)
        except ValueError:
            try:
                parsed = float(s)
            except ValueError:
                return  # fail — not a valid number
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("number_chars/2"))


# ── number_codes/2 ──────────────────────────────────────────────────────────────

@_builtin("number_codes", 2)
def _number_codes__2(number, codes, trail, k):
    """number_codes(Number, Codes) — bidirectional number ↔ code-point-list.

    Number bound → unify Codes with [ord(c) for c in str(Number)].
    Codes bound (list of ints) → join as chars, parse as int or float.
    """
    vn = deref(number)
    vc = deref(codes)
    n_bound = not is_var(vn)
    c_bound = not is_var(vc)

    if n_bound:
        if isinstance(vn, bool) or not isinstance(vn, (int, float)):
            raise LogicException(type_error("number", vn, "number_codes/2"))
        mark = trail.mark()
        if unify(codes, [ord(c) for c in str(vn)], trail):
            yield None
        trail.undo(mark)
    elif c_bound:
        if not isinstance(vc, list):
            raise LogicException(type_error("list", vc, "number_codes/2"))
        elems = []
        for elem in vc:
            e = deref(elem)
            if is_var(e):
                raise LogicException(instantiation_error("number_codes/2"))
            if not isinstance(e, int):
                raise LogicException(type_error("integer", e, "number_codes/2"))
            elems.append(chr(e))
        s = "".join(elems)
        try:
            parsed = int(s)
        except ValueError:
            try:
                parsed = float(s)
            except ValueError:
                return
        mark = trail.mark()
        if unify(number, parsed, trail):
            yield None
        trail.undo(mark)
    else:
        raise LogicException(instantiation_error("number_codes/2"))
